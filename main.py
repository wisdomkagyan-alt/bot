# ============================================================
# SRL TOSS SELENIUM MONITOR 2026
#
# SRL CRICKET ONLY
#
# Source:
#   Sportradar Simulated Reality Sportcentre
#
# Browser:
#   Selenium
#   Chrome / Chromium
#
# Detection:
#   Rendered DOM
#   "won the toss"
#
# Telegram:
#   Instant SRL toss alert
#
# Time:
#   Telegram timestamp = IST
#
# NO Sportradar API
# NO API polling
# NO API 429
# NO Playwright
# ============================================================


# ============================================================
# IMPORTS
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


# ============================================================
# SRL SPORTCENTRE
# ============================================================

SRL_URL = (
    "https://sportcenter.sir.sportradar.com/"
    "pt/simulated-reality/cricket"
)


# ============================================================
# MONITOR SETTINGS
# ============================================================

# How often Selenium checks the already-rendered page.
CHECK_INTERVAL = 2


# Periodically refresh the page so that stale browser
# state cannot persist indefinitely.
PAGE_REFRESH_INTERVAL = 30


# Chrome page-load timeout.
PAGE_LOAD_TIMEOUT = 30


# Telegram timeout.
REQUEST_TIMEOUT = 15


# ============================================================
# STATE FILES
# ============================================================

STATE_FILE = Path(
    "seen_tosses.json"
)


HEARTBEAT_FILE = Path(
    "srl_toss_heartbeat.txt"
)


# ============================================================
# TELEGRAM ENVIRONMENT VARIABLES
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
# BROWSER ENVIRONMENT VARIABLES
# ============================================================

# Railway normally has Chromium installed by the Dockerfile.

CHROME_BINARY = os.getenv(
    "CHROME_BINARY",
    "/usr/bin/chromium",
).strip()


CHROMEDRIVER_PATH = os.getenv(
    "CHROMEDRIVER_PATH",
    "",
).strip()


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
# STATE
# ============================================================

seen_tosses = set()


# ============================================================
# TEXT HELPER
# ============================================================

def text(value):

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(value):

    value = text(value)

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# LOAD JSON
# ============================================================

def load_json_file(
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
# SAVE JSON
# ============================================================

def save_json_file(
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

    data = load_json_file(
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
            "Loaded %s previous toss IDs.",
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

    save_json_file(
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
# TELEGRAM CONFIGURATION
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
        "🇮🇳 Telegram time: IST\n\n"

        "Waiting for SRL toss..."
    )


# ============================================================
# CHROME DRIVER
# ============================================================

def create_driver():

    log.info(
        "Launching Chrome WebDriver..."
    )


    options = Options()


    # --------------------------------------------------------
    # Railway / Linux settings
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
        "--lang=pt"
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
                "Configured Chrome binary does "
                "not exist: %s",
                CHROME_BINARY,
            )


    # --------------------------------------------------------
    # Driver
    # --------------------------------------------------------

    if CHROMEDRIVER_PATH:

        log.info(
            "Using ChromeDriver: %s",
            CHROMEDRIVER_PATH,
        )

        driver = webdriver.Chrome(
            executable_path=CHROMEDRIVER_PATH,
            options=options,
        )

    else:

        # Selenium Manager automatically finds
        # a compatible driver when available.

        driver = webdriver.Chrome(
            options=options
        )


    driver.set_page_load_timeout(
        PAGE_LOAD_TIMEOUT
    )


    return driver


# ============================================================
# OPEN SRL PAGE
# ============================================================

def open_srl_page(
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
            "Initial page load warning: %s",
            exc,
        )


    time.sleep(5)


    log.info(
        "Browser URL: %s",
        driver.current_url,
    )


    try:

        log.info(
            "Browser title: %s",
            driver.title,
        )

    except Exception:

        pass


# ============================================================
# GET RENDERED DOM TEXT
# ============================================================

def get_rendered_text(
    driver,
):

    try:

        result = driver.execute_script(
            """
            return document.body
                ? document.body.innerText
                : "";
            """
        )

        return result or ""


    except Exception as exc:

        log.warning(
            "Could not read rendered DOM: %s",
            exc,
        )

        return ""


# ============================================================
# GET ELEMENT TEXT
# ============================================================

def safe_element_text(
    element,
):

    try:

        value = element.get_attribute(
            "innerText"
        )

        if value:

            return normalize_text(
                value
            )


    except Exception:

        pass


    try:

        return normalize_text(
            element.text
        )

    except Exception:

        return ""


# ============================================================
# CHECK SRL NAME
# ============================================================

def is_srl_name(
    name,
):

    value = normalize_text(
        name
    ).lower()

    return value.endswith(
        " srl"
    )


# ============================================================
# EXTRACT TOSS FROM SENTENCE
# ============================================================

def parse_toss_sentence(
    sentence,
):

    sentence = normalize_text(
        sentence
    )


    if not sentence:

        return None


    # --------------------------------------------------------
    # Only cricket toss text.
    # --------------------------------------------------------

    lower = sentence.lower()


    if "won the toss" not in lower:

        return None


    # --------------------------------------------------------
    # Winner:
    #
    # Karachi Kings SRL won the toss
    #
    # South Africa SRL won the toss
    # --------------------------------------------------------

    pattern = re.compile(
        r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)"
        r"\s+won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        re.IGNORECASE,
    )


    match = pattern.search(
        sentence
    )


    if not match:

        return None


    winner = normalize_text(
        match.group(1)
    )


    decision = normalize_text(
        match.group(2) or ""
    ).lower()


    if not is_srl_name(
        winner
    ):

        return None


    return {
        "winner": winner,
        "decision": decision,
        "raw": sentence,
    }


# ============================================================
# FIND TOSS DIRECTLY IN DOM
# ============================================================

def find_live_tosses(
    driver,
):

    results = []


    # --------------------------------------------------------
    # Search DOM elements containing "won the toss".
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Parse every matching element.
    # --------------------------------------------------------

    for element in elements:

        raw = safe_element_text(
            element
        )


        if not raw:

            continue


        toss = parse_toss_sentence(
            raw
        )


        if toss:

            results.append(
                toss
            )


    # --------------------------------------------------------
    # Remove duplicates.
    # --------------------------------------------------------

    unique = {}


    for toss in results:

        key = (
            toss["winner"].lower(),
            toss["decision"].lower(),
        )


        unique[key] = toss


    return list(
        unique.values()
    )


# ============================================================
# TEXT FALLBACK
# ============================================================

def find_tosses_from_page_text(
    page_text,
):

    results = []


    normalized = normalize_text(
        page_text
    )


    if not normalized:

        return results


    # --------------------------------------------------------
    # Search all occurrences.
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

        winner = normalize_text(
            match.group(1)
        )


        decision = normalize_text(
            match.group(2) or ""
        ).lower()


        if not is_srl_name(
            winner
        ):

            continue


        results.append(
            {
                "winner": winner,
                "decision": decision,
                "raw": match.group(0),
            }
        )


    return results


# ============================================================
# TOSS CODE FALLBACK
#
# Sportcentre sometimes displays:
#
# Toss:SA
# Toss:RR
# Toss:KK
# ============================================================

def find_toss_codes(
    page_text,
):

    results = []


    normalized = normalize_text(
        page_text
    )


    if not normalized:

        return results


    # --------------------------------------------------------
    # This is only a BACKUP.
    #
    # Primary detector remains:
    # "won the toss"
    # --------------------------------------------------------

    pattern = re.compile(
        r"Toss\s*:\s*"
        r"([A-Za-zÀ-ÿ0-9_-]+)",
        re.IGNORECASE,
    )


    for match in pattern.finditer(
        normalized
    ):

        code = normalize_text(
            match.group(1)
        )


        if not code:

            continue


        results.append(
            {
                "winner": code,
                "decision": "",
                "raw": match.group(0),
                "backup": True,
            }
        )


    return results


# ============================================================
# GET FIXTURE FROM PAGE
# ============================================================

def find_fixture_for_winner(
    driver,
    winner,
):

    winner_lower = normalize_text(
        winner
    ).lower()


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
                f"'{winner_lower}'"
                ")]"
            ),
        )


    except Exception:

        return ""


    # --------------------------------------------------------
    # Look for the smallest useful parent containing
    # the winner and another SRL team.
    # --------------------------------------------------------

    for element in elements:

        try:

            current = element

            for _ in range(6):

                try:

                    current = (
                        current.find_element(
                            By.XPATH,
                            ".."
                        )
                    )

                except Exception:

                    break


                value = safe_element_text(
                    current
                )


                if not value:

                    continue


                # Need another SRL team.
                names = re.findall(
                    r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*\sSRL",
                    value,
                    flags=re.IGNORECASE,
                )


                cleaned = []

                for name in names:

                    name = normalize_text(
                        name
                    )

                    if name.lower() not in {
                        x.lower()
                        for x in cleaned
                    }:

                        cleaned.append(
                            name
                        )


                if (
                    len(cleaned) >= 2
                    and any(
                        winner_lower
                        == x.lower()
                        for x in cleaned
                    )
                ):

                    # Usually first two names are
                    # the fixture teams.
                    return (
                        f"{cleaned[0]} vs "
                        f"{cleaned[1]}"
                    )


    return ""


# ============================================================
# BUILD TOSS ID
# ============================================================

def make_toss_id(
    toss,
    fixture="",
):

    raw = (
        f"{fixture.lower()}|"
        f"{toss['winner'].lower()}|"
        f"{toss['decision'].lower()}"
    )


    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:32]


# ============================================================
# DECISION FORMAT
# ============================================================

def format_decision(
    decision,
):

    value = normalize_text(
        decision
    ).lower()


    mapping = {
        "bat": "Elected to bat",
        "bowl": "Elected to bowl",
        "field": "Elected to field",
    }


    return mapping.get(
        value,
        "Not reported",
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
# TOSS MESSAGE
# ============================================================

def build_toss_message(
    toss,
    fixture="",
):

    now = current_ist()


    if not fixture:

        fixture = (
            "SRL Match"
        )


    decision = format_decision(
        toss["decision"]
    )


    return (
        "🏏 SRL TOSS ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🏆 {toss['winner']} "
        "WON THE TOSS\n\n"

        f"⚔️ {fixture}\n\n"

        f"🎯 Decision: {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}\n\n"

        "📡 Sportradar SRL Sportcentre\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# PROCESS TOSS
# ============================================================

def process_toss(
    driver,
    toss,
):

    fixture = find_fixture_for_winner(
        driver,
        toss["winner"],
    )


    identifier = make_toss_id(
        toss,
        fixture,
    )


    # --------------------------------------------------------
    # Duplicate protection.
    # --------------------------------------------------------

    if identifier in seen_tosses:

        log.info(
            "Duplicate toss ignored | %s | %s",
            toss["winner"],
            fixture,
        )

        return False


    log.info(
        "🔥 NEW SRL TOSS DETECTED | "
        "winner=%s | decision=%s | fixture=%s",
        toss["winner"],
        toss["decision"],
        fixture,
    )


    message = build_toss_message(
        toss,
        fixture,
    )


    log.info(
        "Sending Telegram toss alert..."
    )


    if not send_telegram(
        message
    ):

        log.error(
            "Telegram failed. Toss will be retried."
        )

        return False


    # --------------------------------------------------------
    # Save ONLY after Telegram succeeds.
    # --------------------------------------------------------

    seen_tosses.add(
        identifier
    )


    save_state()


    log.info(
        "✅ SRL TOSS TELEGRAM ALERT SENT | %s",
        toss["winner"],
    )


    return True


# ============================================================
# PAGE PREVIEW
# ============================================================

def log_page_preview(
    page_text,
):

    normalized = normalize_text(
        page_text
    )


    if not normalized:

        return


    log.info(
        "Rendered page text length: %s",
        len(normalized),
    )


    log.info(
        "PAGE PREVIEW: %s",
        normalized[:1500],
    )


# ============================================================
# MAIN MONITOR
# ============================================================

def monitor(
    driver,
):

    last_page_text = ""

    last_refresh = time.monotonic()


    while True:

        try:

            # =================================================
            # READ RENDERED DOM
            # =================================================

            page_text = get_rendered_text(
                driver
            )


            if page_text:

                normalized = normalize_text(
                    page_text
                )


                # ---------------------------------------------
                # Only log when page content changes.
                # ---------------------------------------------

                if normalized != last_page_text:

                    log_page_preview(
                        normalized
                    )

                    last_page_text = normalized


            # =================================================
            # PRIMARY DETECTOR
            #
            # DIRECT DOM SEARCH
            # =================================================

            dom_tosses = find_live_tosses(
                driver
            )


            for toss in dom_tosses:

                process_toss(
                    driver,
                    toss,
                )


            # =================================================
            # SECONDARY DETECTOR
            #
            # FULL RENDERED PAGE TEXT
            # =================================================

            text_tosses = (
                find_tosses_from_page_text(
                    page_text
                )
            )


            for toss in text_tosses:

                process_toss(
                    driver,
                    toss,
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


                log.info(
                    "Browser URL: %s",
                    driver.current_url,
                )


                # Reset only page-change logging.
                #
                # DO NOT clear seen_tosses.
                #
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
    # CREDENTIAL CHECK
    # ========================================================

    if not telegram_configured():

        log.error(
            "Telegram configuration missing."
        )

        log.error(
            "Set TELEGRAM_BOT_TOKEN and "
            "TELEGRAM_CHAT_ID in Railway."
        )

        return


    log.info(
        "Telegram configuration detected."
    )


    # ========================================================
    # LOAD STATE
    # ========================================================

    load_state()


    # ========================================================
    # CREATE DRIVER
    # ========================================================

    driver = None


    try:

        driver = create_driver()


        # ====================================================
        # OPEN PAGE
        # ====================================================

        open_srl_page(
            driver
        )


        # ====================================================
        # VERIFY PAGE
        # ====================================================

        page_text = get_rendered_text(
            driver
        )


        log_page_preview(
            page_text
        )


        # ====================================================
        # TELEGRAM STARTUP
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
        # START MONITOR
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
