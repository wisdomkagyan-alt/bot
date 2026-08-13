# ============================================================
# PEPPERSTONE PRICE ACTION HUNTER
# PA-SUPREME-2026 — ADVANCE PRICE-ACTION EDITION v3
#
# 1H  = LOCATION / MARKET STRUCTURE
# 15M = LIQUIDITY / BOS / CHOCH
# 5M  = ENTRY TRIGGER
#
# ALERT STAGES
#   ⚠️ PRE-SIGNAL  = setup approaching zone
#   👀 WATCH       = structure forming
#   🚨 TRADE       = confirmed PA entry
#
# IMPORTANT
#   This version uses Yahoo Finance as the market-data source.
#   It scans cached data every 1 second.
#   Yahoo data itself is refreshed every 15 seconds.
#
#   It is NOT a Pepperstone/MT5 native tick feed.
#
# ANTI-SPAM
#   PRE  = maximum one alert per symbol/direction/setup cycle
#   WATCH = maximum one alert per symbol/direction/structure cycle
#   TRADE = cooldown + daily/session protection
#
# TELEGRAM
#   Set:
#       TELEGRAM_TOKEN
#       TELEGRAM_CHAT_ID
#
# NEVER hard-code the Telegram token.
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


# ============================================================
# VERSION
# ============================================================

VERSION = "PA-SUPREME-2026-ADVANCE-v3"


# ============================================================
# TELEGRAM CONFIG
# ============================================================

TOKEN = os.getenv("TOKEN", "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")

# ============================================================
# ENGINE SETTINGS
# ============================================================

SCAN_INTERVAL = 1.0

DATA_REFRESH_INTERVAL = 15.0

PRE_SIGNAL_ATR = 0.75

PRE_SIGNAL_COOLDOWN = 900

WATCH_COOLDOWN = 600

TRADE_SIGNAL_COOLDOWN = 900

MIN_RR = 1.80

MAX_RR = 4.00

MIN_PA_SCORE = 8

ZONE_TOLERANCE_ATR = 0.35

RETEST_TOLERANCE_ATR = 0.25

SWING_LEFT = 2

SWING_RIGHT = 2

ZONE_LOOKBACK_1H = 80

LIQUIDITY_LOOKBACK = 8

BOS_LOOKBACK = 5

REJECTION_WICK_RATIO = 1.30

DISPLACEMENT_BODY_MULT = 1.20

RISK_PER_TRADE = 50.0

MAX_DAILY_LOSS = -300.0

MAX_CONSECUTIVE_LOSSES = 3

SIGNAL_ONE_PER_SESSION = True


# ============================================================
# MARKETS
# ============================================================

MARKETS = {

    "XAU/USD": {
        "data": "GC=F",
        "execution": "XAUUSD",
        "decimals": 2,
        "market_type": "global",
        "min_sl": 1.50,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "Asian Precision",
            "London",
            "NY+London",
            "NY Killzone",
        ],
    },

    "NAS100": {
        "data": "^NDX",
        "execution": "NAS100",
        "decimals": 1,
        "market_type": "global",
        "min_sl": 12.0,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "London",
            "NY+London",
            "NY Killzone",
        ],
    },

    "SPX500": {
        "data": "^GSPC",
        "execution": "SPX500",
        "decimals": 1,
        "market_type": "global",
        "min_sl": 6.0,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "London",
            "NY+London",
            "NY Killzone",
        ],
    },

    "EUR/USD": {
        "data": "EURUSD=X",
        "execution": "EURUSD",
        "decimals": 5,
        "market_type": "global",
        "min_sl": 0.00025,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "Asian Precision",
            "London",
            "NY+London",
            "NY Killzone",
        ],
    },

    "GBP/JPY": {
        "data": "GBPJPY=X",
        "execution": "GBPJPY",
        "decimals": 3,
        "market_type": "global",
        "min_sl": 0.040,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "Asian Precision",
            "London",
            "NY+London",
            "NY Killzone",
        ],
    },

    "NIFTY50": {
        "data": "^NSEI",
        "execution": "NIFTY50",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 15.0,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "India Open",
            "India Midday",
            "India Close",
        ],
    },

    "BANKNIFTY": {
        "data": "^NSEBANK",
        "execution": "BANKNIFTY",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 20.0,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "India Open",
            "India Midday",
            "India Close",
        ],
    },

    "SENSEX": {
        "data": "^BSESN",
        "execution": "SENSEX",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 40.0,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "India Open",
            "India Midday",
            "India Close",
        ],
    },

    "RELIANCE": {
        "data": "RELIANCE.NS",
        "execution": "RELIANCE",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 5.0,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "India Open",
            "India Midday",
            "India Close",
        ],
    },

    "TCS": {
        "data": "TCS.NS",
        "execution": "TCS",
        "decimals": 2,
        "market_type": "india",
        "min_sl": 8.0,
        "sl_buffer": 0.10,
        "daily_cap": 2,
        "sessions": [
            "India Open",
            "India Midday",
            "India Close",
        ],
    },
}


SYMBOLS = list(MARKETS.keys())


# ============================================================
# RISK / CONTRACT SETTINGS
# ============================================================

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


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)

log = logging.getLogger(VERSION)


http = requests.Session()

cache_lock = Lock()

signal_lock = Lock()

log_lock = Lock()


# ============================================================
# GLOBAL STATE
# ============================================================

frames_cache = {}

frames_time = {}


# ------------------------------------------------------------
# PRE STATE
#
# Structure:
#
# pre_state[key] = {
#     "time": ...,
#     "zone_id": ...,
#     "session": ...
# }
# ------------------------------------------------------------

pre_state = {}


# ------------------------------------------------------------
# WATCH STATE
# ------------------------------------------------------------

watch_state = {}


# ------------------------------------------------------------
# TRADE STATE
# ------------------------------------------------------------

last_trade = {}

last_trade_direction = {}

last_trade_setup = {}


# ------------------------------------------------------------
# DAILY STATE
# ------------------------------------------------------------

daily_count = {
    symbol: 0
    for symbol in SYMBOLS
}


session_count = {
    symbol: {
        "session": None,
        "count": 0,
    }
    for symbol in SYMBOLS
}


daily_pnl = 0.0

consecutive_losses = 0

reset_date = datetime.now(timezone.utc).date()


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):

    if not TOKEN or not CHAT_ID:

        log.warning(
            "Telegram not configured. "
            "Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID."
        )

        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:

        response = http.post(
            url,
            json=payload,
            timeout=10,
        )

        if response.status_code == 200:

            return True

        log.error(
            "Telegram HTTP %s: %s",
            response.status_code,
            response.text[:300],
        )

        return False

    except Exception as exc:

        log.error(
            "Telegram error: %s",
            exc,
        )

        return False


# ============================================================
# SESSION
# ============================================================

def get_session(symbol):

    now = datetime.now(timezone.utc)

    hm = (
        now.hour * 60
        + now.minute
    )

    market_type = MARKETS[symbol]["market_type"]

    if market_type == "india":

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


# ============================================================
# WEEKEND
# ============================================================

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

def fetch_yahoo(ticker):

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

            if raw is None or raw.empty:

                time.sleep(0.5)

                continue

            if isinstance(
                raw.columns,
                pd.MultiIndex,
            ):

                raw.columns = (
                    raw.columns
                    .get_level_values(0)
                )

            raw.columns = [
                str(c).lower()
                for c in raw.columns
            ]

            required = [
                "open",
                "high",
                "low",
                "close",
            ]

            if any(
                col not in raw.columns
                for col in required
            ):

                return None

            if "volume" not in raw.columns:

                raw["volume"] = 0

            df = raw[
                [
                    "open",
                    "high",
                    "low",
                    "close",
                    "volume",
                ]
            ].copy()

            for column in df.columns:

                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

            df = df.replace(
                [math.inf, -math.inf],
                pd.NA,
            )

            df = df.dropna(
                subset=[
                    "open",
                    "high",
                    "low",
                    "close",
                ]
            )

            df = df[
                ~df.index.duplicated(
                    keep="last"
                )
            ]

            if len(df) < 80:

                return None

            return df

        except Exception as exc:

            log.error(
                "Data fetch failed %s: %s",
                ticker,
                exc,
            )

            time.sleep(0.5)

    return None


# ============================================================
# RESAMPLING
# ============================================================

def resample_ohlc(df, rule):

    result = df.resample(rule).agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )

    return result.dropna(
        subset=[
            "open",
            "high",
            "low",
            "close",
        ]
    )


# ============================================================
# REFRESH SYMBOL
# ============================================================

def refresh_symbol(symbol):

    ticker = MARKETS[symbol]["data"]

    base = fetch_yahoo(ticker)

    if base is None:

        return None

    frames = {

        "5M": base.copy(),

        "15M": resample_ohlc(
            base,
            "15min",
        ),

        "1H": resample_ohlc(
            base,
            "1h",
        ),
    }

    if any(
        len(frame) < 50
        for frame in frames.values()
    ):

        return None

    with cache_lock:

        frames_cache[symbol] = frames

        frames_time[symbol] = time.time()

    return frames


# ============================================================
# GET CACHED FRAMES
# ============================================================

def get_frames(symbol):

    now = time.time()

    with cache_lock:

        cached = frames_cache.get(symbol)

        cached_at = frames_time.get(
            symbol,
            0,
        )

    if (
        cached is not None
        and now - cached_at
        < DATA_REFRESH_INTERVAL
    ):

        return cached

    return refresh_symbol(symbol)


# ============================================================
# CANDLE HELPERS
# ============================================================

def candle_body(candle):

    return abs(
        float(candle["close"])
        - float(candle["open"])
    )


def bullish(candle):

    return (
        float(candle["close"])
        > float(candle["open"])
    )


def bearish(candle):

    return (
        float(candle["close"])
        < float(candle["open"])
    )


def average_body(df, length=10):

    value = (
        df["close"]
        - df["open"]
    ).abs().tail(length).mean()

    if pd.isna(value):

        return 0.0

    return float(value)


# ============================================================
# ATR
# ============================================================

def atr_value(df, period=14):

    if len(df) < period + 2:

        return 0.0

    high = df["high"].astype(float)

    low = df["low"].astype(float)

    close = df["close"].astype(float)

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,

            (
                high
                - previous_close
            ).abs(),

            (
                low
                - previous_close
            ).abs(),
        ],
        axis=1,
    ).max(axis=1)

    value = (
        true_range
        .rolling(period)
        .mean()
        .iloc[-1]
    )

    if pd.isna(value):

        return 0.0

    return float(value)


# ============================================================
# SWING HIGHS
# ============================================================

def swing_highs(df):

    result = []

    minimum = (
        SWING_LEFT
        + SWING_RIGHT
        + 1
    )

    if len(df) < minimum:

        return result

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT,
    ):

        value = float(
            df["high"].iloc[i]
        )

        left = df["high"].iloc[
            i - SWING_LEFT:i
        ]

        right = df["high"].iloc[
            i + 1:
            i + SWING_RIGHT + 1
        ]

        if (
            value > float(left.max())
            and value >= float(right.max())
        ):

            result.append(
                (i, value)
            )

    return result


# ============================================================
# SWING LOWS
# ============================================================

def swing_lows(df):

    result = []

    minimum = (
        SWING_LEFT
        + SWING_RIGHT
        + 1
    )

    if len(df) < minimum:

        return result

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT,
    ):

        value = float(
            df["low"].iloc[i]
        )

        left = df["low"].iloc[
            i - SWING_LEFT:i
        ]

        right = df["low"].iloc[
            i + 1:
            i + SWING_RIGHT + 1
        ]

        if (
            value < float(left.min())
            and value <= float(right.min())
        ):

            result.append(
                (i, value)
            )

    return result


# ============================================================
# DEMAND ZONE
# ============================================================

def find_demand_zone(df):

    work = (
        df.tail(ZONE_LOOKBACK_1H)
        .reset_index(drop=True)
    )

    if len(work) < 15:

        return None

    average = average_body(
        work,
        10,
    )

    if average <= 0:

        return None

    candidates = []

    for i in range(
        3,
        len(work),
    ):

        candle = work.iloc[i]

        if not bullish(candle):

            continue

        if (
            candle_body(candle)
            < average * DISPLACEMENT_BODY_MULT
        ):

            continue

        previous_high = float(
            work["high"]
            .iloc[
                max(0, i - 5):i
            ]
            .max()
        )

        if (
            float(candle["close"])
            <= previous_high
        ):

            continue

        base = work.iloc[i - 1]

        candidates.append(
            {
                "low": min(
                    float(base["open"]),
                    float(base["close"]),
                    float(base["low"]),
                ),

                "high": max(
                    float(base["open"]),
                    float(base["close"]),
                    float(base["high"]),
                ),

                "index": i,
            }
        )

    return (
        candidates[-1]
        if candidates
        else None
    )


# ============================================================
# SUPPLY ZONE
# ============================================================

def find_supply_zone(df):

    work = (
        df.tail(ZONE_LOOKBACK_1H)
        .reset_index(drop=True)
    )

    if len(work) < 15:

        return None

    average = average_body(
        work,
        10,
    )

    if average <= 0:

        return None

    candidates = []

    for i in range(
        3,
        len(work),
    ):

        candle = work.iloc[i]

        if not bearish(candle):

            continue

        if (
            candle_body(candle)
            < average * DISPLACEMENT_BODY_MULT
        ):

            continue

        previous_low = float(
            work["low"]
            .iloc[
                max(0, i - 5):i
            ]
            .min()
        )

        if (
            float(candle["close"])
            >= previous_low
        ):

            continue

        base = work.iloc[i - 1]

        candidates.append(
            {
                "low": min(
                    float(base["open"]),
                    float(base["close"]),
                    float(base["low"]),
                ),

                "high": max(
                    float(base["open"]),
                    float(base["close"]),
                    float(base["high"]),
                ),

                "index": i,
            }
        )

    return (
        candidates[-1]
        if candidates
        else None
    )


# ============================================================
# ZONE TEST
# ============================================================

def price_in_zone(
    price,
    zone,
    tolerance,
):

    if zone is None:

        return False

    return (
        zone["low"] - tolerance
        <= price
        <= zone["high"] + tolerance
    )


# ============================================================
# APPROACH TO ZONE
# ============================================================

def approach_to_zone(
    price,
    zone,
    atr,
    direction,
):

    if zone is None or atr <= 0:

        return False, None

    tolerance = (
        atr * ZONE_TOLERANCE_ATR
    )

    limit = (
        atr * PRE_SIGNAL_ATR
    )

    low = float(zone["low"])

    high = float(zone["high"])

    if direction == "BUY":

        if price < low - tolerance:

            return False, None

        if (
            low - tolerance
            <= price
            <= high + tolerance
        ):

            return True, 0.0

        distance = price - high

        return (
            distance <= limit,
            max(0.0, distance),
        )

    if price > high + tolerance:

        return False, None

    if (
        low - tolerance
        <= price
        <= high + tolerance
    ):

        return True, 0.0

    distance = low - price

    return (
        distance <= limit,
        max(0.0, distance),
    )


# ============================================================
# LIQUIDITY SWEEP
# ============================================================

def liquidity_sweep(
    df,
    direction,
):

    if len(df) < (
        LIQUIDITY_LOOKBACK + 3
    ):

        return False, None

    end = len(df) - 2

    start = (
        end - LIQUIDITY_LOOKBACK
    )

    previous = df.iloc[
        start:end
    ]

    candle = df.iloc[end]

    previous_high = float(
        previous["high"].max()
    )

    previous_low = float(
        previous["low"].min()
    )

    if direction == "BUY":

        swept = (
            float(candle["low"])
            < previous_low
        )

        reclaimed = (
            float(candle["close"])
            > previous_low
        )

        valid = swept and reclaimed

        return (
            valid,
            previous_low if valid else None,
        )

    swept = (
        float(candle["high"])
        > previous_high
    )

    reclaimed = (
        float(candle["close"])
        < previous_high
    )

    valid = swept and reclaimed

    return (
        valid,
        previous_high if valid else None,
    )


# ============================================================
# REJECTION CANDLE
# ============================================================

def rejection_candle(
    df,
    direction,
):

    if len(df) < 3:

        return False

    candle = df.iloc[-2]

    op = float(candle["open"])

    close = float(candle["close"])

    high = float(candle["high"])

    low = float(candle["low"])

    body = abs(close - op)

    total = high - low

    if body <= 0 or total <= 0:

        return False

    upper_wick = (
        high - max(op, close)
    )

    lower_wick = (
        min(op, close) - low
    )

    if direction == "BUY":

        return (
            lower_wick
            >= body * REJECTION_WICK_RATIO
            and close > op
            and (close - low) / total
            >= 0.60
        )

    return (
        upper_wick
        >= body * REJECTION_WICK_RATIO
        and close < op
        and (high - close) / total
        >= 0.60
    )


# ============================================================
# DISPLACEMENT
# ============================================================

def displacement(
    df,
    direction,
):

    if len(df) < 12:

        return False

    candle = df.iloc[-2]

    previous = df.iloc[:-1]

    average = average_body(
        previous,
        10,
    )

    if average <= 0:

        return False

    if (
        candle_body(candle)
        < average * DISPLACEMENT_BODY_MULT
    ):

        return False

    if direction == "BUY":

        return bullish(candle)

    return bearish(candle)


# ============================================================
# BOS
# ============================================================

def break_of_structure(
    df,
    direction,
):

    end = len(df) - 1

    if end < BOS_LOOKBACK + 2:

        return False, None

    candle = df.iloc[end - 1]

    previous = df.iloc[
        end - BOS_LOOKBACK - 1:
        end - 1
    ]

    if direction == "BUY":

        level = float(
            previous["high"].max()
        )

        valid = (
            float(candle["close"])
            > level
        )

    else:

        level = float(
            previous["low"].min()
        )

        valid = (
            float(candle["close"])
            < level
        )

    return (
        valid,
        level if valid else None,
    )


# ============================================================
# CHOCH
# ============================================================

def change_of_character(
    df,
    direction,
):

    work = df.iloc[:-1]

    if len(work) < 12:

        return False

    highs = swing_highs(work)

    lows = swing_lows(work)

    if direction == "BUY":

        return bool(
            highs
            and float(
                work["close"].iloc[-1]
            )
            > highs[-1][1]
        )

    return bool(
        lows
        and float(
            work["close"].iloc[-1]
        )
        < lows[-1][1]
    )


# ============================================================
# RETEST
# ============================================================

def retest_level(
    df,
    direction,
    level,
    atr,
):

    if (
        level is None
        or atr <= 0
    ):

        return False

    candle = df.iloc[-2]

    tolerance = (
        atr * RETEST_TOLERANCE_ATR
    )

    if direction == "BUY":

        return (
            float(candle["low"])
            <= level + tolerance
            and float(candle["close"])
            >= level
        )

    return (
        float(candle["high"])
        >= level - tolerance
        and float(candle["close"])
        <= level
    )


# ============================================================
# PRE-SIGNAL SETUP
# ============================================================

def pre_signal_setup(
    frames,
    direction,
):

    atr = atr_value(
        frames["1H"]
    )

    if atr <= 0:

        return {
            "valid": False
        }

    price = float(
        frames["5M"]["close"].iloc[-1]
    )

    if direction == "BUY":

        zone = find_demand_zone(
            frames["1H"]
        )

    else:

        zone = find_supply_zone(
            frames["1H"]
        )

    approaching, distance = (
        approach_to_zone(
            price,
            zone,
            atr,
            direction,
        )
    )

    if not approaching:

        return {
            "valid": False
        }

    closes = (
        frames["5M"]["close"]
        .iloc[-3:]
        .astype(float)
        .tolist()
    )

    if len(closes) < 3:

        return {
            "valid": False
        }

    c1, c2, c3 = closes

    if direction == "BUY":

        moving_toward = (
            c1 <= c2 <= c3
        )

    else:

        moving_toward = (
            c1 >= c2 >= c3
        )

    in_or_near = price_in_zone(
        price,
        zone,
        atr * ZONE_TOLERANCE_ATR,
    )

    if (
        not moving_toward
        and not in_or_near
    ):

        return {
            "valid": False
        }

    return {
        "valid": True,
        "zone": zone,
        "distance": distance,
        "price": price,
        "direction": direction,
    }


# ============================================================
# WATCH SETUP
# ============================================================

def watch_setup(
    frames,
    direction,
):

    swept, sweep_level = (
        liquidity_sweep(
            frames["15M"],
            direction,
        )
    )

    bos_ok, bos_level = (
        break_of_structure(
            frames["15M"],
            direction,
        )
    )

    choch_ok = (
        change_of_character(
            frames["15M"],
            direction,
        )
    )

    rejection = (
        rejection_candle(
            frames["15M"],
            direction,
        )
    )

    displacement_ok = (
        displacement(
            frames["15M"],
            direction,
        )
    )

    score = 0

    if swept:
        score += 2

    if bos_ok:
        score += 3

    if choch_ok:
        score += 2

    if rejection:
        score += 1

    if displacement_ok:
        score += 1

    valid = (
        swept
        or bos_ok
        or choch_ok
    )

    return {
        "valid": valid,
        "score": score,
        "level": (
            bos_level
            if bos_ok
            else sweep_level
        ),
        "sweep": sweep_level,
    }


# ============================================================
# TRADE SETUP
# ============================================================

def trade_setup(
    frames,
    direction,
):

    atr_1h = atr_value(
        frames["1H"]
    )

    price = float(
        frames["5M"]["close"].iloc[-1]
    )

    if direction == "BUY":

        zone = find_demand_zone(
            frames["1H"]
        )

    else:

        zone = find_supply_zone(
            frames["1H"]
        )

    if (
        atr_1h <= 0
        or not price_in_zone(
            price,
            zone,
            atr_1h * ZONE_TOLERANCE_ATR,
        )
    ):

        return {
            "valid": False,
            "score": 0,
        }

    swept, sweep_level = (
        liquidity_sweep(
            frames["15M"],
            direction,
        )
    )

    rejection = (
        rejection_candle(
            frames["15M"],
            direction,
        )
    )

    displacement_ok = (
        displacement(
            frames["15M"],
            direction,
        )
    )

    bos_ok, bos_level = (
        break_of_structure(
            frames["15M"],
            direction,
        )
    )

    choch_ok = (
        change_of_character(
            frames["15M"],
            direction,
        )
    )

    score = 2

    if swept:
        score += 2

    if rejection:
        score += 1

    if bos_ok:
        score += 2

    if choch_ok:
        score += 1

    if displacement_ok:
        score += 1

    reversal_valid = (
        swept
        and rejection
        and (bos_ok or choch_ok)
        and score >= MIN_PA_SCORE
    )

    if reversal_valid:

        return {
            "valid": True,
            "score": score,
            "level": (
                bos_level
                if bos_ok
                else sweep_level
            ),
            "sweep": sweep_level,
            "setup_type": "LIQUIDITY REVERSAL",
        }

    # --------------------------------------------------------
    # BREAKOUT / RETEST
    # --------------------------------------------------------

    atr_5m = atr_value(
        frames["5M"]
    )

    bos_ok, level = (
        break_of_structure(
            frames["15M"],
            direction,
        )
    )

    displacement_ok = (
        displacement(
            frames["15M"],
            direction,
        )
    )

    retest = retest_level(
        frames["5M"],
        direction,
        level,
        atr_5m,
    )

    trigger = rejection_candle(
        frames["5M"],
        direction,
    )

    breakout_score = 0

    if bos_ok:
        breakout_score += 3

    if displacement_ok:
        breakout_score += 2

    if retest:
        breakout_score += 2

    if trigger:
        breakout_score += 2

    breakout_valid = (
        bos_ok
        and displacement_ok
        and retest
        and trigger
        and breakout_score >= 8
    )

    if breakout_valid:

        return {
            "valid": True,
            "score": breakout_score,
            "level": level,
            "sweep": None,
            "setup_type": "BREAKOUT + RETEST",
        }

    return {
        "valid": False,
        "score": 0,
    }


# ============================================================
# ZONE FINGERPRINT
# ============================================================

def zone_id(zone):

    if zone is None:

        return None

    return (
        round(float(zone["low"]), 6),
        round(float(zone["high"]), 6),
    )


# ============================================================
# SETUP KEY
# ============================================================

def setup_key(
    symbol,
    direction,
):

    return f"{symbol}:{direction}"


# ============================================================
# PRE FINGERPRINT
#
# IMPORTANT:
# We deliberately do NOT use current price as the fingerprint.
# Otherwise a changing price would create a new alert every scan.
# ============================================================

def pre_fingerprint(setup):

    return zone_id(
        setup.get("zone")
    )


# ============================================================
# WATCH FINGERPRINT
#
# Rounded structure values prevent tiny numerical changes from
# being treated as completely new setups.
# ============================================================

def watch_fingerprint(setup):

    level = setup.get("level")

    sweep = setup.get("sweep")

    level_id = (
        round(float(level), 4)
        if level is not None
        else None
    )

    sweep_id = (
        round(float(sweep), 4)
        if sweep is not None
        else None
    )

    return (
        level_id,
        sweep_id,
    )


# ============================================================
# PRE ALERT
# ============================================================

def process_pre_signal(
    symbol,
    frames,
    session_name,
):

    now = time.time()

    for direction in (
        "BUY",
        "SELL",
    ):

        setup = pre_signal_setup(
            frames,
            direction,
        )

        key = setup_key(
            symbol,
            direction,
        )

        # ----------------------------------------------------
        # SETUP INVALID
        # ----------------------------------------------------

        if not setup["valid"]:

            old = pre_state.get(key)

            if old is not None:

                # Remove old lock only after the setup has
                # genuinely disappeared for the cooldown.
                if (
                    now - old["last_seen"]
                    >= PRE_SIGNAL_COOLDOWN
                ):

                    pre_state.pop(
                        key,
                        None,
                    )

            continue

        fingerprint = pre_fingerprint(
            setup
        )

        old = pre_state.get(key)

        # ----------------------------------------------------
        # SAME ZONE = NEVER REPEAT
        # ----------------------------------------------------

        if (
            old is not None
            and old["fingerprint"]
            == fingerprint
        ):

            # Keep the setup alive.
            old["last_seen"] = now

            continue

        # ----------------------------------------------------
        # DIFFERENT ZONE
        #
        # Still enforce cooldown so a rapidly changing zone
        # cannot generate messages every second.
        # ----------------------------------------------------

        if (
            old is not None
            and now - old["alert_time"]
            < PRE_SIGNAL_COOLDOWN
        ):

            old["last_seen"] = now

            continue

        cfg = MARKETS[symbol]

        decimals = cfg["decimals"]

        emoji = (
            "🟢"
            if direction == "BUY"
            else "🔴"
        )

        zone_name = (
            "DEMAND"
            if direction == "BUY"
            else "SUPPLY"
        )

        zone = setup["zone"]

        message = (
            "⚠️ *ADVANCE PRE-SIGNAL*\n"
            f"*{cfg['execution']}* | "
            f"{session_name}\n\n"

            f"{emoji} *Potential "
            f"{direction} setup approaching "
            f"{zone_name}*\n"

            f"📍 Current price: "
            f"{setup['price']:,.{decimals}f}\n"

            f"📦 Zone: "
            f"{zone['low']:,.{decimals}f}"
            f" → "
            f"{zone['high']:,.{decimals}f}\n"

            f"📏 Distance: "
            f"{setup['distance']:,.{decimals}f}\n\n"

            "👀 WAIT — NOT A TRADE YET\n"

            "Required next:\n"
            "• 15M liquidity sweep / structure shift\n"
            "• 5M confirmation\n"
            f"• Adaptive RR target ≥ {MIN_RR:.2f}R\n\n"

            "🧭 *Advance warning only*"
        )

        send_telegram(
            message
        )

        pre_state[key] = {
            "alert_time": now,
            "last_seen": now,
            "fingerprint": fingerprint,
            "session": session_name,
        }

        log.info(
            "PRE LOCKED | %s | %s | zone=%s",
            symbol,
            direction,
            fingerprint,
        )


# ============================================================
# WATCH ALERT
# ============================================================

def process_watch(
    symbol,
    frames,
    session_name,
):

    now = time.time()

    price = float(
        frames["5M"]["close"].iloc[-1]
    )

    for direction in (
        "BUY",
        "SELL",
    ):

        setup = watch_setup(
            frames,
            direction,
        )

        if not setup["valid"]:

            continue

        key = setup_key(
            symbol,
            direction,
        )

        fingerprint = watch_fingerprint(
            setup
        )

        old = watch_state.get(key)

        # ----------------------------------------------------
        # SAME STRUCTURE
        # ----------------------------------------------------

        if (
            old is not None
            and old["fingerprint"]
            == fingerprint
        ):

            old["last_seen"] = now

            continue

        # ----------------------------------------------------
        # GLOBAL WATCH COOLDOWN
        #
        # Prevents continuously changing structure from
        # generating a message every second.
        # ----------------------------------------------------

        if (
            old is not None
            and now - old["alert_time"]
            < WATCH_COOLDOWN
        ):

            old["last_seen"] = now

            continue

        cfg = MARKETS[symbol]

        decimals = cfg["decimals"]

        level = setup.get(
            "level"
        )

        if level is None:

            structure_text = "forming"

        else:

            structure_text = (
                f"{float(level):,.{decimals}f}"
            )

        message = (
            f"👀 *PA WATCH — "
            f"{cfg['execution']}*\n\n"

            f"*Direction:* {direction}\n"

            f"*Price:* "
            f"{price:,.{decimals}f}\n"

            f"*Structure:* "
            f"{structure_text}\n"

            "*Status:* 15M structure forming — "
            "wait for 5M confirmation\n"

            f"*Session:* {session_name}"
        )

        send_telegram(
            message
        )

        watch_state[key] = {
            "alert_time": now,
            "last_seen": now,
            "fingerprint": fingerprint,
            "session": session_name,
        }

        log.info(
            "WATCH LOCKED | %s | %s | setup=%s",
            symbol,
            direction,
            fingerprint,
        )


# ============================================================
# ADAPTIVE STOP LOSS
# ============================================================

def calculate_sl(
    symbol,
    direction,
    entry,
    frames,
    setup,
):

    config = MARKETS[symbol]

    atr_5m = atr_value(
        frames["5M"]
    )

    atr_15m = atr_value(
        frames["15M"]
    )

    volatility = max(
        atr_5m,
        atr_15m,
    )

    if volatility <= 0:

        return None

    buffer = max(
        config["min_sl"]
        * config["sl_buffer"],

        volatility * 0.10,
    )

    sweep = setup.get(
        "sweep"
    )

    level = setup.get(
        "level"
    )

    if direction == "BUY":

        candidates = [
            entry
            - config["min_sl"]
        ]

        if sweep is not None:

            candidates.append(
                float(sweep)
                - buffer
            )

        if level is not None:

            candidates.append(
                float(level)
                - buffer
            )

        stop_loss = min(
            candidates
        )

        distance = (
            entry
            - stop_loss
        )

    else:

        candidates = [
            entry
            + config["min_sl"]
        ]

        if sweep is not None:

            candidates.append(
                float(sweep)
                + buffer
            )

        if level is not None:

            candidates.append(
                float(level)
                + buffer
            )

        stop_loss = max(
            candidates
        )

        distance = (
            stop_loss
            - entry
        )

    max_sl = max(
        config["min_sl"] * 5.0,
        volatility * 2.0,
    )

    if (
        distance <= 0
        or distance > max_sl
    ):

        return None

    return (
        stop_loss,
        distance,
    )


# ============================================================
# STRUCTURE TARGET
# ============================================================

def adaptive_target(
    frames,
    direction,
    entry,
    sl_distance,
):

    if sl_distance <= 0:

        return (
            None,
            0.0,
            "INVALID",
        )

    minimum_distance = (
        sl_distance * MIN_RR
    )

    maximum_distance = (
        sl_distance * MAX_RR
    )

    levels = []

    for timeframe in (
        "5M",
        "15M",
        "1H",
    ):

        df = frames[timeframe]

        if direction == "BUY":

            levels.extend(
                [
                    value
                    for _, value
                    in swing_highs(df)
                    if value > entry
                ]
            )

        else:

            levels.extend(
                [
                    value
                    for _, value
                    in swing_lows(df)
                    if value < entry
                ]
            )

    levels = sorted(
        set(
            round(
                float(value),
                8,
            )
            for value in levels
        )
    )

    if direction == "BUY":

        valid = [
            level
            for level in levels
            if (
                entry
                + minimum_distance
                <= level
                <=
                entry
                + maximum_distance
            )
        ]

        if valid:

            target = max(
                valid
            )

            rr = (
                target - entry
            ) / sl_distance

            return (
                target,
                rr,
                "STRUCTURE",
            )

        beyond = [
            level
            for level in levels
            if level
            > entry + minimum_distance
        ]

        if beyond:

            return (
                entry + maximum_distance,
                MAX_RR,
                "4R-CAPPED",
            )

        return (
            entry + minimum_distance,
            MIN_RR,
            "MIN-RR",
        )

    valid = [
        level
        for level in levels
        if (
            entry
            - maximum_distance
            <= level
            <=
            entry
            - minimum_distance
        )
    ]

    if valid:

        target = min(
            valid
        )

        rr = (
            entry - target
        ) / sl_distance

        return (
            target,
            rr,
            "STRUCTURE",
        )

    beyond = [
        level
        for level in levels
        if level
        < entry - minimum_distance
    ]

    if beyond:

        return (
            entry - maximum_distance,
            MAX_RR,
            "4R-CAPPED",
        )

    return (
        entry - minimum_distance,
        MIN_RR,
        "MIN-RR",
    )


# ============================================================
# LOT SIZE
# ============================================================

def calculate_lot(
    symbol,
    sl_distance,
):

    if sl_distance <= 0:

        return 0.0

    dollar_per_point = (
        DOLLAR_PER_POINT[symbol]
    )

    raw = (
        RISK_PER_TRADE
        / (
            sl_distance
            * dollar_per_point
        )
    )

    cap = LOT_CAP[symbol]

    if symbol in {
        "NIFTY50",
        "BANKNIFTY",
        "SENSEX",
        "RELIANCE",
        "TCS",
    }:

        return float(
            max(
                1,
                round(
                    min(
                        raw,
                        cap,
                    )
                ),
            )
        )

    return round(
        max(
            0.01,
            min(
                raw,
                cap,
            ),
        ),
        3,
    )


# ============================================================
# TRADE DUPLICATE PROTECTION
# ============================================================

def trade_allowed(
    symbol,
    direction,
    setup_type,
):

    now = time.time()

    last_time = last_trade.get(
        symbol,
        0,
    )

    if (
        now - last_time
        < TRADE_SIGNAL_COOLDOWN
    ):

        return False

    return True


# ============================================================
# TRADE PROCESS
# ============================================================

def process_trade(
    symbol,
    frames,
    session_name,
):

    if (
        daily_count[symbol]
        >= MARKETS[symbol]["daily_cap"]
    ):

        return False

    for direction in (
        "BUY",
        "SELL",
    ):

        setup = trade_setup(
            frames,
            direction,
        )

        if not setup["valid"]:

            continue

        setup_type = setup.get(
            "setup_type",
            "PA CONFIRMATION",
        )

        if not trade_allowed(
            symbol,
            direction,
            setup_type,
        ):

            continue

        price = float(
            frames["5M"]["close"].iloc[-1]
        )

        if direction == "BUY":

            entry = (
                price
                + EXECUTION_BUFFER[symbol]
            )

        else:

            entry = (
                price
                - EXECUTION_BUFFER[symbol]
            )

        sl_result = calculate_sl(
            symbol,
            direction,
            entry,
            frames,
            setup,
        )

        if sl_result is None:

            log.info(
                "%s %s rejected: "
                "adaptive SL invalid",
                symbol,
                direction,
            )

            continue

        stop_loss, sl_distance = (
            sl_result
        )

        target, rr, target_mode = (
            adaptive_target(
                frames,
                direction,
                entry,
                sl_distance,
            )
        )

        if (
            target is None
            or rr < MIN_RR
        ):

            log.info(
                "%s %s rejected: "
                "RR %.2f < %.2f",
                symbol,
                direction,
                rr,
                MIN_RR,
            )

            continue

        lot = calculate_lot(
            symbol,
            sl_distance,
        )

        score = min(
            10,
            int(
                setup.get(
                    "score",
                    8,
                )
            ) + 1,
        )

        config = MARKETS[symbol]

        decimals = config["decimals"]

        if score >= 10:

            quality = "GOD-TIER PA"

        elif score >= 9:

            quality = "A+ PA"

        else:

            quality = "A PA"

        direction_icon = (
            "📈"
            if direction == "BUY"
            else "📉"
        )

        liquidity_status = (
            "CONFIRMED"
            if setup.get("sweep")
            is not None
            else "STRUCTURE"
        )

        message = (

            f"🚨 *{VERSION} "
            f"TRADE SIGNAL*\n"

            f"*{config['execution']}*\n\n"

            f"{direction_icon} "
            f"*{direction}*\n"

            f"🚀 Setup: "
            f"*{setup_type}*\n"

            f"⭐ PA Score: "
            f"*{score}/10*\n"

            f"🏆 Quality: "
            f"*{quality}*\n\n"

            f"📍 Entry: "
            f"*{entry:,.{decimals}f}*\n"

            f"🛑 SL: "
            f"*{stop_loss:,.{decimals}f}*\n"

            f"🎯 TP: "
            f"*{target:,.{decimals}f}*\n"

            f"⚖️ RR: "
            f"*1:{rr:.2f}*\n"

            f"🧠 Target: "
            f"*{target_mode}*\n"

            f"💵 Lot: "
            f"*{lot}*\n\n"

            f"⏱ Structure: "
            f"1H → 15M → 5M\n"

            f"📌 Session: "
            f"{session_name}\n"

            f"💧 Liquidity: "
            f"{liquidity_status}\n\n"

            "✅ Price Action only\n"
            "🚫 No EMA / RSI / ADX / VWAP"
        )

        send_telegram(
            message
        )

        log_signal(
            symbol,
            direction,
            score,
            setup_type,
            entry,
            stop_loss,
            target,
            rr,
            session_name,
            target_mode,
        )

        with signal_lock:

            last_trade[symbol] = (
                time.time()
            )

            last_trade_direction[
                symbol
            ] = direction

            last_trade_setup[
                symbol
            ] = setup_type

            daily_count[symbol] += 1

            session_count[symbol] = {
                "session": session_name,
                "count": 1,
            }

            # Clear PRE/WATCH after confirmed trade.
            key = setup_key(
                symbol,
                direction,
            )

            pre_state.pop(
                key,
                None,
            )

            watch_state.pop(
                key,
                None,
            )

        log.info(
            "TRADE SIGNAL | %s | %s | "
            "entry=%s | SL=%s | TP=%s | "
            "RR=%.2f | score=%s",
            symbol,
            direction,
            entry,
            stop_loss,
            target,
            rr,
            score,
        )

        return True

    return False


# ============================================================
# CSV LOGGING
# ============================================================

def log_signal(
    symbol,
    direction,
    score,
    setup_type,
    entry,
    stop_loss,
    target,
    rr,
    session_name,
    target_mode,
):

    row = [
        VERSION,

        datetime.now(
            timezone.utc
        ).isoformat(),

        symbol,

        direction,

        score,

        setup_type,

        entry,

        stop_loss,

        target,

        rr,

        session_name,

        target_mode,
    ]

    with log_lock:

        path = "signals_log.csv"

        new_file = (
            not os.path.exists(path)
            or os.path.getsize(path) == 0
        )

        with open(
            path,
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.writer(
                file
            )

            if new_file:

                writer.writerow(
                    [
                        "version",
                        "timestamp",
                        "symbol",
                        "direction",
                        "score",
                        "setup_type",
                        "entry",
                        "sl",
                        "tp",
                        "rr",
                        "session",
                        "target_mode",
                    ]
                )

            writer.writerow(row)

        with open(
            "signals_backup.csv",
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            csv.writer(file).writerow(
                row
            )


# ============================================================
# DAILY RESET
# ============================================================

def reset_daily_state():

    global daily_pnl

    global consecutive_losses

    global reset_date

    today = (
        datetime.now(
            timezone.utc
        ).date()
    )

    if today == reset_date:

        return

    reset_date = today

    daily_pnl = 0.0

    consecutive_losses = 0

    pre_state.clear()

    watch_state.clear()

    last_trade.clear()

    last_trade_direction.clear()

    last_trade_setup.clear()

    for symbol in SYMBOLS:

        daily_count[symbol] = 0

        session_count[symbol] = {
            "session": None,
            "count": 0,
        }

    log.info(
        "Daily state reset complete"
    )


# ============================================================
# SYMBOL PROCESS
# ============================================================

def process_symbol(symbol):

    try:

        if weekend_block():

            return

        if (
            daily_pnl
            <= MAX_DAILY_LOSS
        ):

            return

        if (
            consecutive_losses
            >= MAX_CONSECUTIVE_LOSSES
        ):

            return

        active, session_name = (
            get_session(symbol)
        )

        if not active:

            return

        if (
            session_name
            not in MARKETS[symbol]["sessions"]
        ):

            return

        frames = get_frames(
            symbol
        )

        if frames is None:

            return

        # ----------------------------------------------------
        # STAGE 1
        # ----------------------------------------------------

        process_pre_signal(
            symbol,
            frames,
            session_name,
        )

        # ----------------------------------------------------
        # STAGE 2
        # ----------------------------------------------------

        process_watch(
            symbol,
            frames,
            session_name,
        )

        # ----------------------------------------------------
        # SESSION TRADE GATE
        # ----------------------------------------------------

        state = session_count[
            symbol
        ]

        if (
            state["session"]
            != session_name
        ):

            state["session"] = (
                session_name
            )

            state["count"] = 0

        if (
            SIGNAL_ONE_PER_SESSION
            and state["count"] >= 1
        ):

            return

        # ----------------------------------------------------
        # STAGE 3
        # ----------------------------------------------------

        process_trade(
            symbol,
            frames,
            session_name,
        )

    except Exception as exc:

        log.exception(
            "Symbol processing error %s: %s",
            symbol,
            exc,
        )


# ============================================================
# HEARTBEAT
# ============================================================

def watchdog():

    try:

        with open(
            "heartbeat.txt",
            "w",
            encoding="utf-8",
        ) as file:

            file.write(
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"{VERSION} | ACTIVE"
            )

    except Exception as exc:

        log.error(
            "Watchdog error: %s",
            exc,
        )


# ============================================================
# STARTUP MESSAGE
# ============================================================

def startup_message():

    return (

        f"⚡ *{VERSION} LIVE*\n\n"

        "1H = Location / Structure\n"
        "15M = Liquidity + BOS/CHOCH\n"
        "5M = Trigger\n\n"

        f"⚠️ Advance Pre-Signal: "
        f"{PRE_SIGNAL_ATR:.2f} ATR\n"

        f"⚖️ Adaptive RR: "
        f"{MIN_RR:.2f}R → "
        f"{MAX_RR:.2f}R\n"

        "🎯 Targets use "
        "5M/15M/1H structure\n"

        "🚫 No indicator scoring\n"

        f"🌐 Markets: "
        f"{len(SYMBOLS)}\n"

        f"⏱ Decision scan: "
        f"{SCAN_INTERVAL:.1f}s\n"

        f"📡 Data refresh: "
        f"{DATA_REFRESH_INTERVAL:.1f}s\n\n"

        "PRE = one alert per setup\n"
        "WATCH = one alert per structure\n"
        "TRADE = confirmed PA setup"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global reset_date

    log.info(
        "%s STARTED",
        VERSION,
    )

    if TOKEN and CHAT_ID:

        log.info(
            "Telegram configuration detected"
        )

    else:

        log.warning(
            "Telegram credentials missing"
        )

    send_telegram(
        startup_message()
    )

    last_refresh = 0.0

    loop = 0

    while True:

        try:

            reset_daily_state()

            watchdog()

            now = time.time()

            # ------------------------------------------------
            # DATA REFRESH
            # ------------------------------------------------

            if (
                now - last_refresh
                >= DATA_REFRESH_INTERVAL
            ):

                log.info(
                    "⚡ DATA refresh | "
                    "symbols=%s | "
                    "refresh=%.1fs",
                    len(SYMBOLS),
                    DATA_REFRESH_INTERVAL,
                )

                with ThreadPoolExecutor(
                    max_workers=len(SYMBOLS)
                ) as executor:

                    futures = [
                        executor.submit(
                            refresh_symbol,
                            symbol,
                        )
                        for symbol in SYMBOLS
                    ]

                    for future in as_completed(
                        futures
                    ):

                        try:

                            future.result()

                        except Exception as exc:

                            log.error(
                                "Data worker error: %s",
                                exc,
                            )

                last_refresh = time.time()

            # ------------------------------------------------
            # PA SCAN
            # ------------------------------------------------

            log.info(
                "⚡ LIVE PA scan #%s | "
                "symbols=%s | "
                "interval=%.1fs",
                loop,
                len(SYMBOLS),
                SCAN_INTERVAL,
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

                for future in as_completed(
                    futures
                ):

                    try:

                        future.result()

                    except Exception as exc:

                        log.error(
                            "Worker error: %s",
                            exc,
                        )

            loop += 1

            gc.collect()

            time.sleep(
                SCAN_INTERVAL
            )

        except KeyboardInterrupt:

            log.info(
                "Engine stopped by user"
            )

            break

        except Exception as exc:

            log.exception(
                "Main loop error: %s",
                exc,
            )

            time.sleep(
                SCAN_INTERVAL
            )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
