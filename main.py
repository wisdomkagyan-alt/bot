# ============================================================
# SRL TOSS MONITOR 2026
#
# SPORTRADAR WEBPAGE -> TELEGRAM
#
# IMPORTANT:
# This monitor does NOT bypass or evade website access controls.
# If Sportradar/Akamai returns Access Denied, the monitor waits
# and retries rather than attempting to circumvent the block.
#
# Railway:
#   Chromium + Playwright
#
# Telegram:
#   TELEGRAM_BOT_TOKEN
#   TELEGRAM_CHAT_ID
#
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
# CONFIG
# ============================================================

SYSTEM_VERSION = "SRL-TOSS-MONITOR-2026"

WEBSITE_URL = (
    "https://sportcenter.sir.sportradar.com/"
    "pt/simulated-reality/cricket"
)

CHECK_INTERVAL = 2

PAGE_RELOAD_INTERVAL = 300

PAGE_TIMEOUT = 30000

INITIAL_WAIT = 5000

RELOAD_WAIT = 5000

HEADLESS = True

# Do not send old tosses that were already on the page when
# the monitor started.
ALERT_EXISTING_TOSSES_ON_START = False


# ============================================================
# TELEGRAM
# ============================================================

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
# HTTP
# ============================================================

telegram_http = requests.Session()


# ============================================================
# STATE
# ============================================================

seen_tosses = set()


# ============================================================
# LOAD STATE
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
            "Loaded %s previous toss IDs",
            len(seen_tosses),
        )

    except Exception as exc:

        log.error(
            "State loading failed: %s",
            exc,
        )

        seen_tosses = set()


# ============================================================
# SAVE STATE
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
            "State saving failed: %s",
            exc,
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
# TELEGRAM CONFIGURATION
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
            "Telegram credentials are missing."
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
        "🔄 Check interval: 2s\n"
        "📡 Telegram alerts: ACTIVE\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🌐 Browser: Chromium\n\n"
        "Waiting for the next toss..."
    )


# ============================================================
# ACCESS DENIED DETECTION
# ============================================================

def is_access_denied(
    title,
    text,
):

    combined = (
        f"{title}\n"
        f"{text}"
    ).lower()

    indicators = [
        "access denied",
        "you don't have permission to access",
        "reference #",
        "errors.edgesuite.net",
    ]

    matches = sum(
        1
        for item in indicators
        if item in combined
    )

    return matches >= 2


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace(
        "\u00a0",
        " ",
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
# TOSS PARSER
# ============================================================

def parse_toss_text(text):

    if not text:
        return []

    text = normalize_text(
        text
    )

    results = []

    # --------------------------------------------------------
    # Standard English toss wording.
    # --------------------------------------------------------

    patterns = [

        re.compile(
            r"(?P<team>"
            r"[A-Za-z0-9][A-Za-z0-9 .'\-&/()]{1,100}?"
            r")"
            r"\s+won\s+the\s+toss"
            r"(?:\s+and\s+"
            r"(?P<decision>"
            r"elected\s+to\s+(?:bat|field)"
            r"))?",
            re.IGNORECASE,
        ),

        re.compile(
            r"(?P<team>"
            r"[A-Za-z0-9][A-Za-z0-9 .'\-&/()]{1,100}?"
            r")"
            r"\s+won\s+the\s+toss",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:

        for match in pattern.finditer(
            text
        ):

            team = normalize_text(
                match.group("team")
            )

            decision = normalize_text(
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

            # Avoid false positives.
            if "srl" not in team.lower():
                continue

            results.append(
                {
                    "team": team,
                    "decision": decision,
                    "text": normalize_text(
                        match.group(0)
                    ),
                    "language": "EN",
                }
            )

    # --------------------------------------------------------
    # Portuguese fallback.
    # --------------------------------------------------------

    pt_pattern = re.compile(
        r"(?P<team>"
        r"[A-Za-z0-9][A-Za-z0-9 .'\-&/()]{1,100}?"
        r")"
        r"\s+venceu\s+o\s+sorteio"
        r"(?:\s+e\s+"
        r"(?P<decision>"
        r"escolheu\s+(?:rebater|campo)"
        r"))?",
        re.IGNORECASE,
    )

    for match in pt_pattern.finditer(
        text
    ):

        team = normalize_text(
            match.group("team")
        )

        decision = normalize_text(
            match.groupdict().get(
                "decision"
            )
            or ""
        )

        if "srl" not in team.lower():
            continue

        results.append(
            {
                "team": team,
                "decision": decision,
                "text": normalize_text(
                    match.group(0)
                ),
                "language": "PT",
            }
        )

    # --------------------------------------------------------
    # Deduplicate.
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

def event_id(toss):

    raw = (
        f"{toss['team'].lower()}|"
        f"{toss['decision'].lower()}|"
        f"{toss['text'].lower()}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:32]


# ============================================================
# TOSS MESSAGE
# ============================================================

def toss_message(toss):

    now = datetime.now().astimezone()

    if toss["decision"]:

        decision = toss["decision"]

    else:

        decision = "Decision not shown"

    return (
        "🏏 SRL TOSS ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 {toss['team']} WON THE TOSS\n\n"
        f"📝 {toss['text']}\n\n"
        f"🎯 Decision: {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S %Z')}\n\n"
        "🌐 Sportradar Simulated Reality League\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# ACCESS DENIED TELEGRAM
# ============================================================

def access_denied_message():

    return (
        "⚠️ SRL WEBSITE ACCESS DENIED\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Railway reached the Sportradar URL, "
        "but the website/CDN returned Access Denied.\n\n"
        "The monitor is NOT bypassing the restriction.\n"
        "It will continue retrying automatically.\n\n"
        "🏏 SRL Toss Monitor remains active."
    )


# ============================================================
# PROCESS TOSS
# ============================================================

def process_toss(toss):

    identifier = event_id(
        toss
    )

    if identifier in seen_tosses:

        return False

    log.info(
        "NEW TOSS DETECTED: %s",
        toss["text"],
    )

    message = toss_message(
        toss
    )

    success = send_telegram(
        message
    )

    if success:

        seen_tosses.add(
            identifier
        )

        save_state()

        log.info(
            "Telegram toss alert sent."
        )

        return True

    log.error(
        "Telegram toss alert failed."
    )

    return False


# ============================================================
# BASELINE
# ============================================================

def baseline_tosses(
    tosses
):

    if ALERT_EXISTING_TOSSES_ON_START:

        for toss in tosses:

            process_toss(
                toss
            )

        return

    count = 0

    for toss in tosses:

        identifier = event_id(
            toss
        )

        if identifier not in seen_tosses:

            seen_tosses.add(
                identifier
            )

            count += 1

    if count:

        save_state()

    log.info(
        "Startup baseline complete | "
        "%s existing tosses marked seen",
        count,
    )


# ============================================================
# GET PAGE TEXT
# ============================================================

async def get_page_text(
    page
):

    pieces = []

    # --------------------------------------------------------
    # Main document.
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
            "Main inner_text error: %s",
            exc,
        )

    # --------------------------------------------------------
    # DOM text content.
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
            "Main text_content error: %s",
            exc,
        )

    # --------------------------------------------------------
    # Iframes.
    # --------------------------------------------------------

    for index, frame in enumerate(
        page.frames
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

        except Exception:

            pass

    return normalize_text(
        "\n".join(
            pieces
        )
    )


# ============================================================
# PAGE STATUS
# ============================================================

async def page_status(
    page,
    response=None,
):

    try:

        title = await page.title()

    except Exception:

        title = ""

    try:

        text = await page.locator(
            "body"
        ).inner_text(
            timeout=5000
        )

    except Exception:

        text = ""

    return (
        title,
        normalize_text(text),
    )


# ============================================================
# OPEN WEBSITE
# ============================================================

async def open_website(
    page
):

    log.info(
        "Opening Sportradar SRL page..."
    )

    response = await page.goto(
        WEBSITE_URL,
        wait_until="domcontentloaded",
        timeout=PAGE_TIMEOUT,
    )

    if response:

        log.info(
            "HTTP status: %s",
            response.status,
        )

    await page.wait_for_timeout(
        INITIAL_WAIT
    )

    title, text = await page_status(
        page,
        response,
    )

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

    if is_access_denied(
        title,
        text,
    ):

        log.error(
            "SPORTRADAR ACCESS DENIED"
        )

        log.error(
            "Railway is receiving the CDN "
            "Access Denied page."
        )

        return False

    return True


# ============================================================
# MONITOR PAGE
# ============================================================

async def monitor_page(
    page
):

    first_scan = True

    last_reload = (
        time.monotonic()
    )

    last_access_denied_alert = 0

    diagnostic_counter = 0

    while True:

        try:

            title, raw_text = (
                await page_status(
                    page
                )
            )

            # ------------------------------------------------
            # Access Denied detection.
            # ------------------------------------------------

            if is_access_denied(
                title,
                raw_text,
            ):

                now = time.monotonic()

                log.error(
                    "ACCESS DENIED PAGE DETECTED."
                )

                write_heartbeat(
                    "SPORTRADAR ACCESS DENIED"
                )

                # Do not spam Telegram.
                if (
                    now
                    - last_access_denied_alert
                    > 900
                ):

                    send_telegram(
                        access_denied_message()
                    )

                    last_access_denied_alert = (
                        now
                    )

                await asyncio.sleep(
                    10
                )

                try:

                    await page.reload(
                        wait_until="domcontentloaded",
                        timeout=PAGE_TIMEOUT,
                    )

                    await page.wait_for_timeout(
                        RELOAD_WAIT
                    )

                except Exception as exc:

                    log.error(
                        "Access-denied recovery reload failed: %s",
                        exc,
                    )

                continue

            # ------------------------------------------------
            # Full text extraction.
            # ------------------------------------------------

            page_text = await get_page_text(
                page
            )

            # ------------------------------------------------
            # Diagnostics.
            # ------------------------------------------------

            diagnostic_counter += 1

            if diagnostic_counter % 30 == 0:

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

                    log.info(
                        "PAGE PREVIEW: %s",
                        preview[:1500],
                    )

            # ------------------------------------------------
            # Toss detection.
            # ------------------------------------------------

            tosses = parse_toss_text(
                page_text
            )

            if tosses:

                log.info(
                    "Found %s toss event(s).",
                    len(tosses),
                )

                for toss in tosses:

                    log.info(
                        "TOSS FOUND: %s",
                        toss["text"],
                    )

            # ------------------------------------------------
            # Startup baseline.
            # ------------------------------------------------

            if first_scan:

                log.info(
                    "Initial page scan found "
                    "%s toss event(s)",
                    len(tosses),
                )

                baseline_tosses(
                    tosses
                )

                first_scan = False

            else:

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

                    log.info(
                        "Page reload complete."
                    )

                except Exception as exc:

                    log.error(
                        "Periodic reload failed: %s",
                        exc,
                    )

            await asyncio.sleep(
                CHECK_INTERVAL
            )

        except PlaywrightTimeoutError as exc:

            log.error(
                "Playwright timeout: %s",
                exc,
            )

            write_heartbeat(
                "PLAYWRIGHT TIMEOUT"
            )

            await asyncio.sleep(
                5
            )

        except Exception as exc:

            log.exception(
                "Monitor error: %s",
                exc,
            )

            write_heartbeat(
                "MONITOR ERROR"
            )

            await asyncio.sleep(
                5
            )


# ============================================================
# BROWSER
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

        try:

            accessible = await open_website(
                page
            )

            if not accessible:

                # Stay alive and retry.
                log.warning(
                    "Website unavailable from this "
                    "Railway environment."
                )

                write_heartbeat(
                    "WEBSITE ACCESS DENIED"
                )

                while True:

                    await asyncio.sleep(
                        60
                    )

                    try:

                        log.info(
                            "Retrying Sportradar page..."
                        )

                        accessible = (
                            await open_website(
                                page
                            )
                        )

                        if accessible:

                            log.info(
                                "Sportradar page is accessible again."
                            )

                            break

                    except Exception as exc:

                        log.error(
                            "Retry failed: %s",
                            exc,
                        )

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
    # Telegram.
    # --------------------------------------------------------

    if not telegram_configured():

        log.error(
            "Telegram configuration missing."
        )

        log.error(
            "Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in Railway Variables."
        )

    else:

        log.info(
            "Telegram configuration detected."
        )

        if send_telegram(
            startup_message()
        ):

            log.info(
                "Startup Telegram message sent."
            )

        else:

            log.error(
                "Startup Telegram message failed."
            )

    # --------------------------------------------------------
    # State.
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
                "Browser process crashed: %s",
                exc,
            )

            write_heartbeat(
                "BROWSER CRASH - RECOVERING"
            )

            # Don't flood Telegram.
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
# ERROR MESSAGE
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
# ENTRY
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
