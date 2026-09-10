#!/usr/bin/env python3
"""
grocery_weekly.py
-----------------
Every Friday morning, checks Flipp for deals on your grocery list
near Montreal Nord (H1H 4J5). Sends a comparison table showing
the cheapest price per item across your stores.

Requirements: requests, beautifulsoup4
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
    "milk", "pork", "tofu", "orange juice", "feta",
    "peanuts", "raisins", "plantain", "apples", "strawberries",
    "mangoes", "grapes", "apricot", "strawberry jam", "cream cheese",
    "sour cream", "papaya", "watermelon", "raspberries", "bananas",
    "almonds", "eggs", "avocado", "leclerc biscuits", "chips",
    "maple syrup", "honey", "pangasius", "salmon", "shrimp",
    "potatoes", "onions", "macaroni", "rice", "sushi rice",
    "corn flakes cereal", "mozzarella", "edam cheese", "camembert",
]

TARGET_STORES = ["maxi", "super c", "iga", "walmart", "metro", "adonis", "tnt"]
# ============================================================

FLIPP_SEARCH_URL = "https://flipp.com/api/2/items"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://flipp.com/",
}


# ── Flipp fetcher ──────────────────────────────────────────

def search_item(keyword: str) -> list:
    """Search Flipp for a grocery item near the postal code."""
    params = {
        "locale":      "en-ca",
        "postal_code": POSTAL_CODE,
        "q":           keyword,
    }
    try:
        r = requests.get(FLIPP_SEARCH_URL, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    except Exception as e:
        print(f"[WARN] Flipp search '{keyword}': {e}", file=sys.stderr)
        return []


def find_best_deals(keyword: str) -> list:
    """Find best deals for a keyword, filtered to target stores."""
    items = search_item(keyword)
    deals = []
    for item in items:
        merchant = (item.get("merchant", "") or "").lower()
        name     = item.get("name", "")
        price    = item.get("current_price")
        pre_price = item.get("pre_price")
        valid_to = item.get("valid_to", "")

        # Filter to target stores
        if not any(store in merchant for store in TARGET_STORES):
            continue
        if price is None:
            continue

        deals.append({
            "keyword":   keyword,
            "name":      name,
            "merchant":  item.get("merchant", ""),
            "price":     float(price),
            "pre_price": float(pre_price) if pre_price else None,
            "valid_to":  valid_to,
        })

    # Sort by price, return top 3
    deals.sort(key=lambda x: x["price"])
    return deals[:3]


def scrape_grocery() -> dict:
    """Scrape all items — returns dict of keyword -> list of deals."""
    results = {}
    for keyword in GROCERY_LIST:
        deals = find_best_deals(keyword)
        if deals:
            results[keyword] = deals
        time.sleep(0.3)
    return results


# ── Email builder ──────────────────────────────────────────

def savings_html(deal: dict) -> str:
    if deal["pre_price"] and deal["pre_price"] > deal["price"]:
        saved = deal["pre_price"] - deal["price"]
        return f'<span style="color:#cc0000;font-size:11px"> (-${saved:.2f})</span>'
    return ""

def build_html(results: dict) -> str:
    today_str = date.today().strftime("%A %d %B %Y")

    if not results:
        body = '<p style="padding:20px 0;color:#555">Aucune promotion trouvée cette semaine sur ta liste.</p>'
    else:
        rows = ""
        for keyword, deals in sorted(results.items()):
            best = deals[0]
            other_stores = deals[1:]

            # Best deal row
            savings = savings_html(best)
            other_html = ""
            if other_stores:
                other_parts = ", ".join(
                    f'{d["merchant"]}: <b>${d["price"]:.2f}</b>' for d in other_stores
                )
                other_html = f'<br><small style="color:#888">Aussi: {other_parts}</small>'

            rows += f"""
            <tr style="border-bottom:1px solid #f0f0f0">
              <td style="padding:10px 8px;font-weight:600;font-size:14px;width:35%;vertical-align:top">
                {keyword.title()}
              </td>
              <td style="padding:10px 8px;font-size:14px;vertical-align:top">
                <span style="color:#0b8043;font-weight:700">${best['price']:.2f}</span>{savings}
                <span style="color:#555;font-size:13px"> @ {best['merchant']}</span>
                <br><small style="color:#888;font-size:11px">{best['name'][:60]}</small>
                {other_html}
              </td>
            </tr>"""

        body = f"""
        <p style="color:#555;font-size:13px;margin:0 0 16px">
          Meilleur prix trouvé cette semaine pour chaque article de ta liste.
          Prix valides selon les circulaires Flipp · Postal: {POSTAL_CODE}
        </p>
        <table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif">
          <thead>
            <tr style="background:#f8f9fa;border-bottom:2px solid #ddd">
              <th style="padding:10px 8px;text-align:left;font-size:13px;color:#555">Article</th>
              <th style="padding:10px 8px;text-align:left;font-size:13px;color:#555">Meilleur prix</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>"""

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;color:#333">
<div style="background:#0b8043;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">🛒 Épicerie — Meilleurs prix de la semaine</h1>
  <p style="color:#a8f0c6;font-size:13px;margin:4px 0 0">{today_str} · Maxi · Super C · IGA · Metro · Walmart · Source: Flipp</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">Généré automatiquement chaque vendredi · Adonis et Marché Newon non couverts par Flipp</p>
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
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting grocery_weekly.py...")
    results = scrape_grocery()
    print(f"  Found deals for {len(results)}/{len(GROCERY_LIST)} items")

    subject = f"🛒 Épicerie — meilleurs prix semaine du {date.today().strftime('%d %b %Y')}"
    html = build_html(results)
    send_gmail(subject, html)


if __name__ == "__main__":
    main()
