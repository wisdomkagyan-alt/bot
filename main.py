# ============================================================
# SRL TOSS SELENIUM MONITOR 2026
#
# SRL CRICKET ONLY
#
# Source:
# https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket
#
# Selenium + Chromium
# Rendered DOM detection
# Telegram alerts
#
# ALERT FORMAT:
#
# 🏏 SRL TOSS ALERT
# ━━━━━━━━━━━━━━━━━━━━
#
# 🏆 Chennai Super Kings SRL WON THE TOSS
#
# ⚔️ SRL Match
#
# 🎯 Decision: Elected to bowl
# ⏰ 27 Aug 2026 | 09:20:25 IST
#
# 📡 Sportradar SRL Sportcentre
# 🔔 LIVE TOSS MONITOR
#
# ============================================================

import hashlib
import json
import logging
import os
import re
import time

from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


# ============================================================
# CONFIGURATION
# ============================================================

SYSTEM_VERSION = "SRL-TOSS-SELENIUM-2026"

SRL_URL = (
    "https://sportcenter.sir.sportradar.com/"
    "pt/simulated-reality/cricket"
)

# How often the rendered page is checked.
CHECK_INTERVAL = 2

# Refresh page periodically so newly published tosses appear.
PAGE_REFRESH_INTERVAL = 30

PAGE_LOAD_TIMEOUT = 30

REQUEST_TIMEOUT = 15


# ============================================================
# TELEGRAM
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU",
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "8783763018",
).strip()


# ============================================================
# CHROMIUM
# ============================================================

CHROME_BINARY = os.getenv(
    "CHROME_BINARY",
    "/usr/bin/chromium",
).strip()

CHROMEDRIVER_PATH = os.getenv(
    "CHROMEDRIVER_PATH",
    "",
).strip()


# ============================================================
# STATE
# ============================================================

STATE_FILE = Path(
    "seen_tosses.json"
)

HEARTBEAT_FILE = Path(
    "srl_toss_heartbeat.txt"
)

seen_tosses = set()


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
    "SRL-TOSS-SELENIUM"
)


# ============================================================
# HTTP SESSION
# ============================================================

http = requests.Session()

http.headers.update(
    {
        "accept": "application/json",
        "user-agent": (
            "SRL-Toss-Selenium-Monitor/2026"
        ),
    }
)


# ============================================================
# TEXT CLEANER
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = str(value)

    value = value.replace(
        "\xa0",
        " ",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# JSON LOAD
# ============================================================

def load_json(
    path,
    default,
):

    if not path.exists():
        return default

    try:

        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as exc:

        log.warning(
            "Could not read %s: %s",
            path,
            exc,
        )

        return default


# ============================================================
# JSON SAVE
# ============================================================

def save_json(
    path,
    data,
):

    try:

        path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception as exc:

        log.error(
            "Could not save %s: %s",
            path,
            exc,
        )


# ============================================================
# LOAD STATE
# ============================================================

def load_state():

    global seen_tosses

    data = load_json(
        STATE_FILE,
        [],
    )

    if isinstance(
        data,
        list,
    ):

        seen_tosses = {
            str(x)
            for x in data
        }

        log.info(
            "Loaded %s seen toss IDs.",
            len(seen_tosses),
        )

    else:

        seen_tosses = set()

        log.info(
            "No previous SRL toss state found."
        )


# ============================================================
# SAVE STATE
# ============================================================

def save_state():

    save_json(
        STATE_FILE,
        sorted(
            seen_tosses
        ),
    )


# ============================================================
# HEARTBEAT
# ============================================================

def heartbeat(
    status,
):

    try:

        HEARTBEAT_FILE.write_text(
            (
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"{SYSTEM_VERSION} | "
                f"{status}\n"
            ),
            encoding="utf-8",
        )

    except Exception:

        pass


# ============================================================
# TELEGRAM CONFIG
# ============================================================

def telegram_configured():

    return bool(
        TELEGRAM_BOT_TOKEN
        and TELEGRAM_CHAT_ID
    )


# ============================================================
# SEND TELEGRAM
# ============================================================

def send_telegram(
    message,
):

    if not telegram_configured():

        log.error(
            "Telegram credentials missing."
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

    for attempt in range(
        1,
        4,
    ):

        try:

            response = http.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == 200:

                return True

            log.error(
                "Telegram HTTP %s | %s",
                response.status_code,
                response.text[:500],
            )

        except requests.RequestException as exc:

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

        "🏏 SRL CRICKET ONLY\n"
        "📡 Sportradar SRL Sportcentre\n\n"

        "🌐 Selenium + Chrome WebDriver\n"
        f"🔄 DOM check: {CHECK_INTERVAL}s\n"
        f"🔃 Page refresh: {PAGE_REFRESH_INTERVAL}s\n\n"

        "📡 Telegram: ACTIVE\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🎯 Toss detector: ACTIVE\n"
        "🇮🇳 Time: IST\n\n"

        "Waiting for SRL toss..."
    )


# ============================================================
# CREATE CHROME DRIVER
# ============================================================

def create_driver():

    log.info(
        "Launching Chrome WebDriver..."
    )

    options = Options()

    # --------------------------------------------------------
    # Railway / Linux
    # --------------------------------------------------------

    options.add_argument(
        "--headless=new"
    )

    options.add_argument(
        "--no-sandbox"
    )

    options.add_argument(
        "--disable-dev-shm-usage"
    )

    options.add_argument(
        "--disable-gpu"
    )

    options.add_argument(
        "--window-size=1920,1080"
    )

    options.add_argument(
        "--disable-extensions"
    )

    options.add_argument(
        "--disable-background-networking"
    )

    options.add_argument(
        "--disable-background-timer-throttling"
    )

    options.add_argument(
        "--disable-renderer-backgrounding"
    )

    options.add_argument(
        "--disable-features=Translate"
    )

    options.add_argument(
        "--lang=en-US"
    )

    options.add_argument(
        "--user-agent="
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 "
        "Safari/537.36"
    )

    # --------------------------------------------------------
    # Chromium binary
    # --------------------------------------------------------

    if CHROME_BINARY:

        if Path(
            CHROME_BINARY
        ).exists():

            options.binary_location = (
                CHROME_BINARY
            )

            log.info(
                "Using Chrome binary: %s",
                CHROME_BINARY,
            )

        else:

            log.warning(
                "Chrome binary not found: %s",
                CHROME_BINARY,
            )

    # --------------------------------------------------------
    # Explicit ChromeDriver if supplied.
    # --------------------------------------------------------

    if CHROMEDRIVER_PATH:

        from selenium.webdriver.chrome.service import Service

        log.info(
            "Using ChromeDriver: %s",
            CHROMEDRIVER_PATH,
        )

        service = Service(
            CHROMEDRIVER_PATH
        )

        driver = webdriver.Chrome(
            service=service,
            options=options,
        )

    else:

        driver = webdriver.Chrome(
            options=options
        )

    driver.set_page_load_timeout(
        PAGE_LOAD_TIMEOUT
    )

    return driver


# ============================================================
# OPEN PAGE
# ============================================================

def open_page(
    driver,
):

    log.info(
        "Opening SRL Cricket page..."
    )

    try:

        driver.get(
            SRL_URL
        )

    except Exception as exc:

        log.warning(
            "Page load warning: %s",
            exc,
        )

    time.sleep(5)

    try:

        log.info(
            "Browser URL: %s",
            driver.current_url,
        )

    except Exception:

        pass

    try:

        log.info(
            "Browser title: %s",
            driver.title,
        )

    except Exception:

        pass


# ============================================================
# GET RENDERED BODY TEXT
# ============================================================

def get_page_text(
    driver,
):

    try:

        value = driver.execute_script(
            """
            return document.body
                ? document.body.innerText
                : "";
            """
        )

        return value or ""

    except Exception as exc:

        log.warning(
            "Could not read page DOM: %s",
            exc,
        )

        return ""


# ============================================================
# PAGE PREVIEW
# ============================================================

def log_page_preview(
    page_text,
):

    value = clean_text(
        page_text
    )

    if not value:
        return

    log.info(
        "Rendered page text length: %s",
        len(value),
    )

    log.info(
        "PAGE PREVIEW: %s",
        value[:1500],
    )


# ============================================================
# SRL TEAM VALIDATION
# ============================================================

def is_srl_team(
    name,
):

    value = clean_text(
        name
    ).lower()

    return value.endswith(
        " srl"
    )


# ============================================================
# CLEAN WINNER
# ============================================================

def clean_winner(
    winner,
):

    winner = clean_text(
        winner
    )

    # Remove accidental score/over prefixes.

    winner = re.sub(
        r"^(?:\d+(?:\.\d+)?\s*(?:OV|OVERS?)\s*)+",
        "",
        winner,
        flags=re.IGNORECASE,
    )

    winner = re.sub(
        r"^(?:\d+(?:/\d+)?\s*)+",
        "",
        winner,
    )

    winner = clean_text(
        winner
    )

    return winner


# ============================================================
# PARSE TOSS
#
# Accepts examples:
#
# Chennai Super Kings SRL won the toss
#
# Chennai Super Kings SRL won the toss and elected to bowl
#
# South Africa SRL won the toss and elected to bat
# ============================================================

def parse_toss(
    sentence,
):

    sentence = clean_text(
        sentence
    )

    if not sentence:

        return None

    if "won the toss" not in sentence.lower():

        return None

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Capture only the team directly before
    # "won the toss".
    #
    # Do NOT capture:
    #
    # 0 OV Chennai Super Kings SRL
    #
    # as the winner.
    # --------------------------------------------------------

    pattern = re.compile(
        r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)"
        r"\s+won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        re.IGNORECASE,
    )

    matches = list(
        pattern.finditer(
            sentence
        )
    )

    if not matches:

        return None

    # Use the LAST valid match.
    # This avoids grabbing unrelated preceding text
    # when a DOM element contains multiple lines.

    match = matches[-1]

    winner = clean_winner(
        match.group(1)
    )

    decision = clean_text(
        match.group(2) or ""
    ).lower()

    # --------------------------------------------------------
    # Must be an SRL team.
    # --------------------------------------------------------

    if not is_srl_team(
        winner
    ):

        return None

    return {
        "winner": winner,
        "decision": decision,
    }


# ============================================================
# PRIMARY DOM TOSS DETECTOR
# ============================================================

def find_dom_tosses(
    driver,
):

    results = []

    try:

        elements = driver.find_elements(
            By.XPATH,
            (
                "//*[contains("
                "translate("
                "normalize-space(.),"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                "'abcdefghijklmnopqrstuvwxyz'"
                "),"
                "'won the toss'"
                ")]"
            ),
        )

    except Exception as exc:

        log.warning(
            "DOM toss search failed: %s",
            exc,
        )

        return results

    for element in elements:

        try:

            raw = element.get_attribute(
                "innerText"
            )

        except Exception:

            raw = ""

        raw = clean_text(
            raw
        )

        if not raw:

            continue

        toss = parse_toss(
            raw
        )

        if toss:

            results.append(
                toss
            )

    return deduplicate_tosses(
        results
    )


# ============================================================
# SECONDARY PAGE-TEXT DETECTOR
# ============================================================

def find_text_tosses(
    page_text,
):

    results = []

    normalized = clean_text(
        page_text
    )

    if not normalized:

        return results

    # --------------------------------------------------------
    # Find every occurrence of:
    #
    # TEAM SRL won the toss ...
    # --------------------------------------------------------

    pattern = re.compile(
        r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)"
        r"\s+won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        re.IGNORECASE,
    )

    for match in pattern.finditer(
        normalized
    ):

        winner = clean_winner(
            match.group(1)
        )

        decision = clean_text(
            match.group(2) or ""
        ).lower()

        if not is_srl_team(
            winner
        ):

            continue

        results.append(
            {
                "winner": winner,
                "decision": decision,
            }
        )

    return deduplicate_tosses(
        results
    )


# ============================================================
# DEDUPLICATE TOSSES IN SAME PAGE SCAN
# ============================================================

def deduplicate_tosses(
    tosses,
):

    unique = {}

    for toss in tosses:

        winner = clean_text(
            toss.get(
                "winner",
                ""
            )
        )

        decision = clean_text(
            toss.get(
                "decision",
                ""
            )
        ).lower()

        if not winner:
            continue

        key = (
            winner.lower(),
            decision,
        )

        unique[key] = {
            "winner": winner,
            "decision": decision,
        }

    return list(
        unique.values()
    )


# ============================================================
# IST TIME
# ============================================================

def current_ist():

    ist = timezone(
        timedelta(
            hours=5,
            minutes=30,
        )
    )

    return datetime.now(
        timezone.utc
    ).astimezone(
        ist
    )


# ============================================================
# FORMAT DECISION
# ============================================================

def format_decision(
    decision,
):

    value = clean_text(
        decision
    ).lower()

    if value == "bat":

        return "Elected to bat"

    if value == "bowl":

        return "Elected to bowl"

    if value == "field":

        return "Elected to field"

    return "Not reported"


# ============================================================
# TOSS MESSAGE
# ============================================================

def build_toss_message(
    toss,
):

    now = current_ist()

    decision = format_decision(
        toss["decision"]
    )

    # ========================================================
    # FIXED FORMAT
    #
    # NO FIXTURE
    # NO SCORE
    # NO OVERS
    # NO EXTRA TEXT
    # ========================================================

    return (
    "🏏 SRL TOSS ALERT\n\n"

    f"🏆 {toss['winner']} WON THE TOSS\n\n"

    f"{toss['team1']} vs {toss['team2']}\n\n"

    f"🎯 {decision}\n"
    f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}"
    
    )


# ============================================================
# TOSS ID
#
# Winner + decision only.
# ============================================================

def make_toss_id(
    toss,
):

    raw = (
        f"{toss['winner'].strip().lower()}|"
        f"{toss['decision'].strip().lower()}"
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:32]


# ============================================================
# PROCESS TOSS
# ============================================================

def process_toss(
    toss,
):

    # --------------------------------------------------------
    # Validate winner.
    # --------------------------------------------------------

    winner = clean_winner(
        toss.get(
            "winner",
            ""
        )
    )

    if not winner:

        return False

    if not is_srl_team(
        winner
    ):

        log.warning(
            "Rejected non-SRL winner: %s",
            winner,
        )

        return False

    toss["winner"] = winner

    # --------------------------------------------------------
    # Duplicate ID.
    # --------------------------------------------------------

    identifier = make_toss_id(
        toss
    )

    if identifier in seen_tosses:

        return False

    # --------------------------------------------------------
    # Build EXACTLY ONE message.
    # --------------------------------------------------------

    message = build_toss_message(
        toss
    )

    log.info(
        "🔥 NEW SRL TOSS DETECTED | "
        "winner=%s | decision=%s",
        toss["winner"],
        toss["decision"],
    )

    # --------------------------------------------------------
    # Send exactly one Telegram message.
    # --------------------------------------------------------

    success = send_telegram(
        message
    )

    if not success:

        log.error(
            "Telegram failed. Toss remains unsent."
        )

        return False

    # --------------------------------------------------------
    # Mark sent only AFTER Telegram succeeds.
    # --------------------------------------------------------

    seen_tosses.add(
        identifier
    )

    save_state()

    log.info(
        "✅ SRL TOSS ALERT SENT ONCE | %s",
        toss["winner"],
    )

    return True


# ============================================================
# BASELINE
#
# Existing tosses visible when bot starts are marked as seen.
# They will NOT trigger old alerts.
# ============================================================

def baseline_existing_tosses(
    driver,
):

    log.info(
        "Creating initial SRL toss baseline..."
    )

    page_text = get_page_text(
        driver
    )

    tosses = find_text_tosses(
        page_text
    )

    if not tosses:

        log.info(
            "No existing tosses found during baseline."
        )

        return

    added = 0

    for toss in tosses:

        identifier = make_toss_id(
            toss
        )

        if identifier not in seen_tosses:

            seen_tosses.add(
                identifier
            )

            added += 1

    save_state()

    log.info(
        "Initial baseline complete | "
        "%s existing tosses marked seen.",
        added,
    )


# ============================================================
# MONITOR
# ============================================================

def monitor(
    driver,
):

    last_page_text = ""

    last_refresh = time.monotonic()

    # --------------------------------------------------------
    # Do not alert for old tosses already visible.
    # --------------------------------------------------------

    baseline_existing_tosses(
        driver
    )

    while True:

        try:

            # =================================================
            # READ CURRENT PAGE
            # =================================================

            page_text = get_page_text(
                driver
            )

            normalized = clean_text(
                page_text
            )

            # -------------------------------------------------
            # Log changed page.
            # -------------------------------------------------

            if normalized:

                if normalized != last_page_text:

                    log_page_preview(
                        normalized
                    )

                    last_page_text = normalized

            # =================================================
            # PRIMARY DOM DETECTOR
            # =================================================

            dom_tosses = find_dom_tosses(
                driver
            )

            for toss in dom_tosses:

                process_toss(
                    toss
                )

            # =================================================
            # SECONDARY TEXT DETECTOR
            # =================================================

            text_tosses = find_text_tosses(
                page_text
            )

            for toss in text_tosses:

                process_toss(
                    toss
                )

            # =================================================
            # PERIODIC PAGE REFRESH
            # =================================================

            now = time.monotonic()

            if (
                now - last_refresh
                >= PAGE_REFRESH_INTERVAL
            ):

                log.info(
                    "Refreshing SRL Cricket page..."
                )

                try:

                    driver.refresh()

                except Exception as exc:

                    log.warning(
                        "Refresh warning: %s",
                        exc,
                    )

                time.sleep(5)

                try:

                    log.info(
                        "Browser URL: %s",
                        driver.current_url,
                    )

                    log.info(
                        "Browser title: %s",
                        driver.title,
                    )

                except Exception:

                    pass

                last_page_text = ""

                last_refresh = (
                    time.monotonic()
                )

            # =================================================
            # HEARTBEAT
            # =================================================

            heartbeat(
                "ACTIVE"
            )

            # =================================================
            # WAIT
            # =================================================

            time.sleep(
                CHECK_INTERVAL
            )

        except KeyboardInterrupt:

            log.info(
                "Stopped by user."
            )

            heartbeat(
                "STOPPED"
            )

            break

        except Exception as exc:

            log.exception(
                "Monitor loop error: %s",
                exc,
            )

            heartbeat(
                "ERROR - RECOVERING"
            )

            time.sleep(5)


# ============================================================
# MAIN
# ============================================================

def main():

    log.info(
        "%s STARTING",
        SYSTEM_VERSION,
    )

    # ========================================================
    # TELEGRAM CHECK
    # ========================================================

    if not telegram_configured():

        log.error(
            "Telegram configuration missing."
        )

        log.error(
            "Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in Railway Variables."
        )

        return

    log.info(
        "Telegram configuration detected."
    )

    # ========================================================
    # STATE
    # ========================================================

    load_state()

    # ========================================================
    # DRIVER
    # ========================================================

    driver = None

    try:

        driver = create_driver()

        # ====================================================
        # OPEN SRL PAGE
        # ====================================================

        open_page(
            driver
        )

        # ====================================================
        # INITIAL PAGE
        # ====================================================

        page_text = get_page_text(
            driver
        )

        log_page_preview(
            page_text
        )

        # ====================================================
        # STARTUP MESSAGE
        # ====================================================

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

        # ====================================================
        # MONITOR
        # ====================================================

        monitor(
            driver
        )

    except KeyboardInterrupt:

        log.info(
            "Stopped by user."
        )

    except Exception as exc:

        log.exception(
            "Fatal Selenium error: %s",
            exc,
        )

        heartbeat(
            "FATAL ERROR"
        )

    finally:

        if driver:

            try:

                driver.quit()

                log.info(
                    "Chrome WebDriver closed."
                )

            except Exception:

                pass


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
