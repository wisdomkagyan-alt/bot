# ============================================================
# PEPPERSTONE MOMENTUM HUNTER
# ULTIMATE-HYBRID-SUPREME-2026-ELITE — SCALPER EDITION
# XAU/USD + NAS100 + SPX500 + EUR/USD + GBP/JPY
# SCALP MODE: 1M / 5M SIGNALS ONLY
# ============================================================

import gc
import time
import logging
import requests
import pandas as pd
import ta
import os
import csv
from threading import Lock
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

SYSTEM_VERSION = "ULTIMATE-HYBRID-SUPREME-2026-ELITE-SCALPER"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("SCALPER-SUPREME-2026")

TOKEN   = os.getenv("TOKEN",   "8641713322:AAHZeJOz0_LILD076P1ShvXSfCqQ1xrpFlk")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")

session_http = requests.Session()
signal_lock  = Lock()
log_lock     = Lock()

# ============================================================
# PRIORITY MARKETS
# ============================================================
PRIORITY_MARKETS = [
    "XAU/USD",
    "NAS100",
    "SPX500",
    "EUR/USD",
    "GBP/JPY",
]

# ============================================================
# SESSION SCORE THRESHOLDS — SCALP TUNED (LOWER = MORE SIGNALS)
# ============================================================
SESSION_THRESHOLDS = {
    "Asian Precision": 13,
    "London":          12,
    "NY Killzone":     12,
    "NY+London":       11,
}

# ============================================================
# SCALP RR PROFILES (1:1.5 – 1:2.0 for fast scalps)
# ============================================================
RR_PROFILE = {
    "XAU/USD": {"SCALP": 1.8},
    "NAS100":  {"SCALP": 1.7},
    "SPX500":  {"SCALP": 1.6},
    "EUR/USD": {"SCALP": 1.5},
    "GBP/JPY": {"SCALP": 1.8},
}

# ============================================================
# MARKETS
# ============================================================
MARKETS = {
    "XAU/USD": {
        "mt5":         "XAUUSD.Qraw",
        "yf":          "GC=F",
        "price_lo":    0,
        "price_hi":    float("inf"),
        "sessions":    [0, 20],
        "decimals":    2,
        "min_sl":      3.0,        # tighter for scalp
        "tier":        "GOLD ELITE",
        "bias":        "BULL",
        "rr":          1.8,
        "sweep_bonus": 2,
        "wick_ratio":  1.6,
    },
    "NAS100": {
        "mt5":         "NAS100",
        "yf":          "^NDX",
        "price_lo":    0,
        "price_hi":    float("inf"),
        "sessions":    [0, 21],
        "decimals":    1,
        "min_sl":      20.0,
        "tier":        "NASDAQ ELITE",
        "bias":        "BULL",
        "rr":          1.7,
        "sweep_bonus": 2,
        "wick_ratio":  1.5,
    },
    "SPX500": {
        "mt5":         "SPX500",
        "yf":          "^GSPC",
        "price_lo":    0,
        "price_hi":    float("inf"),
        "sessions":    [0, 21],
        "decimals":    1,
        "min_sl":      10.0,
        "tier":        "SP500 ELITE",
        "bias":        "BULL",
        "rr":          1.6,
        "sweep_bonus": 2,
        "wick_ratio":  1.4,
    },
    "EUR/USD": {
        "mt5":         "EURUSD",
        "yf":          "EURUSD=X",
        "price_lo":    0,
        "price_hi":    float("inf"),
        "sessions":    [0, 24],
        "decimals":    5,
        "min_sl":      0.00050,
        "tier":        "FOREX MAJOR ELITE",
        "bias":        "BULL",
        "rr":          1.5,
        "sweep_bonus": 1,
        "wick_ratio":  1.3,
    },
    "GBP/JPY": {
        "mt5":         "GBPJPY",
        "yf":          "GBPJPY=X",
        "price_lo":    0,
        "price_hi":    float("inf"),
        "sessions":    [0, 24],
        "decimals":    3,
        "min_sl":      0.080,
        "tier":        "FOREX VOLATILITY ELITE",
        "bias":        "BULL",
        "rr":          1.8,
        "sweep_bonus": 2,
        "wick_ratio":  1.5,
    },
}

SYMBOLS = [
    "XAU/USD",
    "NAS100",
    "SPX500",
    "EUR/USD",
    "GBP/JPY",
]

# ============================================================
# CORE SETTINGS — SCALP TUNED
# ============================================================
ATR_MULT               = 0.18          # tighter stops for scalp
VOL_MULT               = 1.05          # slightly lower volume bar for scalp
ADX_THRESHOLD          = 20            # lower ADX for short-term momentum
SIGNAL_COOLDOWN        = 900           # 15 min cooldown between signals
HTF_REFRESH            = 300           # 5 min HTF cache refresh
MAX_DAILY_LOSS         = -300
MAX_CONSECUTIVE_LOSSES = 3
MAIN_LOOP_DELAY        = 3             # faster loop for scalping

STDV_PERIOD         = 10              # shorter std dev window
STDV_THRESHOLD_MULT = 1.10
AOX_FAST            = 3               # faster AOX for scalp
AOX_SLOW            = 13

ENABLE_WIZARD_AI     = True
WIZARD_MIN_SCORE     = 12             # lowered for scalp
WIZARD_VOLUME_MULT   = 1.3
WIZARD_ADX_THRESHOLD = 20

CORRELATION_BLOCK   = True
MAX_OPEN_CORRELATED = 2
VOLATILITY_KILL     = True
FALSE_BREAK_FILTER  = True

# ============================================================
# EXECUTION SLIPPAGE BUFFER
# ============================================================
EXECUTION_BUFFER = {
    "XAU/USD": 0.15,
    "NAS100":  1.5,
    "SPX500":  1.0,
    "EUR/USD": 0.00005,
    "GBP/JPY": 0.010,
}

# ============================================================
# SCORE THRESHOLDS
# ============================================================
RANGE_MIN_SCORE = 5
TREND_MIN_SCORE = 6

# ============================================================
# MARKET STRUCTURE
# ============================================================
MARKET_STRUCTURE = {
    "XAU/USD": {
        "sweep_lookback":            4,
        "zone_lookback":             6,
        "displacement_mult":         1.10,
        "premium_discount_lookback": 12,
        "wick_ratio":                1.6,
    },
    "NAS100": {
        "sweep_lookback":            5,
        "zone_lookback":             8,
        "displacement_mult":         1.20,
        "premium_discount_lookback": 15,
        "wick_ratio":                1.8,
    },
    "SPX500": {
        "sweep_lookback":            5,
        "zone_lookback":             6,
        "displacement_mult":         1.15,
        "premium_discount_lookback": 13,
        "wick_ratio":                1.5,
    },
    "EUR/USD": {
        "sweep_lookback":            6,
        "zone_lookback":             8,
        "displacement_mult":         1.05,
        "premium_discount_lookback": 16,
        "wick_ratio":                1.3,
    },
    "GBP/JPY": {
        "sweep_lookback":            5,
        "zone_lookback":             8,
        "displacement_mult":         1.15,
        "premium_discount_lookback": 14,
        "wick_ratio":                1.6,
    },
}

# ============================================================
# STRUCTURE SCORE THRESHOLDS — RELAXED FOR SCALP
# ============================================================
MARKET_MIN_STRUCTURE_SCORE = {
    "XAU/USD": 3,
    "NAS100":  4,
    "SPX500":  3,
    "EUR/USD": 3,
    "GBP/JPY": 3,
}

# ============================================================
# SESSION CURATION
# ============================================================
ALLOWED_SESSIONS = [
    "Asian Precision",
    "London",
    "NY+London",
    "NY Killzone",
]

# ============================================================
# ATR MULTIPLIERS
# ============================================================
ATR_MARKET_MULTIPLIER = {
    "XAU/USD": 0.90,
    "NAS100":  0.88,
    "SPX500":  0.85,
    "EUR/USD": 0.80,
    "GBP/JPY": 0.95,
}

# ============================================================
# DOLLAR PER POINT
# ============================================================
DOLLAR_PER_POINT = {
    "XAU/USD": 100,
    "NAS100":  10,
    "SPX500":  10,
    "EUR/USD": 100000,
    "GBP/JPY": 1000,
}

# ============================================================
# MAX SPREAD
# ============================================================
MAX_SPREAD = {
    "XAU/USD": 1.35,
    "NAS100":  5.0,
    "SPX500":  3.5,
    "EUR/USD": 0.00035,
    "GBP/JPY": 0.060,
}

# ============================================================
# REGIME — HARDCODED TO SCALP
# ============================================================
REGIME_TIMEFRAME = {
    "SCALP": "1M / 5M",
}

# ============================================================
# DAILY SIGNAL CAPS — HIGHER FOR SCALPING
# ============================================================
MAX_SIGNALS_PER_DAY = {
    "XAU/USD": 12,
    "NAS100":  10,
    "SPX500":  10,
    "EUR/USD": 12,
    "GBP/JPY": 10,
}

# ============================================================
# CORRELATION GROUPS
# ============================================================
CORRELATED_GROUPS = [
    ["NAS100", "SPX500"],
    ["EUR/USD", "GBP/JPY"],
]

# ============================================================
# DUPLICATE SIGNAL WINDOWS — TIGHTENED FOR SCALP
# ============================================================
DUPLICATE_WINDOWS = {
    "XAU/USD": 600,
    "NAS100":  900,
    "SPX500":  900,
    "EUR/USD": 600,
    "GBP/JPY": 600,
}

# ============================================================
# STATE
# ============================================================
daily_pnl           = 0
consecutive_losses  = 0
last_reset_day      = datetime.now(timezone.utc).day

_signal_sent           = {s: 0 for s in SYMBOLS}
_htf_cache             = {s: {"trend": "NEUTRAL", "ts": 0} for s in SYMBOLS}
_last_signal_direction = {}
_last_signal_time      = {}
_signal_counter        = {s: {"session": None, "count": 0} for s in SYMBOLS}
_daily_signal_count    = {s: 0 for s in SYMBOLS}

for _file in ["signals_log.csv", "signals_backup.csv"]:
    if not os.path.exists(_file):
        with open(_file, "a", encoding="utf-8"):
            pass

# ============================================================
# DAILY RESET
# ============================================================
def reset_daily():
    global daily_pnl, consecutive_losses, last_reset_day
    global _daily_signal_count, _htf_cache

    current_day = datetime.now(timezone.utc).day
    if current_day != last_reset_day:
        daily_pnl           = 0
        consecutive_losses  = 0
        last_reset_day      = current_day
        _daily_signal_count = {s: 0 for s in SYMBOLS}
        _htf_cache          = {
            s: {"trend": "NEUTRAL", "ts": 0} for s in SYMBOLS
        }
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
        with open("heartbeat.txt", "w", encoding="utf-8") as f:
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
    try:
        if os.path.isfile(file_path):
            if os.path.getsize(file_path) > 5_000_000:
                os.rename(file_path, f"signals_log_{int(time.time())}.csv")
    except Exception as e:
        log.error(f"Log rotation failure: {e}")

# ============================================================
# SIGNAL LOGGER
# ============================================================
def log_signal(symbol, direction, score, rr, entry, sl, tp,
               session, regime, timeframe, signal_type):
    with log_lock:
        file_exists = os.path.isfile("signals_log.csv")
        with open(
            "signals_log.csv", "a", newline="", encoding="utf-8"
        ) as f:
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
            with open(
                "signals_backup.csv", "a", newline="", encoding="utf-8"
            ) as backup:
                csv.writer(backup).writerow([
                    SYSTEM_VERSION,
                    datetime.now(timezone.utc).isoformat(),
                    symbol, direction, score, rr,
                    entry, sl, tp, session, regime, timeframe, signal_type
                ])
        except Exception as e:
            log.error(f"Backup log failed: {e}")

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(msg):
    for attempt in range(3):
        try:
            r = session_http.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={
                    "chat_id":    CHAT_ID,
                    "text":       msg,
                    "parse_mode": "Markdown"
                },
                timeout=8
            )
            if r.status_code != 200:
                log.error(f"Telegram HTTP {r.status_code} | {r.text}")
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
    now = datetime.now(timezone.utc)
    wd  = now.weekday()
    hr  = now.hour
    if wd == 5:
        return True
    if wd == 6 and hr < 21:
        return True
    return False

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
# DATA FETCHING — SCALP: 1M PRIMARY, 5M FALLBACK
# ============================================================
def fetch_yf(ticker, period="7d", interval="1m"):
    for attempt in range(3):
        try:
            time.sleep(0.4)

            raw = yf.download(
                ticker,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=True,
                threads=False
            )

            if raw.empty:
                log.error(f"{ticker} returned empty data ({interval})")
                time.sleep(1)
                continue

            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)

            raw.columns = [str(c).lower() for c in raw.columns]

            if "volume" in raw.columns:
                if raw["volume"].sum() == 0:
                    raw["volume"] = 1000
            else:
                raw["volume"] = 1000

            required_cols = ["open", "high", "low", "close", "volume"]
            for col in required_cols:
                if col not in raw.columns:
                    raw[col] = 0

            df = raw[required_cols].copy()
            df = df.drop_duplicates()
            df = df.ffill()
            df = df.bfill()

            return df.reset_index(drop=True)

        except Exception as e:
            log.error(
                f"YFinance fetch failed {ticker} | {interval} | "
                f"Attempt {attempt+1} | {e}"
            )
            time.sleep(1)

    return None


def fetch_market_data(symbol_key):
    yf_sym = MARKETS[symbol_key]["yf"]

    # Primary: 1m data (Yahoo Finance allows max 7d for 1m interval)
    df = fetch_yf(yf_sym, period="7d", interval="1m")
    if df is not None and len(df) > 60:
        df = df.drop_duplicates().reset_index(drop=True)
        log.info(f"{symbol_key} using 1M data | bars: {len(df)}")
        return df, "1M"

    # Fallback: 5m data (Yahoo Finance allows max 60d for 5m interval)
    log.info(f"{symbol_key} falling back to 5M data")
    if symbol_key in ["EUR/USD", "GBP/JPY"]:
        df = fetch_yf(yf_sym, period="59d", interval="5m")
    else:
        df = fetch_yf(yf_sym, period="30d", interval="5m")

    if df is not None and len(df) > 60:
        df = df.drop_duplicates().reset_index(drop=True)
        log.info(f"{symbol_key} using 5M fallback data | bars: {len(df)}")
        return df, "5M"

    return None, None


def get_entry_data(symbol_key):
    df, tf = fetch_market_data(symbol_key)
    if df is not None:
        return df, tf
    return None, None

def get_spread(df):
    if df is None or len(df) < 3:
        return 999
    recent    = df.tail(3)
    avg_range = (
        recent["high"].astype(float) - recent["low"].astype(float)
    ).mean()
    return avg_range * 0.18

# ============================================================
# INDICATORS — SCALP TUNED (SHORT EMAs)
# ============================================================
def add_ind(df):
    df  = df.copy()
    cl  = pd.to_numeric(df["close"],  errors="coerce")
    hi  = pd.to_numeric(df["high"],   errors="coerce")
    lo  = pd.to_numeric(df["low"],    errors="coerce")
    vol = pd.to_numeric(df["volume"], errors="coerce")

    # Scalp EMAs: 5, 13, 21, 50 (fast reaction)
    df["ema9"]     = ta.trend.EMAIndicator(cl, 5).ema_indicator()   # mapped to ema9 slot = EMA5
    df["ema21"]    = ta.trend.EMAIndicator(cl, 13).ema_indicator()  # EMA13
    df["ema50"]    = ta.trend.EMAIndicator(cl, 21).ema_indicator()  # EMA21
    df["ema200"]   = ta.trend.EMAIndicator(cl, 50).ema_indicator()  # EMA50 as HTF reference
    df["rsi"]      = ta.momentum.RSIIndicator(cl, 7).rsi()          # faster RSI for scalp
    df["atr"]      = ta.volatility.AverageTrueRange(hi, lo, cl, 7).average_true_range()  # faster ATR
    df["adx"]      = ta.trend.ADXIndicator(hi, lo, cl, 7).adx()    # faster ADX
    df["volma"]    = vol.rolling(10).mean()                          # shorter vol window
    df["vwap"]     = (cl * vol).cumsum() / vol.cumsum()
    df["stdv"]     = cl.rolling(STDV_PERIOD).std()
    df["aox_fast"] = ta.trend.EMAIndicator(cl, AOX_FAST).ema_indicator()
    df["aox_slow"] = ta.trend.EMAIndicator(cl, AOX_SLOW).ema_indicator()
    df["aox"]      = df["aox_fast"] - df["aox_slow"]

    # WaveTrend oscillator
    hlc3      = (hi + lo + cl) / 3
    esa       = hlc3.ewm(span=6, adjust=False).mean()               # faster for scalp
    d         = (hlc3 - esa).abs().ewm(span=6, adjust=False).mean()
    ci        = (hlc3 - esa) / (0.015 * d)
    df["wt1"] = ci.ewm(span=10, adjust=False).mean()                # faster WT
    df["wt2"] = df["wt1"].rolling(3).mean()

    df.replace([float("inf"), float("-inf")], pd.NA, inplace=True)
    df.ffill(inplace=True)
    df.dropna(inplace=True)

    return df

# ============================================================
# HTF TREND (uses EMA50 as short-term trend reference for scalp)
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
    if df is None or len(df) < 30:
        return "NEUTRAL"
    last = df.iloc[-1]
    # For scalp: EMA13 vs EMA21 as the trend gauge
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
# MTF ALIGNMENT — SCALP VERSION (EMA5 > EMA13 > EMA21 > EMA50)
# ============================================================
def mtf_bullish(symbol_key, df):
    if df is None or len(df) < 60:
        return False
    last = df.iloc[-1]
    return (
        float(last["ema9"])   > float(last["ema21"])
        and float(last["ema21"]) > float(last["ema50"])
        and float(last["close"]) > float(last["ema200"])
    )

def mtf_bearish(symbol_key, df):
    if df is None or len(df) < 60:
        return False
    last = df.iloc[-1]
    return (
        float(last["ema9"])   < float(last["ema21"])
        and float(last["ema21"]) < float(last["ema50"])
        and float(last["close"]) < float(last["ema200"])
    )

# ============================================================
# WAVETREND CONFIRMATION
# ============================================================
def wavetrend_confirmation(df, direction):
    if len(df) < 5:
        return False
    wt1_now  = float(df.iloc[-1]["wt1"])
    wt2_now  = float(df.iloc[-1]["wt2"])
    wt1_prev = float(df.iloc[-2]["wt1"])
    wt2_prev = float(df.iloc[-2]["wt2"])
    if direction == "BUY":
        return wt1_prev < wt2_prev and wt1_now > wt2_now and wt1_now < 30
    elif direction == "SELL":
        return wt1_prev > wt2_prev and wt1_now < wt2_now and wt1_now > -30
    return False

# ============================================================
# SCALP TREND LAYERS (H4 only — no weekly/daily for scalp)
# ============================================================
def h4_trend(df, direction):
    if df is None or len(df) < 55:
        return False
    price = float(df.iloc[-1]["close"])
    ema50 = float(df.iloc[-1]["ema200"])  # ema200 slot = EMA50, acts as H4 ref
    return price > ema50 if direction == "BUY" else price < ema50

def vwap_trend(df, direction):
    if df is None or len(df) < 10:
        return False
    price = float(df.iloc[-1]["close"])
    vwap  = float(df.iloc[-1]["vwap"])
    if pd.isna(vwap):
        return False
    return price > vwap if direction == "BUY" else price < vwap

# ============================================================
# SCALP MACRO FILTER (replaces quantum_macro_filter)
# Only checks H4 + VWAP — fast enough for scalp
# ============================================================
def scalp_macro_filter(df, direction):
    if df is None:
        return False
    score = 0
    if h4_trend(df, direction):   score += 4
    if vwap_trend(df, direction): score += 4
    # EMA stack confirmation
    last = df.iloc[-1]
    if direction == "BUY":
        if float(last["ema9"]) > float(last["ema21"]): score += 2
    else:
        if float(last["ema9"]) < float(last["ema21"]): score += 2
    return score >= 6

# ============================================================
# PATTERN DETECTION
# ============================================================
def fair_value_gap(df):
    if len(df) < 3:
        return False, False
    c1 = df.iloc[-3]
    c3 = df.iloc[-1]
    return (
        float(c1["high"]) < float(c3["low"]),
        float(c1["low"])  > float(c3["high"])
    )

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
    return (
        float(last["low"])  < prev_low  and float(last["close"]) > prev_low,
        float(last["high"]) > prev_high and float(last["close"]) < prev_high
    )

def detect_zone_retest(df, symbol_key, direction):
    lookback = MARKET_STRUCTURE[symbol_key]["zone_lookback"]
    if len(df) < lookback:
        return False
    recent  = df.tail(lookback)
    current = df.iloc[-1]
    if direction == "BUY":
        return float(current["low"]) <= float(recent["low"].min()) * 1.002
    if direction == "SELL":
        return float(current["high"]) >= float(recent["high"].max()) * 0.998
    return False

def detect_displacement(df, symbol_key):
    if len(df) < 2:
        return False
    candle = df.iloc[-1]
    body   = abs(float(candle["close"]) - float(candle["open"]))
    return body > float(candle["atr"]) * MARKET_STRUCTURE[symbol_key]["displacement_mult"]

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
    upper_wick = high_price - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low_price
    wick_ratio = MARKETS[symbol_key]["wick_ratio"]
    return lower_wick > body * wick_ratio, upper_wick > body * wick_ratio

def premium_discount(df, symbol_key):
    lookback = MARKET_STRUCTURE[symbol_key]["premium_discount_lookback"]
    if len(df) < lookback:
        return {"discount": False, "premium": False}
    recent   = df.tail(lookback)
    midpoint = (float(recent["high"].max()) + float(recent["low"].min())) / 2
    price    = float(df.iloc[-1]["close"])
    return {"discount": price < midpoint, "premium": price > midpoint}

def break_of_structure(df, direction):
    if len(df) < 6:
        return False
    atr   = float(df.iloc[-1]["atr"])
    close = float(df.iloc[-1]["close"])
    if direction == "BUY":
        return close > float(df["high"].iloc[-6:-1].max()) + atr * 0.08
    if direction == "SELL":
        return close < float(df["low"].iloc[-6:-1].min()) - atr * 0.08
    return False

def institutional_volume(df):
    if len(df) < 11:
        return False
    last  = df.iloc[-1]
    vol   = float(last["volume"])
    volma = float(last["volma"]) if not pd.isna(last["volma"]) else 0
    return volma > 0 and vol > volma * 1.5

def strong_candle(df, direction):
    if len(df) < 2:
        return False
    candle      = df.iloc[-1]
    open_p      = float(candle["open"])
    close_p     = float(candle["close"])
    high_p      = float(candle["high"])
    low_p       = float(candle["low"])
    body        = abs(close_p - open_p)
    total_range = high_p - low_p
    if total_range == 0:
        return False
    if body / total_range < 0.55:
        return False
    if direction == "BUY":
        return close_p > (low_p + total_range * 0.65)
    if direction == "SELL":
        return close_p < (low_p + total_range * 0.35)
    return False

# ============================================================
# INSTITUTIONAL STRUCTURE SCORE
# ============================================================
def institutional_structure_score(df, symbol_key):
    bull_sweep,  bear_sweep  = detect_liquidity_sweep(df, symbol_key)
    bull_wick,   bear_wick   = detect_wick_rejection(
        df, float(df.iloc[-1]["atr"]), symbol_key
    )
    displacement = detect_displacement(df, symbol_key)
    pd_zone      = premium_discount(df, symbol_key)

    buy_score  = 0
    sell_score = 0
    buy_cond   = {}
    sell_cond  = {}

    if bull_sweep:
        buy_score += 2; buy_cond["SWEEP"] = True
    if bull_wick:
        buy_score += 2; buy_cond["WICK"] = True
    if detect_zone_retest(df, symbol_key, "BUY"):
        buy_score += 2; buy_cond["ZONE"] = True
    if displacement:
        buy_score += 2; buy_cond["DISPLACEMENT"] = True
    if pd_zone["discount"]:
        buy_score += 1; buy_cond["DISCOUNT"] = True

    if bear_sweep:
        sell_score += 2; sell_cond["SWEEP"] = True
    if bear_wick:
        sell_score += 2; sell_cond["WICK"] = True
    if detect_zone_retest(df, symbol_key, "SELL"):
        sell_score += 2; sell_cond["ZONE"] = True
    if displacement:
        sell_score += 2; sell_cond["DISPLACEMENT"] = True
    if pd_zone["premium"]:
        sell_score += 1; sell_cond["PREMIUM"] = True

    if buy_score  >= 8: buy_score  += 1
    if sell_score >= 8: sell_score += 1

    return buy_cond, sell_cond, buy_score, sell_score

def detect_supply_demand_zones(df):
    if len(df) < 10:
        return None, None
    recent = df.tail(10)
    return (
        recent["low"].rolling(3).min().iloc[-1],
        recent["high"].rolling(3).max().iloc[-1],
    )

def detect_market_regime(df):
    # Always SCALP regime
    return "SCALP"

def get_signal_number(symbol_key, session):
    global _signal_counter
    if _signal_counter[symbol_key]["session"] != session:
        _signal_counter[symbol_key]["session"] = session
        _signal_counter[symbol_key]["count"]   = 1
    else:
        _signal_counter[symbol_key]["count"] += 1
    n = _signal_counter[symbol_key]["count"]
    entry_type = (
        "SCALP ENTRY"          if n == 1 else
        "SCALP REENTRY"        if n == 2 else
        "SCALP CONTINUATION"
    )
    return n, entry_type

# ============================================================
# SESSION FILTER
# ============================================================
def in_session(symbol_key):
    h = datetime.now(timezone.utc).hour
    s, e = MARKETS[symbol_key]["sessions"]
    if not (s <= h < e):
        return False, "Closed"
    if 1  <= h < 6:  return True, "Asian Precision"
    if 8  <= h < 11: return True, "London"
    if 13 <= h < 15: return True, "NY Killzone"
    if 14 <= h < 16: return True, "NY+London"
    return False, "Closed"

# ============================================================
# SPREAD / VOLATILITY CHECKS
# ============================================================
def spread_too_high(symbol_key, spread):
    return spread > MAX_SPREAD[symbol_key] * 0.90

def volatility_danger(df, symbol_key):
    if len(df) < 30:
        return False
    atr     = float(df.iloc[-1]["atr"])
    atr_avg = df["atr"].rolling(20).mean().iloc[-1]
    if pd.isna(atr_avg) or atr_avg == 0:
        return False
    return (atr / atr_avg) > 2.5

def quantum_volatility_ok(df):
    if len(df) < 30:
        return False
    atr     = float(df.iloc[-1]["atr"])
    atr_avg = df["atr"].rolling(20).mean().iloc[-1]
    if pd.isna(atr_avg) or atr_avg == 0:
        return False
    ratio = atr / atr_avg
    return 0.60 <= ratio <= 2.50

# ============================================================
# FALSE BREAKOUT FILTER — SCALP RELAXED
# ============================================================
def false_breakout_filter(df, direction):
    if len(df) < 3:
        return False

    last = df.iloc[-1]
    prev = df.iloc[-2]
    atr  = float(df.iloc[-1]["atr"])

    if direction == "BUY":
        return float(last["close"]) > float(prev["high"]) - atr * 0.08

    elif direction == "SELL":
        return float(last["close"]) < float(prev["low"]) + atr * 0.08

    return False

# ============================================================
# CORRELATION BLOCKER
# ============================================================
def correlated_signal_block(symbol_key):
    if not CORRELATION_BLOCK:
        return False
    for group in CORRELATED_GROUPS:
        if symbol_key in group:
            active = sum(
                1 for s in group
                if time.time() - _signal_sent.get(s, 0) < 3600
            )
            if active >= MAX_OPEN_CORRELATED:
                log.info(f"Correlation blocker active for {symbol_key}")
                return True
    return False

# ============================================================
# DUPLICATE SIGNAL FILTER
# ============================================================
def duplicate_signal(symbol_key, direction):
    now      = time.time()
    cooldown = DUPLICATE_WINDOWS.get(symbol_key, 600)
    with signal_lock:
        last_dir  = _last_signal_direction.get(symbol_key)
        last_time = _last_signal_time.get(symbol_key, 0)
        if last_dir == direction and now - last_time < cooldown:
            remaining = int(cooldown - (now - last_time))
            log.info(
                f"Duplicate blocked {symbol_key} ({remaining}s remaining)"
            )
            return True
        _last_signal_direction[symbol_key] = direction
        _last_signal_time[symbol_key]      = now
    return False

def economic_news_block():
    return False

# ============================================================
# BUILD BASE SCORE — SCALP TUNED RSI BANDS
# ============================================================
def build_score(df, trend, symbol_key):
    last   = df.iloc[-1]
    rsi    = float(last["rsi"])
    ema9   = float(last["ema9"])
    ema21  = float(last["ema21"])
    ema50  = float(last["ema50"])
    ema200 = float(last["ema200"])
    adx    = float(last["adx"])
    vol    = float(last["volume"])
    volma  = float(last["volma"]) if not pd.isna(last["volma"]) else 0
    atr    = float(last["atr"])
    stdv   = float(last["stdv"])   if not pd.isna(last["stdv"])   else 0
    aox    = float(last["aox"])    if not pd.isna(last["aox"])    else 0

    stdv_ma = (
        df["stdv"].rolling(STDV_PERIOD).mean().iloc[-1]
        if len(df) > STDV_PERIOD else 0
    )

    bull_fvg,   bear_fvg   = fair_value_gap(df)
    bull_choch, bear_choch = detect_choch(df)
    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    bull_wick,  bear_wick  = detect_wick_rejection(df, atr, symbol_key)

    # Scalp: smaller breakout threshold (0.08 vs 0.12)
    bullish_break = float(last["close"]) > float(df.iloc[-2]["high"]) + atr * 0.08
    bearish_break = float(last["close"]) < float(df.iloc[-2]["low"])  - atr * 0.08

    buy = {
        "HTF":   trend == "BULL",
        "EMA":   ema9 > ema21 > ema50,
        "VWAP":  float(last["close"]) > float(last["vwap"]),
        "RSI":   52 <= rsi <= 75,         # wider band for scalp
        "ADX":   adx > ADX_THRESHOLD,
        "VOL":   volma > 0 and vol > volma * VOL_MULT,
        "FVG":   bull_fvg,
        "CHOCH": bull_choch,
        "BOS":   bullish_break,
        "SWEEP": bull_sweep,
        "WICK":  bull_wick,
        "STDV":  stdv_ma > 0 and stdv > stdv_ma * STDV_THRESHOLD_MULT,
        "AOX":   aox > 0,
    }

    sell = {
        "HTF":   trend == "BEAR",
        "EMA":   ema9 < ema21 < ema50,
        "VWAP":  float(last["close"]) < float(last["vwap"]),
        "RSI":   25 <= rsi <= 48,
        "ADX":   adx > ADX_THRESHOLD,
        "VOL":   volma > 0 and vol > volma * VOL_MULT,
        "FVG":   bear_fvg,
        "CHOCH": bear_choch,
        "BOS":   bearish_break,
        "SWEEP": bear_sweep,
        "WICK":  bear_wick,
        "STDV":  stdv_ma > 0 and stdv > stdv_ma * STDV_THRESHOLD_MULT,
        "AOX":   aox < 0,
    }

    buy_score  = sum(buy.values())
    sell_score = sum(sell.values())

    if buy["STDV"]  and buy["AOX"]:  buy_score  += 1
    if sell["STDV"] and sell["AOX"]: sell_score += 1

    sweep_bonus = MARKETS[symbol_key]["sweep_bonus"]
    if bull_sweep and bull_wick: buy_score  += sweep_bonus
    if bear_sweep and bear_wick: sell_score += sweep_bonus

    if symbol_key == "XAU/USD":
        if bull_sweep: buy_score  += 1
        if bear_sweep: sell_score += 1
        if bull_wick:  buy_score  += 1
        if bear_wick:  sell_score += 1

    if adx >= 30:
        if   buy_score > sell_score: buy_score  += 1
        elif sell_score > buy_score: sell_score += 1

    return buy, sell, buy_score, sell_score

# ============================================================
# WIZARD AI — SCALP TUNED
# ============================================================
def wizard_ai_confirmation(df, symbol_key, direction):
    if len(df) < 60:
        return False, 0

    last   = df.iloc[-1]
    close  = float(last["close"])
    ema50  = float(last["ema50"])
    ema200 = float(last["ema200"])
    rsi    = float(last["rsi"])
    adx    = float(last["adx"])
    volume = float(last["volume"])
    volma  = float(last["volma"]) if not pd.isna(last["volma"]) else 0
    aox    = float(last["aox"])   if not pd.isna(last["aox"])   else 0
    vwap   = float(last["vwap"])  if not pd.isna(last["vwap"])  else 0

    score = 0

    if direction == "BUY":
        if close > ema50:                 score += 3
        if ema50  > ema200:               score += 2
        if rsi    > 52:                   score += 2
        if adx    > WIZARD_ADX_THRESHOLD: score += 2
        if aox    > 0:                    score += 2
        if vwap   > 0 and close > vwap:   score += 2
    elif direction == "SELL":
        if close < ema50:                 score += 3
        if ema50  < ema200:               score += 2
        if rsi    < 48:                   score += 2
        if adx    > WIZARD_ADX_THRESHOLD: score += 2
        if aox    < 0:                    score += 2
        if vwap   > 0 and close < vwap:   score += 2

    if volma > 0 and volume > volma * WIZARD_VOLUME_MULT:
        score += 2

    bull_fvg, bear_fvg     = fair_value_gap(df)
    bull_choch, bear_choch = detect_choch(df)
    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    bull_wick, bear_wick   = detect_wick_rejection(
        df, float(last["atr"]), symbol_key
    )

    if direction == "BUY":
        if bull_fvg:   score += 2
        if bull_choch: score += 2
        if bull_sweep: score += 2
        if bull_wick:  score += 2
    elif direction == "SELL":
        if bear_fvg:   score += 2
        if bear_choch: score += 2
        if bear_sweep: score += 2
        if bear_wick:  score += 2

    pd_zone = premium_discount(df, symbol_key)
    if direction == "BUY"  and pd_zone["discount"]: score += 1
    if direction == "SELL" and pd_zone["premium"]:  score += 1

    return score >= WIZARD_MIN_SCORE, score

# ============================================================
# ULTRA SNIPER SCORE — SCALP VERSION
# ============================================================
def ultra_sniper_score(df, symbol_key, direction):
    score = 0
    last  = df.iloc[-1]

    rsi   = float(last["rsi"])
    adx   = float(last["adx"])
    vol   = float(last["volume"])
    volma = float(last["volma"]) if not pd.isna(last["volma"]) else 0

    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    bull_fvg,   bear_fvg   = fair_value_gap(df)

    if direction == "BUY"  and mtf_bullish(symbol_key, df): score += 4
    if direction == "SELL" and mtf_bearish(symbol_key, df): score += 4

    if wavetrend_confirmation(df, direction): score += 3

    if direction == "BUY"  and bull_sweep: score += 2
    if direction == "SELL" and bear_sweep: score += 2

    if direction == "BUY"  and bull_fvg: score += 2
    if direction == "SELL" and bear_fvg: score += 2

    if break_of_structure(df, direction): score += 2
    if institutional_volume(df):          score += 2
    if strong_candle(df, direction):      score += 2

    if direction == "BUY"  and rsi > 55: score += 2
    if direction == "SELL" and rsi < 45: score += 2
    if adx > 25: score += 2

    if volma > 0 and vol > volma * 1.5: score += 3

    return score

# ============================================================
# HELPERS
# ============================================================
def determine_best_direction(buy_score, sell_score):
    return "SELL" if buy_score >= sell_score else "BUY"

def trade_quality(score):
    if   score >= 28: return "GOD-TIER SCALP"
    elif score >= 22: return "ELITE SCALP"
    elif score >= 17: return "HIGH-PROB SCALP"
    return "STANDARD SCALP"

def adaptive_risk(session):
    if   session == "Asian Precision": return 0.6
    elif session == "London":          return 1.0
    elif session == "NY Killzone":     return 1.2
    return 0.9

def get_dynamic_rr(symbol_key, regime):
    return RR_PROFILE.get(symbol_key, {}).get(
        "SCALP", MARKETS[symbol_key]["rr"]
    )

# ============================================================
# LEVELS — TIGHTER FOR SCALP
# ============================================================
def calc_levels(price, atr, symbol_key, df, direction, regime):
    min_sl   = MARKETS[symbol_key]["min_sl"]
    decimals = MARKETS[symbol_key]["decimals"]
    recent   = df.tail(5)       # shorter swing lookback for scalp

    swing_dist = (
        price - float(recent["low"].min())
        if direction == "BUY"
        else float(recent["high"].max()) - price
    )

    atr_sl  = atr * ATR_MULT * ATR_MARKET_MULTIPLIER[symbol_key]
    sl_dist = max(
        min_sl,
        min(max(atr_sl, swing_dist * 0.80), swing_dist * 1.05)
    )

    rr = get_dynamic_rr(symbol_key, regime)

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
        rr
    )

# ============================================================
# LOT SIZE
# ============================================================
def lot_for_risk(price, sl, symbol_key, risk_multiplier=1.0):
    base_risk = 50
    risk      = base_risk * risk_multiplier
    sl_dist   = abs(price - sl)
    if sl_dist <= 0:
        return 0.01
    lot = risk / (sl_dist * DOLLAR_PER_POINT[symbol_key])
    caps = {
        "XAU/USD": 1.50,
        "NAS100":  2.00,
        "SPX500":  2.00,
        "EUR/USD": 3.00,
        "GBP/JPY": 2.00,
    }
    return round(max(0.01, min(lot, caps[symbol_key])), 3)

# ============================================================
# MASTER SIGNAL ENGINE — SCALP VERSION
# ============================================================
def master_signal(symbol_key, df, session, trend, regime,
                  buy, sell, buy_score, sell_score,
                  structure_buy_score, structure_sell_score):

    direction = determine_best_direction(buy_score, sell_score)
    best      = max(buy_score, sell_score)

    # Scalp macro filter (H4 + VWAP, no weekly/daily)
    if not scalp_macro_filter(df, direction):
        log.info(f"REJECTED {symbol_key} scalp macro filter")
        return None, None, None

    if ENABLE_WIZARD_AI:
        wizard_pass, wizard_score = wizard_ai_confirmation(
            df, symbol_key, direction
        )
        if not wizard_pass:
            log.info(
                f"REJECTED {symbol_key} Wizard AI failed | "
                f"Score: {wizard_score}"
            )
            return None, None, None
        best += int(wizard_score * 0.30)
    else:
        wizard_score = 0

    sniper = ultra_sniper_score(df, symbol_key, direction)
    best  += sniper

    required = SESSION_THRESHOLDS.get(session, 12)
    if best < required:
        log.info(
            f"REJECTED {symbol_key} session score too low "
            f"({best} < {required})"
        )
        return None, None, None

    if VOLATILITY_KILL:
        if not quantum_volatility_ok(df):
            log.info(f"REJECTED {symbol_key} volatility filter")
            return None, None, None

    if FALSE_BREAK_FILTER:
        if not false_breakout_filter(df, direction):
            log.info(f"REJECTED {symbol_key} false breakout filter")
            return None, None, None

    return direction, best, wizard_score

# ============================================================
# EXECUTE TRADE
# ============================================================
def execute_trade(symbol_key, df, direction, best, wizard_score,
                  sniper_score, macro_trend, session, trend,
                  regime, buy, sell, source, asia_mode):

    price = float(df.iloc[-1]["close"])
    atr   = float(df.iloc[-1]["atr"])
    rsi   = float(df.iloc[-1]["rsi"])
    adx   = float(df.iloc[-1]["adx"])
    dec   = MARKETS[symbol_key]["decimals"]

    demand_zone, supply_zone = detect_supply_demand_zones(df)

    if direction == "BUY":
        price += EXECUTION_BUFFER[symbol_key]
    else:
        price -= EXECUTION_BUFFER[symbol_key]

    sl, tp, sl_dist, rr = calc_levels(
        price, atr, symbol_key, df, direction, regime
    )

    risk_mult = adaptive_risk(session)
    lot       = lot_for_risk(price, sl, symbol_key, risk_mult)

    quality        = trade_quality(best)
    timeframe      = "1M / 5M"
    signal_num, entry_type = get_signal_number(symbol_key, session)

    log_signal(
        symbol_key, direction, best, rr, price, sl, tp,
        session, regime, timeframe, "SCALP"
    )
    sync_real_pnl()

    checks    = buy if direction == "BUY" else sell
    cond_text = "\n".join([f" {k}" for k, v in checks.items() if v])
    if demand_zone:
        cond_text += "\n DEMAND_ZONE"
    if supply_zone:
        cond_text += "\n SUPPLY_ZONE"

    action_emoji = "📈" if direction == "BUY" else "📉"
    priority_tag = (
        "🔱 *PRIORITY MARKET*\n"
        if symbol_key in PRIORITY_MARKETS else ""
    )

    msg = (
        f"⚡ *{SYSTEM_VERSION}* | SCALP EXECUTION\n"
        f"*{MARKETS[symbol_key]['mt5']}* | "
        f"⭐⭐⭐⭐⭐ {MARKETS[symbol_key]['tier']}\n"
        f"{priority_tag}\n"
        f"🔥 *Action:* {direction} {action_emoji}\n"
        f"🎯 *Signal #:* {signal_num}\n"
        f"📍 *Entry Type:* {entry_type}\n"
        f"🚀 *Signal Type:* SCALP\n"
        f"⏱ *Timeframe:* {timeframe}\n"
        f"⭐ *Total Score:* {best}\n"
        f"🏆 *Trade Quality:* {quality}\n"
        f"🌍 *Macro Trend:* {macro_trend}\n"
        f"⚛ *Scalp Macro Filter:* PASS\n"
        f"🎯 *Sniper Score:* {sniper_score}\n"
        f"🧠 *Wizard AI Score:* "
        f"{wizard_score if ENABLE_WIZARD_AI else 'OFF'}\n"
        f"🧠 *Regime:* {regime}\n"
        f"📊 *Market Bias:* {MARKETS[symbol_key]['bias']}\n\n"
        f"📍 *Entry:* {price:,.{dec}f}\n"
        f"🛑 *SL:* {sl:,.{dec}f}\n"
        f"🎯 *TP:* {tp:,.{dec}f} *(1:{rr} RR)*\n\n"
        f"📈 *RSI:* {rsi:.1f}\n"
        f"📉 *ADX:* {adx:.1f}\n"
        f"🌍 *Trend:* {trend}\n"
        f"⏰ *Session:* {session}\n"
        f"📡 *Data Source:* {source}\n"
        f"🧠 *Mode:* "
        f"{'ASIA SCALP PRECISION' if asia_mode else 'CORE SCALP MODE'}\n\n"
        f"💵 *Lot:* {lot}\n\n"
        f"✅ *Conditions:*\n"
        f"{cond_text}\n\n"
        f"🛡 *ELITE SCALP FILTER ACTIVE*\n"
        f"⚡ *ULTIMATE HYBRID SUPREME — 2026 SCALPER EDITION*"
    )

    send_telegram(msg)

    log.info(
        f"SCALP SIGNAL {symbol_key} {direction} | "
        f"Entry: {price} | SL: {sl} | TP: {tp} | RR: {rr} | "
        f"Quality: {quality} | Sniper: {sniper_score} | "
        f"Signal#: {signal_num} | TF: {source}"
    )

# ============================================================
# PROCESS SYMBOL
# ============================================================
def process_symbol(symbol_key):
    log.info(f"Scanning {symbol_key}")

    if _daily_signal_count[symbol_key] >= MAX_SIGNALS_PER_DAY[symbol_key]:
        log.info(f"REJECTED {symbol_key} daily cap reached")
        return

    if weekend_block(symbol_key):  return
    if daily_loss_lock():          return
    if loss_streak_lock():         return

    watchdog()
    rotate_log()

    ok, session = in_session(symbol_key)
    if not ok:
        return

    if session not in ALLOWED_SESSIONS:
        log.info(f"REJECTED {symbol_key} outside session ({session})")
        return

    if economic_news_block():
        return

    df, source = get_entry_data(symbol_key)
    if df is None or len(df) < 60:
        return

    spread = get_spread(df)
    if spread_too_high(symbol_key, spread):
        log.info(f"REJECTED {symbol_key} spread {spread:.6f}")
        return

    df = add_ind(df)

    if df is None or len(df) < 50:
        log.info(f"REJECTED {symbol_key} insufficient data after indicators")
        return

    if volatility_danger(df, symbol_key):
        log.info(f"REJECTED {symbol_key} extreme volatility danger")
        return

    price = float(df.iloc[-1]["close"])
    atr   = float(df.iloc[-1]["atr"])

    if price <= 0:
        return

    if not (MARKETS[symbol_key]["price_lo"] <= price
            <= MARKETS[symbol_key]["price_hi"]):
        log.info(f"REJECTED {symbol_key} price out of range")
        return

    trend  = get_trend(symbol_key)
    regime = detect_market_regime(df)   # always returns "SCALP"

    # Scalp macro trend: H4 only
    macro_trend = (
        "BULL"    if h4_trend(df, "BUY")
        else "BEAR" if h4_trend(df, "SELL")
        else "NEUTRAL"
    )

    asia_mode = session == "Asian Precision"

    buy, sell, buy_score, sell_score = build_score(df, trend, symbol_key)

    struct_buy, struct_sell, struct_buy_score, struct_sell_score = (
        institutional_structure_score(df, symbol_key)
    )

    buy.update(struct_buy)
    sell.update(struct_sell)
    buy_score  += struct_buy_score
    sell_score += struct_sell_score

    # Asia bonus
    if asia_mode:
        buy_score  += 1 if buy_score  >= 7 else 0
        sell_score += 1 if sell_score >= 7 else 0

    if asia_mode:
        asia_spread_cap = MAX_SPREAD[symbol_key] * 1.05
        if spread > asia_spread_cap:
            log.info(f"REJECTED {symbol_key} Asia spread too high")
            return
        if max(buy_score, sell_score) < 6:
            log.info(f"REJECTED {symbol_key} weak Asia scalp score")
            return

    log.info(
        f"{symbol_key} | BUY: {buy_score} | SELL: {sell_score} | "
        f"Regime: {regime} | Trend: {trend} | Session: {session} | "
        f"Source: {source}"
    )

    best_structure = max(struct_buy_score, struct_sell_score)
    if best_structure < MARKET_MIN_STRUCTURE_SCORE[symbol_key]:
        log.info(f"REJECTED {symbol_key} weak structure score")
        return

    direction = determine_best_direction(buy_score, sell_score)

    if symbol_key != "XAU/USD":
        if trend == "BULL" and direction == "SELL":
            log.info(f"REJECTED {symbol_key} countertrend SELL")
            return
        if trend == "BEAR" and direction == "BUY":
            log.info(f"REJECTED {symbol_key} countertrend BUY")
            return

    demand_zone, supply_zone = detect_supply_demand_zones(df)
    planned_entry   = float(df.iloc[-2]["close"])
    max_entry_drift = atr * 0.50      # wider drift tolerance for scalp

    if direction == "SELL" and supply_zone:
        if price < supply_zone * 0.998:
            log.info(f"REJECTED {symbol_key} weak supply rejection")
            return
    if direction == "BUY" and demand_zone:
        if price > demand_zone * 1.002:
            log.info(f"REJECTED {symbol_key} weak demand rejection")
            return
    if direction == "SELL" and price < planned_entry - max_entry_drift:
        log.info(f"REJECTED {symbol_key} late SELL drift")
        return
    if direction == "BUY" and price > planned_entry + max_entry_drift:
        log.info(f"REJECTED {symbol_key} late BUY drift")
        return

    if correlated_signal_block(symbol_key):
        return

    direction, best, wizard_score = master_signal(
        symbol_key, df, session, trend, regime,
        buy, sell, buy_score, sell_score,
        struct_buy_score, struct_sell_score
    )

    if direction is None:
        return

    sniper_score = ultra_sniper_score(df, symbol_key, direction)

    if duplicate_signal(symbol_key, direction):
        return

    now = time.time()
    if now - _signal_sent[symbol_key] < SIGNAL_COOLDOWN:
        remaining = int(SIGNAL_COOLDOWN - (now - _signal_sent[symbol_key]))
        log.info(f"REJECTED {symbol_key} cooldown {remaining}s")
        return

    with signal_lock:
        _signal_sent[symbol_key]        = now
        _daily_signal_count[symbol_key] += 1

    execute_trade(
        symbol_key, df, direction, best, wizard_score,
        sniper_score, macro_trend, session, trend,
        regime, buy, sell, source, asia_mode
    )

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    log.info(f"{SYSTEM_VERSION} STARTED")
    send_telegram(
        f"⚡ *{SYSTEM_VERSION} LIVE*\n\n"
        f"📊 *Markets Active:*\n"
        f"🥇 XAU/USD\n"
        f"📈 NAS100\n"
        f"📊 SPX500\n"
        f"💶 EUR/USD\n"
        f"💷 GBP/JPY\n\n"
        f"🔱 All Markets Priority\n\n"
        f"⏱ *MODE: SCALP — 1M / 5M ONLY*\n\n"
        f"✅ Scalp Macro Filter (H4 + VWAP)\n"
        f"🎯 Ultra Sniper Score\n"
        f"⚛ WaveTrend Confirmation\n"
        f"📊 EMA5/13/21/50 Stack\n"
        f"📊 Dynamic Scalp RR (1.5–1.8)\n"
        f"💰 Adaptive Risk Engine\n"
        f"🔒 Correlation Blocker\n"
        f"🚫 False Breakout Filter\n"
        f"🏆 Trade Quality Ranking\n"
        f"🧠 Wizard AI Active\n"
        f"🛡 Asia Scalp Precision\n"
        f"🧵 Thread Safe\n"
        f"⚡ ULTIMATE HYBRID SUPREME 2026 — SCALPER EDITION"
    )

    while True:
        try:
            reset_daily()

            with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
                futures = []
                for symbol in PRIORITY_MARKETS:
                    futures.append(
                        executor.submit(process_symbol, symbol)
                    )
                    time.sleep(0.25)   # slightly faster scheduling

                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        log.error(f"Thread error: {e}")

            gc.collect()
            time.sleep(MAIN_LOOP_DELAY)

        except Exception as e:
            log.error(f"Main loop error: {e}")
            time.sleep(MAIN_LOOP_DELAY)

if __name__ == "__main__":
    main()
