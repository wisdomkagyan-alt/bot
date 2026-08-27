# ============================================================
# SRL TOSS SELENIUM MONITOR 2026
#
# SRL CRICKET ONLY
#
# Source:
# https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket
#
# Selenium + Chromium
# Rendered page detection
# Telegram immediate toss alerts
#
# Detects:
#
#   "South Africa SRL won the toss and elected to bat"
#   "India SRL won the toss and elected to bowl"
#
# Also supports completed-match backup:
#
#   "(Toss:SA)"
#   "(Toss:IND)"
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

TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU",
).strip()

TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "8783763018",
).strip()


# ============================================================
# MONITOR SETTINGS
# ============================================================

# Check rendered page every second.
CHECK_INTERVAL = 1

# Refresh browser periodically so newly published
# information is definitely loaded.
PAGE_REFRESH_INTERVAL = 15

REQUEST_TIMEOUT = 15


# ============================================================
# STATE
# ============================================================

STATE_FILE = Path(
    "srl_seen_tosses.json"
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
# LOAD STATE
# ============================================================

def load_state():

    global seen_tosses

    if not STATE_FILE.exists():

        seen_tosses = set()

        log.info(
            "No previous SRL toss state found."
        )

        return

    try:

        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, list):

            seen_tosses = {
                str(x)
                for x in data
            }

        else:

            seen_tosses = set()

        log.info(
            "Loaded %s previous SRL tosses.",
            len(seen_tosses),
        )

    except Exception as exc:

        log.warning(
            "Could not load toss state: %s",
            exc,
        )

        seen_tosses = set()


# ============================================================
# SAVE STATE
# ============================================================

def save_state():

    try:

        STATE_FILE.write_text(
            json.dumps(
                sorted(seen_tosses),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception as exc:

        log.error(
            "Could not save toss state: %s",
            exc,
        )


# ============================================================
# HEARTBEAT
# ============================================================

def heartbeat(status):

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

def send_telegram(message):

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

    for attempt in range(1, 4):

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

        "⚡ Selenium + Chrome WebDriver\n"
        f"🔄 Page check: {CHECK_INTERVAL}s\n"
        f"🌐 Refresh: {PAGE_REFRESH_INTERVAL}s\n\n"

        "📡 Telegram: ACTIVE\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🎯 Toss-text detection: ACTIVE\n\n"

        "Waiting for new SRL toss..."
    )


# ============================================================
# CHROME
# ============================================================

def create_driver():

    log.info(
        "Launching Chrome WebDriver..."
    )

    options = Options()

    # Railway/headless mode.
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
        "--window-size=1440,2200"
    )

    options.add_argument(
        "--disable-notifications"
    )

    options.add_argument(
        "--disable-popup-blocking"
    )

    options.add_argument(
        "--disable-blink-features=AutomationControlled"
    )

    options.add_argument(
        "--lang=en-US"
    )

    # Railway Debian Chromium location.
    chrome_binary = os.getenv(
        "CHROME_BINARY",
        "/usr/bin/chromium",
    )

    chrome_driver = os.getenv(
        "CHROMEDRIVER_PATH",
        "/usr/bin/chromedriver",
    )

    options.binary_location = chrome_binary

    log.info(
        "Using Chrome binary: %s",
        chrome_binary,
    )

    log.info(
        "Using ChromeDriver: %s",
        chrome_driver,
    )

    service = webdriver.ChromeService(
        executable_path=chrome_driver
    )

    driver = webdriver.Chrome(
        service=service,
        options=options,
    )

    driver.set_page_load_timeout(
        30
    )

    driver.implicitly_wait(
        2
    )

    return driver


# ============================================================
# GET PAGE TEXT
# ============================================================

def get_page_text(driver):

    try:

        body = driver.find_element(
            By.TAG_NAME,
            "body",
        )

        text = body.text

        return text.strip()

    except Exception as exc:

        log.warning(
            "Could not read page text: %s",
            exc,
        )

        return ""


# ============================================================
# NORMALIZE TEXT
# ============================================================

def normalize_text(value):

    if not value:
        return ""

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
# SRL TEAM REGEX
# ============================================================

SRL_TEAM_PATTERN = (
    r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?"
    r"\sSRL)"
)


# ============================================================
# EXTRACT ALL SRL TEAMS
# ============================================================

def extract_srl_teams(text):

    teams = []

    for match in re.finditer(
        SRL_TEAM_PATTERN,
        text,
        flags=re.IGNORECASE,
    ):

        team = normalize_text(
            match.group(1)
        )

        if team and team not in teams:

            teams.append(team)

    return teams


# ============================================================
# EXACT TOSS SENTENCE DETECTION
# ============================================================

def find_toss_sentences(page_text):

    results = []

    normalized = normalize_text(
        page_text
    )

    # --------------------------------------------------------
    # Primary detection.
    #
    # This matches the exact style shown on your website:
    #
    # South Africa SRL won the toss and elected to bat
    # --------------------------------------------------------

    pattern = re.compile(
        r"("
        r"[A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?"
        r"\sSRL"
        r")"
        r"\s+won\s+the\s+toss"
        r"(?:\s+and\s+elected\s+to\s+"
        r"(bat|bowl|field))?",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(
        normalized
    ):

        winner = normalize_text(
            match.group(1)
        )

        decision = (
            match.group(2)
            or ""
        ).lower()

        results.append(
            {
                "winner": winner,
                "decision": decision,
                "raw": match.group(0),
            }
        )

    return results


# ============================================================
# COMPLETED MATCH TOSS BACKUP
# ============================================================

TOSS_CODE_MAP = {
    "SA": "South Africa SRL",
    "IND": "India SRL",
    "WI": "West Indies SRL",
    "AFG": "Afghanistan SRL",
    "ENG": "England SRL",
    "PAK": "Pakistan SRL",
    "AUS": "Australia SRL",
    "NZ": "New Zealand SRL",

    "RR": "Rajasthan Royals SRL",
    "LSG": "Lucknow Super Giants SRL",
    "CSK": "Chennai Super Kings SRL",
    "MI": "Mumbai Indians SRL",
    "DC": "Delhi Capitals SRL",
    "SRH": "Sunrisers Hyderabad SRL",
    "GT": "Gujarat Titans SRL",
    "RCB": "Royal Challengers Bangalore SRL",

    "PC": "Pretoria Capitals SRL",
    "MCT": "Mi Cape Town SRL",
    "JSK": "Joburg Super Kings SRL",
    "PR": "Paarl Royals SRL",
    "DSG": "Durban Super Giants SRL",
    "SEC": "Sunrisers Eastern Cape SRL",

    "IU": "Islamabad United SRL",
    "PZ": "Peshawar Zalmi SRL",
    "KK": "Karachi Kings SRL",
    "MS": "Multan Sultans SRL",
    "LQ": "Lahore Qalandars SRL",
    "QG": "Quetta Gladiators SRL",
    "HK": "Hyderabad Kingsmen SRL",

    "OT": "Otago SRL",
    "AKL": "Auckland SRL",
    "CD": "Central Districts SRL",
    "CAN": "Canterbury SRL",
    "ND": "Northern Districts SRL",
    "WEL": "Wellington SRL",
}


# ============================================================
# FIND TOSS CODE BACKUP
# ============================================================

def find_toss_codes(page_text):

    results = []

    normalized = normalize_text(
        page_text
    )

    pattern = re.compile(
        r"\(Toss\s*:\s*([A-Za-z0-9_-]+)\)",
        flags=re.IGNORECASE,
    )

    for match in pattern.finditer(
        normalized
    ):

        code = (
            match.group(1)
            .strip()
            .upper()
        )

        winner = TOSS_CODE_MAP.get(
            code
        )

        if not winner:

            continue

        results.append(
            {
                "winner": winner,
                "decision": "",
                "raw": match.group(0),
            }
        )

    return results


# ============================================================
# FIND FIXTURE AROUND TOSS
# ============================================================

def find_fixture(
    page_text,
    winner,
):

    normalized = normalize_text(
        page_text
    )

    # --------------------------------------------------------
    # First try to locate the winner and nearby text.
    # --------------------------------------------------------

    winner_index = normalized.lower().find(
        winner.lower()
    )

    if winner_index < 0:

        return "SRL Match", "SRL Cricket"

    # --------------------------------------------------------
    # Search nearby area.
    # --------------------------------------------------------

    start = max(
        0,
        winner_index - 500,
    )

    end = min(
        len(normalized),
        winner_index + 700,
    )

    nearby = normalized[
        start:end
    ]

    # --------------------------------------------------------
    # Extract SRL team names.
    # --------------------------------------------------------

    teams = extract_srl_teams(
        nearby
    )

    # Remove duplicates.
    unique_teams = []

    for team in teams:

        if team not in unique_teams:

            unique_teams.append(team)

    # Winner first.
    if winner in unique_teams:

        unique_teams.remove(
            winner
        )

        unique_teams.insert(
            0,
            winner
        )

    if len(unique_teams) >= 2:

        fixture = (
            f"{unique_teams[0]} vs "
            f"{unique_teams[1]}"
        )

    else:

        fixture = "SRL Match"

    # --------------------------------------------------------
    # Determine league.
    # --------------------------------------------------------

    league = "SRL Cricket"

    lower = nearby.lower()

    if "indian premier league srl" in lower:

        league = "Indian Premier League SRL"

    elif "t20 international srl" in lower:

        league = "T20 International SRL"

    elif "sa20 srl" in lower:

        league = "SA20 SRL"

    elif "pakistan super league srl" in lower:

        league = "Pakistan Super League SRL"

    elif "super smash srl" in lower:

        league = "Super Smash SRL"

    elif "caribbean premier league srl" in lower:

        league = "Caribbean Premier League SRL"

    return fixture, league


# ============================================================
# UTC → IST
# ============================================================

def ist_now():

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
    decision
):

    decision = normalize_text(
        decision
    ).lower()

    if decision == "bat":

        return "Elected to bat"

    if decision == "bowl":

        return "Elected to bowl"

    if decision == "field":

        return "Elected to field"

    return "Not reported"


# ============================================================
# TOSS ID
# ============================================================

def make_toss_id(
    winner,
    fixture,
    decision,
):

    raw = (
        f"{winner}|"
        f"{fixture}|"
        f"{decision}"
    ).lower()

    return hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:32]


# ============================================================
# BUILD ALERT
# ============================================================

def build_toss_message(
    winner,
    fixture,
    league,
    decision,
):

    now = ist_now()

    return (
        "🏏 SRL TOSS ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🏆 {winner} WON THE TOSS\n\n"

        f"⚔️ {fixture}\n"
        f"🏆 {league}\n\n"

        f"🎯 Decision: "
        f"{format_decision(decision)}\n"

        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}\n\n"

        "📡 Sportradar SRL Sportcentre\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# PROCESS ONE TOSS
# ============================================================

def process_toss(
    toss,
    page_text,
):

    winner = toss[
        "winner"
    ]

    decision = toss.get(
        "decision",
        "",
    )

    fixture, league = find_fixture(
        page_text,
        winner,
    )

    identifier = make_toss_id(
        winner,
        fixture,
        decision,
    )

    if identifier in seen_tosses:

        return False

    log.info(
        "NEW SRL TOSS | winner=%s | "
        "fixture=%s | decision=%s",
        winner,
        fixture,
        decision,
    )

    message = build_toss_message(
        winner,
        fixture,
        league,
        decision,
    )

    if not send_telegram(
        message
    ):

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
        "SRL TOSS ALERT SENT."
    )

    return True


# ============================================================
# INITIAL PAGE BASELINE
# ============================================================

def initialize_existing_tosses(
    page_text
):

    existing = []

    existing.extend(
        find_toss_sentences(
            page_text
        )
    )

    # --------------------------------------------------------
    # Important:
    #
    # We DO NOT alert for tosses already visible when the
    # bot first starts.
    #
    # Otherwise restarting the bot on a page containing
    # yesterday/today completed matches would generate
    # old alerts.
    # --------------------------------------------------------

    for toss in existing:

        winner = toss[
            "winner"
        ]

        fixture, _ = find_fixture(
            page_text,
            winner,
        )

        identifier = make_toss_id(
            winner,
            fixture,
            toss.get(
                "decision",
                "",
            ),
        )

        seen_tosses.add(
            identifier
        )

    if existing:

        save_state()

        log.info(
            "Initial baseline: %s existing "
            "toss statements registered.",
            len(existing),
        )

    else:

        log.info(
            "Initial baseline: no existing "
            "live toss statements."
        )


# ============================================================
# MONITOR PAGE
# ============================================================

def monitor_page(
    driver
):

    last_refresh = time.monotonic()

    first_scan = True

    last_page_text = ""

    while True:

        try:

            now = time.monotonic()

            # ------------------------------------------------
            # Periodic page refresh.
            # ------------------------------------------------

            if (
                now - last_refresh
                >= PAGE_REFRESH_INTERVAL
            ):

                log.info(
                    "Refreshing SRL Cricket page..."
                )

                driver.refresh()

                time.sleep(3)

                last_refresh = time.monotonic()

                first_scan = False

            # ------------------------------------------------
            # Read rendered DOM.
            # ------------------------------------------------

            page_text = get_page_text(
                driver
            )

            if not page_text:

                time.sleep(
                    CHECK_INTERVAL
                )

                continue

            # ------------------------------------------------
            # Log only when page content changes.
            # ------------------------------------------------

            if page_text != last_page_text:

                log.info(
                    "Rendered page text length: %s",
                    len(page_text),
                )

                preview = normalize_text(
                    page_text
                )[:1500]

                log.info(
                    "PAGE PREVIEW: %s",
                    preview,
                )

                last_page_text = page_text

            # ------------------------------------------------
            # First scan.
            # ------------------------------------------------

            if first_scan:

                initialize_existing_tosses(
                    page_text
                )

                first_scan = False

            # ------------------------------------------------
            # PRIMARY:
            #
            # "South Africa SRL won the toss
            #  and elected to bat"
            # ------------------------------------------------

            tosses = find_toss_sentences(
                page_text
            )

            for toss in tosses:

                process_toss(
                    toss,
                    page_text,
                )

            # ------------------------------------------------
            # BACKUP:
            #
            # "(Toss:SA)"
            #
            # Only used when exact toss sentence is no longer
            # visible.
            # ------------------------------------------------

            if not tosses:

                backup_tosses = (
                    find_toss_codes(
                        page_text
                    )
                )

                for toss in backup_tosses:

                    process_toss(
                        toss,
                        page_text,
                    )

            heartbeat(
                "ACTIVE"
            )

            time.sleep(
                CHECK_INTERVAL
            )

        except KeyboardInterrupt:

            raise

        except Exception as exc:

            log.exception(
                "Monitor loop error: %s",
                exc,
            )

            heartbeat(
                "ERROR - RECOVERING"
            )

            time.sleep(3)


# ============================================================
# MAIN
# ============================================================

def main():

    log.info(
        "%s STARTING",
        SYSTEM_VERSION,
    )

    # --------------------------------------------------------
    # Credentials
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
    # Chrome
    # --------------------------------------------------------

    driver = None

    try:

        driver = create_driver()

        # ----------------------------------------------------
        # Open SRL Cricket page.
        # ----------------------------------------------------

        log.info(
            "Opening SRL Cricket page..."
        )

        driver.get(
            SRL_URL
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

        # ----------------------------------------------------
        # Initial rendered page.
        # ----------------------------------------------------

        page_text = get_page_text(
            driver
        )

        log.info(
            "Rendered page text length: %s",
            len(page_text),
        )

        log.info(
            "PAGE PREVIEW: %s",
            normalize_text(
                page_text
            )[:1500],
        )

        # ----------------------------------------------------
        # Startup Telegram.
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
        # Monitor.
        # ----------------------------------------------------

        monitor_page(
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
            exc,
        )

        heartbeat(
            "FATAL ERROR"
        )

    finally:

        if driver is not None:

            try:

                driver.quit()

            except Exception:

                pass


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
