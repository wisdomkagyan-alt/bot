# ============================================================
# PEPPERSTONE PRICE ACTION HUNTER
# PA-SUPREME-2026 — ADVANCE PRICE-ACTION EDITION
#
# 1H  = LOCATION / MARKET STRUCTURE
# 15M = LIQUIDITY / BOS / CHOCH
# 5M  = ENTRY TRIGGER
#
# NEW:
#   1) ADVANCE PRE-SIGNAL before price reaches the zone
#   2) WATCH signal when liquidity/structure is forming
#   3) TRADE signal only after 5M confirmation
#   4) Adaptive TP from real 5M/15M/1H structure
#   5) RR can expand from 1.80R up to 4.00R
#   6) Avoids late "price already moved away" entries
#   7) 1-second decision loop, with cached market-data refresh
#
# IMPORTANT:
#   Yahoo Finance is NOT a broker-grade tick feed.
#   The loop can scan every second, but Yahoo data only changes
#   when fresh candles/quotes are returned. For true tick/live
#   execution, replace fetch_market_data() with the broker/MT5
#   native feed.
#
# TELEGRAM:
#   TOKEN and CHAT_ID are environment variables.
#   Do NOT hard-code a bot token in source code.
# ============================================================

import csv
import gc
import logging
import math
import os
import time
from datetime import datetime, timezone
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import yfinance as yf

SYSTEM_VERSION = "PA-SUPREME-2026-ADVANCE"

# ============================================================
# SECURITY
# ============================================================
TOKEN = os.getenv("TOKEN", "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")

# ============================================================
# LOGGING
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("PA-SUPREME-2026")

http = requests.Session()
signal_lock = Lock()
log_lock = Lock()

# ============================================================
# MARKETS
# ============================================================
PRIORITY_MARKETS = [
    "XAU/USD", "NAS100", "SPX500", "EUR/USD", "GBP/JPY",
    "NIFTY50", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS",
]

MARKETS = {
    "XAU/USD": {
        "data": "GC=F", "execution": "XAUUSD.Qraw", "decimals": 2,
        "market_type": "global", "min_sl": 1.50,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["Asian Precision", "London", "NY+London", "NY Killzone"],
    },
    "NAS100": {
        "data": "^NDX", "execution": "NAS100", "decimals": 1,
        "market_type": "global", "min_sl": 12.0,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["London", "NY+London", "NY Killzone"],
    },
    "SPX500": {
        "data": "^GSPC", "execution": "SPX500", "decimals": 1,
        "market_type": "global", "min_sl": 6.0,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["London", "NY+London", "NY Killzone"],
    },
    "EUR/USD": {
        "data": "EURUSD=X", "execution": "EURUSD", "decimals": 5,
        "market_type": "global", "min_sl": 0.00025,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["Asian Precision", "London", "NY+London", "NY Killzone"],
    },
    "GBP/JPY": {
        "data": "GBPJPY=X", "execution": "GBPJPY", "decimals": 3,
        "market_type": "global", "min_sl": 0.040,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["Asian Precision", "London", "NY+London", "NY Killzone"],
    },
    "NIFTY50": {
        "data": "^NSEI", "execution": "NIFTY50", "decimals": 2,
        "market_type": "india", "min_sl": 15.0,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "BANKNIFTY": {
        "data": "^NSEBANK", "execution": "BANKNIFTY", "decimals": 2,
        "market_type": "india", "min_sl": 20.0,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "SENSEX": {
        "data": "^BSESN", "execution": "SENSEX", "decimals": 2,
        "market_type": "india", "min_sl": 40.0,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "RELIANCE": {
        "data": "RELIANCE.NS", "execution": "RELIANCE", "decimals": 2,
        "market_type": "india", "min_sl": 5.0,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "TCS": {
        "data": "TCS.NS", "execution": "TCS", "decimals": 2,
        "market_type": "india", "min_sl": 8.0,
        "sl_buffer": 0.10, "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
}

# ============================================================
# RISK
# ============================================================
RISK_PER_TRADE = 50.0

DOLLAR_PER_POINT = {
    "XAU/USD": 100, "NAS100": 10, "SPX500": 10, "EUR/USD": 100000,
    "GBP/JPY": 1000, "NIFTY50": 50, "BANKNIFTY": 20, "SENSEX": 10,
    "RELIANCE": 1, "TCS": 1,
}

LOT_CAP = {
    "XAU/USD": 1.50, "NAS100": 2.00, "SPX500": 2.00,
    "EUR/USD": 3.00, "GBP/JPY": 2.00, "NIFTY50": 50.0,
    "BANKNIFTY": 50.0, "SENSEX": 50.0, "RELIANCE": 500.0, "TCS": 500.0,
}

EXECUTION_BUFFER = {
    "XAU/USD": 0.15, "NAS100": 1.50, "SPX500": 1.00,
    "EUR/USD": 0.00005, "GBP/JPY": 0.010,
    "NIFTY50": 1.00, "BANKNIFTY": 2.00, "SENSEX": 3.00,
    "RELIANCE": 0.50, "TCS": 0.50,
}

MAX_DAILY_LOSS = -300.0
MAX_CONSECUTIVE_LOSSES = 3

# ============================================================
# PRICE ACTION SETTINGS
# ============================================================
SWING_LEFT = 2
SWING_RIGHT = 2

ZONE_LOOKBACK_1H = 80
LIQUIDITY_LOOKBACK = 8
BOS_LOOKBACK = 5

REJECTION_WICK_RATIO = 1.30
DISPLACEMENT_BODY_MULT = 1.20

ZONE_TOLERANCE_ATR = 0.35
RETEST_TOLERANCE_ATR = 0.25

MIN_PA_SCORE = 8
MIN_RR = 1.80
MAX_RR = 4.00

# Advance warning distance from the 1H zone.
PRE_SIGNAL_ATR = 0.75

# Do not send the same pre-alert repeatedly.
PRE_SIGNAL_COOLDOWN = 900
TRADE_SIGNAL_COOLDOWN = 900
WATCH_COOLDOWN = 600

# One actual trade signal per symbol/session.
SIGNAL_ONE_PER_SESSION = True

# Fast decision loop. Data is refreshed separately.
SCAN_INTERVAL = 5.0
DATA_REFRESH_INTERVAL = 15.0

# ============================================================
# STATE
# ============================================================
daily_pnl = 0.0
consecutive_losses = 0
last_reset_date = datetime.now(timezone.utc).date()

daily_signal_count = {s: 0 for s in PRIORITY_MARKETS}
session_signal_count = {s: {"session": None, "count": 0} for s in PRIORITY_MARKETS}

last_trade_time = {}
last_trade_direction = {}
last_trade_type = {}

last_pre_time = {}
last_pre_direction = {}

last_watch_time = {}
last_watch_direction = {}

frames_cache = {}
frames_cache_time = {}
cache_lock = Lock()

# ============================================================
# FILES
# ============================================================
for filename in ("signals_log.csv", "signals_backup.csv"):
    if not os.path.exists(filename):
        with open(filename, "a", encoding="utf-8"):
            pass

# ============================================================
# DAILY STATE
# ============================================================
def reset_daily():
    global daily_pnl, consecutive_losses, last_reset_date

    today = datetime.now(timezone.utc).date()
    if today != last_reset_date:
        daily_pnl = 0.0
        consecutive_losses = 0
        last_reset_date = today

        for symbol in PRIORITY_MARKETS:
            daily_signal_count[symbol] = 0
            session_signal_count[symbol] = {"session": None, "count": 0}

        log.info("Daily state reset complete")


def update_trade_result(pnl):
    global daily_pnl, consecutive_losses
    daily_pnl += float(pnl)
    consecutive_losses = consecutive_losses + 1 if pnl < 0 else 0


def daily_loss_lock():
    return daily_pnl <= MAX_DAILY_LOSS


def loss_streak_lock():
    return consecutive_losses >= MAX_CONSECUTIVE_LOSSES

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        log.warning("Telegram disabled: TOKEN or CHAT_ID missing")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    for attempt in range(3):
        try:
            response = http.post(
                url,
                json={"chat_id": CHAT_ID, "text": message, "parse_mode": "Markdown"},
                timeout=10,
            )

            if response.status_code == 200:
                return True

            log.error("Telegram HTTP %s: %s", response.status_code, response.text[:300])

        except Exception as exc:
            log.error("Telegram attempt %s failed: %s", attempt + 1, exc)

        time.sleep(1)

    return False

# ============================================================
# SESSION
# ============================================================
def in_session(symbol):
    now = datetime.now(timezone.utc)
    hm = now.hour * 60 + now.minute

    if MARKETS[symbol]["market_type"] == "india":
        if 225 <= hm < 330:
            return True, "India Open"
        if 330 <= hm < 450:
            return True, "India Midday"
        if 450 <= hm < 600:
            return True, "India Close"
        return False, "Closed"

    if 60 <= hm < 360:
        return True, "Asian Precision"
    if 480 <= hm < 660:
        return True, "London"
    if 780 <= hm < 840:
        return True, "NY Killzone"
    if 840 <= hm < 960:
        return True, "NY+London"

    return False, "Closed"


def weekend_block():
    now = datetime.now(timezone.utc)
    return now.weekday() == 5 or (now.weekday() == 6 and now.hour < 21)

# ============================================================
# DATA
# ============================================================
def fetch_yf(ticker, period="5d", interval="5m"):
    for attempt in range(2):
        try:
            raw = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False,
                threads=False,
            )

            if raw is None or raw.empty:
                time.sleep(0.5)
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            raw.columns = [str(c).lower() for c in raw.columns]

            needed = ["open", "high", "low", "close"]
            if any(c not in raw.columns for c in needed):
                return None

            if "volume" not in raw.columns:
                raw["volume"] = 0

            df = raw[["open", "high", "low", "close", "volume"]].copy()

            for col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.replace([math.inf, -math.inf], pd.NA)
            df = df.dropna(subset=["open", "high", "low", "close"])
            df = df[~df.index.duplicated(keep="last")]

            if len(df) < 80:
                return None

            return df

        except Exception as exc:
            log.error("Data fetch failed %s: %s", ticker, exc)
            time.sleep(0.5)

    return None


def ohlc_resample(df, rule):
    x = df.copy()
    out = x.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })
    return out.dropna(subset=["open", "high", "low", "close"])


def refresh_symbol_data(symbol):
    ticker = MARKETS[symbol]["data"]
    base = fetch_yf(ticker, "5d", "5m")

    if base is None:
        return None

    frames = {
        "5M": base.copy(),
        "15M": ohlc_resample(base, "15min"),
        "1H": ohlc_resample(base, "1h"),
    }

    if any(len(v) < 50 for v in frames.values()):
        return None

    with cache_lock:
        frames_cache[symbol] = frames
        frames_cache_time[symbol] = time.time()

    return frames


def get_frames(symbol):
    now = time.time()

    with cache_lock:
        cached = frames_cache.get(symbol)
        cached_at = frames_cache_time.get(symbol, 0)

    if cached is not None and now - cached_at < DATA_REFRESH_INTERVAL:
        return cached

    return refresh_symbol_data(symbol)

# ============================================================
# CANDLE HELPERS
# ============================================================
def candle_body(c):
    return abs(float(c["close"]) - float(c["open"]))


def bullish_candle(c):
    return float(c["close"]) > float(c["open"])


def bearish_candle(c):
    return float(c["close"]) < float(c["open"])


def average_body(df, length=10):
    value = (df["close"] - df["open"]).abs().tail(length).mean()
    return float(value) if not pd.isna(value) else 0.0


def atr_value(df, period=14):
    if len(df) < period + 2:
        return 0.0

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - prev).abs(),
        (low - prev).abs(),
    ], axis=1).max(axis=1)

    value = tr.rolling(period).mean().iloc[-1]
    return 0.0 if pd.isna(value) else float(value)

# ============================================================
# SWINGS
# ============================================================
def swing_highs(df):
    out = []
    if len(df) < SWING_LEFT + SWING_RIGHT + 1:
        return out

    for i in range(SWING_LEFT, len(df) - SWING_RIGHT):
        value = float(df["high"].iloc[i])
        left = df["high"].iloc[i-SWING_LEFT:i]
        right = df["high"].iloc[i+1:i+SWING_RIGHT+1]

        if value > float(left.max()) and value >= float(right.max()):
            out.append((i, value))

    return out


def swing_lows(df):
    out = []
    if len(df) < SWING_LEFT + SWING_RIGHT + 1:
        return out

    for i in range(SWING_LEFT, len(df) - SWING_RIGHT):
        value = float(df["low"].iloc[i])
        left = df["low"].iloc[i-SWING_LEFT:i]
        right = df["low"].iloc[i+1:i+SWING_RIGHT+1]

        if value < float(left.min()) and value <= float(right.min()):
            out.append((i, value))

    return out

# ============================================================
# SUPPLY / DEMAND
# ============================================================
def find_demand_zone(df):
    work = df.tail(ZONE_LOOKBACK_1H).reset_index(drop=True)

    if len(work) < 15:
        return None

    avg = average_body(work, 10)
    if avg <= 0:
        return None

    candidates = []

    for i in range(3, len(work)):
        c = work.iloc[i]

        if not bullish_candle(c):
            continue

        if candle_body(c) < avg * DISPLACEMENT_BODY_MULT:
            continue

        prior_high = float(work["high"].iloc[max(0, i-5):i].max())

        if float(c["close"]) <= prior_high:
            continue

        base = work.iloc[i-1]

        candidates.append({
            "low": min(float(base["open"]), float(base["close"]), float(base["low"])),
            "high": max(float(base["open"]), float(base["close"]), float(base["high"])),
            "index": i,
        })

    return candidates[-1] if candidates else None


def find_supply_zone(df):
    work = df.tail(ZONE_LOOKBACK_1H).reset_index(drop=True)

    if len(work) < 15:
        return None

    avg = average_body(work, 10)
    if avg <= 0:
        return None

    candidates = []

    for i in range(3, len(work)):
        c = work.iloc[i]

        if not bearish_candle(c):
            continue

        if candle_body(c) < avg * DISPLACEMENT_BODY_MULT:
            continue

        prior_low = float(work["low"].iloc[max(0, i-5):i].min())

        if float(c["close"]) >= prior_low:
            continue

        base = work.iloc[i-1]

        candidates.append({
            "low": min(float(base["open"]), float(base["close"]), float(base["low"])),
            "high": max(float(base["open"]), float(base["close"]), float(base["high"])),
            "index": i,
        })

    return candidates[-1] if candidates else None

# ============================================================
# ZONE / APPROACH
# ============================================================
def price_in_zone(price, zone, tolerance):
    if zone is None:
        return False

    return zone["low"] - tolerance <= price <= zone["high"] + tolerance


def approach_to_zone(price, zone, atr, direction):
    if zone is None or atr <= 0:
        return False, None

    tolerance = atr * ZONE_TOLERANCE_ATR

    if direction == "BUY":
        distance = max(0.0, price - zone["high"])
        approaching = distance <= PRE_SIGNAL_ATR * atr and price >= zone["low"] - tolerance
        return approaching, distance

    distance = max(0.0, zone["low"] - price)
    approaching = distance <= PRE_SIGNAL_ATR * atr and price <= zone["high"] + tolerance
    return approaching, distance

# ============================================================
# LIQUIDITY / REJECTION / DISPLACEMENT
# ============================================================
def liquidity_sweep(df, direction, closed=True):
    idx = -2 if closed else -1

    if len(df) < LIQUIDITY_LOOKBACK + 3:
        return False, None

    end = len(df) + idx
    start = end - LIQUIDITY_LOOKBACK
    previous = df.iloc[start:end]
    last = df.iloc[end]

    previous_high = float(previous["high"].max())
    previous_low = float(previous["low"].min())

    if direction == "BUY":
        swept = float(last["low"]) < previous_low
        reclaimed = float(last["close"]) > previous_low
        return (swept and reclaimed, previous_low if swept and reclaimed else None)

    swept = float(last["high"]) > previous_high
    reclaimed = float(last["close"]) < previous_high
    return (swept and reclaimed, previous_high if swept and reclaimed else None)


def rejection_candle(df, direction, closed=True):
    idx = -2 if closed else -1
    if len(df) < 3:
        return False

    c = df.iloc[idx]

    op, cl = float(c["open"]), float(c["close"])
    hi, lo = float(c["high"]), float(c["low"])

    body = abs(cl - op)
    total = hi - lo

    if body <= 0 or total <= 0:
        return False

    upper = hi - max(op, cl)
    lower = min(op, cl) - lo

    if direction == "BUY":
        return lower >= body * REJECTION_WICK_RATIO and cl > op and (cl - lo) / total >= 0.60

    return upper >= body * REJECTION_WICK_RATIO and cl < op and (hi - cl) / total >= 0.60


def displacement(df, direction, closed=True):
    idx = -2 if closed else -1

    if len(df) < 12:
        return False

    last = df.iloc[idx]
    prior = df.iloc[:len(df) + idx]
    avg = average_body(prior, 10)

    if avg <= 0 or candle_body(last) < avg * DISPLACEMENT_BODY_MULT:
        return False

    return bullish_candle(last) if direction == "BUY" else bearish_candle(last)

# ============================================================
# BOS / CHOCH
# ============================================================
def bos(df, direction, closed=True):
    end = len(df) - 1 if closed else len(df)
    if end < BOS_LOOKBACK + 2:
        return False, None

    last = df.iloc[end-1]
    prior = df.iloc[end-BOS_LOOKBACK-1:end-1]

    if direction == "BUY":
        level = float(prior["high"].max())
        ok = float(last["close"]) > level
        return ok, level if ok else None

    level = float(prior["low"].min())
    ok = float(last["close"]) < level
    return ok, level if ok else None


def choch(df, direction, closed=True):
    end = len(df) - 1 if closed else len(df)
    work = df.iloc[:end]

    if len(work) < 12:
        return False

    highs = swing_highs(work)
    lows = swing_lows(work)

    if direction == "BUY":
        return bool(highs and float(work.iloc[-1]["close"]) > highs[-1][1])

    return bool(lows and float(work.iloc[-1]["close"]) < lows[-1][1])

# ============================================================
# RETEST
# ============================================================
def retest_level(df, direction, level, atr, closed=True):
    if level is None or atr <= 0 or len(df) < 3:
        return False

    idx = -2 if closed else -1
    c = df.iloc[idx]
    tolerance = atr * RETEST_TOLERANCE_ATR

    if direction == "BUY":
        return float(c["low"]) <= level + tolerance and float(c["close"]) >= level

    return float(c["high"]) >= level - tolerance and float(c["close"]) <= level

# ============================================================
# ADVANCE PRE-SIGNAL
# ============================================================
def pre_signal_setup(df_1h, df_15m, df_5m, direction):
    atr = atr_value(df_1h)
    if atr <= 0:
        return {"valid": False}

    price = float(df_5m.iloc[-1]["close"])

    demand = find_demand_zone(df_1h)
    supply = find_supply_zone(df_1h)
    zone = demand if direction == "BUY" else supply

    approaching, distance = approach_to_zone(price, zone, atr, direction)

    if not approaching:
        return {"valid": False}

    # Previous candles should show movement toward the zone.
    c1 = float(df_5m.iloc[-1]["close"])
    c2 = float(df_5m.iloc[-2]["close"])
    c3 = float(df_5m.iloc[-3]["close"])

    moving_toward = c1 <= c2 <= c3 if direction == "BUY" else c1 >= c2 >= c3

    # Also accept a live touch/near-touch even if the last 3 candles
    # are not perfectly monotonic.
    in_or_near = price_in_zone(price, zone, atr * ZONE_TOLERANCE_ATR)

    if not moving_toward and not in_or_near:
        return {"valid": False}

    return {
        "valid": True,
        "zone": zone,
        "distance": distance,
        "price": price,
        "direction": direction,
    }

# ============================================================
# REVERSAL
# ============================================================
def reversal_setup(df_1h, df_15m, df_5m, direction):
    atr_1h = atr_value(df_1h)
    if atr_1h <= 0:
        return {"valid": False, "score": 0}

    price = float(df_5m.iloc[-1]["close"])
    demand = find_demand_zone(df_1h)
    supply = find_supply_zone(df_1h)
    zone = demand if direction == "BUY" else supply

    if not price_in_zone(price, zone, atr_1h * ZONE_TOLERANCE_ATR):
        return {"valid": False, "score": 0}

    swept, sweep_level = liquidity_sweep(df_15m, direction, closed=True)
    rejection = rejection_candle(df_15m, direction, closed=True)
    disp = displacement(df_15m, direction, closed=True)
    bos_ok, bos_level = bos(df_15m, direction, closed=True)
    choch_ok = choch(df_15m, direction, closed=True)

    score = 2
    if swept:
        score += 2
    if rejection:
        score += 1
    if bos_ok:
        score += 2
    if choch_ok:
        score += 1
    if disp:
        score += 1

    valid = (
        swept
        and rejection
        and (bos_ok or choch_ok)
        and score >= MIN_PA_SCORE
    )

    return {
        "valid": valid,
        "score": score,
        "level": bos_level if bos_ok else sweep_level,
        "sweep": sweep_level,
        "demand": demand,
        "supply": supply,
        "reason": "Reversal confirmed" if valid else "Waiting for confirmation",
    }

# ============================================================
# BREAKOUT
# ============================================================
def breakout_setup(df_1h, df_15m, df_5m, direction):
    atr5 = atr_value(df_5m)
    if atr5 <= 0 or len(df_15m) < BOS_LOOKBACK + 3:
        return {"valid": False, "score": 0}

    ok15, level = bos(df_15m, direction, closed=True)
    disp = displacement(df_15m, direction, closed=True)
    retest = retest_level(df_5m, direction, level, atr5, closed=True)
    trigger = rejection_candle(df_5m, direction, closed=True)

    score = 0
    score += 3 if ok15 else 0
    score += 2 if disp else 0
    score += 2 if retest else 0
    score += 2 if trigger else 0

    valid = ok15 and disp and retest and trigger and score >= 8

    return {
        "valid": valid,
        "score": score,
        "level": level,
        "sweep": None,
        "reason": "Breakout/retest confirmed" if valid else "Waiting for breakout/retest",
    }

# ============================================================
# STRUCTURE TARGET ENGINE
# ============================================================
def structure_levels(dfs, direction, entry):
    levels = []

    for df in dfs:
        if df is None or len(df) < 20:
            continue

        if direction == "BUY":
            levels.extend([x[1] for x in swing_highs(df) if x[1] > entry])
        else:
            levels.extend([x[1] for x in swing_lows(df) if x[1] < entry])

    # Remove almost-duplicate levels.
    levels = sorted(set(round(float(x), 8) for x in levels))

    return levels


def adaptive_target(dfs, direction, entry, sl_dist):
    if sl_dist <= 0:
        return None, 0.0, "INVALID"

    min_target = sl_dist * MIN_RR
    max_target = sl_dist * MAX_RR

    levels = structure_levels(dfs, direction, entry)

    if direction == "BUY":
        valid = [
            x for x in levels
            if entry + min_target <= x <= entry + max_target
        ]

        if valid:
            target = max(valid)
            return target, (target - entry) / sl_dist, "STRUCTURE"

        # If the nearest structure is beyond 4R, cap at 4R.
        beyond = [x for x in levels if x > entry + min_target]
        if beyond:
            return entry + max_target, MAX_RR, "4R-CAPPED"

        return entry + min_target, MIN_RR, "MIN-RR"

    valid = [
        x for x in levels
        if entry - max_target <= x <= entry - min_target
    ]

    if valid:
        target = min(valid)
        return target, (entry - target) / sl_dist, "STRUCTURE"

    beyond = [x for x in levels if x < entry - min_target]
    if beyond:
        return entry - max_target, MAX_RR, "4R-CAPPED"

    return entry - min_target, MIN_RR, "MIN-RR"

# ============================================================
# LEVELS / SL
# ============================================================
def calculate_sl(symbol, direction, entry, frames, setup):
    cfg = MARKETS[symbol]

    atr5 = atr_value(frames["5M"])
    atr15 = atr_value(frames["15M"])
    atr = max(atr5, atr15)

    if atr <= 0:
        return None

    buffer = max(cfg["min_sl"] * cfg["sl_buffer"], atr * 0.10)

    sweep = setup.get("sweep")
    level = setup.get("level")

    if direction == "BUY":
        candidates = [entry - cfg["min_sl"]]
        if sweep is not None:
            candidates.append(float(sweep) - buffer)
        if level is not None:
            candidates.append(float(level) - buffer)
        sl = min(candidates)
        sl_dist = entry - sl
    else:
        candidates = [entry + cfg["min_sl"]]
        if sweep is not None:
            candidates.append(float(sweep) + buffer)
        if level is not None:
            candidates.append(float(level) + buffer)
        sl = max(candidates)
        sl_dist = sl - entry

    # More realistic adaptive ceiling than the old fixed 3x min-SL.
    max_sl = max(cfg["min_sl"] * 5.0, atr * 2.0)

    if sl_dist <= 0 or sl_dist > max_sl:
        return None

    return sl, sl_dist

# ============================================================
# LOT SIZE
# ============================================================
def lot_for_risk(symbol, sl_dist):
    if sl_dist <= 0:
        return 0.0

    dpp = DOLLAR_PER_POINT.get(symbol)
    if not dpp:
        return 0.0

    raw = RISK_PER_TRADE / (sl_dist * dpp)
    cap = LOT_CAP.get(symbol, raw)

    if symbol in {"NIFTY50", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS"}:
        return float(max(1, round(min(raw, cap))))

    return round(max(0.01, min(raw, cap)), 3)

# ============================================================
# GATES
# ============================================================
def session_gate(symbol, session):
    state = session_signal_count[symbol]

    if state["session"] != session:
        state["session"] = session
        state["count"] = 0

    return not SIGNAL_ONE_PER_SESSION or state["count"] < 1


def consume_session_signal(symbol, session):
    state = session_signal_count[symbol]

    if state["session"] != session:
        state["session"] = session
        state["count"] = 0

    state["count"] += 1


def trade_duplicate(symbol, direction, signal_type):
    return time.time() - last_trade_time.get(symbol, 0) < TRADE_SIGNAL_COOLDOWN


def pre_duplicate(symbol, direction):
    return (
        last_pre_direction.get(symbol) == direction
        and time.time() - last_pre_time.get(symbol, 0) < PRE_SIGNAL_COOLDOWN
    )


def watch_duplicate(symbol, direction):
    return (
        last_watch_direction.get(symbol) == direction
        and time.time() - last_watch_time.get(symbol, 0) < WATCH_COOLDOWN
    )

# ============================================================
# TELEGRAM MESSAGES
# ============================================================
def send_pre_signal(symbol, setup, session):
    cfg = MARKETS[symbol]
    dec = cfg["decimals"]
    direction = setup["direction"]
    zone = setup["zone"]
    price = setup["price"]

    emoji = "🟢" if direction == "BUY" else "🔴"
    zone_name = "DEMAND" if direction == "BUY" else "SUPPLY"

    msg = (
        f"⚠️ *ADVANCE PRE-SIGNAL*\n"
        f"*{cfg['execution']}* | {session}\n\n"
        f"{emoji} *Potential {direction} setup approaching {zone_name}*\n"
        f"📍 Current price: {price:,.{dec}f}\n"
        f"📦 Zone: {zone['low']:,.{dec}f} → {zone['high']:,.{dec}f}\n"
        f"📏 Distance: {setup['distance']:,.{dec}f}\n\n"
        f"👀 WAIT — NOT A TRADE YET\n"
        f"Required next:\n"
        f"• 15M liquidity sweep / structure shift\n"
        f"• 5M confirmation\n"
        f"• Adaptive RR target ≥ {MIN_RR:.2f}R\n\n"
        f"🧭 *Advance warning only*"
    )
    send_telegram(msg)


def send_watch_signal(symbol, direction, setup, session):
    cfg = MARKETS[symbol]
    dec = cfg["decimals"]
    price = float(setup["price"])
    level = setup.get("level")

    msg = (
        f"👀 *PA WATCH — {cfg['execution']}*\n\n"
        f"*Direction:* {direction}\n"
        f"*Price:* {price:,.{dec}f}\n"
        f"*Structure:* {level:,.{dec}f}\n" if level is not None else ""
        f"*Status:* setup forming — wait for 5M confirmation\n"
        f"*Session:* {session}"
    )
    send_telegram(msg)


def send_trade_signal(symbol, direction, signal_type, score, session,
                      entry, sl, tp, lot, setup, rr, target_mode):
    cfg = MARKETS[symbol]
    dec = cfg["decimals"]
    quality = "GOD-TIER PA" if score >= 10 else "A+ PA" if score >= 9 else "A PA"

    msg = (
        f"🚨 *{SYSTEM_VERSION} TRADE SIGNAL*\n"
        f"*{cfg['execution']}*\n\n"
        f"{'📈' if direction == 'BUY' else '📉'} *{direction}*\n"
        f"🚀 Setup: *{signal_type}*\n"
        f"⭐ PA Score: *{score}/10*\n"
        f"🏆 Quality: *{quality}*\n\n"
        f"📍 Entry: *{entry:,.{dec}f}*\n"
        f"🛑 SL: *{sl:,.{dec}f}*\n"
        f"🎯 TP: *{tp:,.{dec}f}*\n"
        f"⚖️ RR: *1:{rr:.2f}*\n"
        f"🧠 Target: *{target_mode}*\n"
        f"💵 Lot: *{lot}*\n\n"
        f"⏱ Structure: 1H → 15M → 5M\n"
        f"📌 Session: {session}\n"
        f"💧 Liquidity: {'CONFIRMED' if setup.get('sweep') is not None else 'STRUCTURE'}\n\n"
        f"✅ Price Action only\n"
        f"🚫 No EMA / RSI / ADX / VWAP"
    )
    send_telegram(msg)

# ============================================================
# CSV
# ============================================================
def log_signal(symbol, direction, score, signal_type, entry, sl, tp, rr, session, target_mode):
    row = [
        SYSTEM_VERSION,
        datetime.now(timezone.utc).isoformat(),
        symbol, direction, score, signal_type,
        entry, sl, tp, rr, session, target_mode,
    ]

    with log_lock:
        path = "signals_log.csv"

        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if os.path.getsize(path) == 0:
                writer.writerow([
                    "version", "timestamp", "symbol", "direction",
                    "score", "signal_type", "entry", "sl", "tp",
                    "rr", "session", "target_mode",
                ])
            writer.writerow(row)

        with open("signals_backup.csv", "a", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(row)

# ============================================================
# PRE-SIGNAL PROCESS
# ============================================================
def process_pre_signal(symbol, frames, session):
    df1 = frames["1H"]
    df15 = frames["15M"]
    df5 = frames["5M"]

    for direction in ("BUY", "SELL"):
        setup = pre_signal_setup(df1, df15, df5, direction)

        if not setup["valid"]:
            continue

        if pre_duplicate(symbol, direction):
            continue

        setup["price"] = float(df5.iloc[-1]["close"])
        setup["direction"] = direction

        send_pre_signal(symbol, setup, session)

        last_pre_time[symbol] = time.time()
        last_pre_direction[symbol] = direction

# ============================================================
# TRADE PROCESS
# ============================================================
def process_trade(symbol, frames, session):
    if daily_signal_count[symbol] >= MARKETS[symbol]["daily_cap"]:
        return False

    for direction in ("BUY", "SELL"):
        # --------------------------------------------
        # Reversal first
        # --------------------------------------------
        setup = reversal_setup(
            frames["1H"], frames["15M"], frames["5M"], direction
        )

        signal_type = "LIQUIDITY REVERSAL"

        if not setup["valid"]:
            # ----------------------------------------
            # Breakout + retest
            # ----------------------------------------
            setup = breakout_setup(
                frames["1H"], frames["15M"], frames["5M"], direction
            )
            signal_type = "BREAKOUT + RETEST"

        if not setup["valid"]:
            continue

        if trade_duplicate(symbol, direction, signal_type):
            continue

        price = float(frames["5M"].iloc[-1]["close"])

        if direction == "BUY":
            entry = price + EXECUTION_BUFFER[symbol]
        else:
            entry = price - EXECUTION_BUFFER[symbol]

        sl_data = calculate_sl(symbol, direction, entry, frames, setup)
        if sl_data is None:
            log.info("%s %s rejected: adaptive SL invalid", symbol, direction)
            continue

        sl, sl_dist = sl_data

        tp, rr, target_mode = adaptive_target(
            [frames["5M"], frames["15M"], frames["1H"]],
            direction,
            entry,
            sl_dist,
        )

        if tp is None or rr < MIN_RR:
            log.info("%s %s rejected: RR %.2f < %.2f", symbol, direction, rr, MIN_RR)
            continue

        lot = lot_for_risk(symbol, sl_dist)
        score = min(10, int(setup.get("score", 8)) + 1)

        log_signal(
            symbol, direction, score, signal_type,
            entry, sl, tp, rr, session, target_mode
        )

        send_trade_signal(
            symbol, direction, signal_type, score, session,
            entry, sl, tp, lot, setup, rr, target_mode
        )

        with signal_lock:
            last_trade_time[symbol] = time.time()
            last_trade_direction[symbol] = direction
            last_trade_type[symbol] = signal_type
            daily_signal_count[symbol] += 1
            consume_session_signal(symbol, session)

        log.info(
            "TRADE SIGNAL %s %s | entry=%s sl=%s tp=%s RR=%.2f target=%s score=%s",
            symbol, direction, entry, sl, tp, rr, target_mode, score
        )

        return True

    return False

# ============================================================
# SYMBOL PROCESS
# ============================================================
def process_symbol(symbol):
    try:
        if weekend_block() or daily_loss_lock() or loss_streak_lock():
            return

        ok, session = in_session(symbol)
        if not ok or session not in MARKETS[symbol]["sessions"]:
            return

        frames = get_frames(symbol)
        if frames is None:
            return

        # Advance warning is intentionally BEFORE trade confirmation.
        process_pre_signal(symbol, frames, session)

        if not session_gate(symbol, session):
            return

        process_trade(symbol, frames, session)

    except Exception as exc:
        log.exception("Symbol processing error %s: %s", symbol, exc)

# ============================================================
# WATCHDOG
# ============================================================
def watchdog():
    try:
        with open("heartbeat.txt", "w", encoding="utf-8") as f:
            f.write(
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"{SYSTEM_VERSION} | ACTIVE"
            )
    except Exception as exc:
        log.error("Watchdog failure: %s", exc)

# ============================================================
# STARTUP
# ============================================================
def startup_message():
    return (
        f"⚡ *{SYSTEM_VERSION} LIVE*\n\n"
        f"1H = Location / Structure\n"
        f"15M = Liquidity + BOS/CHOCH\n"
        f"5M = Trigger\n\n"
        f"⚠️ Advance Pre-Signal: {PRE_SIGNAL_ATR:.2f} ATR\n"
        f"⚖️ Adaptive RR: {MIN_RR:.2f}R → {MAX_RR:.2f}R\n"
        f"🎯 Targets use real 5M/15M/1H structure\n"
        f"🚫 No indicator scoring\n"
        f"🌐 Markets: {len(PRIORITY_MARKETS)}\n"
        f"⏱ Decision scan: {SCAN_INTERVAL:.1f}s\n"
        f"📡 Data refresh: {DATA_REFRESH_INTERVAL:.1f}s\n\n"
        f"PRE = warning only\n"
        f"TRADE = confirmed PA setup"
    )

# ============================================================
# MAIN
# ============================================================
def main():
    log.info("%s STARTED", SYSTEM_VERSION)
    log.info(
        "LIVE PA ENGINE | decision_interval=%.1fs | data_refresh=%.1fs | symbols=%s",
        SCAN_INTERVAL, DATA_REFRESH_INTERVAL, len(PRIORITY_MARKETS)
    )

    send_telegram(startup_message())

    loop = 0
    last_data_refresh = 0.0

    while True:
        try:
            reset_daily()
            watchdog()

            # Refresh all symbols together only when cache expires.
            now = time.time()

            if now - last_data_refresh >= DATA_REFRESH_INTERVAL:
                log.info(
                    "⚡ DATA refresh | symbols=%s | refresh=%.1fs",
                    len(PRIORITY_MARKETS), DATA_REFRESH_INTERVAL
                )

                with ThreadPoolExecutor(max_workers=len(PRIORITY_MARKETS)) as executor:
                    futures = [
                        executor.submit(refresh_symbol_data, symbol)
                        for symbol in PRIORITY_MARKETS
                    ]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as exc:
                            log.error("Data worker error: %s", exc)

                last_data_refresh = time.time()

            log.info(
                "⚡ LIVE PA scan #%s | symbols=%s | interval=%.1fs",
                loop, len(PRIORITY_MARKETS), SCAN_INTERVAL
            )

            with ThreadPoolExecutor(max_workers=len(PRIORITY_MARKETS)) as executor:
                futures = [
                    executor.submit(process_symbol, symbol)
                    for symbol in PRIORITY_MARKETS
                ]

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        log.error("Worker error: %s", exc)

            loop += 1
            gc.collect()
            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            log.info("Stopped by user")
            break

        except Exception as exc:
            log.exception("Main loop error: %s", exc)
            time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
