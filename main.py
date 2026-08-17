# PA-SUPREME-2026 — A+ TRADE-ONLY HTF/PO3/SWEEP/MSS/FVG ENGINE
# Telegram: ONLY final A+ TRADE alerts. PRE/WATCH alerts are disabled.
# Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID as environment variables.

import csv, gc, logging, math, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from threading import Lock
import pandas as pd
import requests
import yfinance as yf

SYSTEM_VERSION = "PA-SUPREME-2026-A-PLUS-TRADE-ONLY"
SCAN_INTERVAL = 1.0
DATA_REFRESH_INTERVAL = 15.0
TRADE_COOLDOWN = 1800
SETUP_MEMORY_SECONDS = 7200
ONE_TRADE_PER_SESSION = True
RISK_PER_TRADE = 50.0
MIN_RR = 1.80
SWING_LEFT, SWING_RIGHT = 2, 2
MSS_LOOKBACK = 30
FVG_MIN_ATR = 0.05
FVG_MAX_AGE = 12
DISPLACEMENT_MULT = 1.20
REQUIRE_HTF_ALIGNMENT = True
REQUIRE_DISPLACEMENT = True
REQUIRE_FRESH_FVG = True
REQUIRE_5M_RETEST = True

TOKEN = os.getenv("TOKEN", "8641333494:AAHFkQKnzHsebgk5AIio1_-hGuh38TN2wpU")
CHAT_ID = os.getenv("CHAT_ID", "8783763018")

http = requests.Session()
tg_lock = Lock()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(SYSTEM_VERSION)

MARKETS = {
    "XAU/USD":{"data":"GC=F","execution":"XAUUSD","decimals":2,"market":"global","min_sl":1.50,"dpp":100.0,"lot_cap":1.50},
    "NAS100":{"data":"^NDX","execution":"NAS100","decimals":1,"market":"global","min_sl":12.0,"dpp":10.0,"lot_cap":2.0},
    "SPX500":{"data":"^GSPC","execution":"SPX500","decimals":1,"market":"global","min_sl":6.0,"dpp":10.0,"lot_cap":2.0},
    "EUR/USD":{"data":"EURUSD=X","execution":"EURUSD","decimals":5,"market":"global","min_sl":0.00025,"dpp":100000.0,"lot_cap":3.0},
    "GBP/JPY":{"data":"GBPJPY=X","execution":"GBPJPY","decimals":3,"market":"global","min_sl":0.040,"dpp":1000.0,"lot_cap":2.0},
    "NIFTY50":{"data":"^NSEI","execution":"NIFTY50","decimals":2,"market":"india","min_sl":15.0,"dpp":50.0,"lot_cap":50.0},
    "BANKNIFTY":{"data":"^NSEBANK","execution":"BANKNIFTY","decimals":2,"market":"india","min_sl":20.0,"dpp":20.0,"lot_cap":50.0},
    "SENSEX":{"data":"^BSESN","execution":"SENSEX","decimals":2,"market":"india","min_sl":40.0,"dpp":10.0,"lot_cap":50.0},
    "RELIANCE":{"data":"RELIANCE.NS","execution":"RELIANCE","decimals":2,"market":"india","min_sl":5.0,"dpp":1.0,"lot_cap":500.0},
    "TCS":{"data":"TCS.NS","execution":"TCS","decimals":2,"market":"india","min_sl":8.0,"dpp":1.0,"lot_cap":500.0},
}
SYMBOLS = list(MARKETS)
frames_cache, frames_cache_time = {}, {}
cache_lock = Lock()
last_alert, setup_memory = {}, {}
session_trade_count = {s:{"session":None,"count":0} for s in SYMBOLS}
daily_date = datetime.now(timezone.utc).date()

CSV_FILE = "signals_log.csv"
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE,"w",newline="",encoding="utf-8") as f:
        csv.writer(f).writerow(["timestamp","symbol","direction","stage","setup","price","sl","tp1","tp2","tp3","rr","session","htf_sweep","mss","fvg"])

def send_telegram(message):
    if not TOKEN or not CHAT_ID:
        log.warning("Telegram disabled: set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID")
        return False
    url=f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload={"chat_id":CHAT_ID,"text":message,"parse_mode":"Markdown","disable_web_page_preview":True}
    with tg_lock:
        for attempt in range(3):
            try:
                r=http.post(url,json=payload,timeout=10)
                if r.ok:return True
                log.error("Telegram HTTP %s: %s",r.status_code,r.text[:300])
            except Exception as e:log.error("Telegram attempt %s failed: %s",attempt+1,e)
            time.sleep(1)
    return False

def current_session(symbol):
    now=datetime.now(timezone.utc); m=now.hour*60+now.minute
    if MARKETS[symbol]["market"]=="india": return "India" if 225<=m<600 else None
    if 60<=m<360:return "Asia"
    if 420<=m<720:return "London"
    if 720<=m<1020:return "NY"
    return None

def weekend_block():
    now=datetime.now(timezone.utc)
    return now.weekday()==5 or (now.weekday()==6 and now.hour<21)

def normalize_yahoo(raw):
    if raw is None or raw.empty:return None
    if isinstance(raw.columns,pd.MultiIndex):raw.columns=raw.columns.get_level_values(0)
    raw.columns=[str(c).lower() for c in raw.columns]
    if any(c not in raw.columns for c in ["open","high","low","close"]):return None
    if "volume" not in raw.columns:raw["volume"]=0
    df=raw[["open","high","low","close","volume"]].copy()
    for c in df:df[c]=pd.to_numeric(df[c],errors="coerce")
    return df.replace([math.inf,-math.inf],pd.NA).dropna(subset=["open","high","low","close"]).loc[lambda x:~x.index.duplicated(keep="last")]

def fetch_5m(symbol):
    for _ in range(2):
        try:
            raw=yf.download(MARKETS[symbol]["data"],period="5d",interval="5m",progress=False,auto_adjust=False,threads=False)
            df=normalize_yahoo(raw)
            if df is not None and len(df)>=100:return df
        except Exception as e:log.error("Yahoo fetch %s: %s",symbol,e)
        time.sleep(.5)
    return None

def resample_ohlc(df,rule):
    return df.resample(rule).agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["open","high","low","close"])

def refresh_symbol(symbol):
    base=fetch_5m(symbol)
    if base is None:return None
    frames={"5M":base,"15M":resample_ohlc(base,"15min"),"1H":resample_ohlc(base,"1h")}
    if any(len(x)<30 for x in frames.values()):return None
    with cache_lock:frames_cache[symbol]=frames;frames_cache_time[symbol]=time.time()
    return frames

def get_frames(symbol):
    with cache_lock:
        f=frames_cache.get(symbol);t=frames_cache_time.get(symbol,0)
    return f if f is not None and time.time()-t<DATA_REFRESH_INTERVAL else refresh_symbol(symbol)

def body(c):return abs(float(c.close)-float(c.open))
def bullish(c):return float(c.close)>float(c.open)
def bearish(c):return float(c.close)<float(c.open)

def atr(df,period=14):
    if len(df)<period+2:return 0.0
    h,l,c=df.high.astype(float),df.low.astype(float),df.close.astype(float);pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    v=tr.rolling(period).mean().iloc[-1]
    return 0.0 if pd.isna(v) else float(v)

def avg_body(df,n=10):
    v=(df.close-df.open).abs().tail(n).mean();return 0.0 if pd.isna(v) else float(v)

def swing_highs(df):
    out=[]
    if len(df)<SWING_LEFT+SWING_RIGHT+1:return out
    for i in range(SWING_LEFT,len(df)-SWING_RIGHT):
        v=float(df.high.iloc[i])
        if v>float(df.high.iloc[i-SWING_LEFT:i].max()) and v>=float(df.high.iloc[i+1:i+SWING_RIGHT+1].max()):out.append((i,v))
    return out

def swing_lows(df):
    out=[]
    if len(df)<SWING_LEFT+SWING_RIGHT+1:return out
    for i in range(SWING_LEFT,len(df)-SWING_RIGHT):
        v=float(df.low.iloc[i])
        if v<float(df.low.iloc[i-SWING_LEFT:i].min()) and v<=float(df.low.iloc[i+1:i+SWING_RIGHT+1].min()):out.append((i,v))
    return out

def po3_context(df1):
    if len(df1)<4:return {"phase":"UNKNOWN","bias":"NEUTRAL"}
    p=df1.iloc[-2];cur=df1.iloc[-1];o,h,l,c=map(float,[p.open,p.high,p.low,p.close]);price=float(cur.close)
    if price>h:phase="EXPANSION_ABOVE"
    elif price<l:phase="EXPANSION_BELOW"
    elif price<o:phase="MANIPULATION_BELOW_OPEN"
    elif price>o:phase="DISTRIBUTION_ABOVE_OPEN"
    else:phase="ACCUMULATION_NEAR_OPEN"
    bias="BULLISH" if c>o else "BEARISH" if c<o else "NEUTRAL"
    return {"phase":phase,"bias":bias,"open":o,"high":h,"low":l,"close":c,"mid":(h+l)/2}

def detect_htf_sweep(df1):
    if len(df1)<4:return None
    p=df1.iloc[-3];c=df1.iloc[-2]
    ph,pl=float(p.high),float(p.low);ch,cl,cc=map(float,[c.high,c.low,c.close])
    if cl<pl and cc>=pl:return {"direction":"BUY","level":pl,"sweep_extreme":cl,"candle_range":ch-cl}
    if ch>ph and cc<=ph:return {"direction":"SELL","level":ph,"sweep_extreme":ch,"candle_range":ch-cl}
    return None

def structure_shift(df15,direction):
    if len(df15)<20:return None
    closed=df15.iloc[:-1];search=closed.iloc[max(0,len(closed)-MSS_LOOKBACK):]
    if direction=="BUY":
        hs=swing_highs(search)
        if hs and float(closed.iloc[-1].close)>hs[-1][1]:return {"direction":"BUY","level":hs[-1][1],"type":"BULLISH_MSS"}
    else:
        ls=swing_lows(search)
        if ls and float(closed.iloc[-1].close)<ls[-1][1]:return {"direction":"SELL","level":ls[-1][1],"type":"BEARISH_MSS"}
    return None

def displacement_ok(df15,direction):
    if len(df15)<15:return False
    closed=df15.iloc[:-1];last=closed.iloc[-1];avg=avg_body(closed.iloc[:-1].tail(10),10)
    if avg<=0 or body(last)<avg*DISPLACEMENT_MULT:return False
    return bullish(last) if direction=="BUY" else bearish(last)

def find_recent_fvg(df,direction):
    if len(df)<10:return None
    closed=df.iloc[:-1];start=max(2,len(closed)-FVG_MAX_AGE)
    for i in range(len(closed)-1,start-1,-1):
        c1,c2,c3=closed.iloc[i-2],closed.iloc[i-1],closed.iloc[i];a=atr(closed.iloc[:i+1])
        if a<=0:continue
        if direction=="BUY":
            lo,hi=float(c1.high),float(c3.low)
            if hi<=lo or hi-lo<a*FVG_MIN_ATR or not bullish(c2):continue
        else:
            lo,hi=float(c3.high),float(c1.low)
            if hi<=lo or hi-lo<a*FVG_MIN_ATR or not bearish(c2):continue
        return {"direction":direction,"low":lo,"high":hi,"index":i,"gap":hi-lo,"mid":(lo+hi)/2}
    return None

def fvg_is_fresh(df15,fvg):
    closed=df15.iloc[:-1];age=len(closed)-1-fvg["index"]
    if age<0 or age>FVG_MAX_AGE:return False
    later=closed.iloc[fvg["index"]+1:]
    for _,c in later.iterrows():
        if fvg["direction"]=="BUY" and float(c.high)<fvg["low"] and float(c.close)<fvg["low"]:return False
        if fvg["direction"]=="SELL" and float(c.low)>fvg["high"] and float(c.close)>fvg["high"]:return False
    return True

def fvg_retest_confirmation(df5,fvg,direction):
    if len(df5)<10:return None
    c=df5.iloc[:-1].iloc[-1];lo,hi,cl,op=map(float,[c.low,c.high,c.close,c.open])
    touched=lo<=fvg["high"] and hi>=fvg["low"]
    if not touched:return None
    if direction=="BUY" and cl>=fvg["mid"] and cl>op:return {"entry":cl,"reason":"5M bullish FVG retest/rejection"}
    if direction=="SELL" and cl<=fvg["mid"] and cl<op:return {"entry":cl,"reason":"5M bearish FVG retest/rejection"}
    return None

def calculate_sl(symbol,direction,entry,sweep):
    cfg=MARKETS[symbol];rng=abs(float(sweep["candle_range"]));buffer=max(cfg["min_sl"]*.10,rng*.05)
    sl=float(sweep["sweep_extreme"])-buffer if direction=="BUY" else float(sweep["sweep_extreme"])+buffer
    distance=entry-sl if direction=="BUY" else sl-entry
    if distance<=0:return None
    distance=max(distance,cfg["min_sl"]);max_sl=max(cfg["min_sl"]*5,rng*1.5)
    if distance>max_sl:return None
    return sl,distance

def target_levels(frames,direction,entry):
    levels=[]
    for name in ("5M","15M","1H"):
        df=frames[name].iloc[:-1]
        if len(df)<20:continue
        if direction=="BUY":levels += [v for _,v in swing_highs(df) if v>entry]
        else:levels += [v for _,v in swing_lows(df) if v<entry]
    return sorted(set(round(float(x),8) for x in levels))

def adaptive_targets(frames,direction,entry,sl_distance):
    if sl_distance<=0:return None
    min_dist=sl_distance*MIN_RR;levels=target_levels(frames,direction,entry)
    if direction=="BUY":
        valid=[x for x in levels if x>=entry+min_dist]
        if not valid:return None
        tp3=min(valid);tp1=entry+sl_distance;tp2=min(entry+2*sl_distance,tp3);rr=(tp3-entry)/sl_distance
    else:
        valid=[x for x in levels if x<=entry-min_dist]
        if not valid:return None
        tp3=max(valid);tp1=entry-sl_distance;tp2=max(entry-2*sl_distance,tp3);rr=(entry-tp3)/sl_distance
    return {"tp1":tp1,"tp2":tp2,"tp3":tp3,"rr":rr} if rr>=MIN_RR else None

def lot_size(symbol,sl_distance):
    cfg=MARKETS[symbol]
    raw=RISK_PER_TRADE/(sl_distance*cfg["dpp"]) if sl_distance>0 else 0
    return round(max(.01,min(raw,cfg["lot_cap"])),3)

def setup_id(symbol,direction,sweep,mss,fvg):
    d=MARKETS[symbol]["decimals"]
    return (symbol,direction,round(float(sweep["level"]),d),round(float(mss["level"]),d),round(fvg["low"],d),round(fvg["high"],d))

def already_alerted(key):
    now=time.time();prev=last_alert.get(key,0)
    if now-prev<TRADE_COOLDOWN:return True
    last_alert[key]=now;return False

def trade_allowed(symbol,session):
    if not ONE_TRADE_PER_SESSION:return True
    s=session_trade_count[symbol]
    if s["session"]!=session:s.update(session=session,count=0)
    return s["count"]<1

def consume_trade(symbol,session):
    s=session_trade_count[symbol]
    if s["session"]!=session:s.update(session=session,count=0)
    s["count"]+=1

def fmt(symbol,v):return "N/A" if v is None else f"{float(v):,.{MARKETS[symbol]['decimals']}f}"

def log_signal(symbol,direction,entry,sl,t,session,sweep,mss,fvg):
    with open(CSV_FILE,"a",newline="",encoding="utf-8") as f:
        csv.writer(f).writerow([datetime.now(timezone.utc).isoformat(),symbol,direction,"TRADE","A_PLUS_HTF_SWEEP_MSS_DISPLACEMENT_FVG_RETEST",entry,sl,t["tp1"],t["tp2"],t["tp3"],t["rr"],session,sweep["level"],mss["level"],f"{fvg['low']}->{fvg['high']}"])

def send_trade(symbol,direction,entry,sl,t,lot,sweep,mss,fvg,context,session):
    arrow="📈" if direction=="BUY" else "📉"
    msg=(
        "🚨 *PA-SUPREME A+ TRADE SIGNAL*\n\n"
        f"*{MARKETS[symbol]['execution']}*\n{arrow} *{direction}*\n\n"
        f"Entry: *{fmt(symbol,entry)}*\nSL: *{fmt(symbol,sl)}*\n\n"
        f"TP1: *{fmt(symbol,t['tp1'])}*\nTP2: *{fmt(symbol,t['tp2'])}*\nTP3: *{fmt(symbol,t['tp3'])}*\n\n"
        f"RR: *1:{t['rr']:.2f}*\nRisk: *${RISK_PER_TRADE:.2f}*\nLot: *{lot}*\n\n"
        "*A+ CONFIRMATION*\n✓ 1H HTF / PO3\n✓ 1H liquidity sweep\n✓ HTF alignment\n✓ 15M MSS\n✓ 15M displacement\n✓ Fresh 15M FVG\n✓ 5M FVG retest\n✓ 5M rejection\n✓ Structure TP\n"
        f"✓ RR ≥ 1:{MIN_RR:.2f}\n\n"
        f"Sweep: *{fmt(symbol,sweep['level'])}*\nMSS: *{fmt(symbol,mss['level'])}*\n"
        f"FVG: *{fmt(symbol,fvg['low'])} → {fmt(symbol,fvg['high'])}*\n"
        f"PO3: *{context['phase']}*\nHTF: *{context['bias']}*\nSession: *{session}*\n\n"
        "🔒 *TRADE-ONLY MODE — NO PRE/WATCH ALERTS*"
    )
    send_telegram(msg)

def process_symbol(symbol):
    try:
        if weekend_block():return
        session=current_session(symbol)
        if session is None:return
        frames=get_frames(symbol)
        if frames is None:return
        df1,df15,df5=frames["1H"],frames["15M"],frames["5M"]
        if min(len(df1),len(df15),len(df5))<30:return

        context=po3_context(df1)
        sweep=detect_htf_sweep(df1)
        if sweep is None:return
        direction=sweep["direction"]

        if REQUIRE_HTF_ALIGNMENT:
            aligned=(context["bias"]=="BULLISH" or context["phase"]=="MANIPULATION_BELOW_OPEN") if direction=="BUY" else (context["bias"]=="BEARISH" or context["phase"]=="DISTRIBUTION_ABOVE_OPEN")
            if not aligned:return

        mss=structure_shift(df15,direction)
        if mss is None:return
        if REQUIRE_DISPLACEMENT and not displacement_ok(df15,direction):return
        fvg=find_recent_fvg(df15,direction)
        if fvg is None:return
        if REQUIRE_FRESH_FVG and not fvg_is_fresh(df15,fvg):return

        key=setup_id(symbol,direction,sweep,mss,fvg)
        confirmation=fvg_retest_confirmation(df5,fvg,direction) if REQUIRE_5M_RETEST else {"entry":float(df5.iloc[-2].close)}
        if confirmation is None:return
        if already_alerted(key):return
        if not trade_allowed(symbol,session):return

        entry=float(confirmation["entry"])
        sl_data=calculate_sl(symbol,direction,entry,sweep)
        if sl_data is None:return
        sl,sl_distance=sl_data
        targets=adaptive_targets(frames,direction,entry,sl_distance)
        if targets is None:return
        lot=lot_size(symbol,sl_distance)

        send_trade(symbol,direction,entry,sl,targets,lot,sweep,mss,fvg,context,session)
        log_signal(symbol,direction,entry,sl,targets,session,sweep,mss,fvg)
        consume_trade(symbol,session)
        setup_memory[key]=time.time()
        log.info("A+ TRADE %s %s entry=%s SL=%s TP3=%s RR=1:%.2f",symbol,direction,fmt(symbol,entry),fmt(symbol,sl),fmt(symbol,targets['tp3']),targets['rr'])
    except Exception as e:
        log.exception("process_symbol failed %s: %s",symbol,e)

def startup_message():
    return ("⚡ *PA-SUPREME-2026 A+ LIVE*\n\n"
            "🔎 *TRADE ALERTS ONLY*\n\n"
            "1H = HTF / PO3\n1H = liquidity sweep\n15M = MSS + displacement\n"
            "15M = FVG\n5M = FVG retest + rejection\n\n"
            f"⚖️ Minimum RR = 1:{MIN_RR:.2f}\n"
            "🎯 TP3 = opposing structure/liquidity\n"
            "🛑 SL = sweep structure\n🚫 PRE OFF\n🚫 WATCH OFF\n"
            "🚫 EMA / RSI / MACD / ADX scoring OFF\n🔒 Closed-candle confirmation\n\n"
            "ONLY A+ SETUPS → TELEGRAM")

def reset_daily_state():
    global daily_date
    today=datetime.now(timezone.utc).date()
    if today==daily_date:return
    daily_date=today;setup_memory.clear();last_alert.clear()
    for s in SYMBOLS:session_trade_count[s]={"session":None,"count":0}

def main():
    log.info("%s STARTED",SYSTEM_VERSION)
    if TOKEN and CHAT_ID:send_telegram(startup_message())
    else:log.warning("Set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in Railway")
    last_refresh=0;loop=0
    while True:
        try:
            reset_daily_state();now=time.time()
            if now-last_refresh>=DATA_REFRESH_INTERVAL:
                with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as ex:
                    fs=[ex.submit(refresh_symbol,s) for s in SYMBOLS]
                    for f in as_completed(fs):
                        try:f.result()
                        except Exception as e:log.error("Refresh error: %s",e)
                last_refresh=time.time()
            log.info("A+ SILENT SCAN #%s",loop)
            with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as ex:
                fs=[ex.submit(process_symbol,s) for s in SYMBOLS]
                for f in as_completed(fs):
                    try:f.result()
                    except Exception as e:log.error("Worker error: %s",e)
            cutoff=time.time()-SETUP_MEMORY_SECONDS
            for k,v in list(setup_memory.items()):
                if v<cutoff:setup_memory.pop(k,None)
            loop+=1;gc.collect();time.sleep(SCAN_INTERVAL)
        except KeyboardInterrupt:break
        except Exception as e:
            log.exception("MAIN LOOP ERROR: %s",e);time.sleep(3)

if __name__=="__main__":main()
