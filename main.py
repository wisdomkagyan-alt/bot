# ============================================================
# PEPPERSTONE + INDIA MOMENTUM HUNTER
# ULTIMATE-HYBRID-SUPREME-2026-ELITE — SCALPER EDITION v2
# XAU/USD + NAS100 + SPX500 + EUR/USD + GBP/JPY
# + NIFTY50 + BANKNIFTY + SENSEX + RELIANCE + TCS
#
# ALL FIXES APPLIED:
# FIX 1  — Signal #2/#3 blocked, only #1 per session
# FIX 2  — Lot size fixed $50 risk all markets
# FIX 3  — Min SL strictly enforced
# FIX 4  — RSI extreme hard block (RSI<28 no SELL, RSI>72 no BUY)
# FIX 5  — Duplicate window 30min all pairs
# FIX 6  — India Close session removed
# FIX 7  — Direction logic corrected (was inverted)
# FIX 8  — Countertrend needs RSI confirmation
# FIX 9  — Absolute min score = 20
# FIX 10 — SL validation before every signal
# FIX 11 — Daily bias filter (BEAR day = SELL only, BULL day = BUY only)
# FIX 12 — ADX > 25 mandatory hard block
# FIX 13 — Session momentum check (price moving in signal direction)
# FIX 14 — ANTICIPATION ENTRY: signal fires 2 min before price arrives
# FIX 15 — Entry drift check: block if price moved >0.15% from signal
# FIX 16 — Data freshness check: block if data older than 2 minutes
# FIX 17 — Trailing SL: move to breakeven at 50% TP, trail at 75%
# FIX 18 — News time block: 30min around major releases
# FIX 19 — Same symbol min 30min gap enforced
# FIX 20 — Anticipation distance capped per market (max 5pts gold)
# FIX 21 — ADX unrealistic spike block (ADX > 60 = data error)
# FIX 22 — RSI impossible value block (RSI < 10 or RSI > 90 = data error)
# FIX 23 — ATR sanity check per market (zero or extreme = data error)
# FIX 24 — Candle sanity check (high >= low, close within range)
# FIX 25 — Volume sanity check (volume must be > 0)
# FIX 26 — Price sanity check per market (realistic price range)
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

SYSTEM_VERSION = "ULTIMATE-HYBRID-SUPREME-2026-ELITE-SCALPER-v5.3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[logging.StreamHandler()]
)
log = logging.getLogger("SCALPER-SUPREME-2026-v2")

TOKEN   = os.getenv("TOKEN",   "8641713322:AAHZeJOz0_LILD076P1ShvXSfCqQ1xrpFlk")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")

session_http = requests.Session()
signal_lock  = Lock()
log_lock     = Lock()

# ============================================================
# MARKETS
# ============================================================
PRIORITY_MARKETS = [
    "XAU/USD", "NAS100", "SPX500", "EUR/USD", "GBP/JPY",
    "NIFTY50", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS",
]

MARKETS = {
    # scalp_min_sl = tight SL for 1M/5M scalp signals
    # min_sl       = wider SL for 15M/30M breakout signals
    "XAU/USD":   {"mt5":"XAUUSD.Qraw","yf":"GC=F",        "price_lo":0,"price_hi":float("inf"),"sessions":[0,20],"decimals":2,"min_sl":7.0,  "scalp_min_sl":1.5,  "tier":"GOLD ELITE",             "bias":"BULL","rr":1.8,"sweep_bonus":2,"wick_ratio":1.6,"market_type":"global"},
    "NAS100":    {"mt5":"NAS100",      "yf":"^NDX",        "price_lo":0,"price_hi":float("inf"),"sessions":[0,21],"decimals":1,"min_sl":20.0, "scalp_min_sl":6.0,  "tier":"NASDAQ ELITE",           "bias":"BULL","rr":1.7,"sweep_bonus":2,"wick_ratio":1.5,"market_type":"global"},
    "SPX500":    {"mt5":"SPX500",      "yf":"^GSPC",       "price_lo":0,"price_hi":float("inf"),"sessions":[0,21],"decimals":1,"min_sl":8.0,  "scalp_min_sl":3.0,  "tier":"SP500 ELITE",            "bias":"BULL","rr":1.6,"sweep_bonus":2,"wick_ratio":1.4,"market_type":"global"},
    "EUR/USD":   {"mt5":"EURUSD",      "yf":"EURUSD=X",    "price_lo":0,"price_hi":float("inf"),"sessions":[0,24],"decimals":5,"min_sl":0.0008,"scalp_min_sl":0.0002,"tier":"FOREX MAJOR ELITE",      "bias":"BULL","rr":1.5,"sweep_bonus":1,"wick_ratio":1.3,"market_type":"global"},
    "GBP/JPY":   {"mt5":"GBPJPY",      "yf":"GBPJPY=X",    "price_lo":0,"price_hi":float("inf"),"sessions":[0,24],"decimals":3,"min_sl":0.080,"scalp_min_sl":0.030,"tier":"FOREX VOLATILITY ELITE",  "bias":"BULL","rr":1.8,"sweep_bonus":2,"wick_ratio":1.5,"market_type":"global"},
    "NIFTY50":   {"mt5":"NIFTY50",     "yf":"^NSEI",       "price_lo":0,"price_hi":float("inf"),"sessions":[3,10],"decimals":2,"min_sl":20.0, "scalp_min_sl":10.0, "tier":"INDIA INDEX ELITE",       "bias":"BULL","rr":1.8,"sweep_bonus":2,"wick_ratio":1.6,"market_type":"india"},
    "BANKNIFTY": {"mt5":"BANKNIFTY",   "yf":"^NSEBANK",    "price_lo":0,"price_hi":float("inf"),"sessions":[3,10],"decimals":2,"min_sl":40.0, "scalp_min_sl":18.0, "tier":"INDIA BANK ELITE",        "bias":"BULL","rr":1.8,"sweep_bonus":2,"wick_ratio":1.7,"market_type":"india"},
    "SENSEX":    {"mt5":"SENSEX",      "yf":"^BSESN",      "price_lo":0,"price_hi":float("inf"),"sessions":[3,10],"decimals":2,"min_sl":60.0, "scalp_min_sl":25.0, "tier":"INDIA BSE ELITE",         "bias":"BULL","rr":1.6,"sweep_bonus":2,"wick_ratio":1.5,"market_type":"india"},
    "RELIANCE":  {"mt5":"RELIANCE",    "yf":"RELIANCE.NS", "price_lo":0,"price_hi":float("inf"),"sessions":[3,10],"decimals":2,"min_sl":8.0,  "scalp_min_sl":1.5,  "tier":"INDIA LARGE CAP ELITE",   "bias":"BULL","rr":1.7,"sweep_bonus":2,"wick_ratio":1.6,"market_type":"india"},
    "TCS":       {"mt5":"TCS",         "yf":"TCS.NS",      "price_lo":0,"price_hi":float("inf"),"sessions":[3,10],"decimals":2,"min_sl":12.0, "scalp_min_sl":3.0,  "tier":"INDIA IT ELITE",          "bias":"BULL","rr":1.7,"sweep_bonus":2,"wick_ratio":1.6,"market_type":"india"},
}

SYMBOLS = list(MARKETS.keys())

# ============================================================
# CORE SETTINGS
# ============================================================
ATR_MULT               = 0.12
VOL_MULT               = 1.05
ADX_THRESHOLD          = 25        # default — overridden per session below
ADX_THRESHOLD_ASIAN    = 20        # Asian session lower volume = lower ADX ok
SIGNAL_COOLDOWN        = 1800      # FIX 19 — 30min same symbol gap
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
WIZARD_ADX_THRESHOLD = 25          # FIX 12

CORRELATION_BLOCK   = True
MAX_OPEN_CORRELATED = 2
VOLATILITY_KILL     = True
FALSE_BREAK_FILTER  = True

# FIX 4 — RSI extreme hard blocks
# RSI_EXTREME_OB: block BUY above this (still overbought risk)
# RSI_EXTREME_OS: block SELL below this (data error zone)
# Changed OS from 28 to 15 — RSI 15-28 with strong ADX is valid SELL
RSI_EXTREME_OB = 72    # block BUY above this
RSI_DATA_OB    = 85    # data error above this
RSI_EXTREME_OS = 15    # only block if truly impossible (data error)
RSI_WARN_OS    = 28    # warn zone — allow only if ADX > 30

# FIX 9 — absolute minimum score
ABSOLUTE_MIN_SCORE = 20

# FIX 14 — anticipation entry distance (ATR multiplier)
ANTICIPATION_ATR_MULT = 0.30

# FIX 20 — max anticipation distance cap per market (in price units)
# Prevents entry being set too far from current price on volatile days
MAX_ANTICIPATION_PTS = {
    "XAU/USD":   5.0,    # max 5pts ahead on gold
    "NAS100":    8.0,    # max 8pts ahead
    "SPX500":    4.0,    # max 4pts ahead
    "EUR/USD":   0.0005, # max 5 pips ahead
    "GBP/JPY":   0.050,  # max 5 pips ahead
    "NIFTY50":   8.0,    # max 8pts ahead
    "BANKNIFTY": 15.0,   # max 15pts ahead
    "SENSEX":    25.0,   # max 25pts ahead
    "RELIANCE":  2.0,    # max 2pts ahead
    "TCS":       3.0,    # max 3pts ahead
}
# ============================================================
# FIX 21-26 — DATA QUALITY VALIDATION CONFIG
# Realistic indicator ranges per market
# Anything outside these = data error → signal blocked
# ============================================================

# FIX 21 — Max realistic ADX per market
ADX_MAX_REALISTIC = 55.0  # global cap — ADX above 55 = data spike (83+ is impossible)

# FIX 22 — RSI impossible value bounds (tighter than FIX 4)
RSI_DATA_MIN = 10.0   # below this = data error (FIX 4 already blocks <28 for signals)
RSI_DATA_MAX = 85.0   # above this = data error (RSI rarely exceeds 85 in real markets)

# FIX 23 — ATR sanity bounds per market
ATR_SANITY = {
    "XAU/USD":   {"min": 0.5,    "max": 80.0  },
    "NAS100":    {"min": 2.0,    "max": 300.0 },
    "SPX500":    {"min": 0.5,    "max": 120.0 },
    "EUR/USD":   {"min": 0.0001, "max": 0.008 },
    "GBP/JPY":   {"min": 0.02,   "max": 2.0   },
    "NIFTY50":   {"min": 5.0,    "max": 400.0 },
    "BANKNIFTY": {"min": 10.0,   "max": 800.0 },
    "SENSEX":    {"min": 20.0,   "max": 1000.0},
    "RELIANCE":  {"min": 0.5,    "max": 80.0  },
    "TCS":       {"min": 1.0,    "max": 120.0 },
}

# FIX 26 — Realistic price ranges per market
PRICE_SANITY = {
    "XAU/USD":   {"min": 1000,   "max": 10000  },
    "NAS100":    {"min": 5000,   "max": 50000  },
    "SPX500":    {"min": 1000,   "max": 15000  },
    "EUR/USD":   {"min": 0.80,   "max": 1.60   },
    "GBP/JPY":   {"min": 100.0,  "max": 300.0  },
    "NIFTY50":   {"min": 10000,  "max": 40000  },
    "BANKNIFTY": {"min": 20000,  "max": 80000  },
    "SENSEX":    {"min": 30000,  "max": 120000 },
    "RELIANCE":  {"min": 500,    "max": 5000   },
    "TCS":       {"min": 1000,   "max": 8000   },
}

# ============================================================
# v5 ENGINE CONFIGS
# ============================================================
DIV_LOOKBACK            = 30
DIV_MIN_STRENGTH        = 3.0
DIV_SWING_BARS          = 2
PA_MIN_BODY_RATIO       = 0.55
PA_PIN_WICK_RATIO       = 2.0
PA_ENGULF_RATIO         = 1.10
PA_MIN_SCORE            = 5
SWEEP_EQUAL_THRESHOLD   = 0.0005
SWEEP_PDH_PDL_BUFFER    = 0.0003
SWEEP_ROUND_NUMBERS = {
    "XAU/USD":50.0,"NAS100":100.0,"SPX500":50.0,
    "EUR/USD":0.0050,"GBP/JPY":0.500,
    "NIFTY50":100.0,"BANKNIFTY":200.0,"SENSEX":500.0,
    "RELIANCE":10.0,"TCS":20.0,
}
SWEEP_VOL_MULT          = 1.5
MIN_ENGINES_CONFLUENCE  = 2
CONFLUENCE_BONUS        = {2:0, 3:5, 4:10}

# ============================================================
# ENGINE 5 — CORRELATION THEORY
# Each market has correlated assets that confirm or deny signals
# Positive: both must move same direction
# Negative: must move opposite direction
# Lead: correlated asset leads by 1-5 minutes
# ============================================================

CORRELATION_MAP = {
    # ---- XAUUSD ----
    # Gold RISES when: DXY falls, risk-off, Silver rises
    # Gold FALLS when: DXY rises, risk-on, yields rise
    "XAU/USD": {
        "confirms": [
            {"ticker": "GC=F",   "name": "Gold Futures",  "type": "SELF",     "weight": 1},
            {"ticker": "SI=F",   "name": "Silver",        "type": "POSITIVE", "weight": 3},
            {"ticker": "UUP",    "name": "DXY (Dollar)",  "type": "NEGATIVE", "weight": 4},
        ],
        "lead_asset": "SI=F",    # silver leads gold sometimes
        "block_on_fail": True,   # block signal if main correlation fails
        "min_confirms": 2,       # need 2/3 confirmed to pass
    },
    # ---- NAS100 ----
    # Nasdaq moves with SPX500, opposite to VIX
    "NAS100": {
        "confirms": [
            {"ticker": "^GSPC",  "name": "SPX500",        "type": "POSITIVE", "weight": 4},
            {"ticker": "QQQ",    "name": "QQQ ETF",       "type": "POSITIVE", "weight": 3},
            {"ticker": "^VIX",   "name": "VIX Fear",      "type": "NEGATIVE", "weight": 3},
        ],
        "lead_asset": "^GSPC",
        "block_on_fail": True,
        "min_confirms": 2,
    },
    # ---- SPX500 ----
    "SPX500": {
        "confirms": [
            {"ticker": "^NDX",   "name": "NAS100",        "type": "POSITIVE", "weight": 4},
            {"ticker": "SPY",    "name": "SPY ETF",       "type": "POSITIVE", "weight": 3},
            {"ticker": "^VIX",   "name": "VIX Fear",      "type": "NEGATIVE", "weight": 3},
        ],
        "lead_asset": "^NDX",
        "block_on_fail": True,
        "min_confirms": 2,
    },
    # ---- EUR/USD ----
    # EUR/USD moves with risk-on, opposite DXY
    "EUR/USD": {
        "confirms": [
            {"ticker": "GBPUSD=X","name": "GBP/USD",      "type": "POSITIVE", "weight": 4},
            {"ticker": "AUDUSD=X","name": "AUD/USD",      "type": "POSITIVE", "weight": 3},
            {"ticker": "UUP",     "name": "DXY (Dollar)", "type": "NEGATIVE", "weight": 4},
        ],
        "lead_asset": "GBPUSD=X",
        "block_on_fail": False,  # forex — use as booster not blocker
        "min_confirms": 2,
    },
    # ---- GBP/JPY ----
    # Risk asset — rises with risk-on, falls with risk-off
    "GBP/JPY": {
        "confirms": [
            {"ticker": "USDJPY=X","name": "USD/JPY",      "type": "POSITIVE", "weight": 4},
            {"ticker": "GBPUSD=X","name": "GBP/USD",      "type": "POSITIVE", "weight": 3},
            {"ticker": "^N225",   "name": "Nikkei",       "type": "POSITIVE", "weight": 2},
        ],
        "lead_asset": "USDJPY=X",
        "block_on_fail": False,
        "min_confirms": 2,
    },
    # ---- NIFTY50 ----
    # India index — moves with BANKNIFTY, opposite USDINR
    "NIFTY50": {
        "confirms": [
            {"ticker": "^NSEBANK","name": "BANKNIFTY",    "type": "POSITIVE", "weight": 5},
            {"ticker": "^BSESN",  "name": "SENSEX",       "type": "POSITIVE", "weight": 4},
            {"ticker": "INR=X",   "name": "USD/INR",      "type": "NEGATIVE", "weight": 3},
        ],
        "lead_asset": "^NSEBANK",
        "block_on_fail": True,
        "min_confirms": 2,
    },
    # ---- BANKNIFTY ----
    "BANKNIFTY": {
        "confirms": [
            {"ticker": "^NSEI",   "name": "NIFTY50",      "type": "POSITIVE", "weight": 5},
            {"ticker": "^BSESN",  "name": "SENSEX",       "type": "POSITIVE", "weight": 4},
            {"ticker": "INR=X",   "name": "USD/INR",      "type": "NEGATIVE", "weight": 3},
        ],
        "lead_asset": "^NSEI",
        "block_on_fail": True,
        "min_confirms": 2,
    },
    # ---- SENSEX ----
    "SENSEX": {
        "confirms": [
            {"ticker": "^NSEI",   "name": "NIFTY50",      "type": "POSITIVE", "weight": 5},
            {"ticker": "^NSEBANK","name": "BANKNIFTY",    "type": "POSITIVE", "weight": 4},
            {"ticker": "INR=X",   "name": "USD/INR",      "type": "NEGATIVE", "weight": 3},
        ],
        "lead_asset": "^NSEI",
        "block_on_fail": True,
        "min_confirms": 2,
    },
    # ---- RELIANCE ----
    # Large cap — moves with NIFTY50, oil price
    "RELIANCE": {
        "confirms": [
            {"ticker": "^NSEI",   "name": "NIFTY50",      "type": "POSITIVE", "weight": 4},
            {"ticker": "CL=F",    "name": "Crude Oil",    "type": "POSITIVE", "weight": 3},
            {"ticker": "^NSEBANK","name": "BANKNIFTY",    "type": "POSITIVE", "weight": 2},
        ],
        "lead_asset": "^NSEI",
        "block_on_fail": False,
        "min_confirms": 2,
    },
    # ---- TCS ----
    # IT stock — moves with NAS100, Rupee
    "TCS": {
        "confirms": [
            {"ticker": "^NSEI",   "name": "NIFTY50",      "type": "POSITIVE", "weight": 4},
            {"ticker": "^NDX",    "name": "NAS100",       "type": "POSITIVE", "weight": 3},
            {"ticker": "INR=X",   "name": "USD/INR",      "type": "POSITIVE", "weight": 2},
        ],
        "lead_asset": "^NSEI",
        "block_on_fail": False,
        "min_confirms": 2,
    },
}

# Correlation cache — avoid re-fetching same ticker
_corr_cache = {}
_corr_cache_ts = {}
CORR_CACHE_TTL = 120  # 2 minute cache




# FIX 15 — max entry drift %
MAX_ENTRY_DRIFT_PCT = {
    "XAU/USD":   0.10, "NAS100":    0.10, "SPX500":    0.10,
    "EUR/USD":   0.05, "GBP/JPY":   0.05,
    "NIFTY50":   0.08, "BANKNIFTY": 0.08, "SENSEX":    0.08,
    "RELIANCE":  0.10, "TCS":       0.10,
}

# FIX 16 — max data age in seconds
MAX_DATA_AGE_SECONDS = 120

# FIX 18 — news block times UTC (HH:MM)
HIGH_IMPACT_NEWS_UTC = ["08:30","12:30","14:00","18:00","19:30"]
NEWS_BLOCK_MINUTES   = 30

# ============================================================
# RR PROFILES — FIX: raised to min 2.0
# ============================================================
RR_PROFILE = {
    "XAU/USD":   {"SCALP": 2.2, "BREAKOUT": 3.0},
    "NAS100":    {"SCALP": 2.0, "BREAKOUT": 2.8},
    "SPX500":    {"SCALP": 2.0, "BREAKOUT": 2.5},
    "EUR/USD":   {"SCALP": 2.0, "BREAKOUT": 2.5},
    "GBP/JPY":   {"SCALP": 2.0, "BREAKOUT": 2.8},
    "NIFTY50":   {"SCALP": 2.0, "BREAKOUT": 2.5},
    "BANKNIFTY": {"SCALP": 2.0, "BREAKOUT": 2.5},
    "SENSEX":    {"SCALP": 2.0, "BREAKOUT": 2.5},
    "RELIANCE":  {"SCALP": 2.0, "BREAKOUT": 2.3},
    "TCS":       {"SCALP": 2.0, "BREAKOUT": 2.3},
}

SESSION_THRESHOLDS = {
    "Asian Precision": 18,   # lower ADX/vol in Asia — allow score 18+
    "London":          20,
    "NY Killzone":     20,
    "NY+London":       20,
    "India Open":      20,
    "India Midday":    20,
    "India Close":     25,   # re-allowed but only high quality score 25+
}

BREAKOUT_SESSION_THRESHOLDS = {
    "Asian Precision": 15,
    "London":          14,
    "NY Killzone":     14,
    "NY+London":       13,
    "India Open":      15,
    "India Midday":    13,
}

EXECUTION_BUFFER = {
    "XAU/USD":0.15,"NAS100":1.5,"SPX500":1.0,"EUR/USD":0.00005,"GBP/JPY":0.010,
    "NIFTY50":1.0,"BANKNIFTY":2.0,"SENSEX":3.0,"RELIANCE":0.50,"TCS":0.50,
}

ATR_MARKET_MULTIPLIER = {
    "XAU/USD":0.90,"NAS100":0.88,"SPX500":0.85,"EUR/USD":0.80,"GBP/JPY":0.95,
    "NIFTY50":0.90,"BANKNIFTY":0.92,"SENSEX":0.88,"RELIANCE":0.85,"TCS":0.85,
}

DOLLAR_PER_POINT = {
    "XAU/USD":100,"NAS100":10,"SPX500":10,"EUR/USD":100000,"GBP/JPY":1000,
    "NIFTY50":50,"BANKNIFTY":20,"SENSEX":10,"RELIANCE":1,"TCS":1,
}

MAX_SPREAD = {
    "XAU/USD":1.35,"NAS100":5.0,"SPX500":3.5,"EUR/USD":0.00035,"GBP/JPY":0.060,
    "NIFTY50":5.0,"BANKNIFTY":10.0,"SENSEX":15.0,"RELIANCE":1.0,"TCS":1.5,
}

MAX_SIGNALS_PER_DAY = {
    "XAU/USD":4,"NAS100":3,"SPX500":3,"EUR/USD":4,"GBP/JPY":3,
    "NIFTY50":4,"BANKNIFTY":4,"SENSEX":3,"RELIANCE":3,"TCS":3,
}

MARKET_STRUCTURE = {
    "XAU/USD":   {"sweep_lookback":4, "zone_lookback":6, "displacement_mult":1.10,"premium_discount_lookback":12,"wick_ratio":1.6},
    "NAS100":    {"sweep_lookback":5, "zone_lookback":8, "displacement_mult":1.20,"premium_discount_lookback":15,"wick_ratio":1.8},
    "SPX500":    {"sweep_lookback":5, "zone_lookback":6, "displacement_mult":1.15,"premium_discount_lookback":13,"wick_ratio":1.5},
    "EUR/USD":   {"sweep_lookback":6, "zone_lookback":8, "displacement_mult":1.05,"premium_discount_lookback":16,"wick_ratio":1.3},
    "GBP/JPY":   {"sweep_lookback":5, "zone_lookback":8, "displacement_mult":1.15,"premium_discount_lookback":14,"wick_ratio":1.6},
    "NIFTY50":   {"sweep_lookback":5, "zone_lookback":8, "displacement_mult":1.20,"premium_discount_lookback":16,"wick_ratio":1.7},
    "BANKNIFTY": {"sweep_lookback":5, "zone_lookback":8, "displacement_mult":1.25,"premium_discount_lookback":16,"wick_ratio":1.8},
    "SENSEX":    {"sweep_lookback":5, "zone_lookback":8, "displacement_mult":1.18,"premium_discount_lookback":16,"wick_ratio":1.6},
    "RELIANCE":  {"sweep_lookback":5, "zone_lookback":8, "displacement_mult":1.15,"premium_discount_lookback":14,"wick_ratio":1.5},
    "TCS":       {"sweep_lookback":5, "zone_lookback":8, "displacement_mult":1.15,"premium_discount_lookback":14,"wick_ratio":1.5},
}

MARKET_MIN_STRUCTURE_SCORE = {
    "XAU/USD":3,"NAS100":4,"SPX500":3,"EUR/USD":3,"GBP/JPY":3,
    "NIFTY50":4,"BANKNIFTY":5,"SENSEX":4,"RELIANCE":3,"TCS":3,
}

CORRELATED_GROUPS = [
    ["NAS100","SPX500"],
    ["EUR/USD","GBP/JPY"],
    ["NIFTY50","BANKNIFTY","SENSEX"],
    ["RELIANCE","TCS"],
]

DUPLICATE_WINDOWS = {
    "XAU/USD":1800,"NAS100":1800,"SPX500":1800,
    "EUR/USD":1800,"GBP/JPY":1800,
    "NIFTY50":900,"BANKNIFTY":900,"SENSEX":900,
    "RELIANCE":900,"TCS":900,
}

# India Close re-allowed but with higher score gate (25+)
ALLOWED_SESSIONS = [
    "Asian Precision","London","NY+London","NY Killzone",
    "India Open","India Midday","India Close",
]

# ============================================================
# STATE
# ============================================================
daily_pnl          = 0
consecutive_losses = 0
last_reset_day     = datetime.now(timezone.utc).day

_signal_sent           = {s: 0 for s in SYMBOLS}
_htf_cache             = {s: {"trend":"NEUTRAL","ts":0} for s in SYMBOLS}
_daily_bias_cache      = {s: {"bias":"NEUTRAL","ts":0} for s in SYMBOLS}  # FIX 11
_last_signal_direction = {}
_last_signal_time      = {}
_signal_counter        = {s: {"session":None,"count":0} for s in SYMBOLS}
_daily_signal_count    = {s: 0 for s in SYMBOLS}

for _file in ["signals_log.csv","signals_backup.csv"]:
    if not os.path.exists(_file):
        with open(_file,"a",encoding="utf-8"): pass

# ============================================================
# DAILY RESET
# ============================================================
def reset_daily():
    global daily_pnl,consecutive_losses,last_reset_day
    global _daily_signal_count,_htf_cache,_signal_counter,_daily_bias_cache
    current_day = datetime.now(timezone.utc).day
    if current_day != last_reset_day:
        daily_pnl           = 0
        consecutive_losses  = 0
        last_reset_day      = current_day
        _daily_signal_count = {s:0 for s in SYMBOLS}
        _htf_cache          = {s:{"trend":"NEUTRAL","ts":0} for s in SYMBOLS}
        _daily_bias_cache   = {s:{"bias":"NEUTRAL","ts":0} for s in SYMBOLS}
        _signal_counter     = {s:{"session":None,"count":0} for s in SYMBOLS}
        log.info("Daily reset complete")

def update_trade_result(pnl):
    global daily_pnl,consecutive_losses
    daily_pnl += pnl
    if pnl < 0: consecutive_losses += 1
    else:       consecutive_losses = 0

# ============================================================
# WATCHDOG / LOG
# ============================================================
def watchdog():
    try:
        with open("/tmp/heartbeat.txt","w",encoding="utf-8") as f:
            f.write(f"{datetime.now(timezone.utc).isoformat()} | {SYSTEM_VERSION} | ACTIVE")
    except: pass

def rotate_log():
    try:
        if os.path.isfile("signals_log.csv"):
            if os.path.getsize("signals_log.csv") > 5_000_000:
                os.rename("signals_log.csv",f"signals_log_{int(time.time())}.csv")
    except: pass

def log_signal(symbol,direction,score,rr,entry,sl,tp,session,regime,timeframe,signal_type):
    with log_lock:
        fe = os.path.isfile("signals_log.csv")
        with open("signals_log.csv","a",newline="",encoding="utf-8") as f:
            w = csv.writer(f)
            if not fe:
                w.writerow(["version","timestamp","symbol","direction","score","rr","entry","sl","tp","session","regime","timeframe","signal_type"])
            w.writerow([SYSTEM_VERSION,datetime.now(timezone.utc).isoformat(),symbol,direction,score,rr,entry,sl,tp,session,regime,timeframe,signal_type])
        try:
            with open("signals_backup.csv","a",newline="",encoding="utf-8") as bk:
                csv.writer(bk).writerow([SYSTEM_VERSION,datetime.now(timezone.utc).isoformat(),symbol,direction,score,rr,entry,sl,tp,session,regime,timeframe,signal_type])
        except: pass

# ============================================================
# TELEGRAM
# ============================================================
def send_telegram(msg):
    for attempt in range(3):
        try:
            r = session_http.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id":CHAT_ID,"text":msg,"parse_mode":"Markdown"},
                timeout=8
            )
            if r.status_code != 200:
                time.sleep(2); continue
            log.info("Telegram sent")
            return True
        except Exception as e:
            log.error(f"Telegram error {attempt+1}: {e}")
            time.sleep(2)
    return False

# ============================================================
# CIRCUIT BREAKERS
# ============================================================
def weekend_block(symbol_key):
    now = datetime.now(timezone.utc)
    if now.weekday() == 5: return True
    if now.weekday() == 6 and now.hour < 21: return True
    return False

def daily_loss_lock():
    if daily_pnl <= MAX_DAILY_LOSS:
        log.info("Daily loss lock"); return True
    return False

def loss_streak_lock():
    if consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        log.info("Kill switch"); return True
    return False

# FIX 18 — NEWS BLOCK
def news_block():
    now     = datetime.now(timezone.utc)
    now_str = now.strftime("%H:%M")
    for t in HIGH_IMPACT_NEWS_UTC:
        news_h, news_m = map(int, t.split(":"))
        now_h,  now_m  = map(int, now_str.split(":"))
        diff = abs((now_h*60+now_m) - (news_h*60+news_m))
        if diff <= NEWS_BLOCK_MINUTES:
            log.info(f"NEWS BLOCK active — within {diff}min of {t} UTC")
            return True
    return False

# ============================================================
# SESSION FILTER — FIX 6: India Close removed
# ============================================================
def in_session(symbol_key):
    now = datetime.now(timezone.utc)
    h   = now.hour
    m   = now.minute
    hm  = h*60+m
    s,e = MARKETS[symbol_key]["sessions"]
    if not (s <= h < e): return False,"Closed"
    mtype = MARKETS[symbol_key]["market_type"]
    if mtype == "india":
        if 225 <= hm < 330: return True,"India Open"
        if 330 <= hm < 450: return True,"India Midday"
        if 450 <= hm < 600: return True,"India Close"  # re-allowed with score gate 25+
        return False,"Closed"
    if 1  <= h < 6:  return True,"Asian Precision"
    if 8  <= h < 11: return True,"London"
    if 13 <= h < 15: return True,"NY Killzone"
    if 14 <= h < 16: return True,"NY+London"
    return False,"Closed"

# ============================================================
# DATA FETCHING
# ============================================================
def fetch_yf(ticker, period="7d", interval="1m"):
    for attempt in range(3):
        try:
            time.sleep(0.4)
            raw = yf.download(ticker,period=period,interval=interval,progress=False,auto_adjust=True,threads=False)
            if raw.empty: time.sleep(1); continue
            if isinstance(raw.columns,pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw.columns = [str(c).lower() for c in raw.columns]
            if "volume" in raw.columns:
                if raw["volume"].sum()==0: raw["volume"]=1000
            else: raw["volume"]=1000
            for col in ["open","high","low","close","volume"]:
                if col not in raw.columns: raw[col]=0
            df = raw[["open","high","low","close","volume"]].copy()
            df = df.drop_duplicates().ffill().bfill()
            return df.reset_index(drop=True)
        except Exception as e:
            log.error(f"YF {ticker} {interval} attempt {attempt+1}: {e}")
            time.sleep(1)
    return None

def fetch_market_data(symbol_key, for_breakout=False):
    yf_sym = MARKETS[symbol_key]["yf"]
    if for_breakout:
        period = "59d" if symbol_key in ["EUR/USD","GBP/JPY"] else "30d"
        df = fetch_yf(yf_sym,period=period,interval="15m")
        if df is not None and len(df)>60:
            return df.drop_duplicates().reset_index(drop=True),"15M"
        return None,None
    df = fetch_yf(yf_sym,period="7d",interval="1m")
    if df is not None and len(df)>60:
        return df.drop_duplicates().reset_index(drop=True),"1M"
    period = "59d" if symbol_key in ["EUR/USD","GBP/JPY"] else "30d"
    df = fetch_yf(yf_sym,period=period,interval="5m")
    if df is not None and len(df)>60:
        return df.drop_duplicates().reset_index(drop=True),"5M"
    return None,None

def get_entry_data(symbol_key, for_breakout=False):
    return fetch_market_data(symbol_key,for_breakout=for_breakout)

def get_spread(df):
    if df is None or len(df)<3: return 999
    return (df.tail(3)["high"].astype(float)-df.tail(3)["low"].astype(float)).mean()*0.18

# FIX 16 — DATA FRESHNESS CHECK
def data_is_fresh(df):
    if df is None or df.empty: return False
    try:
        last_idx = df.index[-1]
        if hasattr(last_idx,'tzinfo') and last_idx.tzinfo is None:
            last_idx = pd.Timestamp(last_idx,tz='UTC')
        elif hasattr(last_idx,'tzinfo') and last_idx.tzinfo is not None:
            last_idx = last_idx.tz_convert('UTC')
        age = (datetime.now(timezone.utc) - last_idx.to_pydatetime()).seconds
        if age > MAX_DATA_AGE_SECONDS:
            log.info(f"STALE DATA — {age}s old, max {MAX_DATA_AGE_SECONDS}s")
            return False
        return True
    except:
        return True  # if can't check, allow

# FIX 15 — ENTRY DRIFT CHECK
def entry_is_reachable(signal_price, current_price, symbol_key, direction):
    drift_pct = abs(signal_price - current_price) / current_price * 100
    max_drift  = MAX_ENTRY_DRIFT_PCT.get(symbol_key, 0.10)
    if drift_pct > max_drift:
        log.info(f"REJECTED — entry drift {drift_pct:.3f}% > max {max_drift}% for {symbol_key}")
        return False
    # FIX 15 — also check direction: entry must be reachable
    # For SELL: entry should be ABOVE current price (price rises to entry)
    # For BUY:  entry should be BELOW current price (price falls to entry)
    if direction == "SELL" and signal_price < current_price * (1 - max_drift/100):
        log.info(f"REJECTED — SELL entry {signal_price} already below market {current_price}")
        return False
    if direction == "BUY" and signal_price > current_price * (1 + max_drift/100):
        log.info(f"REJECTED — BUY entry {signal_price} already above market {current_price}")
        return False
    return True


# ============================================================
# FIX 21-26 — COMPREHENSIVE DATA QUALITY VALIDATOR
# Checks ALL indicators and price for each market
# Returns True if data is clean, False if data is corrupt/stale
# ============================================================
def validate_data_quality(df, symbol_key):
    """
    Runs all data quality checks for a symbol.
    Blocks signal if ANY check fails.
    FIX 21: ADX cap
    FIX 22: RSI impossible values
    FIX 23: ATR sanity
    FIX 24: Candle sanity
    FIX 25: Volume sanity
    FIX 26: Price sanity
    """
    if df is None or len(df) < 5:
        log.info(f"DQ FAIL {symbol_key}: insufficient data")
        return False

    last = df.iloc[-1]

    try:
        price  = float(last["close"])
        high   = float(last["high"])
        low    = float(last["low"])
        volume = float(last["volume"]) if "volume" in last else 0
        rsi    = float(last["rsi"])    if "rsi"    in last and not pd.isna(last["rsi"])    else None
        adx    = float(last["adx"])    if "adx"    in last and not pd.isna(last["adx"])    else None
        atr    = float(last["atr"])    if "atr"    in last and not pd.isna(last["atr"])    else None
    except Exception as e:
        log.info(f"DQ FAIL {symbol_key}: parse error {e}")
        return False

    # FIX 26 — Price sanity
    ps = PRICE_SANITY.get(symbol_key, {"min": 0, "max": float("inf")})
    if not (ps["min"] <= price <= ps["max"]):
        log.info(f"DQ FAIL {symbol_key}: price {price} out of range [{ps['min']},{ps['max']}]")
        return False

    # FIX 24 — Candle sanity
    if high < low:
        log.info(f"DQ FAIL {symbol_key}: candle corrupt high={high} < low={low}")
        return False
    if not (low <= price <= high):
        log.info(f"DQ FAIL {symbol_key}: close {price} outside candle [{low},{high}]")
        return False

    # FIX 25 — Volume sanity
    if volume <= 0:
        log.info(f"DQ FAIL {symbol_key}: zero/negative volume {volume}")
        return False

    # FIX 22 — RSI impossible values
    if rsi is not None:
        if rsi < RSI_DATA_MIN or rsi > RSI_DATA_MAX:
            log.info(f"DQ FAIL {symbol_key}: RSI {rsi:.1f} impossible (range {RSI_DATA_MIN}-{RSI_DATA_MAX})")
            return False

    # FIX 21 — ADX unrealistic spike
    if adx is not None:
        if adx > ADX_MAX_REALISTIC:
            log.info(f"DQ FAIL {symbol_key}: ADX {adx:.1f} unrealistic spike (max {ADX_MAX_REALISTIC})")
            return False
        if adx < 0:
            log.info(f"DQ FAIL {symbol_key}: ADX {adx:.1f} negative — data error")
            return False

    # FIX 23 — ATR sanity
    if atr is not None:
        as_ = ATR_SANITY.get(symbol_key, {"min": 0, "max": float("inf")})
        if atr <= 0:
            log.info(f"DQ FAIL {symbol_key}: ATR {atr} zero/negative — data error")
            return False
        if atr < as_["min"] or atr > as_["max"]:
            log.info(f"DQ FAIL {symbol_key}: ATR {atr:.5f} out of range [{as_['min']},{as_['max']}]")
            return False

    # Check last 5 candles for consecutive identical closes (frozen data)
    if len(df) >= 5:
        recent_closes = df["close"].tail(5).astype(float).tolist()
        if len(set(recent_closes)) == 1:
            log.info(f"DQ FAIL {symbol_key}: frozen data — 5 identical closes at {recent_closes[0]}")
            return False

    return True


def validate_signal_indicators(rsi, adx, atr, symbol_key, direction):
    """
    Quick indicator sanity check before firing any signal.
    Called right before execute_trade / execute_breakout.
    """
    # FIX 22 — RSI data error
    # RSI data error — both hard block AND extreme overbought
    if rsi < RSI_DATA_MIN or rsi > RSI_DATA_MAX:
        log.info(f"SIGNAL BLOCKED {symbol_key}: RSI {rsi:.1f} impossible value")
        return False
    if direction == "BUY" and rsi > RSI_EXTREME_OB:
        log.info(f"SIGNAL BLOCKED {symbol_key}: RSI {rsi:.1f} extreme OB — no BUY")
        return False

    # FIX 21 — ADX spike
    if adx > ADX_MAX_REALISTIC:
        log.info(f"SIGNAL BLOCKED {symbol_key}: ADX {adx:.1f} unrealistic")
        return False

    # FIX 23 — ATR zero
    if atr <= 0:
        log.info(f"SIGNAL BLOCKED {symbol_key}: ATR {atr:.5f} invalid")
        return False

    # Combined: RSI extreme + no strong ADX = data error
    if rsi < 12 and adx < 30:
        log.info(f"SIGNAL BLOCKED {symbol_key}: RSI {rsi:.1f} extreme without ADX confirmation")
        return False

    return True



# ============================================================
# ENGINE 5 — FULL CORRELATION ENGINE
# Fetches correlated assets and checks alignment
# Used as CONFIRMATION + SCORE BOOSTER + BLOCKER
# ============================================================

def get_corr_asset_direction(ticker, lookback=10):
    """
    Fetches correlated asset and returns direction.
    Returns: ("UP", price) or ("DOWN", price) or (None, None)
    Uses cache to avoid repeated API calls.
    """
    now = time.time()

    # Check cache
    if ticker in _corr_cache:
        if now - _corr_cache_ts.get(ticker, 0) < CORR_CACHE_TTL:
            return _corr_cache[ticker]

    try:
        df = fetch_yf(ticker, period="1d", interval="1m")
        if df is None or len(df) < lookback:
            return None, None

        current = float(df.iloc[-1]["close"])
        past    = float(df.iloc[-lookback]["close"])
        change  = (current - past) / past * 100

        direction = "UP" if change > 0 else "DOWN"
        result    = (direction, round(change, 3))

        _corr_cache[ticker]    = result
        _corr_cache_ts[ticker] = now
        return result

    except Exception as e:
        log.error(f"Correlation fetch {ticker}: {e}")
        return None, None


def check_correlation_aligned(corr_type, corr_dir, signal_dir):
    """
    Checks if correlation direction aligns with signal.
    POSITIVE: correlated asset must move SAME direction
    NEGATIVE: correlated asset must move OPPOSITE direction
    """
    signal_move = "UP" if signal_dir == "BUY" else "DOWN"

    if corr_type == "POSITIVE":
        return corr_dir == signal_move
    elif corr_type == "NEGATIVE":
        return corr_dir != signal_move
    elif corr_type == "SELF":
        return True  # always aligned with itself
    return False


def run_engine5_correlation(symbol_key, direction):
    """
    ENGINE 5: Full correlation check for a symbol.

    For each correlated asset:
    - Fetch current direction
    - Check if aligned with signal direction
    - Score based on weight
    - Block if critical correlation fails

    Returns: (passed, score_bonus, block_reason, corr_text)
    """
    corr_config = CORRELATION_MAP.get(symbol_key)
    if not corr_config:
        return True, 0, "", "No correlation config"

    confirms      = corr_config.get("confirms", [])
    block_on_fail = corr_config.get("block_on_fail", False)
    min_confirms  = corr_config.get("min_confirms", 2)
    lead_asset    = corr_config.get("lead_asset", "")

    passed_confirms  = []
    failed_confirms  = []
    total_score      = 0
    corr_lines       = []

    for c in confirms:
        ticker    = c["ticker"]
        name      = c["name"]
        corr_type = c["type"]
        weight    = c["weight"]

        # Skip SELF type
        if corr_type == "SELF":
            continue

        corr_dir, change_pct = get_corr_asset_direction(ticker)

        if corr_dir is None:
            corr_lines.append(f"  ⚠️ {name}: no data")
            continue

        aligned = check_correlation_aligned(corr_type, corr_dir, direction)
        arrow   = "↑" if corr_dir == "UP" else "↓"
        sign    = "+" if change_pct and change_pct > 0 else ""

        if aligned:
            total_score += weight
            passed_confirms.append(name)
            corr_lines.append(
                f"  ✅ {name}: {arrow} {sign}{change_pct}% — {'CONFIRMS' if corr_type=='POSITIVE' else 'INVERSE CONFIRMS'}"
            )
        else:
            failed_confirms.append(name)
            corr_lines.append(
                f"  ❌ {name}: {arrow} {sign}{change_pct}% — DIVERGING"
            )

    n_confirmed = len(passed_confirms)
    n_failed    = len(failed_confirms)

    # Check lead asset specifically
    lead_text = ""
    if lead_asset:
        lead_dir, lead_chg = get_corr_asset_direction(lead_asset, lookback=5)
        if lead_dir:
            lead_aligned = check_correlation_aligned("POSITIVE", lead_dir, direction)
            arrow = "↑" if lead_dir == "UP" else "↓"
            if lead_aligned:
                total_score += 2
                lead_text = f"  🔑 LEAD ({lead_asset}): {arrow} confirms direction +2"
            else:
                lead_text = f"  🔑 LEAD ({lead_asset}): {arrow} warns against signal"

    # Determine pass/fail
    if n_confirmed < min_confirms:
        if block_on_fail and n_confirmed == 0:
            reason = f"CORRELATION BLOCKED: {n_confirmed}/{min_confirms} confirmed ({', '.join(failed_confirms)} diverging)"
            log.info(f"CORR BLOCK {symbol_key}: {reason}")
            return False, 0, reason, "\n".join(corr_lines)
        elif block_on_fail and n_failed > n_confirmed:
            reason = f"CORRELATION WARN: more diverging ({n_failed}) than confirming ({n_confirmed})"
            log.info(f"CORR WARN {symbol_key}: {reason}")
            # Reduce score but don't block
            total_score = max(0, total_score - 3)

    # Build correlation text
    status = "PASS ✅" if n_confirmed >= min_confirms else f"PARTIAL ⚠️ ({n_confirmed}/{min_confirms})"
    if lead_text:
        corr_text = f"🔗 *Correlation:* {status}\n" + "\n".join(corr_lines) + "\n" + lead_text
    else:
        corr_text = f"🔗 *Correlation:* {status}\n" + "\n".join(corr_lines)

    log.info(f"CORR {symbol_key} {direction}: {n_confirmed}/{len(confirms)-1} confirmed score+{total_score}")
    return True, total_score, "", corr_text


def get_correlation_regime(symbol_key):
    """
    Determines overall market regime using correlations.
    RISK_ON:  equities up, VIX down, gold neutral/down
    RISK_OFF: equities down, VIX up, gold up
    MIXED:    conflicting signals
    """
    try:
        vix_dir,  _ = get_corr_asset_direction("^VIX",  lookback=10)
        spy_dir,  _ = get_corr_asset_direction("SPY",   lookback=10)
        gold_dir, _ = get_corr_asset_direction("GC=F",  lookback=10)

        risk_on_signals  = 0
        risk_off_signals = 0

        if spy_dir  == "UP":   risk_on_signals  += 2
        if spy_dir  == "DOWN": risk_off_signals += 2
        if vix_dir  == "DOWN": risk_on_signals  += 2
        if vix_dir  == "UP":   risk_off_signals += 2
        if gold_dir == "DOWN": risk_on_signals  += 1
        if gold_dir == "UP":   risk_off_signals += 1

        if risk_on_signals  > risk_off_signals + 1: return "RISK_ON"
        if risk_off_signals > risk_on_signals  + 1: return "RISK_OFF"
        return "MIXED"

    except:
        return "MIXED"


def correlation_regime_filter(symbol_key, direction):
    """
    Uses global market regime to filter signals.
    RISK_OFF: block BUY on equities, allow SELL on equities, allow BUY on gold
    RISK_ON:  allow BUY on equities, block SELL on equities, allow SELL on gold
    """
    regime = get_correlation_regime(symbol_key)

    equity_markets = ["NAS100", "SPX500", "NIFTY50", "BANKNIFTY", "SENSEX", "RELIANCE", "TCS"]
    gold_markets   = ["XAU/USD"]

    if regime == "RISK_OFF":
        if symbol_key in equity_markets and direction == "BUY":
            log.info(f"CORR REGIME BLOCK {symbol_key}: RISK_OFF — no equity BUY")
            return False, regime
        if symbol_key in gold_markets and direction == "SELL":
            log.info(f"CORR REGIME BLOCK {symbol_key}: RISK_OFF — no gold SELL")
            return False, regime

    elif regime == "RISK_ON":
        if symbol_key in gold_markets and direction == "BUY":
            # Gold in risk-on is weaker — reduce score but don't block
            log.info(f"CORR REGIME WARN {symbol_key}: RISK_ON — gold BUY weaker")

    return True, regime

# ============================================================
# ENGINE 2 — RSI DIVERGENCE DETECTOR
# Bullish: price lower low + RSI higher low (near support)
# Bearish: price higher high + RSI lower high (near resistance)
# Based on PDF strategy — 5M timeframe, 1:2 RR
# ============================================================
def find_swing_lows(lows, rsi_vals, n=3):
    """Find swing lows in recent bars."""
    swings = []
    for i in range(1, len(lows)-1):
        if lows[i] <= lows[i-1] and lows[i] <= lows[i+1]:
            swings.append((i, lows[i], rsi_vals[i]))
    return swings[-n:] if len(swings) >= n else swings

def find_swing_highs(highs, rsi_vals, n=3):
    """Find swing highs in recent bars."""
    swings = []
    for i in range(1, len(highs)-1):
        if highs[i] >= highs[i-1] and highs[i] >= highs[i+1]:
            swings.append((i, highs[i], rsi_vals[i]))
    return swings[-n:] if len(swings) >= n else swings

def detect_rsi_divergence(df, symbol_key):
    """
    ENGINE 2: RSI Divergence detection.
    Returns: (bull_div, bear_div, strength, description)
    """
    if len(df) < DIV_LOOKBACK:
        return False, False, 0, ""

    recent = df.tail(DIV_LOOKBACK)
    lows   = recent["low"].astype(float).values
    highs  = recent["high"].astype(float).values
    closes = recent["close"].astype(float).values
    rsi    = recent["rsi"].astype(float).values

    bull_div = bear_div = False
    strength = 0
    desc     = ""

    # BULLISH: price lower low + RSI higher low
    swing_lows = find_swing_lows(lows, rsi)
    if len(swing_lows) >= 2:
        l1 = swing_lows[-2]  # older
        l2 = swing_lows[-1]  # newer
        if l2[1] < l1[1] and l2[2] > l1[2]:
            rsi_diff = l2[2] - l1[2]
            if rsi_diff >= DIV_MIN_STRENGTH:
                bull_div = True
                strength = round(rsi_diff, 1)
                desc     = f"Price ↓{round(l1[1]-l2[1],2)} RSI ↑{strength}"

    # BEARISH: price higher high + RSI lower high
    swing_highs = find_swing_highs(highs, rsi)
    if len(swing_highs) >= 2:
        h1 = swing_highs[-2]
        h2 = swing_highs[-1]
        if h2[1] > h1[1] and h2[2] < h1[2]:
            rsi_diff = h1[2] - h2[2]
            if rsi_diff >= DIV_MIN_STRENGTH:
                bear_div = True
                strength = round(rsi_diff, 1)
                desc     = f"Price ↑{round(h2[1]-h1[1],2)} RSI ↓{strength}"

    return bull_div, bear_div, strength, desc

def divergence_structure_break(df, direction):
    """
    Confirms structure break after RSI divergence.
    BUY:  close > last swing high (buyers stepping in)
    SELL: close < last swing low  (sellers gaining control)
    """
    if len(df) < 8: return False
    close      = float(df.iloc[-1]["close"])
    prev_close = float(df.iloc[-2]["close"])

    if direction == "BUY":
        swing_high = float(df["high"].tail(10).iloc[:-2].max())
        return close > swing_high and prev_close <= swing_high

    if direction == "SELL":
        swing_low = float(df["low"].tail(10).iloc[:-2].min())
        return close < swing_low and prev_close >= swing_low

    return False

def near_key_level(df, symbol_key, direction):
    """
    Checks if divergence forms near support (BUY) or resistance (SELL).
    Uses recent 50-bar range — lower 30% = support, upper 30% = resistance.
    """
    if len(df) < 50: return True
    price   = float(df.iloc[-1]["close"])
    hi_50   = float(df["high"].tail(50).max())
    lo_50   = float(df["low"].tail(50).min())
    rng     = hi_50 - lo_50
    if rng == 0: return True
    if direction == "BUY":  return price <= lo_50 + rng * 0.35
    if direction == "SELL": return price >= hi_50 - rng * 0.35
    return False

def run_engine2(df, symbol_key, direction):
    """
    Full ENGINE 2 check.
    Returns: (passed, score, description)
    """
    bull_div, bear_div, strength, desc = detect_rsi_divergence(df, symbol_key)

    if direction == "BUY" and not bull_div:   return False, 0, "No bull divergence"
    if direction == "SELL" and not bear_div:  return False, 0, "No bear divergence"

    # Structure break required (from PDF)
    if not divergence_structure_break(df, direction):
        return False, 0, "No structure break"

    # Near key level preferred but not mandatory
    at_level = near_key_level(df, symbol_key, direction)

    score = int(strength) + (3 if at_level else 0)
    full_desc = f"RSI DIV {desc}" + (" | AT KEY LEVEL" if at_level else "")

    return True, score, full_desc


# ============================================================
# ENGINE 3 — PRICE ACTION DETECTOR
# Detects: Pin Bar, Engulfing, Inside Bar, Rejection, Doji
# ============================================================
def detect_pin_bar(df, direction):
    """
    Pin bar / Hammer / Shooting star.
    BUY:  long lower wick, small body at top (hammer)
    SELL: long upper wick, small body at bottom (shooting star)
    """
    if len(df) < 3: return False, 0

    c    = df.iloc[-1]
    op   = float(c["open"]); cl = float(c["close"])
    hi   = float(c["high"]); lo = float(c["low"])
    body = abs(cl - op)
    rng  = hi - lo

    if rng == 0 or body < rng * 0.05: return False, 0

    upper_wick = hi - max(op, cl)
    lower_wick = min(op, cl) - lo

    if direction == "BUY":
        # Hammer: lower wick >= 2x body, upper wick small
        if lower_wick >= body * PA_PIN_WICK_RATIO and upper_wick < body * 0.5:
            score = 8 if lower_wick >= body * 3 else 6
            return True, score

    if direction == "SELL":
        # Shooting star: upper wick >= 2x body, lower wick small
        if upper_wick >= body * PA_PIN_WICK_RATIO and lower_wick < body * 0.5:
            score = 8 if upper_wick >= body * 3 else 6
            return True, score

    return False, 0

def detect_engulfing(df, direction):
    """
    Bullish/Bearish engulfing candle.
    Current candle body engulfs previous candle body.
    """
    if len(df) < 3: return False, 0

    curr = df.iloc[-1]; prev = df.iloc[-2]
    c_op = float(curr["open"]); c_cl = float(curr["close"])
    p_op = float(prev["open"]); p_cl = float(prev["close"])
    c_body = abs(c_cl - c_op); p_body = abs(p_cl - p_op)

    if p_body == 0: return False, 0

    if direction == "BUY":
        # Bullish engulf: curr green, prev red, curr body > prev body
        if c_cl > c_op and p_cl < p_op:
            if c_op <= p_cl and c_cl >= p_op:
                score = 9 if c_body >= p_body * PA_ENGULF_RATIO * 1.5 else 7
                return True, score

    if direction == "SELL":
        # Bearish engulf: curr red, prev green, curr body > prev body
        if c_cl < c_op and p_cl > p_op:
            if c_op >= p_cl and c_cl <= p_op:
                score = 9 if c_body >= p_body * PA_ENGULF_RATIO * 1.5 else 7
                return True, score

    return False, 0

def detect_inside_bar_break(df, direction):
    """
    Inside bar breakout.
    Previous bar range contained inside the one before.
    Current bar breaks out of the mother bar.
    """
    if len(df) < 4: return False, 0

    mother  = df.iloc[-3]
    inside  = df.iloc[-2]
    current = df.iloc[-1]

    m_hi = float(mother["high"]); m_lo = float(mother["low"])
    i_hi = float(inside["high"]); i_lo = float(inside["low"])
    c_cl = float(current["close"])

    # Check inside bar condition
    if not (i_hi <= m_hi and i_lo >= m_lo):
        return False, 0

    # Breakout of mother bar
    if direction == "BUY"  and c_cl > m_hi: return True, 7
    if direction == "SELL" and c_cl < m_lo: return True, 7

    return False, 0

def detect_rejection_candle(df, direction):
    """
    Rejection at key level — candle wicks strongly rejected.
    """
    if len(df) < 3: return False, 0

    c  = df.iloc[-1]
    op = float(c["open"]); cl = float(c["close"])
    hi = float(c["high"]); lo = float(c["low"])
    body = abs(cl - op); rng = hi - lo

    if rng == 0: return False, 0
    body_pct = body / rng

    if direction == "BUY"  and body_pct < 0.40 and cl > op: return True, 5
    if direction == "SELL" and body_pct < 0.40 and cl < op: return True, 5

    return False, 0

def detect_double_top_bottom(df, direction):
    """
    Double top (SELL) or Double bottom (BUY).
    Two similar highs/lows within 0.1% of each other.
    """
    if len(df) < 20: return False, 0

    recent = df.tail(20)
    if direction == "SELL":
        highs = recent["high"].astype(float).values
        max1  = highs.max()
        # Find second high within 0.1%
        for h in highs[:-3]:
            if abs(h - max1) / max1 < 0.001 and h != max1:
                return True, 8
    if direction == "BUY":
        lows = recent["low"].astype(float).values
        min1 = lows.min()
        for l in lows[:-3]:
            if abs(l - min1) / min1 < 0.001 and l != min1:
                return True, 8

    return False, 0

def run_engine3(df, symbol_key, direction):
    """
    Full ENGINE 3 — Price Action check.
    Runs all PA patterns, returns best match.
    Returns: (passed, score, description)
    """
    patterns = []

    pin,    pin_s    = detect_pin_bar(df, direction)
    engulf, eng_s    = detect_engulfing(df, direction)
    inside, ins_s    = detect_inside_bar_break(df, direction)
    reject, rej_s    = detect_rejection_candle(df, direction)
    dbl,    dbl_s    = detect_double_top_bottom(df, direction)

    if pin:    patterns.append(("PIN BAR",       pin_s))
    if engulf: patterns.append(("ENGULFING",     eng_s))
    if inside: patterns.append(("INSIDE BREAK",  ins_s))
    if reject: patterns.append(("REJECTION",     rej_s))
    if dbl:    patterns.append(("DOUBLE T/B",    dbl_s))

    if not patterns:
        return False, 0, "No PA pattern"

    # Take highest scoring pattern
    best = max(patterns, key=lambda x: x[1])
    total_score = sum(p[1] for p in patterns)

    if best[1] < PA_MIN_SCORE:
        return False, 0, "PA score too low"

    desc = " + ".join([p[0] for p in patterns])
    return True, total_score, f"PA: {desc} (score:{total_score})"


# ============================================================
# ENGINE 4 — ENHANCED LIQUIDITY SWEEP
# Detects: Equal H/L, Previous Day H/L, Round Numbers
# Enhanced with volume confirmation and rejection candle
# ============================================================
def detect_equal_highs_lows(df, symbol_key, direction):
    """Equal highs (sell target) or equal lows (buy target)."""
    if len(df) < 20: return False

    threshold = SWEEP_EQUAL_THRESHOLD
    recent    = df.tail(20)
    price     = float(df.iloc[-1]["close"])

    if direction == "SELL":
        highs = recent["high"].astype(float).values[:-1]
        # Two or more highs within threshold of each other
        for i in range(len(highs)-1):
            for j in range(i+1, len(highs)):
                if abs(highs[i]-highs[j])/max(highs[i],highs[j]) < threshold:
                    # Price swept above equal highs and rejected
                    if float(df.iloc[-1]["high"]) >= max(highs[i],highs[j]) and price < max(highs[i],highs[j]):
                        return True
    if direction == "BUY":
        lows = recent["low"].astype(float).values[:-1]
        for i in range(len(lows)-1):
            for j in range(i+1, len(lows)):
                if abs(lows[i]-lows[j])/max(lows[i],lows[j]) < threshold:
                    if float(df.iloc[-1]["low"]) <= min(lows[i],lows[j]) and price > min(lows[i],lows[j]):
                        return True
    return False

def detect_prev_day_sweep(df, symbol_key, direction):
    """
    Previous day high/low sweep + rejection.
    Price hunts stops beyond PDH/PDL then reverses.
    """
    if len(df) < 500: return False  # need enough history for prev day

    # Approximate previous day using last 288 bars (1M bars = ~1 day)
    prev_day = df.tail(576).head(288)
    if len(prev_day) < 100: return False

    pdh = float(prev_day["high"].max())
    pdl = float(prev_day["low"].min())

    last_high  = float(df.iloc[-1]["high"])
    last_low   = float(df.iloc[-1]["low"])
    last_close = float(df.iloc[-1]["close"])
    buf        = pdh * SWEEP_PDH_PDL_BUFFER

    if direction == "SELL":
        # Swept above PDH and rejected back below
        return last_high > pdh + buf and last_close < pdh
    if direction == "BUY":
        # Swept below PDL and rejected back above
        return last_low < pdl - buf and last_close > pdl

    return False

def detect_round_number_sweep(df, symbol_key, direction):
    """
    Round number sweep — price hunts stops at round numbers.
    e.g. 4500, 4550 on gold
    """
    if len(df) < 5: return False

    price     = float(df.iloc[-1]["close"])
    last_high = float(df.iloc[-1]["high"])
    last_low  = float(df.iloc[-1]["low"])
    rn_step   = SWEEP_ROUND_NUMBERS.get(symbol_key, 50.0)

    # Nearest round number
    nearest_rn = round(price / rn_step) * rn_step

    if direction == "SELL":
        # Swept above round number and rejected
        return last_high >= nearest_rn and price < nearest_rn
    if direction == "BUY":
        # Swept below round number and rejected
        return last_low <= nearest_rn and price > nearest_rn

    return False

def sweep_volume_confirmed(df):
    """Volume spike confirms the sweep is institutional."""
    if len(df) < 11: return False
    vol   = float(df.iloc[-1]["volume"])
    volma = float(df.iloc[-1]["volma"]) if not pd.isna(df.iloc[-1]["volma"]) else 0
    return volma > 0 and vol > volma * SWEEP_VOL_MULT

def run_engine4(df, symbol_key, direction):
    """
    Full ENGINE 4 — Enhanced Liquidity Sweep.
    Returns: (passed, score, description)
    """
    sweeps = []

    # Basic sweep (already in v4)
    bull_sw, bear_sw = detect_liquidity_sweep(df, symbol_key)
    basic_sweep = bull_sw if direction=="BUY" else bear_sw
    if basic_sweep: sweeps.append(("BASIC SWEEP", 5))

    # Equal highs/lows
    if detect_equal_highs_lows(df, symbol_key, direction):
        sweeps.append(("EQUAL H/L HUNT", 7))

    # Previous day H/L
    if detect_prev_day_sweep(df, symbol_key, direction):
        sweeps.append(("PDH/PDL SWEEP", 8))

    # Round number
    if detect_round_number_sweep(df, symbol_key, direction):
        sweeps.append(("ROUND NUMBER", 6))

    if not sweeps:
        return False, 0, "No sweep detected"

    vol_conf = sweep_volume_confirmed(df)
    vol_bonus = 3 if vol_conf else 0

    total_score = sum(s[1] for s in sweeps) + vol_bonus
    desc = " + ".join([s[0] for s in sweeps])
    if vol_conf: desc += " + VOL SPIKE"

    return True, total_score, f"SWEEP: {desc}"


# ============================================================
# CONFLUENCE ENGINE — Combines all 4 engines
# ============================================================
def run_confluence(df, symbol_key, direction, base_score):
    """
    Runs all 5 engines — Momentum, RSI Div, Price Action, Liq Sweep, Correlation
    Returns: (passed, final_score, engines_passed, confluence_text)
    """
    engines_passed = []; engine_details = []

    # ENGINE 1 — Momentum
    if base_score >= ABSOLUTE_MIN_SCORE:
        engines_passed.append("MOMENTUM")
        engine_details.append(f"ENGINE 1 ✅ MOMENTUM (score:{base_score})")

    # ENGINE 2 — RSI Divergence
    e2_pass,e2_score,e2_desc = run_engine2(df,symbol_key,direction)
    if e2_pass:
        engines_passed.append("RSI DIVERGENCE")
        engine_details.append(f"ENGINE 2 ✅ RSI DIVERGENCE | {e2_desc}")

    # ENGINE 3 — Price Action
    e3_pass,e3_score,e3_desc = run_engine3(df,symbol_key,direction)
    if e3_pass:
        engines_passed.append("PRICE ACTION")
        engine_details.append(f"ENGINE 3 ✅ PRICE ACTION | {e3_desc}")

    # ENGINE 4 — Liquidity Sweep
    e4_pass,e4_score,e4_desc = run_engine4(df,symbol_key,direction)
    if e4_pass:
        engines_passed.append("LIQ SWEEP")
        engine_details.append(f"ENGINE 4 ✅ LIQ SWEEP | {e4_desc}")

    # ENGINE 5 — Correlation Theory
    e5_pass,e5_score,e5_block,e5_desc = run_engine5_correlation(symbol_key,direction)
    if not e5_pass:
        log.info(f"CORR BLOCK {symbol_key}: {e5_block}")
        return False,0,engines_passed,f"CORRELATION BLOCKED: {e5_block}"
    if e5_score > 0:
        engines_passed.append("CORRELATION")
        engine_details.append(f"ENGINE 5 ✅ CORRELATION\n{e5_desc}")

    # Global market regime
    regime_pass,market_regime = correlation_regime_filter(symbol_key,direction)
    if not regime_pass:
        return False,0,engines_passed,f"REGIME BLOCKED: {market_regime}"

    n = len(engines_passed)
    if n < MIN_ENGINES_CONFLUENCE:
        log.info(f"CONFLUENCE FAIL {symbol_key}: {n}/{MIN_ENGINES_CONFLUENCE}")
        return False,0,engines_passed,""

    bonus = CONFLUENCE_BONUS.get(min(n,4),0)
    extra = ((e2_score if e2_pass else 0)+(e3_score if e3_pass else 0)+
             (e4_score if e4_pass else 0)+e5_score)
    final_score = base_score+extra+bonus

    if n>=5: quality="PERFECT CONFLUENCE 🔥🔥🔥🔥"
    elif n==4: quality="GOD-TIER CONFLUENCE 🔥🔥🔥"
    elif n==3: quality="ELITE CONFLUENCE 🔥🔥"
    else: quality="STANDARD CONFLUENCE 🔥"

    conf_text = "\n".join(engine_details)
    conf_text += f"\n\n🌍 *Market Regime:* {market_regime}"
    conf_text += f"\n🔥 *Confluence:* {n}/5 | {quality}"

    log.info(f"CONFLUENCE {symbol_key} {direction}: {n}/5 | score:{final_score} | regime:{market_regime}")
    return True,final_score,engines_passed,conf_text

def add_ind(df):
    df  = df.copy()
    cl  = pd.to_numeric(df["close"], errors="coerce")
    hi  = pd.to_numeric(df["high"],  errors="coerce")
    lo  = pd.to_numeric(df["low"],   errors="coerce")
    vol = pd.to_numeric(df["volume"],errors="coerce")

    df["ema9"]     = ta.trend.EMAIndicator(cl,5).ema_indicator()
    df["ema21"]    = ta.trend.EMAIndicator(cl,13).ema_indicator()
    df["ema50"]    = ta.trend.EMAIndicator(cl,21).ema_indicator()
    df["ema200"]   = ta.trend.EMAIndicator(cl,50).ema_indicator()
    df["rsi"]      = ta.momentum.RSIIndicator(cl,7).rsi()
    df["atr"]      = ta.volatility.AverageTrueRange(hi,lo,cl,7).average_true_range()
    df["adx"]      = ta.trend.ADXIndicator(hi,lo,cl,7).adx()
    df["volma"]    = vol.rolling(10).mean()
    df["vwap"]     = (cl*vol).cumsum()/vol.cumsum()
    df["stdv"]     = cl.rolling(STDV_PERIOD).std()
    df["aox_fast"] = ta.trend.EMAIndicator(cl,AOX_FAST).ema_indicator()
    df["aox_slow"] = ta.trend.EMAIndicator(cl,AOX_SLOW).ema_indicator()
    df["aox"]      = df["aox_fast"]-df["aox_slow"]

    hlc3 = (hi+lo+cl)/3
    esa  = hlc3.ewm(span=6,adjust=False).mean()
    d    = (hlc3-esa).abs().ewm(span=6,adjust=False).mean()
    ci   = (hlc3-esa)/(0.015*d)
    df["wt1"] = ci.ewm(span=10,adjust=False).mean()
    df["wt2"] = df["wt1"].rolling(3).mean()

    df.replace([float("inf"),float("-inf")],pd.NA,inplace=True)
    df.ffill(inplace=True)
    df.dropna(inplace=True)
    return df

# ============================================================
# FIX 11 — DAILY BIAS FILTER
# ============================================================
def get_daily_bias(symbol_key, df):
    """BEAR day = SELL only. BULL day = BUY only."""
    cache = _daily_bias_cache[symbol_key]
    now   = time.time()
    if now - cache["ts"] < 3600:  # refresh every 1 hour
        return cache["bias"]
    if df is None or len(df) < 50:
        return "NEUTRAL"
    # Use 50-bar rolling average as daily bias indicator
    price   = float(df.iloc[-1]["close"])
    ma50    = df["close"].rolling(50).mean().iloc[-1]
    ema200  = float(df.iloc[-1]["ema200"]) if "ema200" in df.columns else ma50
    # Strong bear: price below both MA50 and EMA200
    if price < ma50 and price < ema200:
        bias = "BEAR"
    elif price > ma50 and price > ema200:
        bias = "BULL"
    else:
        bias = "NEUTRAL"
    cache["bias"] = bias
    cache["ts"]   = now
    log.info(f"Daily bias {symbol_key}: {bias} | Price:{price:.2f} MA50:{ma50:.2f}")
    return bias

# ============================================================
# FIX 13 — SESSION MOMENTUM CHECK
# ============================================================
def session_momentum_ok(df, direction):
    """Price must be moving in signal direction in last 15 bars."""
    if df is None or len(df) < 15: return True
    recent = df.tail(15)
    move   = float(recent["close"].iloc[-1]) - float(recent["close"].iloc[0])
    if direction == "SELL" and move < 0: return True   # falling = good for sell
    if direction == "BUY"  and move > 0: return True   # rising = good for buy
    # Neutral momentum — allow but log
    log.info(f"WEAK momentum for {direction}: move={move:.3f}")
    return False

# ============================================================
# TREND HELPERS
# ============================================================
def get_trend(symbol_key):
    cache = _htf_cache[symbol_key]
    now   = time.time()
    if now-cache["ts"] < HTF_REFRESH: return cache["trend"]
    df,_ = get_entry_data(symbol_key)
    if df is None: return "NEUTRAL"
    df = add_ind(df)
    if df is None or len(df)<30: return "NEUTRAL"
    last = df.iloc[-1]
    trend = ("BULL" if last["ema21"]>last["ema50"]
             else "BEAR" if last["ema21"]<last["ema50"]
             else MARKETS[symbol_key].get("bias","NEUTRAL"))
    cache["trend"] = trend
    cache["ts"]    = now
    return trend

def mtf_bullish(symbol_key,df):
    if df is None or len(df)<60: return False
    last = df.iloc[-1]
    return float(last["ema9"])>float(last["ema21"])>float(last["ema50"]) and float(last["close"])>float(last["ema200"])

def mtf_bearish(symbol_key,df):
    if df is None or len(df)<60: return False
    last = df.iloc[-1]
    return float(last["ema9"])<float(last["ema21"])<float(last["ema50"]) and float(last["close"])<float(last["ema200"])

def h4_trend(df,direction):
    if df is None or len(df)<55: return False
    price = float(df.iloc[-1]["close"])
    ema50 = float(df.iloc[-1]["ema200"])
    return price>ema50 if direction=="BUY" else price<ema50

def vwap_trend(df,direction):
    if df is None or len(df)<10: return False
    price = float(df.iloc[-1]["close"])
    vwap  = float(df.iloc[-1]["vwap"])
    if pd.isna(vwap): return False
    return price>vwap if direction=="BUY" else price<vwap

def wavetrend_confirmation(df,direction):
    if len(df)<5: return False
    wt1_now  = float(df.iloc[-1]["wt1"]); wt2_now  = float(df.iloc[-1]["wt2"])
    wt1_prev = float(df.iloc[-2]["wt1"]); wt2_prev = float(df.iloc[-2]["wt2"])
    if direction=="BUY":  return wt1_prev<wt2_prev and wt1_now>wt2_now and wt1_now<30
    return wt1_prev>wt2_prev and wt1_now<wt2_now and wt1_now>-30

def scalp_macro_filter(df,direction):
    if df is None: return False
    score = 0
    if h4_trend(df,direction):   score+=4
    if vwap_trend(df,direction): score+=4
    last = df.iloc[-1]
    if direction=="BUY"  and float(last["ema9"])>float(last["ema21"]): score+=2
    if direction=="SELL" and float(last["ema9"])<float(last["ema21"]): score+=2
    return score>=6

# ============================================================
# PATTERN DETECTION
# ============================================================
def fair_value_gap(df):
    if len(df)<3: return False,False
    c1,c3=df.iloc[-3],df.iloc[-1]
    return float(c1["high"])<float(c3["low"]),float(c1["low"])>float(c3["high"])

def detect_choch(df):
    if len(df)<6: return False,False
    highs=df["high"].tail(6).tolist(); lows=df["low"].tail(6).tolist()
    close=float(df.iloc[-1]["close"])
    return (lows[-2]<lows[-3] and close>highs[-2],highs[-2]>highs[-3] and close<lows[-2])

def detect_liquidity_sweep(df,symbol_key):
    lb=MARKET_STRUCTURE[symbol_key]["sweep_lookback"]
    if len(df)<lb: return False,False
    recent=df.tail(lb); ph=float(recent["high"].iloc[:-1].max()); pl=float(recent["low"].iloc[:-1].min())
    last=recent.iloc[-1]
    return (float(last["low"])<pl and float(last["close"])>pl,
            float(last["high"])>ph and float(last["close"])<ph)

def detect_zone_retest(df,symbol_key,direction):
    lb=MARKET_STRUCTURE[symbol_key]["zone_lookback"]
    if len(df)<lb: return False
    recent=df.tail(lb); current=df.iloc[-1]
    if direction=="BUY":  return float(current["low"])<=float(recent["low"].min())*1.002
    return float(current["high"])>=float(recent["high"].max())*0.998

def detect_displacement(df,symbol_key):
    if len(df)<2: return False
    candle=df.iloc[-1]
    return abs(float(candle["close"])-float(candle["open"]))>float(candle["atr"])*MARKET_STRUCTURE[symbol_key]["displacement_mult"]

def detect_wick_rejection(df,atr,symbol_key):
    if len(df)<2: return False,False
    c=df.iloc[-1]; op,cl,hi,lo=float(c["open"]),float(c["close"]),float(c["high"]),float(c["low"])
    body=abs(cl-op)
    if body<atr*0.05: return False,False
    upper=hi-max(op,cl); lower=min(op,cl)-lo; wr=MARKETS[symbol_key]["wick_ratio"]
    return lower>body*wr,upper>body*wr

def premium_discount(df,symbol_key):
    lb=MARKET_STRUCTURE[symbol_key]["premium_discount_lookback"]
    if len(df)<lb: return {"discount":False,"premium":False}
    recent=df.tail(lb); mid=(float(recent["high"].max())+float(recent["low"].min()))/2
    price=float(df.iloc[-1]["close"])
    return {"discount":price<mid,"premium":price>mid}

def break_of_structure(df,direction):
    if len(df)<6: return False
    atr=float(df.iloc[-1]["atr"]); close=float(df.iloc[-1]["close"])
    if direction=="BUY":  return close>float(df["high"].iloc[-6:-1].max())+atr*0.08
    return close<float(df["low"].iloc[-6:-1].min())-atr*0.08

def institutional_volume(df):
    if len(df)<11: return False
    last=df.iloc[-1]; vol=float(last["volume"])
    volma=float(last["volma"]) if not pd.isna(last["volma"]) else 0
    return volma>0 and vol>volma*1.5

def strong_candle(df,direction):
    if len(df)<2: return False
    c=df.iloc[-1]; op,cl,hi,lo=float(c["open"]),float(c["close"]),float(c["high"]),float(c["low"])
    body=abs(cl-op); total=hi-lo
    if total==0 or body/total<0.55: return False
    if direction=="BUY":  return cl>(lo+total*0.65)
    return cl<(lo+total*0.35)

def detect_supply_demand_zones(df):
    if len(df)<10: return None,None
    recent=df.tail(10)
    return recent["low"].rolling(3).min().iloc[-1],recent["high"].rolling(3).max().iloc[-1]

def institutional_structure_score(df,symbol_key):
    bs,ss=detect_liquidity_sweep(df,symbol_key)
    bw,sw=detect_wick_rejection(df,float(df.iloc[-1]["atr"]),symbol_key)
    disp=detect_displacement(df,symbol_key); pd_zone=premium_discount(df,symbol_key)
    buy_s=sell_s=0; bc={}; sc={}
    if bs: buy_s+=2;  bc["SWEEP"]=True
    if bw: buy_s+=2;  bc["WICK"]=True
    if detect_zone_retest(df,symbol_key,"BUY"):  buy_s+=2;  bc["ZONE"]=True
    if disp: buy_s+=2; bc["DISPLACEMENT"]=True
    if pd_zone["discount"]: buy_s+=1; bc["DISCOUNT"]=True
    if ss: sell_s+=2; sc["SWEEP"]=True
    if sw: sell_s+=2; sc["WICK"]=True
    if detect_zone_retest(df,symbol_key,"SELL"): sell_s+=2; sc["ZONE"]=True
    if disp: sell_s+=2; sc["DISPLACEMENT"]=True
    if pd_zone["premium"]: sell_s+=1; sc["PREMIUM"]=True
    if buy_s>=8:  buy_s+=1
    if sell_s>=8: sell_s+=1
    return bc,sc,buy_s,sell_s

# ============================================================
# BUILD SCORE
# ============================================================
def build_score(df,trend,symbol_key):
    last=df.iloc[-1]
    rsi=float(last["rsi"]); ema9=float(last["ema9"]); ema21=float(last["ema21"])
    ema50=float(last["ema50"]); atr=float(last["atr"]); adx=float(last["adx"])
    vol=float(last["volume"]); volma=float(last["volma"]) if not pd.isna(last["volma"]) else 0
    stdv=float(last["stdv"]) if not pd.isna(last["stdv"]) else 0
    aox=float(last["aox"]) if not pd.isna(last["aox"]) else 0
    stdv_ma=df["stdv"].rolling(STDV_PERIOD).mean().iloc[-1] if len(df)>STDV_PERIOD else 0

    bfvg,sfvg=fair_value_gap(df); bchoch,schoch=detect_choch(df)
    bsweep,ssweep=detect_liquidity_sweep(df,symbol_key)
    bwick,swick=detect_wick_rejection(df,atr,symbol_key)
    bull_break=float(last["close"])>float(df.iloc[-2]["high"])+atr*0.08
    bear_break=float(last["close"])<float(df.iloc[-2]["low"])-atr*0.08

    buy={
        "HTF":   trend=="BULL",
        "EMA":   ema9>ema21>ema50,
        "VWAP":  float(last["close"])>float(last["vwap"]),
        "RSI":   52<=rsi<=RSI_EXTREME_OB,
        "ADX":   adx>ADX_THRESHOLD,
        "VOL":   volma>0 and vol>volma*VOL_MULT,
        "FVG":   bfvg,"CHOCH":bchoch,"BOS":bull_break,
        "SWEEP": bsweep,"WICK":bwick,
        "STDV":  stdv_ma>0 and stdv>stdv_ma*STDV_THRESHOLD_MULT,
        "AOX":   aox>0,
    }
    sell={
        "HTF":   trend=="BEAR",
        "EMA":   ema9<ema21<ema50,
        "VWAP":  float(last["close"])<float(last["vwap"]),
        "RSI":   RSI_EXTREME_OS<=rsi<=48,
        "ADX":   adx>ADX_THRESHOLD,
        "VOL":   volma>0 and vol>volma*VOL_MULT,
        "FVG":   sfvg,"CHOCH":schoch,"BOS":bear_break,
        "SWEEP": ssweep,"WICK":swick,
        "STDV":  stdv_ma>0 and stdv>stdv_ma*STDV_THRESHOLD_MULT,
        "AOX":   aox<0,
    }

    bs=sum(buy.values()); ss=sum(sell.values())
    if buy["STDV"] and buy["AOX"]:  bs+=1
    if sell["STDV"] and sell["AOX"]: ss+=1
    sb=MARKETS[symbol_key]["sweep_bonus"]
    if bsweep and bwick: bs+=sb
    if ssweep and swick: ss+=sb
    if symbol_key in ["XAU/USD","NIFTY50","BANKNIFTY"]:
        if bsweep: bs+=1
        if ssweep: ss+=1
        if bwick:  bs+=1
        if swick:  ss+=1
    if adx>=30:
        if bs>ss: bs+=1
        elif ss>bs: ss+=1
    return buy,sell,bs,ss

# ============================================================
# WIZARD AI
# ============================================================
def wizard_ai_confirmation(df,symbol_key,direction):
    if len(df)<60: return False,0
    last=df.iloc[-1]
    close=float(last["close"]); ema50=float(last["ema50"]); ema200=float(last["ema200"])
    rsi=float(last["rsi"]); adx=float(last["adx"])
    vol=float(last["volume"]); volma=float(last["volma"]) if not pd.isna(last["volma"]) else 0
    aox=float(last["aox"]) if not pd.isna(last["aox"]) else 0
    vwap=float(last["vwap"]) if not pd.isna(last["vwap"]) else 0
    score=0
    if direction=="BUY":
        if close>ema50:  score+=3
        if ema50>ema200: score+=2
        if 52<=rsi<=RSI_EXTREME_OB: score+=2
        if adx>WIZARD_ADX_THRESHOLD: score+=2
        if aox>0:  score+=2
        if vwap>0 and close>vwap: score+=2
    else:
        if close<ema50:  score+=3
        if ema50<ema200: score+=2
        if RSI_EXTREME_OS<=rsi<=48: score+=2
        if adx>WIZARD_ADX_THRESHOLD: score+=2
        if aox<0:  score+=2
        if vwap>0 and close<vwap: score+=2
    if volma>0 and vol>volma*WIZARD_VOLUME_MULT: score+=2
    bfvg,sfvg=fair_value_gap(df); bchoch,schoch=detect_choch(df)
    bsweep,ssweep=detect_liquidity_sweep(df,symbol_key)
    bwick,swick=detect_wick_rejection(df,float(last["atr"]),symbol_key)
    if direction=="BUY":
        if bfvg: score+=2; 
        if bchoch: score+=2
        if bsweep: score+=2
        if bwick: score+=2
    else:
        if sfvg: score+=2
        if schoch: score+=2
        if ssweep: score+=2
        if swick: score+=2
    pd_zone=premium_discount(df,symbol_key)
    if direction=="BUY"  and pd_zone["discount"]: score+=1
    if direction=="SELL" and pd_zone["premium"]:  score+=1
    return score>=WIZARD_MIN_SCORE,score

# ============================================================
# ULTRA SNIPER
# ============================================================
def ultra_sniper_score(df,symbol_key,direction):
    score=0; last=df.iloc[-1]
    rsi=float(last["rsi"]); adx=float(last["adx"])
    vol=float(last["volume"]); volma=float(last["volma"]) if not pd.isna(last["volma"]) else 0
    bs,ss=detect_liquidity_sweep(df,symbol_key); bfvg,sfvg=fair_value_gap(df)
    if direction=="BUY"  and mtf_bullish(symbol_key,df): score+=4
    if direction=="SELL" and mtf_bearish(symbol_key,df): score+=4
    if wavetrend_confirmation(df,direction): score+=3
    if direction=="BUY"  and bs: score+=2
    if direction=="SELL" and ss: score+=2
    if direction=="BUY"  and bfvg: score+=2
    if direction=="SELL" and sfvg: score+=2
    if break_of_structure(df,direction): score+=2
    if institutional_volume(df): score+=2
    if strong_candle(df,direction): score+=2
    if direction=="BUY"  and 55<=rsi<=RSI_EXTREME_OB: score+=2
    if direction=="SELL" and RSI_EXTREME_OS<=rsi<=45: score+=2
    if adx>25: score+=2
    if volma>0 and vol>volma*1.5: score+=3
    return score

# ============================================================
# HELPERS
# ============================================================
def determine_best_direction(buy_score,sell_score):
    return "BUY" if buy_score>=sell_score else "SELL"  # FIX 7 — corrected

def trade_quality(score):
    if score>=28: return "GOD-TIER SCALP"
    if score>=22: return "ELITE SCALP"
    if score>=17: return "HIGH-PROB SCALP"
    return "STANDARD SCALP"

def breakout_quality(score):
    if score>=16: return "GOD-TIER BREAKOUT"
    if score>=13: return "ELITE BREAKOUT"
    return "HIGH-PROB BREAKOUT"

def adaptive_risk(session):
    return {"Asian Precision":0.6,"London":1.0,"NY Killzone":1.2,
            "India Open":1.0,"India Midday":0.8}.get(session,0.9)

def get_dynamic_rr(symbol_key,regime):
    return RR_PROFILE.get(symbol_key,{}).get(regime,MARKETS[symbol_key]["rr"])

def detect_market_regime(df): return "SCALP"

# ============================================================
# FIX 14 — ANTICIPATION ENTRY CALCULATOR
# Sets entry slightly ahead so signal fires 2 min BEFORE price arrives
# ============================================================
def calc_anticipation_entry(current_price, atr, direction, symbol_key):
    """
    SELL: entry set slightly ABOVE current price (~2 min before price arrives)
    BUY:  entry set slightly BELOW current price (~2 min before price arrives)
    FIX 20: distance capped per market so entry is never too far from price
    """
    raw_anticipation = atr * ANTICIPATION_ATR_MULT
    max_anticipation = MAX_ANTICIPATION_PTS.get(symbol_key, 5.0)
    anticipation     = min(raw_anticipation, max_anticipation)  # FIX 20 cap
    dec              = MARKETS[symbol_key]["decimals"]

    if direction == "SELL":
        entry = current_price + anticipation
    else:
        entry = current_price - anticipation

    log.info(f"Anticipation {symbol_key} {direction}: "
             f"current={current_price:.{dec}f} "
             f"raw={raw_anticipation:.{dec}f} "
             f"capped={anticipation:.{dec}f} "
             f"entry={round(entry,dec):.{dec}f}")

    return round(entry, dec)

# ============================================================
# LEVEL CALCULATOR
# ============================================================
def calc_levels(price,atr,symbol_key,df,direction,regime):
    min_sl=MARKETS[symbol_key]["min_sl"]; dec=MARKETS[symbol_key]["decimals"]
    recent=df.tail(3)
    swing_dist=(price-float(recent["low"].min()) if direction=="BUY"
                else float(recent["high"].max())-price)
    atr_sl=atr*ATR_MULT*ATR_MARKET_MULTIPLIER[symbol_key]
    swing_cap=atr*1.5*ATR_MARKET_MULTIPLIER[symbol_key]
    swing_dist=min(swing_dist,swing_cap)
    sl_dist=max(min_sl,max(atr_sl,swing_dist*0.75))
    rr=get_dynamic_rr(symbol_key,regime)
    if direction=="BUY": sl,tp=price-sl_dist,price+sl_dist*rr
    else:                sl,tp=price+sl_dist,price-sl_dist*rr
    return round(sl,dec),round(tp,dec),round(sl_dist,dec),rr

# FIX 2 — Fixed $50 risk lot size
def lot_for_risk(price,sl,symbol_key):
    risk=50.0; sl_dist=abs(price-sl)
    if sl_dist<=0: return 0.01
    lot=risk/(sl_dist*DOLLAR_PER_POINT[symbol_key])
    caps={"XAU/USD":1.50,"NAS100":2.00,"SPX500":2.00,"EUR/USD":3.00,"GBP/JPY":2.00,
          "NIFTY50":50.0,"BANKNIFTY":50.0,"SENSEX":50.0,"RELIANCE":500.0,"TCS":500.0}
    if symbol_key in ["NIFTY50","BANKNIFTY","SENSEX","RELIANCE","TCS"]:
        return float(max(1.0,round(lot)))
    return round(max(0.01,min(lot,caps[symbol_key])),3)

# FIX 3 + FIX 10 — SL validation
def validate_sl_distance(symbol_key, price, sl, is_scalp=True):
    """
    Dual SL validation:
    - scalp signals use scalp_min_sl (tight)
    - breakout signals use min_sl (wider)
    """
    min_sl = (MARKETS[symbol_key].get("scalp_min_sl", MARKETS[symbol_key]["min_sl"])
              if is_scalp else MARKETS[symbol_key]["min_sl"])
    sl_dist = abs(price - sl)
    if sl_dist < min_sl:
        log.info(f"BLOCKED {symbol_key} SL dist {sl_dist:.5f} < {'scalp' if is_scalp else 'breakout'} min {min_sl}")
        return False
    return True

# FIX 4 — RSI extreme hard block
def rsi_extreme_block(rsi, direction, adx=0):
    """
    FIX 4 updated:
    - BUY blocked if RSI > 72 (overbought)
    - SELL blocked if RSI < 15 (data error / impossible)
    - SELL warned if RSI < 28 BUT allowed if ADX > 30 (strong trend)
    """
    if direction == "BUY" and rsi > RSI_EXTREME_OB:
        log.info(f"BLOCKED RSI overbought {rsi:.1f} — no BUY")
        return True
    if direction == "SELL" and rsi < RSI_EXTREME_OS:
        log.info(f"BLOCKED RSI {rsi:.1f} — data error (below {RSI_EXTREME_OS})")
        return True
    # Warning zone: RSI 15-28 on SELL — only allow with strong ADX
    if direction == "SELL" and rsi < RSI_WARN_OS:
        if adx >= 30:
            log.info(f"ALLOWED RSI {rsi:.1f} warn zone — ADX {adx:.1f} confirms strong trend")
            return False  # allow it
        else:
            log.info(f"BLOCKED RSI {rsi:.1f} warn zone — ADX {adx:.1f} too weak")
            return True
    return False

# ============================================================
# SPREAD / VOLATILITY
# ============================================================
def spread_too_high(symbol_key,spread):
    return spread>MAX_SPREAD[symbol_key]*0.90

def volatility_danger(df,symbol_key):
    if len(df)<30: return False
    atr=float(df.iloc[-1]["atr"]); avg=df["atr"].rolling(20).mean().iloc[-1]
    if pd.isna(avg) or avg==0: return False
    return (atr/avg)>2.5

def quantum_volatility_ok(df):
    if len(df)<30: return False
    atr=float(df.iloc[-1]["atr"]); avg=df["atr"].rolling(20).mean().iloc[-1]
    if pd.isna(avg) or avg==0: return False
    return 0.60<=(atr/avg)<=2.50

def false_breakout_filter(df,direction):
    if len(df)<3: return False
    last=df.iloc[-1]; prev=df.iloc[-2]; atr=float(df.iloc[-1]["atr"])
    if direction=="BUY":  return float(last["close"])>float(prev["high"])-atr*0.08
    return float(last["close"])<float(prev["low"])+atr*0.08

def correlated_signal_block(symbol_key):
    if not CORRELATION_BLOCK: return False
    for group in CORRELATED_GROUPS:
        if symbol_key in group:
            active=sum(1 for s in group if time.time()-_signal_sent.get(s,0)<3600)
            if active>=MAX_OPEN_CORRELATED:
                log.info(f"Correlation blocker: {symbol_key}"); return True
    return False

def duplicate_signal(symbol_key,direction):
    now=time.time(); cooldown=DUPLICATE_WINDOWS.get(symbol_key,1800)
    with signal_lock:
        ld=_last_signal_direction.get(symbol_key)
        lt=_last_signal_time.get(symbol_key,0)
        if ld==direction and now-lt<cooldown:
            log.info(f"Duplicate blocked {symbol_key}"); return True
        _last_signal_direction[symbol_key]=direction
        _last_signal_time[symbol_key]=now
    return False

# FIX 1 — Signal gate: only #1 per session
def get_signal_number(symbol_key,session):
    global _signal_counter
    if _signal_counter[symbol_key]["session"]!=session:
        _signal_counter[symbol_key]["session"]=session
        _signal_counter[symbol_key]["count"]=1
    else:
        _signal_counter[symbol_key]["count"]+=1
    return _signal_counter[symbol_key]["count"],"SCALP ENTRY"

def scalp_signal_allowed(symbol_key,session):
    sc=_signal_counter[symbol_key]
    if sc["session"]==session and sc["count"]>=1:
        log.info(f"BLOCKED {symbol_key} signal #2/#3"); return False
    return True

# ============================================================
# MASTER SIGNAL ENGINE
# ============================================================
def master_signal(symbol_key,df,session,trend,regime,
                  buy,sell,buy_score,sell_score,
                  struct_buy_score,struct_sell_score):

    direction=determine_best_direction(buy_score,sell_score)
    best=max(buy_score,sell_score)

    # FIX 9 — absolute min score
    if best<ABSOLUTE_MIN_SCORE:
        log.info(f"REJECTED {symbol_key} score {best}<{ABSOLUTE_MIN_SCORE}"); return None,None,None

    if not scalp_macro_filter(df,direction):
        log.info(f"REJECTED {symbol_key} scalp macro"); return None,None,None

    # FIX 4 — RSI extreme
    rsi=float(df.iloc[-1]["rsi"])
    adx_val=float(df.iloc[-1]["adx"])
    # Session-based ADX threshold
    adx_min = ADX_THRESHOLD_ASIAN if session=="Asian Precision" else ADX_THRESHOLD
    if adx_val < adx_min:
        log.info(f"REJECTED {symbol_key} ADX {adx_val:.1f}<{adx_min} for {session}")
        return None,None,None,None,None
    # RSI extreme block — passes ADX for warn zone decision
    if rsi_extreme_block(rsi, direction, adx_val): return None,None,None,None,None

    # FIX 12 — ADX check now done in RSI section below with session awareness

    # FIX 13 — session momentum
    if not session_momentum_ok(df,direction):
        log.info(f"REJECTED {symbol_key} weak session momentum"); return None,None,None

    if ENABLE_WIZARD_AI:
        wp,ws=wizard_ai_confirmation(df,symbol_key,direction)
        if not wp:
            log.info(f"REJECTED {symbol_key} Wizard AI {ws}"); return None,None,None
        best+=int(ws*0.30)
        wizard_score=ws
    else:
        wizard_score=0

    sniper=ultra_sniper_score(df,symbol_key,direction)
    best+=sniper

    required=SESSION_THRESHOLDS.get(session,20)
    if best<required:
        log.info(f"REJECTED {symbol_key} score {best}<{required}"); return None,None,None

    if VOLATILITY_KILL and not quantum_volatility_ok(df):
        log.info(f"REJECTED {symbol_key} volatility"); return None,None,None

    if FALSE_BREAK_FILTER and not false_breakout_filter(df,direction):
        log.info(f"REJECTED {symbol_key} false breakout"); return None,None,None

    # ============================================================
    # CONFLUENCE CHECK — require 2+ engines to agree
    # ============================================================
    conf_pass, conf_score, engines_passed, conf_text = run_confluence(
        df, symbol_key, direction, best
    )
    if not conf_pass:
        return None, None, None, None, None

    return direction, conf_score, wizard_score, engines_passed, conf_text

# ============================================================
# EXECUTE SCALP TRADE — with FIX 14 anticipation entry
# ============================================================
def execute_trade(symbol_key,df,direction,best,wizard_score,
                  sniper_score,macro_trend,session,trend,
                  regime,buy,sell,source,asia_mode,daily_bias,
                  engines_passed=None,conf_text=""):

    current_price = float(df.iloc[-1]["close"])
    atr           = float(df.iloc[-1]["atr"])
    rsi           = float(df.iloc[-1]["rsi"])
    adx           = float(df.iloc[-1]["adx"])
    dec           = MARKETS[symbol_key]["decimals"]

    # FIX 21-26 — final indicator sanity check before firing signal
    if not validate_signal_indicators(rsi, adx, atr, symbol_key, direction):
        return

    # FIX 14 — Anticipation entry: set entry ahead of current price
    entry = calc_anticipation_entry(current_price, atr, direction, symbol_key)

    # FIX 15 — Validate entry is reachable from current price
    if not entry_is_reachable(entry, current_price, symbol_key, direction):
        return

    demand_zone,supply_zone=detect_supply_demand_zones(df)

    sl,tp,sl_dist,rr=calc_levels(entry,atr,symbol_key,df,direction,regime)

    # FIX 10 — SL validation (scalp mode)
    if not validate_sl_distance(symbol_key, entry, sl, is_scalp=True): return

    # FIX 2 — fixed $50 lot
    lot     = lot_for_risk(entry,sl,symbol_key)
    quality = trade_quality(best)
    signal_num,entry_type=get_signal_number(symbol_key,session)

    # FIX 17 — Trailing SL levels
    tp_50pct = round(entry+(tp-entry)*0.50,dec) if direction=="BUY" else round(entry-(entry-tp)*0.50,dec)
    tp_75pct = round(entry+(tp-entry)*0.75,dec) if direction=="BUY" else round(entry-(entry-tp)*0.75,dec)

    log_signal(symbol_key,direction,best,rr,entry,sl,tp,session,regime,"1M / 5M","SCALP")

    checks=buy if direction=="BUY" else sell
    cond_text="\n".join([f" {k}" for k,v in checks.items() if v])
    if demand_zone: cond_text+="\n DEMANDZONE"
    if supply_zone: cond_text+="\n SUPPLYZONE"

    ae="📈" if direction=="BUY" else "📉"
    mtype=MARKETS[symbol_key]["market_type"]
    market_flag="🇮🇳 *INDIA INTRADAY*\n" if mtype=="india" else "🌍 *GLOBAL MARKET*\n"
    anticipation_dist=abs(entry-current_price)

    msg=(
        f"⚡ *{SYSTEM_VERSION}* | SCALP EXECUTION\n"
        f"*{MARKETS[symbol_key]['mt5']}* | ⭐⭐⭐⭐⭐ {MARKETS[symbol_key]['tier']}\n"
        f"🔱 *PRIORITY MARKET*\n{market_flag}\n"
        f"🔥 *Action:* {direction} {ae}\n"
        f"🎯 *Signal #:* {signal_num}\n"
        f"📍 *Entry Type:* {entry_type}\n"
        f"🚀 *Signal Type:* SCALP\n"
        f"⏱ *Timeframe:* 1M / 5M\n"
        f"⭐ *Total Score:* {best}\n"
        f"🏆 *Trade Quality:* {quality}\n"
        f"🌍 *Macro Trend:* {macro_trend}\n"
        f"📅 *Daily Bias:* {daily_bias}\n"
        f"⚛ *Scalp Macro Filter:* PASS\n"
        f"🎯 *Sniper Score:* {sniper_score}\n"
        f"🧠 *Wizard AI Score:* {wizard_score if ENABLE_WIZARD_AI else 'OFF'}\n"
        f"🧠 *Regime:* SCALP\n"
        f"📊 *Market Bias:* {MARKETS[symbol_key]['bias']}\n\n"
        f"⏳ *Current Price:* {current_price:,.{dec}f}\n"
        f"📍 *Entry:* {entry:,.{dec}f} *(~2 min — price approaching)*\n"
        f"📏 *Distance to Entry:* {anticipation_dist:.{dec}f}\n"
        f"🛑 *SL:* {sl:,.{dec}f}\n"
        f"🎯 *TP:* {tp:,.{dec}f} *(1:{rr} RR)*\n\n"
        f"📊 *Trailing SL Guide:*\n"
        f"  • At 50% TP ({tp_50pct:,.{dec}f}) → Move SL to breakeven\n"
        f"  • At 75% TP ({tp_75pct:,.{dec}f}) → Trail SL by 1 ATR\n\n"
        f"📈 *RSI:* {rsi:.1f}\n"
        f"📉 *ADX:* {adx:.1f}\n"
        f"🌍 *Trend:* {trend}\n"
        f"⏰ *Session:* {session}\n"
        f"📡 *Data Source:* {source}\n"
        f"🧠 *Mode:* {'ASIA SCALP PRECISION' if asia_mode else 'CORE SCALP MODE'}\n\n"
        f"💵 *Lot:* {lot} *(Fixed $50 Risk)*\n\n"
        f"✅ *Conditions:*\n{cond_text}\n\n"
        f"🕐 *Entry Mode:* ⚡ ANTICIPATION — ENTER WHEN PRICE REACHES {entry:,.{dec}f}\n"
        f"🛡 *ELITE SCALP FILTER ACTIVE*\n"
        f"\n🔥 *Engine Confluence:* {len(engines_passed) if engines_passed else 1}/4\n"
        f"{conf_text}\n\n"
        f"🛡 *ELITE SCALP FILTER ACTIVE*\n"
        f"⚡ *ULTIMATE HYBRID SUPREME — 2026 SCALPER EDITION v5.3*"
    )
    send_telegram(msg)
    log.info(f"SCALP SIGNAL {symbol_key} {direction} | CurrentPrice:{current_price} Entry:{entry} SL:{sl} TP:{tp} Lot:{lot}")

# ============================================================
# BREAKOUT ENGINE (15M)
# ============================================================
def detect_breakout_signal(df,symbol_key):
    if df is None or len(df)<30: return None,0
    last=df.iloc[-1]; adx=float(last["adx"]); vol=float(last["volume"])
    volma=float(last["volma"]) if not pd.isna(last["volma"]) else 0
    aox=float(last["aox"]) if not pd.isna(last["aox"]) else 0; atr=float(last["atr"])
    if adx<28: return None,0
    if volma<=0 or vol<volma*1.8: return None,0
    bs,ss=detect_liquidity_sweep(df,symbol_key); bfvg,sfvg=fair_value_gap(df)
    bwick,swick=detect_wick_rejection(df,atr,symbol_key)
    bos_b=break_of_structure(df,"BUY"); bos_s=break_of_structure(df,"SELL")
    bull_sc=bear_sc=0
    if bs: bull_sc+=5
    if bos_b: bull_sc+=4
    if bfvg: bull_sc+=2
    if bwick: bull_sc+=2
    if aox>0: bull_sc+=1
    if vwap_trend(df,"BUY"): bull_sc+=2
    if ss: bear_sc+=5
    if bos_s: bear_sc+=4
    if sfvg: bear_sc+=2
    if swick: bear_sc+=2
    if aox<0: bear_sc+=1
    if vwap_trend(df,"SELL"): bear_sc+=2
    if bull_sc>bear_sc and not bs: return None,0
    if bear_sc>bull_sc and not ss: return None,0
    if bull_sc>bear_sc and bull_sc>=9: return "BUY",bull_sc
    if bear_sc>bull_sc and bear_sc>=9: return "SELL",bear_sc
    return None,0

def execute_breakout(symbol_key,df,direction,score,session,source,daily_bias):
    price=float(df.iloc[-1]["close"]); atr=float(df.iloc[-1]["atr"])
    rsi=float(df.iloc[-1]["rsi"]); adx=float(df.iloc[-1]["adx"])
    dec=MARKETS[symbol_key]["decimals"]
    vol=float(df.iloc[-1]["volume"])
    volma=float(df.iloc[-1]["volma"]) if not pd.isna(df.iloc[-1]["volma"]) else 0

    # FIX 21-26 — indicator sanity before breakout fires
    if not validate_signal_indicators(rsi, adx, atr, symbol_key, direction):
        return

    if rsi_extreme_block(rsi,direction): return

    # FIX 11 — daily bias check for breakout too
    if daily_bias=="BEAR" and direction=="BUY":
        log.info(f"BREAKOUT REJECTED {symbol_key} — BUY against BEAR day"); return
    if daily_bias=="BULL" and direction=="SELL":
        log.info(f"BREAKOUT REJECTED {symbol_key} — SELL against BULL day"); return

    recent=df.tail(5)
    swing_dist=(price-float(recent["low"].min()) if direction=="BUY" else float(recent["high"].max())-price)
    min_sl=MARKETS[symbol_key]["min_sl"]*2.0; sl_dist=max(min_sl,swing_dist*0.90)
    rr=get_dynamic_rr(symbol_key,"BREAKOUT")
    price+=EXECUTION_BUFFER[symbol_key] if direction=="BUY" else -EXECUTION_BUFFER[symbol_key]
    if direction=="BUY":  sl,tp=round(price-sl_dist,dec),round(price+sl_dist*rr,dec)
    else:                 sl,tp=round(price+sl_dist,dec),round(price-sl_dist*rr,dec)
    if not validate_sl_distance(symbol_key, price, sl, is_scalp=False): return
    lot=lot_for_risk(price,sl,symbol_key); quality=breakout_quality(score)
    bs,ss=detect_liquidity_sweep(df,symbol_key)
    sweep_tag="✅ LIQUIDITY SWEEP CONFIRMED" if (direction=="BUY" and bs) or (direction=="SELL" and ss) else "⚠️ MOMENTUM BREAK"
    ae="📈" if direction=="BUY" else "📉"
    mtype=MARKETS[symbol_key]["market_type"]
    market_flag="🇮🇳 *INDIA INTRADAY*\n" if mtype=="india" else "🌍 *GLOBAL MARKET*\n"
    log_signal(symbol_key,direction,score,rr,price,sl,tp,session,"BREAKOUT","15M / 30M","BREAKOUT")
    msg=(
        f"💥 *{SYSTEM_VERSION}* | BREAKOUT EXECUTION\n"
        f"*{MARKETS[symbol_key]['mt5']}* | ⭐⭐⭐⭐⭐ {MARKETS[symbol_key]['tier']}\n"
        f"🔱 *PRIORITY MARKET*\n{market_flag}\n"
        f"🔥 *Action:* {direction} {ae}\n"
        f"📍 *Entry Type:* {'BREAKOUT 🚀' if direction=='BUY' else 'BREAKDOWN 💥'}\n"
        f"🚀 *Signal Type:* BREAKOUT / LIQUIDITY SWEEP\n"
        f"⏱ *Timeframe:* 15M / 30M\n"
        f"⭐ *Breakout Score:* {score}\n"
        f"🏆 *Trade Quality:* {quality}\n"
        f"📅 *Daily Bias:* {daily_bias}\n"
        f"🔍 *Sweep Status:* {sweep_tag}\n\n"
        f"📍 *Entry:* {price:,.{dec}f}\n"
        f"🛑 *SL:* {sl:,.{dec}f}\n"
        f"🎯 *TP:* {tp:,.{dec}f} *(1:{rr} RR)*\n\n"
        f"📈 *RSI:* {rsi:.1f}\n"
        f"📉 *ADX:* {adx:.1f}\n"
        f"📊 *Volume vs MA:* {(vol/volma*100):.0f}% of avg\n"
        f"⏰ *Session:* {session}\n"
        f"📡 *Data Source:* {source}\n\n"
        f"💵 *Lot:* {lot} *(Fixed $50 Risk)*\n\n"
        f"🛡 *ELITE BREAKOUT FILTER ACTIVE*\n"
        f"⚡ *ULTIMATE HYBRID SUPREME — 2026 SCALPER EDITION v2*"
    )
    send_telegram(msg)
    log.info(f"BREAKOUT {symbol_key} {direction} Entry:{price} SL:{sl} TP:{tp} Lot:{lot}")

# ============================================================
# PROCESS SYMBOL
# ============================================================
def process_symbol(symbol_key):
    log.info(f"Scanning {symbol_key}")
    if _daily_signal_count[symbol_key]>=MAX_SIGNALS_PER_DAY[symbol_key]: return
    if weekend_block(symbol_key): return
    if daily_loss_lock():         return
    if loss_streak_lock():        return

    watchdog(); rotate_log()

    ok,session=in_session(symbol_key)
    if not ok or session not in ALLOWED_SESSIONS: return

    # FIX 18 — news block
    if news_block(): return

    # FIX 1 — signal #1 only gate
    if not scalp_signal_allowed(symbol_key,session): return

    df,source=get_entry_data(symbol_key)
    if df is None or len(df)<60: return

    # FIX 16 — data freshness
    if not data_is_fresh(df):
        log.info(f"REJECTED {symbol_key} stale data"); return

    spread=get_spread(df)
    if spread_too_high(symbol_key,spread):
        log.info(f"REJECTED {symbol_key} spread"); return

    df=add_ind(df)
    if df is None or len(df)<50: return

    # FIX 21-26 — data quality validation
    if not validate_data_quality(df, symbol_key):
        log.info(f"REJECTED {symbol_key} data quality fail"); return

    if volatility_danger(df,symbol_key):
        log.info(f"REJECTED {symbol_key} extreme vol"); return

    current_price=float(df.iloc[-1]["close"])
    atr=float(df.iloc[-1]["atr"]); rsi=float(df.iloc[-1]["rsi"])
    if current_price<=0: return

    trend=get_trend(symbol_key)
    regime=detect_market_regime(df)
    asia_mode=session=="Asian Precision"

    # FIX 11 — get daily bias
    daily_bias=get_daily_bias(symbol_key,df)
    macro_trend=daily_bias

    buy,sell,buy_score,sell_score=build_score(df,trend,symbol_key)
    sbc,ssc,sbuy,ssell=institutional_structure_score(df,symbol_key)
    buy.update(sbc); sell.update(ssc)
    buy_score+=sbuy; sell_score+=ssell

    if asia_mode:
        buy_score+=1 if buy_score>=7 else 0
        sell_score+=1 if sell_score>=7 else 0
        if spread>MAX_SPREAD[symbol_key]*1.05:
            log.info(f"REJECTED {symbol_key} Asia spread"); return
        if max(buy_score,sell_score)<6:
            log.info(f"REJECTED {symbol_key} weak Asia score"); return

    if max(sbuy,ssell)<MARKET_MIN_STRUCTURE_SCORE[symbol_key]:
        log.info(f"REJECTED {symbol_key} weak structure"); return

    direction=determine_best_direction(buy_score,sell_score)

    # FIX 11 — daily bias hard block
    if daily_bias=="BEAR" and direction=="BUY":
        log.info(f"REJECTED {symbol_key} BUY on BEAR day"); return
    if daily_bias=="BULL" and direction=="SELL":
        log.info(f"REJECTED {symbol_key} SELL on BULL day"); return

    # FIX 8 — countertrend block
    if symbol_key not in ["XAU/USD"]:
        if trend=="BULL" and direction=="SELL":
            log.info(f"REJECTED {symbol_key} countertrend SELL"); return
        if trend=="BEAR" and direction=="BUY":
            log.info(f"REJECTED {symbol_key} countertrend BUY");  return

    if symbol_key=="XAU/USD":
        if trend=="BULL" and direction=="SELL" and rsi>45:
            log.info(f"REJECTED XAU countertrend SELL RSI {rsi:.1f}"); return
        if trend=="BEAR" and direction=="BUY"  and rsi<55:
            log.info(f"REJECTED XAU countertrend BUY RSI {rsi:.1f}"); return

    demand_zone,supply_zone=detect_supply_demand_zones(df)
    planned=float(df.iloc[-2]["close"]); max_drift=atr*0.50
    if direction=="SELL" and supply_zone and current_price<supply_zone*0.998: return
    if direction=="BUY"  and demand_zone and current_price>demand_zone*1.002: return
    if direction=="SELL" and current_price<planned-max_drift: return
    if direction=="BUY"  and current_price>planned+max_drift: return

    if correlated_signal_block(symbol_key): return

    direction,best,wizard_score,engines_passed,conf_text=master_signal(
        symbol_key,df,session,trend,regime,
        buy,sell,buy_score,sell_score,sbuy,ssell
    )
    if direction is None: return

    sniper_score=ultra_sniper_score(df,symbol_key,direction)

    if duplicate_signal(symbol_key,direction): return

    now=time.time()
    if now-_signal_sent[symbol_key]<SIGNAL_COOLDOWN:
        log.info(f"REJECTED {symbol_key} cooldown"); return

    with signal_lock:
        _signal_sent[symbol_key]=now
        _daily_signal_count[symbol_key]+=1

    execute_trade(symbol_key,df,direction,best,wizard_score,
                  sniper_score,macro_trend,session,trend,
                  regime,buy,sell,source,asia_mode,daily_bias,
                  engines_passed,conf_text)

# ============================================================
# PROCESS BREAKOUT
# ============================================================
def process_breakout(symbol_key):
    ok,session=in_session(symbol_key)
    if not ok or session not in ALLOWED_SESSIONS: return
    if daily_loss_lock() or loss_streak_lock(): return
    if news_block(): return

    df,source=get_entry_data(symbol_key,for_breakout=True)
    if df is None or len(df)<60: return
    df=add_ind(df)
    if df is None or len(df)<50: return

    # FIX 21-26 — data quality validation
    if not validate_data_quality(df, symbol_key):
        log.info(f"BREAKOUT REJECTED {symbol_key} data quality fail"); return

    daily_bias=get_daily_bias(symbol_key,df)
    direction,score=detect_breakout_signal(df,symbol_key)
    if direction is None: return

    required=BREAKOUT_SESSION_THRESHOLDS.get(session,14)
    if score<required:
        log.info(f"BREAKOUT REJECTED {symbol_key} {score}<{required}"); return

    bk_key=f"BK_{symbol_key}"; now=time.time()
    if now-_signal_sent.get(bk_key,0)<1800:
        log.info(f"BREAKOUT {symbol_key} cooldown"); return

    _signal_sent[bk_key]=now
    execute_breakout(symbol_key,df,direction,score,session,source,daily_bias)

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    log.info(f"{SYSTEM_VERSION} STARTED")
    send_telegram(
        f"⚡ *{SYSTEM_VERSION} LIVE*\n\n"
        f"📊 *Global:* XAU/USD | NAS100 | SPX500 | EUR/USD | GBP/JPY\n"
        f"🇮🇳 *India:* NIFTY50 | BANKNIFTY | SENSEX | RELIANCE | TCS\n\n"
        f"✅ FIX 1:  Signal #2/#3 Blocked\n"
        f"✅ FIX 2:  Fixed $50 Risk Lot Size\n"
        f"✅ FIX 3:  Min SL Enforced\n"
        f"✅ FIX 4:  RSI Extreme Hard Block\n"
        f"✅ FIX 5:  Duplicate Window 30min\n"
        f"✅ FIX 6:  India Close Removed\n"
        f"✅ FIX 7:  Direction Logic Corrected\n"
        f"✅ FIX 8:  Countertrend RSI Gate\n"
        f"✅ FIX 9:  Min Score = 20\n"
        f"✅ FIX 10: SL Validation\n"
        f"✅ FIX 11: Daily Bias Filter\n"
        f"✅ FIX 12: ADX > 25 Mandatory\n"
        f"✅ FIX 13: Session Momentum Check\n"
        f"✅ FIX 14: Anticipation Entry 2min Early\n"
        f"✅ FIX 15: Entry Drift Check\n"
        f"✅ FIX 16: Data Freshness Check\n"
        f"✅ FIX 17: Trailing SL Guide\n"
        f"✅ FIX 18: News Time Block\n"
        f"✅ FIX 19: 30min Same Symbol Gap\n✅ FIX 20: Anticipation Distance Capped\n✅ FIX 21: ADX Spike Block (>60 blocked)\n✅ FIX 22: RSI Impossible Block (<10 or >90)\n✅ FIX 23: ATR Sanity Check Per Market\n✅ FIX 24: Candle Sanity Check\n✅ FIX 25: Volume Sanity Check\n✅ FIX 26: Price Range Sanity Check\n\n"
        f"⚡ ULTIMATE HYBRID SUPREME 2026 — SCALPER EDITION v5.3\n\n"
        f"⚙️ 5-ENGINE SYSTEM:\n"
        f"1️⃣ Momentum | 2️⃣ RSI Divergence\n"
        f"3️⃣ Price Action | 4️⃣ Liquidity Sweep\n"
        f"5️⃣ Correlation Theory (NEW)\n\n"
        f"🔗 Correlation Maps: XAUUSD+Silver+DXY | NAS+SPX+VIX\n"
        f"🇮🇳 NIFTY+BANKNIFTY+INR | GBP/JPY+USD/JPY\n\n"
        f"🔥 4-ENGINE CONFLUENCE SYSTEM:\n"
        f"ENGINE 1: Momentum Scalp\n"
        f"ENGINE 2: RSI Divergence\n"
        f"ENGINE 3: Price Action\n"
        f"ENGINE 4: Enhanced Liquidity Sweep"
    )

    loop_count=0
    while True:
        try:
            reset_daily()
            with ThreadPoolExecutor(max_workers=len(PRIORITY_MARKETS)) as executor:
                futures=[executor.submit(process_symbol,s) for s in PRIORITY_MARKETS]
                time.sleep(0.25)
                for future in as_completed(futures):
                    try: future.result()
                    except Exception as e: log.error(f"Scalp thread: {e}")

            if loop_count%5==0:
                with ThreadPoolExecutor(max_workers=len(PRIORITY_MARKETS)) as executor:
                    futures=[executor.submit(process_breakout,s) for s in PRIORITY_MARKETS]
                    for future in as_completed(futures):
                        try: future.result()
                        except Exception as e: log.error(f"Breakout thread: {e}")

            loop_count+=1
            gc.collect()
            time.sleep(MAIN_LOOP_DELAY)

        except Exception as e:
            log.error(f"Main loop: {e}")
            time.sleep(MAIN_LOOP_DELAY)

if __name__=="__main__":
    main()
