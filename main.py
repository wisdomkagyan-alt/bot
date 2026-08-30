# ============================================================
# SRL TOSS + DAILY FIXTURE SELENIUM MONITOR 2026
#
# SRL CRICKET ONLY
#
# SOURCE:
# https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket
#
# FEATURES
# ------------------------------------------------------------
# 1. Selenium + Chromium
# 2. Rendered DOM detection
# 3. SRL toss detection
# 4. Fixture detection
# 5. Telegram toss alerts
# 6. Strong duplicate protection
# 7. Daily fixture board at 00:10 IST
# 8. Fixtures arranged by time
# 9. Fixtures grouped by league
# 10. Railway compatible

===============================================

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

# Daily fixture message time.
DAILY_FIXTURE_HOUR = 0
DAILY_FIXTURE_MINUTE = 10


# ============================================================
# TELEGRAM
#
# IMPORTANT:
# SET THESE IN RAILWAY VARIABLES
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

DAILY_FIXTURE_STATE_FILE = Path(
    "daily_fixture_state.json"
)

HEARTBEAT_FILE = Path(
    "srl_toss_heartbeat.txt"
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
    )
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
        )
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
            "Last fixture board sent: %s",
            last_fixture_date_sent or "NEVER"
        )


# ============================================================
# SAVE DAILY FIXTURE STATE
# ============================================================

def save_daily_fixture_state(
    date_string
):

    global last_fixture_date_sent

    last_fixture_date_sent = date_string

    save_json(
        DAILY_FIXTURE_STATE_FILE,
        {
            "last_date": date_string
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
        "🟢 SRL TOSS MONITOR ONLINE\n\n"
        "🏏 SRL CRICKET ONLY\n"
        "📡 Sportradar SRL Sportcentre\n\n"
        "🌐 Selenium + Chrome WebDriver\n"
        "🔄 DOM check: 2s\n"
        "🔃 Page refresh: 30s\n"
        "📅 Daily fixtures: 00:10 IST\n\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🎯 Toss detector: ACTIVE\n"
        "📋 Fixture board: ACTIVE\n"
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
# GET RAW PAGE TEXT
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

        if team.lower() not in {
            x.lower()
            for x in found
        }:

            found.append(
                team
            )

    return found


# ============================================================
# EXTRACT FIXTURE
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

    # --------------------------------------------------------
    # Remove duplicates while preserving order.
    # --------------------------------------------------------

    unique = []

    for team in teams:

        if team.lower() not in {
            x.lower()
            for x in unique
        }:

            unique.append(
                team
            )

    # --------------------------------------------------------
    # If two teams exist before toss,
    # the final two are the fixture.
    # --------------------------------------------------------

    if len(unique) >= 2:

        return (
            unique[-2],
            unique[-1]
        )

    # --------------------------------------------------------
    # Search entire candidate.
    # --------------------------------------------------------

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
# DOM TOSS DETECTOR
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
        # Parent elements.
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

            # Prefer candidate containing fixture.
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
        # IMPORTANT:
        #
        # If fixture exists, use fixture in scan key.
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
# CURRENT IST
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
# EXACT USER FORMAT
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
    # NEVER send "SRL Match" if fixture is known.
    # --------------------------------------------------------

    if team1 and team2:

        fixture = (
            f"{team1} vs {team2}"
        )

    else:

        fixture = "SRL Fixture"

    return (
        "🏏 SRL TOSS ALERT\n\n"

        f"🏆 {toss['winner']} WON THE TOSS\n\n"

        f"⚔️ {fixture}\n\n"

        f"🎯 {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}"
    )


# ============================================================
# TOSS ID
#
# FIXED DUPLICATE LOGIC
#
# Fixture + winner + decision + DATE
#
# This prevents the same toss being sent repeatedly
# through different DOM elements.
# ============================================================

def make_toss_id(
    toss
):

    now = current_ist()

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

    date_string = now.strftime(
        "%Y-%m-%d"
    )

    # --------------------------------------------------------
    # If fixture is available:
    # fixture + winner + decision + date
    # --------------------------------------------------------

    if team1 and team2:

        raw = (
            f"{date_string}|"
            f"{team1}|"
            f"{team2}|"
            f"{winner}|"
            f"{decision}"
        )

    else:

        # ----------------------------------------------------
        # IMPORTANT:
        #
        # Do NOT let incomplete page-text detection send
        # another copy if the proper fixture version already
        # exists.
        #
        # This fallback remains unique per date.
        # ----------------------------------------------------

        raw = (
            f"{date_string}|"
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

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Don't send an alert without a fixture.
    #
    # This prevents:
    #
    # SRL Match
    #
    # from being sent by the page-text fallback.
    # --------------------------------------------------------

    if not team1 or not team2:

        log.debug(
            "Toss detected but fixture not yet available | "
            "%s",
            winner
        )

        return False

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
        team1,
        team2
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
    # SAVE ONLY AFTER SUCCESS
    # --------------------------------------------------------

    seen_tosses.add(
        identifier
    )

    save_state()

    log.info(
        "✅ SRL TOSS ALERT SENT ONCE | "
        "%s | %s vs %s",
        winner,
        team1,
        team2
    )

    return True


# ============================================================
# DAILY FIXTURE HELPERS
# ============================================================

LEAGUE_NAMES = {
    "Pakistan Super League SRL",
    "SA20 SRL",
    "T20 International SRL",
    "Super Smash SRL",
    "Indian Premier League SRL"
}


# ============================================================
# FIXTURE TIME LINE CHECK
# ============================================================

def is_fixture_time_line(
    line
):

    line = clean_text(
        line
    )

    return bool(
        re.search(
            r"\b\d{1,2}\s+"
            r"[A-ZÀ-Ý]{3}"
            r"\s*\|\s*"
            r"\d{1,2}:\d{2}\b",
            line,
            re.IGNORECASE
        )
    )


# ============================================================
# PARSE PAGE FIXTURES
#
# Expected rendered structure:
#
# League
# Team A
# 30 AGO | 15:30
# Team B
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

    for index, line in enumerate(
        lines
    ):

        # ----------------------------------------------------
        # Detect league header.
        # ----------------------------------------------------

        if line in LEAGUE_NAMES:

            current_league = line

            continue

        # ----------------------------------------------------
        # Fixture time line.
        # ----------------------------------------------------

        if not is_fixture_time_line(
            line
        ):

            continue

        if index <= 0:

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

        # ----------------------------------------------------
        # Extract time.
        # ----------------------------------------------------

        match = re.search(
            r"\b\d{1,2}\s+"
            r"[A-ZÀ-Ý]{3}"
            r"\s*\|\s*"
            r"(\d{1,2}:\d{2})\b",
            line,
            re.IGNORECASE
        )

        if not match:

            continue

        fixture_time = match.group(
            1
        )

        hour, minute = map(
            int,
            fixture_time.split(":")
        )

        fixtures.append(
            {
                "league": (
                    current_league
                    or "SRL"
                ),
                "team1": team1,
                "team2": team2,
                "time": fixture_time,
                "sort_minutes": (
                    hour * 60 + minute
                )
            }
        )

    return fixtures


# ============================================================
# DEDUPLICATE FIXTURES
# ============================================================

def deduplicate_fixtures(
    fixtures
):

    unique = {}

    for fixture in fixtures:

        key = (
            fixture["league"].lower(),
            fixture["team1"].lower(),
            fixture["team2"].lower(),
            fixture["time"]
        )

        unique[key] = fixture

    return list(
        unique.values()
    )


# ============================================================
# FORMAT LEAGUE TITLE
# ============================================================

def format_league_title(
    league
):

    return (
        league
        .upper()
    )


# ============================================================
# BUILD DAILY FIXTURE MESSAGE
#
# FIXTURES ARE SORTED BY TIME
# INSIDE EACH LEAGUE.
# ============================================================

def build_daily_fixture_message(
    page_text
):

    now = current_ist()

    fixtures = parse_daily_fixtures(
        page_text
    )

    fixtures = deduplicate_fixtures(
        fixtures
    )

    if not fixtures:

        log.warning(
            "No SRL fixtures found for daily board."
        )

        return None

    # --------------------------------------------------------
    # Group by league.
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
    # Sort each league chronologically.
    # --------------------------------------------------------

    for league in grouped:

        grouped[league].sort(
            key=lambda x: x[
                "sort_minutes"
            ]
        )

    # --------------------------------------------------------
    # Sort leagues by earliest fixture.
    # --------------------------------------------------------

    ordered_leagues = sorted(
        grouped.keys(),
        key=lambda league: (
            grouped[league][0][
                "sort_minutes"
            ]
        )
    )

    # --------------------------------------------------------
    # Build message.
    # --------------------------------------------------------

    message = (
        "🏏 SRL FIXTURES\n"
        f"📅 {now.strftime('%d %b %Y').upper()}\n"
    )

    for league in ordered_leagues:

        message += (
            "\n\n"
            f"🏆 {format_league_title(league)}\n"
        )

        for fixture in grouped[
            league
        ]:

            message += (
                "\n"
                f"⏰ {fixture['time']}\n"
                f"{fixture['team1']}\n"
                "vs\n"
                f"{fixture['team2']}\n"
            )

    return message.rstrip()


# ============================================================
# DAILY FIXTURE SEND
#
# SENDS ONCE PER IST DATE.
#
# At 00:10, the page should already have the new date.
# ============================================================

def maybe_send_daily_fixtures(
    page_text
):

    global last_fixture_date_sent

    now = current_ist()

    current_date = now.strftime(
        "%Y-%m-%d"
    )

    current_minutes = (
        now.hour * 60
        + now.minute
    )

    target_minutes = (
        DAILY_FIXTURE_HOUR * 60
        + DAILY_FIXTURE_MINUTE
    )

    # --------------------------------------------------------
    # Only after 00:10.
    # --------------------------------------------------------

    if current_minutes < target_minutes:

        return False

    # --------------------------------------------------------
    # Already sent today.
    # --------------------------------------------------------

    if (
        last_fixture_date_sent
        == current_date
    ):

        return False

    # --------------------------------------------------------
    # Build board.
    # --------------------------------------------------------

    message = build_daily_fixture_message(
        page_text
    )

    if not message:

        return False

    log.info(
        "📋 Sending daily SRL fixture board | %s",
        current_date
    )

    success = send_telegram(
        message
    )

    if not success:

        log.error(
            "Daily fixture board failed. "
            "It will retry."
        )

        return False

    save_daily_fixture_state(
        current_date
    )

    log.info(
        "✅ Daily SRL fixture board sent | %s",
        current_date
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

            maybe_send_daily_fixtures(
                page_text
            )

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
            # PAGE TEXT FALLBACK
            #
            # IMPORTANT:
            #
            # process_toss() refuses incomplete fixtures.
            # Therefore this fallback cannot send:
            #
            # SRL Match
            #
            # =================================================

            text_tosses = find_text_tosses(
                page_text
            )

            for toss in text_tosses:

                # ------------------------------------------------
                # Try to recover fixture from the full page text.
                # ------------------------------------------------

                recovered = extract_fixture(
                    page_text,
                    toss["winner"]
                )

                if (
                    recovered[0]
                    and recovered[1]
                ):

                    toss["team1"] = recovered[0]
                    toss["team2"] = recovered[1]

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
    # STATE
    # ========================================================

    load_state()

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
