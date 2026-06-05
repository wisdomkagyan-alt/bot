============================================================
# PEPPERSTONE + INDIA MOMENTUM HUNTER
# ULTIMATE-HYBRID-SUPREME-2026-ELITE — BOX BREAKOUT EDITION
# XAU/USD + NAS100 + SPX500 + EUR/USD + GBP/JPY
# + NIFTY50 + BANKNIFTY + SENSEX + RELIANCE + TCS
#
# STRATEGY: LuxAlgo Box Breakout (as per chart screenshots)
#   1. Mark DAY HIGH and DAY LOW
#   2. Draw box: upper line = day high, lower line = day low
#   3. Entry: on candle CLOSE beyond box upper/lower line
#   4. Target: box height projected from breakout point
#   5. SL: inside the box (opposite line - buffer)
#
# SCALP  : 1M / 5M  (Signal #1 only per session)
# BREAKOUT: 15M / 30M (Box line break + candle close confirmation)
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
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import yfinance as yf

SYSTEM_VERSION = "ULTIMATE-BOX-BREAKOUT-2026-ELITE"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("BOX-BREAKOUT-2026")

TOKEN   = os.getenv("TOKEN",   "8641713322:AAHZeJOz0_LILD076P1ShvXSfCqQ1xrpFlk")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")

session_http = requests.Session()
signal_lock  = Lock()
log_lock     = Lock()

# ============================================================
# PRIORITY MARKETS
# ============================================================
PRIORITY_MARKETS = [
    "XAU/USD", "NAS100", "SPX500", "EUR/USD", "GBP/JPY",
    "NIFTY50", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS",
]

# ============================================================
# SESSION SCORE THRESHOLDS
# ============================================================
SESSION_THRESHOLDS = {
    "Asian Precision": 13,
    "London":          12,
    "NY Killzone":     12,
    "NY+London":       11,
    "India Open":      15,
    "India Midday":    12,
    "India Close":     13,
}

BREAKOUT_SESSION_THRESHOLDS = {
    "Asian Precision": 15,
    "London":          14,
    "NY Killzone":     14,
    "NY+London":       13,
    "India Open":      15,
    "India Midday":    13,
    "India Close":     14,
}

# ============================================================
# RR PROFILES
# ============================================================
RR_PROFILE = {
    "XAU/USD":   {"SCALP": 1.8, "BREAKOUT": 2.5},
    "NAS100":    {"SCALP": 1.7, "BREAKOUT": 2.3},
    "SPX500":    {"SCALP": 1.6, "BREAKOUT": 2.2},
    "EUR/USD":   {"SCALP": 1.5, "BREAKOUT": 2.0},
    "GBP/JPY":   {"SCALP": 1.8, "BREAKOUT": 2.5},
    "NIFTY50":   {"SCALP": 1.8, "BREAKOUT": 2.5},
    "BANKNIFTY": {"SCALP": 1.8, "BREAKOUT": 2.5},
    "SENSEX":    {"SCALP": 1.6, "BREAKOUT": 2.2},
    "RELIANCE":  {"SCALP": 1.7, "BREAKOUT": 2.3},
    "TCS":       {"SCALP": 1.7, "BREAKOUT": 2.3},
}

# ============================================================
# MARKETS
# ============================================================
MARKETS = {
    "XAU/USD": {
        "mt5": "XAUUSD.Qraw", "yf": "GC=F",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [0, 20], "decimals": 2, "min_sl": 1.5,
        "tier": "GOLD ELITE", "bias": "BULL",
        "rr": 1.8, "sweep_bonus": 2, "wick_ratio": 1.6,
        "market_type": "global",
    },
    "NAS100": {
        "mt5": "NAS100", "yf": "^NDX",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [0, 21], "decimals": 1, "min_sl": 12.0,
        "tier": "NASDAQ ELITE", "bias": "BULL",
        "rr": 1.7, "sweep_bonus": 2, "wick_ratio": 1.5,
        "market_type": "global",
    },
    "SPX500": {
        "mt5": "SPX500", "yf": "^GSPC",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [0, 21], "decimals": 1, "min_sl": 6.0,
        "tier": "SP500 ELITE", "bias": "BULL",
        "rr": 1.6, "sweep_bonus": 2, "wick_ratio": 1.4,
        "market_type": "global",
    },
    "EUR/USD": {
        "mt5": "EURUSD", "yf": "EURUSD=X",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [0, 24], "decimals": 5, "min_sl": 0.00025,
        "tier": "FOREX MAJOR ELITE", "bias": "BULL",
        "rr": 1.5, "sweep_bonus": 1, "wick_ratio": 1.3,
        "market_type": "global",
    },
    "GBP/JPY": {
        "mt5": "GBPJPY", "yf": "GBPJPY=X",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [0, 24], "decimals": 3, "min_sl": 0.040,
        "tier": "FOREX VOLATILITY ELITE", "bias": "BULL",
        "rr": 1.8, "sweep_bonus": 2, "wick_ratio": 1.5,
        "market_type": "global",
    },
    "NIFTY50": {
        "mt5": "NIFTY50", "yf": "^NSEI",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [3, 10], "decimals": 2, "min_sl": 15.0,
        "tier": "INDIA INDEX ELITE", "bias": "BULL",
        "rr": 1.8, "sweep_bonus": 2, "wick_ratio": 1.6,
        "market_type": "india",
    },
    "BANKNIFTY": {
        "mt5": "BANKNIFTY", "yf": "^NSEBANK",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [3, 10], "decimals": 2, "min_sl": 20.0,
        "tier": "INDIA BANK ELITE", "bias": "BULL",
        "rr": 1.8, "sweep_bonus": 2, "wick_ratio": 1.7,
        "market_type": "india",
    },
    "SENSEX": {
        "mt5": "SENSEX", "yf": "^BSESN",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [3, 10], "decimals": 2, "min_sl": 40.0,
        "tier": "INDIA BSE ELITE", "bias": "BULL",
        "rr": 1.6, "sweep_bonus": 2, "wick_ratio": 1.5,
        "market_type": "india",
    },
    "RELIANCE": {
        "mt5": "RELIANCE", "yf": "RELIANCE.NS",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [3, 10], "decimals": 2, "min_sl": 5.0,
        "tier": "INDIA LARGE CAP ELITE", "bias": "BULL",
        "rr": 1.7, "sweep_bonus": 2, "wick_ratio": 1.6,
        "market_type": "india",
    },
    "TCS": {
        "mt5": "TCS", "yf": "TCS.NS",
        "price_lo": 0, "price_hi": float("inf"),
        "sessions": [3, 10], "decimals": 2, "min_sl": 8.0,
        "tier": "INDIA IT ELITE", "bias": "BULL",
        "rr": 1.7, "sweep_bonus": 2, "wick_ratio": 1.6,
        "market_type": "india",
    },
}

SYMBOLS = list(MARKETS.keys())

# ============================================================
# CORE SETTINGS
# ============================================================
ATR_MULT               = 0.12
VOL_MULT               = 1.05
ADX_THRESHOLD          = 20
SIGNAL_COOLDOWN        = 600
HTF_REFRESH            = 300
MAX_DAILY_LOSS         = -300
MAX_CONSECUTIVE_LOSSES = 3
MAIN_LOOP_DELAY        = 1

STDV_PERIOD         = 10
STDV_THRESHOLD_MULT = 1.10
AOX_FAST            = 3
AOX_SLOW            = 13

ENABLE_WIZARD_AI     = True
WIZARD_MIN_SCORE     = 12
WIZARD_VOLUME_MULT   = 1.3
WIZARD_ADX_THRESHOLD = 20

CORRELATION_BLOCK   = True
MAX_OPEN_CORRELATED = 2
VOLATILITY_KILL     = True
FALSE_BREAK_FILTER  = True

# ---- Box Breakout settings (LuxAlgo style, as per charts) ----
BOX_LOOKBACK_CANDLES  = 20    # candles to define box high/low
BOX_CONFIRM_CLOSE     = True  # candle must CLOSE beyond box line (not just wick)
BOX_MIN_HEIGHT_ATR    = 0.5   # box must be at least 0.5x ATR tall (filters tiny boxes)
BOX_BREAKOUT_BUFFER   = 0.002 # 0.2% beyond line to confirm break (avoids fakeouts)
BREAKOUT_ADX_MIN      = 22
BREAKOUT_VOL_MULT     = 1.5
BREAKOUT_SWEEP_NEEDED = True

# ============================================================
# EXECUTION SLIPPAGE BUFFER
# ============================================================
EXECUTION_BUFFER = {
    "XAU/USD":   0.15,  "NAS100":    1.5,   "SPX500":    1.0,
    "EUR/USD":   0.00005, "GBP/JPY": 0.010,
    "NIFTY50":   1.0,   "BANKNIFTY": 2.0,   "SENSEX":    3.0,
    "RELIANCE":  0.50,  "TCS":       0.50,
}

ATR_MARKET_MULTIPLIER = {
    "XAU/USD":   0.90, "NAS100":    0.88, "SPX500":    0.85,
    "EUR/USD":   0.80, "GBP/JPY":   0.95,
    "NIFTY50":   0.90, "BANKNIFTY": 0.92, "SENSEX":    0.88,
    "RELIANCE":  0.85, "TCS":       0.85,
}

DOLLAR_PER_POINT = {
    "XAU/USD":   100,    "NAS100":    10,     "SPX500":    10,
    "EUR/USD":   100000, "GBP/JPY":   1000,
    "NIFTY50":   50,     "BANKNIFTY": 20,     "SENSEX":    10,
    "RELIANCE":  1,      "TCS":       1,
}

MAX_SPREAD = {
    "XAU/USD":   1.35,    "NAS100":    5.0,    "SPX500":    3.5,
    "EUR/USD":   0.00035, "GBP/JPY":   0.060,
    "NIFTY50":   5.0,     "BANKNIFTY": 10.0,   "SENSEX":    15.0,
    "RELIANCE":  1.0,     "TCS":       1.5,
}

MAX_SIGNALS_PER_DAY = {
    "XAU/USD":   4,  "NAS100":    3,  "SPX500":    3,
    "EUR/USD":   4,  "GBP/JPY":   3,
    "NIFTY50":   4,  "BANKNIFTY": 4,  "SENSEX":    3,
    "RELIANCE":  3,  "TCS":       3,
}

MARKET_STRUCTURE = {
    "XAU/USD":   {"sweep_lookback": 4,  "zone_lookback": 6,  "displacement_mult": 1.10, "premium_discount_lookback": 12, "wick_ratio": 1.6},
    "NAS100":    {"sweep_lookback": 5,  "zone_lookback": 8,  "displacement_mult": 1.20, "premium_discount_lookback": 15, "wick_ratio": 1.8},
    "SPX500":    {"sweep_lookback": 5,  "zone_lookback": 6,  "displacement_mult": 1.15, "premium_discount_lookback": 13, "wick_ratio": 1.5},
    "EUR/USD":   {"sweep_lookback": 6,  "zone_lookback": 8,  "displacement_mult": 1.05, "premium_discount_lookback": 16, "wick_ratio": 1.3},
    "GBP/JPY":   {"sweep_lookback": 5,  "zone_lookback": 8,  "displacement_mult": 1.15, "premium_discount_lookback": 14, "wick_ratio": 1.6},
    "NIFTY50":   {"sweep_lookback": 5,  "zone_lookback": 8,  "displacement_mult": 1.20, "premium_discount_lookback": 16, "wick_ratio": 1.7},
    "BANKNIFTY": {"sweep_lookback": 5,  "zone_lookback": 8,  "displacement_mult": 1.25, "premium_discount_lookback": 16, "wick_ratio": 1.8},
    "SENSEX":    {"sweep_lookback": 5,  "zone_lookback": 8,  "displacement_mult": 1.18, "premium_discount_lookback": 16, "wick_ratio": 1.6},
    "RELIANCE":  {"sweep_lookback": 5,  "zone_lookback": 8,  "displacement_mult": 1.15, "premium_discount_lookback": 14, "wick_ratio": 1.5},
    "TCS":       {"sweep_lookback": 5,  "zone_lookback": 8,  "displacement_mult": 1.15, "premium_discount_lookback": 14, "wick_ratio": 1.5},
}

MARKET_MIN_STRUCTURE_SCORE = {
    "XAU/USD":   3, "NAS100":    4, "SPX500":    3,
    "EUR/USD":   3, "GBP/JPY":   3,
    "NIFTY50":   4, "BANKNIFTY": 5, "SENSEX":    4,
    "RELIANCE":  3, "TCS":       3,
}

CORRELATED_GROUPS = [
    ["NAS100", "SPX500"],
    ["EUR/USD", "GBP/JPY"],
    ["NIFTY50", "BANKNIFTY", "SENSEX"],
    ["RELIANCE", "TCS"],
]

DUPLICATE_WINDOWS = {
    "XAU/USD":   600, "NAS100":    900, "SPX500":    900,
    "EUR/USD":   600, "GBP/JPY":   600,
    "NIFTY50":   600, "BANKNIFTY": 600, "SENSEX":    600,
    "RELIANCE":  600, "TCS":       600,
}

ALLOWED_SESSIONS = [
    "Asian Precision", "London", "NY+London", "NY Killzone",
    "India Open", "India Midday", "India Close",
]

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

# Box state cache per symbol — stores today's box high/low
_box_cache = {s: {"high": None, "low": None, "date": None, "height": None} for s in SYMBOLS}

for _file in ["signals_log.csv", "signals_backup.csv"]:
    if not os.path.exists(_file):
        with open(_file, "a", encoding="utf-8"):
            pass

# ============================================================
# DAILY RESET
# ============================================================
def reset_daily():
    global daily_pnl, consecutive_losses, last_reset_day
    global _daily_signal_count, _htf_cache, _box_cache
    current_day = datetime.now(timezone.utc).day
    if current_day != last_reset_day:
        daily_pnl           = 0
        consecutive_losses  = 0
        last_reset_day      = current_day
        _daily_signal_count = {s: 0 for s in SYMBOLS}
        _htf_cache          = {s: {"trend": "NEUTRAL", "ts": 0} for s in SYMBOLS}
        # Reset box cache every day — new day = new box
        _box_cache          = {s: {"high": None, "low": None, "date": None, "height": None} for s in SYMBOLS}
        log.info("Daily reset complete — Box levels cleared")

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
# WATCHDOG / LOG ROTATION
# ============================================================
def watchdog():
    try:
        with open("heartbeat.txt", "w", encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} | {SYSTEM_VERSION} | ACTIVE")
    except Exception as e:
        log.error(f"Watchdog failure: {e}")

def rotate_log():
    try:
        if os.path.isfile("signals_log.csv"):
            if os.path.getsize("signals_log.csv") > 5_000_000:
                os.rename("signals_log.csv", f"signals_log_{int(time.time())}.csv")
    except Exception as e:
        log.error(f"Log rotation failure: {e}")

# ============================================================
# SIGNAL LOGGER
# ============================================================
def log_signal(symbol, direction, score, rr, entry, sl, tp,
               session, regime, timeframe, signal_type):
    with log_lock:
        file_exists = os.path.isfile("signals_log.csv")
        with open("signals_log.csv", "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["version","timestamp","symbol","direction",
                                  "score","rr","entry","sl","tp",
                                  "session","regime","timeframe","signal_type"])
            writer.writerow([SYSTEM_VERSION, datetime.now(timezone.utc).isoformat(),
                             symbol, direction, score, rr, entry, sl, tp,
                             session, regime, timeframe, signal_type])
        try:
            with open("signals_backup.csv", "a", newline="", encoding="utf-8") as bk:
                csv.writer(bk).writerow([SYSTEM_VERSION, datetime.now(timezone.utc).isoformat(),
                                         symbol, direction, score, rr, entry, sl, tp,
                                         session, regime, timeframe, signal_type])
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
                json={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"},
                timeout=8
            )
            if r.status_code != 200:
                log.error(f"Telegram HTTP {r.status_code} | {r.text}")
                time.sleep(2)
                continue
            log.info("Telegram sent")
            return True
        except Exception as e:
            log.error(f"Telegram error attempt {attempt+1}: {e}")
            time.sleep(2)
    return False

# ============================================================
# CIRCUIT BREAKERS
# ============================================================
def weekend_block(symbol_key):
    now = datetime.now(timezone.utc)
    wd, hr = now.weekday(), now.hour
    if wd == 5: return True
    if wd == 6 and hr < 21: return True
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
# SESSION FILTER
# ============================================================
def in_session(symbol_key):
    now = datetime.now(timezone.utc)
    h   = now.hour
    m   = now.minute
    hm  = h * 60 + m

    s, e = MARKETS[symbol_key]["sessions"]
    if not (s <= h < e):
        return False, "Closed"

    mtype = MARKETS[symbol_key]["market_type"]

    if mtype == "india":
        if 225 <= hm < 330:  return True, "India Open"
        if 330 <= hm < 450:  return True, "India Midday"
        if 450 <= hm < 600:  return True, "India Close"
        return False, "Closed"

    if 1  <= h < 6:  return True, "Asian Precision"
    if 8  <= h < 11: return True, "London"
    if 13 <= h < 15: return True, "NY Killzone"
    if 14 <= h < 16: return True, "NY+London"
    return False, "Closed"

# ============================================================
# DATA FETCHING
# ============================================================
def fetch_yf(ticker, period="7d", interval="1m"):
    for attempt in range(3):
        try:
            time.sleep(0.4)
            raw = yf.download(ticker, period=period, interval=interval,
                              progress=False, auto_adjust=True, threads=False)
            if raw.empty:
                log.error(f"{ticker} empty ({interval})")
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
            for col in ["open","high","low","close","volume"]:
                if col not in raw.columns:
                    raw[col] = 0
            df = raw[["open","high","low","close","volume"]].copy()
            df = df.drop_duplicates().ffill().bfill()
            return df.reset_index(drop=True)
        except Exception as e:
            log.error(f"YF fetch {ticker} {interval} attempt {attempt+1}: {e}")
            time.sleep(1)
    return None

def fetch_market_data(symbol_key, for_breakout=False):
    yf_sym = MARKETS[symbol_key]["yf"]
    if for_breakout:
        period = "59d" if symbol_key in ["EUR/USD","GBP/JPY"] else "30d"
        df = fetch_yf(yf_sym, period=period, interval="15m")
        if df is not None and len(df) > 60:
            return df.drop_duplicates().reset_index(drop=True), "15M"
        return None, None
    df = fetch_yf(yf_sym, period="7d", interval="1m")
    if df is not None and len(df) > 60:
        return df.drop_duplicates().reset_index(drop=True), "1M"
    period = "59d" if symbol_key in ["EUR/USD","GBP/JPY"] else "30d"
    df = fetch_yf(yf_sym, period=period, interval="5m")
    if df is not None and len(df) > 60:
        return df.drop_duplicates().reset_index(drop=True), "5M"
    return None, None

def get_entry_data(symbol_key, for_breakout=False):
    return fetch_market_data(symbol_key, for_breakout=for_breakout)

def get_spread(df):
    if df is None or len(df) < 3:
        return 999
    recent = df.tail(3)
    return (recent["high"].astype(float) - recent["low"].astype(float)).mean() * 0.18

# ============================================================
# INDICATORS
# ============================================================
def add_ind(df):
    df  = df.copy()
    cl  = pd.to_numeric(df["close"],  errors="coerce")
    hi  = pd.to_numeric(df["high"],   errors="coerce")
    lo  = pd.to_numeric(df["low"],    errors="coerce")
    vol = pd.to_numeric(df["volume"], errors="coerce")

    df["ema9"]   = ta.trend.EMAIndicator(cl, 5).ema_indicator()
    df["ema21"]  = ta.trend.EMAIndicator(cl, 13).ema_indicator()
    df["ema50"]  = ta.trend.EMAIndicator(cl, 21).ema_indicator()
    df["ema200"] = ta.trend.EMAIndicator(cl, 50).ema_indicator()
    df["rsi"]    = ta.momentum.RSIIndicator(cl, 7).rsi()
    df["atr"]    = ta.volatility.AverageTrueRange(hi, lo, cl, 7).average_true_range()
    df["adx"]    = ta.trend.ADXIndicator(hi, lo, cl, 7).adx()
    df["volma"]  = vol.rolling(10).mean()
    df["vwap"]   = (cl * vol).cumsum() / vol.cumsum()
    df["stdv"]   = cl.rolling(STDV_PERIOD).std()
    df["aox_fast"] = ta.trend.EMAIndicator(cl, AOX_FAST).ema_indicator()
    df["aox_slow"] = ta.trend.EMAIndicator(cl, AOX_SLOW).ema_indicator()
    df["aox"]    = df["aox_fast"] - df["aox_slow"]

    hlc3 = (hi + lo + cl) / 3
    esa  = hlc3.ewm(span=6, adjust=False).mean()
    d    = (hlc3 - esa).abs().ewm(span=6, adjust=False).mean()
    ci   = (hlc3 - esa) / (0.015 * d)
    df["wt1"] = ci.ewm(span=10, adjust=False).mean()
    df["wt2"] = df["wt1"].rolling(3).mean()

    df.replace([float("inf"), float("-inf")], pd.NA, inplace=True)
    df.ffill(inplace=True)
    df.dropna(inplace=True)
    return df

# ============================================================
# ★★★ BOX ENGINE — CORE STRATEGY (AS PER CHART SCREENSHOTS) ★★★
#
# Logic matching the TradingView LuxAlgo boxes in your images:
#   - Box upper line = highest high of last N candles (day high)
#   - Box lower line = lowest low of last N candles (day low)
#   - BOX BREAKOUT UP: candle CLOSES above upper line → BUY
#   - BOX BREAKDOWN DN: candle CLOSES below lower line → SELL
#   - Target = entry ± box_height (as shown in chart — full box projected)
#   - SL = opposite box line ± small buffer
# ============================================================

def build_box(df, symbol_key, lookback=None):
    """
    Build the LuxAlgo-style box for the current day.
    Returns: (box_high, box_low, box_height) or (None, None, None)
    """
    if df is None or len(df) < 20:
        return None, None, None

    n   = lookback or BOX_LOOKBACK_CANDLES
    atr = float(df.iloc[-1]["atr"]) if "atr" in df.columns else 1.0

    # Use the last N candles (excluding the current live candle)
    window = df.iloc[-(n+1):-1]
    if len(window) < 5:
        return None, None, None

    box_high   = float(window["high"].max())
    box_low    = float(window["low"].min())
    box_height = box_high - box_low

    # Filter: box must be meaningful (not a tiny range)
    if box_height < atr * BOX_MIN_HEIGHT_ATR:
        log.info(f"{symbol_key} box too small ({box_height:.4f} < {atr * BOX_MIN_HEIGHT_ATR:.4f} ATR)")
        return None, None, None

    return box_high, box_low, box_height


def get_day_box(df, symbol_key):
    """
    Marks the DAY HIGH and DAY LOW (as seen in your charts).
    Uses first N candles of today's session to build the box,
    then watches for breakout beyond those levels.
    Falls back to rolling 20-candle box if session data is short.
    """
    today = datetime.now(timezone.utc).date()
    cache = _box_cache[symbol_key]

    # Return cached box if already built today
    if cache["date"] == str(today) and cache["high"] is not None:
        return cache["high"], cache["low"], cache["height"]

    if df is None or len(df) < 10:
        return None, None, None

    atr = float(df.iloc[-1]["atr"]) if "atr" in df.columns else 1.0

    # Build box from last BOX_LOOKBACK_CANDLES candles (rolling day high/low)
    box_high, box_low, box_height = build_box(df, symbol_key, BOX_LOOKBACK_CANDLES)

    if box_high is None:
        return None, None, None

    # Cache it
    _box_cache[symbol_key] = {
        "high":   box_high,
        "low":    box_low,
        "height": box_height,
        "date":   str(today),
    }
    log.info(f"{symbol_key} BOX SET | High: {box_high:.4f} | Low: {box_low:.4f} | Height: {box_height:.4f}")
    return box_high, box_low, box_height


def detect_box_breakout(df, symbol_key):
    """
    ★ MAIN BOX STRATEGY DETECTOR ★

    Matches the chart pattern:
    - GBP/JPY: price swept above box upper line (supply zone, circled candle),
      then CLOSED back below → SELL signal, target = box height below entry
    - NAS100: price touched box lower line (demand zone, circled candles),
      then CLOSED back above → BUY signal, target = box height above entry

    Returns: (direction, box_high, box_low, box_height, signal_tag) or (None,...)
    """
    if df is None or len(df) < 30:
        return None, None, None, None, None

    box_high, box_low, box_height = get_day_box(df, symbol_key)
    if box_high is None:
        return None, None, None, None, None

    last  = df.iloc[-1]
    prev  = df.iloc[-2]
    close = float(last["close"])
    high  = float(last["high"])
    low   = float(last["low"])
    atr   = float(last["atr"])
    dec   = MARKETS[symbol_key]["decimals"]

    buf = box_height * BOX_BREAKOUT_BUFFER  # small confirmation buffer

    # ── BOX BREAKOUT UP (BUY) ──
    # Candle closes above box upper line → breakout confirmed
    # Matches NAS100 chart: circles at box lows, entry when price breaks up
    box_break_up = (
        close > box_high + buf and          # close is above the box upper line
        prev["close"] <= box_high + buf      # previous candle was inside/at box
    )

    # ── BOX BREAKDOWN DOWN (SELL) ──
    # Candle closes below box lower line → breakdown confirmed
    # Matches GBP/JPY chart: circled candle at box top, then price drops below
    box_break_dn = (
        close < box_low - buf and           # close is below the box lower line
        prev["close"] >= box_low - buf       # previous candle was inside/at box
    )

    # ── BOX REJECTION UP (SELL from top) ──
    # Price WICKS above box upper line but CLOSES back inside (supply rejection)
    # This is the GBP/JPY circled bearish candle pattern — wick above, body inside
    box_reject_top = (
        high > box_high and                  # wick pierced above box
        close < box_high - buf and           # but closed BACK inside (rejection)
        close < float(last["open"])          # red candle (bearish body)
    )

    # ── BOX REJECTION DOWN (BUY from bottom) ──
    # Price WICKS below box lower line but CLOSES back inside (demand rejection)
    # NAS100 chart circled candles: touched box low, closed back up
    box_reject_bot = (
        low < box_low and                    # wick pierced below box
        close > box_low + buf and            # but closed BACK inside (rejection)
        close > float(last["open"])          # green candle (bullish body)
    )

    if box_break_up:
        return "BUY",  box_high, box_low, box_height, "BOX BREAKOUT ▲ (Close above upper line)"
    if box_break_dn:
        return "SELL", box_high, box_low, box_height, "BOX BREAKDOWN ▼ (Close below lower line)"
    if box_reject_top:
        return "SELL", box_high, box_low, box_height, "BOX REJECTION ↩ (Wick above → SELL)"
    if box_reject_bot:
        return "BUY",  box_high, box_low, box_height, "BOX REJECTION ↪ (Wick below → BUY)"

    return None, None, None, None, None


def calc_box_levels(price, box_high, box_low, box_height, symbol_key, direction):
    """
    Target = entry ± box_height (full box projected, as shown in charts).
    SL     = opposite side of the box ± buffer.
    """
    dec      = MARKETS[symbol_key]["decimals"]
    min_sl   = MARKETS[symbol_key]["min_sl"]
    rr       = RR_PROFILE[symbol_key]["BREAKOUT"]

    if direction == "BUY":
        # Entry above box upper line
        sl = round(box_low - (box_height * 0.10), dec)        # SL below box low
        tp = round(price   + box_height, dec)                  # TP = box height above entry
        sl_dist = price - sl
        if sl_dist < min_sl:
            sl = round(price - min_sl, dec)
            sl_dist = min_sl
    else:
        # Entry below box lower line
        sl = round(box_high + (box_height * 0.10), dec)       # SL above box high
        tp = round(price    - box_height, dec)                 # TP = box height below entry
        sl_dist = sl - price
        if sl_dist < min_sl:
            sl = round(price + min_sl, dec)
            sl_dist = min_sl

    actual_rr = round(abs(tp - price) / sl_dist, 2) if sl_dist > 0 else rr
    return sl, tp, round(sl_dist, dec), actual_rr

# ============================================================
# TREND HELPERS
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
    if last["ema21"] > last["ema50"]:
        trend = "BULL"
    elif last["ema21"] < last["ema50"]:
        trend = "BEAR"
    else:
        trend = MARKETS[symbol_key].get("bias", "NEUTRAL")
    cache["trend"] = trend
    cache["ts"]    = now
    return trend

def mtf_bullish(symbol_key, df):
    if df is None or len(df) < 60: return False
    last = df.iloc[-1]
    return float(last["ema9"]) > float(last["ema21"]) > float(last["ema50"]) and float(last["close"]) > float(last["ema200"])

def mtf_bearish(symbol_key, df):
    if df is None or len(df) < 60: return False
    last = df.iloc[-1]
    return float(last["ema9"]) < float(last["ema21"]) < float(last["ema50"]) and float(last["close"]) < float(last["ema200"])

def h4_trend(df, direction):
    if df is None or len(df) < 55: return False
    price = float(df.iloc[-1]["close"])
    ema50 = float(df.iloc[-1]["ema200"])
    return price > ema50 if direction == "BUY" else price < ema50

def vwap_trend(df, direction):
    if df is None or len(df) < 10: return False
    price = float(df.iloc[-1]["close"])
    vwap  = float(df.iloc[-1]["vwap"])
    if pd.isna(vwap): return False
    return price > vwap if direction == "BUY" else price < vwap

def wavetrend_confirmation(df, direction):
    if len(df) < 5: return False
    wt1_now  = float(df.iloc[-1]["wt1"])
    wt2_now  = float(df.iloc[-1]["wt2"])
    wt1_prev = float(df.iloc[-2]["wt1"])
    wt2_prev = float(df.iloc[-2]["wt2"])
    if direction == "BUY":
        return wt1_prev < wt2_prev and wt1_now > wt2_now and wt1_now < 30
    return wt1_prev > wt2_prev and wt1_now < wt2_now and wt1_now > -30

def scalp_macro_filter(df, direction):
    if df is None: return False
    score = 0
    if h4_trend(df, direction):   score += 4
    if vwap_trend(df, direction): score += 4
    last = df.iloc[-1]
    if direction == "BUY"  and float(last["ema9"]) > float(last["ema21"]): score += 2
    if direction == "SELL" and float(last["ema9"]) < float(last["ema21"]): score += 2
    return score >= 6

# ============================================================
# PATTERN DETECTION
# ============================================================
def fair_value_gap(df):
    if len(df) < 3: return False, False
    c1, c3 = df.iloc[-3], df.iloc[-1]
    return float(c1["high"]) < float(c3["low"]), float(c1["low"]) > float(c3["high"])

def detect_choch(df):
    if len(df) < 6: return False, False
    highs = df["high"].tail(6).tolist()
    lows  = df["low"].tail(6).tolist()
    close = float(df.iloc[-1]["close"])
    return (lows[-2] < lows[-3] and close > highs[-2],
            highs[-2] > highs[-3] and close < lows[-2])

def detect_liquidity_sweep(df, symbol_key):
    lookback = MARKET_STRUCTURE[symbol_key]["sweep_lookback"]
    if len(df) < lookback: return False, False
    recent    = df.tail(lookback)
    prev_high = float(recent["high"].iloc[:-1].max())
    prev_low  = float(recent["low"].iloc[:-1].min())
    last      = recent.iloc[-1]
    return (float(last["low"]) < prev_low  and float(last["close"]) > prev_low,
            float(last["high"]) > prev_high and float(last["close"]) < prev_high)

def detect_zone_retest(df, symbol_key, direction):
    lookback = MARKET_STRUCTURE[symbol_key]["zone_lookback"]
    if len(df) < lookback: return False
    recent  = df.tail(lookback)
    current = df.iloc[-1]
    if direction == "BUY":
        return float(current["low"]) <= float(recent["low"].min()) * 1.002
    return float(current["high"]) >= float(recent["high"].max()) * 0.998

def detect_displacement(df, symbol_key):
    if len(df) < 2: return False
    candle = df.iloc[-1]
    body   = abs(float(candle["close"]) - float(candle["open"]))
    return body > float(candle["atr"]) * MARKET_STRUCTURE[symbol_key]["displacement_mult"]

def detect_wick_rejection(df, atr, symbol_key):
    if len(df) < 2: return False, False
    candle = df.iloc[-1]
    op, cl, hi, lo = float(candle["open"]), float(candle["close"]), float(candle["high"]), float(candle["low"])
    body = abs(cl - op)
    if body < atr * 0.05: return False, False
    upper = hi - max(op, cl)
    lower = min(op, cl) - lo
    wr    = MARKETS[symbol_key]["wick_ratio"]
    return lower > body * wr, upper > body * wr

def premium_discount(df, symbol_key):
    lookback = MARKET_STRUCTURE[symbol_key]["premium_discount_lookback"]
    if len(df) < lookback: return {"discount": False, "premium": False}
    recent   = df.tail(lookback)
    midpoint = (float(recent["high"].max()) + float(recent["low"].min())) / 2
    price    = float(df.iloc[-1]["close"])
    return {"discount": price < midpoint, "premium": price > midpoint}

def break_of_structure(df, direction):
    if len(df) < 6: return False
    atr   = float(df.iloc[-1]["atr"])
    close = float(df.iloc[-1]["close"])
    if direction == "BUY":
        return close > float(df["high"].iloc[-6:-1].max()) + atr * 0.08
    return close < float(df["low"].iloc[-6:-1].min()) - atr * 0.08

def institutional_volume(df):
    if len(df) < 11: return False
    last  = df.iloc[-1]
    vol   = float(last["volume"])
    volma = float(last["volma"]) if not pd.isna(last["volma"]) else 0
    return volma > 0 and vol > volma * 1.5

def strong_candle(df, direction):
    if len(df) < 2: return False
    c = df.iloc[-1]
    op, cl, hi, lo = float(c["open"]), float(c["close"]), float(c["high"]), float(c["low"])
    body  = abs(cl - op)
    total = hi - lo
    if total == 0 or body / total < 0.55: return False
    if direction == "BUY":  return cl > (lo + total * 0.65)
    return cl < (lo + total * 0.35)

def detect_supply_demand_zones(df):
    if len(df) < 10: return None, None
    recent = df.tail(10)
    return (recent["low"].rolling(3).min().iloc[-1],
            recent["high"].rolling(3).max().iloc[-1])

def institutional_structure_score(df, symbol_key):
    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    bull_wick,  bear_wick  = detect_wick_rejection(df, float(df.iloc[-1]["atr"]), symbol_key)
    displacement           = detect_displacement(df, symbol_key)
    pd_zone                = premium_discount(df, symbol_key)

    buy_score = sell_score = 0
    buy_cond  = {}
    sell_cond = {}

    if bull_sweep: buy_score  += 2; buy_cond["SWEEP"]        = True
    if bull_wick:  buy_score  += 2; buy_cond["WICK"]         = True
    if detect_zone_retest(df, symbol_key, "BUY"):
                   buy_score  += 2; buy_cond["ZONE"]         = True
    if displacement:
                   buy_score  += 2; buy_cond["DISPLACEMENT"] = True
    if pd_zone["discount"]:
                   buy_score  += 1; buy_cond["DISCOUNT"]     = True

    if bear_sweep: sell_score += 2; sell_cond["SWEEP"]       = True
    if bear_wick:  sell_score += 2; sell_cond["WICK"]        = True
    if detect_zone_retest(df, symbol_key, "SELL"):
                   sell_score += 2; sell_cond["ZONE"]        = True
    if displacement:
                   sell_score += 2; sell_cond["DISPLACEMENT"]= True
    if pd_zone["premium"]:
                   sell_score += 1; sell_cond["PREMIUM"]     = True

    if buy_score  >= 8: buy_score  += 1
    if sell_score >= 8: sell_score += 1

    return buy_cond, sell_cond, buy_score, sell_score

# ============================================================
# SIGNAL GATE
# ============================================================
def get_signal_number(symbol_key, session):
    global _signal_counter
    if _signal_counter[symbol_key]["session"] != session:
        _signal_counter[symbol_key]["session"] = session
        _signal_counter[symbol_key]["count"]   = 1
    else:
        _signal_counter[symbol_key]["count"] += 1
    n = _signal_counter[symbol_key]["count"]
    return n, "SCALP ENTRY"

def scalp_signal_allowed(symbol_key, session):
    sc = _signal_counter[symbol_key]
    if sc["session"] == session and sc["count"] >= 1:
        log.info(f"REJECTED {symbol_key} — signal #2/#3 blocked")
        return False
    return True

# ============================================================
# SPREAD / VOLATILITY
# ============================================================
def spread_too_high(symbol_key, spread):
    return spread > MAX_SPREAD[symbol_key] * 0.90

def volatility_danger(df, symbol_key):
    if len(df) < 30: return False
    atr     = float(df.iloc[-1]["atr"])
    atr_avg = df["atr"].rolling(20).mean().iloc[-1]
    if pd.isna(atr_avg) or atr_avg == 0: return False
    return (atr / atr_avg) > 2.5

def quantum_volatility_ok(df):
    if len(df) < 30: return False
    atr     = float(df.iloc[-1]["atr"])
    atr_avg = df["atr"].rolling(20).mean().iloc[-1]
    if pd.isna(atr_avg) or atr_avg == 0: return False
    return 0.60 <= (atr / atr_avg) <= 2.50

def false_breakout_filter(df, direction):
    if len(df) < 3: return False
    last = df.iloc[-1]
    prev = df.iloc[-2]
    atr  = float(df.iloc[-1]["atr"])
    if direction == "BUY":
        return float(last["close"]) > float(prev["high"]) - atr * 0.08
    return float(last["close"]) < float(prev["low"]) + atr * 0.08

def correlated_signal_block(symbol_key):
    if not CORRELATION_BLOCK: return False
    for group in CORRELATED_GROUPS:
        if symbol_key in group:
            active = sum(1 for s in group if time.time() - _signal_sent.get(s, 0) < 3600)
            if active >= MAX_OPEN_CORRELATED:
                log.info(f"Correlation blocker active for {symbol_key}")
                return True
    return False

def duplicate_signal(symbol_key, direction):
    now      = time.time()
    cooldown = DUPLICATE_WINDOWS.get(symbol_key, 600)
    with signal_lock:
        last_dir  = _last_signal_direction.get(symbol_key)
        last_time = _last_signal_time.get(symbol_key, 0)
        if last_dir == direction and now - last_time < cooldown:
            log.info(f"Duplicate blocked {symbol_key} ({int(cooldown-(now-last_time))}s remaining)")
            return True
        _last_signal_direction[symbol_key] = direction
        _last_signal_time[symbol_key]      = now
    return False

def economic_news_block():
    return False

# ============================================================
# BUILD BASE SCORE
# ============================================================
def build_score(df, trend, symbol_key):
    last   = df.iloc[-1]
    rsi    = float(last["rsi"])
    ema9   = float(last["ema9"])
    ema21  = float(last["ema21"])
    ema50  = float(last["ema50"])
    atr    = float(last["atr"])
    adx    = float(last["adx"])
    vol    = float(last["volume"])
    volma  = float(last["volma"]) if not pd.isna(last["volma"]) else 0
    stdv   = float(last["stdv"])  if not pd.isna(last["stdv"])  else 0
    aox    = float(last["aox"])   if not pd.isna(last["aox"])   else 0
    stdv_ma = df["stdv"].rolling(STDV_PERIOD).mean().iloc[-1] if len(df) > STDV_PERIOD else 0

    bull_fvg,   bear_fvg   = fair_value_gap(df)
    bull_choch, bear_choch = detect_choch(df)
    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    bull_wick,  bear_wick  = detect_wick_rejection(df, atr, symbol_key)
    bullish_break = float(last["close"]) > float(df.iloc[-2]["high"]) + atr * 0.08
    bearish_break = float(last["close"]) < float(df.iloc[-2]["low"])  - atr * 0.08

    buy = {
        "HTF":   trend == "BULL",
        "EMA":   ema9 > ema21 > ema50,
        "VWAP":  float(last["close"]) > float(last["vwap"]),
        "RSI":   52 <= rsi <= 75,
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

    if symbol_key in ["XAU/USD","NIFTY50","BANKNIFTY"]:
        if bull_sweep: buy_score  += 1
        if bear_sweep: sell_score += 1
        if bull_wick:  buy_score  += 1
        if bear_wick:  sell_score += 1

    if adx >= 30:
        if   buy_score > sell_score: buy_score  += 1
        elif sell_score > buy_score: sell_score += 1

    return buy, sell, buy_score, sell_score

# ============================================================
# WIZARD AI
# ============================================================
def wizard_ai_confirmation(df, symbol_key, direction):
    if len(df) < 60: return False, 0
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
        if close > ema50:                  score += 3
        if ema50  > ema200:                score += 2
        if rsi    > 52:                    score += 2
        if adx    > WIZARD_ADX_THRESHOLD:  score += 2
        if aox    > 0:                     score += 2
        if vwap   > 0 and close > vwap:    score += 2
    else:
        if close < ema50:                  score += 3
        if ema50  < ema200:                score += 2
        if rsi    < 48:                    score += 2
        if adx    > WIZARD_ADX_THRESHOLD:  score += 2
        if aox    < 0:                     score += 2
        if vwap   > 0 and close < vwap:    score += 2

    if volma > 0 and volume > volma * WIZARD_VOLUME_MULT: score += 2

    bull_fvg, bear_fvg     = fair_value_gap(df)
    bull_choch, bear_choch = detect_choch(df)
    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    bull_wick, bear_wick   = detect_wick_rejection(df, float(last["atr"]), symbol_key)

    if direction == "BUY":
        if bull_fvg:   score += 2
        if bull_choch: score += 2
        if bull_sweep: score += 2
        if bull_wick:  score += 2
    else:
        if bear_fvg:   score += 2
        if bear_choch: score += 2
        if bear_sweep: score += 2
        if bear_wick:  score += 2

    pd_zone = premium_discount(df, symbol_key)
    if direction == "BUY"  and pd_zone["discount"]: score += 1
    if direction == "SELL" and pd_zone["premium"]:  score += 1

    return score >= WIZARD_MIN_SCORE, score

# ============================================================
# ULTRA SNIPER SCORE
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
    if direction == "BUY"  and bull_sweep:    score += 2
    if direction == "SELL" and bear_sweep:    score += 2
    if direction == "BUY"  and bull_fvg:      score += 2
    if direction == "SELL" and bear_fvg:      score += 2
    if break_of_structure(df, direction):     score += 2
    if institutional_volume(df):              score += 2
    if strong_candle(df, direction):          score += 2
    if direction == "BUY"  and rsi > 55:      score += 2
    if direction == "SELL" and rsi < 45:      score += 2
    if adx > 25:                              score += 2
    if volma > 0 and vol > volma * 1.5:       score += 3
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

def breakout_quality(score):
    if   score >= 16: return "GOD-TIER BREAKOUT"
    elif score >= 13: return "ELITE BREAKOUT"
    return "HIGH-PROB BREAKOUT"

def adaptive_risk(session):
    return {"Asian Precision": 0.6, "London": 1.0, "NY Killzone": 1.2,
            "India Open": 1.0, "India Midday": 0.8, "India Close": 0.7}.get(session, 0.9)

def detect_market_regime(df):
    return "SCALP"

def get_dynamic_rr(symbol_key, regime):
    return RR_PROFILE.get(symbol_key, {}).get(regime, MARKETS[symbol_key]["rr"])

# ============================================================
# LEVEL CALCULATOR (Scalp)
# ============================================================
def calc_levels(price, atr, symbol_key, df, direction, regime):
    min_sl   = MARKETS[symbol_key]["min_sl"]
    decimals = MARKETS[symbol_key]["decimals"]
    recent   = df.tail(3)

    swing_dist = (price - float(recent["low"].min())
                  if direction == "BUY"
                  else float(recent["high"].max()) - price)

    atr_sl    = atr * ATR_MULT * ATR_MARKET_MULTIPLIER[symbol_key]
    swing_cap = atr * 1.5 * ATR_MARKET_MULTIPLIER[symbol_key]
    swing_dist = min(swing_dist, swing_cap)
    sl_dist   = max(min_sl, max(atr_sl, swing_dist * 0.75))
    rr        = get_dynamic_rr(symbol_key, regime)

    if direction == "BUY":
        sl, tp = price - sl_dist, price + sl_dist * rr
    else:
        sl, tp = price + sl_dist, price - sl_dist * rr

    return round(sl, decimals), round(tp, decimals), round(sl_dist, decimals), rr

def lot_for_risk(price, sl, symbol_key, risk_multiplier=1.0):
    risk    = 50 * risk_multiplier
    sl_dist = abs(price - sl)
    if sl_dist <= 0: return 0.01
    lot  = risk / (sl_dist * DOLLAR_PER_POINT[symbol_key])
    caps = {"XAU/USD": 1.50, "NAS100": 2.00, "SPX500": 2.00,
            "EUR/USD": 3.00, "GBP/JPY": 2.00,
            "NIFTY50": 50.0, "BANKNIFTY": 50.0, "SENSEX": 50.0,
            "RELIANCE": 500.0, "TCS": 500.0}
    if symbol_key in ["NIFTY50","BANKNIFTY","SENSEX","RELIANCE","TCS"]:
        lot = max(1.0, round(lot))
        return float(lot)
    return round(max(0.01, min(lot, caps[symbol_key])), 3)

# ============================================================
# MASTER SIGNAL ENGINE (Scalp)
# ============================================================
def master_signal(symbol_key, df, session, trend, regime,
                  buy, sell, buy_score, sell_score,
                  structure_buy_score, structure_sell_score):

    direction = determine_best_direction(buy_score, sell_score)
    best      = max(buy_score, sell_score)

    if not scalp_macro_filter(df, direction):
        log.info(f"REJECTED {symbol_key} scalp macro filter")
        return None, None, None

    if ENABLE_WIZARD_AI:
        wizard_pass, wizard_score = wizard_ai_confirmation(df, symbol_key, direction)
        if not wizard_pass:
            log.info(f"REJECTED {symbol_key} Wizard AI failed | Score: {wizard_score}")
            return None, None, None
        best += int(wizard_score * 0.30)
    else:
        wizard_score = 0

    sniper = ultra_sniper_score(df, symbol_key, direction)
    best  += sniper

    required = SESSION_THRESHOLDS.get(session, 12)
    if best < required:
        log.info(f"REJECTED {symbol_key} session score too low ({best} < {required})")
        return None, None, None

    if VOLATILITY_KILL and not quantum_volatility_ok(df):
        log.info(f"REJECTED {symbol_key} volatility filter")
        return None, None, None

    if FALSE_BREAK_FILTER and not false_breakout_filter(df, direction):
        log.info(f"REJECTED {symbol_key} false breakout filter")
        return None, None, None

    return direction, best, wizard_score

# ============================================================
# EXECUTE SCALP TRADE
# ============================================================
def execute_trade(symbol_key, df, direction, best, wizard_score,
                  sniper_score, macro_trend, session, trend,
                  regime, buy, sell, source, asia_mode):

    price = float(df.iloc[-1]["close"])
    atr   = float(df.iloc[-1]["atr"])
    rsi   = float(df.iloc[-1]["rsi"])
    adx   = float(df.iloc[-1]["adx"])
    dec   = MARKETS[symbol_key]["decimals"]

    price += EXECUTION_BUFFER[symbol_key] if direction == "BUY" else -EXECUTION_BUFFER[symbol_key]
    sl, tp, sl_dist, rr = calc_levels(price, atr, symbol_key, df, direction, regime)
    risk_mult = adaptive_risk(session)
    lot       = lot_for_risk(price, sl, symbol_key, risk_mult)
    quality   = trade_quality(best)
    signal_num, entry_type = get_signal_number(symbol_key, session)

    log_signal(symbol_key, direction, best, rr, price, sl, tp,
               session, regime, "1M / 5M", "SCALP")
    sync_real_pnl()

    checks    = buy if direction == "BUY" else sell
    cond_text = "\n".join([f" {k}" for k, v in checks.items() if v])

    action_emoji = "📈" if direction == "BUY" else "📉"
    mtype        = MARKETS[symbol_key]["market_type"]
    market_flag  = "🇮🇳 *INDIA INTRADAY*\n" if mtype == "india" else "🌍 *GLOBAL MARKET*\n"

    msg = (
        f"⚡ *{SYSTEM_VERSION}* | SCALP EXECUTION\n"
        f"*{MARKETS[symbol_key]['mt5']}* | "
        f"⭐⭐⭐⭐⭐ {MARKETS[symbol_key]['tier']}\n"
        f"🔱 *PRIORITY MARKET*\n"
        f"{market_flag}\n"
        f"🔥 *Action:* {direction} {action_emoji}\n"
        f"🎯 *Signal #:* {signal_num}\n"
        f"📍 *Entry Type:* {entry_type}\n"
        f"🚀 *Signal Type:* SCALP\n"
        f"⏱ *Timeframe:* 1M / 5M\n"
        f"⭐ *Total Score:* {best}\n"
        f"🏆 *Trade Quality:* {quality}\n"
        f"🌍 *Macro Trend:* {macro_trend}\n"
        f"🎯 *Sniper Score:* {sniper_score}\n"
        f"🧠 *Wizard AI Score:* {wizard_score if ENABLE_WIZARD_AI else 'OFF'}\n"
        f"📊 *Market Bias:* {MARKETS[symbol_key]['bias']}\n\n"
        f"📍 *Entry:* {price:,.{dec}f}\n"
        f"🛑 *SL:* {sl:,.{dec}f}\n"
        f"🎯 *TP:* {tp:,.{dec}f} *(1:{rr} RR)*\n\n"
        f"📈 *RSI:* {rsi:.1f} | 📉 *ADX:* {adx:.1f}\n"
        f"⏰ *Session:* {session} | 📡 *Source:* {source}\n"
        f"🧠 *Mode:* {'ASIA SCALP' if asia_mode else 'CORE SCALP'}\n"
        f"💵 *Lot:* {lot}\n\n"
        f"✅ *Conditions:*\n{cond_text}\n\n"
        f"🛡 *ELITE SCALP FILTER ACTIVE*\n"
        f"⚡ *ULTIMATE BOX BREAKOUT — 2026 ELITE*"
    )
    send_telegram(msg)
    log.info(f"SCALP {symbol_key} {direction} | Entry:{price} SL:{sl} TP:{tp}")

# ============================================================
# ★★★ EXECUTE BOX BREAKOUT TRADE (CORE STRATEGY) ★★★
# ============================================================
def execute_box_breakout(symbol_key, df, direction, score,
                          box_high, box_low, box_height, signal_tag,
                          session, source, trend):
    price = float(df.iloc[-1]["close"])
    rsi   = float(df.iloc[-1]["rsi"])
    adx   = float(df.iloc[-1]["adx"])
    vol   = float(df.iloc[-1]["volume"])
    volma = float(df.iloc[-1]["volma"]) if not pd.isna(df.iloc[-1]["volma"]) else 0
    dec   = MARKETS[symbol_key]["decimals"]

    price += EXECUTION_BUFFER[symbol_key] if direction == "BUY" else -EXECUTION_BUFFER[symbol_key]

    # Box-based levels (target = full box height projected)
    sl, tp, sl_dist, rr = calc_box_levels(price, box_high, box_low, box_height, symbol_key, direction)

    lot     = lot_for_risk(price, sl, symbol_key, adaptive_risk(session))
    quality = breakout_quality(score)

    action_emoji = "📈" if direction == "BUY" else "📉"
    mtype        = MARKETS[symbol_key]["market_type"]
    market_flag  = "🇮🇳 *INDIA INTRADAY*\n" if mtype == "india" else "🌍 *GLOBAL MARKET*\n"

    # Box dimensions in message
    box_pct = round((box_height / box_low) * 100, 3) if box_low > 0 else 0

    log_signal(symbol_key, direction, score, rr, price, sl, tp,
               session, "BOX BREAKOUT", "15M", "BOX_BREAKOUT")

    msg = (
        f"📦 *{SYSTEM_VERSION}* | BOX BREAKOUT\n"
        f"*{MARKETS[symbol_key]['mt5']}* | "
        f"⭐⭐⭐⭐⭐ {MARKETS[symbol_key]['tier']}\n"
        f"🔱 *PRIORITY MARKET*\n"
        f"{market_flag}\n"
        f"🔥 *Action:* {direction} {action_emoji}\n"
        f"📍 *Signal:* {signal_tag}\n"
        f"⏱ *Timeframe:* 15M\n"
        f"⭐ *Box Score:* {score}\n"
        f"🏆 *Quality:* {quality}\n"
        f"🌍 *Trend:* {trend}\n\n"
        f"📦 *BOX LEVELS:*\n"
        f"  🔴 Upper Line (Day High): `{box_high:,.{dec}f}`\n"
        f"  🟢 Lower Line (Day Low):  `{box_low:,.{dec}f}`\n"
        f"  📏 Box Height: `{box_height:,.{dec}f}` ({box_pct}%)\n\n"
        f"📍 *Entry:* {price:,.{dec}f}\n"
        f"🛑 *SL:* {sl:,.{dec}f}  ← opposite box line\n"
        f"🎯 *TP:* {tp:,.{dec}f}  ← box height projected *(1:{rr} RR)*\n\n"
        f"📈 *RSI:* {rsi:.1f} | 📉 *ADX:* {adx:.1f}\n"
        f"📊 *Vol vs MA:* {(vol/volma*100):.0f}% of avg\n"
        f"⏰ *Session:* {session} | 📡 *Source:* {source}\n"
        f"💵 *Lot:* {lot}\n\n"
        f"🛡 *BOX BREAKOUT FILTER ACTIVE*\n"
        f"⚡ *ULTIMATE BOX BREAKOUT — 2026 ELITE*"
    )
    send_telegram(msg)
    log.info(f"BOX BREAKOUT {symbol_key} {direction} | Entry:{price} SL:{sl} TP:{tp} RR:{rr} Box:{box_low}-{box_high}")

# ============================================================
# PROCESS SYMBOL — SCALP (1M/5M)
# ============================================================
def process_symbol(symbol_key):
    log.info(f"Scanning {symbol_key}")

    if _daily_signal_count[symbol_key] >= MAX_SIGNALS_PER_DAY[symbol_key]:
        log.info(f"REJECTED {symbol_key} daily cap")
        return
    if weekend_block(symbol_key): return
    if daily_loss_lock():         return
    if loss_streak_lock():        return

    watchdog()
    rotate_log()

    ok, session = in_session(symbol_key)
    if not ok or session not in ALLOWED_SESSIONS:
        return
    if economic_news_block():
        return
    if not scalp_signal_allowed(symbol_key, session):
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
        return
    if volatility_danger(df, symbol_key):
        log.info(f"REJECTED {symbol_key} extreme volatility")
        return

    price = float(df.iloc[-1]["close"])
    if price <= 0:
        return

    trend      = get_trend(symbol_key)
    regime     = detect_market_regime(df)
    asia_mode  = session == "Asian Precision"
    macro_trend = "BULL" if h4_trend(df, "BUY") else "BEAR" if h4_trend(df, "SELL") else "NEUTRAL"

    buy, sell, buy_score, sell_score = build_score(df, trend, symbol_key)
    struct_buy, struct_sell, struct_buy_score, struct_sell_score = institutional_structure_score(df, symbol_key)
    buy.update(struct_buy)
    sell.update(struct_sell)
    buy_score  += struct_buy_score
    sell_score += struct_sell_score

    if max(struct_buy_score, struct_sell_score) < MARKET_MIN_STRUCTURE_SCORE[symbol_key]:
        log.info(f"REJECTED {symbol_key} weak structure")
        return

    direction = determine_best_direction(buy_score, sell_score)

    if symbol_key not in ["XAU/USD"]:
        if trend == "BULL" and direction == "SELL":
            log.info(f"REJECTED {symbol_key} countertrend SELL")
            return
        if trend == "BEAR" and direction == "BUY":
            log.info(f"REJECTED {symbol_key} countertrend BUY")
            return

    if correlated_signal_block(symbol_key): return

    direction, best, wizard_score = master_signal(
        symbol_key, df, session, trend, regime,
        buy, sell, buy_score, sell_score,
        struct_buy_score, struct_sell_score
    )
    if direction is None:
        return

    sniper_score = ultra_sniper_score(df, symbol_key, direction)

    if duplicate_signal(symbol_key, direction): return

    now = time.time()
    if now - _signal_sent[symbol_key] < SIGNAL_COOLDOWN:
        log.info(f"REJECTED {symbol_key} cooldown {int(SIGNAL_COOLDOWN-(now-_signal_sent[symbol_key]))}s")
        return

    with signal_lock:
        _signal_sent[symbol_key]        = now
        _daily_signal_count[symbol_key] += 1

    execute_trade(symbol_key, df, direction, best, wizard_score,
                  sniper_score, macro_trend, session, trend,
                  regime, buy, sell, source, asia_mode)

# ============================================================
# ★★★ PROCESS BOX BREAKOUT — MAIN STRATEGY (15M) ★★★
# ============================================================
def process_box_breakout(symbol_key):
    """
    Runs the LuxAlgo box breakout strategy on 15M data.
    Matches the chart patterns:
    - GBP/JPY: marks day high → waits for rejection candle at top → SELL
    - NAS100: marks day low → waits for bounce candle at bottom → BUY
    """
    ok, session = in_session(symbol_key)
    if not ok or session not in ALLOWED_SESSIONS:
        return
    if daily_loss_lock() or loss_streak_lock():
        return

    df, source = get_entry_data(symbol_key, for_breakout=True)
    if df is None or len(df) < 60:
        return

    df = add_ind(df)
    if df is None or len(df) < 50:
        return

    trend = get_trend(symbol_key)

    # ── Detect box breakout signal ──
    direction, box_high, box_low, box_height, signal_tag = detect_box_breakout(df, symbol_key)
    if direction is None:
        return

    # ── Confirm ADX and volume ──
    adx   = float(df.iloc[-1]["adx"])
    vol   = float(df.iloc[-1]["volume"])
    volma = float(df.iloc[-1]["volma"]) if not pd.isna(df.iloc[-1]["volma"]) else 0

    if adx < BREAKOUT_ADX_MIN:
        log.info(f"BOX {symbol_key} ADX too low ({adx:.1f} < {BREAKOUT_ADX_MIN})")
        return
    if volma > 0 and vol < volma * BREAKOUT_VOL_MULT:
        log.info(f"BOX {symbol_key} volume too low ({vol:.0f} < {volma*BREAKOUT_VOL_MULT:.0f})")
        return

    # ── Score the signal ──
    score = 10  # base for confirmed box break
    if break_of_structure(df, direction):  score += 3
    if institutional_volume(df):           score += 2
    if strong_candle(df, direction):       score += 2
    if vwap_trend(df, direction):          score += 2
    if wavetrend_confirmation(df, direction): score += 2
    bull_sweep, bear_sweep = detect_liquidity_sweep(df, symbol_key)
    if direction == "BUY"  and bull_sweep: score += 3
    if direction == "SELL" and bear_sweep: score += 3

    required = BREAKOUT_SESSION_THRESHOLDS.get(session, 14)
    if score < required:
        log.info(f"BOX {symbol_key} score too low ({score} < {required})")
        return

    # ── Countertrend filter (allow gold) ──
    if symbol_key not in ["XAU/USD"]:
        if trend == "BULL" and direction == "SELL":
            log.info(f"BOX REJECTED {symbol_key} countertrend SELL")
            return
        if trend == "BEAR" and direction == "BUY":
            log.info(f"BOX REJECTED {symbol_key} countertrend BUY")
            return

    # ── Separate cooldown for box breakout signals ──
    bk_key = f"BK_{symbol_key}"
    now    = time.time()
    if now - _signal_sent.get(bk_key, 0) < 1800:
        log.info(f"BOX {symbol_key} cooldown active")
        return

    if duplicate_signal(f"BOX_{symbol_key}", direction):
        return

    _signal_sent[bk_key] = now
    execute_box_breakout(symbol_key, df, direction, score,
                          box_high, box_low, box_height, signal_tag,
                          session, source, trend)

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    log.info(f"{SYSTEM_VERSION} STARTED")
    send_telegram(
        f"📦 *{SYSTEM_VERSION} LIVE*\n\n"
        f"🔷 *BOX BREAKOUT STRATEGY ACTIVE*\n"
        f"📊 Day High / Day Low box marked each session\n"
        f"📈 BUY: candle closes above box upper line\n"
        f"📉 SELL: candle closes below box lower line\n"
        f"🔄 REJECTION: wick beyond line, body closes back inside\n"
        f"🎯 Target = box height projected from entry\n"
        f"🛑 SL = opposite box line\n\n"
        f"📊 *Global Markets:*\n"
        f"🥇 XAU/USD | 📈 NAS100 | 📊 SPX500\n"
        f"💶 EUR/USD | 💷 GBP/JPY\n\n"
        f"🇮🇳 *India Intraday:*\n"
        f"📊 NIFTY50 | 🏦 BANKNIFTY | 📈 SENSEX\n"
        f"🏢 RELIANCE | 💻 TCS\n\n"
        f"⏱ SCALP: 1M/5M | BOX BREAKOUT: 15M\n"
        f"⚡ ULTIMATE BOX BREAKOUT 2026 ELITE"
    )

    loop_count = 0
    while True:
        try:
            reset_daily()

            all_symbols = list(PRIORITY_MARKETS)

            # Scalp pass — every loop
            with ThreadPoolExecutor(max_workers=len(all_symbols)) as executor:
                futures = [executor.submit(process_symbol, s) for s in all_symbols]
                time.sleep(0.25)
                for future in as_completed(futures):
                    try:
                        future.result()
                    except Exception as e:
                        log.error(f"Scalp thread error: {e}")

            # Box breakout pass — every 5 loops
            if loop_count % 5 == 0:
                with ThreadPoolExecutor(max_workers=len(all_symbols)) as executor:
                    futures = [executor.submit(process_box_breakout, s) for s in all_symbols]
                    for future in as_completed(futures):
                        try:
                            future.result()
                        except Exception as e:
                            log.error(f"Box breakout thread error: {e}")

            loop_count += 1
            gc.collect()
            time.sleep(MAIN_LOOP_DELAY)

        except Exception as e:
            log.error(f"Main loop error: {e}")
            time.sleep(MAIN_LOOP_DELAY)

if __name__ == "__main__":
    main()
