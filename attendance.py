"""
Teams (Microsoft) -> UniPi CAS SSO -> class meeting link -> Join (mic/cam off).

Setup:
    pip install playwright python-dotenv
    python -m playwright install chromium
    pip install pyautogui        # optional: dismisses the "Open Teams?" popup

.env:
    SSO_EMAIL=youremail@unipi.gr
    SSO_USER=            # CAS username; empty = part of email before @
    SSO_PASS=yourpassword

classes.json: list of your classes (see file next to this script)

Usage:
    python auto_login.py                 # picks today's class (closest to now)
    python auto_login.py "Networks"      # picks class whose name contains this
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

HERE = Path(__file__).parent
load_dotenv(HERE / ".env")

EMAIL = os.getenv("SSO_EMAIL", "")
USERNAME = os.getenv("SSO_USER", "") or EMAIL.split("@")[0]
PASSWORD = os.getenv("SSO_PASS", "")

START_URL = "https://teams.microsoft.com"
PROFILE_DIR = str(HERE / "browser_profile")
HEADLESS = False
STAY_OPEN_SECONDS = 0  
JOIN_TIMEOUT = 120


# ---------- class selection ----------
def pick_class():
    classes = json.loads((HERE / "classes.json").read_text(encoding="utf-8"))
    if len(sys.argv) > 1:
        q = sys.argv[1].lower()
        for c in classes:
            if q in c["name"].lower():
                return c
        sys.exit(f"No class matching '{sys.argv[1]}' in classes.json")

    today = datetime.now().strftime("%a")  # Mon, Tue, ...
    now_min = datetime.now().hour * 60 + datetime.now().minute
    todays = [c for c in classes if c["day"].lower()[:3] == today.lower()]
    if not todays:
        sys.exit(f"No class scheduled for {today} in classes.json")

    def dist(c):
        h, m = map(int, c["start"].split(":"))
        return abs(h * 60 + m - now_min)

    return min(todays, key=dist)


def to_web_url(url):
    """Teams web-client form of a meetup-join link (skips the 'open app?' launcher)."""
    m = re.match(r"https://teams\.microsoft\.com/l/meetup-join/([^?]+)\?(.*)", url)
    if not m:
        return url
    return ("https://teams.microsoft.com/v2/?meetingjoin=true#/meetup-join/"
            f"{unquote(m.group(1))}?{m.group(2)}")


# ---------- helpers ----------
def try_click(locator, label, timeout=8_000):
    try:
        locator.first.click(timeout=timeout)
        print(f"[+] {label}")
        return True
    except PWTimeout:
        print(f"[-] {label}: not shown, skipping")
        return False


def in_call(page):
    sel = ("[data-tid='hangup-button'], #hangup-button, "
           "button[aria-label*='Leave' i], button[aria-label*='Hang up' i]")
    try:
        return page.locator(sel).first.is_visible()
    except Exception:
        return False


def turn_off_prejoin(page, what):
    """Pre-join screen: switch mic/camera OFF if it's on. what = 'mic' or 'camera'."""
    tid = "toggle-mute" if what == "mic" else "toggle-video"
    sel = (f"[data-tid='{tid}'], [role='switch'][aria-label*='{what}' i], "
           f"[role='checkbox'][aria-label*='{what}' i]")
    try:
        el = page.locator(sel).first
        if el.is_visible() and el.get_attribute("aria-checked") == "true":
            el.click(timeout=2_000)
            print(f"[+] {what} turned off (pre-join)")
    except Exception:
        pass


def ensure_muted_in_call(page):
    """In call: if a 'Mute mic' button is showing, the mic is live -> click it."""
    for _ in range(3):
        try:
            btn = page.get_by_role("button", name=re.compile(r"^(Mute mic|Mute)\b", re.I)).first
            if btn.is_visible():
                btn.click(timeout=2_000)
                print("[+] Mic muted (in call)")
        except Exception:
            pass
        page.wait_for_timeout(1_500)


def dismiss_os_popup():
    """Closes the browser's native 'Open Microsoft Teams?' popup (not part of the page)."""
    try:
        import pyautogui
        time.sleep(2)
        pyautogui.press("esc")
    except ImportError:
        pass


def dump_state(page, tag):
    page.screenshot(path=str(HERE / f"debug_{tag}.png"))
    names = []
    for b in page.locator("button, [role='button'], a").all()[:60]:
        try:
            if b.is_visible():
                t = (b.inner_text() or b.get_attribute("aria-label") or "").strip()
                if t:
                    names.append(t.replace("\n", " ")[:50])
        except Exception:
            pass
    print(f"[debug] url: {page.url}")
    print(f"[debug] visible buttons/links: {names}")
    print(f"[debug] screenshot: debug_{tag}.png")


# ---------- main ----------
def main():
    if not (EMAIL and PASSWORD):
        sys.exit("Missing SSO_EMAIL / SSO_PASS in .env")

    cls = pick_class()
    class_url = cls["url"].strip()
    print(f"[+] Class: {cls['name']}")

    with sync_playwright() as p:
        kwargs = dict(
            user_data_dir=PROFILE_DIR,
            headless=HEADLESS,
            args=["--use-fake-ui-for-media-stream"],
            permissions=["microphone", "camera"],
        )
        try:
            ctx = p.chromium.launch_persistent_context(channel="msedge", **kwargs)
            print("[+] Using Microsoft Edge")
        except Exception:
            ctx = p.chromium.launch_persistent_context(**kwargs)
            print("[+] Using bundled Chromium")
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        # 1. Login (skipped automatically if the saved profile is still signed in)
        page.goto(START_URL, wait_until="domcontentloaded")
        try:
            page.wait_for_selector("input[name='loginfmt']", timeout=25_000)
            page.fill("input[name='loginfmt']", EMAIL)
            page.click("#idSIButton9")
            print("[+] Email submitted")

            page.wait_for_selector("#loginButton", timeout=30_000)
            print(f"[+] CAS page: {page.url.split('/')[2]}")
            page.fill("#username", USERNAME)
            page.fill("#password", PASSWORD)
            page.click("#loginButton")
            print("[+] CAS credentials submitted")
            try_click(page.locator("#idSIButton9"), "Stay signed in: Yes", timeout=15_000)
        except PWTimeout:
            print("[+] Already signed in (saved profile)")

        try:
            page.wait_for_url(re.compile(r"https://teams\.(microsoft|cloud\.microsoft)\.com/.*"),
                              timeout=60_000)
        except PWTimeout:
            print("[!] Never reached Teams after login")
            dump_state(page, "login")
            input("Press Enter to close...")
            return
        page.wait_for_load_state("networkidle")
        print("[+] Signed in to Teams")

        # 2. Open the meeting (direct web-client URL first, original link as fallback)
        page.goto(to_web_url(class_url), wait_until="domcontentloaded")
        print("[+] Meeting link opened")
        dismiss_os_popup()

        # 3. Click through whatever is in the way until we're in the call
        steps = [
            ("Launcher: continue in browser", page.get_by_text(re.compile(
                r"(Continue on this browser|Join on the web instead|"
                r"Use the web app instead|Open in browser|Watch on the web instead)", re.I))),
            ("Join now", page.locator("[data-tid='prejoin-join-button']")),
            ("Join now (text)", page.get_by_role("button", name=re.compile(r"^Join now$", re.I))),
            ("Join (text)", page.get_by_role("button", name=re.compile(r"^Join$", re.I))),
        ]
        start = time.time()
        clicked_any = False
        used_fallback = False
        joined = False
        while time.time() - start < JOIN_TIMEOUT:
            if in_call(page):
                joined = True
                break
            for label, loc in steps:
                try:
                    if loc.count() and loc.first.is_visible():
                        if label.startswith("Join"):
                            turn_off_prejoin(page, "mic")
                            turn_off_prejoin(page, "camera")
                        loc.first.click(timeout=3_000)
                        print(f"[+] {label}")
                        clicked_any = True
                        page.wait_for_timeout(2_000)
                        break
                except Exception:
                    pass
            if not clicked_any and not used_fallback and time.time() - start > 40:
                print("[~] Direct URL stalled, trying original link")
                page.goto(class_url, wait_until="domcontentloaded")
                dismiss_os_popup()
                used_fallback = True
            page.wait_for_timeout(1_500)

        if joined:
            print("[+] In the call")
            ensure_muted_in_call(page)
        else:
            print("[!] Could not confirm join")
            dump_state(page, "join")

        if STAY_OPEN_SECONDS > 0:
            page.wait_for_timeout(STAY_OPEN_SECONDS * 1000)
        else:
            input("Press Enter to close...")

        ctx.close()


if __name__ == "__main__":
    main()