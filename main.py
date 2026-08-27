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
# ALERT:
#
# 🏏 SRL TOSS ALERT
#
# 🏆 Chennai Super Kings SRL WON THE TOSS
#
# Chennai Super Kings SRL vs Mumbai Indians SRL
#
# 🎯 BOWL
# ⏰ 27 Aug 2026 | 09:20:25 IST
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
# CONFIG
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

# IMPORTANT:
# Put these in Railway Variables.
# Do NOT hard-code tokens in the code.

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
        " ",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# CLEAN TEAM NAME
# ============================================================

def clean_team_name(
    value,
):

    value = clean_text(
        value
    )

    if not value:
        return ""

    # Remove things such as:
    #
    # 0 OV Chennai Super Kings SRL
    # 11.2 OV Chennai Super Kings SRL
    # 0/0 Chennai Super Kings SRL
    #
    value = re.sub(
        r"^(?:\d+(?:\.\d+)?\s*"
        r"(?:OV|OVERS?)\s*)+",
        "",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"^(?:\d+/\d+\s*)+",
        "",
        value,
    )

    value = clean_text(
        value
    )

    # Keep only through SRL.
    match = re.search(
        r"(.+?\sSRL)\b",
        value,
        re.IGNORECASE,
    )

    if match:

        value = clean_text(
            match.group(1)
        )

    return value


# ============================================================
# SRL TEAM CHECK
# ============================================================

def is_srl_team(
    name,
):

    name = clean_team_name(
        name
    )

    return bool(
        re.search(
            r"\sSRL$",
            name,
            re.IGNORECASE,
        )
    )


# ============================================================
# EXTRACT SRL TEAM NAMES
# ============================================================

def extract_srl_teams(
    value,
):

    value = clean_text(
        value
    )

    if not value:
        return []

    matches = re.findall(
        r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)\b",
        value,
        flags=re.IGNORECASE,
    )

    teams = []

    for match in matches:

        team = clean_team_name(
            match
        )

        if not is_srl_team(
            team
        ):
            continue

        # Remove duplicates.
        if team.lower() not in {
            x.lower()
            for x in teams
        }:

            teams.append(
                team
            )

    return teams


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
# STARTUP
# ============================================================

def startup_message():

    return (
        "🟢 SRL TOSS MONITOR ONLINE\n\n"
        "🏏 SRL CRICKET ONLY\n"
        "📡 Sportradar SRL Sportcentre\n\n"
        "🌐 Selenium + Chrome WebDriver\n"
        f"🔄 DOM check: {CHECK_INTERVAL}s\n"
        f"🔃 Page refresh: {PAGE_REFRESH_INTERVAL}s\n\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🎯 Toss detector: ACTIVE\n"
        "🇮🇳 Time: IST\n\n"
        "Waiting for SRL toss..."
    )


# ============================================================
# CREATE DRIVER
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

    log.info(
        "Browser URL: %s",
        driver.current_url,
    )

    log.info(
        "Browser title: %s",
        driver.title,
    )


# ============================================================
# PAGE TEXT
# ============================================================

def get_page_text(
    driver,
):

    try:

        return driver.execute_script(
            """
            return document.body
                ? document.body.innerText
                : "";
            """
        ) or ""

    except Exception as exc:

        log.warning(
            "Could not read DOM: %s",
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
# PARSE TOSS SENTENCE
# ============================================================

def parse_toss(
    text_value,
):

    text_value = clean_text(
        text_value
    )

    if not text_value:
        return None

    # Must contain actual toss phrase.
    if not re.search(
        r"\bwon\s+the\s+toss\b",
        text_value,
        re.IGNORECASE,
    ):

        return None

    # --------------------------------------------------------
    # Winner
    # --------------------------------------------------------

    winner_match = re.search(
        r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)"
        r"\s+won\s+the\s+toss",
        text_value,
        flags=re.IGNORECASE,
    )

    if not winner_match:

        return None

    winner = clean_team_name(
        winner_match.group(1)
    )

    if not is_srl_team(
        winner
    ):

        return None

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    decision_match = re.search(
        r"won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        text_value,
        flags=re.IGNORECASE,
    )

    decision = ""

    if decision_match:

        decision = clean_text(
            decision_match.group(1) or ""
        ).lower()

    # --------------------------------------------------------
    # Teams inside same DOM container.
    # --------------------------------------------------------

    teams = extract_srl_teams(
        text_value
    )

    team1 = ""
    team2 = ""

    if len(teams) >= 2:

        # Prefer winner as team1 when present.
        winner_index = None

        for index, team in enumerate(
            teams
        ):

            if team.lower() == winner.lower():

                winner_index = index
                break

        if winner_index is not None:

            team1 = teams[
                winner_index
            ]

            for index, team in enumerate(
                teams
            ):

                if index != winner_index:

                    team2 = team
                    break

        else:

            team1 = teams[0]
            team2 = teams[1]

    return {
        "winner": winner,
        "decision": decision,
        "team1": team1,
        "team2": team2,
    }


# ============================================================
# DOM TOSS DETECTOR
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
            "DOM search failed: %s",
            exc,
        )

        return results

    for element in elements:

        candidate_texts = []

        # ----------------------------------------------------
        # Current element.
        # ----------------------------------------------------

        try:

            value = element.get_attribute(
                "innerText"
            )

            if value:

                candidate_texts.append(
                    value
                )

        except Exception:

            pass

        # ----------------------------------------------------
        # Walk up DOM parents.
        #
        # This is important because the toss sentence
        # may be inside a child element while the two
        # team names are stored in the match row.
        # ----------------------------------------------------

        for level in range(
            1,
            7,
        ):

            try:

                parent_text = driver.execute_script(
                    """
                    let el = arguments[0];
                    let levels = arguments[1];

                    for (let i = 0; i < levels; i++) {
                        if (el && el.parentElement) {
                            el = el.parentElement;
                        }
                    }

                    return el ? el.innerText : "";
                    """,
                    element,
                    level,
                )

                if parent_text:

                    candidate_texts.append(
                        parent_text
                    )

            except Exception:

                continue

        # ----------------------------------------------------
        # Prefer the SMALLEST useful container.
        # ----------------------------------------------------

        candidate_texts = sorted(
            {
                clean_text(x)
                for x in candidate_texts
                if clean_text(x)
            },
            key=len,
        )

        toss = None

        for candidate in candidate_texts:

            parsed = parse_toss(
                candidate
            )

            if not parsed:

                continue

            toss = parsed

            # Stop once fixture has been found.
            if (
                parsed["team1"]
                and parsed["team2"]
            ):

                break

        if toss:

            results.append(
                toss
            )

    return deduplicate_tosses(
        results
    )


# ============================================================
# PAGE TEXT FALLBACK
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
    # Search actual toss sentences.
    # --------------------------------------------------------

    pattern = re.compile(
        r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)"
        r"\s+won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(
        normalized
    ):

        winner = clean_team_name(
            match.group(1)
        )

        if not is_srl_team(
            winner
        ):

            continue

        decision = clean_text(
            match.group(2) or ""
        ).lower()

        # Page-text fallback does not know the exact row,
        # therefore fixture remains SRL Match.
        results.append(
            {
                "winner": winner,
                "decision": decision,
                "team1": "",
                "team2": "",
            }
        )

    return deduplicate_tosses(
        results
    )


# ============================================================
# DEDUPLICATE
# ============================================================

def deduplicate_tosses(
    tosses,
):

    unique = {}

    for toss in tosses:

        winner = clean_team_name(
            toss.get(
                "winner",
                "",
            )
        )

        decision = clean_text(
            toss.get(
                "decision",
                "",
            )
        ).lower()

        team1 = clean_team_name(
            toss.get(
                "team1",
                "",
            )
        )

        team2 = clean_team_name(
            toss.get(
                "team2",
                "",
            )
        )

        if not winner:

            continue

        key = (
            winner.lower(),
            decision,
            team1.lower(),
            team2.lower(),
        )

        unique[key] = {
            "winner": winner,
            "decision": decision,
            "team1": team1,
            "team2": team2,
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
            minutes=30,
        )
    )

    return datetime.now(
        timezone.utc
    ).astimezone(
        ist
    )


# ============================================================
# DECISION
# ============================================================

def format_decision(
    decision,
):

    value = clean_text(
        decision
    ).lower()

    if value == "bat":

        return "BAT"

    if value in {
        "bowl",
        "field",
    }:

        return "BOWL"

    return "TOSS"


# ============================================================
# TOSS MESSAGE
# ============================================================

def build_toss_message(
    toss,
):

    now = current_ist()

    winner = clean_team_name(
        toss["winner"]
    )

    team1 = clean_team_name(
        toss.get(
            "team1",
            "",
        )
    )

    team2 = clean_team_name(
        toss.get(
            "team2",
            "",
        )
    )

    decision = format_decision(
        toss.get(
            "decision",
            "",
        )
    )

    # --------------------------------------------------------
    # Fixture
    # --------------------------------------------------------

    if (
        team1
        and team2
        and team1.lower() != team2.lower()
    ):

        fixture = (
            f"{team1} vs {team2}"
        )

    else:

        fixture = "SRL Match"

    # --------------------------------------------------------
    # EXACT ALERT FORMAT
    # --------------------------------------------------------

    return (
        "🏏 SRL TOSS ALERT\n\n"

        f"🏆 {winner} WON THE TOSS\n\n"

        f"{fixture}\n\n"

        f"🎯 {decision}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}"
    )


# ============================================================
# TOSS ID
# ============================================================

def make_toss_id(
    toss,
):

    # Include fixture so that:
    #
    # Team A + BOWL
    #
    # in one match does not block
    # Team A + BOWL in another match.

    raw = (
        f"{toss.get('winner', '').strip().lower()}|"
        f"{toss.get('team1', '').strip().lower()}|"
        f"{toss.get('team2', '').strip().lower()}|"
        f"{toss.get('decision', '').strip().lower()}"
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

    winner = clean_team_name(
        toss.get(
            "winner",
            "",
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

    toss["team1"] = clean_team_name(
        toss.get(
            "team1",
            "",
        )
    )

    toss["team2"] = clean_team_name(
        toss.get(
            "team2",
            "",
        )
    )

    identifier = make_toss_id(
        toss
    )

    if identifier in seen_tosses:

        return False

    message = build_toss_message(
        toss
    )

    log.info(
        "🔥 NEW SRL TOSS | "
        "winner=%s | "
        "team1=%s | "
        "team2=%s | "
        "decision=%s",
        toss["winner"],
        toss["team1"],
        toss["team2"],
        toss["decision"],
    )

    # --------------------------------------------------------
    # SEND ONCE
    # --------------------------------------------------------

    if not send_telegram(
        message
    ):

        log.error(
            "Telegram failed. "
            "Toss remains unsent."
        )

        return False

    seen_tosses.add(
        identifier
    )

    save_state()

    log.info(
        "✅ SRL TOSS ALERT SENT ONCE"
    )

    return True


# ============================================================
# BASELINE
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
    # Existing tosses should not alert on startup.
    # --------------------------------------------------------

    baseline_existing_tosses(
        driver
    )

    while True:

        try:

            # =================================================
            # READ DOM
            # =================================================

            page_text = get_page_text(
                driver
            )

            normalized = clean_text(
                page_text
            )

            # =================================================
            # PAGE LOG
            # =================================================

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
            # FALLBACK TEXT DETECTOR
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
                        exc,
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

    # --------------------------------------------------------
    # Telegram
    # --------------------------------------------------------

    if not telegram_configured():

        log.error(
            "Telegram configuration missing."
        )

        return

    log.info(
        "Telegram configuration detected."
    )

    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    load_state()

    # --------------------------------------------------------
    # Driver
    # --------------------------------------------------------

    driver = None

    try:

        driver = create_driver()

        open_page(
            driver
        )

        # ----------------------------------------------------
        # Initial page
        # ----------------------------------------------------

        page_text = get_page_text(
            driver
        )

        log_page_preview(
            page_text
        )

        # ----------------------------------------------------
        # Startup
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Monitor
        # ----------------------------------------------------

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
