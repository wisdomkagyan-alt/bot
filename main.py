# ============================================================
# SRL TOSS MONITOR - INSTANT EDITION
#
# - In-page MutationObserver (browser pushes changes instantly)
# - Python drains the event queue every 20 ms
# - Telegram sends run in background threads (never block)
# - Persistent keep-alive connection to Telegram (no handshake)
# - Baseline + warm-up so old tosses never re-alert
# - Auto-restart of Chrome if the driver dies
# - Daily fixture board after 00:10 IST (once per day)
#
# Railway Variables REQUIRED:
#   TELEGRAM_BOT_TOKEN
#   TELEGRAM_CHAT_ID
# Optional:
#   CHROME_BINARY (default /usr/bin/chromium)
#   CHROMEDRIVER_PATH
# ============================================================

import json
import logging
import os
import re
import threading
import time

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


# ============================================================
# CONFIG
# ============================================================

SYSTEM_VERSION = "SRL-TOSS-INSTANT-2026"

SRL_URL = "https://sportcenter.sir.sportradar.com/pt/simulated-reality/cricket"

FAST_POLL = 0.02            # 20 ms queue drain
RELOAD_EVERY = 1800         # safety reload every 30 min
WARMUP_MS = 4000            # ignore initial render after load/reload
FIXTURE_CHECK_EVERY = 30    # seconds
KEEPALIVE_EVERY = 45        # seconds, keeps Telegram connection hot
DEDUP_WINDOW = 600          # same winner blocked for 10 min
MAX_CONSECUTIVE_ERRORS = 5
PAGE_LOAD_TIMEOUT = 30
REQUEST_TIMEOUT = 6

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8783763018").strip()

CHROME_BINARY = os.getenv("CHROME_BINARY", "/usr/bin/chromium").strip()
CHROMEDRIVER_PATH = os.getenv("CHROMEDRIVER_PATH", "").strip()

STATE_FILE = Path("seen_tosses.json")
DAILY_FIXTURE_STATE_FILE = Path("daily_fixture_state.json")
HEARTBEAT_FILE = Path("srl_toss_heartbeat.txt")
PROCESS_LOCK_FILE = Path("/tmp/srl_toss_monitor.lock")

seen_tosses = {}            # winner_key -> {"ts": float, "decision": str}
last_fixture_date_sent = ""

state_lock = threading.Lock()
fixture_lock = threading.Lock()
sender_pool = ThreadPoolExecutor(max_workers=4)
_process_lock_handle = None


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("SRL-TOSS")


# ============================================================
# HTTP (persistent keep-alive session)
# ============================================================

http = requests.Session()
http.mount(
    "https://",
    HTTPAdapter(pool_connections=4, pool_maxsize=8, max_retries=0),
)
http.headers.update({"user-agent": "SRL-Toss-Instant/2026"})


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""
    value = str(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("Could not read %s: %s", path, exc)
        return default


def save_json(path, data):
    try:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:
        log.error("Could not save %s: %s", path, exc)


def heartbeat(status):
    try:
        HEARTBEAT_FILE.write_text(
            f"{datetime.now(timezone.utc).isoformat()} | "
            f"{SYSTEM_VERSION} | {status}\n",
            encoding="utf-8",
        )
    except Exception:
        pass


def current_ist():
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(timezone.utc).astimezone(ist)


# ============================================================
# STATE
# ============================================================

def load_state():
    global seen_tosses
    data = load_json(STATE_FILE, {})
    seen_tosses = data if isinstance(data, dict) else {}
    log.info("Loaded %s seen toss records.", len(seen_tosses))


def save_state():
    with state_lock:
        cutoff = time.time() - 86400
        snapshot = {
            k: v for k, v in seen_tosses.items()
            if v.get("ts", 0) > cutoff
        }
    save_json(STATE_FILE, snapshot)


def load_daily_fixture_state():
    global last_fixture_date_sent
    data = load_json(DAILY_FIXTURE_STATE_FILE, {})
    last_fixture_date_sent = (
        str(data.get("last_date", "")) if isinstance(data, dict) else ""
    )


def save_daily_fixture_state(date_string):
    global last_fixture_date_sent
    last_fixture_date_sent = date_string
    save_json(DAILY_FIXTURE_STATE_FILE, {"last_date": date_string})


# ============================================================
# TELEGRAM
# ============================================================

def telegram_configured():
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_telegram(message):
    if not telegram_configured():
        log.error("Telegram credentials missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }

    for attempt in range(1, 4):
        try:
            r = http.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return True
            log.error("Telegram HTTP %s | %s", r.status_code, r.text[:300])
            if r.status_code == 429:
                try:
                    wait = r.json().get("parameters", {}).get("retry_after", 1)
                except Exception:
                    wait = 1
                time.sleep(min(float(wait), 5))
        except requests.RequestException as exc:
            log.error("Telegram attempt %s failed: %s", attempt, exc)
        time.sleep(0.3)
    return False


def telegram_keepalive():
    """Cheap call that keeps the TLS connection warm."""
    try:
        http.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe",
            timeout=REQUEST_TIMEOUT,
        )
    except Exception:
        pass


def startup_message():
    return (
        "🟢 SRL TOSS MONITOR ONLINE\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "🏏 SRL CRICKET ONLY\n"
        "📡 Sportradar SRL Sportcentre\n\n"
        "⚡ Mode: INSTANT (MutationObserver)\n"
        f"🔄 Queue drain: {int(FAST_POLL * 1000)} ms\n\n"
        "📡 Telegram: ACTIVE\n"
        "🛡 Duplicate protection: ACTIVE\n"
        "🎯 Toss detector: ACTIVE\n"
        "📋 Daily fixtures: ACTIVE\n"
        "🇮🇳 Time: IST\n\n"
        "Waiting for SRL toss..."
    )


# ============================================================
# CHROME
# ============================================================

def create_driver():
    log.info("Launching Chrome WebDriver...")

    options = Options()
    for arg in (
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-renderer-backgrounding",
        "--disable-features=Translate",
        "--blink-settings=imagesEnabled=false",
        "--lang=en-US",
        "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ):
        options.add_argument(arg)

    options.page_load_strategy = "eager"

    if CHROME_BINARY and Path(CHROME_BINARY).exists():
        options.binary_location = CHROME_BINARY
        log.info("Using Chrome binary: %s", CHROME_BINARY)
    elif CHROME_BINARY:
        log.warning("Chrome binary not found: %s", CHROME_BINARY)

    if CHROMEDRIVER_PATH:
        from selenium.webdriver.chrome.service import Service
        driver = webdriver.Chrome(
            service=Service(CHROMEDRIVER_PATH), options=options
        )
    else:
        driver = webdriver.Chrome(options=options)

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
    return driver


def open_page(driver):
    log.info("Opening SRL Cricket page...")
    try:
        driver.get(SRL_URL)
    except Exception as exc:
        log.warning("Page load warning: %s", exc)
    wait_ready(driver)
    try:
        log.info("Browser URL: %s | title: %s", driver.current_url, driver.title)
    except Exception:
        pass


def wait_ready(driver, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if driver.execute_script("return document.readyState") in (
                "interactive",
                "complete",
            ):
                return
        except Exception:
            pass
        time.sleep(0.1)


def get_page_text(driver):
    try:
        return driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        ) or ""
    except Exception as exc:
        log.warning("Could not read page DOM: %s", exc)
        return ""


# ============================================================
# IN-PAGE OBSERVER
#
# - Records existing toss sentences as baseline (no alert)
# - During warm-up, new sentences are recorded but not emitted
# - After warm-up, any NEW toss sentence is queued instantly
# - Same sentence is not re-emitted for 45 min
# ============================================================

OBSERVER_JS = """
if (!window.__srlObs) {
  window.__srlQ = [];
  window.__srlSeen = new Map();
  window.__srlWarmUntil = Date.now() + __WARMUP__;
  const RE = /([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\\sSRL)\\s+won\\s+the\\s+toss(?:\\s+and\\s+elected\\s+to\\s+(bat|bowl|field))?/gi;
  const TTL = 45 * 60 * 1000;

  const hasNew = (text) => {
    const txt = text.replace(/\\s+/g, ' ');
    const now = Date.now();
    let any = false, m;
    RE.lastIndex = 0;
    while ((m = RE.exec(txt)) !== null) {
      const sig = m[0].toLowerCase();
      const prev = window.__srlSeen.get(sig);
      if (prev === undefined || now - prev > TTL) {
        window.__srlSeen.set(sig, now);
        any = true;
      }
    }
    return any;
  };

  const check = (node) => {
    const el = node.nodeType === 1 ? node : node.parentElement;
    if (!el) return;
    const t = el.innerText || el.textContent || "";
    if (!/won the toss/i.test(t)) return;
    if (!hasNew(t)) return;
    if (Date.now() < window.__srlWarmUntil) return;
    const c = [t];
    let cur = el;
    for (let i = 0; i < 10 && cur.parentElement; i++) {
      cur = cur.parentElement;
      const pt = cur.innerText || "";
      if (pt.length > 1200) break;
      c.push(pt);
    }
    window.__srlQ.push(c);
  };

  // Baseline: everything already on the page
  try { hasNew(document.body ? document.body.innerText : ""); } catch (e) {}

  window.__srlObs = new MutationObserver((muts) => {
    for (const m of muts) {
      if (m.type === 'characterData') { check(m.target); }
      m.addedNodes.forEach(check);
    }
  });
  window.__srlObs.observe(document.documentElement,
    { childList: true, subtree: true, characterData: true });
}
const q = window.__srlQ;
window.__srlQ = [];
return q;
""".replace("__WARMUP__", str(WARMUP_MS))


def drain_events(driver):
    return driver.execute_script(OBSERVER_JS) or []


# ============================================================
# TEAM / TOSS PARSING
# ============================================================

def is_srl_team(name):
    return clean_text(name).lower().endswith(" srl")


def clean_team_name(value):
    value = clean_text(value)
    value = re.sub(
        r"^\d+(?:\.\d+)?\s*(?:OV|OVERS?)\s+", "", value, flags=re.IGNORECASE
    )
    value = re.sub(r"^\d+(?:/\d+)?\s+", "", value)
    return clean_text(value)


TEAM_RE = re.compile(r"\b([A-ZÀ-Ý][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)\b")


def extract_srl_teams(value):
    value = clean_text(value)
    found = []
    for match in TEAM_RE.finditer(value):
        team = clean_team_name(match.group(1))
        if is_srl_team(team) and team not in found:
            found.append(team)
    return found


def extract_fixture(value):
    value = clean_text(value)
    if not value:
        return "", ""

    pos = value.lower().find("won the toss")
    before = value[:pos] if pos >= 0 else value

    teams = extract_srl_teams(before)
    if len(teams) >= 2:
        team2 = teams[-1]
        remaining = [x for x in teams[:-1] if x.lower() != team2.lower()]
        if remaining:
            return remaining[-1], team2

    teams = extract_srl_teams(value)
    unique = []
    seen = set()
    for t in teams:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique.append(t)
    if len(unique) >= 2:
        return unique[-2], unique[-1]
    return "", ""


TOSS_RE = re.compile(
    r"([A-Za-zÀ-ÿ0-9][A-Za-zÀ-ÿ0-9 .&'_-]*?\sSRL)"
    r"\s+won\s+the\s+toss"
    r"(?:\s+and\s+elected\s+to\s+(bat|bowl|field))?",
    re.IGNORECASE,
)


def parse_toss(sentence):
    sentence = clean_text(sentence)
    if not sentence or "won the toss" not in sentence.lower():
        return None

    matches = list(TOSS_RE.finditer(sentence))
    if not matches:
        return None

    m = matches[-1]
    winner = clean_team_name(m.group(1))
    decision = clean_text(m.group(2) or "").lower()
    if not is_srl_team(winner):
        return None

    team1, team2 = extract_fixture(sentence)
    return {
        "winner": winner,
        "decision": decision,
        "team1": team1,
        "team2": team2,
    }


def pick_toss(candidates):
    """Smallest text gives the cleanest winner; larger text fills teams."""
    texts = sorted({clean_text(c) for c in candidates if c}, key=len)
    result = None
    for text in texts:
        toss = parse_toss(text)
        if not toss:
            continue
        if result is None:
            result = toss
        else:
            if not result["decision"] and toss["decision"]:
                result["decision"] = toss["decision"]
            if toss["team1"] and toss["team2"] and not (
                result["team1"] and result["team2"]
            ):
                result["team1"], result["team2"] = toss["team1"], toss["team2"]
        if result["team1"] and result["team2"] and result["decision"]:
            break
    return result


# ============================================================
# TOSS MESSAGE
# ============================================================

def format_decision(decision):
    value = clean_text(decision).lower()
    if value == "bat":
        return "Elected to bat"
    if value in {"bowl", "field"}:
        return "Elected to bowl"
    return "Not reported"


def build_toss_message(toss):
    now = current_ist()
    team1, team2 = toss.get("team1", ""), toss.get("team2", "")
    fixture_text = f"{team1} vs {team2}" if team1 and team2 else "SRL Match"

    return (
        f"🏆 {toss['winner']} WON THE TOSS\n\n"
        f"🎯 {format_decision(toss.get('decision', ''))}\n"
        f"⚔️ {fixture_text}\n"
        f"⏰ {now.strftime('%d %b %Y | %H:%M:%S IST')}\n\n"
        "🏏 SRL TOSS ALERT\n"
        "📡 Sportradar SRL Sportcentre\n"
        "🔔 LIVE TOSS MONITOR"
    )


# ============================================================
# PROCESS TOSS (runs in background thread)
#
# - claims the winner under a lock BEFORE sending
# - allows ONE follow-up alert if the first had no decision
# ============================================================

def process_toss(toss):
    detected = time.perf_counter()

    winner = clean_team_name(toss.get("winner", ""))
    if not winner or not is_srl_team(winner):
        return False

    toss["winner"] = winner
    toss["decision"] = clean_text(toss.get("decision", "")).lower()
    toss["team1"] = clean_team_name(toss.get("team1", ""))
    toss["team2"] = clean_team_name(toss.get("team2", ""))

    key = winner.lower()
    now = time.time()

    with state_lock:
        previous = seen_tosses.get(key)
        if previous and now - previous.get("ts", 0) < DEDUP_WINDOW:
            upgrade = (not previous.get("decision")) and toss["decision"]
            if not upgrade:
                log.info("🔒 DUPLICATE BLOCKED | %s", winner)
                return False
        seen_tosses[key] = {"ts": now, "decision": toss["decision"]}

    log.info(
        "🔥 NEW SRL TOSS | winner=%s | decision=%s | %s vs %s",
        winner,
        toss["decision"] or "-",
        toss["team1"] or "SRL",
        toss["team2"] or "Match",
    )

    ok = send_telegram(build_toss_message(toss))

    if not ok:
        with state_lock:
            if previous is None:
                seen_tosses.pop(key, None)
            else:
                seen_tosses[key] = previous
        log.error("❌ Telegram failed. Unlocked for retry.")
        return False

    log.info(
        "✅ ALERT SENT | %s | %.0f ms after detection",
        winner,
        (time.perf_counter() - detected) * 1000,
    )
    save_state()
    return True


# ============================================================
# DAILY FIXTURES
# ============================================================

LEAGUES = [
    "Pakistan Super League SRL",
    "SA20 SRL",
    "T20 International SRL",
    "Super Smash SRL",
    "Indian Premier League SRL",
]

TIME_RE = re.compile(
    r"\b\d{1,2}\s+[A-Za-zÀ-ÿ]{3}\s*\|\s*(\d{1,2}):(\d{2})\b"
)


def parse_daily_fixtures(page_text):
    lines = [
        clean_text(x) for x in page_text.splitlines() if clean_text(x)
    ]
    fixtures = []
    current_league = ""

    for i, line in enumerate(lines):
        for league in LEAGUES:
            if line.lower() == league.lower():
                current_league = league
                break

        m = TIME_RE.search(line)
        if not m or not current_league or i == 0 or i + 1 >= len(lines):
            continue

        team1 = clean_team_name(lines[i - 1])
        team2 = clean_team_name(lines[i + 1])
        if not (is_srl_team(team1) and is_srl_team(team2)):
            continue

        hour, minute = int(m.group(1)), int(m.group(2))
        fixtures.append(
            {
                "league": current_league,
                "team1": team1,
                "team2": team2,
                "time": f"{hour:02d}:{minute:02d}",
                "sort_time": hour * 60 + minute,
            }
        )
    return fixtures


def build_daily_fixture_message(page_text):
    now = current_ist()
    fixtures = parse_daily_fixtures(page_text)
    if not fixtures:
        log.warning("No SRL fixtures found for daily schedule.")
        return None

    unique = {}
    for f in fixtures:
        key = (f["league"].lower(), f["team1"].lower(),
               f["team2"].lower(), f["time"])
        unique[key] = f

    grouped = {}
    for f in unique.values():
        grouped.setdefault(f["league"], []).append(f)
    for league in grouped:
        grouped[league].sort(key=lambda x: x["sort_time"])

    message = f"🏏 SRL FIXTURES\n📅 {now.strftime('%d %b %Y').upper()}"
    for league, items in grouped.items():
        message += f"\n\n🏆 {league.upper()}\n"
        for f in items:
            message += (
                f"\n⏰ {f['time']}\n{f['team1']}\nvs\n{f['team2']}\n"
            )
    return message.rstrip()


def maybe_send_daily_fixtures(page_text):
    """Runs in a background thread; never blocks toss detection."""
    if not fixture_lock.acquire(blocking=False):
        return
    try:
        now = current_ist()
        today = now.strftime("%Y-%m-%d")

        if now.hour * 60 + now.minute < 10:
            return
        if last_fixture_date_sent == today:
            return

        message = build_daily_fixture_message(page_text)
        if not message:
            return

        log.info("📋 Sending daily SRL fixture schedule...")
        if send_telegram(message):
            save_daily_fixture_state(today)
            log.info("✅ Daily fixtures sent | %s", today)
        else:
            log.error("Daily fixtures failed. Will retry.")
    finally:
        fixture_lock.release()


# ============================================================
# SINGLE PROCESS LOCK
# ============================================================

def acquire_process_lock():
    global _process_lock_handle
    try:
        import fcntl
        _process_lock_handle = open(PROCESS_LOCK_FILE, "w")
        fcntl.flock(
            _process_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB
        )
        _process_lock_handle.write(str(os.getpid()))
        _process_lock_handle.flush()
        log.info("🔒 Single-process lock acquired | PID=%s", os.getpid())
        return True
    except BlockingIOError:
        log.error("❌ Another SRL monitor is already running.")
        return False
    except Exception as exc:
        log.error("Process lock error: %s", exc)
        return False


def release_process_lock():
    global _process_lock_handle
    if _process_lock_handle is None:
        return
    try:
        import fcntl
        fcntl.flock(_process_lock_handle.fileno(), fcntl.LOCK_UN)
        _process_lock_handle.close()
    except Exception:
        pass
    _process_lock_handle = None


# ============================================================
# MONITOR LOOP
#
# Returns "restart" if Chrome seems dead (caller rebuilds it).
# ============================================================

def monitor(driver):
    last_reload = time.monotonic()
    last_fixture = 0.0
    last_keepalive = time.monotonic()
    errors = 0

    while True:
        try:
            events = drain_events(driver)
            errors = 0

            for candidates in events:
                toss = pick_toss(candidates)
                if toss:
                    sender_pool.submit(process_toss, toss)

            now = time.monotonic()

            if now - last_fixture > FIXTURE_CHECK_EVERY:
                last_fixture = now
                text = get_page_text(driver)
                sender_pool.submit(maybe_send_daily_fixtures, text)

            if now - last_keepalive > KEEPALIVE_EVERY:
                last_keepalive = now
                sender_pool.submit(telegram_keepalive)

            if now - last_reload > RELOAD_EVERY:
                log.info("Safety reload...")
                try:
                    driver.refresh()
                except Exception as exc:
                    log.warning("Refresh warning: %s", exc)
                wait_ready(driver)
                last_reload = time.monotonic()
                # observer re-installs itself on the next drain,
                # with a fresh baseline + warm-up window

            heartbeat("ACTIVE")
            time.sleep(FAST_POLL)

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            errors += 1
            log.error("Monitor error %s/%s: %s",
                      errors, MAX_CONSECUTIVE_ERRORS, exc)
            heartbeat("ERROR - RECOVERING")
            if errors >= MAX_CONSECUTIVE_ERRORS:
                return "restart"
            time.sleep(0.5)


# ============================================================
# MAIN
# ============================================================

def main():
    log.info("%s STARTING", SYSTEM_VERSION)

    if not acquire_process_lock():
        return

    if not telegram_configured():
        log.error(
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in Railway Variables."
        )
        release_process_lock()
        return

    load_state()
    load_daily_fixture_state()
    telegram_keepalive()  # open the TLS connection now

    if send_telegram(startup_message()):
        log.info("Startup Telegram message sent.")

    driver = None
    try:
        while True:
            try:
                driver = create_driver()
                open_page(driver)
                drain_events(driver)  # install observer + baseline now
                result = monitor(driver)
                log.warning("Monitor returned: %s. Restarting Chrome.", result)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                log.exception("Driver error: %s", exc)
                heartbeat("DRIVER ERROR")
            finally:
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    driver = None
            time.sleep(3)

    except KeyboardInterrupt:
        log.info("Stopped by user.")
        heartbeat("STOPPED")
    finally:
        sender_pool.shutdown(wait=False)
        release_process_lock()


if __name__ == "__main__":
    main()
