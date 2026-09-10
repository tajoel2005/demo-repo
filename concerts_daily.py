#!/usr/bin/env python3
"""
concerts_daily.py
-----------------
Checks Ticketmaster Discovery API daily for Montreal concerts
by your favourite artists. Alerts when:
  - A new show is announced (any price)
  - Tickets are under $50
  - Tickets are $50-$100 (shared as FYI)

Runs daily via GitHub Actions.
Stores seen events in concerts_seen.json to avoid repeat alerts.

Requirements: requests (already in venv)
"""

import json, os, hashlib, smtplib, sys
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ============================================================
# CONFIG
# ============================================================
YOUR_EMAIL          = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD  = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
TM_API_KEY          = os.environ.get("TM_API_KEY", "ACz2Vf0WUkn41U2rxrxnabz68d8h6KFM")
SEEN_FILE           = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concerts_seen.json")

ARTISTS = [
    "Tracy Chapman", "Sabrina Carpenter", "Gims", "Zaz",
    "Christophe Maé", "Lionel Richie", "JP Cooper", "Kygo",
    "Olivia Rodrigo", "Drake", "The Weeknd", "Doja Cat",
    "Ne-Yo", "50 Cent", "Busta Rhymes", "Burna Boy",
    "Tame Impala", "Jon Batiste", "Celine Dion", "Charlie Puth",
    "Lana Del Rey", "Phil Collins", "Emmanuel Moire", "Stromae",
    "M83", "Justin Bieber", "Nico & Vinz"
]

PRICE_ALERT   = 50.0   # under this → green alert
PRICE_FYI     = 100.0  # under this → yellow FYI
# ============================================================

TM_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}


# ── Seen helpers ───────────────────────────────────────────

def load_seen() -> dict:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_seen(seen: dict) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)

def eid(event: dict) -> str:
    return event.get("id", hashlib.md5(event.get("name","").encode()).hexdigest()[:12])


# ── Ticketmaster fetcher ───────────────────────────────────

def fetch_events(artist: str) -> list:
    params = {
        "apikey":             TM_API_KEY,
        "keyword":            artist,
        "city":               "Montreal",
        "countryCode":        "CA",
        "classificationName": "music",
        "size":               10,
        "sort":               "date,asc",
    }
    try:
        r = requests.get(TM_URL, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("_embedded", {}).get("events", [])
    except Exception as e:
        print(f"[WARN] {artist}: {e}", file=sys.stderr)
        return []


def parse_event(e: dict, artist: str) -> dict:
    name    = e.get("name", "")
    date_str = e.get("dates", {}).get("start", {}).get("localDate", "")
    time_str = e.get("dates", {}).get("start", {}).get("localTime", "")
    venue   = e.get("_embedded", {}).get("venues", [{}])[0].get("name", "")
    url     = e.get("url", "")
    prices  = e.get("priceRanges", [])
    min_price = prices[0].get("min") if prices else None
    max_price = prices[0].get("max") if prices else None
    status  = e.get("dates", {}).get("status", {}).get("code", "")
    return {
        "id":        eid(e),
        "artist":    artist,
        "name":      name,
        "date":      date_str,
        "time":      time_str,
        "venue":     venue,
        "url":       url,
        "min_price": min_price,
        "max_price": max_price,
        "status":    status,
    }


# ── Main scraper ───────────────────────────────────────────

def scrape_all() -> list:
    results = []
    for artist in ARTISTS:
        events = fetch_events(artist)
        for e in events:
            parsed = parse_event(e, artist)
            # Only keep events in or near Montreal and in the future
            if parsed["date"] and parsed["date"] >= date.today().isoformat():
                results.append(parsed)
    return results


def categorise(events: list, seen: dict):
    under_50   = []
    under_100  = []
    new_events = []

    for e in events:
        is_new = e["id"] not in seen
        p = e["min_price"]

        if p is not None and p < PRICE_ALERT:
            under_50.append(e)
        elif p is not None and p < PRICE_FYI:
            under_100.append(e)
        elif is_new:
            new_events.append(e)

    return under_50, under_100, new_events


# ── Email builder ──────────────────────────────────────────

def price_str(e: dict) -> str:
    if e["min_price"] is None:
        return "Prix non affiché"
    if e["max_price"] and e["max_price"] != e["min_price"]:
        return f"${e['min_price']:.0f} – ${e['max_price']:.0f}"
    return f"${e['min_price']:.0f}"

def format_date(d: str) -> str:
    try:
        return datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")
    except:
        return d

def row(e: dict, dot: str) -> str:
    p = price_str(e)
    d = format_date(e["date"])
    t = f" à {e['time'][:5]}" if e["time"] else ""
    return (
        f'<tr style="border-bottom:1px solid #eee">'
        f'<td style="padding:10px 6px 10px 0;font-size:18px;width:28px;vertical-align:top">{dot}</td>'
        f'<td style="padding:10px 0">'
        f'<a href="{e["url"]}" style="color:#1a0dab;text-decoration:none;font-weight:600;font-size:15px">'
        f'{e["artist"]}</a>'
        f'<br><span style="font-size:13px;color:#333">{e["name"]}</span>'
        f'<br><small style="color:#555">{d}{t} · {e["venue"]}</small>'
        f'<br><small style="color:#0b8043;font-weight:600">{p}</small>'
        f'</td></tr>'
    )

def section(title_html, subtitle, items, dot):
    if not items:
        return ""
    rows = "".join(row(e, dot) for e in items)
    return (
        f'<h2 style="font-size:16px;margin:24px 0 6px;padding-bottom:6px;border-bottom:1px solid #eee">'
        f'{title_html}</h2>'
        f'<p style="color:#666;font-size:13px;margin:0 0 8px">{subtitle}</p>'
        f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
    )

def build_html(under_50, under_100, new_events) -> str:
    today_str = date.today().strftime("%A %d %B %Y")
    body = ""
    body += section(
        f"🎵 Billets sous 50$ ({len(under_50)})",
        "Ces concerts sont dans ta liste d'artistes avec des billets abordables — fonce !",
        under_50, "🟢"
    )
    body += section(
        f"🎶 Billets 50$–100$ ({len(under_100)})",
        "Un peu plus cher mais dans la zone raisonnable — à toi de décider.",
        under_100, "🟡"
    )
    body += section(
        f"🆕 Nouveaux concerts annoncés ({len(new_events)})",
        "Nouveaux shows de tes artistes — prix non encore disponibles ou au-dessus de 100$.",
        new_events, "🔵"
    )
    if not body:
        body = '<p style="padding:20px 0;color:#555">✅ Aucun nouveau concert aujourd\'hui. Reviens demain !</p>'

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:660px;margin:auto;padding:20px;color:#333">
<div style="background:#1a0050;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">🎤 Alertes concerts Montréal</h1>
  <p style="color:#c8b8ff;font-size:13px;margin:4px 0 0">{today_str} · Tes artistes · Via Ticketmaster</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">
    Généré automatiquement · Nouveaux concerts vus ne s'affichent plus · Source: Ticketmaster CA
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
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting concerts_daily.py...")

    events = scrape_all()
    print(f"  Found {len(events)} upcoming Montreal events for your artists")

    seen = load_seen()
    under_50, under_100, new_events = categorise(events, seen)
    print(f"  Under $50: {len(under_50)} | $50-$100: {len(under_100)} | New: {len(new_events)}")

    # Mark all current events as seen
    today_str = date.today().isoformat()
    for e in events:
        seen[e["id"]] = {"artist": e["artist"], "name": e["name"], "seen_date": today_str}
    save_seen(seen)

    total = len(under_50) + len(under_100) + len(new_events)
    if total == 0:
        print("  Nothing new to report — no email sent.")
        return

    subject = f"🎤 Concerts Montréal — {len(under_50)} sous 50$ · {len(under_100)} sous 100$ · {len(new_events)} nouveaux ({date.today().strftime('%d %b')})"
    html = build_html(under_50, under_100, new_events)
    send_gmail(subject, html)


if __name__ == "__main__":
    main()
