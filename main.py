# ============================================================
# SRL TOSS MONITOR 2026
#
# SPORTRADAR LIVE WEBSITE -> TELEGRAM
#
# Website:
# https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket
#
# PURPOSE
# -------
# Continuously monitor the rendered Sportradar SRL cricket
# website and immediately send a Telegram alert whenever a
# NEW "won the toss" event appears.
#
# MONITORING
# ----------
# - Chromium / Playwright
# - Main page DOM
# - All iframes
# - Rendered text
# - DOM textContent
# - Page HTML fallback
#
# CHECK INTERVAL
# --------------
# 2 seconds
#
# DUPLICATE PROTECTION
# --------------------
# seen_tosses.json
#
# IMPORTANT
# ---------
# Telegram credentials MUST be supplied through Railway
# environment variables:
#
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
#
# DO NOT hard-code your Telegram bot token.
# ============================================================


# ============================================================
# IMPORTS
# ============================================================

import asyncio
import hashlib
import json
import logging
import os
import re
import time

from datetime import datetime
from pathlib import Path

import requests

from playwright.async_api import (
    async_playwright,
    TimeoutError as PlaywrightTimeoutError,
)


# ============================================================
# SYSTEM CONFIGURATION
# ============================================================

SYSTEM_VERSION = "SRL-TOSS-MONITOR-2026"

WEBSITE_URL = (
    "https://sportcenter.sir.sportradar.com/"
    "pt/simulated-reality/cricket"
)


# ============================================================
# MONITOR SETTINGS
# ============================================================

# Check the rendered page every 2 seconds.
CHECK_INTERVAL = 2

# Reload browser page every 5 minutes.
PAGE_RELOAD_INTERVAL = 300

# Browser timeout.
PAGE_TIMEOUT = 30000

# Railway/server mode.
HEADLESS = True

# Wait after opening/reloading website.
INITIAL_WAIT = 5000

# Wait after reload.
RELOAD_WAIT = 5000


# ============================================================
# STARTUP BEHAVIOUR
# ============================================================

# False:
#   Existing tosses already visible when the bot starts are
#   marked as seen and NOT sent.
#
# True:
#   Existing visible tosses are sent immediately.
#
# Recommended:
ALERT_EXISTING_TOSSES_ON_START = False


# ============================================================
# TELEGRAM
# ============================================================

# IMPORTANT:
# These MUST exist before telegram_configured() is called.

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU",
)

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "8783763018",
)


# ============================================================
# FILES
# ============================================================

STATE_FILE = Path(
    "seen_tosses.json"
)

HEARTBEAT_FILE = Path(
    "srl_toss_heartbeat.txt"
)

DEBUG_HTML_FILE = Path(
    "srl_debug.html"
)


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s | "
        "%(levelname)s | "
        "%(message)s"
    ),
)

log = logging.getLogger(
    "SRL-TOSS-MONITOR"
)


# ============================================================
# TELEGRAM HTTP SESSION
# ============================================================

telegram_http = requests.Session()


# ============================================================
# GLOBAL STATE
# ============================================================

seen_tosses = set()


# ============================================================
# LOAD PERSISTENT STATE
# ============================================================

def load_state():

    global seen_tosses

    if not STATE_FILE.exists():

        seen_tosses = set()

        log.info(
            "No previous state file found."
        )

        return

    try:

        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):

            seen_tosses = {
                str(item)
                for item in data
            }

        else:

            seen_tosses = set()

        log.info(
            "Loaded %s previously seen toss events",
            len(seen_tosses),
        )

    except Exception as exc:

        log.error(
            "Could not load state: %s",
            exc,
        )

        seen_tosses = set()


# ============================================================
# SAVE PERSISTENT STATE
# ============================================================

def save_state():

    try:

        STATE_FILE.write_text(
            json.dumps(
                sorted(seen_tosses),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception as exc:

        log.error(
            "Could not save state: %s",
            exc,
        )


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def clean_text(text):

    if text is None:
        return ""

    text = str(text)

    text = text.replace(
        "\u00a0",
        " ",
    )

    text = text.replace(
        "\r",
        "\n",
    )

    text = re.sub(
        r"[ \t]+",
        " ",
        text,
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text,
    )

    return text.strip()


# ============================================================
# TEAM NAME CLEANING
# ============================================================

def clean_team_name(team):

    team = clean_text(team)

    # Remove common accidental punctuation.
    team = team.strip(
        " -–—:|•·"
    )

    return team.strip()


# ============================================================
# TOSS PARSER
# ============================================================

def parse_toss_text(text):

    if not text:
        return []

    text = clean_text(text)

    results = []

    # --------------------------------------------------------
    # English
    # --------------------------------------------------------

    english_patterns = [

        re.compile(
            r"(?P<team>[A-Za-z0-9][A-Za-z0-9 .'\-&/()]{1,100}?)"
            r"\s+won\s+the\s+toss"
            r"(?:\s+and\s+"
            r"(?P<decision>"
            r"elected\s+to\s+(?:bat|field)"
            r"))?",
            re.IGNORECASE,
        ),

        re.compile(
            r"(?P<team>[A-Za-z0-9][A-Za-z0-9 .'\-&/()]{1,100}?)"
            r"\s+won\s+the\s+toss",
            re.IGNORECASE,
        ),
    ]

    for pattern in english_patterns:

        for match in pattern.finditer(text):

            team = clean_team_name(
                match.group("team")
            )

            decision = clean_text(
                match.groupdict().get(
                    "decision"
                )
                or ""
            )

            if not team:
                continue

            if len(team) < 3:
                continue

            if len(team) > 100:
                continue

            # SRL teams generally contain SRL.
            # This prevents accidental matches elsewhere.
            if "srl" not in team.lower():
                continue

            results.append(
                {
                    "team": team,
                    "decision": decision,
                    "text": clean_text(
                        match.group(0)
                    ),
                    "language": "EN",
                }
            )

    # --------------------------------------------------------
    # Portuguese fallback
    # --------------------------------------------------------

    portuguese_patterns = [

        re.compile(
            r"(?P<team>[A-Za-z0-9][A-Za-z0-9 .'\-&/()]{1,100}?)"
            r"\s+venceu\s+o\s+sorteio"
            r"(?:\s+e\s+"
            r"(?P<decision>"
            r"escolheu\s+(?:rebater|campo)"
            r"))?",
            re.IGNORECASE,
        ),
    ]

    for pattern in portuguese_patterns:

        for match in pattern.finditer(text):

            team = clean_team_name(
                match.group("team")
            )

            decision = clean_text(
                match.groupdict().get(
                    "decision"
                )
                or ""
            )

            if not team:
                continue

            if "srl" not in team.lower():
                continue

            results.append(
                {
                    "team": team,
                    "decision": decision,
                    "text": clean_text(
                        match.group(0)
                    ),
                    "language": "PT",
                }
            )

    # --------------------------------------------------------
    # Deduplicate results.
    # --------------------------------------------------------

    unique = {}

    for item in results:

        key = (
            item["team"].lower(),
            item["decision"].lower(),
            item["text"].lower(),
        )

        unique[key] = item

    return list(
        unique.values()
    )


# ============================================================
# EVENT ID
# ============================================================

def make_event_id(toss):

    raw = (
        f"{toss['team'].strip().lower()}|"
        f"{toss['decision'].strip().lower()}|"
        f"{toss['text'].strip().lower()}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:32]


# ============================================================
# TELEGRAM CONFIGURATION CHECK
# ============================================================

def telegram_configured():

    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    )


# ============================================================
# TELEGRAM SEND
# ============================================================

def send_telegram(message):

    if not telegram_configured():

        log.error(
            "Telegram is NOT configured."
        )

        log.error(
            "Required variables:"
        )

        log.error(
            "TELEGRAM_BOT_TOKEN"
        )

        log.error(
            "TELEGRAM_CHAT_ID"
        )

        return False

    url = (
        "https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    for attempt in range(1, 4):

        try:

            response = telegram_http.post(
                url,
                json=payload,
                timeout=15,
            )

            if response.status_code == 200:

                return True

            log.error(
                "Telegram HTTP %s: %s",
                response.status_code,
                response.text[:500],
            )

        except Exception as exc:

            log.error(
                "Telegram attempt %s failed: %s",
                attempt,
                exc,
            )

        time.sleep(2)

    return False


# ============================================================
# STARTUP MESSAGE
# ============================================================

def startup_message():

    return (
        "🟢 SRL TOSS MONITOR ONLINE\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏏 Sportradar SRL Cricket\n"
        "⚡ Live webpage monitoring\n"
        f"🔄 Check interval: {CHECK_INTERVAL}s\n"
        "📡 Telegram alerts: ACTIVE\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🌐 Browser engine: Chromium\n\n"
        "Waiting for the next toss..."
    )


# ============================================================
# TOSS TELEGRAM MESSAGE
# ============================================================

def build_toss_message(toss):

    now = datetime.now().astimezone()

    team = toss["team"]

    decision = toss["decision"]

    if decision:

        decision_text = decision

    else:

        decision_text = (
            "Decision not shown"
        )

    return (
        "🏏 SRL TOSS ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 {team} WON THE TOSS\n\n"
        f"📝 {toss['text']}\n\n"
        f"🎯 Decision: {decision_text}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S %Z')}\n\n"
        "🌐 Sportradar Simulated Reality League\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# ERROR TELEGRAM MESSAGE
# ============================================================

def build_error_message(exc):

    return (
        "🔴 SRL TOSS MONITOR ERROR\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Error: {type(exc).__name__}\n"
        f"Message: {str(exc)[:500]}\n\n"
        "Automatic recovery will be attempted."
    )


# ============================================================
# HEARTBEAT
# ============================================================

def write_heartbeat(status):

    try:

        HEARTBEAT_FILE.write_text(
            (
                f"{datetime.now().astimezone().isoformat()} | "
                f"{SYSTEM_VERSION} | "
                f"{status}\n"
            ),
            encoding="utf-8",
        )

    except Exception:
        pass


# ============================================================
# PROCESS NEW TOSS
# ============================================================

def process_toss(toss):

    event_id = make_event_id(
        toss
    )

    # Already sent.
    if event_id in seen_tosses:

        return False

    log.info(
        "NEW TOSS DETECTED: %s",
        toss["text"],
    )

    message = build_toss_message(
        toss
    )

    success = send_telegram(
        message
    )

    if success:

        seen_tosses.add(
            event_id
        )

        save_state()

        log.info(
            "Telegram alert SENT: %s",
            toss["text"],
        )

        return True

    log.error(
        "Telegram failed. "
        "Event will be retried."
    )

    return False


# ============================================================
# BASELINE
# ============================================================

def baseline_current_tosses(tosses):

    if ALERT_EXISTING_TOSSES_ON_START:

        log.info(
            "Startup alert mode enabled."
        )

        return

    added = 0

    for toss in tosses:

        event_id = make_event_id(
            toss
        )

        if event_id not in seen_tosses:

            seen_tosses.add(
                event_id
            )

            added += 1

    if added:

        save_state()

    log.info(
        "Startup baseline complete | "
        "%s existing tosses marked seen",
        added,
    )


# ============================================================
# PAGE TEXT EXTRACTION
# ============================================================

async def get_main_page_text(page):

    pieces = []

    # --------------------------------------------------------
    # inner_text
    # --------------------------------------------------------

    try:

        text = await page.locator(
            "body"
        ).inner_text(
            timeout=5000
        )

        if text:

            pieces.append(
                text
            )

    except Exception as exc:

        log.debug(
            "body.inner_text failed: %s",
            exc,
        )

    # --------------------------------------------------------
    # text_content
    # --------------------------------------------------------

    try:

        text = await page.locator(
            "body"
        ).text_content(
            timeout=5000
        )

        if text:

            pieces.append(
                text
            )

    except Exception as exc:

        log.debug(
            "body.text_content failed: %s",
            exc,
        )

    return "\n".join(
        pieces
    )


# ============================================================
# IFRAME TEXT EXTRACTION
# ============================================================

async def get_frame_text(page):

    pieces = []

    frames = page.frames

    if len(frames) > 1:

        log.info(
            "Detected %s browser frames",
            len(frames),
        )

    for index, frame in enumerate(
        frames
    ):

        if frame == page.main_frame:

            continue

        try:

            text = await frame.locator(
                "body"
            ).inner_text(
                timeout=3000
            )

            if text:

                log.info(
                    "Iframe %s text length: %s",
                    index,
                    len(text),
                )

                pieces.append(
                    text
                )

        except Exception as exc:

            log.debug(
                "Iframe %s read failed: %s",
                index,
                exc,
            )

    return "\n".join(
        pieces
    )


# ============================================================
# FULL PAGE HTML
# ============================================================

async def get_page_html(page):

    try:

        return await page.content()

    except Exception as exc:

        log.debug(
            "Page HTML extraction failed: %s",
            exc,
        )

        return ""


# ============================================================
# EXTRACT TOSSES FROM PAGE
# ============================================================

async def extract_tosses_from_page(page):

    main_text = await get_main_page_text(
        page
    )

    frame_text = await get_frame_text(
        page
    )

    combined_text = (
        main_text
        + "\n"
        + frame_text
    )

    tosses = parse_toss_text(
        combined_text
    )

    # --------------------------------------------------------
    # HTML fallback
    # --------------------------------------------------------

    if not tosses:

        html = await get_page_html(
            page
        )

        if html:

            html_tosses = parse_toss_text(
                html
            )

            if html_tosses:

                log.info(
                    "Toss detected from HTML fallback."
                )

                tosses.extend(
                    html_tosses
                )

    # --------------------------------------------------------
    # Deduplicate.
    # --------------------------------------------------------

    unique = {}

    for toss in tosses:

        key = make_event_id(
            toss
        )

        unique[key] = toss

    return (
        list(
            unique.values()
        ),
        combined_text,
    )


# ============================================================
# PAGE DIAGNOSTICS
# ============================================================

async def log_page_diagnostics(
    page,
    page_text,
    force=False,
):

    if (
        not force
        and not page_text
    ):

        return

    try:

        title = await page.title()

    except Exception:

        title = "UNKNOWN"

    log.info(
        "Browser URL: %s",
        page.url,
    )

    log.info(
        "Browser title: %s",
        title,
    )

    log.info(
        "Number of frames: %s",
        len(page.frames),
    )

    log.info(
        "Rendered page text length: %s",
        len(page_text),
    )

    if page_text:

        preview = re.sub(
            r"\s+",
            " ",
            page_text,
        )

        preview = preview[:1500]

        log.info(
            "PAGE PREVIEW: %s",
            preview,
        )


# ============================================================
# DEBUG PAGE SAVE
# ============================================================

async def save_debug_page(
    page
):

    try:

        html = await page.content()

        DEBUG_HTML_FILE.write_text(
            html,
            encoding="utf-8",
        )

        log.info(
            "Saved debug HTML: %s",
            DEBUG_HTML_FILE,
        )

    except Exception as exc:

        log.warning(
            "Could not save debug HTML: %s",
            exc,
        )


# ============================================================
# DEBUG SCREENSHOT
# ============================================================

async def save_debug_screenshot(
    page
):

    try:

        await page.screenshot(
            path="srl_debug.png",
            full_page=True,
        )

        log.info(
            "Saved debug screenshot: srl_debug.png"
        )

    except Exception as exc:

        log.warning(
            "Could not save screenshot: %s",
            exc,
        )


# ============================================================
# NETWORK MONITOR
# ============================================================

def setup_network_monitor(
    page
):

    async def handle_response(
        response
    ):

        try:

            url = response.url

            # We are interested primarily in API/data responses.
            interesting = any(
                keyword in url.lower()
                for keyword in [
                    "api",
                    "cricket",
                    "match",
                    "event",
                    "score",
                    "sport",
                    "simulated",
                    "reality",
                    "live",
                    "feed",
                ]
            )

            if not interesting:

                return

            content_type = (
                response.headers.get(
                    "content-type",
                    "",
                )
                .lower()
            )

            # Avoid downloading large images/fonts/etc.
            if not any(
                item in content_type
                for item in [
                    "json",
                    "text",
                    "javascript",
                    "xml",
                ]
            ):

                return

            try:

                body = await response.text()

            except Exception:

                return

            if not body:

                return

            # ------------------------------------------------
            # Look for toss directly inside network payload.
            # ------------------------------------------------

            tosses = parse_toss_text(
                body
            )

            for toss in tosses:

                log.info(
                    "NETWORK TOSS DETECTED: %s",
                    toss["text"],
                )

                process_toss(
                    toss
                )

        except Exception as exc:

            # Network events are supplementary.
            # Never crash the main monitor because of them.
            log.debug(
                "Network response handler error: %s",
                exc,
            )

    page.on(
        "response",
        handle_response,
    )


# ============================================================
# PAGE LOAD
# ============================================================

async def open_page(
    page
):

    log.info(
        "Opening Sportradar SRL page..."
    )

    await page.goto(
        WEBSITE_URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    log.info(
        "Page loaded. Waiting for dynamic content..."
    )

    await page.wait_for_timeout(
        INITIAL_WAIT
    )

    await log_page_diagnostics(
        page,
        "",
        force=True,
    )


# ============================================================
# LIVE MONITOR
# ============================================================

async def monitor_page(
    page
):

    first_scan = True

    last_reload = (
        time.monotonic()
    )

    diagnostic_counter = 0

    last_page_length = None

    while True:

        try:

            # ------------------------------------------------
            # Read website.
            # ------------------------------------------------

            tosses, page_text = (
                await extract_tosses_from_page(
                    page
                )
            )

            # ------------------------------------------------
            # Diagnostics every ~60 seconds.
            # ------------------------------------------------

            diagnostic_counter += 1

            if (
                diagnostic_counter % 30 == 0
                or (
                    last_page_length !=
                    len(page_text)
                )
            ):

                await log_page_diagnostics(
                    page,
                    page_text,
                )

                last_page_length = (
                    len(page_text)
                )

            # ------------------------------------------------
            # Tosses found.
            # ------------------------------------------------

            if tosses:

                log.info(
                    "Current page contains "
                    "%s toss event(s)",
                    len(tosses),
                )

                for toss in tosses:

                    log.info(
                        "FOUND: %s",
                        toss["text"],
                    )

            # ------------------------------------------------
            # First scan.
            # ------------------------------------------------

            if first_scan:

                log.info(
                    "Initial page scan found "
                    "%s toss event(s)",
                    len(tosses),
                )

                baseline_current_tosses(
                    tosses
                )

                if (
                    ALERT_EXISTING_TOSSES_ON_START
                ):

                    for toss in tosses:

                        process_toss(
                            toss
                        )

                first_scan = False

            else:

                # --------------------------------------------
                # Every later scan.
                # --------------------------------------------

                for toss in tosses:

                    process_toss(
                        toss
                    )

            # ------------------------------------------------
            # Heartbeat.
            # ------------------------------------------------

            write_heartbeat(
                "ACTIVE"
            )

            # ------------------------------------------------
            # Periodic reload.
            # ------------------------------------------------

            elapsed = (
                time.monotonic()
                - last_reload
            )

            if (
                elapsed
                >= PAGE_RELOAD_INTERVAL
            ):

                log.info(
                    "Periodic page reload..."
                )

                await page.reload(
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                await page.wait_for_timeout(
                    RELOAD_WAIT
                )

                last_reload = (
                    time.monotonic()
                )

                log.info(
                    "Page reload complete."
                )

            # ------------------------------------------------
            # Next scan.
            # ------------------------------------------------

            await asyncio.sleep(
                CHECK_INTERVAL
            )

        except PlaywrightTimeoutError as exc:

            log.error(
                "Page timeout: %s",
                exc,
            )

            write_heartbeat(
                "PAGE TIMEOUT"
            )

            try:

                await page.reload(
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                await page.wait_for_timeout(
                    RELOAD_WAIT
                )

                last_reload = (
                    time.monotonic()
                )

            except Exception as reload_exc:

                log.error(
                    "Recovery reload failed: %s",
                    reload_exc,
                )

            await asyncio.sleep(
                3
            )

        except Exception as exc:

            log.exception(
                "Monitor loop error: %s",
                exc,
            )

            write_heartbeat(
                "ERROR"
            )

            await asyncio.sleep(
                5
            )


# ============================================================
# BROWSER ENGINE
# ============================================================

async def run_browser():

    async with async_playwright() as p:

        log.info(
            "Launching Chromium..."
        )

        browser = await p.chromium.launch(

            headless=HEADLESS,

            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-gpu",
            ],
        )

        context = await browser.new_context(

            viewport={
                "width": 1440,
                "height": 1000,
            },

            locale="en-US",

            timezone_id="Asia/Kolkata",

            user_agent=(
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/139.0.0.0 "
                "Safari/537.36"
            ),
        )

        page = await context.new_page()

        # ----------------------------------------------------
        # Network monitoring.
        # ----------------------------------------------------

        setup_network_monitor(
            page
        )

        try:

            # ------------------------------------------------
            # Open website.
            # ------------------------------------------------

            await open_page(
                page
            )

            # ------------------------------------------------
            # Monitor continuously.
            # ------------------------------------------------

            await monitor_page(
                page
            )

        finally:

            await context.close()

            await browser.close()


# ============================================================
# MAIN
# ============================================================

async def main():

    log.info(
        "%s STARTING",
        SYSTEM_VERSION,
    )

    # --------------------------------------------------------
    # Telegram check.
    # --------------------------------------------------------

    if not telegram_configured():

        log.warning(
            "Telegram credentials are missing."
        )

        log.warning(
            "Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in Railway Variables."
        )

    else:

        log.info(
            "Telegram configuration detected."
        )

        sent = send_telegram(
            startup_message()
        )

        if sent:

            log.info(
                "Startup Telegram message sent."
            )

        else:

            log.error(
                "Startup Telegram message failed."
            )

    # --------------------------------------------------------
    # Load duplicate state.
    # --------------------------------------------------------

    load_state()

    # --------------------------------------------------------
    # Browser recovery loop.
    # --------------------------------------------------------

    while True:

        try:

            await run_browser()

        except KeyboardInterrupt:

            log.info(
                "Stopped by user."
            )

            write_heartbeat(
                "STOPPED"
            )

            break

        except Exception as exc:

            log.exception(
                "Browser crashed: %s",
                exc,
            )

            write_heartbeat(
                "BROWSER CRASH - RECOVERING"
            )

            # Avoid Telegram flooding.
            if telegram_configured():

                send_telegram(
                    build_error_message(
                        exc
                    )
                )

            log.info(
                "Restarting browser in 10 seconds..."
            )

            await asyncio.sleep(
                10
            )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(
            main()
        )

    except KeyboardInterrupt:

        log.info(
            "SRL Toss Monitor stopped."
        )
