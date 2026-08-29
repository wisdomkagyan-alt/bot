# ============================================================
# SRL TOSS SELENIUM MONITOR 2026
#
# SRL CRICKET ONLY
#
# SOURCE:
# https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket
#
# Selenium + Chromium
# Rendered DOM detection
# Telegram alerts
#
# FEATURES
#
# 1. LIVE SRL TOSS DETECTION
# 2. DUPLICATE TOSS PROTECTION
# 3. IST TIME
# 4. DAILY SRL FIXTURE BOARD
#    - Sent once every new day
#    - 00:01 IST or immediately after restart if missed
#    - All today's fixtures
#    - Grouped by league
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

# How often DOM is checked.
CHECK_INTERVAL = 2

# Refresh page periodically.
PAGE_REFRESH_INTERVAL = 30

PAGE_LOAD_TIMEOUT = 30

REQUEST_TIMEOUT = 15


# ============================================================
# DAILY FIXTURE BOARD
# ============================================================

# First daily board time = 00:01 IST.
DAILY_FIXTURE_HOUR = 0
DAILY_FIXTURE_MINUTE = 1

FIXTURE_STATE_FILE = Path(
    "daily_fixture_state.json"
)

last_fixture_board_date = ""


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
        )
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

def load_fixture_state():

    global last_fixture_board_date

    data = load_json(
        FIXTURE_STATE_FILE,
        {}
    )

    if isinstance(
        data,
        dict
    ):

        last_fixture_board_date = str(
            data.get(
                "last_sent_date",
                ""
            )
        )

        log.info(
            "Last fixture board date: %s",
            last_fixture_board_date or "NONE"
        )

    else:

        last_fixture_board_date = ""


# ============================================================
# SAVE DAILY FIXTURE STATE
# ============================================================

def save_fixture_state():

    save_json(
        FIXTURE_STATE_FILE,
        {
            "last_sent_date":
                last_fixture_board_date
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
        "📋 Daily fixture board: ACTIVE\n"
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
# GET PAGE TEXT
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
# SRL TEAM VALIDATION
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
# LEAGUE HEADER DETECTION
# ============================================================

def is_league_header(
    name
):

    value = clean_text(
        name
    ).lower()

    if not value:

        return False

    # Known SRL competition header patterns.

    if value in {
        "sa20 srl",
        "super smash srl"
    }:

        return True

    if value.endswith(
        " league srl"
    ):

        return True

    if value.endswith(
        " international srl"
    ):

        return True

    return False


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

    if not value:

        return []

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

        if is_league_header(
            team
        ):

            continue

        duplicate = False

        for existing in found:

            if existing.lower() == team.lower():

                duplicate = True
                break

        if not duplicate:

            found.append(
                team
            )

    return found


# ============================================================
# EXTRACT FIXTURE FROM TOSS TEXT
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

        return (
            teams[-2],
            teams[-1]
        )

    teams = extract_srl_teams(
        value
    )

    if len(teams) >= 2:

        return (
            teams[-2],
            teams[-1]
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
#
# We inspect the toss element AND ancestors.
# This helps catch tosses such as:
#
# Joburg Super Kings SRL won the toss and elected to bat
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

                if (
                    parent_text
                    and len(parent_text) <= 1200
                ):

                    candidates.append(
                        parent_text
                    )

            except Exception:

                break

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
# FALLBACK PAGE TEXT TOSS DETECTOR
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
# FORMAT TOSS DECISION
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
# CURRENT SIMPLE FORMAT
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
# Fixture included whenever available.
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

    if identifier in seen_tosses:

        return False

    log.info(
        "🔥 NEW SRL TOSS DETECTED | "
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

    message = build_toss_message(
        toss
    )

    success = send_telegram(
        message
    )

    if not success:

        log.error(
            "Telegram failed. "
            "Toss will be retried."
        )

        return False

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
# DAILY FIXTURE HELPERS
# ============================================================

def is_fixture_time(
    value
):

    return bool(
        re.search(
            r"\b\d{1,2}\s+AGO\s*\|\s*\d{1,2}:\d{2}\b",
            value,
            re.IGNORECASE
        )
    )


# ============================================================
# EXTRACT DAILY FIXTURES FROM PAGE TEXT
#
# The SRL page can render rows in slightly different orders.
#
# Examples:
#
# Team A
# Team B
# 29 AGO | 14:30
#
# OR:
#
# Team A
# 29 AGO | 14:30
# Team B
#
# This parser supports both.
# ============================================================

def extract_daily_fixtures_from_text(
    page_text
):

    lines = [
        clean_text(x)
        for x in str(
            page_text
        ).splitlines()
        if clean_text(x)
    ]

    fixtures = []

    current_league = "SRL"

    for index, line in enumerate(
        lines
    ):

        # ----------------------------------------------------
        # Detect league headers.
        # ----------------------------------------------------

        if is_league_header(
            line
        ):

            current_league = line
            continue

        # ----------------------------------------------------
        # We only care about scheduled fixture time rows.
        # ----------------------------------------------------

        time_match = re.search(
            r"\b(\d{1,2})\s+AGO\s*\|\s*(\d{1,2}:\d{2})\b",
            line,
            re.IGNORECASE
        )

        if not time_match:

            continue

        match_day = int(
            time_match.group(1)
        )

        match_time = time_match.group(2)

        # ----------------------------------------------------
        # Search nearby lines.
        # ----------------------------------------------------

        before = []
        after = []

        for distance in range(
            1,
            5
        ):

            pos = index - distance

            if pos >= 0:

                before.append(
                    lines[pos]
                )

        for distance in range(
            1,
            5
        ):

            pos = index + distance

            if pos < len(lines):

                after.append(
                    lines[pos]
                )

        # ----------------------------------------------------
        # Candidate team lines.
        # ----------------------------------------------------

        before_teams = []

        for candidate in before:

            if is_league_header(
                candidate
            ):

                continue

            found = extract_srl_teams(
                candidate
            )

            for team in found:

                if team.lower() not in {
                    x.lower()
                    for x in before_teams
                }:

                    before_teams.append(
                        team
                    )

        after_teams = []

        for candidate in after:

            if is_league_header(
                candidate
            ):

                continue

            found = extract_srl_teams(
                candidate
            )

            for team in found:

                if team.lower() not in {
                    x.lower()
                    for x in after_teams
                }:

                    after_teams.append(
                        team
                    )

        team1 = ""
        team2 = ""

        # ----------------------------------------------------
        # Case 1:
        #
        # Team 1
        # Team 2
        # TIME
        #
        # This is common in rendered page text.
        # ----------------------------------------------------

        if len(before_teams) >= 2:

            team1 = before_teams[1]
            team2 = before_teams[0]

            # In page order the nearest previous team is
            # usually Team 2, and the next is Team 1.

        # ----------------------------------------------------
        # Case 2:
        #
        # Team 1
        # TIME
        # Team 2
        # ----------------------------------------------------

        elif (
            len(before_teams) >= 1
            and len(after_teams) >= 1
        ):

            team1 = before_teams[0]
            team2 = after_teams[0]

        # ----------------------------------------------------
        # Case 3:
        #
        # TIME
        # Team 1
        # Team 2
        # ----------------------------------------------------

        elif len(after_teams) >= 2:

            team1 = after_teams[0]
            team2 = after_teams[1]

        if not team1 or not team2:

            continue

        if team1.lower() == team2.lower():

            continue

        # ----------------------------------------------------
        # Check surrounding row for completed/live text.
        # ----------------------------------------------------

        surrounding = " ".join(
            before[:2]
            + [line]
            + after[:2]
        ).lower()

        if "terminado" in surrounding:

            continue

        if "won by" in surrounding:

            continue

        # ----------------------------------------------------
        # Avoid accidentally using toss text as fixture.
        # ----------------------------------------------------

        if "won the toss" in surrounding:

            continue

        fixtures.append(
            {
                "league": current_league,
                "team1": team1,
                "team2": team2,
                "time": match_time,
                "day": match_day
            }
        )

    return deduplicate_fixtures(
        fixtures
    )


# ============================================================
# DEDUPLICATE FIXTURES
# ============================================================

def deduplicate_fixtures(
    fixtures
):

    unique = {}

    for fixture in fixtures:

        league = clean_text(
            fixture.get(
                "league",
                "SRL"
            )
        )

        team1 = clean_team_name(
            fixture.get(
                "team1",
                ""
            )
        )

        team2 = clean_team_name(
            fixture.get(
                "team2",
                ""
            )
        )

        match_time = clean_text(
            fixture.get(
                "time",
                ""
            )
        )

        match_day = fixture.get(
            "day"
        )

        if not team1 or not team2:

            continue

        if team1.lower() == team2.lower():

            continue

        key = (
            league.lower(),
            team1.lower(),
            team2.lower(),
            str(match_day),
            match_time
        )

        unique[key] = {
            "league": league,
            "team1": team1,
            "team2": team2,
            "time": match_time,
            "day": match_day
        }

    return list(
        unique.values()
    )


# ============================================================
# BUILD STYLE 5 DAILY BOARD
#
# Example:
#
# 🏏 SRL FIXTURES — 30 AUG
#
# 🇵🇰 PSL SRL
# 03:30  Karachi Kings SRL vs Islamabad United SRL
# ...
#
# ============================================================

def build_fixture_board(
    fixtures,
    now
):

    if not fixtures:

        return None

    # --------------------------------------------------------
    # Group leagues while preserving page order.
    # --------------------------------------------------------

    groups = {}

    league_order = []

    for fixture in fixtures:

        league = clean_text(
            fixture.get(
                "league",
                "SRL"
            )
        )

        if not league:

            league = "SRL"

        if league not in groups:

            groups[league] = []
            league_order.append(
                league
            )

        groups[league].append(
            fixture
        )

    # --------------------------------------------------------
    # Header
    # --------------------------------------------------------

    lines = []

    lines.append(
        "🏏 SRL FIXTURES"
    )

    lines.append(
        f"📅 {now.strftime('%d %b').upper()}"
    )

    # --------------------------------------------------------
    # League emoji.
    # --------------------------------------------------------

    def league_prefix(
        league
    ):

        value = league.lower()

        if "pakistan" in value:

            return "🇵🇰"

        if "sa20" in value:

            return "🇿🇦"

        if "international" in value:

            return "🌍"

        if "super smash" in value:

            return "🇳🇿"

        if "indian premier" in value:

            return "🇮🇳"

        return "🏏"

    # --------------------------------------------------------
    # League short names for cleaner Telegram.
    # --------------------------------------------------------

    def league_display(
        league
    ):

        value = league.strip()

        lower = value.lower()

        if "pakistan super league" in lower:

            return "PSL SRL"

        if "indian premier league" in lower:

            return "IPL SRL"

        if "t20 international" in lower:

            return "T20I SRL"

        if "super smash" in lower:

            return "SUPER SMASH SRL"

        if "sa20" in lower:

            return "SA20 SRL"

        return value

    # --------------------------------------------------------
    # Build each league.
    # --------------------------------------------------------

    for league in league_order:

        lines.append("")

        lines.append(
            f"{league_prefix(league)} "
            f"{league_display(league)}"
        )

        # ----------------------------------------------------
        # Keep fixtures in Sportcentre order.
        # ----------------------------------------------------

        for fixture in groups[league]:

            lines.append(
                f"{fixture['time']}  "
                f"{fixture['team1']} vs "
                f"{fixture['team2']}"
            )

    return "\n".join(
        lines
    )


# ============================================================
# CHECK DAILY FIXTURE BOARD
#
# Runs from the normal 2-second monitor loop.
#
# At 00:01 IST:
#
# refresh
#   ↓
# read rendered DOM
#   ↓
# extract today's fixtures
#   ↓
# send one board
#   ↓
# save today's date
#
# ============================================================

def check_daily_fixture_board(
    driver
):

    global last_fixture_board_date

    now = current_ist()

    today_string = now.strftime(
        "%Y-%m-%d"
    )

    # --------------------------------------------------------
    # Before 00:01 = do nothing.
    # --------------------------------------------------------

    if now.hour < DAILY_FIXTURE_HOUR:

        return

    if (
        now.hour == DAILY_FIXTURE_HOUR
        and now.minute < DAILY_FIXTURE_MINUTE
    ):

        return

    # --------------------------------------------------------
    # Already sent today.
    # --------------------------------------------------------

    if (
        last_fixture_board_date
        == today_string
    ):

        return

    log.info(
        "📋 Preparing new daily SRL fixture board..."
    )

    # --------------------------------------------------------
    # Refresh page.
    # --------------------------------------------------------

    try:

        log.info(
            "Refreshing page for daily fixture board..."
        )

        driver.refresh()

        time.sleep(5)

    except Exception as exc:

        log.warning(
            "Daily fixture refresh warning: %s",
            exc
        )

    # --------------------------------------------------------
    # Read rendered page.
    # --------------------------------------------------------

    page_text = get_page_text(
        driver
    )

    if not page_text:

        log.warning(
            "Daily fixture board: empty page."
        )

        return

    # --------------------------------------------------------
    # Extract all fixtures.
    # --------------------------------------------------------

    fixtures = extract_daily_fixtures_from_text(
        page_text
    )

    if not fixtures:

        log.warning(
            "Daily fixture board: "
            "no fixtures detected. Will retry."
        )

        return

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Only today's fixtures.
    # --------------------------------------------------------

    todays_fixtures = [
        fixture
        for fixture in fixtures
        if fixture.get("day") == now.day
    ]

    if not todays_fixtures:

        log.warning(
            "Daily fixture board: "
            "no fixtures matched today's date %s. "
            "Will retry.",
            now.day
        )

        return

    # --------------------------------------------------------
    # Build board.
    # --------------------------------------------------------

    message = build_fixture_board(
        todays_fixtures,
        now
    )

    if not message:

        log.warning(
            "Daily fixture board message empty."
        )

        return

    # --------------------------------------------------------
    # LOG.
    # --------------------------------------------------------

    log.info(
        "📋 DAILY FIXTURE BOARD | "
        "%s fixtures | %s",
        len(todays_fixtures),
        today_string
    )

    log.info(
        "DAILY FIXTURE BOARD:\n%s",
        message
    )

    # --------------------------------------------------------
    # SEND EXACTLY ONCE.
    # --------------------------------------------------------

    success = send_telegram(
        message
    )

    if not success:

        log.error(
            "❌ Daily fixture board Telegram failed. "
            "Will retry."
        )

        return

    # --------------------------------------------------------
    # Mark date only AFTER Telegram succeeds.
    # --------------------------------------------------------

    last_fixture_board_date = (
        today_string
    )

    save_fixture_state()

    log.info(
        "✅ DAILY SRL FIXTURE BOARD SENT | "
        "%s fixtures | %s",
        len(todays_fixtures),
        today_string
    )


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
            # FALLBACK PAGE TEXT TOSS DETECTOR
            # =================================================

            text_tosses = find_text_tosses(
                page_text
            )

            for toss in text_tosses:

                process_toss(
                    toss
                )

            # =================================================
            # DAILY FIXTURE BOARD
            # =================================================

            check_daily_fixture_board(
                driver
            )

            # =================================================
            # NORMAL PAGE REFRESH
            # =================================================

            now_monotonic = time.monotonic()

            if (
                now_monotonic
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
    # LOAD STATE
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
