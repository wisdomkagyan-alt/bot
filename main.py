# ============================================================
# SRL TOSS SELENIUM MONITOR 2026
#
# SRL CRICKET ONLY
#
# Source:
#   https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket
#
# Selenium + Chromium
# Rendered DOM detection
# Telegram alerts
#
# NO Sportradar API
# NO Playwright
# NO API 429
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

CHECK_INTERVAL = 2
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
# CHROME
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
# HTTP
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
# TEXT
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
# TELEGRAM
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
# CREATE CHROME DRIVER
# ============================================================

def create_driver():

    log.info(
        "Launching Chrome WebDriver..."
    )


    options = Options()


    # --------------------------------------------------------
    # Headless Linux / Railway
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
    # Chromium
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
    # ChromeDriver
    # --------------------------------------------------------

    if CHROMEDRIVER_PATH:

        log.info(
            "Using ChromeDriver: %s",
            CHROMEDRIVER_PATH,
        )

        from selenium.webdriver.chrome.service import Service

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
# OPEN SRL PAGE
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
# GET RENDERED PAGE TEXT
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
# CHECK SRL TEAM NAME
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
# EXTRACT SRL NAMES
# ============================================================

def extract_srl_names(
    value,
):

    value = clean_text(
        value
    )


    pattern = re.compile(
        r"\b"
        r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?"
        r"\sSRL)"
        r"\b",
        re.IGNORECASE,
    )


    names = []


    for match in pattern.finditer(
        value
    ):

        name = clean_text(
            match.group(1)
        )


        if not is_srl_team(
            name
        ):

            continue


        # Remove obvious UI/header text.
        if name.lower() in {
            "simulated reality league",
        }:

            continue


        if not any(
            name.lower() == existing.lower()
            for existing in names
        ):

            names.append(
                name
            )


    return names


# ============================================================
# PARSE TOSS SENTENCE
# ============================================================

def parse_toss(
    sentence,
):

    sentence = clean_text(
        sentence
    )


    if not sentence:

        return None


    lower = sentence.lower()


    if "won the toss" not in lower:

        return None


    # --------------------------------------------------------
    # Exact structure shown by SRL Sportcentre:
    #
    # Karachi Kings SRL won the toss and elected to bowl
    #
    # South Africa SRL won the toss and elected to bat
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


    winner = clean_text(
        match.group(1)
    )


    decision = clean_text(
        match.group(2) or ""
    ).lower()


    if not is_srl_team(
        winner
    ):

        return None


    return {
        "winner": winner,
        "decision": decision,
        "raw": sentence,
    }


# ============================================================
# DIRECT DOM TOSS SEARCH
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
            "Direct DOM search failed: %s",
            exc,
        )

        return results


    # --------------------------------------------------------
    # Process matching elements.
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Deduplicate.
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
# PAGE TEXT TOSS SEARCH
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

        winner = clean_text(
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
                "raw": match.group(0),
            }
        )


    return results


# ============================================================
# FIND FIXTURE FROM DOM
# ============================================================

def find_fixture(
    driver,
    winner,
):

    winner_lower = clean_text(
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
    # Start at matching element and move upward.
    # --------------------------------------------------------

    for element in elements:

        current = element


        for _ in range(7):

            try:

                current = current.find_element(
                    By.XPATH,
                    ".."
                )

            except Exception:

                break


            value = clean_text(
                current.get_attribute(
                    "innerText"
                )
            )


            if not value:

                continue


            names = extract_srl_names(
                value
            )


            # ------------------------------------------------
            # Need winner + opponent.
            # ------------------------------------------------

            winner_index = None


            for index, name in enumerate(
                names
            ):

                if (
                    name.lower()
                    == winner_lower
                ):

                    winner_index = index
                    break


            if winner_index is None:

                continue


            # ------------------------------------------------
            # Prefer the nearest other SRL name.
            # ------------------------------------------------

            candidates = [
                name
                for name in names
                if name.lower()
                != winner_lower
            ]


            if not candidates:

                continue


            opponent = candidates[0]


            # ------------------------------------------------
            # If the row has only two teams, excellent.
            # ------------------------------------------------

            if len(names) == 2:

                return (
                    f"{names[0]} vs "
                    f"{names[1]}"
                )


            # ------------------------------------------------
            # For larger ancestor elements, use the nearest
            # name around the winner.
            # ------------------------------------------------

            if winner_index > 0:

                opponent = names[
                    winner_index - 1
                ]

            elif winner_index + 1 < len(names):

                opponent = names[
                    winner_index + 1
                ]


            return (
                f"{winner} vs "
                f"{opponent}"
            )


    return ""


# ============================================================
# FALLBACK: FIND FIXTURE FROM TOSS TEXT
# ============================================================

def find_fixture_from_text(
    page_text,
    winner,
):

    normalized = clean_text(
        page_text
    )


    names = extract_srl_names(
        normalized
    )


    # We cannot safely determine the opponent from the whole
    # page if many SRL matches exist.
    #
    # Therefore return blank and let the DOM method handle it.

    return ""


# ============================================================
# MAKE UNIQUE TOSS ID
# ============================================================

def make_toss_id(
    toss,
    fixture,
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
# FORMAT DECISION
# ============================================================

def format_decision(
    decision,
):

    value = clean_text(
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
# CURRENT IST TIME
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
# BUILD TELEGRAM MESSAGE
# ============================================================

def build_toss_message(
    toss,
    fixture,
):

    now = current_ist()


    if not fixture:

        fixture = "SRL Match"


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
# PROCESS ONE TOSS
# ============================================================

def process_toss(
    driver,
    toss,
):

    fixture = find_fixture(
        driver,
        toss["winner"],
    )


    if not fixture:

        fixture = find_fixture_from_text(
            get_page_text(driver),
            toss["winner"],
        )


    identifier = make_toss_id(
        toss,
        fixture,
    )


    # --------------------------------------------------------
    # DUPLICATE PROTECTION
    # --------------------------------------------------------

    if identifier in seen_tosses:

        log.info(
            "Duplicate toss ignored | "
            "%s | %s",
            toss["winner"],
            fixture,
        )

        return False


    # --------------------------------------------------------
    # NEW TOSS
    # --------------------------------------------------------

    log.info(
        "🔥 NEW SRL TOSS DETECTED | "
        "winner=%s | decision=%s | fixture=%s",
        toss["winner"],
        toss["decision"],
        fixture,
    )


    log.info(
        "RAW TOSS TEXT | %s",
        toss["raw"][:500],
    )


    message = build_toss_message(
        toss,
        fixture,
    )


    # --------------------------------------------------------
    # TELEGRAM
    # --------------------------------------------------------

    if not send_telegram(
        message
    ):

        log.error(
            "Telegram failed. "
            "Toss will be retried."
        )

        return False


    # --------------------------------------------------------
    # SAVE ONLY AFTER SUCCESS
    # --------------------------------------------------------

    seen_tosses.add(
        identifier
    )


    save_state()


    log.info(
        "✅ SRL TOSS TELEGRAM ALERT SENT | "
        "%s",
        toss["winner"],
    )


    return True


# ============================================================
# BASELINE EXISTING TOSSES
# ============================================================

def baseline_existing_tosses(
    driver,
):

    log.info(
        "Creating initial toss baseline..."
    )


    page_text = get_page_text(
        driver
    )


    tosses = find_text_tosses(
        page_text
    )


    if not tosses:

        log.info(
            "No existing tosses found "
            "during baseline."
        )

        return


    count = 0


    for toss in tosses:

        fixture = find_fixture(
            driver,
            toss["winner"],
        )


        identifier = make_toss_id(
            toss,
            fixture,
        )


        if identifier not in seen_tosses:

            seen_tosses.add(
                identifier
            )

            count += 1


    save_state()


    log.info(
        "Initial baseline complete | "
        "%s tosses recorded without alert.",
        count,
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
    # IMPORTANT:
    #
    # Existing completed matches on the page should NOT
    # generate alerts when the bot first starts.
    # --------------------------------------------------------

    baseline_existing_tosses(
        driver
    )


    while True:

        try:

            # =================================================
            # READ CURRENT RENDERED PAGE
            # =================================================

            page_text = get_page_text(
                driver
            )


            normalized = clean_text(
                page_text
            )


            if normalized:

                # ---------------------------------------------
                # Log only changed page.
                # ---------------------------------------------

                if normalized != last_page_text:

                    log_page_preview(
                        normalized
                    )

                    last_page_text = normalized


            # =================================================
            # PRIMARY DETECTOR
            # =================================================

            dom_tosses = find_dom_tosses(
                driver
            )


            for toss in dom_tosses:

                process_toss(
                    driver,
                    toss,
                )


            # =================================================
            # SECONDARY DETECTOR
            # =================================================

            text_tosses = find_text_tosses(
                page_text
            )


            for toss in text_tosses:

                process_toss(
                    driver,
                    toss,
                )


            # =================================================
            # PERIODIC REFRESH
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


                # Give the page time to render.

                time.sleep(5)


                log.info(
                    "Browser URL: %s",
                    driver.current_url,
                )


                # Force next page preview.

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
    # TELEGRAM
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
        # OPEN SRL
        # ====================================================

        open_page(
            driver
        )


        # ====================================================
        # VERIFY PAGE
        # ====================================================

        page_text = get_page_text(
            driver
        )


        log_page_preview(
            page_text
        )


        # ====================================================
        # STARTUP TELEGRAM
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
