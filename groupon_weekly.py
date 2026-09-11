#!/usr/bin/env python3
"""
groupon_weekly.py
-----------------
Scrapes Groupon Montreal for deals with 70%+ discount.
Uses Playwright to load all deals including infinite scroll.
Runs weekly via GitHub Actions.

Requirements: playwright, beautifulsoup4
"""
import os, smtplib, sys, re
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from bs4 import BeautifulSoup

YOUR_EMAIL         = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
MIN_DISCOUNT       = 70

GROUPON_URL = "https://www.groupon.com/local/montreal"

def scrape_groupon():
    from playwright.sync_api import sync_playwright
    deals = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(GROUPON_URL, wait_until="networkidle", timeout=30000)

        # Scroll down multiple times to load more deals
        for _ in range(8):
            page.evaluate("window.scrollBy(0, 1500)")
            page.wait_for_timeout(1500)

        html = page.content()
        browser.close()

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_=lambda c: c and "flex-1" in c and "flex-col" in c and "gap-1" in c)
    print(f"  Total cards found: {len(cards)}")

    seen_titles = set()
    for card in cards:
        text = card.get_text(" ", strip=True)
        discount_match = re.search(r'-(\d+)%', text)
        if not discount_match:
            continue
        pct = int(discount_match.group(1))
        if pct < MIN_DISCOUNT:
            continue

        # Extract prices
        prices = re.findall(r'CA?\$[\d,\.]+', text)
        orig  = prices[0] if len(prices) >= 2 else None
        curr  = prices[1] if len(prices) >= 2 else (prices[0] if prices else None)

        # Extract title — first meaningful text chunk
        title = text[:80].split("  ")[0].strip()
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # Find URL
        parent = card.parent
        url = None
        for _ in range(6):
            if parent and parent.name == "a":
                url = parent.get("href", "")
                if not url.startswith("http"):
                    url = "https://www.groupon.com" + url
                break
            if parent:
                parent = parent.parent

        deals.append({
            "title":    title,
            "pct":      pct,
            "orig":     orig,
            "curr":     curr,
            "url":      url or GROUPON_URL,
        })

    deals.sort(key=lambda x: -x["pct"])
    return deals

def build_html(deals):
    today_str = date.today().strftime("%A %d %B %Y")

    if not deals:
        body = f'<p style="padding:20px 0;color:#555">Aucun deal Groupon de {MIN_DISCOUNT}%+ trouvé cette semaine à Montréal.</p>'
    else:
        rows = ""
        for d in deals:
            price_html = ""
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
                {price_html}
                <br><span style="background:#cc0000;color:#fff;font-size:11px;padding:2px 6px;border-radius:3px;font-weight:700">-{d['pct']}%</span>
              </td>
            </tr>'''

        body = f'''<p style="color:#555;font-size:13px;margin:0 0 16px">
            {len(deals)} deals Groupon de {MIN_DISCOUNT}%+ trouvés à Montréal cette semaine
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
  <h1 style="color:#fff;font-size:20px;margin:0">🏷️ Groupon Montreal — Deals {MIN_DISCOUNT}%+</h1>
  <p style="color:#e8c8ff;font-size:13px;margin:4px 0 0">{today_str} · Source: Groupon.com</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">Généré automatiquement chaque vendredi · Cliquez sur les liens pour voir les détails complets</p>
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
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting groupon_weekly.py...")
    deals = scrape_groupon()
    print(f"  Found {len(deals)} deals at {MIN_DISCOUNT}%+")
    subject = f"🏷️ Groupon Montreal — {len(deals)} deals {MIN_DISCOUNT}%+ ({date.today().strftime('%d %b %Y')})"
    send_gmail(subject, build_html(deals))

if __name__ == "__main__":
    main()
