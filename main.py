# ============================================================
# PEPPERSTONE MOMENTUM HUNTER v23.0-TOPG-QML-REVERSAL
# GOLD + NAS100 + DE30 + US30
# TOPG QML COUNTER-TREND REVERSAL ENGINE
# ============================================================
#
# CHANGE LOG (vs v22.1-INSTITUTIONAL-CONTINUATION-ONLY):
#   Infrastructure is unchanged: Telegram delivery, logging,
#   watchdog/heartbeat, log rotation + backup, circuit breakers
#   (weekend/daily-loss/loss-streak), duplicate-signal filter,
#   session curation, data fetching, indicator engine, lot sizing,
#   and the threaded main loop.
#
#   The STRATEGY engine has been replaced end-to-end to implement
#   the "TopG Gold Reversal Strategy" (QML / Quasimodo retracement
#   model) from the supplied guide:
#     1. IMPULSE      - an aggressive directional move (~$100 on gold
#                        in 2-3 hours per the guide; proportionally
#                        ESTIMATED for the index instruments, see
#                        QML_PARAMS below - tune these)
#     2. CHOCH_1M     - first Change-of-Character on the 1-minute chart
#     3. QML_RETEST   - first retest of the Quasimodo Level formed by
#                        the swing-low -> swing-high -> higher-low ->
#                        break-of-structure sequence (guide Ch.4)
#     4. CONFIRMATION - bullish/bearish engulfing, rejection wick, or
#                        displacement candle in the reversal direction
#     5. SPREAD_OK    - already gated earlier in process_symbol
#
#   All five must be true (an AND-gate / checklist, matching the
#   guide's "only when every condition is present" rule) - this
#   REPLACES the old weighted buy_score/sell_score system, and the
#   old countertrend-blocking filter is gone since this strategy is
#   explicitly counter-trend by design.
#
#   The guide documents the BULLISH case only (buying gold after an
#   aggressive sell-off). The SELL side implemented here is a
#   symmetric mirror (fading an aggressive rally) so the bot keeps
#   working the same way across all four instruments - it is an
#   extrapolation, not something the source PDF specifies.
#
#   Removed (belonged to the old continuation scorer, nothing else
#   in the file used them): build_score, institutional_structure_score,
#   detect_zone_retest, premium_discount, detect_supply_demand_zones,
#   fair_value_gap, RANGE_MIN_SCORE, TREND_MIN_SCORE,
#   MARKET_MIN_STRUCTURE_SCORE, REGIME_TIMEFRAME.
# ============================================================

import time
import logging
import requests
import pandas as pd
import ta
import os
import csv
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

SYSTEM_VERSION = "v23.0-TOPG-QML-REVERSAL"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("v23.0-topg-qml")

# NOTE: this token/chat id were hardcoded as fallback defaults in the
# source file. If this script came from a shared/purchased source
# rather than a bot you created yourself, treat this token as
# compromised and regenerate it via @BotFather - a hardcoded fallback
# means anyone holding a copy of this file can use your bot.
TOKEN   = os.getenv("TOKEN",   "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")

# ============================================================
# MARKETS
# ============================================================
MARKETS = {
    "XAU/USD": {
        "mt5":        "XAUUSD.Qraw",
        "yf":         "GC=F",
        "price_lo":   4000,
        "price_hi":   7000,
        "sessions":   [7, 20],
        "decimals":   2,
        "min_sl":     7.0,
        "tier":       "GOLD ELITE",
        "bias":       "BULL",
        "rr":         2.8,
        "sweep_bonus": 3,
        "wick_ratio": 1.8,
    },
    "NAS100": {
        "mt5":        "NAS100",
        "yf":         "^NDX",
        "price_lo":   15000,
        "price_hi":   30000,
        "sessions":   [13, 21],
        "decimals":   1,
        "min_sl":     55.0,
        "tier":       "NASDAQ ELITE",
        "bias":       "BULL",
        "rr":         2.7,
        "sweep_bonus": 2,
        "wick_ratio": 1.6,
    },
    "DE30": {
        "mt5":        "DE30.Qraw",
        "yf":         "^GDAXI",
        "price_lo":   15000,
        "price_hi":   25000,
        "sessions":   [7, 18],
        "decimals":   1,
        "min_sl":     50.0,
        "tier":       "DE30 ELITE",
        "bias":       "BULL",
        "rr":         2.8,
        "sweep_bonus": 3,
        "wick_ratio": 1.7,
    },
    "US30": {
        "mt5":        "US30",
        "yf":         "^DJI",
        "price_lo":   30000,
        "price_hi":   50000,
        "sessions":   [13, 21],
        "decimals":   1,
        "min_sl":     65.0,
        "tier":       "US30 ELITE",
        "bias":       "BULL",
        "rr":         2.6,
        "sweep_bonus": 2,
        "wick_ratio": 1.5,
    },
}

SYMBOLS = ["XAU/USD", "NAS100", "DE30", "US30"]

# ============================================================
# CORE SETTINGS
# ============================================================
ATR_MULT               = 0.28
VOL_MULT                = 1.05
ADX_THRESHOLD           = 24
SIGNAL_COOLDOWN         = 3600
HTF_REFRESH             = 900
MAX_DAILY_LOSS          = -300
MAX_CONSECUTIVE_LOSSES  = 3
MAIN_LOOP_DELAY         = 2
M1_CACHE_REFRESH        = 55   # seconds; ~1 fresh pull per new 1-minute bar

STDV_PERIOD           = 20
STDV_THRESHOLD_MULT   = 1.15
AOX_FAST              = 5
AOX_SLOW              = 34

# ============================================================
# EXECUTION SLIPPAGE BUFFER
# ============================================================
EXECUTION_BUFFER = {
    "XAU/USD": 0.20,
    "NAS100":  2.5,
    "DE30":    3.0,
    "US30":    2.5,
}

# ============================================================
# MARKET STRUCTURE — CANDLE HISTORY SETTINGS
# (still used: sweep_lookback + displacement_mult feed the
#  confirmation-candle and bonus liquidity-sweep checks below)
# ============================================================
MARKET_STRUCTURE = {
    "XAU/USD": {
        "sweep_lookback":            6,
        "zone_lookback":             10,
        "displacement_mult":         1.20,
        "premium_discount_lookback": 24,
        "wick_ratio":                1.8,
    },
    "NAS100": {
        "sweep_lookback":            8,
        "zone_lookback":             12,
        "displacement_mult":         1.35,
        "premium_discount_lookback": 30,
        "wick_ratio":                2.0,
    },
    "DE30": {
        "sweep_lookback":            7,
        "zone_lookback":             14,
        "displacement_mult":         1.25,
        "premium_discount_lookback": 28,
        "wick_ratio":                1.9,
    },
    "US30": {
        "sweep_lookback":            8,
        "zone_lookback":             12,
        "displacement_mult":         1.30,
        "premium_discount_lookback": 28,
        "wick_ratio":                1.8,
    },
}

# ============================================================
# TOPG QML STRATEGY PARAMETERS
# impulse_threshold is the only figure the guide states explicitly
# (XAU/USD: ~$100 in 2-3 hours). NAS100/DE30/US30 figures are
# proportional ESTIMATES (~1.5-2% of typical price) - backtest and
# tune these before trusting signals on those symbols.
# ============================================================
QML_PARAMS = {
    "XAU/USD": {"impulse_lookback_bars": 30, "impulse_threshold": 100.0, "swing_order": 3, "qml_zone_buffer": 0.0015},
    "NAS100":  {"impulse_lookback_bars": 30, "impulse_threshold": 350.0, "swing_order": 3, "qml_zone_buffer": 0.0015},
    "DE30":    {"impulse_lookback_bars": 30, "impulse_threshold": 300.0, "swing_order": 3, "qml_zone_buffer": 0.0015},
    "US30":    {"impulse_lookback_bars": 30, "impulse_threshold": 650.0, "swing_order": 3, "qml_zone_buffer": 0.0015},
}

# ============================================================
# SESSION CURATION
# ============================================================
LONDON_NY_ONLY = [
    "London",
    "NY+London",
    "NY Killzone"
]

# ============================================================
# ATR MULTIPLIERS
# ============================================================
ATR_MARKET_MULTIPLIER = {
    "XAU/USD": 1.05,
    "NAS100":  1.03,
    "DE30":    1.08,
    "US30":    1.04,
}

# ============================================================
# DOLLAR PER POINT
# ============================================================
DOLLAR_PER_POINT = {
    "XAU/USD": 100,
    "NAS100":  10,
    "DE30":    10,
    "US30":    10,
}

# ============================================================
# MAX SPREAD
# ============================================================
MAX_SPREAD = {
    "XAU/USD": 1.20,
    "NAS100":  4.0,
    "DE30":    5.0,
    "US30":    6.0,
}

# ============================================================
# STATE
# ============================================================
daily_pnl              = 0
consecutive_losses     = 0
last_reset_day         = datetime.now(timezone.utc).day

_signal_sent            = {s: 0 for s in SYMBOLS}
_htf_cache              = {s: {"trend": "NEUTRAL", "ts": 0} for s in SYMBOLS}
_m1_cache               = {s: {"df": None, "ts": 0} for s in SYMBOLS}
_last_signal_direction  = {}
_last_signal_time       = {}
_signal_counter         = {s: {"session": None, "count": 0} for s in SYMBOLS}

# ============================================================
# DAILY RESET & TRADE TRACKING
# ============================================================
def reset_daily():
    global daily_pnl, consecutive_losses, last_reset_day
    current_day = datetime.now(timezone.utc).day
    if current_day != last_reset_day:
        daily_pnl          = 0
        consecutive_losses = 0
        last_reset_day     = current_day
        log.info("Daily reset complete")

def update_trade_result(pnl):
    global daily_pnl, consecutive_losses
    daily_pnl += pnl
    if pnl < 0:
        consecutive_losses += 1
    else:
        consecutive_losses = 0

def sync_real_pnl():
    return daily_pnl

# ============================================================
# WATCHDOG
# ============================================================
def watchdog():
    try:
        with open("heartbeat.txt", "w") as f:
            f.write(
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"{SYSTEM_VERSION} | ACTIVE"
            )
    except Exception as e:
        log.error(f"Watchdog failure: {e}")

# ============================================================
# LOG ROTATION
# ============================================================
def rotate_log():
    file_path = "signals_log.csv"
    if os.path.isfile(file_path):
        if os.path.getsize(file_path) > 5_000_000:
            os.rename(file_path, f"signals_log_{int(time.time())}.csv")

# ============================================================
# SIGNAL LOGGER WITH BACKUP FAILSAFE
# ============================================================
def log_signal(symbol, direction, score, rr, entry, sl, tp,
               session, regime, timeframe, signal_type):
    file_exists = os.path.isfile("signals_log.csv")
    with open("signals_log.csv", "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "version", "timestamp", "symbol", "direction",
                "score", "rr", "entry", "sl", "tp",
                "session", "regime", "timeframe", "signal_type"
            ])
        writer.writerow([
            SYSTEM_VERSION,
            datetime.now(timezone.utc).isoformat(),
            symbol, direction, score, rr,
            entry, sl, tp, session, regime, timeframe, signal_type
        ])

    try:
        with open("signals_backup.csv", "a", newline="") as backup:
            backup_writer = csv.writer(backup)
            backup_writer.writerow([
                SYSTEM_VERSION,
                datetime.now(timezone.utc).isoformat(),
                symbol, direction, score, rr,
                entry, sl, tp, session,
                regime, timeframe, signal_type
            ])
    except Exception as e:
        log.error(f"Backup log failed: {e}")

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(msg):
    for attempt in range(3):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={
                    "chat_id":    CHAT_ID,
                    "text":       msg,
                    "parse_mode": "Markdown"
                },
                timeout=8
            )
            if r.status_code != 200:
                log.error(
                    f"Telegram HTTP Error {r.status_code} | "
                    f"Response: {r.text}"
                )
                time.sleep(2)
                continue
            log.info(f"Telegram sent | {r.text}")
            return True
        except Exception as e:
            log.error(f"Telegram error attempt {attempt + 1}: {e}")
            time.sleep(2)
    return False

# ============================================================
# CIRCUIT BREAKERS
# ============================================================
def weekend_block(symbol_key):
    return datetime.now(timezone.utc).weekday() >= 5

def daily_loss_lock():
    if daily_pnl <= MAX_DAILY_LOSS:
        log.info("Daily loss lock active")
        return True
    return False

def loss_streak_lock():
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        log.info("Kill switch: 3 consecutive losses")
        return True
    return False

# ============================================================
# DUPLICATE SIGNAL FILTER
# ============================================================
def duplicate_signal(symbol_key, direction):
    now = time.time()

    duplicate_windows = {
        "XAU/USD": 3600,
        "NAS100":  5400,
        "DE30":    10800,
        "US30":    5400,
    }

    cooldown = duplicate_windows.get(symbol_key, 5400)

    if (
        _last_signal_direction.get(symbol_key) == direction
        and now - _last_signal_time.get(symbol_key, 0) < cooldown
    ):
        remaining = int(cooldown - (now - _last_signal_time.get(symbol_key, 0)))
        log.info(f"Duplicate signal blocked for {symbol_key} ({remaining}s remaining)")
        return True

    _last_signal_direction[symbol_key] = direction
    _last_signal_time[symbol_key]      = now
    return False

def economic_news_block():
    # Deliberately a no-op: per the guide, the impulsive moves this
    # strategy waits for are usually CAUSED by news events (NFP, CPI,
    # FOMC, geopolitical shocks). Blocking around news would filter
    # out exactly the conditions the setup depends on.
    return False

# ============================================================
# SYMBOL-SPECIFIC SCAN DELAY
# ============================================================
def get_scan_delay(symbol_key):
    delays = {"XAU/USD": 3, "NAS100": 5, "DE30": 5, "US30": 5}
    return delays.get(symbol_key, 5)

# ============================================================
# SESSION FILTER (FINAL OPTIMIZED VERSION)
# ============================================================
def in_session(symbol_key):
    h = datetime.now(timezone.utc).hour
    s, e = MARKETS[symbol_key]["sessions"]

    if not (s <= h < e):
        return False, "Closed"

    if h < 7:
        return False, "Asian"

    if 7 <= h < 12:
        return True, "London"

    if 13 <= h < 15:
        return True, "NY Killzone"

    if 12 <= h < 16:
        return True, "NY+London"

    return False, "Closed"

# ============================================================
# DATA FETCHING
# ============================================================
def fetch_yf(ticker, period="15d", interval="5m"):
    try:
        raw = yf.download(
            ticker, period=period, interval=interval,
            progress=False, auto_adjust=True
        )
        if raw.empty:
            return None
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw.columns = [str(c).lower() for c in raw.columns]
        return raw[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
    except:
        return None

def get_entry_data(symbol_key):
    yf_sym = MARKETS[symbol_key]["yf"]

    if yf_sym:
        df = fetch_yf(yf_sym)

        if df is None:
            log.error(f"{symbol_key} data fetch failed")
            return None, None

        if len(df) > 100:
            return df, "yf"

    return None, None

def get_m1_data(symbol_key):
    """1-minute data, used only for the CHOCH_1M check the guide calls
    for. Cached briefly since Yahoo only retains ~7d of 1m history and
    there's no point re-pulling faster than a new 1m bar can form."""
    cache = _m1_cache[symbol_key]
    now = time.time()
    if cache["df"] is not None and now - cache["ts"] < M1_CACHE_REFRESH:
        return cache["df"]

    yf_sym = MARKETS[symbol_key]["yf"]
    df = fetch_yf(yf_sym, period="5d", interval="1m")
    if df is not None and len(df) > 20:
        cache["df"] = df
        cache["ts"] = now
        return df
    return cache["df"]

def get_spread(df):
    if df is None or len(df) < 3:
        return 999
    recent    = df.tail(3)
    avg_range = (
        recent["high"].astype(float) - recent["low"].astype(float)
    ).mean()
    return avg_range * 0.18

# ============================================================
# INDICATORS
# ============================================================
def add_ind(df):
    df  = df.copy()
    cl  = pd.to_numeric(df["close"],  errors="coerce")
    hi  = pd.to_numeric(df["high"],   errors="coerce")
    lo  = pd.to_numeric(df["low"],    errors="coerce")
    vol = pd.to_numeric(df["volume"], errors="coerce")

    df["ema9"]     = ta.trend.EMAIndicator(cl, 9).ema_indicator()
    df["ema21"]    = ta.trend.EMAIndicator(cl, 21).ema_indicator()
    df["ema50"]    = ta.trend.EMAIndicator(cl, 50).ema_indicator()
    df["ema200"]   = ta.trend.EMAIndicator(cl, 200).ema_indicator()
    df["rsi"]      = ta.momentum.RSIIndicator(cl, 14).rsi()
    df["atr"]      = ta.volatility.AverageTrueRange(hi, lo, cl, 14).average_true_range()
    df["adx"]      = ta.trend.ADXIndicator(hi, lo, cl, 14).adx()
    df["volma"]    = vol.rolling(20).mean()
    df["vwap"]     = (cl * vol).cumsum() / vol.cumsum()
    df["stdv"]     = cl.rolling(STDV_PERIOD).std()
    df["aox_fast"] = ta.trend.EMAIndicator(cl, AOX_FAST).ema_indicator()
    df["aox_slow"] = ta.trend.EMAIndicator(cl, AOX_SLOW).ema_indicator()
    df["aox"]      = df["aox_fast"] - df["aox_slow"]

    df.replace([float("inf"), float("-inf")], pd.NA, inplace=True)
    df.dropna(inplace=True)

    return df

# ============================================================
# HTF TREND (context only now - no longer gates entries; this is a
# counter-trend strategy by design, per the guide)
# ============================================================
def get_trend(symbol_key):
    cache = _htf_cache[symbol_key]
    now   = time.time()
    if now - cache["ts"] < HTF_REFRESH:
        return cache["trend"]
    df, _ = get_entry_data(symbol_key)
    if df is None:
        return "NEUTRAL"
    df = add_ind(df)
    if df is None or len(df) < 50:
        return "NEUTRAL"
    last = df.iloc[-1]
    if last["ema21"] > last["ema50"]:
        trend = "BULL"
    elif last["ema21"] < last["ema50"]:
        trend = "BEAR"
    else:
        trend = MARKETS[symbol_key].get("bias", "NEUTRAL")
    cache["trend"] = trend
    cache["ts"]    = now
    return trend

# ============================================================
# REUSABLE CANDLE/STRUCTURE PRIMITIVES (kept from v22.1)
# ============================================================
def detect_choch(df):
    if len(df) < 6:
        return False, False
    highs = df["high"].tail(6).tolist()
    lows  = df["low"].tail(6).tolist()
    close = float(df.iloc[-1]["close"])
    return (
        lows[-2]  < lows[-3]  and close > highs[-2],
        highs[-2] > highs[-3] and close < lows[-2]
    )

def detect_liquidity_sweep(df, symbol_key):
    lookback  = MARKET_STRUCTURE[symbol_key]["sweep_lookback"]
    if len(df) < lookback:
        return False, False
    recent    = df.tail(lookback)
    prev_high = float(recent["high"].iloc[:-1].max())
    prev_low  = float(recent["low"].iloc[:-1].min())
    last      = recent.iloc[-1]
    bullish_sweep = (
        float(last["low"]) < prev_low
        and float(last["close"]) > prev_low
    )
    bearish_sweep = (
        float(last["high"]) > prev_high
        and float(last["close"]) < prev_high
    )
    return bullish_sweep, bearish_sweep

def detect_displacement(df, symbol_key):
    if len(df) < 2:
        return False
    mult   = MARKET_STRUCTURE[symbol_key]["displacement_mult"]
    candle = df.iloc[-1]
    body   = abs(float(candle["close"]) - float(candle["open"]))
    atr    = float(candle["atr"])
    return body > atr * mult

def detect_wick_rejection(df, atr, symbol_key):
    if len(df) < 2:
        return False, False
    candle      = df.iloc[-1]
    open_price  = float(candle["open"])
    close_price = float(candle["close"])
    high_price  = float(candle["high"])
    low_price   = float(candle["low"])
    body        = abs(close_price - open_price)
    if body < atr * 0.05:
        return False, False
    upper_wick     = high_price - max(open_price, close_price)
    lower_wick     = min(open_price, close_price) - low_price
    wick_ratio     = MARKETS[symbol_key]["wick_ratio"]
    bullish_reject = lower_wick > body * wick_ratio
    bearish_reject = upper_wick > body * wick_ratio
    return bullish_reject, bearish_reject

# ============================================================
# TOPG QML REVERSAL ENGINE (new)
# ============================================================
def detect_impulsive_move(df, symbol_key):
    """Guide Ch.2 / Step 1: an aggressive directional move of at least
    impulse_threshold points inside impulse_lookback_bars candles
    (~2-3h on 5m bars). Direction is decided by whether the window's
    single highest high or single lowest low came first."""
    params = QML_PARAMS[symbol_key]
    lookback = params["impulse_lookback_bars"]
    if len(df) < lookback:
        return False, False, 0.0

    window      = df.tail(lookback)
    window_high = float(window["high"].max())
    window_low  = float(window["low"].min())
    high_pos    = int(window["high"].values.argmax())
    low_pos     = int(window["low"].values.argmin())
    move        = window_high - window_low
    threshold   = params["impulse_threshold"]

    bearish_impulse = bool(high_pos < low_pos and move >= threshold)
    bullish_impulse = bool(low_pos < high_pos and move >= threshold)
    return bearish_impulse, bullish_impulse, move

def find_swing_points(df, order=3):
    """Fractal swing high/low detector. df must already be reset-index
    (0..n-1). Returns [(position, price), ...] lists."""
    highs = df["high"].astype(float).values
    lows  = df["low"].astype(float).values
    n = len(df)
    swing_highs, swing_lows = [], []
    for i in range(order, n - order):
        seg_low  = lows[i - order:i + order + 1]
        seg_high = highs[i - order:i + order + 1]
        if lows[i] == seg_low.min():
            swing_lows.append((i, float(lows[i])))
        if highs[i] == seg_high.max():
            swing_highs.append((i, float(highs[i])))
    return swing_highs, swing_lows

def detect_qml_bullish(df, symbol_key, lookback=80):
    """Guide Ch.4-5, bullish case:
      L1 (swing low) -> H1 (swing high) -> L2 (higher low) ->
      BOS (close breaks above H1) -> price retests the L2 zone
      (the 'prior structural area' = the Quasimodo Level) for the
      first time since the BOS."""
    params = QML_PARAMS[symbol_key]
    sub = df.tail(lookback).reset_index(drop=True)
    swing_highs, swing_lows = find_swing_points(sub, order=params["swing_order"])
    if len(swing_lows) < 2 or len(swing_highs) < 1:
        return None

    n = len(sub)
    closes = sub["close"].astype(float).values
    lows   = sub["low"].astype(float).values
    recency_floor = n - params["impulse_lookback_bars"] - 10

    for li in range(len(swing_lows) - 1, 0, -1):
        l2_idx, l2_price = swing_lows[li]
        l1_idx, l1_price = swing_lows[li - 1]
        if l1_idx < recency_floor:
            continue
        if l2_idx <= l1_idx or l2_price <= l1_price:
            continue

        h1_candidates = [h for h in swing_highs if l1_idx < h[0] < l2_idx]
        if not h1_candidates:
            continue
        h1_idx, h1_price = max(h1_candidates, key=lambda x: x[1])

        bos_idx = None
        for j in range(l2_idx + 1, n):
            if closes[j] > h1_price:
                bos_idx = j
                break
        if bos_idx is None or bos_idx >= n - 1:
            continue

        buf = params["qml_zone_buffer"]
        qml_low  = l2_price * (1 - buf)
        qml_high = l2_price * (1 + buf)

        already_retested = any(lows[k] <= qml_high for k in range(bos_idx + 1, n - 1))
        if already_retested:
            continue

        retesting_now = lows[-1] <= qml_high and closes[-1] >= qml_low * 0.995
        if retesting_now:
            return {"l1": l1_price, "h1": h1_price, "l2": l2_price,
                    "qml_low": qml_low, "qml_high": qml_high}
    return None

def detect_qml_bearish(df, symbol_key, lookback=80):
    """Symmetric mirror of detect_qml_bullish for the SELL side
    (fading an aggressive rally). NOTE: the source guide only
    documents the bullish gold case - this mirror is an
    extrapolation to keep the bot's existing two-sided behaviour."""
    params = QML_PARAMS[symbol_key]
    sub = df.tail(lookback).reset_index(drop=True)
    swing_highs, swing_lows = find_swing_points(sub, order=params["swing_order"])
    if len(swing_highs) < 2 or len(swing_lows) < 1:
        return None

    n = len(sub)
    closes = sub["close"].astype(float).values
    highs  = sub["high"].astype(float).values
    recency_floor = n - params["impulse_lookback_bars"] - 10

    for hi in range(len(swing_highs) - 1, 0, -1):
        h2_idx, h2_price = swing_highs[hi]
        h1_idx, h1_price = swing_highs[hi - 1]
        if h1_idx < recency_floor:
            continue
        if h2_idx <= h1_idx or h2_price >= h1_price:
            continue

        l1_candidates = [l for l in swing_lows if h1_idx < l[0] < h2_idx]
        if not l1_candidates:
            continue
        l1_idx, l1_price = min(l1_candidates, key=lambda x: x[1])

        bos_idx = None
        for j in range(h2_idx + 1, n):
            if closes[j] < l1_price:
                bos_idx = j
                break
        if bos_idx is None or bos_idx >= n - 1:
            continue

        buf = params["qml_zone_buffer"]
        qml_low  = h2_price * (1 - buf)
        qml_high = h2_price * (1 + buf)

        already_retested = any(highs[k] >= qml_low for k in range(bos_idx + 1, n - 1))
        if already_retested:
            continue

        retesting_now = highs[-1] >= qml_low and closes[-1] <= qml_high * 1.005
        if retesting_now:
            return {"h1": h1_price, "l1": l1_price, "h2": h2_price,
                    "qml_low": qml_low, "qml_high": qml_high}
    return None

def detect_engulfing(df):
    if len(df) < 2:
        return False, False
    prev = df.iloc[-2]
    curr = df.iloc[-1]
    po, pc = float(prev["open"]), float(prev["close"])
    co, cc = float(curr["open"]), float(curr["close"])
    bullish_engulf = pc < po and cc > co and cc >= po and co <= pc
    bearish_engulf = pc > po and cc < co and cc <= po and co >= pc
    return bullish_engulf, bearish_engulf

def detect_confirmation_candle(df, symbol_key, direction):
    """Guide Ch.5 Step 4: engulfing OR rejection wick OR a strong
    displacement candle closing in the reversal direction."""
    atr = float(df.iloc[-1]["atr"])
    bull_engulf, bear_engulf = detect_engulfing(df)
    bull_wick, bear_wick     = detect_wick_rejection(df, atr, symbol_key)
    displacement               = detect_displacement(df, symbol_key)
    curr = df.iloc[-1]
    bullish_close = float(curr["close"]) > float(curr["open"])
    bearish_close = float(curr["close"]) < float(curr["open"])

    if direction == "BUY":
        return bool(bull_engulf or bull_wick or (displacement and bullish_close))
    return bool(bear_engulf or bear_wick or (displacement and bearish_close))

def detect_choch_1m(symbol_key, direction):
    """Guide Ch.5 Step 2: first CHOCH on the 1-minute chart."""
    df = get_m1_data(symbol_key)
    if df is None or len(df) < 20:
        return False
    bull_choch, bear_choch = detect_choch(df)
    return bull_choch if direction == "BUY" else bear_choch

def build_qml_checklist(df, symbol_key, direction, spread_ok):
    """Guide Ch.6 entry checklist as an explicit AND-gate - every item
    must be True (matches 'only when every condition is present')."""
    bearish_impulse, bullish_impulse, move_size = detect_impulsive_move(df, symbol_key)
    impulse_ok = bearish_impulse if direction == "BUY" else bullish_impulse

    choch_ok = detect_choch_1m(symbol_key, direction)

    qml = (detect_qml_bullish(df, symbol_key) if direction == "BUY"
           else detect_qml_bearish(df, symbol_key))
    qml_ok = qml is not None

    confirmation_ok = detect_confirmation_candle(df, symbol_key, direction) if qml_ok else False

    checklist = {
        "IMPULSE":      impulse_ok,
        "CHOCH_1M":     choch_ok,
        "QML_RETEST":   qml_ok,
        "CONFIRMATION": confirmation_ok,
        "SPREAD_OK":    spread_ok,
    }
    return checklist, all(checklist.values()), move_size, qml

# ============================================================
# MARKET REGIME (informational only - no longer gates entries)
# ============================================================
def detect_market_regime(df):
    adx = float(df.iloc[-1]["adx"])
    if adx >= 35:
        return "BREAKOUT"
    elif adx >= 25:
        return "TREND"
    else:
        return "RANGE"

# ============================================================
# SIGNAL COUNTER
# ============================================================
def get_signal_number(symbol_key, session):
    global _signal_counter

    if _signal_counter[symbol_key]["session"] != session:
        _signal_counter[symbol_key]["session"] = session
        _signal_counter[symbol_key]["count"]   = 1
    else:
        _signal_counter[symbol_key]["count"] += 1

    signal_num = _signal_counter[symbol_key]["count"]

    if signal_num == 1:
        entry_type = "PRIMARY QML RETEST"
    elif signal_num == 2:
        entry_type = "SECONDARY QML RETEST"
    else:
        entry_type = "EXTENDED QML RETEST"

    return signal_num, entry_type

# ============================================================
# LEVELS (guide Ch.7-8: structure-based SL, RR-based Target 1)
# ============================================================
def calc_levels(price, atr, symbol_key, df, direction, qml):
    min_sl   = MARKETS[symbol_key]["min_sl"]
    decimals = MARKETS[symbol_key]["decimals"]
    rr       = MARKETS[symbol_key]["rr"]
    buffer   = atr * ATR_MARKET_MULTIPLIER[symbol_key] * 0.20
    last_low  = float(df.iloc[-1]["low"])
    last_high = float(df.iloc[-1]["high"])

    if direction == "BUY":
        structure_low = min(qml["qml_low"], last_low) if qml else last_low
        sl_dist = max(min_sl, price - structure_low + buffer)
        sl = price - sl_dist
        tp = price + sl_dist * rr
    else:
        structure_high = max(qml["qml_high"], last_high) if qml else last_high
        sl_dist = max(min_sl, structure_high + buffer - price)
        sl = price + sl_dist
        tp = price - sl_dist * rr

    return round(sl, decimals), round(tp, decimals), round(sl_dist, decimals), rr

# ============================================================
# LOT SIZE
# ============================================================
def lot_for_risk(price, sl, symbol_key, risk=25):
    sl_dist = abs(price - sl)
    if sl_dist <= 0:
        return 0.01
    lot = risk / (sl_dist * DOLLAR_PER_POINT[symbol_key])
    caps = {
        "XAU/USD": 1.50,
        "NAS100":  2.00,
        "DE30":    1.50,
        "US30":    1.50,
    }
    return round(max(0.01, min(lot, caps[symbol_key])), 3)

# ============================================================
# PROCESS SYMBOL
# ============================================================
def process_symbol(symbol_key):
    log.info(f"Scanning {symbol_key}")

    if weekend_block(symbol_key):
        return
    if daily_loss_lock():
        return
    if loss_streak_lock():
        return

    watchdog()
    rotate_log()

    ok, session = in_session(symbol_key)
    if not ok:
        return

    if session not in LONDON_NY_ONLY:
        log.info(f"REJECTED {symbol_key} outside curated session ({session})")
        return

    if economic_news_block():
        log.info(f"BLOCKED {symbol_key} news window")
        return

    df, source = get_entry_data(symbol_key)
    if df is None or len(df) < 100:
        return

    spread = get_spread(df)
    if spread > MAX_SPREAD[symbol_key] * 0.90:
        log.info(f"REJECTED {symbol_key} spread {spread:.4f}")
        return

    df = add_ind(df)
    if df is None or len(df) < 90:
        log.info(f"REJECTED {symbol_key} insufficient cleaned data")
        return

    price = float(df.iloc[-1]["close"])
    atr   = float(df.iloc[-1]["atr"])

    if price <= 0:
        log.info(f"REJECTED {symbol_key} invalid price")
        return

    if not (MARKETS[symbol_key]["price_lo"] <= price <= MARKETS[symbol_key]["price_hi"]):
        log.info(f"REJECTED {symbol_key} price out of range")
        return

    trend  = get_trend(symbol_key)
    regime = detect_market_regime(df)

    checklist_buy,  buy_ready,  buy_move,  qml_buy  = build_qml_checklist(df, symbol_key, "BUY",  True)
    checklist_sell, sell_ready, sell_move, qml_sell = build_qml_checklist(df, symbol_key, "SELL", True)

    log.info(
        f"{symbol_key} | BUY {sum(checklist_buy.values())}/5 | "
        f"SELL {sum(checklist_sell.values())}/5 | Regime: {regime} | "
        f"Trend: {trend} | Session: {session}"
    )

    if not buy_ready and not sell_ready:
        return

    if buy_ready:
        direction, checklist, qml, move_size = "BUY", checklist_buy, qml_buy, buy_move
    else:
        direction, checklist, qml, move_size = "SELL", checklist_sell, qml_sell, sell_move

    if duplicate_signal(symbol_key, direction):
        return

    now = time.time()
    if now - _signal_sent[symbol_key] < SIGNAL_COOLDOWN:
        remaining = int(SIGNAL_COOLDOWN - (now - _signal_sent[symbol_key]))
        log.info(f"REJECTED {symbol_key} cooldown {remaining}s")
        return

    _signal_sent[symbol_key] = now

    if direction == "BUY":
        price += EXECUTION_BUFFER[symbol_key]
    else:
        price -= EXECUTION_BUFFER[symbol_key]

    sl, tp, sl_dist, rr = calc_levels(price, atr, symbol_key, df, direction, qml)
    lot         = lot_for_risk(price, sl, symbol_key)
    timeframe   = "1M CHOCH / 5M Structure"
    signal_type = "QML_REVERSAL"
    signal_num, entry_type = get_signal_number(symbol_key, session)

    dec = MARKETS[symbol_key]["decimals"]
    rsi = float(df.iloc[-1]["rsi"])
    adx = float(df.iloc[-1]["adx"])

    checklist_score = sum(checklist.values())
    log_signal(symbol_key, direction, checklist_score, rr, price, sl, tp,
               session, regime, timeframe, signal_type)
    sync_real_pnl()

    cond_text = "\n".join([f" {k}" for k, v in checklist.items() if v])

    sweep_note = ""
    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    if (direction == "BUY" and bull_sweep) or (direction == "SELL" and bear_sweep):
        sweep_note = "\n LIQUIDITY_SWEEP (bonus confluence)"

    action_emoji  = "📈" if direction == "BUY" else "📉"
    impulse_label = (
        "Bearish impulse -> buy-the-dip reversal" if direction == "BUY"
        else "Bullish impulse -> sell-the-rip reversal"
    )

    msg = (
        f"🎯 *{SYSTEM_VERSION}* | TOPG QML EXECUTION\n"
        f"*{MARKETS[symbol_key]['mt5']}* | ⭐⭐⭐⭐⭐ {MARKETS[symbol_key]['tier']}\n\n"
        f"🔥 *Action:* {direction} {action_emoji}\n"
        f"🔁 *Setup:* {impulse_label}\n"
        f"🎯 *Signal #:* {signal_num}\n"
        f"📍 *Entry Type:* {entry_type}\n"
        f"🚀 *Signal Type:* QML REVERSAL\n"
        f"⭐ *Checklist:* {checklist_score}/5\n"
        f"🧠 *Regime:* {regime}\n"
        f"⏱ *Timeframe:* {timeframe}\n"
        f"📏 *Impulse size:* {move_size:.{dec}f}\n\n"
        f"📍 *Entry:* {price:,.{dec}f}\n"
        f"🛑 *SL:* {sl:,.{dec}f} (beyond QML structure)\n"
        f"🎯 *TP1:* {tp:,.{dec}f} *(1:{rr} RR)*\n"
        f"ℹ️ *TP2/TP3:* manage manually - next HTF liquidity / major structure\n\n"
        f"📈 *RSI:* {rsi:.1f}\n"
        f"📉 *ADX:* {adx:.1f}\n"
        f"🌍 *HTF Trend:* {trend} (this is a counter-trend retracement)\n"
        f"⏰ *Session:* {session}\n"
        f"📡 *Source:* {source}\n\n"
        f"💵 *Lot:* {lot}\n\n"
        f"✅ *Checklist Passed:*\n"
        f"{cond_text}"
        f"{sweep_note}\n\n"
        f"🛡 *TOPG QML REVERSAL FILTER ACTIVE*\n"
        f"⚡ *COUNTER-TREND INSTITUTIONAL MODE*"
    )

    send_telegram(msg)

    log.info(
        f"SIGNAL SENT {symbol_key} {direction} | "
        f"Entry: {price} | SL: {sl} | TP: {tp} | "
        f"RR: {rr} | Type: QML_REVERSAL | Signal#: {signal_num} | "
        f"EntryType: {entry_type} | Regime: {regime} | TF: {timeframe}"
    )

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    log.info(f"{SYSTEM_VERSION} STARTED")
    send_telegram(
        f"🚀 *{SYSTEM_VERSION} LIVE*\n\n"
        f"📊 *Markets Active:*\n"
        f"🥇 XAU/USD\n"
        f"📈 NAS100\n"
        f"🇩🇪 DE30\n"
        f"🇺🇸 US30\n\n"
        f"🔁 TopG QML Reversal Engine Active\n"
        f"🛡 Impulse -> 1M CHOCH -> QML Retest -> Confirmation\n"
        f"⚡ Counter-Trend Institutional Mode"
    )

    while True:
        try:
            reset_daily()

            with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
                futures = []
                for symbol in SYMBOLS:
                    futures.append(
                        executor.submit(process_symbol, symbol)
                    )
                    time.sleep(0.15)

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        log.error(f"Thread error: {e}")

            time.sleep(MAIN_LOOP_DELAY)

        except Exception as e:
            log.error(f"Main loop error: {e}")
            time.sleep(MAIN_LOOP_DELAY)

if __name__ == "__main__":
    main()
