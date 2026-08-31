#============================================================
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
#
# USE RAILWAY VARIABLES ONLY
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU"
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "8783763018"
).strip()

# ============================================================
# CHROMIUM
# ============================================================

CHROME_BINARY = os.getenv(
    "CHROME_BINARY",
    "/usr/bin/chromium"
).strip()

CHROMEDRIVER_PATH = os.getenv(
    "CHROMEDRIVER_PATH",
    ""
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
# TEXT CLEANER
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    value = str(value)

    value = value.replace(
        "\xa0",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()

# ============================================================
# JSON LOAD
# ============================================================

def load_json(
    path,
    default
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
            exc
        )

        return default

# ============================================================
# JSON SAVE
# ============================================================

def save_json(
    path,
    data
):

    try:

        path.write_text(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

    except Exception as exc:

        log.error(
            "Could not save %s: %s",
            path,
            exc
        )

# ============================================================
# LOAD STATE
# ============================================================

def load_state():

    global seen_tosses

    data = load_json(
        STATE_FILE,
        []
    )

    if isinstance(
        data,
        list
    ):

        seen_tosses = {
            str(x)
            for x in data
        }

        log.info(
            "Loaded %s seen toss IDs.",
            len(seen_tosses)
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
        sorted(seen_tosses)
    )

# ============================================================
# HEARTBEAT
# ============================================================

def heartbeat(
    status
):

    try:

        HEARTBEAT_FILE.write_text(
            (
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"{SYSTEM_VERSION} | "
                f"{status}\n"
            ),
            encoding="utf-8"
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
    message
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
        "disable_web_page_preview": True
    }

    for attempt in range(
        1,
        4
    ):

        try:

            response = http.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT
            )

            if response.status_code == 200:

                return True

            log.error(
                "Telegram HTTP %s | %s",
                response.status_code,
                response.text[:500]
            )

        except requests.RequestException as exc:

            log.error(
                "Telegram attempt %s failed: %s",
                attempt,
                exc
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
                CHROME_BINARY
            )

        else:

            log.warning(
                "Chrome binary not found: %s",
                CHROME_BINARY
            )

    # --------------------------------------------------------
    # ChromeDriver
    # --------------------------------------------------------

    if CHROMEDRIVER_PATH:

        from selenium.webdriver.chrome.service import Service

        service = Service(
            CHROMEDRIVER_PATH
        )

        driver = webdriver.Chrome(
            service=service,
            options=options
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
    driver
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
            exc
        )

    time.sleep(5)

    try:

        log.info(
            "Browser URL: %s",
            driver.current_url
        )

        log.info(
            "Browser title: %s",
            driver.title
        )

    except Exception:

        pass

# ============================================================
# PAGE TEXT
# ============================================================

def get_page_text(
    driver
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
            exc
        )

        return ""

# ============================================================
# PAGE PREVIEW
# ============================================================

def log_page_preview(
    page_text
):

    value = clean_text(
        page_text
    )

    if not value:
        return

    log.info(
        "Rendered page text length: %s",
        len(value)
    )

    log.info(
        "PAGE PREVIEW: %s",
        value[:1500]
    )

# ============================================================
# SRL TEAM
# ============================================================

def is_srl_team(
    name
):

    value = clean_text(
        name
    )

    return value.lower().endswith(
        " srl"
    )

# ============================================================
# CLEAN TEAM NAME
# ============================================================

def clean_team_name(
    value
):

    value = clean_text(
        value
    )

    value = re.sub(
        r"^\d+(?:\.\d+)?\s*(?:OV|OVERS?)\s+",
        "",
        value,
        flags=re.IGNORECASE
    )

    value = re.sub(
        r"^\d+(?:/\d+)?\s+",
        "",
        value
    )

    return clean_text(
        value
    )

# ============================================================
# EXTRACT SRL TEAMS FROM DOM TEXT
#
# IMPORTANT:
# This deliberately does NOT use re.IGNORECASE.
# It prevents score fragments such as "0/0" from
# becoming part of a team name.
# ============================================================

def extract_srl_teams(
    value
):

    value = clean_text(
        value
    )

    pattern = re.compile(
        r"\b("
        r"[A-ZÀ-Ý]"
        r"[A-Za-zÀ-ÿ0-9 .&'_-]*?"
        r"\sSRL"
        r")\b"
    )

    found = []

    for match in pattern.finditer(
        value
    ):

        team = clean_team_name(
            match.group(1)
        )

        if not is_srl_team(
            team
        ):

            continue

        if team not in found:

            found.append(
                team
            )

    return found

# ============================================================
# FIXTURE EXTRACTION
#
# Looks at the text immediately surrounding the toss.
#
# If the DOM row contains:
#
# Joburg Super Kings SRL
# Durban Super Giants SRL
# Joburg Super Kings SRL won the toss...
#
# the fixture becomes:
#
# Joburg Super Kings SRL
# vs
# Durban Super Giants SRL
# ============================================================

def extract_fixture(
    value,
    winner
):

    value = clean_text(
        value
    )

    winner = clean_team_name(
        winner
    )

    if not value:

        return (
            "",
            ""
        )

    # --------------------------------------------------------
    # Only examine text before "won the toss".
    # --------------------------------------------------------

    lower = value.lower()

    position = lower.find(
        "won the toss"
    )

    if position >= 0:

        before_toss = value[
            :position
        ]

    else:

        before_toss = value

    teams = extract_srl_teams(
        before_toss
    )

    # --------------------------------------------------------
    # If there are at least two teams,
    # use the final two distinct teams.
    # --------------------------------------------------------

    if len(teams) >= 2:

        team2 = teams[-1]

        remaining = [
            x for x in teams[:-1]
            if x.lower() != team2.lower()
        ]

        if remaining:

            team1 = remaining[-1]

            return (
                team1,
                team2
            )

    # --------------------------------------------------------
    # Sometimes the winner appears immediately before
    # "won the toss", while the opponent is in the same
    # DOM row but after/before another element.
    # Search whole candidate text.
    # --------------------------------------------------------

    teams = extract_srl_teams(
        value
    )

    unique = []

    for team in teams:

        if team.lower() not in {
            x.lower() for x in unique
        }:

            unique.append(
                team
            )

    if len(unique) >= 2:

        return (
            unique[-2],
            unique[-1]
        )

    return (
        "",
        ""
    )

# ============================================================
# PARSE TOSS SENTENCE
# ============================================================

def parse_toss(
    sentence
):

    sentence = clean_text(
        sentence
    )

    if not sentence:

        return None

    if "won the toss" not in sentence.lower():

        return None

    pattern = re.compile(
        r"([A-Za-zÀ-ÿ0-9]"
        r"[A-Za-zÀ-ÿ0-9 .&'_-]*?"
        r"\sSRL)"
        r"\s+won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        re.IGNORECASE
    )

    matches = list(
        pattern.finditer(
            sentence
        )
    )

    if not matches:

        return None

    match = matches[-1]

    winner = clean_team_name(
        match.group(1)
    )

    decision = clean_text(
        match.group(2) or ""
    ).lower()

    if not is_srl_team(
        winner
    ):

        return None

    team1, team2 = extract_fixture(
        sentence,
        winner
    )

    return {
        "winner": winner,
        "decision": decision,
        "team1": team1,
        "team2": team2
    }

# ============================================================
# FIND DOM TOSSES
#
# IMPROVED:
# We inspect the toss element AND its ancestors.
# This is the important fix for signals such as JSK.
# ============================================================

def find_dom_tosses(
    driver
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
            )
        )

    except Exception as exc:

        log.warning(
            "DOM toss search failed: %s",
            exc
        )

        return results

    for element in elements:

        candidates = []

        # ----------------------------------------------------
        # Current element.
        # ----------------------------------------------------

        try:

            current_text = clean_text(
                element.get_attribute(
                    "innerText"
                )
            )

            if current_text:

                candidates.append(
                    current_text
                )

        except Exception:

            pass

        # ----------------------------------------------------
        # Walk ancestors.
        #
        # We stop after 10 levels.
        # ----------------------------------------------------

        current = element

        for _ in range(10):

            try:

                current = current.find_element(
                    By.XPATH,
                    ".."
                )

                parent_text = clean_text(
                    current.get_attribute(
                        "innerText"
                    )
                )

                if parent_text:

                    # Don't keep enormous page-level elements.
                    if len(parent_text) <= 1200:

                        candidates.append(
                            parent_text
                        )

            except Exception:

                break

        # ----------------------------------------------------
        # Prefer the SMALLEST candidate that gives us
        # a fixture.
        # ----------------------------------------------------

        candidates = sorted(
            set(candidates),
            key=len
        )

        selected_toss = None

        for candidate in candidates:

            toss = parse_toss(
                candidate
            )

            if not toss:

                continue

            if (
                toss["team1"]
                and toss["team2"]
            ):

                selected_toss = toss
                break

            if selected_toss is None:

                selected_toss = toss

        if selected_toss:

            results.append(
                selected_toss
            )

    return deduplicate_tosses(
        results
    )

# ============================================================
# PAGE TEXT FALLBACK
#
# Kept as a backup if DOM structure changes.
# ============================================================

def find_text_tosses(
    page_text
):

    results = []

    normalized = clean_text(
        page_text
    )

    if not normalized:

        return results

    pattern = re.compile(
        r"([A-Za-zÀ-ÿ0-9]"
        r"[A-Za-zÀ-ÿ0-9 .&'_-]*?"
        r"\sSRL)"
        r"\s+won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        re.IGNORECASE
    )

    for match in pattern.finditer(
        normalized
    ):

        winner = clean_team_name(
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
                "team1": "",
                "team2": ""
            }
        )

    return deduplicate_tosses(
        results
    )

# ============================================================
# DEDUPLICATE SCAN RESULTS
# ============================================================

def deduplicate_tosses(
    tosses
):

    unique = {}

    for toss in tosses:

        winner = clean_team_name(
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

        team1 = clean_team_name(
            toss.get(
                "team1",
                ""
            )
        )

        team2 = clean_team_name(
            toss.get(
                "team2",
                ""
            )
        )

        if not winner:

            continue

        # ----------------------------------------------------
        # Use fixture when available.
        # ----------------------------------------------------

        if team1 and team2:

            key = (
                winner.lower(),
                team1.lower(),
                team2.lower(),
                decision
            )

        else:

            key = (
                winner.lower(),
                decision
            )

        unique[key] = {
            "winner": winner,
            "decision": decision,
            "team1": team1,
            "team2": team2
        }

    return list(
        unique.values()
    )

# ============================================================
# IST
# ============================================================

def current_ist():

    ist = timezone(
        timedelta(
            hours=5,
            minutes=30
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
    decision
):

    value = clean_text(
        decision
    ).lower()

    if value == "bat":

        return "Elected to bat"

    if value in {
        "bowl",
        "field"
    }:

        return "Elected to bowl"

    return "Not reported"

# ============================================================
# TOSS MESSAGE
#
# KEEPING YOUR CURRENT SIMPLE FORMAT
# ============================================================

def build_toss_message(
    toss
):

    now = current_ist()

    decision = format_decision(
        toss.get(
            "decision",
            ""
        )
    )

    return (
        "🏏 SRL TOSS ALERT\n\n"

        f"🏆 {toss['winner']} WON THE TOSS\n\n"

        "⚔️ SRL Match\n\n"

        f"🎯 Decision: {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}\n\n"

        "📡 Sportradar SRL Sportcentre\n"
        "🔔 LIVE TOSS MONITOR"
    )

# ============================================================
# TOSS ID
#
# IMPORTANT FIX:
#
# Fixture is included when available.
#
# Therefore:
#
# JSK + BAT + Match A
#
# is different from:
#
# JSK + BAT + Match B
# ============================================================

def make_toss_id(
    toss
):

    winner = clean_text(
        toss.get(
            "winner",
            ""
        )
    ).lower()

    decision = clean_text(
        toss.get(
            "decision",
            ""
        )
    ).lower()

    team1 = clean_text(
        toss.get(
            "team1",
            ""
        )
    ).lower()

    team2 = clean_text(
        toss.get(
            "team2",
            ""
        )
    ).lower()

    # --------------------------------------------------------
    # BEST ID
    # --------------------------------------------------------

    if team1 and team2:

        raw = (
            f"{team1}|"
            f"{team2}|"
            f"{winner}|"
            f"{decision}"
        )

    else:

        # Fallback only when page text gives no fixture.
        raw = (
            f"{winner}|"
            f"{decision}"
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
    toss
):

    winner = clean_team_name(
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

        return False

    toss["winner"] = winner

    team1 = clean_team_name(
        toss.get(
            "team1",
            ""
        )
    )

    team2 = clean_team_name(
        toss.get(
            "team2",
            ""
        )
    )

    toss["team1"] = team1
    toss["team2"] = team2

    identifier = make_toss_id(
        toss
    )

    # --------------------------------------------------------
    # DUPLICATE
    # --------------------------------------------------------

    if identifier in seen_tosses:

        log.debug(
            "Duplicate toss ignored | "
            "%s | %s | %s vs %s",
            winner,
            toss.get("decision", ""),
            team1,
            team2
        )

        return False

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    log.info(
        "🔥 NEW SRL TOSS DETECTED | "
        "winner=%s | decision=%s | "
        "fixture=%s vs %s",
        winner,
        toss.get(
            "decision",
            ""
        ),
        team1 or "SRL",
        team2 or "Match"
    )

    # --------------------------------------------------------
    # MESSAGE
    # --------------------------------------------------------

    message = build_toss_message(
        toss
    )

    # --------------------------------------------------------
    # SEND
    # --------------------------------------------------------

    success = send_telegram(
        message
    )

    if not success:

        log.error(
            "Telegram failed. "
            "Toss will be retried."
        )

        return False

    # --------------------------------------------------------
    # MARK ONLY AFTER SUCCESS
    # --------------------------------------------------------

    seen_tosses.add(
        identifier
    )

    save_state()

    log.info(
        "✅ SRL TOSS ALERT SENT ONCE | "
        "%s | %s",
        winner,
        toss.get(
            "decision",
            ""
        )
    )

    return True

# ============================================================
# MONITOR
# ============================================================

def monitor(
    driver
):

    last_page_text = ""

    last_refresh = (
        time.monotonic()
    )

    while True:

        try:

            # =================================================
            # READ PAGE
            # =================================================

            page_text = get_page_text(
                driver
            )

            normalized = clean_text(
                page_text
            )

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
            # FALLBACK PAGE TEXT DETECTOR
            # =================================================

            text_tosses = find_text_tosses(
                page_text
            )

            for toss in text_tosses:

                process_toss(
                    toss
                )

            # =================================================
            # REFRESH
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
                        exc
                    )

                time.sleep(5)

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
                exc
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
        SYSTEM_VERSION
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

    driver = None

    try:

        # ====================================================
        # CHROME
        # ====================================================

        driver = create_driver()

        # ====================================================
        # OPEN
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
        # STARTUP
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
            exc
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
