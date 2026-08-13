# ============================================================
# PEPPERSTONE PRICE ACTION HUNTER
# PA-SUPREME-2026 — ADVANCE PRICE-ACTION EDITION v2
#
# 1H  = LOCATION / MARKET STRUCTURE
# 15M = LIQUIDITY / BOS / CHOCH
# 5M  = ENTRY TRIGGER
#
# ALERT STAGES
#   ⚠️ PRE-SIGNAL = one alert per detected zone
#   👀 WATCH      = one alert per structure setup
#   🚨 TRADE      = confirmed PA entry
#
# IMPORTANT FIX:
#   The old version could repeatedly send PRE messages every
#   scan because the same zone remained valid.
#
#   This version locks:
#       SYMBOL + DIRECTION + ZONE
#
#   Therefore the same zone cannot spam Telegram every second.
#
# DATA:
#   Yahoo Finance is used for market data in this version.
#
# LOOP:
#   Decision scan     = 1 second
#   Data refresh      = 15 seconds
#
# STRUCTURE:
#   1H -> Location
#   15M -> Liquidity / BOS / CHOCH
#   5M -> Trigger
#
# TARGET:
#   Minimum RR = 1.80R
#   Maximum RR = 4.00R
#   Target uses 5M / 15M / 1H structure
#
# ============================================================

import os
import time
import csv
import math
import gc
import logging

from datetime import datetime, timezone
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
import yfinance as yf


# ============================================================
# SYSTEM
# ============================================================

VERSION = "PA-SUPREME-2026-ADVANCE-v2"


# ============================================================
# TELEGRAM CONFIG
# ============================================================
#
# Set these as environment variables:
#
# TELEGRAM_TOKEN
# TELEGRAM_CHAT_ID
#
# Example:
#
# export TELEGRAM_TOKEN="YOUR_NEW_BOT_TOKEN"
# export TELEGRAM_CHAT_ID="YOUR_CHAT_ID"
#
# ============================================================

TOKEN = (
    os.getenv("TELEGRAM_TOKEN")
    or os.getenv("TOKEN", "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU")
)

CHAT_ID = (
    os.getenv("TELEGRAM_CHAT_ID")
    or os.getenv("CHAT_ID", "8783763018")
)


# ============================================================
# ENGINE SETTINGS
# ============================================================

SCAN_INTERVAL = 1.0

DATA_REFRESH_INTERVAL = 15.0


# ============================================================
# ADVANCE SIGNAL
# ============================================================

PRE_SIGNAL_ATR = 0.75

PRE_SIGNAL_COOLDOWN = 900

WATCH_COOLDOWN = 600

TRADE_SIGNAL_COOLDOWN = 900


# ============================================================
# RR
# ============================================================

MIN_RR = 1.80

MAX_RR = 4.00


# ============================================================
# PRICE ACTION
# ============================================================

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


# ============================================================
# RISK
# ============================================================

RISK_PER_TRADE = 50.0

MAX_DAILY_LOSS = -300.0

MAX_CONSECUTIVE_LOSSES = 3


# ============================================================
# SESSION LIMIT
# ============================================================

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
# DOLLAR PER POINT
# ============================================================

DPP = {

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


# ============================================================
# LOT CAPS
# ============================================================

LOT_CAP = {

    "XAU/USD": 1.5,

    "NAS100": 2.0,

    "SPX500": 2.0,

    "EUR/USD": 3.0,

    "GBP/JPY": 2.0,

    "NIFTY50": 50,

    "BANKNIFTY": 50,

    "SENSEX": 50,

    "RELIANCE": 500,

    "TCS": 500,
}


# ============================================================
# EXECUTION BUFFER
# ============================================================

BUFFER = {

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


# ============================================================
# HTTP
# ============================================================

http = requests.Session()


# ============================================================
# LOCKS
# ============================================================

cache_lock = Lock()

signal_lock = Lock()

log_lock = Lock()


# ============================================================
# CACHE
# ============================================================

frames_cache = {}

frames_time = {}


# ============================================================
# IMPORTANT ALERT STATE
#
# PRE STATE:
#   Prevents same zone from sending repeatedly.
#
# WATCH STATE:
#   Prevents same structure from sending repeatedly.
#
# ============================================================

pre_state = {}

watch_state = {}

last_trade = {}


# ============================================================
# DAILY STATE
# ============================================================

daily_count = {
    s: 0 for s in SYMBOLS
}


session_count = {
    s: {
        "session": None,
        "count": 0,
    }
    for s in SYMBOLS
}


daily_pnl = 0.0

losses = 0

reset_date = datetime.now(timezone.utc).date()


# ============================================================
# TELEGRAM
# ============================================================

def tg(message):

    if not TOKEN or not CHAT_ID:

        log.warning(
            "Telegram not configured. "
            "Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID."
        )

        return False

    try:

        url = (
            f"https://api.telegram.org/"
            f"bot{TOKEN}/sendMessage"
        )

        response = http.post(

            url,

            json={
                "chat_id": CHAT_ID,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
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

        log.error(
            "Telegram error: %s",
            exc,
        )

    return False


# ============================================================
# SESSION
# ============================================================

def session(symbol):

    now = datetime.now(timezone.utc)

    hm = (
        now.hour * 60
        + now.minute
    )

    # --------------------------------------------------------
    # INDIA
    # --------------------------------------------------------

    if MARKETS[symbol]["market_type"] == "india":

        if 225 <= hm < 330:

            return True, "India Open"

        if 330 <= hm < 450:

            return True, "India Midday"

        if 450 <= hm < 600:

            return True, "India Close"

        return False, "Closed"

    # --------------------------------------------------------
    # GLOBAL
    # --------------------------------------------------------

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

def weekend():

    now = datetime.now(timezone.utc)

    return (
        now.weekday() == 5
        or (
            now.weekday() == 6
            and now.hour < 21
        )
    )


# ============================================================
# YAHOO DATA
# ============================================================

def fetch(ticker):

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

            return None

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

        required = (
            "open",
            "high",
            "low",
            "close",
        )

        if any(
            c not in raw.columns
            for c in required
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

        return None


# ============================================================
# RESAMPLE
# ============================================================

def resample(df, rule):

    return (
        df.resample(rule)
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna(
            subset=[
                "open",
                "high",
                "low",
                "close",
            ]
        )
    )


# ============================================================
# REFRESH SYMBOL
# ============================================================

def refresh(symbol):

    base = fetch(
        MARKETS[symbol]["data"]
    )

    if base is None:

        return None

    result = {

        "5M": base.copy(),

        "15M": resample(
            base,
            "15min",
        ),

        "1H": resample(
            base,
            "1h",
        ),
    }

    if any(
        len(value) < 50
        for value in result.values()
    ):

        return None

    with cache_lock:

        frames_cache[symbol] = result

        frames_time[symbol] = time.time()

    return result


# ============================================================
# GET FRAMES
# ============================================================

def frames(symbol):

    with cache_lock:

        cached = frames_cache.get(symbol)

        cached_time = frames_time.get(
            symbol,
            0,
        )

    if (
        cached is not None
        and time.time() - cached_time
        < DATA_REFRESH_INTERVAL
    ):

        return cached

    return refresh(symbol)


# ============================================================
# CANDLE HELPERS
# ============================================================

def body(candle):

    return abs(
        float(candle.close)
        - float(candle.open)
    )


def bull(candle):

    return (
        float(candle.close)
        > float(candle.open)
    )


def bear(candle):

    return (
        float(candle.close)
        < float(candle.open)
    )


def avgbody(df, n=10):

    value = (
        (df.close - df.open)
        .abs()
        .tail(n)
        .mean()
    )

    if pd.isna(value):

        return 0

    return float(value)


# ============================================================
# ATR
# ============================================================

def atr(df, n=14):

    if len(df) < n + 2:

        return 0

    previous_close = df.close.shift(1)

    tr = pd.concat(

        [
            df.high - df.low,

            (
                df.high
                - previous_close
            ).abs(),

            (
                df.low
                - previous_close
            ).abs(),
        ],

        axis=1,
    ).max(axis=1)

    value = (
        tr.rolling(n)
        .mean()
        .iloc[-1]
    )

    if pd.isna(value):

        return 0

    return float(value)


# ============================================================
# SWING HIGHS
# ============================================================

def highs(df):

    result = []

    if len(df) < (
        SWING_LEFT
        + SWING_RIGHT
        + 1
    ):

        return result

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT,
    ):

        value = float(
            df.high.iloc[i]
        )

        left = float(
            df.high.iloc[
                i - SWING_LEFT:i
            ].max()
        )

        right = float(
            df.high.iloc[
                i + 1:
                i + SWING_RIGHT + 1
            ].max()
        )

        if (
            value > left
            and value >= right
        ):

            result.append(
                (i, value)
            )

    return result


# ============================================================
# SWING LOWS
# ============================================================

def lows(df):

    result = []

    if len(df) < (
        SWING_LEFT
        + SWING_RIGHT
        + 1
    ):

        return result

    for i in range(
        SWING_LEFT,
        len(df) - SWING_RIGHT,
    ):

        value = float(
            df.low.iloc[i]
        )

        left = float(
            df.low.iloc[
                i - SWING_LEFT:i
            ].min()
        )

        right = float(
            df.low.iloc[
                i + 1:
                i + SWING_RIGHT + 1
            ].min()
        )

        if (
            value < left
            and value <= right
        ):

            result.append(
                (i, value)
            )

    return result


# ============================================================
# DEMAND ZONE
# ============================================================

def demand(df):

    work = (
        df.tail(
            ZONE_LOOKBACK_1H
        )
        .reset_index(
            drop=True
        )
    )

    average = avgbody(work)

    if len(work) < 15:

        return None

    if average <= 0:

        return None

    candidates = []

    for i in range(
        3,
        len(work),
    ):

        candle = work.iloc[i]

        if not bull(candle):

            continue

        if (
            body(candle)
            < average
            * DISPLACEMENT_BODY_MULT
        ):

            continue

        previous_high = float(
            work.high.iloc[
                max(0, i - 5):i
            ].max()
        )

        if (
            float(candle.close)
            <= previous_high
        ):

            continue

        base = work.iloc[i - 1]

        candidates.append({

            "low": min(
                float(base.open),
                float(base.close),
                float(base.low),
            ),

            "high": max(
                float(base.open),
                float(base.close),
                float(base.high),
            ),

            "index": i,
        })

    return (
        candidates[-1]
        if candidates
        else None
    )


# ============================================================
# SUPPLY ZONE
# ============================================================

def supply(df):

    work = (
        df.tail(
            ZONE_LOOKBACK_1H
        )
        .reset_index(
            drop=True
        )
    )

    average = avgbody(work)

    if len(work) < 15:

        return None

    if average <= 0:

        return None

    candidates = []

    for i in range(
        3,
        len(work),
    ):

        candle = work.iloc[i]

        if not bear(candle):

            continue

        if (
            body(candle)
            < average
            * DISPLACEMENT_BODY_MULT
        ):

            continue

        previous_low = float(
            work.low.iloc[
                max(0, i - 5):i
            ].min()
        )

        if (
            float(candle.close)
            >= previous_low
        ):

            continue

        base = work.iloc[i - 1]

        candidates.append({

            "low": min(
                float(base.open),
                float(base.close),
                float(base.low),
            ),

            "high": max(
                float(base.open),
                float(base.close),
                float(base.high),
            ),

            "index": i,
        })

    return (
        candidates[-1]
        if candidates
        else None
    )


# ============================================================
# PRICE IN ZONE
# ============================================================

def in_zone(
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

def approach(
    price,
    zone,
    atr_value,
    direction,
):

    if (
        zone is None
        or atr_value <= 0
    ):

        return False, None

    tolerance = (
        atr_value
        * ZONE_TOLERANCE_ATR
    )

    limit = (
        atr_value
        * PRE_SIGNAL_ATR
    )

    low = float(zone["low"])

    high = float(zone["high"])


    # --------------------------------------------------------
    # BUY
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # SELL
    # --------------------------------------------------------

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

def sweep(df, direction):

    if len(df) < (
        LIQUIDITY_LOOKBACK + 3
    ):

        return False, None

    end = len(df) - 2

    previous = df.iloc[
        end - LIQUIDITY_LOOKBACK:
        end
    ]

    candle = df.iloc[end]

    previous_high = float(
        previous.high.max()
    )

    previous_low = float(
        previous.low.min()
    )


    if direction == "BUY":

        swept = (
            float(candle.low)
            < previous_low
        )

        reclaimed = (
            float(candle.close)
            > previous_low
        )

        valid = (
            swept
            and reclaimed
        )

        return (
            valid,
            previous_low
            if valid
            else None,
        )


    swept = (
        float(candle.high)
        > previous_high
    )

    reclaimed = (
        float(candle.close)
        < previous_high
    )

    valid = (
        swept
        and reclaimed
    )

    return (
        valid,
        previous_high
        if valid
        else None,
    )


# ============================================================
# REJECTION
# ============================================================

def rejection(
    df,
    direction,
):

    if len(df) < 3:

        return False

    candle = df.iloc[-2]

    op = float(candle.open)

    close = float(candle.close)

    high = float(candle.high)

    low = float(candle.low)

    candle_body = abs(
        close - op
    )

    total_range = high - low

    if (
        candle_body <= 0
        or total_range <= 0
    ):

        return False

    upper_wick = (
        high
        - max(op, close)
    )

    lower_wick = (
        min(op, close)
        - low
    )


    if direction == "BUY":

        return (
            lower_wick
            >= candle_body
            * REJECTION_WICK_RATIO

            and close > op

            and (
                (close - low)
                / total_range
            ) >= 0.60
        )


    return (
        upper_wick
        >= candle_body
        * REJECTION_WICK_RATIO

        and close < op

        and (
            (high - close)
            / total_range
        ) >= 0.60
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

    average = avgbody(
        df.iloc[:-1]
    )

    if average <= 0:

        return False

    if (
        body(candle)
        < average
        * DISPLACEMENT_BODY_MULT
    ):

        return False

    if direction == "BUY":

        return bull(candle)

    return bear(candle)


# ============================================================
# BOS
# ============================================================

def bos(
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
            previous.high.max()
        )

        valid = (
            float(candle.close)
            > level
        )

    else:

        level = float(
            previous.low.min()
        )

        valid = (
            float(candle.close)
            < level
        )

    return (
        valid,
        level if valid else None,
    )


# ============================================================
# CHOCH
# ============================================================

def choch(
    df,
    direction,
):

    work = df.iloc[:-1]

    if len(work) < 12:

        return False

    swing_high = highs(work)

    swing_low = lows(work)


    if direction == "BUY":

        return bool(
            swing_high
            and float(
                work.close.iloc[-1]
            )
            > swing_high[-1][1]
        )


    return bool(
        swing_low
        and float(
            work.close.iloc[-1]
        )
        < swing_low[-1][1]
    )


# ============================================================
# RETEST
# ============================================================

def retest(
    df,
    direction,
    level,
    atr_value,
):

    if (
        level is None
        or atr_value <= 0
    ):

        return False

    candle = df.iloc[-2]

    tolerance = (
        atr_value
        * RETEST_TOLERANCE_ATR
    )


    if direction == "BUY":

        return (
            float(candle.low)
            <= level + tolerance

            and float(candle.close)
            >= level
        )


    return (
        float(candle.high)
        >= level - tolerance

        and float(candle.close)
        <= level
    )


# ============================================================
# PRE-SIGNAL SETUP
# ============================================================

def pre_setup(
    frames,
    direction,
):

    atr_1h = atr(
        frames["1H"]
    )

    price = float(
        frames["5M"].close.iloc[-1]
    )

    zone = (
        demand(frames["1H"])
        if direction == "BUY"
        else supply(frames["1H"])
    )

    valid, distance = approach(
        price,
        zone,
        atr_1h,
        direction,
    )

    if not valid:

        return {
            "valid": False
        }


    c1 = float(
        frames["5M"].close.iloc[-1]
    )

    c2 = float(
        frames["5M"].close.iloc[-2]
    )

    c3 = float(
        frames["5M"].close.iloc[-3]
    )


    if direction == "BUY":

        moving_toward = (
            c1 < c2 < c3
        )

    else:

        moving_toward = (
            c1 > c2 > c3
        )


    if not moving_toward:

        if not in_zone(
            price,
            zone,
            atr_1h
            * ZONE_TOLERANCE_ATR,
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

    swept, sweep_level = sweep(
        frames["15M"],
        direction,
    )

    bos_valid, bos_level = bos(
        frames["15M"],
        direction,
    )

    choch_valid = choch(
        frames["15M"],
        direction,
    )

    rejection_valid = rejection(
        frames["15M"],
        direction,
    )

    displacement_valid = displacement(
        frames["15M"],
        direction,
    )


    score = (

        (2 if swept else 0)

        + (3 if bos_valid else 0)

        + (2 if choch_valid else 0)

        + (1 if rejection_valid else 0)

        + (1 if displacement_valid else 0)
    )


    return {

        "valid": bool(
            swept
            or bos_valid
            or choch_valid
        ),

        "score": score,

        "level": (
            bos_level
            if bos_valid
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

    atr_1h = atr(
        frames["1H"]
    )

    price = float(
        frames["5M"].close.iloc[-1]
    )

    zone = (
        demand(frames["1H"])
        if direction == "BUY"
        else supply(frames["1H"])
    )


    if (
        atr_1h <= 0
        or not in_zone(
            price,
            zone,
            atr_1h
            * ZONE_TOLERANCE_ATR,
        )
    ):

        return {
            "valid": False,
            "score": 0,
        }


    # --------------------------------------------------------
    # REVERSAL
    # --------------------------------------------------------

    swept, sweep_level = sweep(
        frames["15M"],
        direction,
    )

    rejection_valid = rejection(
        frames["15M"],
        direction,
    )

    displacement_valid = displacement(
        frames["15M"],
        direction,
    )

    bos_valid, bos_level = bos(
        frames["15M"],
        direction,
    )

    choch_valid = choch(
        frames["15M"],
        direction,
    )


    score = (

        2

        + (2 if swept else 0)

        + (1 if rejection_valid else 0)

        + (2 if bos_valid else 0)

        + (1 if choch_valid else 0)

        + (1 if displacement_valid else 0)
    )


    if (
        swept
        and rejection_valid
        and (bos_valid or choch_valid)
        and score >= MIN_PA_SCORE
    ):

        return {

            "valid": True,

            "score": score,

            "level": (
                bos_level
                if bos_valid
                else sweep_level
            ),

            "sweep": sweep_level,
        }


    # --------------------------------------------------------
    # BREAKOUT + RETEST
    # --------------------------------------------------------

    atr_5m = atr(
        frames["5M"]
    )

    bos_valid, level = bos(
        frames["15M"],
        direction,
    )

    displacement_valid = displacement(
        frames["15M"],
        direction,
    )

    retest_valid = retest(
        frames["5M"],
        direction,
        level,
        atr_5m,
    )

    trigger_valid = rejection(
        frames["5M"],
        direction,
    )


    score = (

        (3 if bos_valid else 0)

        + (2 if displacement_valid else 0)

        + (2 if retest_valid else 0)

        + (2 if trigger_valid else 0)
    )


    if (
        bos_valid
        and displacement_valid
        and retest_valid
        and trigger_valid
        and score >= 8
    ):

        return {

            "valid": True,

            "score": score,

            "level": level,

            "sweep": None,
        }


    return {

        "valid": False,

        "score": 0,
    }


# ============================================================
# STOP LOSS
# ============================================================

def sl_calc(
    symbol,
    direction,
    entry,
    frames,
    setup,
):

    config = MARKETS[symbol]

    atr_value = max(

        atr(frames["5M"]),

        atr(frames["15M"]),
    )

    if atr_value <= 0:

        return None


    buffer = max(

        config["min_sl"]
        * config["sl_buffer"],

        atr_value * 0.10,
    )


    sweep_level = setup.get(
        "sweep"
    )

    structure_level = setup.get(
        "level"
    )


    if direction == "BUY":

        candidates = [
            entry
            - config["min_sl"]
        ]

        if sweep_level is not None:

            candidates.append(
                float(sweep_level)
                - buffer
            )

        if structure_level is not None:

            candidates.append(
                float(structure_level)
                - buffer
            )

        sl = min(candidates)

        distance = entry - sl


    else:

        candidates = [
            entry
            + config["min_sl"]
        ]

        if sweep_level is not None:

            candidates.append(
                float(sweep_level)
                + buffer
            )

        if structure_level is not None:

            candidates.append(
                float(structure_level)
                + buffer
            )

        sl = max(candidates)

        distance = sl - entry


    max_sl = max(

        config["min_sl"] * 5,

        atr_value * 2,
    )


    if (
        distance <= 0
        or distance > max_sl
    ):

        return None


    return sl, distance


# ============================================================
# TARGET ENGINE
# ============================================================

def target(
    frames,
    direction,
    entry,
    stop_distance,
):

    levels = []


    for dataframe in (

        frames["5M"],

        frames["15M"],

        frames["1H"],
    ):

        swing_levels = (

            highs(dataframe)
            if direction == "BUY"
            else lows(dataframe)
        )


        for _, value in swing_levels:

            if direction == "BUY":

                if value > entry:

                    levels.append(
                        value
                    )

            else:

                if value < entry:

                    levels.append(
                        value
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


    minimum_distance = (
        stop_distance
        * MIN_RR
    )

    maximum_distance = (
        stop_distance
        * MAX_RR
    )


    if direction == "BUY":

        valid = [

            value

            for value in levels

            if (
                entry
                + minimum_distance
                <= value
                <= entry
                + maximum_distance
            )
        ]

    else:

        valid = [

            value

            for value in levels

            if (
                entry
                - maximum_distance
                <= value
                <= entry
                - minimum_distance
            )
        ]


    if valid:

        target_price = (
            max(valid)
            if direction == "BUY"
            else min(valid)
        )


        rr = (

            (
                target_price
                - entry
            )
            / stop_distance

            if direction == "BUY"

            else

            (
                entry
                - target_price
            )
            / stop_distance
        )


        return (
            target_price,
            rr,
            "STRUCTURE",
        )


    beyond = (

        [
            value
            for value in levels
            if value
            > entry + minimum_distance
        ]

        if direction == "BUY"

        else

        [
            value
            for value in levels
            if value
            < entry - minimum_distance
        ]
    )


    if beyond:

        return (

            entry + maximum_distance
            if direction == "BUY"
            else
            entry - maximum_distance,

            MAX_RR,

            "4R-CAPPED",
        )


    return (

        entry + minimum_distance
        if direction == "BUY"
        else
        entry - minimum_distance,

        MIN_RR,

        "MIN-RR",
    )


# ============================================================
# LOT SIZE
# ============================================================

def lot(
    symbol,
    stop_distance,
):

    if stop_distance <= 0:

        return 0.0

    raw = (
        RISK_PER_TRADE
        / (
            stop_distance
            * DPP[symbol]
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
# ZONE ID
#
# This is the main anti-spam mechanism.
# ============================================================

def zone_id(zone):

    if zone is None:

        return None

    return (

        round(
            float(zone["low"]),
            8,
        ),

        round(
            float(zone["high"]),
            8,
        ),
    )


# ============================================================
# SIGNAL KEY
# ============================================================

def signal_key(
    symbol,
    direction,
):

    return (
        f"{symbol}:{direction}"
    )


# ============================================================
# PRE SIGNAL PROCESS
# ============================================================

def process_pre(
    symbol,
    frames_data,
    current_session,
):

    now = time.time()


    for direction in (
        "BUY",
        "SELL",
    ):

        setup = pre_setup(
            frames_data,
            direction,
        )


        key = signal_key(
            symbol,
            direction,
        )


        # ----------------------------------------------------
        # No longer valid
        # ----------------------------------------------------

        if not setup["valid"]:

            old = pre_state.get(
                key
            )

            if (
                old
                and
                now - old["time"]
                >= PRE_SIGNAL_COOLDOWN
            ):

                pre_state.pop(
                    key,
                    None,
                )

            continue


        current_zone_id = zone_id(
            setup["zone"]
        )


        old = pre_state.get(
            key
        )


        # ----------------------------------------------------
        # MAIN ANTI-SPAM LOCK
        #
        # Same symbol + direction +
        # same zone = NO NEW MESSAGE
        # ----------------------------------------------------

        if (
            old
            and
            old["zone_id"]
            == current_zone_id
        ):

            continue


        config = MARKETS[symbol]

        decimals = config[
            "decimals"
        ]

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


        message = (

            "⚠️ *ADVANCE PRE-SIGNAL*\n"

            f"*{config['execution']}* "
            f"| {current_session}\n\n"

            f"{emoji} *Potential "
            f"{direction} setup approaching "
            f"{zone_name}*\n"

            f"📍 Current price: "
            f"{setup['price']:,.{decimals}f}\n"

            f"📦 Zone: "
            f"{setup['zone']['low']:,.{decimals}f}"
            f" → "
            f"{setup['zone']['high']:,.{decimals}f}\n"

            f"📏 Distance: "
            f"{setup['distance']:,.{decimals}f}\n\n"

            "👀 WAIT — NOT A TRADE YET\n"

            "Required next:\n"

            "• 15M liquidity sweep / "
            "structure shift\n"

            "• 5M confirmation\n"

            f"• Adaptive RR target ≥ "
            f"{MIN_RR:.2f}R\n\n"

            "🧭 *Advance warning only*"
        )


        tg(message)


        # ----------------------------------------------------
        # LOCK
        # ----------------------------------------------------

        pre_state[key] = {

            "time": now,

            "zone_id":
                current_zone_id,

            "session":
                current_session,
        }


        log.info(

            "PRE LOCKED %s %s zone=%s",

            symbol,

            direction,

            current_zone_id,
        )


# ============================================================
# WATCH PROCESS
# ============================================================

def process_watch(
    symbol,
    frames_data,
    current_session,
):

    now = time.time()

    price = float(
        frames_data["5M"]
        .close
        .iloc[-1]
    )


    for direction in (
        "BUY",
        "SELL",
    ):

        setup = watch_setup(
            frames_data,
            direction,
        )


        if not setup["valid"]:

            continue


        key = signal_key(
            symbol,
            direction,
        )


        level_id = (

            round(
                float(
                    setup["level"]
                ),
                8,
            )

            if setup.get("level")
            is not None

            else None
        )


        sweep_id = (

            round(
                float(
                    setup["sweep"]
                ),
                8,
            )

            if setup.get("sweep")
            is not None

            else None
        )


        setup_id = (
            level_id,
            sweep_id,
        )


        old = watch_state.get(
            key
        )


        # ----------------------------------------------------
        # SAME STRUCTURE
        # ----------------------------------------------------

        if (
            old
            and old["setup_id"]
            == setup_id
        ):

            continue


        # ----------------------------------------------------
        # COOLDOWN
        # ----------------------------------------------------

        if (
            old
            and
            now - old["time"]
            < WATCH_COOLDOWN
        ):

            continue


        config = MARKETS[symbol]

        decimals = config[
            "decimals"
        ]


        if setup.get("level") is not None:

            level_text = (
                f"{setup['level']:,."
                f"{decimals}f}"
            )

        else:

            level_text = "forming"


        message = (

            f"👀 *PA WATCH — "
            f"{config['execution']}*\n\n"

            f"*Direction:* {direction}\n"

            f"*Price:* "
            f"{price:,.{decimals}f}\n"

            f"*Structure:* {level_text}\n"

            "*Status:* 15M structure "
            "forming — wait for 5M confirmation\n"

            f"*Session:* {current_session}"
        )


        tg(message)


        watch_state[key] = {

            "time": now,

            "setup_id":
                setup_id,

            "session":
                current_session,
        }


        log.info(

            "WATCH LOCKED %s %s setup=%s",

            symbol,

            direction,

            setup_id,
        )


# ============================================================
# TRADE PROCESS
# ============================================================

def process_trade(
    symbol,
    frames_data,
    current_session,
):

    if (
        daily_count[symbol]
        >= MARKETS[symbol]["daily_cap"]
    ):

        return


    for direction in (
        "BUY",
        "SELL",
    ):

        setup = trade_setup(
            frames_data,
            direction,
        )


        if not setup["valid"]:

            continue


        # ----------------------------------------------------
        # TRADE COOLDOWN
        # ----------------------------------------------------

        if (
            time.time()
            - last_trade.get(
                symbol,
                0,
            )
            < TRADE_SIGNAL_COOLDOWN
        ):

            continue


        price = float(
            frames_data["5M"]
            .close
            .iloc[-1]
        )


        if direction == "BUY":

            entry = (
                price
                + BUFFER[symbol]
            )

        else:

            entry = (
                price
                - BUFFER[symbol]
            )


        stop_data = sl_calc(

            symbol,

            direction,

            entry,

            frames_data,

            setup,
        )


        if stop_data is None:

            log.info(

                "%s %s rejected: "
                "adaptive SL invalid",

                symbol,

                direction,
            )

            continue


        sl, stop_distance = (
            stop_data
        )


        tp, rr, target_mode = target(

            frames_data,

            direction,

            entry,

            stop_distance,
        )


        if (
            tp is None
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


        lot_size = lot(

            symbol,

            stop_distance,
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

        decimals = config[
            "decimals"
        ]


        if score >= 10:

            quality = (
                "GOD-TIER PA"
            )

        elif score >= 9:

            quality = "A+ PA"

        else:

            quality = "A PA"


        message = (

            f"🚨 *{VERSION} "
            "TRADE SIGNAL*\n"

            f"*{config['execution']}*\n\n"

            f"{'📈' if direction == 'BUY' else '📉'} "
            f"*{direction}*\n"

            "🚀 Setup: "
            "*LIQUIDITY/STRUCTURE PA*\n"

            f"⭐ PA Score: "
            f"*{score}/10*\n"

            f"🏆 Quality: "
            f"*{quality}*\n\n"

            f"📍 Entry: "
            f"*{entry:,.{decimals}f}*\n"

            f"🛑 SL: "
            f"*{sl:,.{decimals}f}*\n"

            f"🎯 TP: "
            f"*{tp:,.{decimals}f}*\n"

            f"⚖️ RR: "
            f"*1:{rr:.2f}*\n"

            f"🧠 Target: "
            f"*{target_mode}*\n"

            f"💵 Lot: "
            f"*{lot_size}*\n\n"

            "⏱ Structure: "
            "1H → 15M → 5M\n"

            f"📌 Session: "
            f"{current_session}\n\n"

            "✅ Price Action only\n"

            "🚫 No EMA / RSI / "
            "ADX / VWAP"
        )


        tg(message)


        log_signal(

            symbol,

            direction,

            score,

            entry,

            sl,

            tp,

            rr,

            current_session,

            target_mode,
        )


        last_trade[
            symbol
        ] = time.time()


        daily_count[
            symbol
        ] += 1


        session_count[
            symbol
        ] = {

            "session":
                current_session,

            "count": 1,
        }


        # ----------------------------------------------------
        # Clear PRE/WATCH for completed setup
        # ----------------------------------------------------

        setup_key = signal_key(
            symbol,
            direction,
        )


        pre_state.pop(
            setup_key,
            None,
        )


        watch_state.pop(
            setup_key,
            None,
        )


        log.info(

            "TRADE SIGNAL %s %s "
            "| entry=%s "
            "| sl=%s "
            "| tp=%s "
            "| RR=%.2f "
            "| target=%s "
            "| score=%s",

            symbol,

            direction,

            entry,

            sl,

            tp,

            rr,

            target_mode,

            score,
        )


        return


# ============================================================
# CSV LOG
# ============================================================

def log_signal(
    symbol,
    direction,
    score,
    entry,
    sl,
    tp,
    rr,
    current_session,
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

        entry,

        sl,

        tp,

        rr,

        current_session,

        target_mode,
    ]


    with log_lock:

        filename = (
            "signals_log.csv"
        )


        new_file = (

            not os.path.exists(
                filename
            )

            or
            os.path.getsize(
                filename
            ) == 0
        )


        with open(
            filename,
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.writer(
                file
            )


            if new_file:

                writer.writerow([

                    "version",

                    "timestamp",

                    "symbol",

                    "direction",

                    "score",

                    "entry",

                    "sl",

                    "tp",

                    "rr",

                    "session",

                    "target_mode",
                ])


            writer.writerow(row)


        with open(
            "signals_backup.csv",
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            csv.writer(
                file
            ).writerow(row)


# ============================================================
# SYMBOL PROCESS
# ============================================================

def process_symbol(symbol):

    try:

        # ----------------------------------------------------
        # GLOBAL LOCKS
        # ----------------------------------------------------

        if weekend():

            return

        if daily_pnl <= MAX_DAILY_LOSS:

            return

        if losses >= MAX_CONSECUTIVE_LOSSES:

            return


        # ----------------------------------------------------
        # SESSION
        # ----------------------------------------------------

        session_ok, current_session = (
            session(symbol)
        )


        if not session_ok:

            return


        if (
            current_session
            not in MARKETS[symbol][
                "sessions"
            ]
        ):

            return


        # ----------------------------------------------------
        # MARKET DATA
        # ----------------------------------------------------

        frames_data = frames(
            symbol
        )


        if frames_data is None:

            return


        # ----------------------------------------------------
        # STAGE 1
        # PRE
        # ----------------------------------------------------

        process_pre(

            symbol,

            frames_data,

            current_session,
        )


        # ----------------------------------------------------
        # STAGE 2
        # WATCH
        # ----------------------------------------------------

        process_watch(

            symbol,

            frames_data,

            current_session,
        )


        # ----------------------------------------------------
        # SESSION TRADE LIMIT
        # ----------------------------------------------------

        state = session_count[
            symbol
        ]


        if (
            state["session"]
            != current_session
        ):

            state.update({

                "session":
                    current_session,

                "count":
                    0,
            })


        if (
            SIGNAL_ONE_PER_SESSION
            and state["count"] >= 1
        ):

            return


        # ----------------------------------------------------
        # STAGE 3
        # TRADE
        # ----------------------------------------------------

        process_trade(

            symbol,

            frames_data,

            current_session,
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

def startup():

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

        "⚠️ PRE = one alert per setup\n"

        "👀 WATCH = one alert per "
        "structure setup\n"

        "🚨 TRADE = confirmed PA setup"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    global reset_date

    global daily_pnl

    global losses


    log.info(
        "%s STARTED",
        VERSION,
    )


    # --------------------------------------------------------
    # Telegram startup test
    # --------------------------------------------------------

    tg(
        startup()
    )


    last_refresh = 0.0

    loop = 0


    while True:

        try:

            # ------------------------------------------------
            # DAILY RESET
            # ------------------------------------------------

            today = (
                datetime.now(
                    timezone.utc
                ).date()
            )


            if today != reset_date:

                reset_date = today

                daily_pnl = 0.0

                losses = 0

                pre_state.clear()

                watch_state.clear()

                daily_count.update({

                    symbol: 0

                    for symbol in SYMBOLS
                })


                session_count.update({

                    symbol: {

                        "session":
                            None,

                        "count":
                            0,
                    }

                    for symbol in SYMBOLS
                })


                log.info(
                    "Daily state reset"
                )


            # ------------------------------------------------
            # HEARTBEAT
            # ------------------------------------------------

            with open(
                "heartbeat.txt",
                "w",
                encoding="utf-8",
            ) as heartbeat:

                heartbeat.write(

                    f"{datetime.now(timezone.utc).isoformat()} "
                    f"| {VERSION} "
                    f"| ACTIVE"
                )


            # ------------------------------------------------
            # DATA REFRESH
            # ------------------------------------------------

            if (
                time.time()
                - last_refresh
                >= DATA_REFRESH_INTERVAL
            ):

                log.info(

                    "⚡ DATA refresh "
                    "| symbols=%s "
                    "| refresh=%.1fs",

                    len(SYMBOLS),

                    DATA_REFRESH_INTERVAL,
                )


                with ThreadPoolExecutor(

                    max_workers=len(
                        SYMBOLS
                    )

                ) as executor:


                    futures = [

                        executor.submit(
                            refresh,
                            symbol,
                        )

                        for symbol
                        in SYMBOLS
                    ]


                    for future in as_completed(
                        futures
                    ):

                        try:

                            future.result()

                        except Exception as exc:

                            log.error(

                                "Data worker: %s",

                                exc,
                            )


                last_refresh = (
                    time.time()
                )


            # ------------------------------------------------
            # 1-SECOND DECISION SCAN
            # ------------------------------------------------

            log.info(

                "⚡ LIVE PA scan #%s "
                "| symbols=%s "
                "| interval=%.1fs",

                loop,

                len(SYMBOLS),

                SCAN_INTERVAL,
            )


            with ThreadPoolExecutor(

                max_workers=len(
                    SYMBOLS
                )

            ) as executor:


                futures = [

                    executor.submit(
                        process_symbol,
                        symbol,
                    )

                    for symbol
                    in SYMBOLS
                ]


                for future in as_completed(
                    futures
                ):

                    try:

                        future.result()

                    except Exception as exc:

                        log.error(

                            "Worker: %s",

                            exc,
                        )


            loop += 1

            gc.collect()

            time.sleep(
                SCAN_INTERVAL
            )


        except KeyboardInterrupt:

            log.info(
                "Stopped by user"
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
# ENTRY
# ============================================================

if __name__ == "__main__":

    main()
