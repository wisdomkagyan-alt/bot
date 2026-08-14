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

VERSION = "PA-SUPREME-2026-ADVANCE-v4"

# ============================================================
# RAILWAY VARIABLES
# ============================================================
# Railway -> Service -> Variables:
#
# TOKEN=your_new_telegram_bot_token
# CHAT_ID=your_chat_id
#
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

# Lowered from the previous very restrictive confirmation.
MIN_TRADE_SCORE = 6

MIN_RR = 1.80
MAX_RR = 4.00

MIN_PA_SCORE_DISPLAY = 8

SIGNAL_ONE_PER_SESSION = True

RISK_PER_TRADE = 50.0

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

# ============================================================
# MARKETS
# ============================================================
PRIORITY_MARKETS = [
    "XAU/USD",
    "NAS100",
    "SPX500",
    "EUR/USD",
    "GBP/JPY",
    "NIFTY50",
    "BANKNIFTY",
    "SENSEX",
    "RELIANCE",
    "TCS",
]

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

# ============================================================
# RISK / LOT
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

log = logging.getLogger("PA-SUPREME")

http = requests.Session()

cache_lock = Lock()
file_lock = Lock()
state_lock = Lock()

# ============================================================
# CACHE
# ============================================================
frames_cache = {}
frames_cache_time = {}

# ============================================================
# SIGNAL STATE
# ============================================================
last_pre = {}
last_watch = {}
last_trade = {}

# Important:
# A setup must exist before it can become a TRADE.
active_setups = {}

session_state = {
    symbol: {
        "session": None,
        "count": 0,
    }
    for symbol in PRIORITY_MARKETS
}

daily_signal_count = {
    symbol: 0
    for symbol in PRIORITY_MARKETS
}

daily_pnl = 0.0
consecutive_losses = 0

last_reset_date = datetime.now(timezone.utc).date()

# ============================================================
# FILES
# ============================================================
for filename in (
    "signals_log.csv",
    "signals_backup.csv",
):

    if not os.path.exists(filename):

        open(
            filename,
            "a",
            encoding="utf-8",
        ).close()

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(message):

    if not TOKEN or not CHAT_ID:

        log.warning(
            "Telegram disabled: TOKEN or CHAT_ID missing"
        )

        return False

    url = (
        f"https://api.telegram.org/bot"
        f"{TOKEN}/sendMessage"
    )

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

            if response.ok:
                return True

            log.error(
                "Telegram HTTP %s: %s",
                response.status_code,
                response.text[:300],
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
# DAILY STATE
# ============================================================
def reset_daily():

    global daily_pnl
    global consecutive_losses
    global last_reset_date

    today = datetime.now(timezone.utc).date()

    if today != last_reset_date:

        daily_pnl = 0.0
        consecutive_losses = 0
        last_reset_date = today

        for symbol in PRIORITY_MARKETS:

            daily_signal_count[symbol] = 0

            session_state[symbol] = {
                "session": None,
                "count": 0,
            }

        active_setups.clear()
        last_pre.clear()
        last_watch.clear()
        last_trade.clear()

        log.info(
            "Daily state reset"
        )

# ============================================================
# DAILY LOCK
# ============================================================
def daily_lock():

    if daily_pnl <= MAX_DAILY_LOSS:
        return True

    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return True

    return False

# ============================================================
# SESSION
# ============================================================
def in_session(symbol):

    now = datetime.now(timezone.utc)

    hm = (
        now.hour * 60
        + now.minute
    )

    market_type = MARKETS[symbol]["market_type"]

    # India times converted to UTC.
    if market_type == "india":

        if 225 <= hm < 330:
            return True, "India Open"

        if 330 <= hm < 450:
            return True, "India Midday"

        if 450 <= hm < 600:
            return True, "India Close"

        return False, "Closed"

    # Global sessions UTC.

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
# SESSION GATE
# ============================================================
def session_gate(symbol, session):

    state = session_state[symbol]

    if state["session"] != session:

        state["session"] = session
        state["count"] = 0

    if not SIGNAL_ONE_PER_SESSION:
        return True

    return state["count"] < 1

# ============================================================
# CONSUME SESSION SIGNAL
# ============================================================
def consume_session(symbol, session):

    state = session_state[symbol]

    if state["session"] != session:

        state["session"] = session
        state["count"] = 0

    state["count"] += 1

# ============================================================
# YAHOO DATA
# ============================================================
def fetch_yf(
    ticker,
    period="5d",
    interval="5m",
):

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

            df = (
                df
                .replace(
                    [math.inf, -math.inf],
                    pd.NA,
                )
                .dropna(
                    subset=required
                )
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
# RESAMPLE
# ============================================================
def ohlc_resample(df, rule):

    return (
        df
        .resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
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
# REFRESH DATA
# ============================================================
def refresh_symbol_data(symbol):

    ticker = MARKETS[symbol]["data"]

    base = fetch_yf(ticker)

    if base is None:
        return None

    frames = {
        "5M": base.copy(),
        "15M": ohlc_resample(
            base,
            "15min",
        ),
        "1H": ohlc_resample(
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

        frames_cache_time[symbol] = (
            time.time()
        )

    return frames

# ============================================================
# GET CACHED FRAMES
# ============================================================
def get_frames(symbol):

    with cache_lock:

        frames = frames_cache.get(
            symbol
        )

        cached_at = frames_cache_time.get(
            symbol,
            0,
        )

    if (
        frames is not None
        and time.time() - cached_at
        < DATA_REFRESH_INTERVAL
    ):

        return frames

    return refresh_symbol_data(symbol)

# ============================================================
# CANDLE HELPERS
# ============================================================
def candle_body(candle):

    return abs(
        float(candle["close"])
        - float(candle["open"])
    )

# ============================================================
def bullish(candle):

    return (
        float(candle["close"])
        > float(candle["open"])
    )

# ============================================================
def bearish(candle):

    return (
        float(candle["close"])
        < float(candle["open"])
    )

# ============================================================
def average_body(
    df,
    length=10,
):

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
def atr_value(
    df,
    period=14,
):

    if len(df) < period + 2:
        return 0.0

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    previous_close = close.shift(1)

    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
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

    output = []

    if len(df) < (
        SWING_LEFT
        + SWING_RIGHT
        + 1
    ):

        return output

    end = len(df) - SWING_RIGHT

    for i in range(
        SWING_LEFT,
        end,
    ):

        value = float(
            df["high"].iloc[i]
        )

        left = df[
            "high"
        ].iloc[
            i - SWING_LEFT:i
        ]

        right = df[
            "high"
        ].iloc[
            i + 1:i + SWING_RIGHT + 1
        ]

        if (
            value > float(left.max())
            and value >= float(right.max())
        ):

            output.append(
                (i, value)
            )

    return output

# ============================================================
# SWING LOWS
# ============================================================
def swing_lows(df):

    output = []

    if len(df) < (
        SWING_LEFT
        + SWING_RIGHT
        + 1
    ):

        return output

    end = len(df) - SWING_RIGHT

    for i in range(
        SWING_LEFT,
        end,
    ):

        value = float(
            df["low"].iloc[i]
        )

        left = df[
            "low"
        ].iloc[
            i - SWING_LEFT:i
        ]

        right = df[
            "low"
        ].iloc[
            i + 1:i + SWING_RIGHT + 1
        ]

        if (
            value < float(left.min())
            and value <= float(right.min())
        ):

            output.append(
                (i, value)
            )

    return output

# ============================================================
# DEMAND ZONE
# ============================================================
def find_demand_zone(df):

    work = (
        df
        .tail(ZONE_LOOKBACK_1H)
        .reset_index(drop=True)
    )

    if len(work) < 15:
        return None

    avg = average_body(
        work,
        10,
    )

    if avg <= 0:
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
            < avg * DISPLACEMENT_BODY_MULT
        ):

            continue

        prior_high = float(
            work[
                "high"
            ].iloc[
                max(0, i - 5):i
            ].max()
        )

        if (
            float(candle["close"])
            <= prior_high
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

    if not candidates:
        return None

    return candidates[-1]

# ============================================================
# SUPPLY ZONE
# ============================================================
def find_supply_zone(df):

    work = (
        df
        .tail(ZONE_LOOKBACK_1H)
        .reset_index(drop=True)
    )

    if len(work) < 15:
        return None

    avg = average_body(
        work,
        10,
    )

    if avg <= 0:
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
            < avg * DISPLACEMENT_BODY_MULT
        ):

            continue

        prior_low = float(
            work[
                "low"
            ].iloc[
                max(0, i - 5):i
            ].min()
        )

        if (
            float(candle["close"])
            >= prior_low
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

    if not candidates:
        return None

    return candidates[-1]

# ============================================================
# ZONE KEY
# ============================================================
def zone_key(
    symbol,
    direction,
    zone,
):

    if zone is None:
        return None

    return (
        symbol,
        direction,
        round(
            zone["low"],
            8,
        ),
        round(
            zone["high"],
            8,
        ),
    )

# ============================================================
# PRICE IN ZONE
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
        atr
        * ZONE_TOLERANCE_ATR
    )

    if direction == "BUY":

        distance = max(
            0.0,
            price - zone["high"],
        )

        approaching = (
            distance
            <= PRE_SIGNAL_ATR * atr
            and price
            >= zone["low"] - tolerance
        )

        return (
            approaching,
            distance,
        )

    distance = max(
        0.0,
        zone["low"] - price,
    )

    approaching = (
        distance
        <= PRE_SIGNAL_ATR * atr
        and price
        <= zone["high"] + tolerance
    )

    return (
        approaching,
        distance,
    )

# ============================================================
# LIQUIDITY SWEEP
# ============================================================
def liquidity_sweep(
    df,
    direction,
    closed=True,
):

    idx = (
        -2
        if closed
        else -1
    )

    if len(df) < (
        LIQUIDITY_LOOKBACK + 3
    ):

        return False, None

    end = len(df) + idx

    previous = df.iloc[
        end - LIQUIDITY_LOOKBACK:end
    ]

    last = df.iloc[end]

    previous_high = float(
        previous["high"].max()
    )

    previous_low = float(
        previous["low"].min()
    )

    if direction == "BUY":

        swept = (
            float(last["low"])
            < previous_low
        )

        reclaimed = (
            float(last["close"])
            > previous_low
        )

        if swept and reclaimed:
            return True, previous_low

        return False, None

    swept = (
        float(last["high"])
        > previous_high
    )

    reclaimed = (
        float(last["close"])
        < previous_high
    )

    if swept and reclaimed:
        return True, previous_high

    return False, None

# ============================================================
# REJECTION
# ============================================================
def rejection_candle(
    df,
    direction,
    closed=True,
):

    idx = (
        -2
        if closed
        else -1
    )

    if len(df) < 3:
        return False

    candle = df.iloc[idx]

    op = float(candle["open"])
    cl = float(candle["close"])
    hi = float(candle["high"])
    lo = float(candle["low"])

    body = abs(cl - op)

    total = hi - lo

    if body <= 0 or total <= 0:
        return False

    upper = (
        hi
        - max(op, cl)
    )

    lower = (
        min(op, cl)
        - lo
    )

    if direction == "BUY":

        return (
            lower
            >= body * REJECTION_WICK_RATIO
            and cl > op
            and (cl - lo) / total >= 0.60
        )

    return (
        upper
        >= body * REJECTION_WICK_RATIO
        and cl < op
        and (hi - cl) / total >= 0.60
    )

# ============================================================
# DISPLACEMENT
# ============================================================
def displacement(
    df,
    direction,
    closed=True,
):

    idx = (
        -2
        if closed
        else -1
    )

    if len(df) < 12:
        return False

    last = df.iloc[idx]

    prior = df.iloc[
        :len(df) + idx
    ]

    avg = average_body(
        prior,
        10,
    )

    if (
        avg <= 0
        or candle_body(last)
        < avg * DISPLACEMENT_BODY_MULT
    ):

        return False

    if direction == "BUY":
        return bullish(last)

    return bearish(last)

# ============================================================
# BOS
# ============================================================
def bos(
    df,
    direction,
    closed=True,
):

    end = (
        len(df) - 1
        if closed
        else len(df)
    )

    if end < BOS_LOOKBACK + 2:
        return False, None

    last = df.iloc[end - 1]

    prior = df.iloc[
        end - BOS_LOOKBACK - 1:
        end - 1
    ]

    if direction == "BUY":

        level = float(
            prior["high"].max()
        )

        ok = (
            float(last["close"])
            > level
        )

        return (
            ok,
            level if ok else None,
        )

    level = float(
        prior["low"].min()
    )

    ok = (
        float(last["close"])
        < level
    )

    return (
        ok,
        level if ok else None,
    )

# ============================================================
# CHOCH
# ============================================================
def choch(
    df,
    direction,
    closed=True,
):

    end = (
        len(df) - 1
        if closed
        else len(df)
    )

    work = df.iloc[:end]

    if len(work) < 12:
        return False

    highs = swing_highs(work)
    lows = swing_lows(work)

    if direction == "BUY":

        return bool(
            highs
            and float(
                work.iloc[-1]["close"]
            )
            > highs[-1][1]
        )

    return bool(
        lows
        and float(
            work.iloc[-1]["close"]
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
    closed=True,
):

    if (
        level is None
        or atr <= 0
        or len(df) < 3
    ):

        return False

    idx = (
        -2
        if closed
        else -1
    )

    candle = df.iloc[idx]

    tolerance = (
        atr
        * RETEST_TOLERANCE_ATR
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
    df1,
    df15,
    df5,
    direction,
):

    atr = atr_value(df1)

    if atr <= 0:
        return {
            "valid": False
        }

    price = float(
        df5.iloc[-1]["close"]
    )

    if direction == "BUY":
        zone = find_demand_zone(df1)
    else:
        zone = find_supply_zone(df1)

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

    c1 = float(
        df5.iloc[-1]["close"]
    )

    c2 = float(
        df5.iloc[-2]["close"]
    )

    c3 = float(
        df5.iloc[-3]["close"]
    )

    if direction == "BUY":

        moving_toward = (
            c1 <= c2 <= c3
        )

    else:

        moving_toward = (
            c1 >= c2 >= c3
        )

    near = price_in_zone(
        price,
        zone,
        atr * ZONE_TOLERANCE_ATR,
    )

    if not moving_toward and not near:
        return {
            "valid": False
        }

    return {
        "valid": True,
        "direction": direction,
        "zone": zone,
        "distance": distance,
        "price": price,
    }

# ============================================================
# WATCH SETUP
# ============================================================
def watch_setup(
    frames,
    direction,
):

    df1 = frames["1H"]
    df15 = frames["15M"]
    df5 = frames["5M"]

    atr = atr_value(df1)

    if atr <= 0:
        return {
            "valid": False
        }

    price = float(
        df5.iloc[-1]["close"]
    )

    if direction == "BUY":
        zone = find_demand_zone(df1)
    else:
        zone = find_supply_zone(df1)

    if not price_in_zone(
        price,
        zone,
        atr * ZONE_TOLERANCE_ATR,
    ):

        return {
            "valid": False
        }

    swept, sweep = liquidity_sweep(
        df15,
        direction,
        True,
    )

    bos_ok, bos_level = bos(
        df15,
        direction,
        True,
    )

    choch_ok = choch(
        df15,
        direction,
        True,
    )

    rejection = rejection_candle(
        df15,
        direction,
        True,
    )

    disp = displacement(
        df15,
        direction,
        True,
    )

    partial = (
        swept
        or bos_ok
        or choch_ok
        or rejection
        or disp
    )

    if not partial:
        return {
            "valid": False
        }

    level = (
        bos_level
        if bos_ok
        else sweep
    )

    return {
        "valid": True,
        "direction": direction,
        "price": price,
        "level": level,
        "zone": zone,
        "sweep": sweep,
        "bos": bos_ok,
        "choch": choch_ok,
        "rejection": rejection,
        "displacement": disp,
    }

# ============================================================
# TRADE CONFIRMATION
#
# NEW:
# 5M closed candle trigger is mandatory.
#
# But the old requirement:
# sweep AND rejection AND BOS/CHOCH AND score >= 8
#
# has been relaxed.
# ============================================================
def trade_setup(
    frames,
    direction,
):

    df1 = frames["1H"]
    df15 = frames["15M"]
    df5 = frames["5M"]

    atr1 = atr_value(df1)
    atr5 = atr_value(df5)

    if atr1 <= 0 or atr5 <= 0:
        return {
            "valid": False,
            "score": 0,
        }

    # IMPORTANT:
    # Use the CLOSED 5M candle.
    price = float(
        df5.iloc[-2]["close"]
    )

    if direction == "BUY":
        zone = find_demand_zone(df1)
    else:
        zone = find_supply_zone(df1)

    zone_touch = price_in_zone(
        price,
        zone,
        atr1 * ZONE_TOLERANCE_ATR,
    )

    swept, sweep = liquidity_sweep(
        df15,
        direction,
        True,
    )

    bos_ok, bos_level = bos(
        df15,
        direction,
        True,
    )

    choch_ok = choch(
        df15,
        direction,
        True,
    )

    rejection_15 = rejection_candle(
        df15,
        direction,
        True,
    )

    displacement_15 = displacement(
        df15,
        direction,
        True,
    )

    retest = retest_level(
        df5,
        direction,
        bos_level,
        atr5,
        True,
    )

    rejection_5 = rejection_candle(
        df5,
        direction,
        True,
    )

    displacement_5 = displacement(
        df5,
        direction,
        True,
    )

    # ========================================================
    # REAL 5M TRIGGER
    # ========================================================
    five_trigger = (
        rejection_5
        or displacement_5
    )

    # ========================================================
    # SCORE
    # ========================================================
    score = 0

    if zone_touch:
        score += 2

    if swept:
        score += 2

    if bos_ok:
        score += 2

    if choch_ok:
        score += 1

    if rejection_15:
        score += 1

    if displacement_15:
        score += 1

    if retest:
        score += 1

    if five_trigger:
        score += 1

    # ========================================================
    # STRUCTURE CONFIRMATION
    # ========================================================
    structure_ok = (
        zone_touch
        or swept
        or bos_ok
        or choch_ok
        or rejection_15
        or displacement_15
    )

    # ========================================================
    # FINAL TRADE RULE
    # ========================================================
    valid = (
        five_trigger
        and structure_ok
        and score >= MIN_TRADE_SCORE
    )

    return {
        "valid": valid,
        "score": score,
        "price": price,
        "zone": zone,
        "sweep": sweep,
        "level": (
            bos_level
            if bos_ok
            else sweep
        ),
        "retest": retest,
        "five_trigger": five_trigger,
        "reason": (
            "5M closed confirmation"
            if valid
            else "Waiting for 5M confirmation"
        ),
    }

# ============================================================
# STOP LOSS
# ============================================================
def calculate_sl(
    symbol,
    direction,
    entry,
    frames,
    setup,
):

    cfg = MARKETS[symbol]

    atr5 = atr_value(
        frames["5M"]
    )

    atr15 = atr_value(
        frames["15M"]
    )

    atr = max(
        atr5,
        atr15,
    )

    if atr <= 0:
        return None

    buffer = max(
        cfg["min_sl"]
        * cfg["sl_buffer"],
        atr * 0.10,
    )

    sweep = setup.get(
        "sweep"
    )

    level = setup.get(
        "level"
    )

    if direction == "BUY":

        candidates = [
            entry - cfg["min_sl"]
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

        sl = min(candidates)

        sl_dist = (
            entry - sl
        )

    else:

        candidates = [
            entry + cfg["min_sl"]
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

        sl = max(candidates)

        sl_dist = (
            sl - entry
        )

    max_sl = max(
        cfg["min_sl"] * 5.0,
        atr * 2.0,
    )

    if (
        sl_dist <= 0
        or sl_dist > max_sl
    ):

        return None

    return (
        sl,
        sl_dist,
    )

# ============================================================
# STRUCTURE TARGETS
# ============================================================
def structure_levels(
    dfs,
    direction,
    entry,
):

    levels = []

    for df in dfs:

        if len(df) < 20:
            continue

        if direction == "BUY":

            levels.extend(
                [
                    x[1]
                    for x in swing_highs(df)
                    if x[1] > entry
                ]
            )

        else:

            levels.extend(
                [
                    x[1]
                    for x in swing_lows(df)
                    if x[1] < entry
                ]
            )

    return sorted(
        set(
            round(
                float(x),
                8,
            )
            for x in levels
        )
    )

# ============================================================
# ADAPTIVE TP
# ============================================================
def adaptive_target(
    dfs,
    direction,
    entry,
    sl_dist,
):

    if sl_dist <= 0:

        return (
            None,
            0.0,
            "INVALID",
        )

    minimum_target = (
        sl_dist * MIN_RR
    )

    maximum_target = (
        sl_dist * MAX_RR
    )

    levels = structure_levels(
        dfs,
        direction,
        entry,
    )

    if direction == "BUY":

        valid = [
            x
            for x in levels
            if (
                entry + minimum_target
                <= x
                <= entry + maximum_target
            )
        ]

        if valid:

            target = max(valid)

            rr = (
                target - entry
            ) / sl_dist

            return (
                target,
                rr,
                "STRUCTURE",
            )

        beyond = [
            x
            for x in levels
            if x > entry + minimum_target
        ]

        if beyond:

            return (
                entry + maximum_target,
                MAX_RR,
                "4R-CAPPED",
            )

        return (
            entry + minimum_target,
            MIN_RR,
            "MIN-RR",
        )

    valid = [
        x
        for x in levels
        if (
            entry - maximum_target
            <= x
            <= entry - minimum_target
        )
    ]

    if valid:

        target = min(valid)

        rr = (
            entry - target
        ) / sl_dist

        return (
            target,
            rr,
            "STRUCTURE",
        )

    beyond = [
        x
        for x in levels
        if x < entry - minimum_target
    ]

    if beyond:

        return (
            entry - maximum_target,
            MAX_RR,
            "4R-CAPPED",
        )

    return (
        entry - minimum_target,
        MIN_RR,
        "MIN-RR",
    )

# ============================================================
# LOT SIZE
# ============================================================
def lot_for_risk(
    symbol,
    sl_dist,
):

    dpp = DOLLAR_PER_POINT.get(
        symbol,
        0,
    )

    if sl_dist <= 0 or not dpp:
        return 0.0

    raw = (
        RISK_PER_TRADE
        / (sl_dist * dpp)
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
# COOLDOWN
# ============================================================
def cooldown_ok(
    store,
    key,
    cooldown,
):

    now = time.time()

    return (
        now - store.get(
            key,
            0,
        )
        >= cooldown
    )

# ============================================================
def mark(
    store,
    key,
):

    store[key] = time.time()

# ============================================================
# PRE MESSAGE
# ============================================================
def send_pre(
    symbol,
    setup,
    session,
):

    cfg = MARKETS[symbol]

    decimals = cfg["decimals"]

    zone = setup["zone"]

    direction = setup["direction"]

    if direction == "BUY":

        emoji = "🟢"

        zone_name = "DEMAND"

    else:

        emoji = "🔴"

        zone_name = "SUPPLY"

    message = (
        "⚠️ *ADVANCE PRE-SIGNAL*\n"
        f"*{cfg['execution']}* | {session}\n\n"
        f"{emoji} *Potential {direction} setup "
        f"approaching {zone_name}*\n"
        f"📍 Current price: "
        f"{setup['price']:,.{decimals}f}\n"
        f"📦 Zone: "
        f"{zone['low']:,.{decimals}f} "
        f"→ "
        f"{zone['high']:,.{decimals}f}\n"
        f"📏 Distance: "
        f"{setup['distance']:,.{decimals}f}\n\n"
        "👀 WAIT — NOT A TRADE YET\n"
        "Required next:\n"
        "• 15M liquidity sweep / structure shift\n"
        "• 5M closed confirmation\n"
        f"• Adaptive RR target ≥ {MIN_RR:.2f}R\n\n"
        "🧭 *Advance warning only*"
    )

    send_telegram(message)

# ============================================================
# WATCH MESSAGE
# ============================================================
def send_watch(
    symbol,
    setup,
    session,
):

    cfg = MARKETS[symbol]

    decimals = cfg["decimals"]

    level = setup.get(
        "level"
    )

    if level is None:

        level_text = "forming"

    else:

        level_text = (
            f"{level:,.{decimals}f}"
        )

    message = (
        f"👀 *PA WATCH — "
        f"{cfg['execution']}*\n\n"
        f"Direction: *{setup['direction']}*\n"
        f"Price: *"
        f"{setup['price']:,.{decimals}f}"
        f"*\n"
        f"Structure: *{level_text}*\n"
        "Status: 15M structure forming — "
        "wait for 5M confirmation\n"
        f"Session: {session}"
    )

    send_telegram(message)

# ============================================================
# TRADE MESSAGE
# ============================================================
def send_trade(
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
    rr,
    target_mode,
):

    cfg = MARKETS[symbol]

    decimals = cfg["decimals"]

    if score >= 10:

        quality = "GOD-TIER PA"

    elif score >= 9:

        quality = "A+ PA"

    else:

        quality = "A PA"

    if direction == "BUY":

        direction_icon = "📈"

    else:

        direction_icon = "📉"

    if setup.get("sweep") is not None:

        liquidity = "CONFIRMED"

    else:

        liquidity = "STRUCTURE"

    message = (
        f"🚨 *{VERSION} TRADE SIGNAL*\n"
        f"*{cfg['execution']}*\n\n"
        f"{direction_icon} *{direction}*\n"
        f"🚀 Setup: *{signal_type}*\n"
        f"⭐ PA Score: *{score}/10*\n"
        f"🏆 Quality: *{quality}*\n\n"
        f"📍 Entry: *"
        f"{entry:,.{decimals}f}"
        f"*\n"
        f"🛑 SL: *"
        f"{sl:,.{decimals}f}"
        f"*\n"
        f"🎯 TP: *"
        f"{tp:,.{decimals}f}"
        f"*\n"
        f"⚖️ RR: *1:{rr:.2f}*\n"
        f"🧠 Target: *{target_mode}*\n"
        f"💵 Lot: *{lot}*\n\n"
        "⏱ Structure: 1H → 15M → 5M\n"
        f"📌 Session: {session}\n"
        f"💧 Liquidity: {liquidity}\n"
        "✅ 5M CLOSED CONFIRMATION\n"
        "🚫 No EMA / RSI / ADX / VWAP"
    )

    send_telegram(message)

# ============================================================
# CSV
# ============================================================
def log_signal(
    symbol,
    direction,
    score,
    signal_type,
    entry,
    sl,
    tp,
    rr,
    session,
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
        signal_type,
        entry,
        sl,
        tp,
        rr,
        session,
        target_mode,
    ]

    with file_lock:

        path = "signals_log.csv"

        with open(
            path,
            "a",
            newline="",
            encoding="utf-8",
        ) as file:

            writer = csv.writer(file)

            if os.path.getsize(path) == 0:

                writer.writerow(
                    [
                        "version",
                        "timestamp",
                        "symbol",
                        "direction",
                        "score",
                        "signal_type",
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
# PRE PROCESS
# ============================================================
def process_pre(
    symbol,
    frames,
    session,
):

    for direction in (
        "BUY",
        "SELL",
    ):

        setup = pre_signal_setup(
            frames["1H"],
            frames["15M"],
            frames["5M"],
            direction,
        )

        if not setup["valid"]:
            continue

        key = zone_key(
            symbol,
            direction,
            setup["zone"],
        )

        if key is None:
            continue

        if not cooldown_ok(
            last_pre,
            key,
            PRE_SIGNAL_COOLDOWN,
        ):

            continue

        setup["price"] = float(
            frames["5M"]
            .iloc[-1]["close"]
        )

        setup["direction"] = direction

        send_pre(
            symbol,
            setup,
            session,
        )

        mark(
            last_pre,
            key,
        )

# ============================================================
# WATCH PROCESS
# ============================================================
def process_watch(
    symbol,
    frames,
    session,
):

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

        key = zone_key(
            symbol,
            direction,
            setup["zone"],
        )

        if key is None:
            continue

        if not cooldown_ok(
            last_watch,
            key,
            WATCH_COOLDOWN,
        ):

            continue

        setup["price"] = float(
            frames["5M"]
            .iloc[-1]["close"]
        )

        send_watch(
            symbol,
            setup,
            session,
        )

        mark(
            last_watch,
            key,
        )

        # This setup is now officially active.
        active_setups[key] = {
            "last_seen": time.time(),
            "session": session,
        }

# ============================================================
# TRADE PROCESS
# ============================================================
def process_trade(
    symbol,
    frames,
    session,
):

    if (
        daily_signal_count[symbol]
        >= MARKETS[symbol]["daily_cap"]
    ):

        return

    if not session_gate(
        symbol,
        session,
    ):

        return

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

        zone = setup.get(
            "zone"
        )

        key = zone_key(
            symbol,
            direction,
            zone,
        )

        if key is None:
            continue

        # ====================================================
        # IMPORTANT:
        # A trade must belong to an existing PRE/WATCH setup.
        # ====================================================
        if key not in active_setups:

            continue

        if not cooldown_ok(
            last_trade,
            key,
            TRADE_SIGNAL_COOLDOWN,
        ):

            continue

        # Closed 5M candle price.
        price = float(
            frames["5M"]
            .iloc[-2]["close"]
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

        sl_data = calculate_sl(
            symbol,
            direction,
            entry,
            frames,
            setup,
        )

        if sl_data is None:

            log.info(
                "%s %s rejected: "
                "adaptive SL invalid",
                symbol,
                direction,
            )

            continue

        sl, sl_dist = sl_data

        tp, rr, target_mode = (
            adaptive_target(
                [
                    frames["5M"],
                    frames["15M"],
                    frames["1H"],
                ],
                direction,
                entry,
                sl_dist,
            )
        )

        if (
            tp is None
            or rr < MIN_RR
        ):

            continue

        lot = lot_for_risk(
            symbol,
            sl_dist,
        )

        score = min(
            10,
            max(
                MIN_PA_SCORE_DISPLAY,
                int(
                    setup.get(
                        "score",
                        0,
                    )
                ),
            ),
        )

        if setup.get(
            "sweep"
        ) is not None:

            signal_type = (
                "LIQUIDITY REVERSAL"
            )

        else:

            signal_type = (
                "5M STRUCTURE CONFIRMATION"
            )

        log_signal(
            symbol,
            direction,
            score,
            signal_type,
            entry,
            sl,
            tp,
            rr,
            session,
            target_mode,
        )

        send_trade(
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
            rr,
            target_mode,
        )

        with state_lock:

            mark(
                last_trade,
                key,
            )

            daily_signal_count[
                symbol
            ] += 1

            consume_session(
                symbol,
                session,
            )

            # Setup completed.
            active_setups.pop(
                key,
                None,
            )

        log.info(
            "TRADE %s %s | "
            "entry=%s sl=%s tp=%s "
            "rr=%.2f score=%s",
            symbol,
            direction,
            entry,
            sl,
            tp,
            rr,
            score,
        )

        return

# ============================================================
# SYMBOL PROCESS
# ============================================================
def process_symbol(symbol):

    try:

        if (
            weekend_block()
            or daily_lock()
        ):

            return

        ok, session = in_session(
            symbol
        )

        if not ok:
            return

        if (
            session
            not in MARKETS[symbol]["sessions"]
        ):

            return

        frames = get_frames(
            symbol
        )

        if frames is None:
            return

        # ====================================================
        # STAGE 1
        # ====================================================
        process_pre(
            symbol,
            frames,
            session,
        )

        # ====================================================
        # STAGE 2
        # ====================================================
        process_watch(
            symbol,
            frames,
            session,
        )

        # ====================================================
        # STAGE 3
        # ====================================================
        process_trade(
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
        f"⚡ *{VERSION} LIVE*\n\n"
        "1H = Location / Structure\n"
        "15M = Liquidity + BOS/CHOCH\n"
        "5M = Closed Trigger\n\n"
        f"⚠️ Pre-Signal: "
        f"{PRE_SIGNAL_ATR:.2f} ATR\n"
        "👀 Watch: 15M structure forming\n"
        f"🚨 Trade: score ≥ "
        f"{MIN_TRADE_SCORE} "
        "+ real 5M trigger\n"
        f"⚖️ Adaptive RR: "
        f"{MIN_RR:.2f}R → "
        f"{MAX_RR:.2f}R\n"
        "🎯 5M/15M/1H structure targets\n"
        "🚫 No EMA / RSI / ADX / VWAP\n"
        f"🌐 Markets: "
        f"{len(PRIORITY_MARKETS)}\n"
        f"⏱ Scan: "
        f"{SCAN_INTERVAL:.1f}s\n"
        f"📡 Data: "
        f"{DATA_REFRESH_INTERVAL:.1f}s\n\n"
        "PRE → WATCH → TRADE"
    )

# ============================================================
# WATCHDOG
# ============================================================
def watchdog():

    with open(
        "heartbeat.txt",
        "w",
        encoding="utf-8",
    ) as file:

        file.write(
            f"{datetime.now(timezone.utc).isoformat()} "
            f"| {VERSION} | ACTIVE"
        )

# ============================================================
# MAIN
# ============================================================
def main():

    log.info(
        "%s STARTED",
        VERSION,
    )

    if not TOKEN or not CHAT_ID:

        log.warning(
            "Telegram variables missing. "
            "Set TOKEN and CHAT_ID "
            "in Railway Variables."
        )

    else:

        send_telegram(
            startup_message()
        )

    loop = 0

    last_refresh = 0.0

    while True:

        try:

            reset_daily()

            watchdog()

            now = time.time()

            # =================================================
            # DATA REFRESH
            # =================================================
            if (
                now - last_refresh
                >= DATA_REFRESH_INTERVAL
            ):

                log.info(
                    "DATA refresh | "
                    "%s symbols | "
                    "%.1fs",
                    len(PRIORITY_MARKETS),
                    DATA_REFRESH_INTERVAL,
                )

                with ThreadPoolExecutor(
                    max_workers=len(
                        PRIORITY_MARKETS
                    )
                ) as executor:

                    futures = [
                        executor.submit(
                            refresh_symbol_data,
                            symbol,
                        )
                        for symbol
                        in PRIORITY_MARKETS
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

            # =================================================
            # 1 SECOND PA SCAN
            # =================================================
            with ThreadPoolExecutor(
                max_workers=len(
                    PRIORITY_MARKETS
                )
            ) as executor:

                futures = [
                    executor.submit(
                        process_symbol,
                        symbol,
                    )
                    for symbol
                    in PRIORITY_MARKETS
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

            if loop % 10 == 0:

                log.info(
                    "LIVE scan #%s | "
                    "active_setups=%s",
                    loop,
                    len(active_setups),
                )

            gc.collect()

            time.sleep(
                SCAN_INTERVAL
            )

        except KeyboardInterrupt:

            log.info(
                "Stopped"
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
# START
# ============================================================
if __name__ == "__main__":
    main()
