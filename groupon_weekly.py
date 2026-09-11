#!/usr/bin/env python3
"""groupon_weekly.py v3 — local Montreal deals 50%+"""
import os, smtplib, sys, re
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

YOUR_EMAIL         = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
MIN_DISCOUNT       = 50

# Online/national deals to exclude — not local Montreal experiences
EXCLUDE_KEYWORDS = [
    "microsoft", "windows", "office", "adobe", "software", "license",
    "activation", "digital download", "lifetime access", "printerpix",
    "canvasonsale", "canvas on demand", "photoaffections", "printingforless",
    "semaglutide", "tirzepatide", "weight loss", "psychic", "tarot",
    "duct cleaning", "air duct", "chimney", "carpet cleaning",
    "photo book", "photo canvas", "photobook", "owlkids", "magazine",
    "subscription", "vpn", "antivirus", "acrobat",
]

# Only keep deals that mention local Montreal context
LOCAL_KEYWORDS = [
    "montreal", "mtl", "québec", "laval", "longueuil", "brossard",
    "restaurant", "spa", "massage", "golf", "escape", "bowling",
    "laser tag", "paintball", "karting", "arcade", "cinema", "theatre",
    "yoga", "fitness", "gym", "pilates", "dance", "swim", "pool",
    "hotel", "brunch", "dinner", "sushi", "pizza", "burger",
    "haircut", "salon", "facial", "manicure", "pedicure",
    "cruise", "tour", "activity", "experience", "adventure",
    "paint", "pottery", "cooking class", "wine tasting",
]

GROUPON_URLS = [
    "https://www.groupon.com/local/montreal",
    "https://www.groupon.com/local/montreal/activities",
    "https://www.groupon.com/local/montreal/health-beauty",
    "https://www.groupon.com/local/montreal/food-drink",
    "https://www.groupon.com/local/montreal/all-services",
]

def is_local(title):
    t = title.lower()
    if any(ex in t for ex in EXCLUDE_KEYWORDS):
        return False
    return True

def scrape_groupon():
    from playwright.sync_api import sync_playwright
    all_html = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled","--disable-dev-shm-usage"]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            locale="en-CA",
            timezone_id="America/Toronto",
            extra_http_headers={
                "Accept-Language": "en-CA,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        for url in GROUPON_URLS:
            try:
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                for _ in range(6):
                    page.evaluate("window.scrollBy(0, 1200)")
                    page.wait_for_timeout(1000)
                all_html.append(page.content())
                page.close()
            except Exception as e:
                print(f"[WARN] {url}: {e}", file=sys.stderr)

        browser.close()

    # Parse all pages
    seen_titles = set()
    deals = []

    for html in all_html:
        soup = BeautifulSoup(html, "html.parser")
        cards = soup.find_all("div", class_=lambda c: c and "flex-1" in c and "flex-col" in c and "gap-1" in c)

        for card in cards:
            text = card.get_text(" ", strip=True)
            discount_match = re.search(r'-(\d+)%', text)
            if not discount_match:
                continue
            pct = int(discount_match.group(1))
            if pct < MIN_DISCOUNT:
                continue

            title = text[:100].split("  ")[0].strip()
            if title in seen_titles:
                continue

            # Filter out non-local deals
            if not is_local(title):
                continue

            seen_titles.add(title)

            prices = re.findall(r'CA?\$[\d,\.]+', text)
            orig = prices[0] if len(prices) >= 2 else None
            curr = prices[1] if len(prices) >= 2 else (prices[0] if prices else None)

            parent = card.parent
            url = None
            for _ in range(6):
                if parent and parent.name == "a":
                    url = parent.get("href","")
                    if url and not url.startswith("http"):
                        url = "https://www.groupon.com" + url
                    break
                if parent:
                    parent = parent.parent

            deals.append({
                "title": title,
                "pct":   pct,
                "orig":  orig,
                "curr":  curr,
                "url":   url or "https://www.groupon.com/local/montreal",
            })

    deals.sort(key=lambda x: -x["pct"])
    return deals

def build_html(deals):
    today_str = date.today().strftime("%A %d %B %Y")
    if not deals:
        body = f'<p style="padding:20px 0;color:#555">Aucun deal local Groupon de {MIN_DISCOUNT}%+ trouvé cette semaine à Montréal.</p>'
    else:
        rows = ""
        for d in deals:
            if d["orig"] and d["curr"]:
                price_html = f'<span style="color:#0b8043;font-weight:700;font-size:16px">{d["curr"]}</span> <span style="color:#aaa;text-decoration:line-through;font-size:13px">{d["orig"]}</span>'
            elif d["curr"]:
                price_html = f'<span style="color:#0b8043;font-weight:700;font-size:16px">{d["curr"]}</span>'
            else:
                price_html = '<span style="color:#888;font-size:13px">Prix sur Groupon</span>'

            rows += f'''<tr style="border-bottom:1px solid #f0f0f0">
              <td style="padding:10px 8px;vertical-align:top">
                <a href="{d['url']}" style="color:#1a0dab;text-decoration:none;font-weight:600;font-size:14px">{d['title'][:70]}</a>
              </td>
              <td style="padding:10px 8px;text-align:right;vertical-align:top;white-space:nowrap">
                {price_html}<br>
                <span style="background:#cc0000;color:#fff;font-size:11px;padding:2px 6px;border-radius:3px;font-weight:700">-{d['pct']}%</span>
              </td>
            </tr>'''

        body = f'''<p style="color:#555;font-size:13px;margin:0 0 16px">
            {len(deals)} deals locaux Groupon de {MIN_DISCOUNT}%+ à Montréal · Restaurants, spas, activités, expériences
          </p>
          <table style="width:100%;border-collapse:collapse">
            <thead><tr style="background:#f8f9fa;border-bottom:2px solid #ddd">
              <th style="padding:10px 8px;text-align:left;font-size:13px;color:#555">Deal</th>
              <th style="padding:10px 8px;text-align:right;font-size:13px;color:#555">Prix</th>
            </tr></thead>
            <tbody>{rows}</tbody>
          </table>'''

    return f'''<!DOCTYPE html><html>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;color:#333">
<div style="background:#82318E;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">Groupon Montreal — Deals locaux {MIN_DISCOUNT}%+</h1>
  <p style="color:#e8c8ff;font-size:13px;margin:4px 0 0">{today_str} · Restaurants · Spas · Activités · Experiences</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">Genere automatiquement chaque vendredi · Cliquez pour voir les details</p>
</div>
</body></html>'''

def send_gmail(subject, html):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = YOUR_EMAIL
    msg["To"]      = YOUR_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(YOUR_EMAIL, GMAIL_APP_PASSWORD)
        s.sendmail(YOUR_EMAIL, [YOUR_EMAIL], msg.as_string())
    print(f"[OK] Email sent to {YOUR_EMAIL}")

def main():
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting groupon_weekly.py v3...")
    deals = scrape_groupon()
    print(f"  Found {len(deals)} local deals at {MIN_DISCOUNT}%+")
    subject = f"Groupon Montreal — {len(deals)} deals locaux {MIN_DISCOUNT}%+ ({date.today().strftime('%d %b %Y')})"
    send_gmail(subject, build_html(deals))

if __name__ == "__main__":
    main()
