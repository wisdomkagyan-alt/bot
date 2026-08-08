# ============================================================
# INTEGRATION: TOPG 6-STEP ENGINE + TELEGRAM BOT
# 
# This shows how to integrate topg_6step_strategy.py with your
# Telegram trading bot for live signal generation.
# ============================================================

import logging
import requests
import pandas as pd
from datetime import datetime, timezone
from topg_6step_strategy import topg_6step_signal, STRATEGY_CONFIG
import yfinance as yf

log = logging.getLogger("TOPG_BOT_INTEGRATION")

# ============================================================
# TELEGRAM CONFIGURATION
# ============================================================
TELEGRAM_TOKEN = "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU"
TELEGRAM_CHAT_ID = "8783763018"

# ============================================================
# MARKET CONFIGURATION
# ============================================================
MARKETS = {
    "XAU/USD": {
        "yf_symbol": "GC=F",
        "interval": "5m",
        "session_hours": (7, 20),  # UTC
        "active_sessions": ["London", "NY Killzone"],
    },
    "NAS100": {
        "yf_symbol": "^NDX",
        "interval": "5m",
        "session_hours": (13, 21),
        "active_sessions": ["London", "NY Killzone"],
    },
}

# ============================================================
# TELEGRAM SENDER
# ============================================================
def send_telegram_signal(signal_data, symbol_key):
    """
    Convert the 6-step signal into a formatted Telegram message
    """
    if not signal_data or not signal_data.get("ready_to_execute"):
        return False
    
    direction = signal_data["direction"]
    emoji = "📈" if direction == "BULL" else "📉"
    
    # Build checklist visual
    checklist_items = [
        ("Step 1: BOS", signal_data["step_1_bos"]["confirmed"]),
        ("Step 2: ChoCH", signal_data["step_2_choch"]["confirmed"]),
        ("Step 3: Order Block", True),  # Always True if we got here
        ("Step 4: Sweep", signal_data["step_4_sweep"]["detected"]),
        ("Step 5: Entry", signal_data["step_5_entry"]["confirmed"]),
        ("Step 6: SL/TP", True),  # Always True if we got here
    ]
    
    checklist_text = "\n".join([f"  {'✅' if v else '❌'} {k}" for k, v in checklist_items])
    
    # Calculate risk/reward metrics
    entry = signal_data["entry_price"]
    sl = signal_data["stop_loss"]
    tp = signal_data["take_profit"]
    risk = abs(entry - sl)
    reward = abs(tp - entry)
    
    # Format message
    message = f"""
🎯 *TOPG 6-STEP REVERSAL SIGNAL*

*{symbol_key}* | {emoji} *{direction}*
⭐⭐⭐⭐⭐ HIGH PROBABILITY SETUP

*Entry:* {entry:.2f}
*Stop Loss:* {sl:.2f}
*Take Profit:* {tp:.2f}

*Risk:* {risk:.2f}
*Reward:* {reward:.2f}
*RR Ratio:* 1:{signal_data["risk_reward_ratio"]:.2f}

*6-Step Checklist:*
{checklist_text}

*Signal Type:* Counter-Trend Reversal
*Timeframe:* 5M Entry / HTF Structure
*Status:* 🟢 READY TO EXECUTE

⚡ Risk Management:
   • Stop Loss = Below OB Structure
   • Exit if SL closes broken
   • Move to breakeven at +1R
   • Trail profit above OB zone

🔗 *Source:* TopG QML Reversal Strategy
📊 *Setup:* {signal_data["step_4_sweep"]["detected"] and 'with' or 'without'} Liquidity Sweep

Timestamp: {signal_data["timestamp"]}
"""
    
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            },
            timeout=10
        )
        
        if response.status_code == 200:
            log.info(f"✅ Signal sent to Telegram | {symbol_key} {direction}")
            return True
        else:
            log.error(f"❌ Telegram error {response.status_code}")
            return False
    
    except Exception as e:
        log.error(f"❌ Telegram send failed: {e}")
        return False


# ============================================================
# DATA FETCHING (with caching)
# ============================================================
_data_cache = {}

def fetch_market_data(symbol_key, force_refresh=False):
    """
    Fetch latest OHLCV data from Yahoo Finance
    Caches for 50 seconds to avoid rate limiting
    """
    cache_key = symbol_key
    current_time = datetime.now(timezone.utc).timestamp()
    
    # Check cache
    if cache_key in _data_cache and not force_refresh:
        cached_df, cached_ts = _data_cache[cache_key]
        if current_time - cached_ts < 50:  # 50s cache
            log.debug(f"Using cached data for {symbol_key}")
            return cached_df
    
    # Fetch fresh data
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
            log.error(f"No data received for {symbol_key}")
            return None
        
        # Normalize columns
        df.columns = [c.lower() for c in df.columns]
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        df = df[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
        
        # Add ATR
        import ta
        df["atr"] = ta.volatility.AverageTrueRange(
            df["high"], df["low"], df["close"], 14
        ).average_true_range()
        
        # Cache it
        _data_cache[cache_key] = (df, current_time)
        
        log.info(f"✅ Fresh data loaded for {symbol_key} | {len(df)} candles")
        return df
    
    except Exception as e:
        log.error(f"Data fetch error for {symbol_key}: {e}")
        return None


# ============================================================
# SESSION FILTER
# ============================================================
def is_active_session(symbol_key):
    """
    Check if current time is in an active trading session for the symbol
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
# SIGNAL FILTERING (Prevent duplicate signals)
# ============================================================
_last_signal = {}

def is_duplicate_signal(symbol_key, direction, cooldown_seconds=3600):
    """
    Check if a signal was just sent for this symbol/direction
    """
    key = f"{symbol_key}_{direction}"
    current_time = datetime.now(timezone.utc).timestamp()
    
    if key in _last_signal:
        last_time = _last_signal[key]
        if current_time - last_time < cooldown_seconds:
            remaining = int(cooldown_seconds - (current_time - last_time))
            log.info(f"Duplicate signal blocked for {key} ({remaining}s cooldown)")
            return True
    
    _last_signal[key] = current_time
    return False


# ============================================================
# MAIN SIGNAL PROCESSING
# ============================================================
def process_symbol(symbol_key, test_direction=None):
    """
    Main entry point: fetch data, run 6-step check, send signal if ready
    
    Args:
        symbol_key: "XAU/USD", "NAS100", etc.
        test_direction: "BULL" or "BEAR" (if None, checks both)
    """
    log.info(f"\n{'='*70}")
    log.info(f"Processing {symbol_key}")
    log.info(f"{'='*70}")
    
    # SESSION CHECK
    active, session = is_active_session(symbol_key)
    if not active:
        log.info(f"⏰ Outside active session ({session})")
        return
    
    log.info(f"✅ Active session: {session}")
    
    # FETCH DATA
    df = fetch_market_data(symbol_key)
    if df is None or len(df) < 100:
        log.error(f"Insufficient data for {symbol_key}")
        return
    
    log.info(f"Data loaded: {len(df)} candles")
    
    # GET SIGNAL CONFIG
    config = STRATEGY_CONFIG.get(symbol_key, {})
    
    # CHECK BOTH DIRECTIONS
    directions_to_check = [test_direction] if test_direction else ["BULL", "BEAR"]
    
    for direction in directions_to_check:
        log.info(f"\nChecking {direction} setup...")
        
        # DUPLICATE FILTER
        if is_duplicate_signal(symbol_key, direction):
            continue
        
        # RUN 6-STEP ENGINE
        signal = topg_6step_signal(df, symbol=symbol_key, direction=direction, config=config)
        
        if signal and signal.get("ready_to_execute"):
            log.info(f"\n{'='*70}")
            log.info(f"✅ SIGNAL READY FOR {symbol_key} {direction}")
            log.info(f"{'='*70}")
            
            # SEND TO TELEGRAM
            sent = send_telegram_signal(signal, symbol_key)
            
            if sent:
                # Log signal to file
                log_signal_to_file(signal)
            
            return signal
    
    log.info(f"No signals ready for {symbol_key}")
    return None


# ============================================================
# SIGNAL LOGGING
# ============================================================
def log_signal_to_file(signal_data, filename="signals_log.csv"):
    """
    Log every signal to CSV for backtesting and tracking
    """
    import csv
    import os
    
    file_exists = os.path.isfile(filename)
    
    try:
        with open(filename, "a", newline="") as f:
            writer = csv.writer(f)
            
            if not file_exists:
                # Write header
                writer.writerow([
                    "timestamp", "symbol", "direction",
                    "entry_price", "stop_loss", "take_profit",
                    "risk_reward_ratio", "bos_confirmed", "choch_confirmed",
                    "sweep_detected", "entry_confirmed"
                ])
            
            # Write signal data
            writer.writerow([
                signal_data["timestamp"],
                signal_data["symbol"],
                signal_data["direction"],
                signal_data["entry_price"],
                signal_data["stop_loss"],
                signal_data["take_profit"],
                signal_data["risk_reward_ratio"],
                signal_data["step_1_bos"]["confirmed"],
                signal_data["step_2_choch"]["confirmed"],
                signal_data["step_4_sweep"]["detected"],
                signal_data["step_5_entry"]["confirmed"],
            ])
            
            log.info(f"✅ Signal logged to {filename}")
    
    except Exception as e:
        log.error(f"Failed to log signal: {e}")


# ============================================================
# MAIN LOOP (for continuous monitoring)
# ============================================================
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

def main_loop(scan_interval=5):
    """
    Continuous monitoring loop - runs forever
    
    Args:
        scan_interval: seconds between scans
    """
    log.info("🚀 TOPG 6-STEP BOT STARTED")
    
    # Send startup message
    send_telegram_alert(
        f"✅ TOPG 6-Step Bot Online\n"
        f"Monitoring: {', '.join(MARKETS.keys())}\n"
        f"Strategy: Counter-Trend Reversals\n"
        f"Method: BOS → ChoCH → OB → Sweep → Entry → SL/TP"
    )
    
    try:
        while True:
            try:
                # Scan all symbols in parallel
                with ThreadPoolExecutor(max_workers=len(MARKETS)) as executor:
                    futures = []
                    
                    for symbol_key in MARKETS.keys():
                        future = executor.submit(process_symbol, symbol_key)
                        futures.append((symbol_key, future))
                        time.sleep(0.5)  # Stagger requests
                    
                    # Collect results
                    for symbol_key, future in futures:
                        try:
                            future.result()
                        except Exception as e:
                            log.error(f"Error processing {symbol_key}: {e}")
                
                # Wait before next scan
                time.sleep(scan_interval)
            
            except Exception as e:
                log.error(f"Scan loop error: {e}")
                time.sleep(scan_interval)
    
    except KeyboardInterrupt:
        log.info("Bot stopped by user")
        send_telegram_alert("⛔ TOPG 6-Step Bot Stopped")


def send_telegram_alert(text):
    """Send a plain text alert (non-signal message)"""
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=5
        )
    except:
        pass


# ============================================================
# CLI / TESTING
# ============================================================
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(name)s | %(message)s"
    )
    
    if len(sys.argv) > 1:
        # Test a specific symbol/direction
        # Usage: python integration.py XAU/USD BULL
        symbol = sys.argv[1]
        direction = sys.argv[2] if len(sys.argv) > 2 else None
        
        log.info(f"Testing {symbol} {direction or 'both directions'}")
        signal = process_symbol(symbol, test_direction=direction)
        
        if signal:
            print("\n" + "="*70)
            print("SIGNAL OBJECT:")
            print("="*70)
            for key, value in signal.items():
                print(f"{key}: {value}")
    
    else:
        # Run continuous bot
        main_loop(scan_interval=5)
