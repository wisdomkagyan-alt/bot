
# ============================================================
# SRL TOSS MONITOR
# SPORTRADAR LIVE WEBSITE -> TELEGRAM
#
# Purpose:
#   Monitor the live Sportradar Simulated Reality League
#   cricket page and immediately send a Telegram alert when
#   a new "won the toss" event appears.
#
# Website:
#   https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket
#
# Detection:
#   X won the toss
#   X won the toss and elected to bat
#   X won the toss and elected to field
#
# Browser:
#   Playwright Chromium
#
# Poll:
#   Every 2 seconds
#
# Recovery:
#   Browser/page reload every 5 minutes
#
# Duplicate protection:
#   seen_tosses.json
#
# IMPORTANT:
#   Do NOT hard-code your Telegram bot token.
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
# CONFIGURATION
# ============================================================

SYSTEM_VERSION = "SRL-TOSS-MONITOR-2026"

WEBSITE_URL = (
    "https://sportcenter.sir.sportradar.com/"
    "pt/simulated-reality/cricket"
)

# How often the rendered page is checked.
# 2 seconds gives near-immediate Telegram alerts.
CHECK_INTERVAL = 2

# Reload page periodically in case the SPA/websocket becomes stale.
PAGE_RELOAD_INTERVAL = 300

# Browser timeout.
PAGE_TIMEOUT = 30000

# Keep browser visible while testing.
# False = headless server mode.
HEADLESS = True

# Existing tosses already visible when the program starts:
#
# False:
#   Ignore old tosses and only alert on NEW tosses.
#
# True:
#   Send alerts for tosses already visible on startup.
#
ALERT_EXISTING_TOSSES_ON_START = False


# ============================================================
# TELEGRAM SECURITY
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

STATE_FILE = Path("seen_tosses.json")
HEARTBEAT_FILE = Path("srl_toss_heartbeat.txt")
ERROR_LOG_FILE = Path("srl_toss_errors.log")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

log = logging.getLogger("SRL-TOSS-MONITOR")


# ============================================================
# HTTP SESSION
# ============================================================

telegram_http = requests.Session()


# ============================================================
# TOSS DETECTION
# ============================================================

# English:
#
#   South Africa SRL won the toss
#   South Africa SRL won the toss and elected to bat
#   South Africa SRL won the toss and elected to field
#
# We intentionally operate line-by-line because the rendered
# page generally places the toss message in its own text line.

ENGLISH_TOSS_PATTERNS = [
    re.compile(
        r"^(?P<team>.+?)\s+won\s+the\s+toss"
        r"(?:\s+and\s+(?P<decision>elected\s+to\s+(?:bat|field)))?"
        r"\s*$",
        re.IGNORECASE,
    ),
]


# Optional Portuguese support.
# The URL contains /pt/, although the supplied screenshot shows
# the rendered interface in English.
PORTUGUESE_TOSS_PATTERNS = [
    re.compile(
        r"^(?P<team>.+?)\s+venceu\s+o\s+sorteio"
        r"(?:\s+e\s+(?P<decision>escolheu\s+(?:rebater|campo)))?"
        r"\s*$",
        re.IGNORECASE,
    ),
]


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
        return

    try:
        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):
            seen_tosses = set(
                str(x)
                for x in data
            )

        else:
            seen_tosses = set()

        log.info(
            "Loaded %s previously seen toss events",
            len(seen_tosses),
        )

    except Exception as exc:
        log.error(
            "State file could not be loaded: %s",
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
            "State save failed: %s",
            exc,
        )


# ============================================================
# EVENT ID
# ============================================================

def make_event_id(
    team,
    decision,
    source_text,
):
    """
    Creates a stable ID for one toss event.

    We include the visible source text so that if the same team
    appears in another match later, it is not automatically
    treated as the same event.
    """

    raw = (
        f"{team.strip().lower()}|"
        f"{decision.strip().lower()}|"
        f"{source_text.strip().lower()}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_line(line):
    if not line:
        return ""

    line = line.replace(
        "\u00a0",
        " ",
    )

    line = re.sub(
        r"\s+",
        " ",
        line,
    )

    return line.strip()


# ============================================================
# PARSE TOSS LINE
# ============================================================

def parse_toss_line(line):
    """
    Returns:

        {
            "team": "...",
            "decision": "...",
            "text": "..."
        }

    or None.
    """

    original = clean_line(line)

    if not original:
        return None

    # --------------------------------------------------------
    # English
    # --------------------------------------------------------

    for pattern in ENGLISH_TOSS_PATTERNS:
        match = pattern.search(original)

        if match:
            team = clean_line(
                match.group("team")
            )

            decision = clean_line(
                match.group("decision")
                or ""
            )

            return {
                "team": team,
                "decision": decision,
                "text": original,
                "language": "EN",
            }

    # --------------------------------------------------------
    # Portuguese
    # --------------------------------------------------------

    for pattern in PORTUGUESE_TOSS_PATTERNS:
        match = pattern.search(original)

        if match:
            team = clean_line(
                match.group("team")
            )

            decision = clean_line(
                match.group("decision")
                or ""
            )

            return {
                "team": team,
                "decision": decision,
                "text": original,
                "language": "PT",
            }

    return None


# ============================================================
# EXTRACT TOSSES FROM PAGE
# ============================================================

def extract_tosses(page_text):
    """
    Scan the complete rendered page.

    Returns unique toss records.
    """

    results = []

    lines = page_text.splitlines()

    for line in lines:
        line = clean_line(line)

        if not line:
            continue

        toss = parse_toss_line(line)

        if toss is None:
            continue

        results.append(toss)

    # Remove duplicates within one page scan.
    unique = {}

    for toss in results:
        key = (
            toss["team"].lower(),
            toss["decision"].lower(),
            toss["text"].lower(),
        )

        unique[key] = toss

    return list(unique.values())


# ============================================================
# TELEGRAM
# ============================================================

def telegram_configured():
    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    )


def send_telegram(message):
    if not telegram_configured():
        log.error(
            "Telegram credentials are missing. "
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
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
# TOSS MESSAGE
# ============================================================

def build_toss_message(toss):
    now = datetime.now().astimezone()

    team = toss["team"]
    decision = toss["decision"]

    if decision:
        decision_text = decision
    else:
        decision_text = "Decision not shown"

    return (
        "🏏 SRL TOSS ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏆 {team} WON THE TOSS\n\n"
        f"📝 {toss['text']}\n\n"
        f"🎯 Decision: {decision_text}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S %Z')}\n\n"
        "🌐 Sportradar Simulated Reality League\n"
        "🔔 LIVE TOSS MONITOR\n\n"
        f"🔗 {WEBSITE_URL}"
    )


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
        "🛡 Duplicate protection: ACTIVE\n\n"
        "Waiting for the next toss..."
    )


# ============================================================
# ERROR MESSAGE
# ============================================================

def error_message(exc):
    return (
        "🔴 SRL TOSS MONITOR ERROR\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{type(exc).__name__}: {exc}\n\n"
        "The monitor will attempt recovery automatically."
    )


# ============================================================
# HEARTBEAT
# ============================================================

def write_heartbeat(status="ACTIVE"):
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
# PAGE HEALTH
# ============================================================

async def page_is_alive(page):
    try:
        await page.locator("body").count()
        return True

    except Exception:
        return False


# ============================================================
# BASELINE
# ============================================================

def baseline_current_tosses(tosses):
    """
    On first startup we normally DO NOT send old tosses.

    We mark everything currently visible as already seen.
    This means:
        06:21 old toss -> ignored
        07:21 new toss -> alert
        08:21 new toss -> alert
    """

    if ALERT_EXISTING_TOSSES_ON_START:
        return

    added = 0

    for toss in tosses:

        event_id = make_event_id(
            toss["team"],
            toss["decision"],
            toss["text"],
        )

        if event_id not in seen_tosses:
            seen_tosses.add(event_id)
            added += 1

    if added:
        save_state()

    log.info(
        "Startup baseline complete | %s existing tosses marked seen",
        added,
    )


# ============================================================
# PROCESS NEW TOSS
# ============================================================

def process_toss(toss):
    event_id = make_event_id(
        toss["team"],
        toss["decision"],
        toss["text"],
    )

    if event_id in seen_tosses:
        return False

    message = build_toss_message(toss)

    log.info(
        "NEW TOSS DETECTED | %s",
        toss["text"],
    )

    success = send_telegram(message)

    if success:
        seen_tosses.add(event_id)
        save_state()

        log.info(
            "Telegram toss alert sent | %s",
            toss["text"],
        )

        return True

    log.error(
        "Telegram failed; event remains unacknowledged."
    )

    return False


# ============================================================
# PAGE MONITOR
# ============================================================

async def monitor_page(page):
    first_scan = True
    last_reload = time.monotonic()

    while True:

        try:

            # ------------------------------------------------
            # Get rendered page text.
            # ------------------------------------------------

            page_text = await page.locator(
                "body"
            ).inner_text(
                timeout=10000
            )

            # ------------------------------------------------
            # Extract current tosses.
            # ------------------------------------------------

            tosses = extract_tosses(
                page_text
            )

            # ------------------------------------------------
            # First scan.
            # ------------------------------------------------

            if first_scan:

                log.info(
                    "Initial page scan found %s toss event(s)",
                    len(tosses),
                )

                baseline_current_tosses(
                    tosses
                )

                # If explicitly configured to alert on
                # currently visible tosses:
                if ALERT_EXISTING_TOSSES_ON_START:

                    for toss in tosses:
                        process_toss(toss)

                first_scan = False

            else:

                # --------------------------------------------
                # Detect new tosses.
                # --------------------------------------------

                for toss in tosses:
                    process_toss(toss)

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

            if elapsed >= PAGE_RELOAD_INTERVAL:

                log.info(
                    "Periodic page reload..."
                )

                await page.reload(
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                await page.wait_for_timeout(
                    3000
                )

                last_reload = (
                    time.monotonic()
                )

                log.info(
                    "Page reload complete"
                )

            # ------------------------------------------------
            # Wait before next scan.
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

            await asyncio.sleep(
                3
            )

            try:
                await page.reload(
                    wait_until="domcontentloaded",
                    timeout=PAGE_TIMEOUT,
                )

                await page.wait_for_timeout(
                    3000
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
                    5
                )

        except Exception as exc:

            log.exception(
                "Monitor loop error"
            )

            write_heartbeat(
                "ERROR"
            )

            # Do not send Telegram for every scan error.
            # Otherwise a temporary website failure could
            # flood the Telegram chat.

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
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
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
                5000
            )

            log.info(
                "Starting live toss monitor."
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
    # Security check.
    # --------------------------------------------------------

    if not telegram_configured():

        log.warning(
            "Telegram credentials are not configured."
        )

        log.warning(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
        )

    else:

        send_telegram(
            startup_message()
        )

    # --------------------------------------------------------
    # Load persistent state.
    # --------------------------------------------------------

    load_state()

    # --------------------------------------------------------
    # Main recovery loop.
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

            # Notify only once per browser crash.
            if telegram_configured():
                send_telegram(
                    error_message(exc)
                )

            log.info(
                "Restarting browser in 10 seconds..."
            )

            await asyncio.sleep(
                10
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
