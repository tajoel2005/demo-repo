#!/usr/bin/env python3
"""
concours_daily.py — v3
Fetches contests from concoursdujour.com using WordPress REST API + requests.
No Playwright needed — works on a locked Mac.

Requirements:
    pip install requests beautifulsoup4
"""

import json, os, hashlib, smtplib, sys, time, html as html_module
from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests
from bs4 import BeautifulSoup

# ============================================================
# CONFIG
# ============================================================
YOUR_EMAIL         = "tajoel2005@gmail.com"
GMAIL_APP_PASSWORD = "YOUR_APP_PASSWORD_HERE"
SEEN_FILE          = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concours_seen.json")
URGENT_DAYS        = 5
MAX_POSTS          = 60
# ============================================================

API_URL  = "https://www.concoursdujour.com/wp-json/wp/v2/posts"
HEADERS  = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
MONTHS   = {
    "janvier":"01","février":"02","mars":"03","avril":"04",
    "mai":"05","juin":"06","juillet":"07","août":"08",
    "septembre":"09","octobre":"10","novembre":"11","décembre":"12"
}
DAILY_KEYWORDS    = ["quotidienne"]
ONE_TIME_KEYWORDS = ["une fois", "plusieurs périodes"]


# ── Helpers ────────────────────────────────────────────────

def load_seen() -> dict:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_seen(seen: dict) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=2, ensure_ascii=False)

def cid(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]

def normalise_date(raw: str) -> str:
    raw = raw.strip().lower()
    for fr, num in MONTHS.items():
        if fr in raw:
            raw = raw.replace(fr, num)
            break
    for fmt in ("%d %m %Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return raw

def days_until(date_str: str) -> int:
    try:
        return (date.fromisoformat(date_str) - date.today()).days
    except Exception:
        return 999

def safe(text: str) -> str:
    """Escape HTML special characters so titles render correctly in email."""
    return html_module.escape(str(text))


# ── Scraper ────────────────────────────────────────────────

def get_posts() -> list:
    """Get all posts (id, link, title) from WordPress REST API."""
    posts = []
    page  = 1
    while len(posts) < MAX_POSTS:
        try:
            r = requests.get(
                API_URL,
                headers=HEADERS,
                params={"per_page": 20, "page": page, "_fields": "id,link,title"},
                timeout=15
            )
            if r.status_code in (400, 404):
                break
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            posts.extend(batch)
            page += 1
        except Exception as e:
            print(f"[WARN] API page {page}: {e}", file=sys.stderr)
            break
    return posts


def parse_fields(url: str) -> dict:
    """Fetch an individual contest page and extract Prérequis, Fréquence, Expire."""
    fields = {"prerequis": "", "frequence": "", "expire": ""}
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for block in soup.find_all("div", class_="pt-cv-custom-fields"):
            name_tag  = block.find("span", class_="pt-cv-ctf-name")
            value_tag = block.find("div",  class_="pt-cv-ctf-value")
            if not name_tag or not value_tag:
                continue
            key = name_tag.get_text(strip=True).lower().rstrip(":")
            val = value_tag.get_text(strip=True)
            if "prérequis" in key or "prerequis" in key:
                fields["prerequis"] = val
            elif "fréquence" in key or "frequence" in key:
                fields["frequence"] = val
            elif "expire" in key:
                fields["expire"] = normalise_date(val)
    except Exception as e:
        print(f"[WARN] parse_fields {url}: {e}", file=sys.stderr)
    return fields


def scrape_contests() -> list:
    posts = get_posts()
    print(f"  {len(posts)} posts from API")
    contests = []
    for p in posts:
        url   = p.get("link", "")
        # Title comes from API — decode HTML entities properly
        title = BeautifulSoup(p.get("title", {}).get("rendered", ""), "html.parser").get_text()
        if not url:
            continue
        fields = parse_fields(url)
        contests.append({
            "title":     title,
            "url":       url,
            "prerequis": fields["prerequis"],
            "frequence": fields["frequence"],
            "expire":    fields["expire"],
        })
        time.sleep(0.25)
    return contests


# ── Filtering ──────────────────────────────────────────────

def is_expired(c)  -> bool: return c["expire"] != "" and days_until(c["expire"]) < 0
def is_daily(c)    -> bool: return any(k in c["frequence"].lower() for k in DAILY_KEYWORDS)
def is_one_time(c) -> bool: return any(k in c["frequence"].lower() for k in ONE_TIME_KEYWORDS)

def filter_contests(contests, seen):
    eligible = [c for c in contests if c["prerequis"].lower() == "aucun" and not is_expired(c)]
    daily        = [c for c in eligible if is_daily(c)]
    one_time_new = [c for c in eligible if is_one_time(c) and cid(c["url"]) not in seen]
    unknown_new  = [c for c in eligible if not is_daily(c) and not is_one_time(c) and cid(c["url"]) not in seen]
    return daily, one_time_new, unknown_new


# ── Email ──────────────────────────────────────────────────

def build_html(daily, one_time_new, unknown_new) -> str:
    today_str = date.today().strftime("%A %d %B %Y")

    def row(c):
        days      = days_until(c["expire"])
        urgent    = 0 < days <= URGENT_DAYS
        dot       = "🔴" if urgent else "🟢"
        color     = "#cc0000" if urgent else "#888"
        exp_html  = (f"<br><small style='color:{color}'>Expire dans {days} jour{'s' if days>1 else ''}</small>"
                     if days < 999 else "")
        title_esc = safe(c["title"])
        url_esc   = c["url"]   # URLs don't need html.escape
        return (
            f'<tr style="border-bottom:1px solid #eee">'
            f'<td style="padding:10px 6px 10px 0;font-size:18px;width:28px;vertical-align:top">{dot}</td>'
            f'<td style="padding:10px 0">'
            f'<a href="{url_esc}" style="color:#1a0dab;text-decoration:none;font-weight:500;font-size:15px">'
            f'{title_esc}</a>{exp_html}</td></tr>'
        )

    def section(title_html, subtitle, items):
        if not items:
            return ""
        rows = "".join(row(c) for c in items)
        return (
            f'<h2 style="font-size:16px;margin:24px 0 6px;padding-bottom:6px;border-bottom:1px solid #eee">'
            f'{title_html}</h2>'
            f'<p style="color:#666;font-size:13px;margin:0 0 8px">{subtitle}</p>'
            f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
        )

    urgent_daily = [c for c in daily if 0 < days_until(c["expire"]) <= URGENT_DAYS]
    normal_daily = [c for c in daily if days_until(c["expire"]) > URGENT_DAYS]

    body = ""
    body += section(
        "🔁 À jouer aujourd'hui (" + str(len(daily)) + ")",
        "Ces concours sont quotidiens — joue-les chaque jour.",
        urgent_daily + normal_daily
    )
    body += section(
        "🆕 Nouveaux concours à inscription unique (" + str(len(one_time_new)) + ")",
        "À jouer une seule fois — ne s'afficheront plus après aujourd'hui.",
        one_time_new
    )
    body += section(
        "❓ Fréquence inconnue (" + str(len(unknown_new)) + ")",
        "Vérifie manuellement la fréquence sur la page du concours.",
        unknown_new
    )

    if not body:
        body = '<p style="padding:20px 0;color:#555">✅ Aucun nouveau concours aujourd\'hui. Reviens demain !</p>'

    return f"""<!DOCTYPE html><html><body style="font-family:Arial,sans-serif;max-width:660px;margin:auto;padding:20px;color:#333">
<div style="background:#1a73e8;padding:16px 20px;border-radius:8px 8px 0 0">
  <h1 style="color:#fff;font-size:20px;margin:0">🎯 Concours du jour</h1>
  <p style="color:#c8dcff;font-size:13px;margin:4px 0 0">{today_str} · Prérequis = Aucun · Source: concoursdujour.com</p>
</div>
<div style="border:1px solid #dadce0;border-top:none;padding:16px 20px;border-radius:0 0 8px 8px">
  {body}
  <hr style="margin:24px 0;border:none;border-top:1px solid #eee">
  <p style="color:#aaa;font-size:11px;margin:0">Généré automatiquement · Les concours uniques déjà vus ne s'affichent plus</p>
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
    print(f"[{datetime.now():%Y-%m-%d %H:%M}] Starting concours_daily.py v3...")

    try:
        contests = scrape_contests()
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return

    print(f"  Scraped {len(contests)} contests")
    if not contests:
        return

    seen = load_seen()
    daily, one_time_new, unknown_new = filter_contests(contests, seen)
    print(f"  Daily: {len(daily)} | New one-time: {len(one_time_new)} | Unknown: {len(unknown_new)}")

    today_str = date.today().isoformat()
    for c in one_time_new + unknown_new:
        seen[cid(c["url"])] = {"title": c["title"], "seen_date": today_str}
    save_seen(seen)

    nd, nn = len(daily), len(one_time_new)
    subject = (f"🎯 Concours du jour — {nd} quotidien{'s' if nd!=1 else ''} + "
               f"{nn} nouveau{'x' if nn!=1 else ''} ({date.today().strftime('%d %b')})")
    html = build_html(daily, one_time_new, unknown_new)

    if GMAIL_APP_PASSWORD == "YOUR_APP_PASSWORD_HERE":
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "concours_preview.html")
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  [PREVIEW] Saved to {out}")
    else:
        send_gmail(subject, html)

if __name__ == "__main__":
    main()
