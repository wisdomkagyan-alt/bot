# ============================================================
# SRL TOSS API MONITOR 2026
#
# Sportradar Cricket API -> Telegram
#
# SRL CRICKET ONLY
#
# No Playwright
# No Chromium
# No webpage scraping
#
# Railway Variables:
#
#   SPORTRADAR_API_KEY
#   SPORTRADAR_ACCESS_LEVEL
#   TELEGRAM_BOT_TOKEN
#   TELEGRAM_CHAT_ID
#
# ============================================================

import hashlib
import json
import logging
import os
import time

from datetime import datetime, timezone
from pathlib import Path

import requests


# ============================================================
# CONFIGURATION
# ============================================================

SYSTEM_VERSION = "SRL-TOSS-API-MONITOR-2026"


# NEVER hard-code credentials.
SPORTRADAR_API_KEY = os.getenv(
    "SPORTRADAR_API_KEY",
    "91cAuMjzEUOfHnWuYqa3f0UBgfEipHGLnTeY1ypS",
).strip()


TELEGRAM_BOT_TOKEN = os.getenv(
    "TELEGRAM_BOT_TOKEN",
    "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU",
).strip()


TELEGRAM_CHAT_ID = os.getenv(
    "TELEGRAM_CHAT_ID",
    "8783763018",
).strip()


# ============================================================
# SPORTRADAR SETTINGS
# ============================================================

# t = trial
# p = production

SPORTRADAR_ACCESS_LEVEL = os.getenv(
    "SPORTRADAR_ACCESS_LEVEL",
    "t",
).strip().lower()


if SPORTRADAR_ACCESS_LEVEL not in {
    "t",
    "p",
}:
    SPORTRADAR_ACCESS_LEVEL = "t"


LANGUAGE = "en"

FORMAT = "json"


API_BASE = (
    "https://api.sportradar.com/"
    f"cricket-{SPORTRADAR_ACCESS_LEVEL}2/"
    f"{LANGUAGE}"
)


# ============================================================
# MONITOR SETTINGS
# ============================================================

# Refresh live schedule every 10 seconds.
SCHEDULE_INTERVAL = 10


# Check accepted SRL match summaries every 2 seconds.
SUMMARY_INTERVAL = 2


REQUEST_TIMEOUT = 15


# ============================================================
# STATE FILES
# ============================================================

STATE_FILE = Path(
    "seen_tosses.json"
)


MATCH_STATE_FILE = Path(
    "known_matches.json"
)


HEARTBEAT_FILE = Path(
    "srl_toss_heartbeat.txt"
)


# ============================================================
# SRL CRICKET ONLY
# ============================================================

SRL_KEYWORDS = (
    "simulated reality",
    "simulated reality league",
    "srl cricket",
)


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
    "SRL-TOSS-API"
)


# ============================================================
# HTTP SESSION
# ============================================================

http = requests.Session()

http.headers.update(
    {
        "accept": "application/json",
        "user-agent": (
            "SRL-Toss-Monitor/2026"
        ),
    }
)


# ============================================================
# STATE
# ============================================================

seen_tosses = set()

known_matches = {}


# ============================================================
# JSON LOAD
# ============================================================

def load_json_file(
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

def save_json_file(
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
    global known_matches

    toss_data = load_json_file(
        STATE_FILE,
        [],
    )

    if isinstance(
        toss_data,
        list,
    ):

        seen_tosses = {
            str(x)
            for x in toss_data
        }

    else:

        seen_tosses = set()


    match_data = load_json_file(
        MATCH_STATE_FILE,
        {},
    )

    if isinstance(
        match_data,
        dict,
    ):

        known_matches = match_data

    else:

        known_matches = {}


    log.info(
        "Loaded %s seen toss IDs",
        len(seen_tosses),
    )

    log.info(
        "Loaded %s known matches",
        len(known_matches),
    )


# ============================================================
# SAVE STATE
# ============================================================

def save_state():

    save_json_file(
        STATE_FILE,
        sorted(seen_tosses),
    )

    save_json_file(
        MATCH_STATE_FILE,
        known_matches,
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
# SEND TELEGRAM
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


        except Exception as exc:

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
        "🟢 SRL TOSS API MONITOR ONLINE\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        "🏏 SRL CRICKET ONLY\n"
        "📡 Sportradar Cricket API\n\n"

        "⚡ Live schedule monitoring\n"
        f"🔄 Schedule: {SCHEDULE_INTERVAL}s\n"
        f"⚡ Toss check: {SUMMARY_INTERVAL}s\n\n"

        "📡 Telegram: ACTIVE\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🎯 SRL filter: ACTIVE\n\n"

        "Waiting for SRL toss data..."
    )


# ============================================================
# API GET
# ============================================================

def api_get(
    path,
    params=None,
):

    url = (
        f"{API_BASE}{path}"
    )


    headers = {
        "accept": "application/json",
        "x-api-key": SPORTRADAR_API_KEY,
    }


    try:

        response = http.get(
            url,
            headers=headers,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )


    except requests.RequestException as exc:

        log.error(
            "Sportradar request failed: %s",
            exc,
        )

        return None


    if response.status_code != 200:

        log.error(
            "Sportradar HTTP %s | %s",
            response.status_code,
            response.text[:1000],
        )

        return None


    try:

        return response.json()


    except ValueError as exc:

        log.error(
            "Invalid Sportradar JSON: %s",
            exc,
        )

        return None


# ============================================================
# STRING HELPER
# ============================================================

def text(
    value,
):

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# TEAM EXTRACTION
# ============================================================

def extract_team_names(
    event,
):

    if not isinstance(
        event,
        dict,
    ):

        return []


    competitors = event.get(
        "competitors",
        [],
    )


    names = []


    if not isinstance(
        competitors,
        list,
    ):

        return names


    for competitor in competitors:

        if not isinstance(
            competitor,
            dict,
        ):

            continue


        name = (
            competitor.get("name")
            or competitor.get(
                "display_name"
            )
            or competitor.get(
                "short_name"
            )
        )


        if name:

            names.append(
                text(name)
            )


    return names


# ============================================================
# EVENT METADATA
# ============================================================

def extract_event_metadata(
    event,
):

    if not isinstance(
        event,
        dict,
    ):

        return {
            "tournament_name": "",
            "tournament_id": "",
            "category_name": "",
            "category_id": "",
            "season_name": "",
            "season_id": "",
            "sport_name": "",
            "sport_id": "",
        }


    tournament = event.get(
        "tournament",
        {},
    )


    if not isinstance(
        tournament,
        dict,
    ):

        tournament = {}


    category = tournament.get(
        "category",
        {},
    )


    if not isinstance(
        category,
        dict,
    ):

        category = {}


    sport = tournament.get(
        "sport",
        {},
    )


    if not isinstance(
        sport,
        dict,
    ):

        sport = {}


    season = event.get(
        "season",
        {},
    )


    if not isinstance(
        season,
        dict,
    ):

        season = {}


    return {
        "tournament_name": text(
            tournament.get("name")
        ),

        "tournament_id": text(
            tournament.get("id")
        ),

        "category_name": text(
            category.get("name")
        ),

        "category_id": text(
            category.get("id")
        ),

        "season_name": text(
            season.get("name")
        ),

        "season_id": text(
            season.get("id")
        ),

        "sport_name": text(
            sport.get("name")
        ),

        "sport_id": text(
            sport.get("id")
        ),
    }


# ============================================================
# SRL DETECTION
# ============================================================

def is_srl_event(
    event,
):

    if not isinstance(
        event,
        dict,
    ):

        return False


    metadata = extract_event_metadata(
        event
    )


    teams = extract_team_names(
        event
    )


    values = [
        metadata["tournament_name"],
        metadata["category_name"],
        metadata["season_name"],
        *teams,
    ]


    combined = " ".join(
        values
    ).lower()


    # --------------------------------------------------------
    # Must be cricket.
    # --------------------------------------------------------

    sport_name = (
        metadata["sport_name"]
        .lower()
    )


    sport_id = (
        metadata["sport_id"]
        .lower()
    )


    if (
        sport_name
        and "cricket" not in sport_name
    ):

        return False


    # --------------------------------------------------------
    # Explicit SRL identifiers.
    # --------------------------------------------------------

    for keyword in SRL_KEYWORDS:

        if keyword in combined:

            return True


    # --------------------------------------------------------
    # Log why an event was rejected.
    # --------------------------------------------------------

    return False


# ============================================================
# EXTRACT SCHEDULE EVENTS
# ============================================================

def extract_schedule_events(
    payload,
):

    if not isinstance(
        payload,
        dict,
    ):

        return []


    events = []


    sport_events = payload.get(
        "sport_events"
    )


    if isinstance(
        sport_events,
        list,
    ):

        events.extend(
            sport_events
        )


    sport_event = payload.get(
        "sport_event"
    )


    if isinstance(
        sport_event,
        dict,
    ):

        events.append(
            sport_event
        )


    return events


# ============================================================
# DISCOVER SRL MATCHES
# ============================================================

def discover_live_matches():

    log.info(
        "Requesting Sportradar Daily Live Schedule..."
    )


    payload = api_get(
        "/schedules/live/schedule.json"
    )


    if payload is None:

        return []


    events = extract_schedule_events(
        payload
    )


    log.info(
        "Live schedule returned %s events",
        len(events),
    )


    matches = []


    for event in events:

        if not isinstance(
            event,
            dict,
        ):

            continue


        event_id = text(
            event.get("id")
        )


        if not event_id:

            continue


        teams = extract_team_names(
            event
        )


        metadata = extract_event_metadata(
            event
        )


        # ----------------------------------------------------
        # RAW EVENT LOG
        # ----------------------------------------------------

        log.info(
            "LIVE EVENT | id=%s | "
            "teams=%s | "
            "sport=%s | "
            "tournament=%s | "
            "category=%s | "
            "season=%s",
            event_id,
            " vs ".join(teams),
            metadata["sport_name"],
            metadata["tournament_name"],
            metadata["category_name"],
            metadata["season_name"],
        )


        # ----------------------------------------------------
        # SRL CRICKET ONLY
        # ----------------------------------------------------

        if not is_srl_event(event):

            log.info(
                "SKIP NON-SRL | id=%s | teams=%s",
                event_id,
                " vs ".join(teams),
            )

            continue


        # ----------------------------------------------------
        # SRL ACCEPTED
        # ----------------------------------------------------

        log.info(
            "SRL MATCH ACCEPTED | "
            "id=%s | teams=%s | tournament=%s",
            event_id,
            " vs ".join(teams),
            metadata["tournament_name"],
        )


        record = {
            "id": event_id,

            "scheduled": text(
                event.get("scheduled")
            ),

            "teams": teams,

            "tournament": metadata[
                "tournament_name"
            ],

            "category": metadata[
                "category_name"
            ],

            "season": metadata[
                "season_name"
            ],
        }


        known_matches[event_id] = record

        matches.append(record)


    if matches:

        save_state()


    log.info(
        "SRL-filtered matches: %s",
        len(matches),
    )


    return matches


# ============================================================
# MATCH SUMMARY
# ============================================================

def get_match_summary(
    match_id,
):

    return api_get(
        f"/matches/{match_id}/summary.json"
    )


# ============================================================
# FIND NESTED VALUE
# ============================================================

def find_value(
    obj,
    target_key,
):

    if isinstance(
        obj,
        dict,
    ):

        if target_key in obj:

            return obj[target_key]


        for value in obj.values():

            result = find_value(
                value,
                target_key,
            )


            if result is not None:

                return result


    elif isinstance(
        obj,
        list,
    ):

        for item in obj:

            result = find_value(
                item,
                target_key,
            )


            if result is not None:

                return result


    return None


# ============================================================
# COMPETITOR MAP
# ============================================================

def build_competitor_map(
    payload,
):

    result = {}


    def walk(obj):

        if isinstance(
            obj,
            dict,
        ):

            competitor_id = obj.get(
                "id"
            )


            name = (
                obj.get("name")
                or obj.get(
                    "display_name"
                )
                or obj.get(
                    "short_name"
                )
            )


            if (
                competitor_id
                and name
                and str(
                    competitor_id
                ).startswith(
                    "sr:competitor:"
                )
            ):

                result[
                    str(competitor_id)
                ] = text(name)


            for value in obj.values():

                walk(value)


        elif isinstance(
            obj,
            list,
        ):

            for item in obj:

                walk(item)


    walk(payload)


    return result


# ============================================================
# EXTRACT TOSS
# ============================================================

def extract_toss(
    payload,
    match_id,
):

    if not isinstance(
        payload,
        dict,
    ):

        return None


    toss_won_by = find_value(
        payload,
        "toss_won_by",
    )


    toss_decision = find_value(
        payload,
        "toss_decision",
    )


    # No toss yet.
    if not toss_won_by:

        return None


    competitor_map = (
        build_competitor_map(
            payload
        )
    )


    winner_id = str(
        toss_won_by
    )


    winner_name = (
        competitor_map.get(
            winner_id
        )
    )


    if not winner_name:

        winner_name = winner_id


    return {
        "match_id": match_id,
        "winner_id": winner_id,
        "winner_name": winner_name,
        "decision": text(
            toss_decision
        ),
    }


# ============================================================
# TOSS ID
# ============================================================

def make_toss_id(
    toss,
):

    raw = (
        f"{toss['match_id']}|"
        f"{toss['winner_id']}|"
        f"{toss['decision']}"
    )


    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:32]


# ============================================================
# DECISION FORMAT
# ============================================================

def format_decision(
    decision,
):

    value = text(
        decision
    ).lower()


    decision_map = {
        "bat": "Elected to bat",
        "bowl": "Elected to bowl",
        "field": "Elected to field",
    }


    return decision_map.get(
        value,
        decision or "Not reported",
    )


# ============================================================
# TOSS MESSAGE
# ============================================================

def build_toss_message(
    toss,
):

    # ALWAYS UTC.
    now = datetime.now(
        timezone.utc
    )


    match = known_matches.get(
        toss["match_id"],
        {},
    )


    teams = match.get(
        "teams",
        [],
    )


    tournament = match.get(
        "tournament",
        "",
    )


    fixture = (
        " vs ".join(teams)
        if teams
        else "SRL Match"
    )


    decision_text = format_decision(
        toss["decision"]
    )


    return (
        "🏏 SRL TOSS ALERT\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"

        f"🏆 {toss['winner_name']} "
        "WON THE TOSS\n\n"

        f"⚔️ {fixture}\n"
        f"🏆 {tournament or 'SRL Cricket'}\n\n"

        f"🎯 Decision: {decision_text}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S UTC')}\n\n"

        "📡 Sportradar Cricket API\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# PROCESS TOSS
# ============================================================

def process_toss(
    toss,
):

    identifier = make_toss_id(
        toss
    )


    if identifier in seen_tosses:

        return False


    log.info(
        "NEW SRL TOSS | "
        "%s | %s | %s",
        toss["match_id"],
        toss["winner_name"],
        toss["decision"],
    )


    message = build_toss_message(
        toss
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
        "SRL TOSS TELEGRAM ALERT SENT."
    )


    return True


# ============================================================
# CHECK ONE MATCH
# ============================================================

def check_match(
    match,
):

    match_id = match.get(
        "id"
    )


    if not match_id:

        return


    payload = get_match_summary(
        match_id
    )


    if payload is None:

        return


    toss = extract_toss(
        payload,
        match_id,
    )


    if toss is None:

        return


    process_toss(
        toss
    )


# ============================================================
# CHECK ALL SRL MATCHES
# ============================================================

def check_all_matches():

    if not known_matches:

        return


    matches = list(
        known_matches.values()
    )


    for match in matches:

        try:

            check_match(
                match
            )


        except Exception as exc:

            log.exception(
                "Match check failed %s: %s",
                match.get("id"),
                exc,
            )


# ============================================================
# API TEST
# ============================================================

def test_api():

    if not SPORTRADAR_API_KEY:

        log.error(
            "SPORTRADAR_API_KEY is missing."
        )

        return False


    log.info(
        "Testing Sportradar Cricket API..."
    )


    payload = api_get(
        "/schedules/live/schedule.json"
    )


    if payload is None:

        log.error(
            "Sportradar API test FAILED."
        )

        return False


    log.info(
        "Sportradar API connection OK."
    )


    return True


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

    if not SPORTRADAR_API_KEY:

        log.error(
            "SPORTRADAR_API_KEY is not configured."
        )

        return


    if not telegram_configured():

        log.error(
            "Telegram configuration missing."
        )

        return


    log.info(
        "Sportradar API configuration detected."
    )


    log.info(
        "Telegram configuration detected."
    )


    # --------------------------------------------------------
    # Load state
    # --------------------------------------------------------

    load_state()


    # --------------------------------------------------------
    # API test
    # --------------------------------------------------------

    if not test_api():

        log.error(
            "Stopping because Sportradar API "
            "could not be accessed."
        )

        return


    # --------------------------------------------------------
    # Startup Telegram
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # Main loop
    # --------------------------------------------------------

    last_schedule_check = 0


    while True:

        try:

            now = time.monotonic()


            # ------------------------------------------------
            # Refresh live schedule
            # ------------------------------------------------

            if (
                now
                - last_schedule_check
                >= SCHEDULE_INTERVAL
            ):

                discover_live_matches()

                last_schedule_check = now


            # ------------------------------------------------
            # Check SRL match summaries
            # ------------------------------------------------

            check_all_matches()


            heartbeat(
                "ACTIVE"
            )


            time.sleep(
                SUMMARY_INTERVAL
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
                "Main loop error: %s",
                exc,
            )


            heartbeat(
                "ERROR - RECOVERING"
            )


            time.sleep(5)


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
