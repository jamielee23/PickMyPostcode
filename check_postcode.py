# check_postcode.py
import os, re, time, sys
from typing import List, Tuple
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

POSTCODE = os.getenv("POSTCODE", "GL51 8LS").strip()
POSTCODE_RE = re.compile(r"\bGL51\s?8LS\b", re.IGNORECASE)

URLS = [
    "https://pickmypostcode.com/",
    "https://pickmypostcode.com/survey-draw/",
    "https://pickmypostcode.com/video/",
    "https://pickmypostcode.com/stackpot/",
]

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "").strip()

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
    # Best-effort: try common accept/continue labels
    labels = [
        "Accept all", "Accept All", "Accept", "I agree", "Agree",
        "Continue", "Got it", "OK", "Okay"
    ]
    for label in labels:
        if safe_click_text(page, label, timeout=1500):
            break

def check_one(page, url) -> Tuple[bool, str]:
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    dismiss_cookies(page)

    # Page-specific interactions
    if "/survey-draw" in url:
        # “No thanks, not today”
        safe_click_text(page, "No thanks, not today", timeout=3000)
    if "/video" in url:
        # Try common "Play" affordances
        # (overlay buttons, aria labels, player icons)
        try_click_selectors(page, [
            'button[aria-label*="Play" i]',
            'button:has-text("Play")',
            'text="Play"',
            '.jw-icon-play',
            '.vjs-big-play-button',
            'video',
        ], timeout=2500)

    # Give dynamic parts a moment
    page.wait_for_timeout(1200)

    # Read the page text
    try:
        text = page.evaluate("document.body ? document.body.innerText : ''")
    except PWTimeout:
        text = page.inner_text("body", timeout=2000)

    found = bool(POSTCODE_RE.search(text or ""))
    return found, url

def notify_slack(found_on: List[str]):
    import json, urllib.request
    msg = (
        f":tada: Postcode *{POSTCODE}* was found on:\n"
        + "\n".join(f"• {u}" for u in found_on)
    )
    data = json.dumps({"text": msg}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()

def main():
    found_on = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        for u in URLS:
            try:
                hit, url = check_one(page, u)
                print(f"[check] {url} -> {'FOUND' if hit else 'not found'}")
                if hit:
                    found_on.append(url)
            except Exception as e:
                print(f"[error] {u}: {e}", file=sys.stderr)
        browser.close()

    if found_on:
        if SLACK_WEBHOOK_URL:
            try:
                notify_slack(found_on)
                print("[notify] Slack message sent.")
            except Exception as e:
                print(f"[notify] Slack failed: {e}", file=sys.stderr)
        else:
            print("[notify] Matches found (no SLACK_WEBHOOK_URL set):")
            for u in found_on:
                print(f" - {u}")

if __name__ == "__main__":
    main()
