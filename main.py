# ============================================================
# SRL TOSS + DAILY FIXTURE SELENIUM MONITOR 2026
#
# SRL CRICKET ONLY
#
# SOURCE:
# https://sportcenter.sir.sportradar.com/
# pt/simulated-reality/cricket
#
# FEATURES
# ------------------------------------------------------------
# 1. Selenium + Chromium
# 2. Rendered DOM detection
# 3. SRL toss detection
# 4. Toss fixture detection
# 5. Telegram toss alerts
# 6. Daily fixture board at 00:10 IST
# 7. Fixture board follows Sportradar league/page order
# 8. Duplicate protection
# 9. Automatic page refresh
# 10. Railway compatible
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

# Daily fixture message window.
#
# The bot checks continuously.
# If it is between 00:10 and 00:20 IST,
# the daily fixture message is sent once.
DAILY_FIXTURE_HOUR = 0
DAILY_FIXTURE_MINUTE = 10
DAILY_FIXTURE_WINDOW_MINUTES = 10


# ============================================================
# TELEGRAM
#
# SET THESE IN RAILWAY VARIABLES
#
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    ""
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    ""
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
# STATE FILES
# ============================================================

STATE_FILE = Path(
    "seen_tosses.json"
)

FIXTURE_STATE_FILE = Path(
    "sent_fixture_dates.json"
)

HEARTBEAT_FILE = Path(
    "srl_toss_heartbeat.txt"
)


# ============================================================
# STATE
# ============================================================

seen_tosses = set()

sent_fixture_dates = set()


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
# LOAD TOSS STATE
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
            "No previous toss state found."
        )


# ============================================================
# SAVE TOSS STATE
# ============================================================

def save_state():

    save_json(
        STATE_FILE,
        sorted(
            seen_tosses
        )
    )


# ============================================================
# LOAD DAILY FIXTURE STATE
# ============================================================

def load_fixture_state():

    global sent_fixture_dates

    data = load_json(
        FIXTURE_STATE_FILE,
        []
    )

    if isinstance(
        data,
        list
    ):

        sent_fixture_dates = {
            str(x)
            for x in data
        }

        log.info(
            "Loaded %s daily fixture dates.",
            len(sent_fixture_dates)
        )

    else:

        sent_fixture_dates = set()


# ============================================================
# SAVE DAILY FIXTURE STATE
# ============================================================

def save_fixture_state():

    save_json(
        FIXTURE_STATE_FILE,
        sorted(
            sent_fixture_dates
        )
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
        "📋 Daily fixtures: 00:10 IST\n"
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
# SRL TEAM CHECK
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

    # Remove score/over prefixes.

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
# EXTRACT SRL TEAMS
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

        duplicate = False

        for old in found:

            if old.lower() == team.lower():

                duplicate = True

                break

        if not duplicate:

            found.append(
                team
            )

    return found


# ============================================================
# FIXTURE EXTRACTION
#
# This is deliberately robust.
#
# It checks:
#
# 1. Text before toss
# 2. Whole DOM candidate
# 3. Nearby SRL team names
#
# Example:
#
# Royal Challengers Bangalore SRL
# 30 AGO | 14:30
# Chennai Super Kings SRL
#
# Chennai Super Kings SRL won the toss...
#
# Result:
#
# Royal Challengers Bangalore SRL
# vs
# Chennai Super Kings SRL
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
    # Remove toss result portion.
    # --------------------------------------------------------

    lower = value.lower()

    toss_position = lower.find(
        "won the toss"
    )

    if toss_position >= 0:

        before_toss = value[
            :toss_position
        ]

    else:

        before_toss = value

    # --------------------------------------------------------
    # Extract teams before toss.
    # --------------------------------------------------------

    teams = extract_srl_teams(
        before_toss
    )

    # --------------------------------------------------------
    # Remove duplicates while preserving order.
    # --------------------------------------------------------

    unique = []

    for team in teams:

        if not any(
            team.lower() == x.lower()
            for x in unique
        ):

            unique.append(
                team
            )

    # --------------------------------------------------------
    # If winner is present, fixture is usually:
    #
    # previous team + winner
    #
    # or
    #
    # winner + opponent
    # --------------------------------------------------------

    winner_index = -1

    for index, team in enumerate(
        unique
    ):

        if team.lower() == winner.lower():

            winner_index = index

    # --------------------------------------------------------
    # Best case:
    # winner is the final team before toss.
    # Previous team is opponent.
    # --------------------------------------------------------

    if winner_index >= 0:

        if winner_index > 0:

            opponent = unique[
                winner_index - 1
            ]

            return (
                opponent,
                winner
            )

    # --------------------------------------------------------
    # If there are exactly two teams,
    # use them directly.
    # --------------------------------------------------------

    if len(unique) >= 2:

        return (
            unique[-2],
            unique[-1]
        )

    # --------------------------------------------------------
    # Search whole candidate.
    # --------------------------------------------------------

    all_teams = extract_srl_teams(
        value
    )

    unique_all = []

    for team in all_teams:

        if not any(
            team.lower() == x.lower()
            for x in unique_all
        ):

            unique_all.append(
                team
            )

    if len(unique_all) >= 2:

        return (
            unique_all[-2],
            unique_all[-1]
        )

    return (
        "",
        ""
    )


# ============================================================
# PARSE TOSS
# ============================================================

def parse_toss(
    sentence
):

    sentence = clean_text(
        sentence
    )

    if not sentence:

        return None

    lower = sentence.lower()

    if "won the toss" not in lower:

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
# IMPORTANT FIX
#
# Inspect the toss element and several ancestors.
# The fixture is normally stored in the parent match row.
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
        # Current element
        # ----------------------------------------------------

        try:

            text = clean_text(
                element.get_attribute(
                    "innerText"
                )
            )

            if text:

                candidates.append(
                    text
                )

        except Exception:

            pass

        # ----------------------------------------------------
        # Ancestors
        # ----------------------------------------------------

        current = element

        for _ in range(12):

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

                if not parent_text:

                    continue

                # Ignore enormous page containers.

                if len(parent_text) <= 2000:

                    candidates.append(
                        parent_text
                    )

            except Exception:

                break

        # ----------------------------------------------------
        # Also inspect nearby siblings through JS.
        #
        # This helps when team names are siblings rather
        # than inside the exact toss element.
        # ----------------------------------------------------

        try:

            sibling_text = driver.execute_script(
                """
                const el = arguments[0];

                let node = el;

                for (let i = 0; i < 5 && node; i++) {

                    let parent = node.parentElement;

                    if (!parent) break;

                    let txt = parent.innerText || "";

                    if (txt.length <= 2000) {
                        return txt;
                    }

                    node = parent;
                }

                return "";
                """,
                element
            )

            sibling_text = clean_text(
                sibling_text
            )

            if sibling_text:

                candidates.append(
                    sibling_text
                )

        except Exception:

            pass

        # ----------------------------------------------------
        # Smallest useful candidate first.
        # ----------------------------------------------------

        candidates = sorted(
            set(candidates),
            key=len
        )

        selected = None

        for candidate in candidates:

            toss = parse_toss(
                candidate
            )

            if not toss:

                continue

            # Prefer candidate with fixture.

            if (
                toss["team1"]
                and toss["team2"]
            ):

                selected = toss

                break

            if selected is None:

                selected = toss

        if selected:

            results.append(
                selected
            )

    return deduplicate_tosses(
        results
    )


# ============================================================
# PAGE TEXT TOSS FALLBACK
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

        # Page text fallback normally cannot safely
        # determine fixture, so leave blank.

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
# DEDUPLICATE TOSS SCAN RESULTS
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

        # Fixture-aware key.

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

        # If fixture version appears later,
        # replace the fixture-less version.

        if key not in unique:

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
# IST TIME
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

        return "BAT"

    if value in {
        "bowl",
        "field"
    }:

        return "BOWL"

    return "NOT REPORTED"


# ============================================================
# TOSS MESSAGE
#
# NEW FORMAT:
#
# 🏏 SRL TOSS ALERT
#
# 🏆 Chennai Super Kings SRL WON THE TOSS
#
# Chennai Super Kings SRL vs Mumbai Indians SRL
#
# 🎯 BOWL
# ⏰ 27 Aug 2026 | 09:20:25 IST
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

    winner = clean_team_name(
        toss.get(
            "winner",
            ""
        )
    )

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

    # --------------------------------------------------------
    # Fixture available.
    # --------------------------------------------------------

    if team1 and team2:

        fixture = (
            f"{team1} vs {team2}"
        )

    else:

        fixture = "SRL Match"

    return (
        "🏏 SRL TOSS ALERT\n\n"

        f"🏆 {winner} WON THE TOSS\n\n"

        f"{fixture}\n\n"

        f"🎯 {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}"
    )


# ============================================================
# TOSS ID
#
# Fixture is included whenever available.
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

    if team1 and team2:

        raw = (
            f"{team1}|"
            f"{team2}|"
            f"{winner}|"
            f"{decision}"
        )

    else:

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

    toss["team1"] = clean_team_name(
        toss.get(
            "team1",
            ""
        )
    )

    toss["team2"] = clean_team_name(
        toss.get(
            "team2",
            ""
        )
    )

    identifier = make_toss_id(
        toss
    )

    # --------------------------------------------------------
    # DUPLICATE
    # --------------------------------------------------------

    if identifier in seen_tosses:

        return False

    # --------------------------------------------------------
    # LOG
    # --------------------------------------------------------

    log.info(
        "🔥 NEW SRL TOSS | "
        "winner=%s | decision=%s | "
        "fixture=%s vs %s",
        winner,
        toss.get(
            "decision",
            ""
        ),
        toss["team1"] or "SRL",
        toss["team2"] or "Match"
    )

    # --------------------------------------------------------
    # BUILD MESSAGE
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
            "Telegram failed. Toss will be retried."
        )

        return False

    # --------------------------------------------------------
    # MARK AFTER SUCCESS
    # --------------------------------------------------------

    seen_tosses.add(
        identifier
    )

    save_state()

    log.info(
        "✅ SRL TOSS ALERT SENT ONCE | %s",
        winner
    )

    return True


# ============================================================
# DAILY FIXTURE SUPPORT
# ============================================================

LEAGUE_NAMES = [
    "Pakistan Super League SRL",
    "SA20 SRL",
    "T20 International SRL",
    "Super Smash SRL",
    "Indian Premier League SRL",
]


# ============================================================
# NORMALIZE DATE MONTH
# ============================================================

def normalize_month(
    month
):

    value = clean_text(
        month
    ).upper()

    month_map = {
        "JAN": 1,
        "JANUARY": 1,

        "FEB": 2,
        "FEV": 2,
        "FEBRUARY": 2,

        "MAR": 3,
        "MARÇO": 3,
        "MARCH": 3,

        "APR": 4,
        "ABR": 4,
        "APRIL": 4,

        "MAY": 5,
        "MAI": 5,

        "JUN": 6,
        "JUNE": 6,

        "JUL": 7,
        "JULHO": 7,
        "JULY": 7,

        "AUG": 8,
        "AGO": 8,
        "AUGUST": 8,

        "SEP": 9,
        "SET": 9,
        "SEPT": 9,
        "SEPTEMBER": 9,

        "OCT": 10,
        "OUT": 10,
        "OCTOBER": 10,

        "NOV": 11,
        "NOVEMBER": 11,

        "DEC": 12,
        "DEZ": 12,
        "DECEMBER": 12,
    }

    return month_map.get(
        value,
        0
    )


# ============================================================
# TARGET DATE
# ============================================================

def target_date_strings():

    now = current_ist()

    day = now.day

    year = now.year

    month_number = now.month

    month_names = {
        1: ["JAN", "JANUARY"],
        2: ["FEB", "FEV", "FEBRUARY"],
        3: ["MAR", "MARCH"],
        4: ["APR", "ABR", "APRIL"],
        5: ["MAY", "MAI"],
        6: ["JUN", "JUNE"],
        7: ["JUL", "JULY"],
        8: ["AUG", "AGO", "AUGUST"],
        9: ["SEP", "SET", "SEPT", "SEPTEMBER"],
        10: ["OCT", "OUT", "OCTOBER"],
        11: ["NOV", "NOVEMBER"],
        12: ["DEC", "DEZ", "DECEMBER"],
    }

    return {
        "day": day,
        "year": year,
        "months": month_names.get(
            month_number,
            []
        )
    }


# ============================================================
# PARSE FIXTURE LINES
#
# Expected rendered structure:
#
# League
# Team 1
# 30 AGO | 15:30
# Team 2
#
# Team 1
# 30 AGO | 21:30
# Team 2
# ============================================================

def parse_daily_fixtures(
    page_text
):

    fixtures = []

    if not page_text:

        return fixtures

    lines = page_text.splitlines()

    # --------------------------------------------------------
    # Clean lines but preserve individual lines.
    # --------------------------------------------------------

    cleaned_lines = []

    for line in lines:

        value = clean_text(
            line
        )

        if value:

            cleaned_lines.append(
                value
            )

    target = target_date_strings()

    current_league = None

    i = 0

    while i < len(cleaned_lines):

        line = cleaned_lines[i]

        # ----------------------------------------------------
        # Detect league.
        # ----------------------------------------------------

        for league in LEAGUE_NAMES:

            if line.lower() == league.lower():

                current_league = league

                break

        # ----------------------------------------------------
        # Look for date/time line.
        #
        # Examples:
        #
        # 30 AGO | 15:30
        # 30 AUG | 15:30
        # ----------------------------------------------------

        date_match = re.search(
            r"(\d{1,2})\s+"
            r"([A-Za-zÀ-ÿ]+)"
            r"\s*\|\s*"
            r"(\d{1,2}:\d{2})",
            line,
            re.IGNORECASE
        )

        if date_match:

            day = int(
                date_match.group(1)
            )

            month_text = date_match.group(2)

            month_number = normalize_month(
                month_text
            )

            time_value = date_match.group(3)

            # ------------------------------------------------
            # Only current day.
            # ------------------------------------------------

            if (
                day == target["day"]
                and month_number
                == current_ist().month
                and current_league
            ):

                # --------------------------------------------
                # Normally:
                #
                # previous line = team1
                # current line = date
                # next line = team2
                # --------------------------------------------

                team1 = ""
                team2 = ""

                if i > 0:

                    previous = clean_team_name(
                        cleaned_lines[i - 1]
                    )

                    if is_srl_team(
                        previous
                    ):

                        team1 = previous

                if i + 1 < len(
                    cleaned_lines
                ):

                    following = clean_team_name(
                        cleaned_lines[i + 1]
                    )

                    if is_srl_team(
                        following
                    ):

                        team2 = following

                # --------------------------------------------
                # Validate fixture.
                # --------------------------------------------

                if (
                    team1
                    and team2
                ):

                    fixtures.append(
                        {
                            "league": current_league,
                            "time": time_value,
                            "team1": team1,
                            "team2": team2
                        }
                    )

        i += 1

    return deduplicate_fixtures(
        fixtures
    )


# ============================================================
# FIXTURE DEDUPLICATION
# ============================================================

def deduplicate_fixtures(
    fixtures
):

    result = []

    seen = set()

    for fixture in fixtures:

        key = (
            fixture["league"].lower(),
            fixture["time"],
            fixture["team1"].lower(),
            fixture["team2"].lower()
        )

        if key in seen:

            continue

        seen.add(
            key
        )

        result.append(
            fixture
        )

    return result


# ============================================================
# FORMAT DAILY FIXTURE MESSAGE
#
# EXACT STYLE REQUESTED
#
# League order follows Sportradar.
# Fixture order follows Sportradar.
# ============================================================

def build_daily_fixture_message(
    fixtures
):

    now = current_ist()

    date_text = now.strftime(
        "%d %b %Y"
    ).upper()

    if not fixtures:

        return (
            "🏏 SRL FIXTURES\n"
            f"📅 {date_text}\n\n"
            "No fixtures found."
        )

    # --------------------------------------------------------
    # Group while preserving page order.
    # --------------------------------------------------------

    grouped = {}

    league_order = []

    for fixture in fixtures:

        league = fixture[
            "league"
        ]

        if league not in grouped:

            grouped[league] = []

            league_order.append(
                league
            )

        grouped[
            league
        ].append(
            fixture
        )

    # --------------------------------------------------------
    # Build message.
    # --------------------------------------------------------

    parts = []

    parts.append(
        "🏏 SRL FIXTURES"
    )

    parts.append(
        f"📅 {date_text}"
    )

    for league in league_order:

        parts.append("")

        parts.append(
            f"🏆 {league.upper()}"
        )

        for fixture in grouped[
            league
        ]:

            parts.append("")

            parts.append(
                f"⏰ {fixture['time']}"
            )

            parts.append(
                fixture["team1"]
            )

            parts.append(
                "vs"
            )

            parts.append(
                fixture["team2"]
            )

    return "\n".join(
        parts
    )


# ============================================================
# SEND DAILY FIXTURES
# ============================================================

def send_daily_fixtures(
    driver
):

    now = current_ist()

    date_key = now.strftime(
        "%Y-%m-%d"
    )

    # --------------------------------------------------------
    # Already sent today.
    # --------------------------------------------------------

    if date_key in sent_fixture_dates:

        return False

    # --------------------------------------------------------
    # Only run around 00:10.
    #
    # Window:
    #
    # 00:10 -> 00:19
    # --------------------------------------------------------

    if now.hour != DAILY_FIXTURE_HOUR:

        return False

    if not (
        DAILY_FIXTURE_MINUTE
        <= now.minute
        <
        DAILY_FIXTURE_MINUTE
        + DAILY_FIXTURE_WINDOW_MINUTES
    ):

        return False

    log.info(
        "🗓 DAILY FIXTURE TIME REACHED | %s",
        date_key
    )

    # --------------------------------------------------------
    # Read fresh page.
    # --------------------------------------------------------

    page_text = get_page_text(
        driver
    )

    if not page_text:

        log.warning(
            "Could not read page for daily fixtures."
        )

        return False

    # --------------------------------------------------------
    # Parse.
    # --------------------------------------------------------

    fixtures = parse_daily_fixtures(
        page_text
    )

    log.info(
        "Daily fixture parser found %s fixtures.",
        len(fixtures)
    )

    # --------------------------------------------------------
    # If page hasn't loaded fixtures yet,
    # don't mark as sent.
    # It will retry on next scan.
    # --------------------------------------------------------

    if not fixtures:

        log.warning(
            "No today's fixtures found. "
            "Daily fixture message will retry."
        )

        return False

    # --------------------------------------------------------
    # Build.
    # --------------------------------------------------------

    message = build_daily_fixture_message(
        fixtures
    )

    log.info(
        "Sending daily fixture board..."
    )

    # --------------------------------------------------------
    # Send.
    # --------------------------------------------------------

    success = send_telegram(
        message
    )

    if not success:

        log.error(
            "Daily fixture Telegram failed."
        )

        return False

    # --------------------------------------------------------
    # Mark after successful send.
    # --------------------------------------------------------

    sent_fixture_dates.add(
        date_key
    )

    save_fixture_state()

    log.info(
        "✅ DAILY FIXTURE BOARD SENT | "
        "%s fixtures | %s",
        len(fixtures),
        date_key
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
            # DAILY FIXTURE BOARD
            # =================================================

            send_daily_fixtures(
                driver
            )

            # =================================================
            # PRIMARY DOM TOSS DETECTOR
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
            # PERIODIC REFRESH
            # =================================================

            now_mono = time.monotonic()

            if (
                now_mono
                - last_refresh
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

    load_fixture_state()

    driver = None

    try:

        # ====================================================
        # CHROME
        # ====================================================

        driver = create_driver()

        # ====================================================
        # OPEN PAGE
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
