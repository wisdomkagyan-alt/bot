# ============================================================
# SRL TOSS MONITOR 2026
#
# Sportradar SRL Sportcentre Cricket
# Selenium + Chrome WebDriver -> Telegram
#
# SRL CRICKET ONLY
#
# NO generic Sportradar Cricket API
# NO Playwright
# NO API schedule endpoint
#
# Railway Variables:
#
#   TELEGRAM_BOT_TOKEN
#   TELEGRAM_CHAT_ID
#
# ============================================================

import hashlib
import json
import logging
import os
import re
import time

from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


# ============================================================
# CONFIGURATION
# ============================================================

SYSTEM_VERSION = "SRL-TOSS-SELENIUM-2026"

SRL_URL = (
    "https://sportcenter.sir.sportradar.com/"
    "pt/simulated-reality/cricket"
)


# ============================================================
# TELEGRAM
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
# MONITOR SETTINGS
# ============================================================

# How often Selenium scans the already-open page.
SCAN_INTERVAL = 2

# Reload page periodically so newly-rendered data is obtained.
PAGE_REFRESH_INTERVAL = 30

# Initial page wait.
PAGE_LOAD_WAIT = 8

# Selenium page-load timeout.
PAGE_LOAD_TIMEOUT = 30

# HTTP timeout for Telegram.
REQUEST_TIMEOUT = 15


# ============================================================
# STATE
# ============================================================

STATE_FILE = Path(
    "seen_srl_tosses.json"
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
# TEXT HELPERS
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
# STATE LOAD
# ============================================================

def load_state():

    global seen_tosses

    if not STATE_FILE.exists():

        log.info(
            "No previous SRL toss state found."
        )

        seen_tosses = set()

        return

    try:

        data = json.loads(
            STATE_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(
            data,
            list,
        ):

            seen_tosses = {
                str(item)
                for item in data
            }

        else:

            seen_tosses = set()

        log.info(
            "Loaded %s previously seen SRL tosses.",
            len(seen_tosses),
        )

    except Exception as exc:

        log.warning(
            "Could not load state: %s",
            exc,
        )

        seen_tosses = set()


# ============================================================
# STATE SAVE
# ============================================================

def save_state():

    try:

        STATE_FILE.write_text(
            json.dumps(
                sorted(
                    seen_tosses
                ),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    except Exception as exc:

        log.error(
            "Could not save state: %s",
            exc,
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

def send_telegram(
    message
):

    if not telegram_configured():

        log.error(
            "Telegram credentials are missing."
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
        4
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
        "📡 Sportradar SRL Sportcentre\n"
        "🌐 Selenium + Chrome WebDriver\n\n"

        f"⚡ Scan interval: {SCAN_INTERVAL}s\n"
        f"🔄 Page refresh: {PAGE_REFRESH_INTERVAL}s\n\n"

        "📡 Telegram: ACTIVE\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🎯 SRL filter: ACTIVE\n"
        "🕐 Timezone: IST\n\n"

        "Waiting for live SRL toss..."
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
    # Railway / Docker
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
        "--window-size=1440,2000"
    )

    options.add_argument(
        "--disable-blink-features=AutomationControlled"
    )

    options.add_argument(
        "--disable-notifications"
    )

    options.add_argument(
        "--disable-popup-blocking"
    )

    options.add_argument(
        "--lang=en-US"
    )

    options.add_argument(
        "--user-agent="
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )

    # --------------------------------------------------------
    # Try Railway's standard Chromium paths.
    # --------------------------------------------------------

    chrome_binary_candidates = [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
    ]

    for binary in chrome_binary_candidates:

        if Path(binary).exists():

            options.binary_location = binary

            log.info(
                "Using Chrome binary: %s",
                binary,
            )

            break


    driver_candidates = [
        "/usr/bin/chromedriver",
        "/usr/bin/chromium-driver",
    ]

    driver_path = None

    for candidate in driver_candidates:

        if Path(candidate).exists():

            driver_path = candidate

            log.info(
                "Using ChromeDriver: %s",
                candidate,
            )

            break


    if driver_path:

        service = Service(
            executable_path=driver_path
        )

        driver = webdriver.Chrome(
            service=service,
            options=options,
        )

    else:

        log.info(
            "ChromeDriver path not found. "
            "Allowing Selenium Manager to locate it."
        )

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
            "Initial page load exception: %s",
            exc,
        )

    time.sleep(
        PAGE_LOAD_WAIT
    )

    log.info(
        "Browser URL: %s",
        driver.current_url,
    )

    log.info(
        "Browser title: %s",
        driver.title,
    )

    return inspect_page(
        driver,
        initial=True,
    )


# ============================================================
# PAGE INSPECTION
# ============================================================

def inspect_page(
    driver,
    initial=False,
):

    try:

        body_text = clean_text(
            driver.find_element(
                "tag name",
                "body",
            ).text
        )

    except Exception as exc:

        log.error(
            "Could not read page body: %s",
            exc,
        )

        return ""

    if initial:

        log.info(
            "Rendered page text length: %s",
            len(body_text),
        )

        preview = body_text[
            :1000
        ]

        if preview:

            log.info(
                "PAGE PREVIEW: %s",
                preview,
            )

    return body_text


# ============================================================
# SRL PAGE VALIDATION
# ============================================================

def page_is_srl(
    body_text
):

    if not body_text:

        return False

    lower = body_text.lower()

    # --------------------------------------------------------
    # Strong SRL indicators visible on the actual page.
    # --------------------------------------------------------

    indicators = [
        "simulated reality league",
        "indian premier league srl",
        "t20 international srl",
        "sa20 srl",
        "pakistan super league srl",
        "super smash srl",
    ]

    return any(
        indicator in lower
        for indicator in indicators
    )


# ============================================================
# FIND TOSS SENTENCES
# ============================================================

def find_toss_sentences(
    body_text
):

    if not body_text:

        return []

    results = []

    # --------------------------------------------------------
    # Primary live SRL wording.
    #
    # Example:
    #
    # South Africa SRL won the toss and elected to bat
    #
    # --------------------------------------------------------

    pattern = re.compile(
        r"([A-Za-z0-9 .&'’\-]+?)"
        r"\s+won the toss and elected to\s+"
        r"(bat|bowl|field)\b",
        re.IGNORECASE,
    )

    for match in pattern.finditer(
        body_text
    ):

        winner = clean_text(
            match.group(1)
        )

        decision = clean_text(
            match.group(2)
        ).lower()

        results.append(
            {
                "winner": winner,
                "decision": decision,
                "raw": clean_text(
                    match.group(0)
                ),
            }
        )

    return results


# ============================================================
# SRL TEAM CHECK
# ============================================================

def is_srl_team(
    team_name
):

    value = clean_text(
        team_name
    ).lower()

    return (
        value.endswith(" srl")
        or " srl " in f" {value} "
    )


# ============================================================
# VALIDATE TOSS
# ============================================================

def validate_toss(
    toss
):

    winner = clean_text(
        toss.get("winner")
    )

    decision = clean_text(
        toss.get("decision")
    ).lower()

    if not winner:

        return False

    if not is_srl_team(
        winner
    ):

        log.warning(
            "Rejected non-SRL toss winner: %s",
            winner,
        )

        return False

    if decision not in {
        "bat",
        "bowl",
        "field",
    }:

        return False

    return True


# ============================================================
# FIND MATCH CONTEXT
# ============================================================

def find_match_context(
    body_text,
    winner,
):

    lines = [
        clean_text(line)
        for line in body_text.splitlines()
        if clean_text(line)
    ]

    winner_lower = winner.lower()

    winner_index = -1

    for index, line in enumerate(lines):

        if (
            winner_lower in line.lower()
            and
            "won the toss" in line.lower()
        ):

            winner_index = index

            break

    if winner_index < 0:

        # Fallback search.
        for index, line in enumerate(lines):

            if winner_lower in line.lower():

                winner_index = index

                break

    if winner_index < 0:

        return {
            "teams": [],
            "tournament": "",
        }


    # --------------------------------------------------------
    # Search nearby lines for SRL teams.
    # --------------------------------------------------------

    nearby = lines[
        max(
            0,
            winner_index - 8
        ):
        min(
            len(lines),
            winner_index + 8
        )
    ]

    teams = []

    for line in nearby:

        if is_srl_team(line):

            # Avoid obvious status lines.
            if (
                "won the toss" not in line.lower()
                and "elected to" not in line.lower()
            ):

                if line not in teams:

                    teams.append(
                        line
                    )

    # Winner may only occur in toss sentence.
    if winner not in teams:

        teams.insert(
            0,
            winner
        )

    # Keep only plausible team names.
    teams = [
        team
        for team in teams
        if len(team) <= 80
    ]

    # --------------------------------------------------------
    # Tournament detection.
    # --------------------------------------------------------

    tournament = ""

    tournament_names = [
        "Indian Premier League SRL",
        "T20 International SRL",
        "SA20 SRL",
        "Pakistan Super League SRL",
        "Super Smash SRL",
        "Caribbean Premier League SRL",
        "Big Bash League SRL",
    ]

    # Search entire page because section header may be
    # several lines above the match.
    body_lower = body_text.lower()

    for name in tournament_names:

        if name.lower() in body_lower:

            # Prefer tournament near the match.
            tournament = name

            break

    return {
        "teams": teams[:2],
        "tournament": tournament,
    }


# ============================================================
# TOSS IDENTIFIER
# ============================================================

def make_toss_id(
    toss
):

    raw = (
        f"{toss.get('winner','')}|"
        f"{toss.get('decision','')}|"
        f"{toss.get('fixture','')}"
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
    decision
):

    value = clean_text(
        decision
    ).lower()

    if value == "bat":

        return "Elected to bat"

    if value in {
        "bowl",
        "field",
    }:

        return "Elected to bowl"

    return value or "Not reported"


# ============================================================
# BUILD TOSS ALERT
# ============================================================

def build_toss_message(
    toss
):

    # --------------------------------------------------------
    # ALWAYS INDIA STANDARD TIME
    # --------------------------------------------------------

    now_ist = datetime.now(
        timezone.utc
    ).astimezone(
        ZoneInfo(
            "Asia/Kolkata"
        )
    )

    winner = toss[
        "winner"
    ]

    decision = format_decision(
        toss[
            "decision"
        ]
    )

    fixture = toss.get(
        "fixture",
        "",
    )

    tournament = toss.get(
        "tournament",
        "",
    )

    if not fixture:

        fixture = (
            f"{winner} vs SRL"
        )

    if not tournament:

        tournament = (
            "SRL Cricket"
        )

    return (
        "🏏 SRL TOSS ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🏆 {winner} WON THE TOSS\n\n"

        f"⚔️ {fixture}\n"
        f"🏆 {tournament}\n\n"

        f"🎯 Decision: {decision}\n"
        f"⏰ {now_ist.strftime('%d %b %Y | %H:%M:%S IST')}\n\n"

        "📡 Sportradar SRL Sportcentre\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# PROCESS TOSS
# ============================================================

def process_toss(
    toss
):

    if not validate_toss(
        toss
    ):

        return False

    identifier = make_toss_id(
        toss
    )

    if identifier in seen_tosses:

        return False

    log.info(
        "NEW SRL TOSS | winner=%s | decision=%s",
        toss["winner"],
        toss["decision"],
    )

    message = build_toss_message(
        toss
    )

    log.info(
        "Sending Telegram SRL toss alert..."
    )

    if not send_telegram(
        message
    ):

        log.error(
            "Telegram failed. Toss will be retried."
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
# EXTRACT AND PROCESS PAGE TOSSES
# ============================================================

def scan_for_tosses(
    body_text
):

    if not page_is_srl(
        body_text
    ):

        log.warning(
            "Page does not currently look like SRL Cricket."
        )

        return 0

    tosses = find_toss_sentences(
        body_text
    )

    if not tosses:

        return 0

    detected = 0

    for toss in tosses:

        winner = toss[
            "winner"
        ]

        context = find_match_context(
            body_text,
            winner,
        )

        teams = context.get(
            "teams",
            []
        )

        tournament = context.get(
            "tournament",
            ""
        )

        # ----------------------------------------------------
        # Build fixture.
        # ----------------------------------------------------

        if len(teams) >= 2:

            fixture = (
                f"{teams[0]} vs {teams[1]}"
            )

        else:

            fixture = ""

        enriched = {
            "winner": winner,
            "decision": toss[
                "decision"
            ],
            "fixture": fixture,
            "tournament": tournament,
        }

        log.info(
            "TOSS DETECTED | %s | %s | %s",
            winner,
            format_decision(
                toss["decision"]
            ),
            fixture or "fixture unknown",
        )

        if process_toss(
            enriched
        ):

            detected += 1

    return detected


# ============================================================
# MAIN
# ============================================================

def main():

    log.info(
        "%s STARTING",
        SYSTEM_VERSION,
    )

    # --------------------------------------------------------
    # Validate Telegram.
    # --------------------------------------------------------

    if not telegram_configured():

        log.error(
            "Telegram configuration missing."
        )

        log.error(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID "
            "in Railway Variables."
        )

        return

    log.info(
        "Telegram configuration detected."
    )

    # --------------------------------------------------------
    # Load duplicate state.
    # --------------------------------------------------------

    load_state()

    # --------------------------------------------------------
    # Start Chrome.
    # --------------------------------------------------------

    driver = None

    try:

        driver = create_driver()

        # ----------------------------------------------------
        # Open SRL page.
        # ----------------------------------------------------

        open_srl_page(
            driver
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

        last_refresh = time.monotonic()

        startup_scan = True

        while True:

            try:

                now = time.monotonic()

                # ------------------------------------------------
                # Refresh page periodically.
                # ------------------------------------------------

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
                            "Page refresh failed: %s",
                            exc,
                        )

                    time.sleep(
                        PAGE_LOAD_WAIT
                    )

                    last_refresh = now

                # ------------------------------------------------
                # Read rendered page.
                # ------------------------------------------------

                body_text = inspect_page(
                    driver,
                    initial=startup_scan,
                )

                startup_scan = False

                # ------------------------------------------------
                # Access Denied detection.
                # ------------------------------------------------

                if (
                    "access denied" in body_text.lower()
                    or
                    "you don't have permission" in body_text.lower()
                ):

                    log.error(
                        "SRL SPORTCENTRE ACCESS DENIED."
                    )

                    heartbeat(
                        "ACCESS DENIED"
                    )

                    time.sleep(
                        SCAN_INTERVAL
                    )

                    continue

                # ------------------------------------------------
                # Scan toss.
                # ------------------------------------------------

                found = scan_for_tosses(
                    body_text
                )

                if found:

                    log.info(
                        "New SRL toss alerts sent: %s",
                        found,
                    )

                heartbeat(
                    "ACTIVE"
                )

                time.sleep(
                    SCAN_INTERVAL
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

                time.sleep(
                    5
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

            except Exception:

                pass

        log.info(
            "SRL monitor stopped."
        )


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
