# check_postcode.py
import os, re, sys, json, urllib.request, smtplib
from email.mime_text import MIMEText
from datetime import datetime
from typing import List, Tuple
from playwright.sync_api import sync_playwright

# === Core config ===
POSTCODE = os.getenv("POSTCODE", "GL51 8LS").strip()
POSTCODE_RE = re.compile(r"\bGL51\s?8LS\b", re.IGNORECASE)

URLS = [
    "https://pickmypostcode.com/",
    "https://pickmypostcode.com/survey-draw/",
    "https://pickmypostcode.com/video/",
    "https://pickmypostcode.com/stackpot/",
]

# === Notifications (Slack optional, Email required for this setup) ===
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()

# Defaults set for Jamie/Hotmail; override via env if needed
DEFAULT_EMAIL = "jamie.lee.23@hotmail.com"
EMAIL_TO = os.getenv("EMAIL_TO", DEFAULT_EMAIL).strip()
EMAIL_FROM = os.getenv("EMAIL_FROM", DEFAULT_EMAIL).strip()
EMAIL_SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[Postcode Monitor]")
EMAIL_ALWAYS = os.getenv("EMAIL_ALWAYS", "0").strip()  # "1" to email even if not found

# Outlook/Hotmail SMTP defaults (override via env if sending from elsewhere)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.office365.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", DEFAULT_EMAIL).strip()
SMTP_PASS = os.getenv("SMTP_PASS", "").strip()

# === Helpers ===
def safe_click_text(page, text, timeout=2000):
    try:
        page.get_by_text(text, exact=True).click(timeout=timeout)
        return True
    except Exception:
        return False

def try_click_selectors(page, selectors: List[str], timeout=2000):
    for sel in selectors:
        try:
            page.locator(sel).first.click(timeout=timeout)
            return True
        except Exception:
            continue
    return False

def dismiss_cookies(page):
    for label in [
        "Accept all", "Accept All", "Accept", "I agree", "Agree",
        "Continue", "Got it", "OK", "Okay", "Allow all", "Allow All"
    ]:
        if safe_click_text(page, label, timeout=1500):
            break

def check_one(page, url) -> Tuple[bool, str, str]:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    dismiss_cookies(page)

    if "/survey-draw" in url:
        safe_click_text(page, "No thanks, not today", timeout=3000)

    if "/video" in url:
        try_click_selectors(page, [
            'button[aria-label*="Play" i]',
            'button:has-text("Play")',
            'text="Play"',
            '.jw-icon-play',
            '.vjs-big-play-button',
            'video',
        ], timeout=2500)

    page.wait_for_timeout(1200)
    text = page.evaluate("document.body ? document.body.innerText : ''") or ""
    found = bool(POSTCODE_RE.search(text))
    return found, url, ("FOUND" if found else "not found")

def notify_slack(found_on: List[str], summary_lines: List[str]):
    if not SLACK_WEBHOOK_URL:
        return
    msg = (
        f":tada: Postcode *{POSTCODE}* was found on:\n" + "\n".join(f"• {u}" for u in found_on)
        if found_on else
        f":mag: No matches for {POSTCODE}."
    )
    if summary_lines:
        msg += "\n\n" + "\n".join(summary_lines[-8:])  # keep it short
    data = json.dumps({"text": msg}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL, data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()

def notify_email(found_on: List[str], summary_lines: List[str]):
    if not EMAIL_TO or not EMAIL_FROM or not SMTP_HOST:
        return
    date_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    subject_status = "FOUND" if found_on else "No match"
    subject = f"{EMAIL_SUBJECT_PREFIX} {subject_status} for {POSTCODE} — {date_str}"

    body_lines = []
    if found_on:
        body_lines.append(f"Postcode {POSTCODE} was found on:")
        body_lines += [f" - {u}" for u in found_on]
    else:
        body_lines.append(f"No matches for {POSTCODE} this run.")
    body_lines.append("")
    body_lines.append("Run summary:")
    body_lines += summary_lines

    msg = MIMEText("\n".join(body_lines), "plain", "utf-8")
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg["Subject"] = subject

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.ehlo()
        try:
            s.starttls()
            s.ehlo()
        except Exception:
            pass
        if SMTP_USER and SMTP_PASS:
            s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(EMAIL_FROM, [e.strip() for e in EMAIL_TO.split(",") if e.strip()], msg.as_string())

def main():
    found_on, summary_lines = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx =
