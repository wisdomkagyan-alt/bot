# ============================================================
# SRL TOSS + DAILY FIXTURE SELENIUM MONITOR 2026
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
# FEATURES:
#
# 1. LIVE SRL TOSS MONITOR
# 2. DUPLICATE TOSS PROTECTION
# 3. DAILY FIXTURE SCHEDULE
# 4. DAILY FIXTURE SEND AFTER 00:10 IST
# 5. FIXTURES SORTED BY TIME WITHIN EACH LEAGUE
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

# Daily fixture board is eligible after:
# 00:10 IST
DAILY_FIXTURE_HOUR = 0
DAILY_FIXTURE_MINUTE = 10


# ============================================================
# TELEGRAM
#
# IMPORTANT:
# Set these in Railway Variables.
#
# TELEGRAM_BOT_TOKEN
# TELEGRAM_CHAT_ID
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

# ------------------------------------------------------------
# DAILY FIXTURE STATE
# ------------------------------------------------------------

DAILY_FIXTURE_STATE_FILE = Path(
    "daily_fixture_state.json"
)

seen_tosses = set()

last_fixture_date_sent = ""


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

def clean_text(
    value
):

    if value is None:

        return ""

    value = str(
        value
    )

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
            "No previous SRL toss state found."
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

def load_daily_fixture_state():

    global last_fixture_date_sent

    data = load_json(
        DAILY_FIXTURE_STATE_FILE,
        {}
    )

    if isinstance(
        data,
        dict
    ):

        last_fixture_date_sent = str(
            data.get(
                "last_date",
                ""
            )
        )

        log.info(
            "Last daily fixture date sent: %s",
            last_fixture_date_sent or "NONE"
        )

    else:

        last_fixture_date_sent = ""

        log.info(
            "No previous daily fixture state found."
        )


# ============================================================
# SAVE DAILY FIXTURE STATE
# ============================================================

def save_daily_fixture_state(
    date_string
):

    global last_fixture_date_sent

    last_fixture_date_sent = str(
        date_string
    )

    save_json(
        DAILY_FIXTURE_STATE_FILE,
        {
            "last_date": last_fixture_date_sent
        }
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
        "📋 Daily fixtures: ACTIVE\n"
        "🕛 Fixture send: 00:10 IST\n"
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

        if team not in found:

            found.append(
                team
            )

    return found


# ============================================================
# FIXTURE EXTRACTION
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

    teams = extract_srl_teams(
        value
    )

    unique = []

    for team in teams:

        if team.lower() not in {
            x.lower()
            for x in unique
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
        # Walk ancestors
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

                    if len(parent_text) <= 1200:

                        candidates.append(
                            parent_text
                        )

            except Exception:

                break

        # ----------------------------------------------------
        # Smallest candidate first
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
# DEDUPLICATE TOSS RESULTS
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
# EXTRACT PAGE DISPLAY DATE
#
# Example:
#
# 31 Ago, 2026
#
# Returns:
#
# 31 AUG 2026
# ============================================================

def extract_page_date(
    page_text
):

    normalized = clean_text(
        page_text
    )

    if not normalized:

        return None

    # --------------------------------------------------------
    # Portuguese month abbreviations used by page
    # --------------------------------------------------------

    month_map = {
        "jan": "JAN",
        "fev": "FEB",
        "mar": "MAR",
        "abr": "APR",
        "mai": "MAY",
        "jun": "JUN",
        "jul": "JUL",
        "ago": "AUG",
        "set": "SEP",
        "out": "OCT",
        "nov": "NOV",
        "dez": "DEC"
    }

    pattern = re.compile(
        r"\b"
        r"(\d{1,2})"
        r"\s+"
        r"([A-Za-zÀ-ÿ]{3})"
        r"(?:,)?"
        r"\s+"
        r"(\d{4})"
        r"\b",
        re.IGNORECASE
    )

    matches = list(
        pattern.finditer(
            normalized
        )
    )

    if not matches:

        return None

    # The first full date is the page date.
    match = matches[0]

    day = int(
        match.group(1)
    )

    month_raw = (
        match.group(2)
        .lower()
    )

    year = int(
        match.group(3)
    )

    month = month_map.get(
        month_raw,
        month_raw.upper()
    )

    if month not in {
        "JAN",
        "FEB",
        "MAR",
        "APR",
        "MAY",
        "JUN",
        "JUL",
        "AUG",
        "SEP",
        "OCT",
        "NOV",
        "DEC"
    }:

        return None

    return {
        "display": (
            f"{day:02d} "
            f"{month} "
            f"{year}"
        ),
        "state": (
            f"{year:04d}-"
            f"{datetime.strptime(month, '%b').month:02d}-"
            f"{day:02d}"
        )
    }


# ============================================================
# DAILY FIXTURE PARSER
#
# Expected rendered structure:
#
# League
# Team 1
# 31 AGO | 15:30
# Team 2
#
# ============================================================

def parse_daily_fixtures(
    page_text
):

    lines = [
        clean_text(x)
        for x in page_text.splitlines()
        if clean_text(x)
    ]

    fixtures = []

    current_league = ""

    league_patterns = [
        "Pakistan Super League SRL",
        "SA20 SRL",
        "T20 International SRL",
        "Super Smash SRL",
        "Indian Premier League SRL"
    ]

    for index, line in enumerate(lines):

        # ----------------------------------------------------
        # League detection
        # ----------------------------------------------------

        for league in league_patterns:

            if line.lower() == league.lower():

                current_league = league

                break

        # ----------------------------------------------------
        # Fixture time
        #
        # 31 AGO | 15:30
        # 31 AUG | 15:30
        # ----------------------------------------------------

        time_match = re.search(
            r"\b"
            r"\d{1,2}"
            r"\s+"
            r"[A-Za-zÀ-ÿ]{3}"
            r"\s*\|\s*"
            r"(\d{1,2}):(\d{2})"
            r"\b",
            line,
            re.IGNORECASE
        )

        if not time_match:

            continue

        if not current_league:

            continue

        # ----------------------------------------------------
        # Expected structure:
        #
        # previous line = team 1
        # current line  = date/time
        # next line     = team 2
        # ----------------------------------------------------

        if index == 0:

            continue

        if index + 1 >= len(lines):

            continue

        team1 = clean_team_name(
            lines[index - 1]
        )

        team2 = clean_team_name(
            lines[index + 1]
        )

        if not is_srl_team(
            team1
        ):

            continue

        if not is_srl_team(
            team2
        ):

            continue

        hour = int(
            time_match.group(1)
        )

        minute = int(
            time_match.group(2)
        )

        # ----------------------------------------------------
        # Basic time validation
        # ----------------------------------------------------

        if hour < 0 or hour > 23:

            continue

        if minute < 0 or minute > 59:

            continue

        fixtures.append(
            {
                "league": current_league,
                "team1": team1,
                "team2": team2,
                "time": (
                    f"{hour:02d}:"
                    f"{minute:02d}"
                ),
                "sort_time": (
                    hour * 60
                    + minute
                )
            }
        )

    return fixtures


# ============================================================
# BUILD DAILY FIXTURE MESSAGE
# ============================================================

def build_daily_fixture_message(
    page_text
):

    page_date = extract_page_date(
        page_text
    )

    if not page_date:

        log.warning(
            "Could not determine SRL page date."
        )

        return None, None

    fixtures = parse_daily_fixtures(
        page_text
    )

    if not fixtures:

        log.warning(
            "No SRL fixtures found for daily schedule."
        )

        return None, None

    # --------------------------------------------------------
    # Remove duplicate fixtures
    # --------------------------------------------------------

    unique = {}

    for fixture in fixtures:

        key = (
            fixture["league"].lower(),
            fixture["team1"].lower(),
            fixture["team2"].lower(),
            fixture["time"]
        )

        unique[key] = fixture

    fixtures = list(
        unique.values()
    )

    # --------------------------------------------------------
    # Group by league
    # --------------------------------------------------------

    grouped = {}

    for fixture in fixtures:

        league = fixture[
            "league"
        ]

        grouped.setdefault(
            league,
            []
        ).append(
            fixture
        )

    # --------------------------------------------------------
    # Sort by time within each league
    # --------------------------------------------------------

    for league in grouped:

        grouped[league].sort(
            key=lambda x: x[
                "sort_time"
            ]
        )

    # --------------------------------------------------------
    # Fixed league order
    #
    # This keeps the familiar SRL order.
    # Fixtures themselves are time sorted.
    # --------------------------------------------------------

    league_order = [
        "Pakistan Super League SRL",
        "SA20 SRL",
        "T20 International SRL",
        "Super Smash SRL",
        "Indian Premier League SRL"
    ]

    ordered_grouped = {}

    for league in league_order:

        if league in grouped:

            ordered_grouped[
                league
            ] = grouped[league]

    # --------------------------------------------------------
    # Any unexpected SRL league is retained at the end.
    # --------------------------------------------------------

    for league in grouped:

        if league not in ordered_grouped:

            ordered_grouped[
                league
            ] = grouped[league]

    # --------------------------------------------------------
    # Build Telegram message
    # --------------------------------------------------------

    message = (
        "🏏 SRL FIXTURES\n"
        f"📅 {page_date['display']}\n"
    )

    for league in ordered_grouped:

        message += (
            "\n\n"
            f"🏆 {league.upper()}\n"
        )

        for fixture in ordered_grouped[
            league
        ]:

            message += (
                "\n"
                f"⏰ {fixture['time']}\n"
                f"{fixture['team1']}\n"
                "vs\n"
                f"{fixture['team2']}\n"
            )

    return (
        message.rstrip(),
        page_date["state"]
    )


# ============================================================
# DAILY FIXTURE SCHEDULER
#
# Runs continuously from the normal 2-second monitor loop.
#
# At/after 00:10 IST:
#
# - Read currently displayed page
# - Determine page date
# - Send once for that page date
#
# ============================================================

def maybe_send_daily_fixtures(
    page_text
):

    global last_fixture_date_sent

    now = current_ist()

    current_minutes = (
        now.hour * 60
        + now.minute
    )

    target_minutes = (
        DAILY_FIXTURE_HOUR * 60
        + DAILY_FIXTURE_MINUTE
    )

    # --------------------------------------------------------
    # Before 00:10
    # --------------------------------------------------------

    if current_minutes < target_minutes:

        return

    # --------------------------------------------------------
    # Build schedule from CURRENT rendered page
    # --------------------------------------------------------

    message, page_date = (
        build_daily_fixture_message(
            page_text
        )
    )

    if not message:

        return

    if not page_date:

        return

    # --------------------------------------------------------
    # Already sent this exact page date
    # --------------------------------------------------------

    if (
        last_fixture_date_sent
        == page_date
    ):

        return

    # --------------------------------------------------------
    # Safety:
    #
    # If the displayed page date is not today,
    # do not send the wrong day's fixtures.
    #
    # This prevents the bot from sending yesterday's
    # fixtures if Sportradar has not switched the page yet.
    # --------------------------------------------------------

    today_state = now.strftime(
        "%Y-%m-%d"
    )

    if page_date != today_state:

        log.info(
            "Daily fixture waiting | "
            "current IST date=%s | "
            "page date=%s",
            today_state,
            page_date
        )

        return

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

    log.info(
        "📋 Sending daily SRL fixture schedule | "
        "date=%s",
        page_date
    )

    success = send_telegram(
        message
    )

    if not success:

        log.error(
            "Daily fixture schedule failed. "
            "Will retry."
        )

        return

    # --------------------------------------------------------
    # Mark only AFTER Telegram succeeds
    # --------------------------------------------------------

    save_daily_fixture_state(
        page_date
    )

    log.info(
        "✅ Daily SRL fixture schedule sent once | "
        "%s",
        page_date
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

    return "Not reported"


# ============================================================
# TOSS MESSAGE
#
# EXACT CURRENT FORMAT
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
    # Fixture
    # --------------------------------------------------------

    if team1 and team2:

        fixture = (
            f"{team1} vs {team2}"
        )

    else:

        fixture = "SRL Match"

    return (
        "🏏 SRL TOSS ALERT\n\n"

        f"🏆 {toss['winner']} WON THE TOSS\n\n"

        f"⚔️ {fixture}\n\n"

        f"🎯 {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}"
    )


# ============================================================
# TOSS ID
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
            toss.get(
                "decision",
                ""
            ),
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
    # MARK AFTER SUCCESS
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
            # DAILY FIXTURE SCHEDULE
            #
            # IMPORTANT:
            # This runs BEFORE toss detectors but does not
            # modify toss state or toss processing.
            # =================================================

            maybe_send_daily_fixtures(
                page_text
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
    # TOSS STATE
    # ========================================================

    load_state()

    # ========================================================
    # DAILY FIXTURE STATE
    # ========================================================

    load_daily_fixture_state()

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
