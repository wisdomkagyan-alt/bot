#!/usr/bin/env python3
# ============================================================
# TOPG 6-STEP REVERSAL STRATEGY - COMPLETE BOT
# v1.0 | Production-Ready | All-In-One Implementation
#
# This single file contains everything needed to:
# 1. Detect reversal setups using the 6-step method
# 2. Fetch live market data (Yahoo Finance)
# 3. Run continuous monitoring
# 4. Send signals to Telegram
# 5. Log all trades for backtesting
#
# SETUP (3 steps):
# 1. pip install pandas numpy ta yfinance requests
# 2. Get Telegram bot token from @BotFather
# 3. Edit TELEGRAM_TOKEN and TELEGRAM_CHAT_ID below
# 4. Run: python TOPG_COMPLETE_BOT.py
#
# ============================================================

import logging
import requests
import pandas as pd
import numpy as np
import ta
import yfinance as yf
import os
import csv
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================================================
# LOGGING SETUP
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('topg_bot.log')
    ]
)
log = logging.getLogger("TOPG_6STEP_BOT")

# ============================================================
# TELEGRAM CONFIGURATION - EDIT THESE
# ============================================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8783763018")

# ============================================================
# MARKET CONFIGURATION
# ============================================================
MARKETS = {
    "XAU/USD": {
        "yf_symbol": "GC=F",
        "mt5_name": "XAUUSD",
        "interval": "5m",
        "session_hours": (7, 20),
        "active_sessions": ["London", "NY Killzone"],
        "decimals": 2,
        "impulse_threshold": 100.0,
        "min_impulse_bars": 20,
        "sweep_lookback": 6,
        "order_block_range": 10,
        "min_rr": 2.0,
    },
    "NAS100": {
        "yf_symbol": "^NDX",
        "mt5_name": "NAS100",
        "interval": "5m",
        "session_hours": (13, 21),
        "active_sessions": ["London", "NY Killzone"],
        "decimals": 1,
        "impulse_threshold": 350.0,
        "min_impulse_bars": 20,
        "sweep_lookback": 8,
        "order_block_range": 12,
        "min_rr": 2.0,
    },
    "DE30": {
        "yf_symbol": "^GDAXI",
        "mt5_name": "DE30",
        "interval": "5m",
        "session_hours": (7, 18),
        "active_sessions": ["London"],
        "decimals": 1,
        "impulse_threshold": 300.0,
        "min_impulse_bars": 20,
        "sweep_lookback": 7,
        "order_block_range": 14,
        "min_rr": 2.0,
    },
    "US30": {
        "yf_symbol": "^DJI",
        "mt5_name": "US30",
        "interval": "5m",
        "session_hours": (13, 21),
        "active_sessions": ["NY Killzone"],
        "decimals": 1,
        "impulse_threshold": 650.0,
        "min_impulse_bars": 20,
        "sweep_lookback": 8,
        "order_block_range": 12,
        "min_rr": 2.0,
    },
}

# ============================================================
# GLOBAL STATE
# ============================================================
_data_cache = {}
_last_signal = {}
data_cache_duration = 50  # seconds

# ============================================================
# PART 1: CORE 6-STEP STRATEGY ENGINE
# ============================================================

def identify_bos(df, direction="BULL"):
    """
    STEP 1: Identify Break of Structure
    
    BOS = price breaks previous swing high (BULL) or swing low (BEAR)
    This confirms institutional momentum in the reversal direction.
    
    Returns: (bos_exists, bos_price, swing_high, swing_low)
    """
    if len(df) < 10:
        return False, None, None, None
    
    recent = df.tail(20)
    highs = recent["high"].astype(float).values
    lows = recent["low"].astype(float).values
    
    prev_high = highs[-5:-1].max()
    prev_low = lows[-5:-1].min()
    current_close = float(df.iloc[-1]["close"])
    
    if direction == "BULL":
        # Bullish BOS: close breaks below previous low (bearish impulse)
        bos_confirmed = current_close < prev_low
        return bos_confirmed, float(current_close), float(prev_high), float(prev_low)
    else:  # BEAR
        # Bearish BOS: close breaks above previous high (bullish impulse)
        bos_confirmed = current_close > prev_high
        return bos_confirmed, float(current_close), float(prev_high), float(prev_low)


def detect_choch(df, direction="BULL"):
    """
    STEP 2: Detect Change of Character (ChoCH)
    
    ChoCH = first candle closing in opposite direction of prevailing trend
    This is the earliest signal that institutional reversal is happening.
    
    Returns: (choch_exists, choch_bar_index, reversal_candle)
    """
    if len(df) < 5:
        return False, None, None
    
    recent = df.tail(10).reset_index(drop=True)
    
    if direction == "BULL":
        # Bullish reversal ChoCH: after bearish moves, first bullish close
        for i in range(len(recent) - 1, 0, -1):
            prev_lows = recent.iloc[:i]["low"].astype(float).values
            prev_low = prev_lows.min()
            curr_close = float(recent.iloc[i]["close"])
            curr_open = float(recent.iloc[i]["open"])
            
            if curr_close > curr_open and curr_close > prev_low * 1.001:
                return True, i, recent.iloc[i]
    else:  # BEAR
        # Bearish reversal ChoCH: after bullish moves, first bearish close
        for i in range(len(recent) - 1, 0, -1):
            prev_highs = recent.iloc[:i]["high"].astype(float).values
            prev_high = prev_highs.max()
            curr_close = float(recent.iloc[i]["close"])
            curr_open = float(recent.iloc[i]["open"])
            
            if curr_close < curr_open and curr_close < prev_high * 0.999:
                return True, i, recent.iloc[i]
    
    return False, None, None


def mark_order_block(df, direction="BULL", lookback=15):
    """
    STEP 3: Mark Order Block
    
    Order Block = the last opposing candle before the impulse move
    This is where institutional traders placed their orders.
    Price returns to this zone for entry confirmation.
    
    Returns: (ob_price, ob_high, ob_low, ob_index)
    """
    if len(df) < lookback:
        return None, None, None, None
    
    recent = df.tail(lookback).reset_index(drop=True)
    
    if direction == "BULL":
        # After bearish impulse, find the strong bearish candle
        for i in range(len(recent) - 2, 0, -1):
            candle = recent.iloc[i]
            open_p = float(candle["open"])
            close_p = float(candle["close"])
            
            if close_p < open_p:  # Bearish candle
                ob_high = float(candle["high"])
                ob_low = float(candle["low"])
                ob_price = (ob_high + ob_low) / 2
                return ob_price, ob_high, ob_low, i
    else:  # BEAR
        # After bullish impulse, find the strong bullish candle
        for i in range(len(recent) - 2, 0, -1):
            candle = recent.iloc[i]
            open_p = float(candle["open"])
            close_p = float(candle["close"])
            
            if close_p > open_p:  # Bullish candle
                ob_high = float(candle["high"])
                ob_low = float(candle["low"])
                ob_price = (ob_high + ob_low) / 2
                return ob_price, ob_high, ob_low, i
    
    return None, None, None, None


def detect_liquidity_sweep(df, direction="BULL", lookback=6):
    """
    STEP 4: Detect Liquidity Sweep (BONUS - not required)
    
    Sweep = price touches/breaks previous swing level, then reverses
    Shows institutional traders hunting retail stop-losses.
    Increases probability when present.
    
    Returns: (sweep_detected, sweep_price, sweep_index, reversal_close)
    """
    if len(df) < lookback + 2:
        return False, None, None, None
    
    recent = df.tail(lookback + 2).reset_index(drop=True)
    
    if direction == "BULL":
        # Bullish sweep: price touches below previous low, then closes above
        prev_lows = recent.iloc[:-2]["low"].astype(float).values
        prev_low = prev_lows.min()
        
        current_low = float(recent.iloc[-1]["low"])
        current_close = float(recent.iloc[-1]["close"])
        
        if current_low < prev_low and current_close > prev_low:
            return True, float(prev_low), len(recent) - 1, current_close
    else:  # BEAR
        # Bearish sweep: price touches above previous high, then closes below
        prev_highs = recent.iloc[:-2]["high"].astype(float).values
        prev_high = prev_highs.max()
        
        current_high = float(recent.iloc[-1]["high"])
        current_close = float(recent.iloc[-1]["close"])
        
        if current_high > prev_high and current_close < prev_high:
            return True, float(prev_high), len(recent) - 1, current_close
    
    return False, None, None, None


def detect_impulse_move(df, symbol_key, direction="BULL"):
    """
    Helper: Detect if there was an impulsive directional move
    This precedes the reversal and validates the setup.
    
    Returns: (impulse_exists, move_size)
    """
    config = MARKETS[symbol_key]
    lookback = config["min_impulse_bars"]
    threshold = config["impulse_threshold"]
    
    if len(df) < lookback:
        return False, 0.0
    
    window = df.tail(lookback)
    window_high = float(window["high"].max())
    window_low = float(window["low"].min())
    high_pos = int(window["high"].values.argmax())
    low_pos = int(window["low"].values.argmin())
    move = window_high - window_low
    
    if direction == "BULL":
        # Bullish reversal after bearish impulse (low comes first)
        impulse_ok = bool(low_pos < high_pos and move >= threshold)
    else:  # BEAR
        # Bearish reversal after bullish impulse (high comes first)
        impulse_ok = bool(high_pos < low_pos and move >= threshold)
    
    return impulse_ok, move


def confirm_entry(df, ob_price, ob_high, ob_low, direction="BULL"):
    """
    STEP 5: Confirm Entry at Order Block
    
    Entry confirmation when:
    1. Price retests Order Block zone
    2. AND engulfing candle OR rejection wick OR displacement candle
    3. AND closes in reversal direction
    
    Returns: (entry_confirmed, entry_price, entry_candle)
    """
    if len(df) < 2:
        return False, None, None
    
    current = df.iloc[-1]
    previous = df.iloc[-2]
    
    curr_open = float(current["open"])
    curr_close = float(current["close"])
    curr_high = float(current["high"])
    curr_low = float(current["low"])
    
    prev_open = float(previous["open"])
    prev_close = float(previous["close"])
    
    body = abs(curr_close - curr_open)
    upper_wick = curr_high - max(curr_close, curr_open)
    lower_wick = min(curr_close, curr_open) - curr_low
    
    if direction == "BULL":
        # Bullish confirmation
        in_ob_zone = (curr_low <= ob_high and curr_low >= ob_low * 0.995)
        engulfing = (curr_open <= prev_close and curr_close > prev_open)
        rejection_wick = (lower_wick > body * 1.5 and curr_close > curr_open)
        displacement = (body > float(current.get("atr", body)) * 1.2)
        
        confirmed = in_ob_zone and (engulfing or rejection_wick or displacement)
        entry_price = curr_close if confirmed else None
        
        return confirmed, entry_price, current
    else:  # BEAR
        # Bearish confirmation
        in_ob_zone = (curr_high >= ob_low and curr_high <= ob_high * 1.005)
        engulfing = (curr_open >= prev_close and curr_close < prev_open)
        rejection_wick = (upper_wick > body * 1.5 and curr_close < curr_open)
        displacement = (body > float(current.get("atr", body)) * 1.2)
        
        confirmed = in_ob_zone and (engulfing or rejection_wick or displacement)
        entry_price = curr_close if confirmed else None
        
        return confirmed, entry_price, current


def calculate_sl_and_tp(entry_price, ob_high, ob_low, direction="BULL", min_rr=2.0):
    """
    STEP 6: Calculate Stop Loss and Take Profit
    
    SL = placed BEYOND the Order Block (invalidation level)
    TP = calculated for risk/reward ratio
    
    Returns: (sl_price, tp_price, risk_distance, rr_ratio)
    """
    if direction == "BULL":
        # Buy trade: SL below OB
        buffer = entry_price * 0.005  # 0.5% buffer
        sl = ob_low - buffer
        risk_dist = entry_price - sl
        tp = entry_price + (risk_dist * min_rr)
        rr = (tp - entry_price) / risk_dist if risk_dist != 0 else 0
        
        return round(sl, 2), round(tp, 2), round(risk_dist, 2), round(rr, 2)
    else:  # BEAR
        # Sell trade: SL above OB
        buffer = entry_price * 0.005
        sl = ob_high + buffer
        risk_dist = sl - entry_price
        tp = entry_price - (risk_dist * min_rr)
        rr = (entry_price - tp) / risk_dist if risk_dist != 0 else 0
        
        return round(sl, 2), round(tp, 2), round(risk_dist, 2), round(rr, 2)


def build_6step_checklist(df, symbol_key, direction="BULL"):
    """
    Combine all 6 steps into a complete checklist
    
    Returns: (checklist_dict, all_passed, signal_object)
    """
    config = MARKETS[symbol_key]
    
    # Step 1: BOS
    bos_ok, bos_price, swing_high, swing_low = identify_bos(df, direction)
    
    # Step 2: ChoCH
    choch_ok, choch_idx, choch_candle = detect_choch(df, direction)
    
    # Step 3: Order Block
    ob_price, ob_high, ob_low, ob_idx = mark_order_block(df, direction)
    ob_ok = ob_price is not None
    
    # Step 4: Liquidity Sweep (BONUS - not required)
    sweep_ok, sweep_price, sweep_idx, sweep_close = detect_liquidity_sweep(df, direction)
    
    # Step 5: Entry Confirmation
    entry_ok, entry_price, entry_candle = confirm_entry(df, ob_price, ob_high, ob_low, direction) if ob_ok else (False, None, None)
    
    # Build checklist
    checklist = {
        "step_1_bos": bos_ok,
        "step_2_choch": choch_ok,
        "step_3_order_block": ob_ok,
        "step_4_sweep": sweep_ok,
        "step_5_entry": entry_ok,
    }
    
    # All 6 steps must be true (sweep is bonus)
    # Actually: 1,2,3,5,6 must be true. 4 is bonus.
    all_passed = bos_ok and choch_ok and ob_ok and entry_ok
    
    if all_passed:
        # Step 6: SL & TP
        sl, tp, risk_dist, rr = calculate_sl_and_tp(entry_price, ob_high, ob_low, direction, config["min_rr"])
        
        if rr < config["min_rr"]:
            all_passed = False
        else:
            signal = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "symbol": symbol_key,
                "direction": direction,
                "status": "READY",
                "checklist": checklist,
                "sweep_detected": sweep_ok,
                "entry_price": entry_price,
                "stop_loss": sl,
                "take_profit": tp,
                "risk_distance": risk_dist,
                "risk_reward_ratio": rr,
                "ready_to_execute": True,
            }
            return checklist, all_passed, signal
    
    return checklist, all_passed, None


# ============================================================
# PART 2: DATA FETCHING
# ============================================================

def fetch_market_data(symbol_key, force_refresh=False):
    """
    Fetch OHLCV data from Yahoo Finance with caching
    """
    cache_key = symbol_key
    current_time = time.time()
    
    if cache_key in _data_cache and not force_refresh:
        cached_df, cached_ts = _data_cache[cache_key]
        if current_time - cached_ts < data_cache_duration:
            return cached_df
    
    try:
        yf_symbol = MARKETS[symbol_key]["yf_symbol"]
        interval = MARKETS[symbol_key]["interval"]
        
        df = yf.download(
            yf_symbol,
            period="15d",
            interval=interval,
            progress=False,
            auto_adjust=True
        )
        
        if df.empty:
            log.error(f"❌ No data received for {symbol_key}")
            return None
        
        # Normalize columns
        df.columns = [c.lower() for c in df.columns]
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
        
        # Add ATR
        df["atr"] = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], 14
        ).average_true_range()
        
        # Cache it
        _data_cache[cache_key] = (df, current_time)
        
        log.info(f"✅ Data loaded: {symbol_key} | {len(df)} candles")
        return df
    
    except Exception as e:
        log.error(f"❌ Data fetch error for {symbol_key}: {e}")
        return None


# ============================================================
# PART 3: SESSION FILTERING
# ============================================================

def is_active_session(symbol_key):
    """
    Check if current UTC time is in active trading session
    """
    start_hour, end_hour = MARKETS[symbol_key]["session_hours"]
    current_hour = datetime.now(timezone.utc).hour
    
    if not (start_hour <= current_hour < end_hour):
        return False, "Market Closed"
    
    # Map hour to session name
    if 7 <= current_hour < 12:
        session = "London"
    elif 13 <= current_hour < 15:
        session = "NY Killzone"
    elif 12 <= current_hour < 16:
        session = "NY+London"
    else:
        session = "Asian"
    
    active_sessions = MARKETS[symbol_key]["active_sessions"]
    
    if session in active_sessions:
        return True, session
    else:
        return False, session


# ============================================================
# PART 4: DUPLICATE SIGNAL PREVENTION
# ============================================================

def is_duplicate_signal(symbol_key, direction, cooldown_seconds=3600):
    """
    Prevent sending same signal twice within cooldown period
    """
    key = f"{symbol_key}_{direction}"
    current_time = time.time()
    
    if key in _last_signal:
        last_time = _last_signal[key]
        if current_time - last_time < cooldown_seconds:
            remaining = int(cooldown_seconds - (current_time - last_time))
            log.info(f"⏱️  Duplicate blocked: {key} ({remaining}s cooldown)")
            return True
    
    _last_signal[key] = current_time
    return False


# ============================================================
# PART 5: TELEGRAM INTEGRATION
# ============================================================

def send_telegram(message_text, retry_count=3):
    """
    Send message to Telegram with retry logic
    """
    for attempt in range(retry_count):
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": message_text,
                    "parse_mode": "Markdown"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                log.info("✅ Telegram sent")
                return True
            else:
                log.error(f"❌ Telegram error {response.status_code}")
                if attempt < retry_count - 1:
                    time.sleep(2)
        
        except Exception as e:
            log.error(f"❌ Telegram send error: {e}")
            if attempt < retry_count - 1:
                time.sleep(2)
    
    return False


def format_signal_message(signal, symbol_key):
    """
    Convert signal object to formatted Telegram message
    """
    direction = signal["direction"]
    emoji = "📈" if direction == "BULL" else "📉"
    
    checklist_items = [
        ("BOS", signal["checklist"]["step_1_bos"]),
        ("ChoCH", signal["checklist"]["step_2_choch"]),
        ("Order Block", signal["checklist"]["step_3_order_block"]),
        ("Sweep", signal["checklist"]["step_4_sweep"]),
        ("Entry", signal["checklist"]["step_5_entry"]),
    ]
    
    checklist_text = "\n".join([f"  {'✅' if v else '❌'} {k}" for k, v in checklist_items])
    
    config = MARKETS[symbol_key]
    decimals = config["decimals"]
    
    message = f"""
🎯 *TOPG 6-STEP REVERSAL SIGNAL*

*{symbol_key}* | {emoji} *{direction}*
⭐⭐⭐⭐⭐ HIGH PROBABILITY

*📍 Entry:* `{signal['entry_price']:.{decimals}f}`
*🛑 SL:* `{signal['stop_loss']:.{decimals}f}`
*🎯 TP:* `{signal['take_profit']:.{decimals}f}`

*📊 Risk/Reward:*
• Risk: `{signal['risk_distance']:.{decimals}f}`
• Reward: `{signal['risk_distance'] * signal['risk_reward_ratio']:.{decimals}f}`
• Ratio: `1:{signal['risk_reward_ratio']:.1f}`

*✅ 6-Step Checklist:*
{checklist_text}

*Signal Type:* Counter-Trend Reversal
*Timeframe:* 5M Entry / HTF Structure
*Status:* 🟢 READY TO EXECUTE

⚡ *Risk Management:*
  • SL = Below OB Structure
  • Exit if price closes SL
  • Move to +1R after entry
  • Trail stop above OB

📊 *Setup:* {'with' if signal['sweep_detected'] else 'without'} Liquidity Sweep

🔗 *Timestamp:* {signal['timestamp']}
"""
    
    return message


# ============================================================
# PART 6: SIGNAL LOGGING
# ============================================================

def log_signal_to_csv(signal, symbol_key):
    """
    Log signal to CSV for performance tracking
    """
    filename = "signals_log.csv"
    file_exists = os.path.isfile(filename)
    
    try:
        with open(filename, "a", newline="") as f:
            writer = csv.writer(f)
            
            if not file_exists:
                writer.writerow([
                    "timestamp", "symbol", "direction", "entry",
                    "stop_loss", "take_profit", "rr_ratio",
                    "step_1_bos", "step_2_choch", "step_3_ob",
                    "step_4_sweep", "step_5_entry"
                ])
            
            writer.writerow([
                signal["timestamp"],
                symbol_key,
                signal["direction"],
                signal["entry_price"],
                signal["stop_loss"],
                signal["take_profit"],
                signal["risk_reward_ratio"],
                signal["checklist"]["step_1_bos"],
                signal["checklist"]["step_2_choch"],
                signal["checklist"]["step_3_order_block"],
                signal["checklist"]["step_4_sweep"],
                signal["checklist"]["step_5_entry"],
            ])
            
            log.info(f"📝 Signal logged to CSV")
    
    except Exception as e:
        log.error(f"❌ CSV logging error: {e}")


# ============================================================
# PART 7: MAIN SIGNAL PROCESSING
# ============================================================

def process_symbol(symbol_key, test_direction=None):
    """
    Main entry point: process a single symbol
    """
    log.info(f"\n{'='*70}")
    log.info(f"Processing {symbol_key}")
    log.info(f"{'='*70}")
    
    # Session check
    active, session = is_active_session(symbol_key)
    if not active:
        log.info(f"⏰ Outside active session ({session})")
        return None
    
    log.info(f"✅ Active session: {session}")
    
    # Fetch data
    df = fetch_market_data(symbol_key)
    if df is None or len(df) < 100:
        log.error(f"❌ Insufficient data")
        return None
    
    # Process both directions
    directions_to_check = [test_direction] if test_direction else ["BULL", "BEAR"]
    
    for direction in directions_to_check:
        log.info(f"\nChecking {direction} setup...")
        
        # Duplicate filter
        if is_duplicate_signal(symbol_key, direction):
            continue
        
        # Run 6-step check
        checklist, all_passed, signal = build_6step_checklist(df, symbol_key, direction)
        
        checklist_score = sum(checklist.values())
        log.info(f"Checklist: {checklist_score}/5 items passed")
        
        for step, passed in checklist.items():
            status = "✅" if passed else "❌"
            log.info(f"  {status} {step}")
        
        if all_passed and signal:
            log.info(f"\n{'='*70}")
            log.info(f"🎯 SIGNAL READY: {symbol_key} {direction}")
            log.info(f"{'='*70}")
            
            # Send Telegram
            message = format_signal_message(signal, symbol_key)
            sent = send_telegram(message)
            
            if sent:
                # Log to CSV
                log_signal_to_csv(signal, symbol_key)
            
            return signal
    
    return None


# ============================================================
# PART 8: MAIN LOOP
# ============================================================

def main_loop(scan_interval=5, max_workers=4):
    """
    Continuous monitoring loop
    """
    log.info(f"\n{'#'*70}")
    log.info(f"# TOPG 6-STEP REVERSAL BOT v1.0")
    log.info(f"# Starting main loop (scan interval: {scan_interval}s)")
    log.info(f"#{'#'*68}")
    
    startup_msg = (
        f"🚀 *TOPG 6-STEP BOT ONLINE*\n\n"
        f"📊 *Monitoring:*\n"
        + "\n".join([f"  • {s}" for s in MARKETS.keys()]) +
        f"\n\n🔁 *Strategy:* Counter-Trend Reversals\n"
        f"⚡ *Method:* BOS → ChoCH → OB → Sweep → Entry → SL/TP\n"
        f"📈 *Status:* LIVE"
    )
    send_telegram(startup_msg)
    
    try:
        while True:
            try:
                # Scan all symbols in parallel
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = []
                    
                    for symbol_key in MARKETS.keys():
                        future = executor.submit(process_symbol, symbol_key)
                        futures.append((symbol_key, future))
                        time.sleep(0.3)
                    
                    # Collect results
                    for symbol_key, future in futures:
                        try:
                            future.result()
                        except Exception as e:
                            log.error(f"❌ Processing error {symbol_key}: {e}")
                
                log.info(f"Scan complete | Next scan in {scan_interval}s")
                time.sleep(scan_interval)
            
            except Exception as e:
                log.error(f"❌ Main loop error: {e}")
                time.sleep(scan_interval)
    
    except KeyboardInterrupt:
        log.info("\n⛔ Bot stopped by user")
        send_telegram("⛔ TOPG 6-Step Bot Stopped")


# ============================================================
# PART 9: CLI / TESTING INTERFACE
# ============================================================

def cli_test_symbol(symbol_key, direction=None):
    """
    Test a specific symbol from command line
    """
    log.info(f"Testing {symbol_key} {direction or 'both directions'}")
    signal = process_symbol(symbol_key, test_direction=direction)
    
    if signal:
        print("\n" + "="*70)
        print("SIGNAL READY")
        print("="*70)
        print(f"Symbol: {signal['symbol']}")
        print(f"Direction: {signal['direction']}")
        print(f"Entry: {signal['entry_price']}")
        print(f"SL: {signal['stop_loss']}")
        print(f"TP: {signal['take_profit']}")
        print(f"RR: {signal['risk_reward_ratio']}")
        print("="*70)
    else:
        print("\n❌ No signal ready")


def cli_show_markets():
    """
    Show available markets
    """
    print("\nAvailable Markets:")
    for symbol_key in MARKETS.keys():
        config = MARKETS[symbol_key]
        print(f"  • {symbol_key} ({config['yf_symbol']})")


def cli_show_signals():
    """
    Show recent signals from log
    """
    if not os.path.isfile("signals_log.csv"):
        print("No signals logged yet")
        return
    
    try:
        df = pd.read_csv("signals_log.csv")
        print(f"\nRecent Signals ({len(df)} total):")
        print(df.tail(10).to_string())
    except Exception as e:
        print(f"Error reading log: {e}")


# ============================================================
# MAIN ENTRY POINT
# ============================================================

if __name__ == "__main__":
    import sys
    
    # Check for Telegram credentials
    if TELEGRAM_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("""
╔════════════════════════════════════════════════════════════╗
║  SETUP REQUIRED: Edit TELEGRAM_TOKEN and TELEGRAM_CHAT_ID  ║
║                                                            ║
║  1. Get token from @BotFather on Telegram                 ║
║  2. Get chat ID: message @userinfobot                      ║
║  3. Edit lines in this file:                              ║
║     TELEGRAM_TOKEN = "YOUR_TOKEN_HERE"                    ║
║     TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"                ║
║                                                            ║
║  Or set environment variables:                            ║
║     export TELEGRAM_TOKEN="..."                           ║
║     export TELEGRAM_CHAT_ID="..."                         ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
        """)
        sys.exit(1)
    
    if len(sys.argv) > 1:
        command = sys.argv[1].lower()
        
        if command == "test":
            # Test specific symbol
            symbol = sys.argv[2] if len(sys.argv) > 2 else "XAU/USD"
            direction = sys.argv[3] if len(sys.argv) > 3 else None
            cli_test_symbol(symbol, direction)
        
        elif command == "list":
            cli_show_markets()
        
        elif command == "signals":
            cli_show_signals()
        
        elif command == "run":
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 5
            main_loop(scan_interval=interval)
        
        else:
            print(f"""
TOPG 6-Step Reversal Bot - Commands:

  python TOPG_COMPLETE_BOT.py run [interval]
    • Run continuous monitoring (default: 5s scan interval)
    • Example: python TOPG_COMPLETE_BOT.py run 10

  python TOPG_COMPLETE_BOT.py test [symbol] [direction]
    • Test specific symbol for signals
    • Example: python TOPG_COMPLETE_BOT.py test XAU/USD BULL

  python TOPG_COMPLETE_BOT.py list
    • Show available markets

  python TOPG_COMPLETE_BOT.py signals
    • Show recent signals from log

SETUP:
  1. pip install pandas numpy ta yfinance requests
  2. Edit TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in this file
  3. Run: python TOPG_COMPLETE_BOT.py run

Logs: Check topg_bot.log for detailed output
            """)
    else:
        # Default: run continuous monitoring
        main_loop(scan_interval=5)
