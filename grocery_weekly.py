#!/usr/bin/env python3
import os, smtplib, sys, time
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

YOUR_EMAIL         = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
POSTAL_CODE        = "H1H4J5"
MIN_DISCOUNT_PCT   = 50

TARGET_STORES = [
    "maxi","super c","iga","walmart","metro","adonis",
    "kim phat","euro marche","marche richelieu","marche bonichoix",
    "marche tradition","rachelle","mayrand","provigo"
]

FLIPP_URL = "https://backflipp.wishabi.com/flipp/items/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/",
}

SEARCH_KEYWORDS = [
    "meat","chicken","beef","pork","fish","seafood","salmon","shrimp",
    "fruit","vegetable","dairy","cheese","eggs","milk","juice",
    "cereal","bread","pasta","rice","snack","chips","frozen",
    "organic","sale","special","promo",
]

def search_keyword(keyword):
    params = {"locale":"en-ca","postal_code":POSTAL_CODE,"q":keyword}
    try:
        r = requests.get(FLIPP_URL, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json().get("items", [])
    except Exception as e:
        print(f"[WARN] {keyword}: {e}", file=sys.stderr)
        return []

def scrape_deals():
    seen_ids = set()
    big_deals = []

    for keyword in SEARCH_KEYWORDS:
        items = search_keyword(keyword)
        for item in items:
            item_id = item.get("id") or item.get("flyer_item_id")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)

            merchant = (item.get("merchant_name") or "").lower()
            if not any(s in merchant for s in TARGET_STORES):
                continue

            price = item.get("current_price")
            orig  = item.get("original_price")

            if price is None or orig is None:
                continue
            if orig <= 0 or price >= orig:
                continue

            discount_pct = round((orig - price) / orig * 100)
            if discount_pct < MIN_DISCOUNT_PCT:
                continue

            big_deals.append({
                "name":         item.get("name",""),
                "merchant":     item.get("merchant_name",""),
                "price":        float(price),
                "orig":         float(orig),
                "discount_pct": discount_pct,
                "valid_to":     item.get("valid_to",""),
            })
        time.sleep(0.2)

    # Sort by discount % descending
    big_deals.sort(key=lambda x: -x["discount_pct"])
    return big_deals

def fmt_date(d):
    try: return datetime.strptime(d[:10],"%Y-%m-%d").strftime("%d %b")
    except: return ""

def build_html(deals):
    today_str = date.today().strftime("%A %d %B %Y")

    if not deals:
        body = '<p style="padding:20px 0;color:#555">Aucune promotion de 50%+ trouvee cette semaine.</p>'
    else:
        rows = ""
        for d in deals:
            vld = f' · valide jusqu\'au {fmt_date(d["valid_to"])}' if d["valid_to"] else ""
            rows += f'''<tr style="border-bottom:1px solid #f0f0f0">
              <td style="padding:10px 8px;font-size:14px;vertical-align:top">
                <span style="font-weight:600">{d["name"][:60]}</span>
                <br><small style="color:#555">{d["merchant"]}{vld}</small>
              </td>
              <td style="padding:10px 8px;text-align:right;vertical-align:top;white-space:nowrap">
                <span style="color:#0b8043;font-weight:700;font-size:16px">${d["price"]:.2f}</span>
                <br><small style="color:#aaa;text-decoration:line-through">${d["orig"]:.2f}</small>
                <br><span style="background:#cc0000;color:#fff;font-size:11px;padding:2px 6px;border-radius:3px;font-weight:700">-{d["discount_pct"]}%</span>
              </td>
            </tr>'''

        body = f'''<p style="color:#555;font-size:13px;margin:0 0 16px">
            {len(deals)} promotions de {MIN_DISCOUNT_PCT}%+ trouvees pres de Montreal Nord · Source: Flipp
          </p>
          <table style="width:100%;border-collapse:collapse">
            <thead><tr style="background:#f8f9fa;border-bottom:2px solid #ddd">
              <th style="padding:10px 8px;text-align:left;font-size:13px;color:#555">Produit</th>
              <th style="padding:10px 8px;text-align:right;font-size:13px;color:#555">Prix</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>'''

    return f'''<!DOCTYPE html><html>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;color:#333">
<div style="background:#cc0000;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">Epicerie - Promotions 50%+ cette semaine</h1>
  <p style="color:#ffcccc;font-size:13px;margin:4px 0 0">{today_str} · Maxi · Super C · IGA · Metro · Walmart · Source: Flipp</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">Genere automatiquement chaque vendredi</p>
</div>
</body></html>'''

def send_gmail(subject, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = YOUR_EMAIL
    msg["To"]   = YOUR_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(YOUR_EMAIL, GMAIL_APP_PASSWORD)
        s.sendmail(YOUR_EMAIL, [YOUR_EMAIL], msg.as_string())
    print(f"[OK] Email sent to {YOUR_EMAIL}")

def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting grocery_weekly.py v4...")
    deals = scrape_deals()
    print(f"  Found {len(deals)} deals with {MIN_DISCOUNT_PCT}%+ discount")
    subject = f"Epicerie - {len(deals)} promos 50%+ semaine du {date.today().strftime('%d %b %Y')}"
    send_gmail(subject, build_html(deals))

if __name__ == "__main__":
    main()
