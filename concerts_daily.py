#!/usr/bin/env python3
"""concerts_daily.py v3 — genre-based Montreal concert alerts"""
import json, os, hashlib, smtplib, sys
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

YOUR_EMAIL         = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
TM_API_KEY         = os.environ.get("TM_API_KEY", "ACz2Vf0WUkn41U2rxrxnabz68d8h6KFM")
SEEN_FILE          = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concerts_seen.json")

GENRES = {
    "R&B / Soul":     "KnvZfZ7vAee",
    "Hip-Hop / Rap":  "KnvZfZ7vAv1",
    "Pop":            "KnvZfZ7vAeA",
    "Electronic":     "KnvZfZ7vAvF",
    "World / Reggae": "KnvZfZ7vAv6",
    "Jazz":           "KnvZfZ7vAvE",
}

TM_URL  = "https://app.ticketmaster.com/discovery/v2/events.json"
HEADERS = {"User-Agent": "Mozilla/5.0"}

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)

def fetch_genre(genre_name, genre_id):
    events = []
    for page in range(3):  # fetch up to 3 pages = 60 events per genre
        params = {
            "apikey":    TM_API_KEY,
            "latlong":   "45.5017,-73.5673",
            "radius":    "50",
            "unit":      "km",
            "genreId":   genre_id,
            "segmentId": "KZFzniwnSyZfZ7v7nJ",
            "size":      20,
            "page":      page,
            "sort":      "date,asc",
        }
        try:
            r = requests.get(TM_URL, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            batch = data.get("_embedded", {}).get("events", [])
            if not batch:
                break
            events.extend(batch)
            total_pages = data.get("page", {}).get("totalPages", 1)
            if page >= total_pages - 1:
                break
        except Exception as e:
            print(f"[WARN] {genre_name} page {page}: {e}", file=sys.stderr)
            break
    return events

def scrape_all():
    seen_ids = set()
    results  = []
    today    = date.today().isoformat()

    for genre_name, genre_id in GENRES.items():
        events = fetch_genre(genre_name, genre_id)
        for e in events:
            eid  = e.get("id","")
            edate = e.get("dates",{}).get("start",{}).get("localDate","")
            if not eid or eid in seen_ids:
                continue
            if edate and edate < today:
                continue
            seen_ids.add(eid)
            prices = e.get("priceRanges",[])
            results.append({
                "id":        eid,
                "genre":     genre_name,
                "name":      e.get("name",""),
                "date":      edate,
                "time":      e.get("dates",{}).get("start",{}).get("localTime",""),
                "venue":     e.get("_embedded",{}).get("venues",[{}])[0].get("name",""),
                "city":      e.get("_embedded",{}).get("venues",[{}])[0].get("city",{}).get("name",""),
                "url":       e.get("url",""),
                "min_price": float(prices[0]["min"]) if prices else None,
                "max_price": float(prices[0]["max"]) if prices else None,
            })

    results.sort(key=lambda x: x["date"])
    return results

def fmt_date(d, t=""):
    try:
        out = datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")
        if t:
            out += f" à {t[:5]}"
        return out
    except:
        return d

def price_str(e):
    if e["min_price"] is None:
        return "Prix à confirmer"
    if e["max_price"] and e["max_price"] != e["min_price"]:
        return f"${e['min_price']:.0f} – ${e['max_price']:.0f}"
    return f"${e['min_price']:.0f}"

def build_html(new_events, seen):
    today_str = date.today().strftime("%A %d %B %Y")

    # Group by genre
    by_genre = {}
    for e in new_events:
        by_genre.setdefault(e["genre"], []).append(e)

    body = ""
    for genre_name, events in by_genre.items():
        rows = ""
        for e in events:
            p = price_str(e)
            price_color = "#0b8043" if e["min_price"] and e["min_price"] < 50 else "#1a73e8" if e["min_price"] and e["min_price"] < 100 else "#555"
            price_tag = f'<span style="background:#e6f4ea;color:#0b8043;font-size:10px;padding:1px 5px;border-radius:3px;font-weight:700">MOINS DE 50$</span> ' if e["min_price"] and e["min_price"] < 50 else ""
            rows += f'''<tr style="border-bottom:1px solid #f0f0f0">
              <td style="padding:10px 8px;vertical-align:top">
                {price_tag}<a href="{e['url']}" style="color:#1a0dab;text-decoration:none;font-weight:600;font-size:14px">{e['name'][:55]}</a>
                <br><small style="color:#555">{fmt_date(e['date'], e['time'])} · {e['venue']} · {e['city']}</small>
              </td>
              <td style="padding:10px 8px;text-align:right;vertical-align:top;white-space:nowrap">
                <span style="color:{price_color};font-weight:700">{p}</span>
              </td>
            </tr>'''

        body += f'''<h2 style="font-size:15px;margin:20px 0 6px;padding:6px 10px;background:#f8f9fa;border-left:4px solid #1a73e8">{genre_name} ({len(events)})</h2>
        <table style="width:100%;border-collapse:collapse">{rows}</table>'''

    if not body:
        body = '<p style="padding:20px 0;color:#555">Aucun nouveau concert cette semaine.</p>'

    return f'''<!DOCTYPE html><html>
<body style="font-family:Arial,sans-serif;max-width:700px;margin:auto;padding:20px;color:#333">
<div style="background:#1a0050;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">🎤 Nouveaux concerts Montreal</h1>
  <p style="color:#c8b8ff;font-size:13px;margin:4px 0 0">{today_str} · R&B · Hip-Hop · Pop · Electronic · World · Jazz · Rayon 50km</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  <p style="color:#555;font-size:13px;margin:0 0 12px">{len(new_events)} nouveaux concerts detectes · Les concerts deja vus ne s'affichent plus · Cliquez pour voir les prix complets</p>
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">Genere automatiquement · Source: Ticketmaster CA</p>
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
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting concerts_daily.py v3...")
    events = scrape_all()
    print(f"  Found {len(events)} upcoming events across {len(GENRES)} genres")

    seen = load_seen()
    new_events = [e for e in events if e["id"] not in seen]
    print(f"  New events not yet seen: {len(new_events)}")

    # Mark all as seen
    today_str = date.today().isoformat()
    for e in events:
        seen[e["id"]] = {"name": e["name"], "seen_date": today_str}
    save_seen(seen)

    if not new_events:
        print("  Nothing new — no email sent.")
        return

    subject = f"🎤 Concerts Montreal — {len(new_events)} nouveaux shows ({date.today().strftime('%d %b')})"
    send_gmail(subject, build_html(new_events, seen))

if __name__ == "__main__":
    main()
