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
# FEATURES
# ------------------------------------------------------------
# 1. Live SRL toss monitoring
# 2. ONE alert per real toss
# 3. Duplicate DOM detection protection
# 4. Daily fixture board after 00:10 IST
# 5. Fixture grouping by league
# 6. Fixtures sorted chronologically
# 7. Daily fixture board sent only once
# 8. Existing toss alert format preserved
# 9. Selenium + Chromium
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


# ============================================================
# TELEGRAM
#
# USE RAILWAY VARIABLES
#
# TELEGRAM_BOT_TOKEN = your existing token
# TELEGRAM_CHAT_ID   = your existing chat ID
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
# DAILY FIXTURE STATE
# ============================================================

DAILY_FIXTURE_STATE_FILE = Path(
    "daily_fixture_state.json"
)

last_fixture_date_sent = ""


# ============================================================
# LIVE TOSS LOCK
#
# Prevents multiple DOM detections of the same toss
# from generating multiple Telegram messages.
# ============================================================

live_toss_locks = set()


# ============================================================
# SINGLE PROCESS LOCK
#
# Prevents two copies of the monitor running inside the
# same Railway container.
# ============================================================

PROCESS_LOCK_FILE = Path(
    "/tmp/srl_toss_monitor.lock"
)

_process_lock_handle = None


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
        sorted(seen_tosses)
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

    else:

        last_fixture_date_sent = ""


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
            x
            for x in teams[:-1]
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
# IMPORTANT:
# We still inspect the toss element and ancestors.
# Duplicate protection happens later.
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
        # Ancestors
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
        # Smallest useful candidate first
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
        # Keep fixture information when available.
        #
        # This function only removes identical scan results.
        # Final one-alert protection happens in process_toss().
        # ----------------------------------------------------

        key = (
            winner.lower(),
            team1.lower(),
            team2.lower(),
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
# YOUR EXISTING FORMAT
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

    if team1 and team2:

        fixture_text = (
            f"{team1} vs {team2}"
        )

    else:

        fixture_text = "SRL Match"

    return (
        "🏏 SRL TOSS ALERT\n\n"

        f"🏆 {toss['winner']} WON THE TOSS\n\n"

        f"⚔️ {fixture_text}\n\n"

        f"🎯 {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}\n\n"

        "📡 Sportradar SRL Sportcentre\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# TOSS ID
#
# IMPORTANT FIX
#
# The same toss can appear in several DOM structures.
#
# We therefore use:
#
# DATE + WINNER + HOUR + MINUTE
#
# instead of:
#
# fixture + winner + decision
#
# This means:
#
# Same toss:
#   same winner
#   same date
#   same minute
#   => SAME ID
#
# Another match later:
#   same winner
#   different minute
#   => DIFFERENT ID
#
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

    raw = (
        "SRL-TOSS|"
        f"{now.strftime('%Y-%m-%d')}|"
        f"{now.strftime('%H:%M')}|"
        f"{winner}"
    )

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:32]


# ============================================================
# PROCESS TOSS
#
# ONE REAL TOSS -> ONE TELEGRAM ALERT
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

    # --------------------------------------------------------
    # CLEAN DATA
    # --------------------------------------------------------

    toss["winner"] = winner

    toss["decision"] = clean_text(
        toss.get(
            "decision",
            ""
        )
    ).lower()

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

    # --------------------------------------------------------
    # CANONICAL EVENT ID
    # --------------------------------------------------------

    identifier = make_toss_id(
        toss
    )

    # ========================================================
    # LIVE LOCK
    #
    # CRITICAL:
    # Lock BEFORE Telegram send.
    #
    # Therefore multiple DOM detections cannot send
    # multiple Telegram messages.
    # ========================================================

    if identifier in live_toss_locks:

        log.info(
            "🔒 DUPLICATE BLOCKED | "
            "%s",
            winner
        )

        return False

    # ========================================================
    # PERSISTENT STATE
    # ========================================================

    if identifier in seen_tosses:

        log.info(
            "💾 ALREADY SENT | "
            "%s",
            winner
        )

        live_toss_locks.add(
            identifier
        )

        return False

    # ========================================================
    # LOCK IMMEDIATELY
    # ========================================================

    live_toss_locks.add(
        identifier
    )

    log.info(
        "🔥 NEW SRL TOSS DETECTED | "
        "winner=%s | decision=%s | "
        "fixture=%s vs %s",
        winner,
        toss.get(
            "decision",
            ""
        ),
        toss.get(
            "team1",
            ""
        ) or "SRL",
        toss.get(
            "team2",
            ""
        ) or "Match"
    )

    # ========================================================
    # BUILD MESSAGE
    # ========================================================

    message = build_toss_message(
        toss
    )

    # ========================================================
    # SEND
    # ========================================================

    success = send_telegram(
        message
    )

    # ========================================================
    # FAILED
    #
    # Unlock so the same toss can retry.
    # ========================================================

    if not success:

        live_toss_locks.discard(
            identifier
        )

        log.error(
            "❌ Telegram failed. "
            "Toss unlocked for retry."
        )

        return False

    # ========================================================
    # SUCCESS
    #
    # Save permanently.
    # ========================================================

    seen_tosses.add(
        identifier
    )

    save_state()

    log.info(
        "✅ SRL TOSS ALERT SENT ONCE | "
        "%s",
        winner
    )

    return True


# ============================================================
# DAILY FIXTURE PARSER
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

    for index, line in enumerate(
        lines
    ):

        # ----------------------------------------------------
        # League detection
        # ----------------------------------------------------

        for league in league_patterns:

            if line.lower() == league.lower():

                current_league = league

                break

        # ----------------------------------------------------
        # Date/time detection
        #
        # Examples:
        #
        # 30 AGO | 15:30
        # 30 AUG | 15:30
        # ----------------------------------------------------

        time_match = re.search(
            r"\b\d{1,2}\s+"
            r"[A-Za-zÀ-ÿ]{3}"
            r"\s*\|\s*"
            r"(\d{1,2}):(\d{2})\b",
            line
        )

        if not time_match:

            continue

        if not current_league:

            continue

        if index == 0:

            continue

        if index + 1 >= len(lines):

            continue

        # ----------------------------------------------------
        # Teams directly surrounding the time line
        # ----------------------------------------------------

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

    now = current_ist()

    fixtures = parse_daily_fixtures(
        page_text
    )

    if not fixtures:

        log.warning(
            "No SRL fixtures found for daily schedule."
        )

        return None

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
    # Sort fixtures chronologically
    # --------------------------------------------------------

    for league in grouped:

        grouped[league].sort(
            key=lambda x: x[
                "sort_time"
            ]
        )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    message = (
        "🏏 SRL FIXTURES\n"
        f"📅 {now.strftime('%d %b %Y').upper()}"
    )

    for league in grouped:

        message += (
            "\n\n"
            f"🏆 {league.upper()}\n"
        )

        for fixture in grouped[league]:

            message += (
                "\n"
                f"⏰ {fixture['time']}\n"
                f"{fixture['team1']}\n"
                "vs\n"
                f"{fixture['team2']}\n"
            )

    return message.rstrip()


# ============================================================
# DAILY FIXTURE SCHEDULER
#
# SEND ONCE EVERY DAY AFTER 00:10 IST
# ============================================================

def maybe_send_daily_fixtures(
    page_text
):

    global last_fixture_date_sent

    now = current_ist()

    today = now.strftime(
        "%Y-%m-%d"
    )

    current_minutes = (
        now.hour * 60
        + now.minute
    )

    target_minutes = 10

    # --------------------------------------------------------
    # Before 00:10
    # --------------------------------------------------------

    if current_minutes < target_minutes:

        return

    # --------------------------------------------------------
    # Already sent today
    # --------------------------------------------------------

    if (
        last_fixture_date_sent
        == today
    ):

        return

    # --------------------------------------------------------
    # Build board
    # --------------------------------------------------------

    message = build_daily_fixture_message(
        page_text
    )

    if not message:

        return

    log.info(
        "📋 Sending daily SRL fixture schedule..."
    )

    # --------------------------------------------------------
    # Send
    # --------------------------------------------------------

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
    # Save ONLY after successful send
    # --------------------------------------------------------

    save_daily_fixture_state(
        today
    )

    log.info(
        "✅ Daily SRL fixture schedule sent | %s",
        today
    )


# ============================================================
# SINGLE PROCESS LOCK
# ============================================================

def acquire_process_lock():

    global _process_lock_handle

    try:

        import fcntl

        _process_lock_handle = open(
            PROCESS_LOCK_FILE,
            "w"
        )

        fcntl.flock(
            _process_lock_handle.fileno(),
            fcntl.LOCK_EX | fcntl.LOCK_NB
        )

        _process_lock_handle.write(
            str(os.getpid())
        )

        _process_lock_handle.flush()

        log.info(
            "🔒 Single-process lock acquired | PID=%s",
            os.getpid()
        )

        return True

    except BlockingIOError:

        log.error(
            "❌ Another SRL monitor process "
            "is already running."
        )

        return False

    except Exception as exc:

        log.error(
            "Process lock error: %s",
            exc
        )

        return False


# ============================================================
# RELEASE PROCESS LOCK
# ============================================================

def release_process_lock():

    global _process_lock_handle

    if _process_lock_handle is None:

        return

    try:

        import fcntl

        fcntl.flock(
            _process_lock_handle.fileno(),
            fcntl.LOCK_UN
        )

        _process_lock_handle.close()

    except Exception:

        pass

    _process_lock_handle = None


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
            # Independent from toss detection.
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
    # SINGLE INSTANCE
    # ========================================================

    if not acquire_process_lock():

        return

    driver = None

    try:

        # ====================================================
        # TELEGRAM
        # ====================================================

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

        # ====================================================
        # STATE
        # ====================================================

        load_state()

        load_daily_fixture_state()

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

        heartbeat(
            "STOPPED"
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

        release_process_lock()


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
