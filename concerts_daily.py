curl -L "https://claude.ai" > /dev/null 2>&1; cat > ~/Documents/scripts/concerts_daily.py << 'ENDOFFILE'
#!/usr/bin/env python3
"""concerts_daily.py v2"""
import json, os, hashlib, smtplib, sys
from datetime import datetime, date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import requests

YOUR_EMAIL         = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "YOUR_APP_PASSWORD_HERE")
TM_API_KEY         = os.environ.get("TM_API_KEY", "ACz2Vf0WUkn41U2rxrxnabz68d8h6KFM")
SEEN_FILE          = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concerts_seen.json")
PRICE_ALERT = 50.0
PRICE_FYI   = 100.0

YOUR_ARTISTS = [
    "Tracy Chapman","Sabrina Carpenter","Gims","Zaz","Christophe Maé",
    "Lionel Richie","JP Cooper","Kygo","Olivia Rodrigo","Drake",
    "The Weeknd","Doja Cat","Ne-Yo","50 Cent","Busta Rhymes","Burna Boy",
    "Tame Impala","Jon Batiste","Celine Dion","Charlie Puth","Lana Del Rey",
    "Phil Collins","Emmanuel Moire","Stromae","M83","Justin Bieber","Nico & Vinz",
]
SIMILAR_ARTISTS = [
    "Wizkid","Davido","Tems","Rema","Asake","Black Sherif","Ayra Starr","Omah Lay","Kizz Daniel",
    "Aya Nakamura","Ninho","Angèle","Tayc","Dadju","Pomme","Vianney","Louane","Yseult","Naps",
    "Jungle","Glass Animals","Parcels","Caribou","Air","Bonobo","Polo & Pan","L'Impératrice",
    "SZA","H.E.R.","Raye","Teddy Swims","Benson Boone","Gracie Abrams","Conan Gray",
    "Jacob Collier","Samara Joy","Lucky Daye","Daniel Caesar","Giveon",
]
ALL_ARTISTS = YOUR_ARTISTS + SIMILAR_ARTISTS

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

def eid(event):
    return event.get("id", hashlib.md5(event.get("name","").encode()).hexdigest()[:12])

def fetch_events(artist):
    params = {
        "apikey": TM_API_KEY, "keyword": artist,
        "city": "Montreal", "countryCode": "CA",
        "classificationName": "music", "size": 5, "sort": "date,asc",
    }
    try:
        r = requests.get(TM_URL, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json().get("_embedded", {}).get("events", [])
    except Exception as e:
        print(f"[WARN] {artist}: {e}", file=sys.stderr)
        return []

def parse_event(e, artist, is_similar):
    prices = e.get("priceRanges", [])
    return {
        "id": eid(e), "artist": artist, "is_similar": is_similar,
        "name": e.get("name",""),
        "date": e.get("dates",{}).get("start",{}).get("localDate",""),
        "time": e.get("dates",{}).get("start",{}).get("localTime",""),
        "venue": e.get("_embedded",{}).get("venues",[{}])[0].get("name",""),
        "url": e.get("url",""),
        "min_price": prices[0].get("min") if prices else None,
        "max_price": prices[0].get("max") if prices else None,
    }

def scrape_all():
    results = []
    today = date.today().isoformat()
    for artist in YOUR_ARTISTS:
        for e in fetch_events(artist):
            p = parse_event(e, artist, False)
            if p["date"] >= today:
                results.append(p)
    for artist in SIMILAR_ARTISTS:
        for e in fetch_events(artist):
            p = parse_event(e, artist, True)
            if p["date"] >= today:
                results.append(p)
    seen_ids = set()
    unique = []
    for e in results:
        if e["id"] not in seen_ids:
            seen_ids.add(e["id"])
            unique.append(e)
    return unique

def categorise(events, seen):
    under_50, under_100, new_ann = [], [], []
    for e in events:
        is_new = e["id"] not in seen
        p = e["min_price"]
        if p is not None and p < PRICE_ALERT:
            under_50.append(e)
        elif p is not None and p < PRICE_FYI:
            under_100.append(e)
        elif is_new:
            new_ann.append(e)
    return under_50, under_100, new_ann

def price_str(e):
    if e["min_price"] is None: return "Prix non affiché"
    if e["max_price"] and e["max_price"] != e["min_price"]:
        return f"${e['min_price']:.0f} – ${e['max_price']:.0f}"
    return f"${e['min_price']:.0f}"

def fmt_date(d):
    try: return datetime.strptime(d, "%Y-%m-%d").strftime("%d %b %Y")
    except: return d

def row(e, dot):
    p   = price_str(e)
    d   = fmt_date(e["date"])
    t   = f" à {e['time'][:5]}" if e["time"] else ""
    tag = ' <span style="background:#e8f0fe;color:#1a73e8;font-size:10px;padding:1px 5px;border-radius:3px">découverte</span>' if e["is_similar"] else ""
    return (
        f'<tr style="border-bottom:1px solid #eee">'
        f'<td style="padding:10px 6px 10px 0;font-size:18px;width:28px;vertical-align:top">{dot}</td>'
        f'<td style="padding:10px 0">'
        f'<a href="{e["url"]}" style="color:#1a0dab;text-decoration:none;font-weight:600;font-size:15px">{e["artist"]}</a>{tag}'
        f'<br><span style="font-size:13px;color:#333">{e["name"]}</span>'
        f'<br><small style="color:#555">{d}{t} · {e["venue"]}</small>'
        f'<br><small style="color:#0b8043;font-weight:600">{p}</small>'
        f'</td></tr>'
    )

def section(title_html, subtitle, items, dot):
    if not items: return ""
    rows = "".join(row(e, dot) for e in items)
    return (
        f'<h2 style="font-size:16px;margin:24px 0 6px;padding-bottom:6px;border-bottom:1px solid #eee">{title_html}</h2>'
        f'<p style="color:#666;font-size:13px;margin:0 0 8px">{subtitle}</p>'
        f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
    )

def build_html(under_50, under_100, new_ann):
    today_str = date.today().strftime("%A %d %B %Y")
    body = ""
    body += section(f"🎵 Billets sous 50$ ({len(under_50)})", "Concerts abordables — fonce !", under_50, "🟢")
    body += section(f"🎶 Billets 50$–100$ ({len(under_100)})", "Un peu plus cher mais raisonnable.", under_100, "🟡")
    body += section(f"🆕 Nouveaux concerts annoncés ({len(new_ann)})", "Nouveaux shows annoncés. Étiquette 'découverte' = artistes similaires suggérés.", new_ann, "🔵")
    if not body:
        body = '<p style="padding:20px 0;color:#555">✅ Aucun nouveau concert aujourd\'hui.</p>'
    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:660px;margin:auto;padding:20px;color:#333">
<div style="background:#1a0050;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">🎤 Alertes concerts Montréal</h1>
  <p style="color:#c8b8ff;font-size:13px;margin:4px 0 0">{today_str} · {len(YOUR_ARTISTS)} favoris + {len(SIMILAR_ARTISTS)} similaires</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">Généré automatiquement · Source: Ticketmaster CA</p>
</div></body></html>"""

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
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting concerts_daily.py v2...")
    print(f"  Checking {len(ALL_ARTISTS)} artists")
    events = scrape_all()
    print(f"  Found {len(events)} upcoming Montreal events")
    seen = load_seen()
    under_50, under_100, new_ann = categorise(events, seen)
    print(f"  Under $50: {len(under_50)} | $50-$100: {len(under_100)} | New: {len(new_ann)}")
    today_str = date.today().isoformat()
    for e in events:
        seen[e["id"]] = {"artist": e["artist"], "seen_date": today_str}
    save_seen(seen)
    total = len(under_50) + len(under_100) + len(new_ann)
    if total == 0:
        print("  Nothing new — no email sent.")
        return
    subject = f"🎤 Concerts Montréal — {len(under_50)} sous 50$ · {len(under_100)} sous 100$ · {len(new_ann)} nouveaux ({date.today().strftime('%d %b')})"
    send_gmail(subject, build_html(under_50, under_100, new_ann))

if __name__ == "__main__":
    main()
ENDOFFILE
echo "Done — checking SIMILAR_ARTISTS:"
grep "SIMILAR_ARTISTS" ~/Documents/scripts/concerts_daily.py | head -2
