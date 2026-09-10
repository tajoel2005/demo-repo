#!/usr/bin/env python3
"""
grocery_weekly.py v3
--------------------
Every Friday morning, checks Flipp (backflipp.wishabi.com) for deals
on your grocery list near Montreal Nord (H1H 4J5).
Sends a comparison table showing cheapest flyer price per item.

Requirements: requests (already in venv)
"""

import json, os, smtplib, sys, time
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ============================================================
# CONFIG
# ============================================================
YOUR_EMAIL         = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
POSTAL_CODE        = "H1H4J5"

GROCERY_LIST = [
    ("lait",             "milk"),
    ("porc",             "pork"),
    ("tofu",             "tofu"),
    ("jus d'orange",     "orange juice"),
    ("feta",             "feta"),
    ("arachides",        "peanuts"),
    ("raisins secs",     "raisins"),
    ("plantain",         "plantain"),
    ("pommes",           "apples"),
    ("fraises",          "strawberries"),
    ("mangues",          "mangoes"),
    ("raisin",           "grapes"),
    ("confiture fraise", "strawberry jam"),
    ("fromage frais",    "cream cheese"),
    ("crème sure",       "sour cream"),
    ("melon d'eau",      "watermelon"),
    ("framboises",       "raspberries"),
    ("bananes",          "bananas"),
    ("amandes",          "almonds"),
    ("oeufs",            "eggs"),
    ("avocats",          "avocado"),
    ("chips",            "chips"),
    ("sirop d'érable",   "maple syrup"),
    ("miel",             "honey"),
    ("saumon",           "salmon"),
    ("crevettes",        "shrimp"),
    ("patates",          "potatoes"),
    ("oignons",          "onions"),
    ("macaroni",         "macaroni"),
    ("riz",              "rice"),
    ("céréales",         "corn flakes cereal"),
    ("mozzarella",       "mozzarella"),
    ("fromage edam",     "edam cheese"),
    ("camembert",        "camembert"),
    ("pangasius",        "pangasius"),
]

TARGET_STORES = [
    "maxi", "super c", "iga", "walmart", "metro",
    "adonis", "kim phat", "euro marche", "marché richelieu",
    "marché bonichoix", "marché tradition", "rachelle"
]
# ============================================================

FLIPP_URL = "https://backflipp.wishabi.com/flipp/items/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept":     "application/json",
    "Referer":    "https://flipp.com/",
}


# ── Flipp fetcher ──────────────────────────────────────────

def search_item(keyword_en: str) -> list:
    params = {
        "locale":      "en-ca",
        "postal_code": POSTAL_CODE,
        "q":           keyword_en,
    }
    try:
        r = requests.get(FLIPP_URL, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("items", [])
    except Exception as e:
        print(f"[WARN] Flipp '{keyword_en}': {e}", file=sys.stderr)
        return []


def find_best_deals(label_fr: str, keyword_en: str) -> list:
    items = search_item(keyword_en)
    deals = []
    for item in items:
        merchant = (item.get("merchant_name") or "").lower()
        name     = item.get("name", "")
        price    = item.get("current_price")
        orig     = item.get("original_price")
        valid_to = item.get("valid_to", "")

        if price is None:
            continue

        # Case-insensitive partial match against target stores
        if not any(s.lower() in merchant for s in TARGET_STORES):
            continue

        deals.append({
            "label_fr": label_fr,
            "name":     name,
            "merchant": item.get("merchant_name", ""),
            "price":    float(price),
            "orig":     float(orig) if orig else None,
            "valid_to": valid_to,
        })

    deals.sort(key=lambda x: x["price"])
    return deals[:3]


def scrape_grocery() -> list:
    results = []
    for label_fr, keyword_en in GROCERY_LIST:
        deals = find_best_deals(label_fr, keyword_en)
        if deals:
            results.append((label_fr, deals))
        time.sleep(0.4)
    return results


# ── Email builder ──────────────────────────────────────────

def fmt_date(d: str) -> str:
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").strftime("%d %b")
    except:
        return ""


def build_html(results: list) -> str:
    today_str = date.today().strftime("%A %d %B %Y")

    if not results:
        body = '<p style="padding:20px 0;color:#555">Aucune promotion trouvée cette semaine.</p>'
    else:
        rows = ""
        for label_fr, deals in results:
            best = deals[0]

            savings_html = ""
            if best["orig"] and best["orig"] > best["price"]:
                saved = best["orig"] - best["price"]
                savings_html = f' <span style="color:#cc0000;font-size:11px">(-${saved:.2f})</span>'

            valid_html = ""
            if best["valid_to"]:
                valid_html = f'<small style="color:#aaa"> · valide jusqu\'au {fmt_date(best["valid_to"])}</small>'

            other_html = ""
            if len(deals) > 1:
                others = ", ".join(
                    f'{d["merchant"]}: <b>${d["price"]:.2f}</b>'
                    for d in deals[1:]
                )
                other_html = f'<br><small style="color:#888">Aussi: {others}</small>'

            rows += f"""
            <tr style="border-bottom:1px solid #f0f0f0">
              <td style="padding:10px 8px;font-weight:600;font-size:14px;width:30%;vertical-align:top">
                {label_fr.title()}
              </td>
              <td style="padding:10px 8px;font-size:14px;vertical-align:top">
                <span style="color:#0b8043;font-weight:700">${best['price']:.2f}</span>{savings_html}
                <span style="color:#555;font-size:13px"> @ {best['merchant']}</span>
                {valid_html}
                <br><small style="color:#999;font-size:11px">{best['name'][:70]}</small>
                {other_html}
              </td>
            </tr>"""

        body = f"""
        <p style="color:#555;font-size:13px;margin:0 0 16px">
          Meilleur prix circulaire cette semaine · Code postal: {POSTAL_CODE} · Source: Flipp
        </p>
        <table style="width:100%;border-collapse:collapse">
          <thead>
            <tr style="background:#f8f9fa;border-bottom:2px solid #ddd">
              <th style="padding:10px 8px;text-align:left;font-size:13px;color:#555">Article</th>
              <th style="padding:10px 8px;text-align:left;font-size:13px;color:#555">Meilleur prix</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    return f"""<!DOCTYPE html><html>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;color:#333">
<div style="background:#0b8043;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">🛒 Épicerie — Meilleurs prix de la semaine</h1>
  <p style="color:#a8f0c6;font-size:13px;margin:4px 0 0">
    {today_str} · Maxi · Super C · IGA · Metro · Walmart · Adonis · Source: Flipp
  </p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">
    Généré automatiquement chaque vendredi · Marché Newon non couvert par Flipp
  </p>
</div>
</body></html>"""


# ── Gmail ──────────────────────────────────────────────────

def send_gmail(subject: str, html: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = YOUR_EMAIL
    msg["To"]      = YOUR_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(YOUR_EMAIL, GMAIL_APP_PASSWORD)
        s.sendmail(YOUR_EMAIL, [YOUR_EMAIL], msg.as_string())
    print(f"[OK] Email sent to {YOUR_EMAIL}")


# ── Main ───────────────────────────────────────────────────

def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting grocery_weekly.py v3...")
    results = scrape_grocery()
    print(f"  Found deals for {len(results)}/{len(GROCERY_LIST)} items")

    subject = f"🛒 Épicerie — meilleurs prix semaine du {date.today().strftime('%d %b %Y')}"
    html    = build_html(results)
    send_gmail(subject, html)


if __name__ == "__main__":
    main()
