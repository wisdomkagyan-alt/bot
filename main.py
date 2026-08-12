# ============================================================
# PEPPERSTONE PRICE ACTION HUNTER
# PA-SUPREME-2026 — SCALPER EDITION
#
# 1H  = LOCATION / MARKET STRUCTURE
# 15M = LIQUIDITY SWEEP + BOS / CHOCH
# 5M  = RETEST / ENTRY TRIGGER
#
# SETUPS:
#   1) LIQUIDITY REVERSAL
#   2) CONFIRMED BREAKOUT / RETEST
#
# Indicators removed from the decision engine:
#   EMA / RSI / ADX / VWAP / WaveTrend / AOX / Wizard AI
#
# ATR is used ONLY for an SL buffer.
#
# IMPORTANT:
#   This script generates Telegram trade alerts. It does not
#   place broker orders.
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

SYSTEM_VERSION = "PA-SUPREME-2026-SCALPER"

# ============================================================
# SECURITY
# ============================================================
# Set these as environment variables:
#   TOKEN="your_new_bot_token"
#   CHAT_ID="your_chat_id"
#
# DO NOT hard-code the Telegram bot token.
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
# PRIORITY MARKETS
# ============================================================
PRIORITY_MARKETS = [
    "XAU/USD", "NAS100", "SPX500", "EUR/USD", "GBP/JPY",
    "NIFTY50", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS",
]

# ============================================================
# MARKET DATA
# ============================================================
MARKETS = {
    "XAU/USD": {
        "data": "GC=F",
        "execution": "XAUUSD.Qraw",
        "decimals": 2,
        "market_type": "global",
        "min_sl": 1.50,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["Asian Precision", "London", "NY+London", "NY Killzone"],
    },
    "NAS100": {
        "data": "^NDX",
        "execution": "NAS100",
        "decimals": 1,
        "market_type": "global",
        "min_sl": 12.0,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["London", "NY+London", "NY Killzone"],
    },
    "SPX500": {
        "data": "^GSPC",
        "execution": "SPX500",
        "decimals": 1,
        "market_type": "global",
        "min_sl": 6.0,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["London", "NY+London", "NY Killzone"],
    },
    "EUR/USD": {
        "data": "EURUSD=X",
        "execution": "EURUSD",
        "decimals": 5,
        "market_type": "global",
        "min_sl": 0.00025,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["Asian Precision", "London", "NY+London", "NY Killzone"],
    },
    "GBP/JPY": {
        "data": "GBPJPY=X",
        "execution": "GBPJPY",
        "decimals": 3,
        "market_type": "global",
        "min_sl": 0.040,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["Asian Precision", "London", "NY+London", "NY Killzone"],
    },

    "NIFTY50": {
        "data": "^NSEI",
        "execution": "NIFTY50",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 15.0,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "BANKNIFTY": {
        "data": "^NSEBANK",
        "execution": "BANKNIFTY",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 20.0,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "SENSEX": {
        "data": "^BSESN",
        "execution": "SENSEX",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 40.0,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "RELIANCE": {
        "data": "RELIANCE.NS",
        "execution": "RELIANCE",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 5.0,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
    "TCS": {
        "data": "TCS.NS",
        "execution": "TCS",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 8.0,
        "sl_buffer": 0.10,
        "rr": 2.00,
        "daily_cap": 2,
        "sessions": ["India Open", "India Midday", "India Close"],
    },
}

# ============================================================
# RISK / EXECUTION
# ============================================================
RISK_PER_TRADE = 50.0

DOLLAR_PER_POINT = {
    "XAU/USD": 100,
    "NAS100": 10,
    "SPX500": 10,
    "EUR/USD": 100000,
    "GBP/JPY": 1000,
    "NIFTY50": 50,
    "BANKNIFTY": 20,
    "SENSEX": 10,
    "RELIANCE": 1,
    "TCS": 1,
}

LOT_CAP = {
    "XAU/USD": 1.50,
    "NAS100": 2.00,
    "SPX500": 2.00,
    "EUR/USD": 3.00,
    "GBP/JPY": 2.00,
    "NIFTY50": 50.0,
    "BANKNIFTY": 50.0,
    "SENSEX": 50.0,
    "RELIANCE": 500.0,
    "TCS": 500.0,
}

EXECUTION_BUFFER = {
    "XAU/USD": 0.15,
    "NAS100": 1.50,
    "SPX500": 1.00,
    "EUR/USD": 0.00005,
    "GBP/JPY": 0.010,
    "NIFTY50": 1.00,
    "BANKNIFTY": 2.00,
    "SENSEX": 3.00,
    "RELIANCE": 0.50,
    "TCS": 0.50,
}

MAX_DAILY_LOSS = -300.0
MAX_CONSECUTIVE_LOSSES = 3

# ============================================================
# PRICE ACTION SETTINGS
# ============================================================
SWING_LEFT = 2
SWING_RIGHT = 2

ZONE_LOOKBACK_1H = 80
ZONE_LOOKBACK_15M = 60

LIQUIDITY_LOOKBACK = 8
BOS_LOOKBACK = 5

REJECTION_WICK_RATIO = 1.30
DISPLACEMENT_BODY_MULT = 1.20

ZONE_TOLERANCE_ATR = 0.35
RETEST_TOLERANCE_ATR = 0.25

MIN_PA_SCORE = 8
MIN_RR = 1.80

# Only one scalp/reversal signal per symbol per session.
SIGNAL_ONE_PER_SESSION = True

# Separate cooldown for breakout/reversal alerts.
SIGNAL_COOLDOWN = 900

# Correlated instruments: maximum one signal in a group
# during the correlation window.
CORRELATION_BLOCK = True
MAX_CORRELATED_SIGNALS = 1
CORRELATION_WINDOW = 1800

CORRELATED_GROUPS = [
    ["NAS100", "SPX500"],
    ["EUR/USD", "GBP/JPY"],
    ["NIFTY50", "BANKNIFTY", "SENSEX"],
    ["RELIANCE", "TCS"],
]

# ============================================================
# LOOP SETTINGS
# ============================================================
# Yahoo Finance is not a broker-grade real-time feed.
# 30 seconds is intentionally used instead of hammering
# the API every second.
SCAN_INTERVAL = 30

# ============================================================
# STATE
# ============================================================
daily_pnl = 0.0
consecutive_losses = 0
last_reset_date = datetime.now(timezone.utc).date()

daily_signal_count = {s: 0 for s in PRIORITY_MARKETS}
session_signal_count = {
    s: {"session": None, "count": 0} for s in PRIORITY_MARKETS
}
last_signal_time = {}
last_signal_direction = {}
last_signal_type = {}

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

    if pnl < 0:
        consecutive_losses += 1
    else:
        consecutive_losses = 0


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
                json={
                    "chat_id": CHAT_ID,
                    "text": message,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )

            if response.status_code == 200:
                return True

            log.error(
                "Telegram HTTP %s: %s",
                response.status_code,
                response.text[:300],
            )

        except Exception as exc:
            log.error("Telegram attempt %s failed: %s", attempt + 1, exc)

        time.sleep(2)

    return False

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
# SESSION ENGINE
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

    # UTC global sessions.
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

    if now.weekday() == 5:
        return True

    if now.weekday() == 6 and now.hour < 21:
        return True

    return False

# ============================================================
# DATA FETCH
# ============================================================
def fetch_yf(ticker, period, interval):
    for attempt in range(3):
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
                time.sleep(1)
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            raw.columns = [str(c).lower() for c in raw.columns]

            required = ["open", "high", "low", "close"]
            if any(c not in raw.columns for c in required):
                return None

            if "volume" not in raw.columns:
                raw["volume"] = 0

            df = raw[
                ["open", "high", "low", "close", "volume"]
            ].copy()

            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            df = df.replace([math.inf, -math.inf], pd.NA)
            df = df.dropna(subset=["open", "high", "low", "close"])
            df = df.drop_duplicates()

            if df.empty:
                return None

            return df.reset_index(drop=True)

        except Exception as exc:
            log.error(
                "Yahoo fetch failed %s %s attempt %s: %s",
                ticker,
                interval,
                attempt + 1,
                exc,
            )
            time.sleep(1)

    return None


def fetch_timeframes(symbol):
    ticker = MARKETS[symbol]["data"]

    # Current intraday data:
    # 5M -> entry trigger
    # 15M -> setup
    # 1H -> location
    df_5m = fetch_yf(ticker, "60d", "5m")
    df_15m = fetch_yf(ticker, "60d", "15m")
    df_1h = fetch_yf(ticker, "60d", "1h")

    if any(x is None or len(x) < 50 for x in [df_5m, df_15m, df_1h]):
        return None

    return {
        "5M": df_5m,
        "15M": df_15m,
        "1H": df_1h,
    }

# ============================================================
# BASIC PRICE-ACTION HELPERS
# ============================================================
def candle_body(c):
    return abs(float(c["close"]) - float(c["open"]))


def candle_range(c):
    return max(0.0, float(c["high"]) - float(c["low"]))


def bullish_candle(c):
    return float(c["close"]) > float(c["open"])


def bearish_candle(c):
    return float(c["close"]) < float(c["open"])


def average_body(df, length=10):
    bodies = (df["close"] - df["open"]).abs()
    value = bodies.tail(length).mean()
    return float(value) if not pd.isna(value) else 0.0


def atr_value(df, period=14):
    if len(df) < period + 2:
        return 0.0

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = tr.rolling(period).mean().iloc[-1]

    if pd.isna(atr):
        return 0.0

    return float(atr)

# ============================================================
# SWING DETECTION
# ============================================================
def swing_highs(df):
    highs = []

    if len(df) < SWING_LEFT + SWING_RIGHT + 1:
        return highs

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT
    ):
        value = float(df["high"].iloc[i])

        left = df["high"].iloc[
            i - SWING_LEFT:i
        ]

        right = df["high"].iloc[
            i + 1:i + SWING_RIGHT + 1
        ]

        if value > float(left.max()) and value >= float(right.max()):
            highs.append((i, value))

    return highs


def swing_lows(df):
    lows = []

    if len(df) < SWING_LEFT + SWING_RIGHT + 1:
        return lows

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT
    ):
        value = float(df["low"].iloc[i])

        left = df["low"].iloc[
            i - SWING_LEFT:i
        ]

        right = df["low"].iloc[
            i + 1:i + SWING_RIGHT + 1
        ]

        if value < float(left.min()) and value <= float(right.min()):
            lows.append((i, value))

    return lows

# ============================================================
# SUPPLY / DEMAND
# ============================================================
def find_demand_zone(df):
    """
    Finds a recent bullish displacement and uses the candle/base
    immediately before the displacement as the demand zone.
    """
    work = df.tail(ZONE_LOOKBACK_1H).reset_index(drop=True)

    if len(work) < 15:
        return None

    avg_body = average_body(work, 10)

    if avg_body <= 0:
        return None

    candidates = []

    for i in range(3, len(work)):
        c = work.iloc[i]
        body = candle_body(c)

        if not bullish_candle(c):
            continue

        if body < avg_body * DISPLACEMENT_BODY_MULT:
            continue

        prior_high = float(work["high"].iloc[max(0, i - 5):i].max())

        if float(c["close"]) <= prior_high:
            continue

        base = work.iloc[i - 1]

        low = min(
            float(base["open"]),
            float(base["close"]),
            float(base["low"]),
        )

        high = max(
            float(base["open"]),
            float(base["close"]),
            float(base["high"]),
        )

        candidates.append({
            "low": low,
            "high": high,
            "index": i,
        })

    if not candidates:
        return None

    return candidates[-1]


def find_supply_zone(df):
    """
    Finds a recent bearish displacement and uses the candle/base
    immediately before the displacement as the supply zone.
    """
    work = df.tail(ZONE_LOOKBACK_1H).reset_index(drop=True)

    if len(work) < 15:
        return None

    avg_body = average_body(work, 10)

    if avg_body <= 0:
        return None

    candidates = []

    for i in range(3, len(work)):
        c = work.iloc[i]
        body = candle_body(c)

        if not bearish_candle(c):
            continue

        if body < avg_body * DISPLACEMENT_BODY_MULT:
            continue

        prior_low = float(work["low"].iloc[max(0, i - 5):i].min())

        if float(c["close"]) >= prior_low:
            continue

        base = work.iloc[i - 1]

        low = min(
            float(base["open"]),
            float(base["close"]),
            float(base["low"]),
        )

        high = max(
            float(base["open"]),
            float(base["close"]),
            float(base["high"]),
        )

        candidates.append({
            "low": low,
            "high": high,
            "index": i,
        })

    if not candidates:
        return None

    return candidates[-1]

# ============================================================
# ZONE LOCATION
# ============================================================
def price_in_zone(price, zone, tolerance):
    if zone is None:
        return False

    return (
        float(zone["low"]) - tolerance
        <= price
        <= float(zone["high"]) + tolerance
    )


def near_demand(price, zone, atr):
    return price_in_zone(
        price,
        zone,
        atr * ZONE_TOLERANCE_ATR,
    )


def near_supply(price, zone, atr):
    return price_in_zone(
        price,
        zone,
        atr * ZONE_TOLERANCE_ATR,
    )

# ============================================================
# LIQUIDITY SWEEP
# ============================================================
def liquidity_sweep(df, direction):
    """
    BUY:
      current candle sweeps a previous low and closes back above it.

    SELL:
      current candle sweeps a previous high and closes back below it.
    """
    if len(df) < LIQUIDITY_LOOKBACK + 2:
        return False, None

    previous = df.iloc[
        -LIQUIDITY_LOOKBACK - 1:-1
    ]

    last = df.iloc[-1]

    previous_high = float(previous["high"].max())
    previous_low = float(previous["low"].min())

    if direction == "BUY":
        swept = float(last["low"]) < previous_low
        reclaimed = float(last["close"]) > previous_low

        return (
            swept and reclaimed,
            previous_low if swept and reclaimed else None,
        )

    swept = float(last["high"]) > previous_high
    reclaimed = float(last["close"]) < previous_high

    return (
        swept and reclaimed,
        previous_high if swept and reclaimed else None,
    )

# ============================================================
# REJECTION CANDLE
# ============================================================
def rejection_candle(df, direction):
    if len(df) < 2:
        return False

    c = df.iloc[-1]

    op = float(c["open"])
    cl = float(c["close"])
    hi = float(c["high"])
    lo = float(c["low"])

    body = abs(cl - op)

    if body <= 0:
        return False

    upper = hi - max(op, cl)
    lower = min(op, cl) - lo

    total = hi - lo

    if total <= 0:
        return False

    if direction == "BUY":
        close_position = (cl - lo) / total

        return (
            lower >= body * REJECTION_WICK_RATIO
            and cl > op
            and close_position >= 0.60
        )

    close_position = (hi - cl) / total

    return (
        upper >= body * REJECTION_WICK_RATIO
        and cl < op
        and close_position >= 0.60
    )

# ============================================================
# DISPLACEMENT
# ============================================================
def displacement(df, direction):
    if len(df) < 12:
        return False

    last = df.iloc[-1]
    body = candle_body(last)
    avg = average_body(df.iloc[:-1], 10)

    if avg <= 0:
        return False

    if body < avg * DISPLACEMENT_BODY_MULT:
        return False

    if direction == "BUY":
        return bullish_candle(last)

    return bearish_candle(last)

# ============================================================
# BOS / CHOCH
# ============================================================
def bos(df, direction):
    if len(df) < BOS_LOOKBACK + 2:
        return False, None

    last = df.iloc[-1]

    prior = df.iloc[
        -BOS_LOOKBACK - 1:-1
    ]

    if direction == "BUY":
        level = float(prior["high"].max())
        confirmed = float(last["close"]) > level

        return confirmed, level if confirmed else None

    level = float(prior["low"].min())
    confirmed = float(last["close"]) < level

    return confirmed, level if confirmed else None


def choch(df, direction):
    """
    Lightweight structure-shift confirmation.
    BOS remains the stronger confirmation.
    """
    if len(df) < 8:
        return False

    highs = swing_highs(df)
    lows = swing_lows(df)

    if direction == "BUY":
        if len(highs) < 1 or len(lows) < 1:
            return False

        last_high = highs[-1][1]
        return float(df.iloc[-1]["close"]) > last_high

    if len(highs) < 1 or len(lows) < 1:
        return False

    last_low = lows[-1][1]
    return float(df.iloc[-1]["close"]) < last_low

# ============================================================
# RETEST
# ============================================================
def retest_level(df, direction, level, atr):
    if level is None or len(df) < 3:
        return False

    tolerance = atr * RETEST_TOLERANCE_ATR
    last = df.iloc[-1]

    if direction == "BUY":
        touched = float(last["low"]) <= level + tolerance
        held = float(last["close"]) >= level
        return touched and held

    touched = float(last["high"]) >= level - tolerance
    held = float(last["close"]) <= level
    return touched and held

# ============================================================
# HIGHER-TIMEFRAME LOCATION
# ============================================================
def htf_location(df_1h, direction):
    atr = atr_value(df_1h)

    if atr <= 0:
        return False, None, None

    price = float(df_1h.iloc[-1]["close"])

    demand = find_demand_zone(df_1h)
    supply = find_supply_zone(df_1h)

    tolerance = atr * ZONE_TOLERANCE_ATR

    if direction == "BUY":
        return (
            near_demand(price, demand, atr),
            demand,
            supply,
        )

    return (
        near_supply(price, supply, atr),
        demand,
        supply,
    )

# ============================================================
# 15M REVERSAL SETUP
# ============================================================
def reversal_setup(df_1h, df_15m, direction):
    """
    A+ reversal:
      1H location
      15M liquidity sweep
      15M rejection
      15M BOS / CHOCH
    """
    atr_1h = atr_value(df_1h)
    atr_15m = atr_value(df_15m)

    if atr_1h <= 0 or atr_15m <= 0:
        return {
            "valid": False,
            "score": 0,
            "level": None,
            "sweep": None,
            "reason": "ATR unavailable",
        }

    price_1h = float(df_1h.iloc[-1]["close"])

    demand = find_demand_zone(df_1h)
    supply = find_supply_zone(df_1h)

    if direction == "BUY":
        location = near_demand(price_1h, demand, atr_1h)
    else:
        location = near_supply(price_1h, supply, atr_1h)

    if not location:
        return {
            "valid": False,
            "score": 0,
            "level": None,
            "sweep": None,
            "reason": "No 1H zone location",
        }

    swept, sweep_level = liquidity_sweep(df_15m, direction)

    if not swept:
        return {
            "valid": False,
            "score": 0,
            "level": None,
            "sweep": None,
            "reason": "No liquidity sweep",
        }

    rejection = rejection_candle(df_15m, direction)
    displacement_ok = displacement(df_15m, direction)
    bos_ok, bos_level = bos(df_15m, direction)
    choch_ok = choch(df_15m, direction)

    score = 2  # 1H location
    score += 2  # liquidity sweep

    if rejection:
        score += 1

    if bos_ok:
        score += 2

    if choch_ok:
        score += 1

    if displacement_ok:
        score += 1

    # Reversal must have structure confirmation.
    valid = (
        location
        and swept
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
        "reason": "Reversal confirmed" if valid else "Structure confirmation incomplete",
    }

# ============================================================
# BREAKOUT / RETEST
# ============================================================
def breakout_setup(df_1h, df_15m, df_5m, direction):
    """
    Confirmed breakout:
      1H opposing zone / structure
      15M close through structure
      15M displacement
      5M retest
      5M confirmation candle
    """
    atr_15m = atr_value(df_15m)
    atr_5m = atr_value(df_5m)

    if atr_15m <= 0 or atr_5m <= 0:
        return {
            "valid": False,
            "score": 0,
            "level": None,
            "reason": "ATR unavailable",
        }

    last_15 = df_15m.iloc[-1]
    last_5 = df_5m.iloc[-1]

    prior = df_15m.iloc[-BOS_LOOKBACK - 1:-1]

    if direction == "BUY":
        level = float(prior["high"].max())
        breakout = float(last_15["close"]) > level
        displacement_ok = displacement(df_15m, "BUY")

        retest = retest_level(
            df_5m,
            "BUY",
            level,
            atr_5m,
        )

        confirmation = (
            bullish_candle(last_5)
            and float(last_5["close"]) > level
        )

    else:
        level = float(prior["low"].min())
        breakout = float(last_15["close"]) < level
        displacement_ok = displacement(df_15m, "SELL")

        retest = retest_level(
            df_5m,
            "SELL",
            level,
            atr_5m,
        )

        confirmation = (
            bearish_candle(last_5)
            and float(last_5["close"]) < level
        )

    score = 0

    if breakout:
        score += 3

    if displacement_ok:
        score += 2

    if retest:
        score += 2

    if confirmation:
        score += 2

    valid = (
        breakout
        and displacement_ok
        and retest
        and confirmation
        and score >= 8
    )

    return {
        "valid": valid,
        "score": score,
        "level": level,
        "reason": "Breakout/retest confirmed" if valid else "Breakout incomplete",
    }

# ============================================================
# PA SCORE
# ============================================================
def quality_from_score(score):
    if score >= 10:
        return "GOD-TIER PA"
    if score >= 9:
        return "A+ PA"
    if score >= 8:
        return "A PA"
    return "SKIP"

# ============================================================
# CORRELATION BLOCKER
# ============================================================
def correlated_signal_block(symbol):
    if not CORRELATION_BLOCK:
        return False

    now = time.time()

    for group in CORRELATED_GROUPS:
        if symbol not in group:
            continue

        active = 0

        for other in group:
            timestamp = last_signal_time.get(other, 0)

            if now - timestamp < CORRELATION_WINDOW:
                active += 1

        if active >= MAX_CORRELATED_SIGNALS:
            log.info(
                "Correlation block: %s | group=%s",
                symbol,
                group,
            )
            return True

    return False

# ============================================================
# SESSION SIGNAL #1 GATE
# ============================================================
def session_gate(symbol, session):
    state = session_signal_count[symbol]

    if state["session"] != session:
        state["session"] = session
        state["count"] = 0

    if SIGNAL_ONE_PER_SESSION and state["count"] >= 1:
        return False

    return True


def consume_session_signal(symbol, session):
    state = session_signal_count[symbol]

    if state["session"] != session:
        state["session"] = session
        state["count"] = 0

    state["count"] += 1

# ============================================================
# DUPLICATE / COOLDOWN
# ============================================================
def duplicate_or_cooldown(symbol, direction, signal_type):
    now = time.time()

    last_time = last_signal_time.get(symbol, 0)
    last_dir = last_signal_direction.get(symbol)
    last_type = last_signal_type.get(symbol)

    if now - last_time < SIGNAL_COOLDOWN:
        return True

    if last_dir == direction and last_type == signal_type:
        return True

    return False

# ============================================================
# LEVELS
# ============================================================
def calculate_levels(
    symbol,
    direction,
    price,
    df_5m,
    df_15m,
    setup,
    signal_type,
):
    cfg = MARKETS[symbol]

    atr = atr_value(df_5m)

    if atr <= 0:
        atr = atr_value(df_15m)

    if atr <= 0:
        return None

    decimals = cfg["decimals"]
    buffer = max(
        cfg["min_sl"] * cfg["sl_buffer"],
        atr * 0.10,
    )

    if signal_type == "REVERSAL":
        sweep = setup.get("sweep")

        if sweep is not None:
            if direction == "BUY":
                sl_dist = max(
                    cfg["min_sl"],
                    price - float(sweep) + buffer,
                )
            else:
                sl_dist = max(
                    cfg["min_sl"],
                    float(sweep) - price + buffer,
                )
        else:
            sl_dist = max(cfg["min_sl"], atr * 0.80)

    else:
        level = setup.get("level")

        if direction == "BUY":
            sl_dist = max(
                cfg["min_sl"],
                price - float(level) + buffer,
            )
        else:
            sl_dist = max(
                cfg["min_sl"],
                float(level) - price + buffer,
            )

    # Protect against an accidental extreme SL.
    max_sl = max(cfg["min_sl"] * 3.0, atr * 2.0)

    if sl_dist > max_sl:
        return None

    rr = cfg["rr"]

    if rr < MIN_RR:
        return None

    if direction == "BUY":
        sl = price - sl_dist
        tp = price + sl_dist * rr
    else:
        sl = price + sl_dist
        tp = price - sl_dist * rr

    return (
        round(sl, decimals),
        round(tp, decimals),
        round(sl_dist, decimals),
        rr,
    )

# ============================================================
# LOT SIZE
# ============================================================
def lot_for_risk(symbol, sl_dist):
    if sl_dist <= 0:
        return 0.0

    dpp = DOLLAR_PER_POINT.get(symbol)

    if not dpp:
        return 0.0

    raw = RISK_PER_TRADE / (
        sl_dist * dpp
    )

    cap = LOT_CAP.get(symbol, raw)

    if symbol in {
        "NIFTY50",
        "BANKNIFTY",
        "SENSEX",
        "RELIANCE",
        "TCS",
    }:
        return float(max(1, round(min(raw, cap))))

    return round(
        max(0.01, min(raw, cap)),
        3,
    )

# ============================================================
# TARGET STRUCTURE
# ============================================================
def nearest_structure_target(
    df,
    direction,
    entry,
    rr_tp,
):
    highs = [x[1] for x in swing_highs(df)]
    lows = [x[1] for x in swing_lows(df)]

    if direction == "BUY":
        candidates = [
            x for x in highs
            if x > entry
        ]
        return min(candidates) if candidates else rr_tp

    candidates = [
        x for x in lows
        if x < entry
    ]

    return max(candidates) if candidates else rr_tp

# ============================================================
# LOGGING
# ============================================================
def log_signal(
    symbol,
    direction,
    score,
    signal_type,
    entry,
    sl,
    tp,
    session,
):
    row = [
        SYSTEM_VERSION,
        datetime.now(timezone.utc).isoformat(),
        symbol,
        direction,
        score,
        signal_type,
        entry,
        sl,
        tp,
        session,
    ]

    with log_lock:
        with open(
            "signals_log.csv",
            "a",
            newline="",
            encoding="utf-8",
        ) as f:
            writer = csv.writer(f)

            if os.path.getsize("signals_log.csv") == 0:
                writer.writerow([
                    "version",
                    "timestamp",
                    "symbol",
                    "direction",
                    "score",
                    "signal_type",
                    "entry",
                    "sl",
                    "tp",
                    "session",
                ])

            writer.writerow(row)

        with open(
            "signals_backup.csv",
            "a",
            newline="",
            encoding="utf-8",
        ) as f:
            csv.writer(f).writerow(row)

# ============================================================
# TELEGRAM MESSAGE
# ============================================================
def send_signal(
    symbol,
    direction,
    signal_type,
    score,
    session,
    entry,
    sl,
    tp,
    lot,
    setup,
):
    cfg = MARKETS[symbol]
    dec = cfg["decimals"]

    emoji = "📈" if direction == "BUY" else "📉"

    flag = (
        "🇮🇳 INDIA INTRADAY"
        if cfg["market_type"] == "india"
        else "🌍 GLOBAL"
    )

    quality = quality_from_score(score)

    sweep = setup.get("sweep")
    level = setup.get("level")

    msg = (
        f"⚡ *{SYSTEM_VERSION}*\n"
        f"*{cfg['execution']}* | {flag}\n\n"
        f"🔥 *{direction}* {emoji}\n"
        f"🚀 *Setup:* {signal_type}\n"
        f"⏱ *Structure:* 1H → 15M → 5M\n"
        f"⭐ *PA Score:* {score}/10\n"
        f"🏆 *Quality:* {quality}\n\n"
        f"📍 *Entry:* {entry:,.{dec}f}\n"
        f"🛑 *SL:* {sl:,.{dec}f}\n"
        f"🎯 *TP:* {tp:,.{dec}f}\n"
        f"⚖️ *RR:* 1:{cfg['rr']:.2f}\n"
        f"💵 *Lot:* {lot}\n\n"
        f"📌 *Session:* {session}\n"
        f"💧 *Liquidity:* "
        f"{'CONFIRMED' if sweep is not None else 'N/A'}\n"
        f"📐 *Structure Level:* "
        f"{f'{level:,.{dec}f}' if level is not None else 'N/A'}\n\n"
        f"✅ 1H Location\n"
        f"✅ 15M Price Action\n"
        f"✅ Liquidity / Structure\n"
        f"✅ 5M Trigger\n"
        f"✅ Risk Filter\n\n"
        f"🛡 *PRICE ACTION ONLY — NO INDICATOR SCORING*"
    )

    send_telegram(msg)

# ============================================================
# REVERSAL PROCESS
# ============================================================
def process_reversal(symbol, frames, session):
    df_1h = frames["1H"]
    df_15m = frames["15M"]
    df_5m = frames["5M"]

    for direction in ("BUY", "SELL"):
        setup = reversal_setup(
            df_1h,
            df_15m,
            direction,
        )

        if not setup["valid"]:
            continue

        # 5M must provide an entry trigger after 15M setup.
        level = setup.get("level")

        if level is None:
            continue

        atr_5m = atr_value(df_5m)

        if atr_5m <= 0:
            continue

        trigger = retest_level(
            df_5m,
            direction,
            float(level),
            atr_5m,
        )

        if not trigger:
            continue

        if not rejection_candle(df_5m, direction):
            continue

        if correlated_signal_block(symbol):
            return False

        if duplicate_or_cooldown(
            symbol,
            direction,
            "REVERSAL",
        ):
            continue

        price = float(df_5m.iloc[-1]["close"])

        if direction == "BUY":
            price += EXECUTION_BUFFER[symbol]
        else:
            price -= EXECUTION_BUFFER[symbol]

        levels = calculate_levels(
            symbol,
            direction,
            price,
            df_5m,
            df_15m,
            setup,
            "REVERSAL",
        )

        if levels is None:
            log.info(
                "%s reversal rejected: invalid SL/structure",
                symbol,
            )
            continue

        sl, tp, sl_dist, rr = levels

        # TP cannot be blindly forced through nearby structure.
        structural_tp = nearest_structure_target(
            df_15m,
            direction,
            price,
            tp,
        )

        if direction == "BUY":
            if structural_tp > price and structural_tp < tp:
                tp = structural_tp
        else:
            if structural_tp < price and structural_tp > tp:
                tp = structural_tp

        actual_rr = (
            abs(tp - price) / sl_dist
            if sl_dist > 0
            else 0
        )

        if actual_rr < MIN_RR:
            log.info(
                "%s reversal rejected: RR %.2f < %.2f",
                symbol,
                actual_rr,
                MIN_RR,
            )
            continue

        lot = lot_for_risk(symbol, sl_dist)

        score = min(10, setup["score"] + 1)

        log_signal(
            symbol,
            direction,
            score,
            "REVERSAL",
            price,
            sl,
            tp,
            session,
        )

        send_signal(
            symbol,
            direction,
            "LIQUIDITY REVERSAL",
            score,
            session,
            price,
            sl,
            tp,
            lot,
            setup,
        )

        with signal_lock:
            last_signal_time[symbol] = time.time()
            last_signal_direction[symbol] = direction
            last_signal_type[symbol] = "REVERSAL"

            daily_signal_count[symbol] += 1

            consume_session_signal(
                symbol,
                session,
            )

        log.info(
            "REVERSAL SIGNAL %s %s | entry=%s sl=%s tp=%s score=%s",
            symbol,
            direction,
            price,
            sl,
            tp,
            score,
        )

        return True

    return False

# ============================================================
# BREAKOUT PROCESS
# ============================================================
def process_breakout(symbol, frames, session):
    df_1h = frames["1H"]
    df_15m = frames["15M"]
    df_5m = frames["5M"]

    for direction in ("BUY", "SELL"):
        setup = breakout_setup(
            df_1h,
            df_15m,
            df_5m,
            direction,
        )

        if not setup["valid"]:
            continue

        if correlated_signal_block(symbol):
            return False

        if duplicate_or_cooldown(
            symbol,
            direction,
            "BREAKOUT",
        ):
            continue

        price = float(df_5m.iloc[-1]["close"])

        if direction == "BUY":
            price += EXECUTION_BUFFER[symbol]
        else:
            price -= EXECUTION_BUFFER[symbol]

        levels = calculate_levels(
            symbol,
            direction,
            price,
            df_5m,
            df_15m,
            setup,
            "BREAKOUT",
        )

        if levels is None:
            continue

        sl, tp, sl_dist, rr = levels

        actual_rr = (
            abs(tp - price) / sl_dist
            if sl_dist > 0
            else 0
        )

        if actual_rr < MIN_RR:
            continue

        lot = lot_for_risk(symbol, sl_dist)

        score = min(10, setup["score"] + 1)

        log_signal(
            symbol,
            direction,
            score,
            "BREAKOUT",
            price,
            sl,
            tp,
            session,
        )

        send_signal(
            symbol,
            direction,
            "BREAKOUT + RETEST",
            score,
            session,
            price,
            sl,
            tp,
            lot,
            setup,
        )

        with signal_lock:
            last_signal_time[symbol] = time.time()
            last_signal_direction[symbol] = direction
            last_signal_type[symbol] = "BREAKOUT"

            daily_signal_count[symbol] += 1

            consume_session_signal(
                symbol,
                session,
            )

        log.info(
            "BREAKOUT SIGNAL %s %s | entry=%s sl=%s tp=%s score=%s",
            symbol,
            direction,
            price,
            sl,
            tp,
            score,
        )

        return True

    return False

# ============================================================
# MASTER SYMBOL PROCESS
# ============================================================
def process_symbol(symbol):
    try:
        if weekend_block():
            return

        if daily_loss_lock():
            return

        if loss_streak_lock():
            return

        if daily_signal_count[symbol] >= MARKETS[symbol]["daily_cap"]:
            return

        ok, session = in_session(symbol)

        if not ok:
            return

        if session not in MARKETS[symbol]["sessions"]:
            return

        if not session_gate(symbol, session):
            return

        frames = fetch_timeframes(symbol)

        if frames is None:
            return

        # ----------------------------------------------------
        # REVERSAL FIRST
        # ----------------------------------------------------
        fired = process_reversal(
            symbol,
            frames,
            session,
        )

        if fired:
            return

        # ----------------------------------------------------
        # BREAKOUT SECOND
        # ----------------------------------------------------
        process_breakout(
            symbol,
            frames,
            session,
        )

    except Exception as exc:
        log.exception(
            "Symbol processing error %s: %s",
            symbol,
            exc,
        )

# ============================================================
# STARTUP MESSAGE
# ============================================================
def startup_message():
    return (
        f"⚡ *{SYSTEM_VERSION} LIVE*\n\n"
        f"📊 *PRICE ACTION ENGINE*\n"
        f"1H = Location / Structure\n"
        f"15M = Liquidity + BOS/CHOCH\n"
        f"5M = Retest + Trigger\n\n"
        f"🔥 *Setups*\n"
        f"1. Liquidity Reversal\n"
        f"2. Breakout + Retest\n\n"
        f"🇮🇳 NIFTY50 | BANKNIFTY | SENSEX\n"
        f"🏢 RELIANCE | TCS\n"
        f"🌍 XAU/USD | NAS100 | SPX500\n"
        f"💶 EUR/USD | GBP/JPY\n\n"
        f"🔒 Signal #1 per session\n"
        f"🛡 Correlation blocker\n"
        f"🛑 Daily loss lock\n"
        f"🛑 Consecutive-loss lock\n"
        f"⚖️ Minimum RR: {MIN_RR}\n\n"
        f"🚫 EMA / RSI / ADX / VWAP / Wizard AI removed\n"
        f"✅ Pure Price Action / Liquidity / Structure"
    )

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    log.info("%s STARTED", SYSTEM_VERSION)

    send_telegram(startup_message())

    loop = 0

    while True:
        try:
            reset_daily()
            watchdog()

            log.info(
                "Starting PA scan #%s | symbols=%s",
                loop,
                len(PRIORITY_MARKETS),
            )

            with ThreadPoolExecutor(
                max_workers=len(PRIORITY_MARKETS)
            ) as executor:

                futures = [
                    executor.submit(
                        process_symbol,
                        symbol,
                    )
                    for symbol in PRIORITY_MARKETS
                ]

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as exc:
                        log.error(
                            "Worker error: %s",
                            exc,
                        )

            loop += 1

            gc.collect()

            time.sleep(SCAN_INTERVAL)

        except KeyboardInterrupt:
            log.info("Stopped by user")
            break

        except Exception as exc:
            log.exception(
                "Main loop error: %s",
                exc,
            )
            time.sleep(SCAN_INTERVAL)


if __name__ == "__main__":
    main()
