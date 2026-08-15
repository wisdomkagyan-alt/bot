# ============================================================
# PA-SUPREME-2026 — HTF PO3 / AMD / SWEEP / MSS / FVG ENGINE
#
# PURPOSE
#   Rebuilds the publicly described workflow around:
#     1H HTF location / Power of 3 context
#     1H liquidity sweep
#     15M market-structure shift (MSS/BOS)
#     15M displacement
#     15M FVG creation
#     5M FVG retest + confirmation
#     Adaptive SL / structure-based TP / RR
#
# ALERTS
#   PRE  -> approaching HTF liquidity
#   WATCH -> HTF sweep + 15M structure is developing
#   TRADE -> full confirmation only
#
# IMPORTANT
#   This is NOT the closed-source TTM script. It implements the
#   publicly described HTF/AMD/PO3/sweep concepts. The proprietary
#   source/hidden rules of the TradingView script are unavailable.
#
# DATA
#   Uses Yahoo Finance because this version is designed to run on
#   Railway/Render without a desktop MT5 terminal.
#   Replace the data adapter later with Pepperstone/MT5 for native
#   broker-grade live prices.
#
# TELEGRAM
#   Railway Environment Variables:
#       TELEGRAM_TOKEN = your bot token
#       TELEGRAM_CHAT_ID = your chat id
#
# DO NOT put secrets directly in this file.
# ============================================================

import csv
import gc
import logging
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock

import pandas as pd
import requests
import yfinance as yf


# ============================================================
# VERSION / GLOBAL SETTINGS
# ============================================================

SYSTEM_VERSION = "PA-SUPREME-2026-PO3-FVG"

SCAN_INTERVAL = 1.0
DATA_REFRESH_INTERVAL = 15.0

# Confirmation uses CLOSED candles.
USE_CLOSED_CANDLES = True

# Alert cooldowns.
PRE_COOLDOWN = 900
WATCH_COOLDOWN = 900
TRADE_COOLDOWN = 1800

# Prevent duplicate alerts for the same setup even if the price
# remains in exactly the same state.
SETUP_MEMORY_SECONDS = 7200

# One confirmed trade per symbol per session.
ONE_TRADE_PER_SESSION = True

# Risk model.
RISK_PER_TRADE = 50.0
MIN_RR = 1.80
# No artificial maximum RR. TP3 is determined by the next qualifying
# opposing structure/liquidity level. MIN_RR remains the hard minimum.
MAX_RR = None

# PA settings.
SWING_LEFT = 2
SWING_RIGHT = 2
MSS_LOOKBACK = 6
FVG_MIN_ATR = 0.05
FVG_MAX_AGE = 12
DISPLACEMENT_MULT = 1.20

# Pre-signal distance from previous HTF liquidity.
PRE_ATR_DISTANCE = 0.75

# HTF sweep must take previous HTF extreme and close back inside.
SWEEP_CLOSE_BACK_INSIDE = True

# ============================================================
# TELEGRAM
# ============================================================

TOKEN = os.getenv("TOKEN", "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")


http = requests.Session()
telegram_lock = Lock()


def send_telegram(message: str) -> bool:
    if not TOKEN or not CHAT_ID:
        log.warning("Telegram disabled: missing TELEGRAM_TOKEN/TELEGRAM_CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    with telegram_lock:
        for attempt in range(3):
            try:
                r = http.post(url, json=payload, timeout=10)

                if r.ok:
                    return True

                log.error(
                    "Telegram HTTP %s: %s",
                    r.status_code,
                    r.text[:300],
                )

            except Exception as exc:
                log.error(
                    "Telegram attempt %s failed: %s",
                    attempt + 1,
                    exc,
                )

            time.sleep(1)

    return False


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

log = logging.getLogger(SYSTEM_VERSION)


# ============================================================
# MARKETS
# ============================================================

MARKETS = {
    "XAU/USD": {
        "data": "GC=F",
        "execution": "XAUUSD",
        "decimals": 2,
        "market": "global",
        "min_sl": 1.50,
        "dpp": 100.0,
        "lot_cap": 1.50,
        "sessions": ["Asia", "London", "NY"],
    },

    "NAS100": {
        "data": "^NDX",
        "execution": "NAS100",
        "decimals": 1,
        "market": "global",
        "min_sl": 12.0,
        "dpp": 10.0,
        "lot_cap": 2.0,
        "sessions": ["London", "NY"],
    },

    "SPX500": {
        "data": "^GSPC",
        "execution": "SPX500",
        "decimals": 1,
        "market": "global",
        "min_sl": 6.0,
        "dpp": 10.0,
        "lot_cap": 2.0,
        "sessions": ["London", "NY"],
    },

    "EUR/USD": {
        "data": "EURUSD=X",
        "execution": "EURUSD",
        "decimals": 5,
        "market": "global",
        "min_sl": 0.00025,
        "dpp": 100000.0,
        "lot_cap": 3.0,
        "sessions": ["Asia", "London", "NY"],
    },

    "GBP/JPY": {
        "data": "GBPJPY=X",
        "execution": "GBPJPY",
        "decimals": 3,
        "market": "global",
        "min_sl": 0.040,
        "dpp": 1000.0,
        "lot_cap": 2.0,
        "sessions": ["Asia", "London", "NY"],
    },

    "NIFTY50": {
        "data": "^NSEI",
        "execution": "NIFTY50",
        "decimals": 2,
        "market": "india",
        "min_sl": 15.0,
        "dpp": 50.0,
        "lot_cap": 50.0,
        "sessions": ["India"],
    },

    "BANKNIFTY": {
        "data": "^NSEBANK",
        "execution": "BANKNIFTY",
        "decimals": 2,
        "market": "india",
        "min_sl": 20.0,
        "dpp": 20.0,
        "lot_cap": 50.0,
        "sessions": ["India"],
    },

    "SENSEX": {
        "data": "^BSESN",
        "execution": "SENSEX",
        "decimals": 2,
        "market": "india",
        "min_sl": 40.0,
        "dpp": 10.0,
        "lot_cap": 50.0,
        "sessions": ["India"],
    },

    "RELIANCE": {
        "data": "RELIANCE.NS",
        "execution": "RELIANCE",
        "decimals": 2,
        "market": "india",
        "min_sl": 5.0,
        "dpp": 1.0,
        "lot_cap": 500.0,
        "sessions": ["India"],
    },

    "TCS": {
        "data": "TCS.NS",
        "execution": "TCS",
        "decimals": 2,
        "market": "india",
        "min_sl": 8.0,
        "dpp": 1.0,
        "lot_cap": 500.0,
        "sessions": ["India"],
    },
}

SYMBOLS = list(MARKETS.keys())


# ============================================================
# RUNTIME STATE
# ============================================================

frames_cache = {}
frames_cache_time = {}
cache_lock = Lock()

last_alert = {}
setup_memory = {}

session_trade_count = {
    symbol: {"session": None, "count": 0}
    for symbol in SYMBOLS
}

daily_trade_count = {symbol: 0 for symbol in SYMBOLS}

daily_date = datetime.now(timezone.utc).date()


# ============================================================
# FILE LOGGING
# ============================================================

CSV_FILE = "signals_log.csv"

if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            "timestamp",
            "symbol",
            "direction",
            "stage",
            "setup",
            "price",
            "sl",
            "tp1",
            "tp2",
            "tp3",
            "rr",
            "session",
            "htf_sweep",
            "mss",
            "fvg",
        ])


def log_signal(
    symbol,
    direction,
    stage,
    setup,
    price,
    sl,
    tp1,
    tp2,
    tp3,
    rr,
    session,
    sweep,
    mss,
    fvg,
):
    with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
        csv.writer(f).writerow([
            datetime.now(timezone.utc).isoformat(),
            symbol,
            direction,
            stage,
            setup,
            price,
            sl,
            tp1,
            tp2,
            tp3,
            rr,
            session,
            sweep,
            mss,
            fvg,
        ])


# ============================================================
# DAILY RESET
# ============================================================

def reset_daily_state():
    global daily_date

    today = datetime.now(timezone.utc).date()

    if today == daily_date:
        return

    daily_date = today

    for symbol in SYMBOLS:
        daily_trade_count[symbol] = 0
        session_trade_count[symbol] = {
            "session": None,
            "count": 0,
        }

    setup_memory.clear()
    last_alert.clear()

    log.info("Daily state reset")


# ============================================================
# SESSION
# ============================================================

def current_session(symbol):
    now = datetime.now(timezone.utc)
    minutes = now.hour * 60 + now.minute

    if MARKETS[symbol]["market"] == "india":
        # Approx. NSE/BSE session in UTC.
        if 225 <= minutes < 600:
            return "India"
        return None

    if 60 <= minutes < 360:
        return "Asia"

    if 420 <= minutes < 720:
        return "London"

    if 720 <= minutes < 1020:
        return "NY"

    return None


def weekend_block():
    now = datetime.now(timezone.utc)

    if now.weekday() == 5:
        return True

    if now.weekday() == 6 and now.hour < 21:
        return True

    return False


# ============================================================
# DATA ENGINE
# ============================================================

def normalize_yahoo(raw):
    if raw is None or raw.empty:
        return None

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)

    raw.columns = [str(c).lower() for c in raw.columns]

    required = ["open", "high", "low", "close"]

    if any(c not in raw.columns for c in required):
        return None

    if "volume" not in raw.columns:
        raw["volume"] = 0

    df = raw[["open", "high", "low", "close", "volume"]].copy()

    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.replace([math.inf, -math.inf], pd.NA)
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[~df.index.duplicated(keep="last")]

    return df


def fetch_5m(symbol):
    ticker = MARKETS[symbol]["data"]

    for attempt in range(2):
        try:
            raw = yf.download(
                ticker,
                period="5d",
                interval="5m",
                progress=False,
                auto_adjust=False,
                threads=False,
            )

            df = normalize_yahoo(raw)

            if df is not None and len(df) >= 100:
                return df

        except Exception as exc:
            log.error(
                "Yahoo fetch failed %s attempt=%s: %s",
                symbol,
                attempt + 1,
                exc,
            )

        time.sleep(0.5)

    return None


def resample_ohlc(df, rule):
    x = df.copy()

    out = x.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    })

    return out.dropna(subset=["open", "high", "low", "close"])


def refresh_symbol(symbol):
    base = fetch_5m(symbol)

    if base is None:
        return None

    frames = {
        "5M": base.copy(),
        "15M": resample_ohlc(base, "15min"),
        "1H": resample_ohlc(base, "1h"),
    }

    if any(len(df) < 30 for df in frames.values()):
        return None

    with cache_lock:
        frames_cache[symbol] = frames
        frames_cache_time[symbol] = time.time()

    return frames


def get_frames(symbol):
    with cache_lock:
        cached = frames_cache.get(symbol)
        cached_at = frames_cache_time.get(symbol, 0)

    if cached is not None:
        if time.time() - cached_at < DATA_REFRESH_INTERVAL:
            return cached

    return refresh_symbol(symbol)


# ============================================================
# CANDLE / ATR HELPERS
# ============================================================

def body(c):
    return abs(float(c["close"]) - float(c["open"]))


def bullish(c):
    return float(c["close"]) > float(c["open"])


def bearish(c):
    return float(c["close"]) < float(c["open"])


def atr(df, period=14):
    if len(df) < period + 2:
        return 0.0

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    previous_close = close.shift(1)

    tr = pd.concat([
        high - low,
        (high - previous_close).abs(),
        (low - previous_close).abs(),
    ], axis=1).max(axis=1)

    value = tr.rolling(period).mean().iloc[-1]

    if pd.isna(value):
        return 0.0

    return float(value)


def avg_body(df, length=10):
    value = (
        (df["close"] - df["open"])
        .abs()
        .tail(length)
        .mean()
    )

    if pd.isna(value):
        return 0.0

    return float(value)


# ============================================================
# SWING ENGINE
# ============================================================

def swing_highs(df):
    result = []

    if len(df) < SWING_LEFT + SWING_RIGHT + 1:
        return result

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT,
    ):
        value = float(df["high"].iloc[i])

        left = df["high"].iloc[
            i - SWING_LEFT:i
        ]

        right = df["high"].iloc[
            i + 1:i + SWING_RIGHT + 1
        ]

        if value > float(left.max()) and value >= float(right.max()):
            result.append((i, value))

    return result


def swing_lows(df):
    result = []

    if len(df) < SWING_LEFT + SWING_RIGHT + 1:
        return result

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT,
    ):
        value = float(df["low"].iloc[i])

        left = df["low"].iloc[
            i - SWING_LEFT:i
        ]

        right = df["low"].iloc[
            i + 1:i + SWING_RIGHT + 1
        ]

        if value < float(left.min()) and value <= float(right.min()):
            result.append((i, value))

    return result


# ============================================================
# HTF PO3 / AMD CONTEXT
# ============================================================

def po3_context(df1h):
    """
    Public-concept implementation.

    Uses the previous closed 1H candle and its open/high/low/close
    to classify the current price into broad AMD/PO3 context.

    This is contextual, not a claim to reproduce proprietary TTM
    internal classification.
    """

    if len(df1h) < 4:
        return {
            "phase": "UNKNOWN",
            "bias": "NEUTRAL",
            "open": None,
            "high": None,
            "low": None,
            "close": None,
        }

    previous = df1h.iloc[-2]
    current = df1h.iloc[-1]

    htf_open = float(previous["open"])
    htf_high = float(previous["high"])
    htf_low = float(previous["low"])
    htf_close = float(previous["close"])

    current_price = float(current["close"])

    midpoint = (htf_high + htf_low) / 2.0

    if current_price > htf_high:
        phase = "EXPANSION_ABOVE"
    elif current_price < htf_low:
        phase = "EXPANSION_BELOW"
    elif current_price < htf_open:
        phase = "MANIPULATION_BELOW_OPEN"
    elif current_price > htf_open:
        phase = "DISTRIBUTION_ABOVE_OPEN"
    else:
        phase = "ACCUMULATION_NEAR_OPEN"

    if htf_close > htf_open:
        bias = "BULLISH"
    elif htf_close < htf_open:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return {
        "phase": phase,
        "bias": bias,
        "open": htf_open,
        "high": htf_high,
        "low": htf_low,
        "close": htf_close,
        "mid": midpoint,
    }


# ============================================================
# HTF SWEEP ENGINE
# ============================================================

def detect_htf_sweep(df1h):
    """
    Detects sweep of the PREVIOUS closed 1H candle.

    Bullish sweep:
      current closed 1H low < previous 1H low
      and current close >= previous low

    Bearish sweep:
      current closed 1H high > previous 1H high
      and current close <= previous high

    If the candle closes beyond the level, it is treated as a
    breakout rather than a sweep.
    """

    if len(df1h) < 4:
        return None

    previous = df1h.iloc[-3]
    current = df1h.iloc[-2]

    previous_high = float(previous["high"])
    previous_low = float(previous["low"])

    current_high = float(current["high"])
    current_low = float(current["low"])
    current_close = float(current["close"])

    bullish_sweep = (
        current_low < previous_low
        and current_close >= previous_low
    )

    bearish_sweep = (
        current_high > previous_high
        and current_close <= previous_high
    )

    if bullish_sweep:
        return {
            "direction": "BUY",
            "level": previous_low,
            "sweep_extreme": current_low,
            "candle_high": current_high,
            "candle_low": current_low,
            "candle_close": current_close,
            "candle_range": current_high - current_low,
            "mid": (current_high + current_low) / 2.0,
        }

    if bearish_sweep:
        return {
            "direction": "SELL",
            "level": previous_high,
            "sweep_extreme": current_high,
            "candle_high": current_high,
            "candle_low": current_low,
            "candle_close": current_close,
            "candle_range": current_high - current_low,
            "mid": (current_high + current_low) / 2.0,
        }

    return None


# ============================================================
# 15M MSS / BOS
# ============================================================

def structure_shift(df15, direction):
    """
    Closed 15M candle must break a recent confirmed swing.

    BUY  -> close above previous swing high
    SELL -> close below previous swing low
    """

    if len(df15) < 20:
        return None

    closed = df15.iloc[:-1]

    if direction == "BUY":
        highs = swing_highs(closed)

        if not highs:
            return None

        level = highs[-1][1]
        last_close = float(closed.iloc[-1]["close"])

        if last_close > level:
            return {
                "direction": "BUY",
                "level": level,
                "type": "BULLISH_MSS",
            }

    else:
        lows = swing_lows(closed)

        if not lows:
            return None

        level = lows[-1][1]
        last_close = float(closed.iloc[-1]["close"])

        if last_close < level:
            return {
                "direction": "SELL",
                "level": level,
                "type": "BEARISH_MSS",
            }

    return None


# ============================================================
# DISPLACEMENT
# ============================================================

def displacement_ok(df15, direction):
    if len(df15) < 15:
        return False

    closed = df15.iloc[:-1]

    last = closed.iloc[-1]

    recent = closed.iloc[:-1].tail(10)

    average = avg_body(recent, 10)

    if average <= 0:
        return False

    if body(last) < average * DISPLACEMENT_MULT:
        return False

    if direction == "BUY":
        return bullish(last)

    return bearish(last)


# ============================================================
# FVG ENGINE
# ============================================================

def find_recent_fvg(df, direction):
    """
    Three-candle FVG.

    Bullish:
      candle[3].high < candle[1].low

    Bearish:
      candle[3].low > candle[1].high

    We use CLOSED candles only.
    """

    if len(df) < 10:
        return None

    closed = df.iloc[:-1]

    start = max(2, len(closed) - FVG_MAX_AGE)

    for i in range(len(closed) - 1, start - 1, -1):
        c1 = closed.iloc[i - 2]
        c2 = closed.iloc[i - 1]
        c3 = closed.iloc[i]

        local_atr = atr(closed.iloc[:i + 1])

        if local_atr <= 0:
            continue

        if direction == "BUY":
            gap_low = float(c1["high"])
            gap_high = float(c3["low"])

            if gap_high <= gap_low:
                continue

            gap_size = gap_high - gap_low

            if gap_size < local_atr * FVG_MIN_ATR:
                continue

            return {
                "direction": "BUY",
                "low": gap_low,
                "high": gap_high,
                "index": i,
                "gap": gap_size,
                "mid": (gap_low + gap_high) / 2.0,
            }

        else:
            gap_low = float(c3["high"])
            gap_high = float(c1["low"])

            if gap_high <= gap_low:
                continue

            gap_size = gap_high - gap_low

            if gap_size < local_atr * FVG_MIN_ATR:
                continue

            return {
                "direction": "SELL",
                "low": gap_low,
                "high": gap_high,
                "index": i,
                "gap": gap_size,
                "mid": (gap_low + gap_high) / 2.0,
            }

    return None


# ============================================================
# 5M FVG RETEST / CONFIRMATION
# ============================================================

def fvg_retest_confirmation(df5, fvg, direction):
    if fvg is None:
        return None

    if len(df5) < 10:
        return None

    closed = df5.iloc[:-1]

    current = closed.iloc[-1]

    low = float(current["low"])
    high = float(current["high"])
    close = float(current["close"])

    touched = (
        low <= fvg["high"]
        and high >= fvg["low"]
    )

    if not touched:
        return None

    if direction == "BUY":
        rejected = (
            close >= fvg["mid"]
            and close > float(current["open"])
        )

        if rejected:
            return {
                "confirmed": True,
                "entry": close,
                "reason": "5M bullish FVG retest confirmed",
            }

    else:
        rejected = (
            close <= fvg["mid"]
            and close < float(current["open"])
        )

        if rejected:
            return {
                "confirmed": True,
                "entry": close,
                "reason": "5M bearish FVG retest confirmed",
            }

    return None


# ============================================================
# PRE-SIGNAL
# ============================================================

def pre_signal(symbol, frames, direction):
    df1 = frames["1H"]
    df5 = frames["5M"]

    if len(df1) < 10:
        return None

    sweep_reference = df1.iloc[-2]

    h = float(sweep_reference["high"])
    l = float(sweep_reference["low"])

    price = float(df5.iloc[-1]["close"])

    htf_atr = atr(df1)

    if htf_atr <= 0:
        return None

    if direction == "BUY":
        distance = price - l

        if 0 <= distance <= PRE_ATR_DISTANCE * htf_atr:
            return {
                "direction": "BUY",
                "price": price,
                "liquidity": l,
                "distance": distance,
            }

    else:
        distance = h - price

        if 0 <= distance <= PRE_ATR_DISTANCE * htf_atr:
            return {
                "direction": "SELL",
                "price": price,
                "liquidity": h,
                "distance": distance,
            }

    return None


# ============================================================
# SL ENGINE
# ============================================================

def calculate_sl(symbol, direction, entry, sweep, mss):
    cfg = MARKETS[symbol]

    if sweep is None:
        return None

    htf_range = abs(float(sweep["candle_range"]))

    buffer = max(
        cfg["min_sl"] * 0.10,
        htf_range * 0.05,
    )

    if direction == "BUY":
        sl = float(sweep["sweep_extreme"]) - buffer
        distance = entry - sl

    else:
        sl = float(sweep["sweep_extreme"]) + buffer
        distance = sl - entry

    if distance <= 0:
        return None

    max_sl = max(
        cfg["min_sl"] * 5.0,
        htf_range * 1.5,
    )

    distance = max(distance, cfg["min_sl"])

    if distance > max_sl:
        return None

    return sl, distance


# ============================================================
# STRUCTURE TARGETS
# ============================================================

def target_levels(frames, direction, entry):
    levels = []

    for name in ("5M", "15M", "1H"):
        df = frames[name]

        if len(df) < 20:
            continue

        closed = df.iloc[:-1]

        if direction == "BUY":
            levels.extend(
                value
                for _, value in swing_highs(closed)
                if value > entry
            )

        else:
            levels.extend(
                value
                for _, value in swing_lows(closed)
                if value < entry
            )

    levels = sorted(
        set(round(float(x), 8) for x in levels)
    )

    return levels


def adaptive_targets(frames, direction, entry, sl_distance):
    """
    Structure-driven target engine.

    TP1:
        1R management level.

    TP2:
        2R when the structural TP3 allows it; otherwise TP3.

    TP3:
        The NEAREST qualifying opposing structure/liquidity level
        that provides at least MIN_RR. There is deliberately NO
        artificial maximum RR. A valid 5R/6R/8R structural target
        is allowed if the market structure supports it.

    If no structural level reaches MIN_RR, the setup is rejected
    rather than inventing an arbitrary far-away target.
    """
    if sl_distance <= 0:
        return None

    min_distance = sl_distance * MIN_RR
    levels = target_levels(frames, direction, entry)

    if direction == "BUY":
        valid = [
            x for x in levels
            if x >= entry + min_distance
        ]

        if valid:
            # Nearest meaningful opposing structure beyond MIN_RR.
            tp3 = min(valid)
        else:
            return None

        tp1 = entry + sl_distance * 1.0
        tp2 = entry + sl_distance * 2.0

        if tp2 > tp3:
            tp2 = tp3

        rr = (tp3 - entry) / sl_distance

    else:
        valid = [
            x for x in levels
            if x <= entry - min_distance
        ]

        if valid:
            # Nearest meaningful opposing structure beyond MIN_RR.
            tp3 = max(valid)
        else:
            return None

        tp1 = entry - sl_distance * 1.0
        tp2 = entry - sl_distance * 2.0

        if tp2 < tp3:
            tp2 = tp3

        rr = (entry - tp3) / sl_distance

    if rr < MIN_RR:
        return None

    return {
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "rr": rr,
    }


# ============================================================
# LOT SIZE
# ============================================================

def lot_size(symbol, sl_distance):
    cfg = MARKETS[symbol]

    if sl_distance <= 0:
        return 0.0

    raw = RISK_PER_TRADE / (
        sl_distance * cfg["dpp"]
    )

    return round(
        max(
            0.01,
            min(raw, cfg["lot_cap"]),
        ),
        3,
    )


# ============================================================
# SETUP ID / DEDUP
# ============================================================

def setup_id(
    symbol,
    direction,
    sweep,
    mss,
    fvg,
):
    sweep_level = round(
        float(sweep["level"]),
        MARKETS[symbol]["decimals"],
    )

    mss_level = round(
        float(mss["level"]),
        MARKETS[symbol]["decimals"],
    )

    fvg_low = round(
        float(fvg["low"]),
        MARKETS[symbol]["decimals"],
    )

    fvg_high = round(
        float(fvg["high"]),
        MARKETS[symbol]["decimals"],
    )

    return (
        symbol,
        direction,
        sweep_level,
        mss_level,
        fvg_low,
        fvg_high,
    )


def already_alerted(key, stage, cooldown):
    now = time.time()

    state_key = (key, stage)

    previous = last_alert.get(state_key, 0)

    if now - previous < cooldown:
        return True

    last_alert[state_key] = now
    return False


# ============================================================
# SESSION TRADE GATE
# ============================================================

def trade_allowed(symbol, session):
    if not ONE_TRADE_PER_SESSION:
        return True

    state = session_trade_count[symbol]

    if state["session"] != session:
        state["session"] = session
        state["count"] = 0

    return state["count"] < 1


def consume_trade(symbol, session):
    state = session_trade_count[symbol]

    if state["session"] != session:
        state["session"] = session
        state["count"] = 0

    state["count"] += 1
    daily_trade_count[symbol] += 1


# ============================================================
# MESSAGE HELPERS
# ============================================================

def fmt(symbol, value):
    if value is None:
        return "N/A"

    dec = MARKETS[symbol]["decimals"]

    return f"{float(value):,.{dec}f}"


def send_pre(symbol, direction, data, context):
    arrow = "🟢" if direction == "BUY" else "🔴"

    message = (
        "⚠️ *ADVANCE PRE-SIGNAL*\n\n"
        f"*{MARKETS[symbol]['execution']}*\n"
        f"{arrow} Potential *{direction}*\n\n"
        f"HTF: *1H*\n"
        f"PO3 phase: *{context['phase']}*\n"
        f"HTF bias: *{context['bias']}*\n"
        f"Current: *{fmt(symbol, data['price'])}*\n"
        f"Liquidity: *{fmt(symbol, data['liquidity'])}*\n"
        f"Distance: *{fmt(symbol, data['distance'])}*\n\n"
        "WAIT — NOT A TRADE\n"
        "Required:\n"
        "• HTF sweep\n"
        "• 15M MSS\n"
        "• displacement\n"
        "• FVG\n"
        "• 5M retest"
    )

    send_telegram(message)


def send_watch(
    symbol,
    direction,
    sweep,
    mss,
    fvg,
    context,
):
    arrow = "🟢" if direction == "BUY" else "🔴"

    message = (
        "👀 *PA WATCH*\n\n"
        f"*{MARKETS[symbol]['execution']}*\n"
        f"{arrow} *{direction} setup developing*\n\n"
        "✓ HTF location\n"
        "✓ HTF liquidity sweep\n"
        "✓ 15M MSS\n"
        "✓ 15M FVG\n\n"
        f"Sweep: *{fmt(symbol, sweep['level'])}*\n"
        f"MSS: *{fmt(symbol, mss['level'])}*\n"
        f"FVG: *{fmt(symbol, fvg['low'])} → "
        f"{fmt(symbol, fvg['high'])}*\n"
        f"PO3: *{context['phase']}*\n\n"
        "WAIT FOR 5M RETEST + CONFIRMATION"
    )

    send_telegram(message)


def send_trade(
    symbol,
    direction,
    setup_type,
    entry,
    sl,
    targets,
    lot,
    sweep,
    mss,
    fvg,
    context,
    session,
):
    arrow = "📈" if direction == "BUY" else "📉"

    rr = targets["rr"]

    message = (
        "🚨 *PA-SUPREME TRADE SIGNAL*\n\n"
        f"*{MARKETS[symbol]['execution']}*\n"
        f"{arrow} *{direction}*\n"
        f"Setup: *{setup_type}*\n\n"
        f"Entry: *{fmt(symbol, entry)}*\n"
        f"SL: *{fmt(symbol, sl)}*\n\n"
        f"TP1: *{fmt(symbol, targets['tp1'])}*\n"
        f"TP2: *{fmt(symbol, targets['tp2'])}*\n"
        f"TP3: *{fmt(symbol, targets['tp3'])}*\n\n"
        f"RR: *1:{rr:.2f}* (structure-based)\n"
        f"Risk: *${RISK_PER_TRADE:.2f}*\n"
        f"Lot estimate: *{lot}*\n\n"
        "CONFIRMATION\n"
        "✓ 1H HTF / PO3\n"
        "✓ HTF liquidity sweep\n"
        "✓ 15M MSS\n"
        "✓ 15M displacement\n"
        "✓ FVG\n"
        "✓ 5M FVG retest\n\n"
        f"HTF sweep: *{fmt(symbol, sweep['level'])}*\n"
        f"15M MSS: *{fmt(symbol, mss['level'])}*\n"
        f"FVG: *{fmt(symbol, fvg['low'])} → "
        f"{fmt(symbol, fvg['high'])}*\n"
        f"PO3: *{context['phase']}*\n"
        f"Session: *{session}*\n\n"
        "Price Action only.\n"
        "No EMA / RSI / MACD / ADX scoring.\n"
        "RR has no artificial maximum; TP3 must come from valid structure."
    )

    send_telegram(message)


# ============================================================
# FULL SETUP PROCESS
# ============================================================

def process_symbol(symbol):
    try:
        if weekend_block():
            return

        session = current_session(symbol)

        if session is None:
            return

        frames = get_frames(symbol)

        if frames is None:
            return

        df1 = frames["1H"]
        df15 = frames["15M"]
        df5 = frames["5M"]

        if len(df1) < 30 or len(df15) < 30 or len(df5) < 30:
            return

        context = po3_context(df1)

        # ----------------------------------------------------
        # PRE-SIGNAL
        # ----------------------------------------------------

        for direction in ("BUY", "SELL"):
            pre = pre_signal(
                symbol,
                frames,
                direction,
            )

            if pre is None:
                continue

            pre_key = (
                symbol,
                direction,
                round(
                    pre["liquidity"],
                    MARKETS[symbol]["decimals"],
                ),
            )

            if not already_alerted(
                pre_key,
                "PRE",
                PRE_COOLDOWN,
            ):
                send_pre(
                    symbol,
                    direction,
                    pre,
                    context,
                )

        # ----------------------------------------------------
        # HTF SWEEP
        # ----------------------------------------------------

        sweep = detect_htf_sweep(df1)

        if sweep is None:
            return

        direction = sweep["direction"]

        # ----------------------------------------------------
        # 15M MSS
        # ----------------------------------------------------

        mss = structure_shift(
            df15,
            direction,
        )

        if mss is None:
            return

        # ----------------------------------------------------
        # DISPLACEMENT
        # ----------------------------------------------------

        if not displacement_ok(
            df15,
            direction,
        ):
            return

        # ----------------------------------------------------
        # FVG
        # ----------------------------------------------------

        fvg = find_recent_fvg(
            df15,
            direction,
        )

        if fvg is None:
            return

        key = setup_id(
            symbol,
            direction,
            sweep,
            mss,
            fvg,
        )

        # ----------------------------------------------------
        # WATCH
        # ----------------------------------------------------

        if not already_alerted(
            key,
            "WATCH",
            WATCH_COOLDOWN,
        ):
            send_watch(
                symbol,
                direction,
                sweep,
                mss,
                fvg,
                context,
            )

        # ----------------------------------------------------
        # 5M RETEST
        # ----------------------------------------------------

        confirmation = fvg_retest_confirmation(
            df5,
            fvg,
            direction,
        )

        if confirmation is None:
            return

        # ----------------------------------------------------
        # DUPLICATE TRADE PROTECTION
        # ----------------------------------------------------

        if already_alerted(
            key,
            "TRADE",
            TRADE_COOLDOWN,
        ):
            return

        if not trade_allowed(
            symbol,
            session,
        ):
            log.info(
                "%s rejected: one trade/session gate",
                symbol,
            )
            return

        entry = float(
            confirmation["entry"]
        )

        # ----------------------------------------------------
        # SL
        # ----------------------------------------------------

        sl_data = calculate_sl(
            symbol,
            direction,
            entry,
            sweep,
            mss,
        )

        if sl_data is None:
            return

        sl, sl_distance = sl_data

        # ----------------------------------------------------
        # TP
        # ----------------------------------------------------

        targets = adaptive_targets(
            frames,
            direction,
            entry,
            sl_distance,
        )

        if targets is None:
            log.info(
                "%s %s rejected: RR < %.2f",
                symbol,
                direction,
                MIN_RR,
            )
            return

        lot = lot_size(
            symbol,
            sl_distance,
        )

        # ----------------------------------------------------
        # TRADE
        # ----------------------------------------------------

        send_trade(
            symbol,
            direction,
            "HTF SWEEP + MSS + FVG RETEST",
            entry,
            sl,
            targets,
            lot,
            sweep,
            mss,
            fvg,
            context,
            session,
        )

        log_signal(
            symbol=symbol,
            direction=direction,
            stage="TRADE",
            setup="HTF_SWEEP_MSS_FVG_RETEST",
            price=entry,
            sl=sl,
            tp1=targets["tp1"],
            tp2=targets["tp2"],
            tp3=targets["tp3"],
            rr=targets["rr"],
            session=session,
            sweep=sweep["level"],
            mss=mss["level"],
            fvg=f"{fvg['low']}->{fvg['high']}",
        )

        consume_trade(
            symbol,
            session,
        )

        setup_memory[key] = time.time()

        log.info(
            "TRADE %s %s entry=%s sl=%s tp=%s rr=%.2f",
            symbol,
            direction,
            entry,
            sl,
            targets["tp3"],
            targets["rr"],
        )

    except Exception as exc:
        log.exception(
            "process_symbol failed %s: %s",
            symbol,
            exc,
        )


# ============================================================
# STARTUP
# ============================================================

def startup_message():
    return (
        "⚡ *PA-SUPREME-2026 LIVE*\n\n"
        "1H = HTF / PO3 location\n"
        "1H = liquidity sweep\n"
        "15M = MSS + displacement\n"
        "15M = FVG\n"
        "5M = FVG retest trigger\n\n"
        f"⚠️ PRE = {PRE_ATR_DISTANCE:.2f} ATR warning\n"
        f"⚖️ RR = {MIN_RR:.2f}R minimum → structure-based TP\n"
        "🛑 Closed candles for confirmation\n"
        "🚫 No EMA / RSI / MACD / ADX scoring\n"
        f"🌐 Markets = {len(SYMBOLS)}\n"
        f"⏱ Scan = {SCAN_INTERVAL:.1f}s\n"
        f"📡 Data refresh = {DATA_REFRESH_INTERVAL:.1f}s\n\n"
        "PRE → WATCH → TRADE"
    )


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    log.info(
        "%s STARTED | scan=%.1fs refresh=%.1fs",
        SYSTEM_VERSION,
        SCAN_INTERVAL,
        DATA_REFRESH_INTERVAL,
    )

    if not TOKEN or not CHAT_ID:
        log.warning(
            "Telegram variables missing. "
            "Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in Railway."
        )

    send_telegram(startup_message())

    last_refresh = 0.0
    loop = 0

    while True:
        try:
            reset_daily_state()

            now = time.time()

            # ------------------------------------------------
            # Refresh Yahoo data every 15 seconds.
            # ------------------------------------------------

            if now - last_refresh >= DATA_REFRESH_INTERVAL:
                log.info(
                    "DATA REFRESH | %s symbols",
                    len(SYMBOLS),
                )

                with ThreadPoolExecutor(
                    max_workers=len(SYMBOLS)
                ) as executor:

                    futures = {
                        executor.submit(
                            refresh_symbol,
                            symbol,
                        ): symbol
                        for symbol in SYMBOLS
                    }

                    for future in as_completed(futures):
                        symbol = futures[future]

                        try:
                            future.result()
                        except Exception as exc:
                            log.error(
                                "Refresh worker failed %s: %s",
                                symbol,
                                exc,
                            )

                last_refresh = time.time()

            # ------------------------------------------------
            # PA decision scan.
            # ------------------------------------------------

            log.info(
                "PA SCAN #%s | symbols=%s",
                loop,
                len(SYMBOLS),
            )

            with ThreadPoolExecutor(
                max_workers=len(SYMBOLS)
            ) as executor:

                futures = [
                    executor.submit(
                        process_symbol,
                        symbol,
                    )
                    for symbol in SYMBOLS
                ]

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        log.error(
                            "PA worker error: %s",
                            exc,
                        )

            # Remove old setup memory.
            cutoff = time.time() - SETUP_MEMORY_SECONDS

            old_keys = [
                key
                for key, timestamp in setup_memory.items()
                if timestamp < cutoff
            ]

            for key in old_keys:
                setup_memory.pop(key, None)

            loop += 1

            gc.collect()

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            log.info("Stopped by user")
            break

        except Exception as exc:
            log.exception(
                "MAIN LOOP ERROR: %s",
                exc,
            )

            time.sleep(3.0)


if __name__ == "__main__":
    main()
