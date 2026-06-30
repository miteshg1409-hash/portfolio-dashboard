import streamlit as st
import pandas as pd
import numpy as np
import re, os, json, smtplib, ssl, feedparser
import requests as _req
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
import plotly.express as px
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# ── IST ──────────────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))
def now_ist(): return datetime.now(IST)

# ── File paths ────────────────────────────────────────────────────────
_B = os.path.dirname(os.path.abspath(__file__))
def _fp(n): return os.path.join(_B, n)
OVERRIDES_F  = _fp("ticker_overrides.json")
MAPPING_F    = _fp("column_mappings.json")
TX_F         = _fp("transactions.csv")
HISTORY_F    = _fp("portfolio_history.csv")
ALERTS_F     = _fp("price_alerts.json")
SETTINGS_F   = _fp("app_settings.json")
MF_F         = _fp("mf_watchlist.json")
TX_COLS      = ["date","share_name","ticker","txn_type","quantity","price"]
HIST_COLS    = ["date","total_invested","total_current","total_pnl"]

def _jload(p, d):
    try:
        if os.path.exists(p):
            with open(p,"r",encoding="utf-8") as f: return json.load(f)
    except: pass
    return d

def _jsave(p, d):
    try:
        with open(p,"w",encoding="utf-8") as f: json.dump(d,f,ensure_ascii=False,indent=2)
        return True
    except: return False

load_overrides  = lambda: _jload(OVERRIDES_F, {})
save_overrides  = lambda d: _jsave(OVERRIDES_F, d)
load_mappings   = lambda: _jload(MAPPING_F, {})
save_mappings   = lambda d: _jsave(MAPPING_F, d)
load_price_alerts = lambda: _jload(ALERTS_F, {})
save_price_alerts = lambda d: _jsave(ALERTS_F, d)
load_settings   = lambda: _jload(SETTINGS_F, {})
save_settings   = lambda d: _jsave(SETTINGS_F, d)
load_mf_list    = lambda: _jload(MF_F, [])
save_mf_list    = lambda d: _jsave(MF_F, d)

def load_transactions():
    try:
        if os.path.exists(TX_F):
            df = pd.read_csv(TX_F)
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            return df
    except: pass
    return pd.DataFrame(columns=TX_COLS)

def save_transactions(df):
    try:
        out = df.copy()
        out['date'] = pd.to_datetime(out['date']).dt.strftime('%Y-%m-%d')
        out.to_csv(TX_F, index=False); return True
    except: return False

def append_transactions(rows):
    combined = pd.concat([load_transactions(), rows], ignore_index=True)
    save_transactions(combined); return combined

def append_history_snap(ti, tc, tp):
    try:
        today = now_ist().strftime('%Y-%m-%d')
        h = pd.read_csv(HISTORY_F) if os.path.exists(HISTORY_F) else pd.DataFrame(columns=HIST_COLS)
        h = h[h['date'] != today]
        h = pd.concat([h, pd.DataFrame([{"date":today,"total_invested":ti,"total_current":tc,"total_pnl":tp}])], ignore_index=True)
        h.to_csv(HISTORY_F, index=False)
    except: pass

def load_history():
    try:
        if os.path.exists(HISTORY_F):
            h = pd.read_csv(HISTORY_F)
            h['date'] = pd.to_datetime(h['date'])
            return h.sort_values('date')
    except: pass
    return pd.DataFrame(columns=HIST_COLS)

# ══════════════════════════════════════════════════════════════════════
# PAGE CONFIG + THEME
# ══════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="AlphaPortfolio Pro+ v6", layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
.stApp{background:#0d1117;color:#cdd9e5;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#161b22,#0d1117);border-right:1px solid #30363d;}
[data-testid="stSidebar"] *{color:#cdd9e5!important;}
.stTabs [data-baseweb="tab-list"]{background:#161b22;border-radius:8px 8px 0 0;padding:4px 6px 0;gap:4px;border-bottom:2px solid #30363d;}
.stTabs [data-baseweb="tab"]{background:#21262d;color:#8b949e!important;border-radius:6px 6px 0 0;padding:8px 14px;font-weight:600;font-size:12px;border:1px solid #30363d;border-bottom:none;}
.stTabs [aria-selected="true"]{background:#1f6feb!important;color:#fff!important;border-color:#1f6feb!important;}
.stTabs [data-baseweb="tab-panel"]{background:#161b22;border:1px solid #30363d;border-top:none;border-radius:0 0 8px 8px;padding:16px;}
.tc{background:linear-gradient(135deg,#161b22,#1c2128);padding:16px 18px;border-radius:10px;border:1px solid #30363d;box-shadow:0 2px 12px rgba(0,0,0,.4);margin-bottom:12px;transition:border-color .2s;}
.tc:hover{border-color:#1f6feb;}
.mt{font-size:10px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;}
.mv{font-size:20px;color:#e6edf3;font-weight:700;margin-top:5px;font-family:'Courier New',monospace;}
.mg{color:#3fb950;font-size:11px;font-weight:600;margin-top:3px;}
.mr{color:#f85149;font-size:11px;font-weight:600;margin-top:3px;}
.mb{color:#58a6ff;font-size:11px;font-weight:600;margin-top:3px;}
.rw{background:rgba(248,81,73,.12);border:1px solid #f85149;padding:10px 14px;border-radius:8px;color:#ffa198;margin-bottom:12px;font-size:13px;line-height:1.5;}
.ah{background:rgba(63,185,80,.12);border:1px solid #3fb950;padding:8px 12px;border-radius:8px;color:#56d364;margin-bottom:8px;font-size:13px;}
.al{background:rgba(248,81,73,.12);border:1px solid #f85149;padding:8px 12px;border-radius:8px;color:#ffa198;margin-bottom:8px;font-size:13px;}
.mb-box{background:#1c2128;padding:12px 16px;border-radius:8px;border:1px dashed #58a6ff;margin-bottom:16px;color:#cdd9e5;}
.mbar{background:#161b22;border-bottom:1px solid #30363d;padding:8px 16px;display:flex;gap:20px;align-items:center;flex-wrap:wrap;font-size:13px;}
.mi{display:flex;flex-direction:column;}
.mn{font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.8px;}
.mv2{font-family:'Courier New',monospace;font-weight:700;color:#e6edf3;font-size:14px;}
.mcg{color:#3fb950;font-size:10px;font-weight:600;}
.mcr{color:#f85149;font-size:10px;font-weight:600;}
.nc{background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 12px;margin-bottom:7px;transition:border-color .2s;}
.nc:hover{border-color:#58a6ff;}
.nt{color:#e6edf3;font-weight:600;font-size:13px;line-height:1.4;}
.nm{color:#8b949e;font-size:11px;margin-top:3px;}
.ai-msg{background:#1c2128;border-left:3px solid #58a6ff;padding:12px 16px;border-radius:0 8px 8px 0;margin-bottom:10px;font-size:13px;line-height:1.6;color:#cdd9e5;}
.ai-user{background:#161b22;border-left:3px solid #3fb950;padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:8px;font-size:13px;color:#cdd9e5;}
.stTextInput>div>div>input,.stSelectbox>div>div>div{background:#21262d!important;color:#e6edf3!important;border:1px solid #30363d!important;border-radius:6px!important;}
.stDataFrame{border:1px solid #30363d!important;border-radius:8px;}
.stButton>button{background:#21262d;color:#cdd9e5;border:1px solid #30363d;border-radius:6px;font-weight:600;transition:all .2s;}
.stButton>button:hover{background:#1f6feb;color:#fff;border-color:#1f6feb;}
::-webkit-scrollbar{width:5px;height:5px;}
::-webkit-scrollbar-track{background:#0d1117;}
::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px;}
::-webkit-scrollbar-thumb:hover{background:#58a6ff;}
h1,h2,h3,h4{color:#e6edf3!important;}
</style>""", unsafe_allow_html=True)

st_autorefresh(interval=1000, key="ar1")

# ══════════════════════════════════════════════════════════════════════
# TICKER RESOLVER
# ══════════════════════════════════════════════════════════════════════
_TP = re.compile(r'^[A-Z0-9][A-Z0-9.\-&]*$')

def _is_ticker(v):
    v=v.strip(); vu=v.upper()
    if not v: return False
    if vu.endswith('.NS') or vu.endswith('.BO'): return True
    if ' ' in v or any(c.islower() for c in v): return False
    return len(vu)<=12 and bool(_TP.match(vu))

def _yahoo_search(q):
    try:
        r=_req.get("https://query2.finance.yahoo.com/v1/finance/search",
            params={"q":q,"quotesCount":8,"newsCount":0},
            headers={"User-Agent":"Mozilla/5.0"},timeout=6)
        if r.status_code==200:
            qs=r.json().get("quotes",[])
            eq=[x for x in qs if x.get("quoteType") in ("EQUITY","ETF",None)] or qs
            for x in eq:
                if x.get("symbol","").endswith(".NS"): return x["symbol"]
            for x in eq:
                if x.get("symbol","").endswith(".BO"): return x["symbol"]
            if eq: return eq[0].get("symbol")
    except: pass
    try:
        qs=yf.Search(q,max_results=8).quotes or []
        for x in qs:
            if x.get("symbol","").endswith(".NS"): return x["symbol"]
        if qs: return qs[0].get("symbol")
    except: pass
    return None

@st.cache_data(ttl=43200, show_spinner=False)
def resolve_tickers(raw_t, overrides_t):
    ov=dict(overrides_t); res={}
    for r in raw_t:
        rc=str(r).strip()
        if r in ov and ov[r]: res[r]=ov[r].strip().upper(); continue
        if not rc: res[r]=None; continue
        res[r]=rc.upper() if _is_ticker(rc) else _yahoo_search(rc)
    return res

@st.cache_data(ttl=60, show_spinner=False)
def fetch_prices(tickers):
    d={}
    for t in tickers:
        if not t: continue
        try:
            h=yf.Ticker(t).history(period="2d")
            d[t]=h['Close'].iloc[-1] if not h.empty else 0
        except: d[t]=0
    return d

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_52w(tickers):
    d={}
    for t in tickers:
        if not t: continue
        try:
            h=yf.Ticker(t).history(period="1y")
            d[t]=(h['High'].max(),h['Low'].min()) if not h.empty else (0,0)
        except: d[t]=(0,0)
    return d

@st.cache_data(ttl=21600, show_spinner=False)
def fetch_sectors(tickers):
    d={}
    for t in tickers:
        if not t: continue
        try: d[t]=yf.Ticker(t).info.get('sector') or 'Unknown'
        except: d[t]='Unknown'
    return d

@st.cache_data(ttl=120, show_spinner=False)
def fetch_indices():
    idx={"NIFTY 50":"^NSEI","SENSEX":"^BSESN","BANK NIFTY":"^NSEBANK","NIFTY IT":"^CNXIT","GOLD":"GC=F"}
    res={}
    for n,s in idx.items():
        try:
            h=yf.Ticker(s).history(period="2d")
            if len(h)>=2:
                c,p=h['Close'].iloc[-1],h['Close'].iloc[-2]
                res[n]=(round(c,2),round((c-p)/p*100,2))
            elif len(h)==1:
                res[n]=(round(h['Close'].iloc[-1],2),0.0)
        except: pass
    return res

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark(period="1y"):
    try:
        h=yf.Ticker("^NSEI").history(period=period)
        if not h.empty:
            return round((h['Close'].iloc[-1]-h['Close'].iloc[0])/h['Close'].iloc[0]*100,2), h
    except: pass
    return None, pd.DataFrame()

@st.cache_data(ttl=10, show_spinner=False)
def fetch_suggestions(q):
    if not q or len(q.strip())<2: return []
    s=[]
    try:
        r=_req.get("https://query2.finance.yahoo.com/v1/finance/search",
            params={"q":q,"quotesCount":10,"newsCount":0},
            headers={"User-Agent":"Mozilla/5.0"},timeout=4)
        if r.status_code==200:
            for x in r.json().get("quotes",[]):
                if x.get("quoteType") not in ("EQUITY","ETF","MUTUALFUND",None): continue
                s.append({"label":f"{x.get('longname') or x.get('shortname') or x.get('symbol')}  —  {x.get('symbol')}  [{x.get('exchange','')}]","ticker":x.get("symbol",""),"name":x.get("longname") or x.get("shortname") or ""})
    except: pass
    if not s:
        try:
            for x in (yf.Search(q,max_results=10).quotes or []):
                s.append({"label":f"{x.get('longname') or x.get('shortname') or x.get('symbol')}  —  {x.get('symbol')}","ticker":x.get("symbol",""),"name":x.get("longname") or ""})
        except: pass
    return s[:10]

@st.cache_data(ttl=60, show_spinner=False)
def search_stock_full(ticker):
    try:
        tk=yf.Ticker(ticker)
        h1d=tk.history(period="1d"); h1y=tk.history(period="1y")
        if h1d.empty: return None
        try: info=tk.info; cn=info.get('longName') or info.get('shortName') or ticker; cur=info.get('currency','')
        except: cn=ticker; cur=''
        return {"ticker":ticker,"company_name":cn,"currency":cur,"live_price":h1d['Close'].iloc[-1],
                "high_52w":h1y['High'].max() if not h1y.empty else None,
                "low_52w":h1y['Low'].min() if not h1y.empty else None,"history":h1y}
    except: return None

# ══════════════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def fetch_technicals(ticker, period="6mo"):
    """Fetch OHLCV and compute RSI, MACD, Bollinger Bands, Moving Averages."""
    try:
        h = yf.Ticker(ticker).history(period=period)
        if h.empty or len(h) < 30: return None
        close = h['Close']
        # Moving Averages
        h['MA20']  = close.rolling(20).mean()
        h['MA50']  = close.rolling(50).mean()
        h['MA200'] = close.rolling(200).mean()
        # RSI (14)
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, 1e-10)
        h['RSI'] = 100 - (100 / (1 + rs))
        # MACD
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        h['MACD']        = ema12 - ema26
        h['MACD_Signal'] = h['MACD'].ewm(span=9, adjust=False).mean()
        h['MACD_Hist']   = h['MACD'] - h['MACD_Signal']
        # Bollinger Bands (20, 2σ)
        h['BB_Mid']   = close.rolling(20).mean()
        h['BB_Upper'] = h['BB_Mid'] + 2 * close.rolling(20).std()
        h['BB_Lower'] = h['BB_Mid'] - 2 * close.rolling(20).std()
        # Volume MA
        h['Vol_MA20'] = h['Volume'].rolling(20).mean()
        return h.dropna(subset=['MA20','RSI','MACD'])
    except: return None

def get_technical_signal(df):
    """Quick signal summary from latest indicator values."""
    last = df.iloc[-1]
    signals = []
    rsi = last.get('RSI', 50)
    if rsi < 30:   signals.append(("RSI", "Oversold 🟢", "#3fb950"))
    elif rsi > 70: signals.append(("RSI", "Overbought 🔴", "#f85149"))
    else:          signals.append(("RSI", f"Neutral ({rsi:.0f})", "#8b949e"))
    macd = last.get('MACD', 0); sig = last.get('MACD_Signal', 0)
    if macd > sig: signals.append(("MACD", "Bullish ↑ 🟢", "#3fb950"))
    else:          signals.append(("MACD", "Bearish ↓ 🔴", "#f85149"))
    close = last['Close']; bb_u = last.get('BB_Upper'); bb_l = last.get('BB_Lower')
    if bb_u and close > bb_u:      signals.append(("Bollinger", "Above Upper Band ⚠️", "#e3b341"))
    elif bb_l and close < bb_l:    signals.append(("Bollinger", "Below Lower Band 🟢", "#3fb950"))
    else:                          signals.append(("Bollinger", "Inside Bands", "#8b949e"))
    ma20 = last.get('MA20'); ma50 = last.get('MA50')
    if ma20 and ma50:
        if close > ma20 > ma50:    signals.append(("Trend", "Strong Uptrend 🟢", "#3fb950"))
        elif close < ma20 < ma50:  signals.append(("Trend", "Strong Downtrend 🔴", "#f85149"))
        else:                      signals.append(("Trend", "Mixed / Sideways", "#8b949e"))
    return signals

# ══════════════════════════════════════════════════════════════════════
# OPTIONS CHAIN
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=60, show_spinner=False)
def fetch_options(ticker):
    """Fetch options chain from Yahoo Finance for a given ticker."""
    try:
        tk = yf.Ticker(ticker)
        exp_dates = tk.options
        if not exp_dates: return None, None, []
        nearest_exp = exp_dates[0]
        chain = tk.option_chain(nearest_exp)
        calls = chain.calls[['strike','lastPrice','bid','ask','volume','openInterest','impliedVolatility']].copy()
        puts  = chain.puts[['strike','lastPrice','bid','ask','volume','openInterest','impliedVolatility']].copy()
        calls.columns = ['Strike','Last','Bid','Ask','Volume','OI','IV']
        puts.columns  = ['Strike','Last','Bid','Ask','Volume','OI','IV']
        calls['IV'] = (calls['IV'] * 100).round(2)
        puts['IV']  = (puts['IV']  * 100).round(2)
        return calls, puts, list(exp_dates)
    except: return None, None, []

# ══════════════════════════════════════════════════════════════════════
# MUTUAL FUND TRACKER
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mf_nav(scheme_code):
    """Fetch MF NAV from AMFI India API (free, no auth needed)."""
    try:
        r = _req.get(f"https://api.mfapi.in/mf/{scheme_code}", timeout=8)
        if r.status_code == 200:
            data = r.json()
            meta = data.get('meta', {})
            nav_data = data.get('data', [])
            if nav_data:
                latest = nav_data[0]
                hist_df = pd.DataFrame(nav_data[:365])
                hist_df['date'] = pd.to_datetime(hist_df['date'], format='%d-%m-%Y', errors='coerce')
                hist_df['nav']  = pd.to_numeric(hist_df['nav'], errors='coerce')
                hist_df = hist_df.sort_values('date')
                return {
                    "scheme_name": meta.get('scheme_name',''),
                    "fund_house":  meta.get('fund_house',''),
                    "scheme_type": meta.get('scheme_type',''),
                    "nav":         float(latest.get('nav', 0)),
                    "nav_date":    latest.get('date',''),
                    "history":     hist_df,
                    "1m_return":   _mf_return(hist_df, 30),
                    "3m_return":   _mf_return(hist_df, 90),
                    "1y_return":   _mf_return(hist_df, 365),
                }
    except: pass
    return None

@st.cache_data(ttl=86400, show_spinner=False)
def search_mf(query):
    """Search AMFI scheme list for matching fund names."""
    try:
        r = _req.get("https://api.mfapi.in/mf/search?q=" + _req.utils.quote(query), timeout=6)
        if r.status_code == 200:
            return r.json()[:20]
    except: pass
    return []

def _mf_return(hist_df, days):
    try:
        cutoff = hist_df['date'].max() - timedelta(days=days)
        old = hist_df[hist_df['date'] <= cutoff]
        if old.empty: return None
        old_nav = old.iloc[-1]['nav']
        new_nav = hist_df.iloc[-1]['nav']
        return round((new_nav - old_nav) / old_nav * 100, 2)
    except: return None

# ══════════════════════════════════════════════════════════════════════
# NEWS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def fetch_news(tickers_t, max_per=4):
    from email.utils import parsedate_to_datetime
    two_w = datetime.now(timezone.utc) - timedelta(days=14)
    all_n=[]; seen=set()
    for t in list(tickers_t)[:20]:
        if not t: continue
        clean = t.replace(".NS","").replace(".BO","")
        for url in [
            f"https://news.google.com/rss/search?q={clean}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en",
            f"https://news.google.com/rss/search?q={clean}+shares+India&hl=en-IN&gl=IN&ceid=IN:en",
        ]:
            try:
                fd=feedparser.parse(url)
                for e in fd.entries[:max_per]:
                    title=e.get("title","").strip()
                    if not title or title in seen: continue
                    pub_s=e.get("published","")
                    try:
                        dt=parsedate_to_datetime(pub_s)
                        if dt < two_w: continue
                        pd_=dt.strftime("%d %b %Y, %H:%M")
                    except: dt=None; pd_=pub_s[:16]
                    seen.add(title)
                    all_n.append({"ticker":t,"title":title,"link":e.get("link","#"),
                                  "published":pd_,"pub_dt":dt,
                                  "source":"Google News",
                                  "summary":e.get("summary","")[:180] if e.get("summary") else ""})
            except: pass
    for src,url in [
        ("Economic Times","https://economictimes.indiatimes.com/markets/stocks/rss.cms"),
        ("Business Standard","https://www.business-standard.com/rss/markets-106.rss"),
        ("Moneycontrol","https://www.moneycontrol.com/rss/latestnews.xml"),
        ("LiveMint","https://www.livemint.com/rss/markets"),
    ]:
        try:
            fd=feedparser.parse(url)
            for e in fd.entries[:5]:
                title=e.get("title","").strip()
                if not title or title in seen: continue
                pub_s=e.get("published","")
                try:
                    from email.utils import parsedate_to_datetime as p2d
                    dt=p2d(pub_s)
                    if dt < two_w: continue
                    pd_=dt.strftime("%d %b %Y, %H:%M")
                except: dt=None; pd_=pub_s[:16]
                seen.add(title)
                all_n.append({"ticker":"📰 Market","title":title,"link":e.get("link","#"),
                              "published":pd_,"pub_dt":dt,"source":src,
                              "summary":e.get("summary","")[:180] if e.get("summary") else ""})
        except: pass
    all_n.sort(key=lambda x: x["pub_dt"] if x["pub_dt"] else datetime(2000,1,1,tzinfo=timezone.utc), reverse=True)
    return all_n[:60]

# ══════════════════════════════════════════════════════════════════════
# AI ADVISOR (Claude API)
# ══════════════════════════════════════════════════════════════════════
def rule_based_advisor(df_port, question_type="general", user_question=""):
    """Free, no-API-key rule-based portfolio advisor. Analyzes the actual holdings data
    using fixed financial rules (concentration, sector exposure, momentum, drawdown, tax)
    and returns a formatted text response — no external AI call needed."""
    if df_port is None or df_port.empty:
        return "📭 No portfolio data loaded yet. Upload your holdings file first so I can analyze it."

    d = df_port.copy()
    total_inv = d['Invested'].sum()
    total_cur = d['Current'].sum() if 'Current' in d.columns else total_inv
    total_pnl = total_cur - total_inv
    ret_pct   = (total_pnl/total_inv*100) if total_inv > 0 else 0
    n_stocks  = len(d['share_name'].unique())
    win_rate  = (d['PnL']>0).sum()/max(len(d),1)*100 if 'PnL' in d.columns else 0
    max_w     = d['Weight'].max() if 'Weight' in d.columns else 0
    max_w_stock = d.loc[d['Weight'].idxmax(),'share_name'] if 'Weight' in d.columns and not d.empty else "N/A"
    best = d.loc[d['Returns_Pct'].idxmax()] if 'Returns_Pct' in d.columns and not d.empty else None
    worst = d.loc[d['Returns_Pct'].idxmin()] if 'Returns_Pct' in d.columns and not d.empty else None
    losers = d[d['PnL']<0].sort_values('Returns_Pct').head(5) if 'PnL' in d.columns else pd.DataFrame()
    gainers = d[d['PnL']>0].sort_values('Returns_Pct',ascending=False).head(5) if 'PnL' in d.columns else pd.DataFrame()

    lines = []

    if question_type == "health":
        lines.append(f"## 🔍 Portfolio Health Check\n")
        lines.append(f"**Overview:** {n_stocks} stocks | Invested ₹{total_inv:,.0f} | Current ₹{total_cur:,.0f} | P&L **₹{total_pnl:+,.0f} ({ret_pct:+.2f}%)**\n")
        lines.append(f"**Win Rate:** {win_rate:.1f}% of holdings are profitable\n")
        if max_w > 25:
            lines.append(f"⚠️ **Concentration Risk:** {max_w_stock} is {max_w:.1f}% of your portfolio — well above the recommended 15-20% single-stock cap. Consider trimming.")
        elif max_w > 15:
            lines.append(f"🟡 **Moderate Concentration:** {max_w_stock} is {max_w:.1f}% of portfolio — keep an eye on this.")
        else:
            lines.append(f"✅ **Good Diversification:** No single stock exceeds 15% — healthy spread.")
        if n_stocks < 10:
            lines.append(f"\n⚠️ Only {n_stocks} stocks held — consider diversifying further (15-20 stocks is typically a good range for retail portfolios).")
        elif n_stocks > 40:
            lines.append(f"\n🟡 {n_stocks} stocks is quite high — over-diversification can dilute returns and make tracking difficult.")
        if ret_pct < 0:
            lines.append(f"\n📉 Portfolio currently in loss. Review underperformers below before deciding to average down or exit.")
        if not losers.empty:
            lines.append(f"\n**Biggest drags on portfolio:**")
            for _,r in losers.iterrows():
                lines.append(f"- {r['share_name']}: {r['Returns_Pct']:+.1f}% (₹{r['PnL']:+,.0f})")

    elif question_type == "risk":
        lines.append(f"## ⚠️ Risk Assessment\n")
        high_risk = d[d['Weight']>15].sort_values('Weight',ascending=False) if 'Weight' in d.columns else pd.DataFrame()
        if not high_risk.empty:
            lines.append(f"**Stocks above 15% weight (concentration risk):**")
            for _,r in high_risk.iterrows():
                lines.append(f"- {r['share_name']}: {r['Weight']:.1f}% of portfolio")
        else:
            lines.append("✅ No major single-stock concentration risk detected.")
        if 'Sector' in d.columns:
            sec = d.groupby('Sector')['Invested'].sum()
            sec_pct = (sec/sec.sum()*100).sort_values(ascending=False)
            top_sec = sec_pct.index[0] if len(sec_pct)>0 else None
            if top_sec and sec_pct.iloc[0] > 35:
                lines.append(f"\n⚠️ **Sector Concentration:** {sec_pct.iloc[0]:.1f}% of capital is in **{top_sec}** sector — consider diversifying across sectors.")
        big_losers = d[d['Returns_Pct']<-20] if 'Returns_Pct' in d.columns else pd.DataFrame()
        if not big_losers.empty:
            lines.append(f"\n🔴 **{len(big_losers)} stock(s) down more than 20%:** " + ", ".join(big_losers['share_name'].tolist()))
        lines.append(f"\n**Overall Volatility Indicator:** {'High' if d['Returns_Pct'].std() > 25 else 'Moderate' if d['Returns_Pct'].std() > 12 else 'Low'} (std dev of returns: {d['Returns_Pct'].std():.1f}%)" if 'Returns_Pct' in d.columns else "")

    elif question_type == "rebalance":
        lines.append(f"## 📈 Rebalancing Suggestions\n")
        if max_w > 20:
            lines.append(f"1. **Trim {max_w_stock}** — currently {max_w:.1f}% of portfolio. Consider reducing to ~15% and redeploying into underweight quality names.")
        if not gainers.empty:
            lines.append(f"\n2. **Consider partial profit-booking on top gainers:**")
            for _,r in gainers.head(3).iterrows():
                lines.append(f"   - {r['share_name']}: +{r['Returns_Pct']:.1f}% — lock in some gains if it now exceeds your target allocation.")
        if not losers.empty:
            lines.append(f"\n3. **Review these underperformers** — decide if the thesis still holds, or if it's time to cut losses:")
            for _,r in losers.head(3).iterrows():
                lines.append(f"   - {r['share_name']}: {r['Returns_Pct']:+.1f}%")
        lines.append(f"\n4. **Diversification check:** {n_stocks} stocks held. " + ("Consider adding 3-5 more names across uncovered sectors." if n_stocks<12 else "Allocation count looks reasonable."))

    elif question_type == "tax":
        lines.append(f"## 🧾 Tax Optimization (STCG vs LTCG)\n")
        lines.append("Indian capital gains tax rules: **STCG (held <1yr) taxed @20%**, **LTCG (held >1yr) taxed @12.5%** above ₹1 lakh exemption per year.\n")
        lines.append("**General tax-saving strategies based on your holdings:**")
        if not losers.empty:
            lines.append(f"- **Tax-loss harvesting:** You have {len(d[d['PnL']<0])} stock(s) in loss. Booking losses before March 31st can offset gains elsewhere and reduce your tax bill (subject to your specific situation — consult a CA).")
        if not gainers.empty:
            lines.append(f"- For profitable holdings nearing the 1-year mark, **waiting until LTCG eligibility** (>365 days) can cut your tax rate roughly in half (20%→12.5%).")
        lines.append(f"- Each financial year, the first **₹1 lakh of LTCG is tax-free** — consider booking profits up to this threshold annually if you have long-held winners.")
        lines.append("\n⚠️ This is general guidance, not professional tax advice. Please consult a Chartered Accountant for your specific tax filing.")

    elif question_type == "sector":
        lines.append(f"## 📊 Sector Diversification Review\n")
        if 'Sector' in d.columns:
            sec = d.groupby('Sector')['Invested'].sum().sort_values(ascending=False)
            sec_pct = (sec/sec.sum()*100)
            lines.append("**Current sector allocation:**")
            for sname, pct in sec_pct.items():
                flag = " ⚠️ (overweight)" if pct > 35 else (" 🟢" if pct < 20 else "")
                lines.append(f"- {sname}: {pct:.1f}%{flag}")
            if sec_pct.iloc[0] > 35:
                lines.append(f"\n⚠️ Heavy concentration in **{sec_pct.index[0]}** ({sec_pct.iloc[0]:.1f}%). A market downturn specific to this sector could disproportionately hurt your portfolio.")
            if len(sec_pct) < 4:
                lines.append(f"\n🟡 Only {len(sec_pct)} sector(s) represented — consider spreading across more sectors (Financials, IT, Pharma, FMCG, Energy, Auto, etc.) to reduce correlated risk.")
        else:
            lines.append("Sector data not available — visit Overview Dashboard first to load sector classification.")

    elif question_type == "buysell":
        lines.append(f"## 💡 Holdings-Based Observations\n")
        lines.append("*(Not investment advice — these are data-driven observations from your current holdings only.)*\n")
        if not gainers.empty:
            lines.append(f"**Strong performers (consider your target allocation):**")
            for _,r in gainers.head(3).iterrows():
                tag = "🎯 At/near take-profit zone" if r.get('Returns_Pct',0) >= 20 else "📈 Performing well"
                lines.append(f"- {r['share_name']}: {r['Returns_Pct']:+.1f}% — {tag}")
        if not losers.empty:
            lines.append(f"\n**Underperformers (review thesis):**")
            for _,r in losers.head(3).iterrows():
                tag = "🛑 Near stop-loss zone" if r.get('Returns_Pct',0) <= -10 else "📉 Watch closely"
                lines.append(f"- {r['share_name']}: {r['Returns_Pct']:+.1f}% — {tag}")
        lines.append(f"\nUse the **Technical Indicators** tab for RSI/MACD signals on specific stocks before deciding.")

    else:  # free-form question matching
        q = user_question.lower()
        if any(w in q for w in ["sell","exit","reduce","trim"]):
            lines.append("### 💡 Stocks to review for selling/trimming:\n")
            if not losers.empty:
                for _,r in losers.head(5).iterrows():
                    lines.append(f"- **{r['share_name']}**: {r['Returns_Pct']:+.1f}% (₹{r['PnL']:+,.0f}) — biggest underperformer")
            if max_w > 20:
                lines.append(f"\n- **{max_w_stock}** is {max_w:.1f}% of your portfolio — consider trimming for concentration risk.")
        elif any(w in q for w in ["tax","stcg","ltcg"]):
            return rule_based_advisor(df_port, "tax")
        elif any(w in q for w in ["risk","concentrat","diversif"]):
            return rule_based_advisor(df_port, "risk")
        elif any(w in q for w in ["sector"]):
            return rule_based_advisor(df_port, "sector")
        elif any(w in q for w in ["rebalanc"]):
            return rule_based_advisor(df_port, "rebalance")
        elif any(w in q for w in ["rsi","macd","bollinger","technical","indicator"]):
            lines.append("### 📊 Technical Indicators Explained\n")
            lines.append("- **RSI (Relative Strength Index):** Measures momentum 0-100. Above 70 = potentially overbought, below 30 = potentially oversold.")
            lines.append("- **MACD:** Shows trend direction via moving average crossovers. MACD crossing above signal line = bullish; below = bearish.")
            lines.append("- **Bollinger Bands:** Price bands based on volatility. Price near upper band = potentially overbought; near lower band = potentially oversold.")
            lines.append("\nVisit the **📊 Technical Indicators** tab to see these live for any stock in your portfolio.")
        elif any(w in q for w in ["defensiv","safe","stable"]):
            lines.append("### 🛡️ Defensive Stock Categories (General Education)\n")
            lines.append("Defensive sectors typically include: **FMCG** (consumer staples — demand stays steady), **Pharma** (healthcare needs are non-discretionary), and **Utilities** (power, water).")
            lines.append("\nThese tend to be less volatile during market downturns compared to high-beta sectors like IT or Realty. Use the **Sector Allocation** chart on Overview Dashboard to see your current defensive exposure.")
            lines.append("\n⚠️ This is general market education, not a specific stock recommendation.")
        else:
            lines.append(f"### 📋 Quick Portfolio Snapshot\n")
            lines.append(f"You have **{n_stocks} stocks**, total invested ₹{total_inv:,.0f}, currently worth ₹{total_cur:,.0f} ({ret_pct:+.2f}%).")
            lines.append(f"\nTry asking about: **risk**, **rebalancing**, **tax**, **sector diversification**, or **which stocks to review**.")

    return "\n".join(lines) if lines else "I couldn't generate a specific answer — try rephrasing, or use the Auto Analysis tab for a structured report."


def build_portfolio_context(df_port):
    """Build a concise portfolio summary string (used for display/debug, not an external API)."""
    if df_port is None or df_port.empty: return "No portfolio data available."
    total_inv = df_port['Invested'].sum()
    total_cur = df_port['Current'].sum() if 'Current' in df_port.columns else 0
    total_pnl = (total_cur - total_inv) if total_cur else 0
    ret_pct   = (total_pnl / total_inv * 100) if total_inv > 0 else 0
    top5 = df_port.nlargest(5,'Invested')[['share_name','Invested','Returns_Pct']].to_string(index=False) if 'Returns_Pct' in df_port.columns else "N/A"
    worst3 = df_port.nsmallest(3,'Returns_Pct')[['share_name','Returns_Pct']].to_string(index=False) if 'Returns_Pct' in df_port.columns else "N/A"
    n = len(df_port['share_name'].unique())
    return (f"Portfolio: {n} stocks, Invested ₹{total_inv:,.0f}, Current ₹{total_cur:,.0f}, "
            f"P&L ₹{total_pnl:,.0f} ({ret_pct:+.2f}%)\n"
            f"Top 5 holdings by value:\n{top5}\n"
            f"Worst 3 performers:\n{worst3}")

# ══════════════════════════════════════════════════════════════════════
# EMAIL + TELEGRAM
# ══════════════════════════════════════════════════════════════════════
def send_email(sender, pwd, recipient, subject, body):
    try:
        msg=MIMEMultipart(); msg['Subject']=subject; msg['From']=sender; msg['To']=recipient
        msg.attach(MIMEText(body,"plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com",465,context=ssl.create_default_context()) as s:
            s.login(sender,pwd); s.sendmail(sender,recipient,msg.as_string())
        return True,""
    except Exception as e: return False,str(e)

def send_telegram(token, chat_id, text):
    try:
        r=_req.post(f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id":chat_id,"text":text,"parse_mode":"HTML"},timeout=8)
        return r.status_code==200, r.text
    except Exception as e: return False,str(e)

def dispatch(subj, body, cfg):
    if cfg.get("email_enabled") and cfg.get("email_sender") and cfg.get("email_password"):
        send_email(cfg["email_sender"],cfg["email_password"],cfg.get("email_recipient",cfg["email_sender"]),subj,body)
    if cfg.get("telegram_enabled") and cfg.get("telegram_token") and cfg.get("telegram_chat_id"):
        send_telegram(cfg["telegram_token"],cfg["telegram_chat_id"],f"<b>{subj}</b>\n\n{body}")

# ══════════════════════════════════════════════════════════════════════
# FIFO + XIRR
# ══════════════════════════════════════════════════════════════════════
def compute_fifo(df_tx):
    if df_tx.empty: return pd.DataFrame(), pd.DataFrame()
    rr=[]; ol=[]
    for sn,grp in df_tx.sort_values('date').groupby('share_name'):
        q=[]
        for _,row in grp.iterrows():
            qty=float(row['quantity']); price=float(row['price']); dt=row['date']
            tk=row.get('ticker','')
            if str(row['txn_type']).upper()=='BUY':
                q.append({"dt":dt,"qty":qty,"price":price})
            elif str(row['txn_type']).upper()=='SELL':
                rem=qty
                while rem>1e-9 and q:
                    lot=q[0]; mq=min(lot['qty'],rem)
                    hd=(dt-lot['dt']).days if pd.notna(dt) and pd.notna(lot['dt']) else 0
                    rr.append({"share_name":sn,"ticker":tk,"sell_date":dt,"buy_date":lot['dt'],
                                "quantity":mq,"buy_price":lot['price'],"sell_price":price,
                                "realized_pnl":(price-lot['price'])*mq,"holding_days":hd,
                                "tax_term":"LTCG (>1yr)" if hd>365 else "STCG (<1yr)"})
                    lot['qty']-=mq; rem-=mq
                    if lot['qty']<=1e-9: q.pop(0)
        for lot in q:
            if lot['qty']>1e-9: ol.append({"share_name":sn,"buy_date":lot['dt'],"quantity":lot['qty'],"buy_price":lot['price']})
    return pd.DataFrame(rr), pd.DataFrame(ol)

def xirr(cfs):
    if len(cfs)<2: return None
    dates=[c[0] for c in cfs]; amts=[c[1] for c in cfs]; t0=min(dates)
    def npv(r): return sum(a/((1+r)**((d-t0).days/365)) for d,a in zip(dates,amts))
    def dnpv(r): return sum(-((d-t0).days/365)*a/((1+r)*(((d-t0).days/365)+1)) for d,a in zip(dates,amts))
    rate=0.1
    for _ in range(100):
        try:
            f,fp=npv(rate),dnpv(rate)
            if abs(fp)<1e-10: break
            nr=rate-f/fp
            if abs(nr-rate)<1e-7: rate=nr; break
            rate=nr
        except: break
    if rate<=-1 or rate>100: return None
    return rate*100

# ══════════════════════════════════════════════════════════════════════
# SCORECARD
# ══════════════════════════════════════════════════════════════════════
def scorecard(df_h, bench_ret=None):
    n=len(df_h['share_name'].unique()); inv=df_h['Invested'].sum(); cur=df_h.get('Current',df_h['Invested']).sum()
    pnl=(cur-inv); ret=(pnl/inv*100) if inv>0 else 0
    wr=(df_h['PnL']>0).sum()/max(len(df_h),1)*100 if 'PnL' in df_h.columns else 0
    mw=df_h['Weight'].max() if 'Weight' in df_h.columns else 0
    vol=df_h['Returns_Pct'].std() if 'Returns_Pct' in df_h.columns else 1
    avg_r=df_h['Returns_Pct'].mean() if 'Returns_Pct' in df_h.columns else 0
    sharpe=(avg_r/vol) if vol and vol>0 else 0
    mdd=((df_h.get('Simulated_Live',df_h.get('buy_price',0))-df_h.get('buy_price',0))/df_h.get('buy_price',pd.Series([1])).replace(0,1)*100).min() if 'buy_price' in df_h.columns else 0
    alpha=(ret-bench_ret) if bench_ret is not None else None
    sc=0
    sc+=20 if n>=15 else (15 if n>=10 else (10 if n>=5 else 4))
    sc+=min(20,int(wr/5))
    sc+=20 if mw<10 else (14 if mw<20 else (8 if mw<30 else 2))
    sc+=20 if ret>=20 else (15 if ret>=10 else (10 if ret>=0 else 2))
    sc+=10 if sharpe>1 else (7 if sharpe>0.5 else (4 if sharpe>0 else 1))
    sc+=10 if mdd>-10 else (6 if mdd>-20 else 2)
    label=("Outstanding 🌟" if sc>=85 else "Excellent 💪" if sc>=70 else "Good 👍" if sc>=55 else "Moderate ⚠️" if sc>=40 else "Needs Work 🔴")
    color=("#3fb950" if sc>=70 else "#e3b341" if sc>=45 else "#f85149")
    return {"score":sc,"label":label,"color":color,"n":n,"wr":wr,"mw":mw,"ret":ret,"sharpe":sharpe,"alpha":alpha,"mdd":mdd,"vol":vol}

def cpnl(v):
    if isinstance(v,str): return ''
    return 'color:#3fb950;font-weight:bold;' if v>=0 else 'color:#f85149;font-weight:bold;'

# ══════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════
for k,v in [("alerted",set()),("overrides",None),("transactions",None),("mappings",None),
            ("settings",None),("mf_list",None),("search_ticker",""),
            ("ai_history",[]),("ai_portfolio_analysis","")]:
    if k not in st.session_state: st.session_state[k]=v

if st.session_state.overrides   is None: st.session_state.overrides   = load_overrides()
if st.session_state.transactions is None: st.session_state.transactions = load_transactions()
if st.session_state.mappings    is None: st.session_state.mappings    = load_mappings()
if st.session_state.settings    is None: st.session_state.settings    = load_settings()
if st.session_state.mf_list     is None: st.session_state.mf_list     = load_mf_list()

_cfg = st.session_state.settings

# ══════════════════════════════════════════════════════════════════════
# MARKET BAR
# ══════════════════════════════════════════════════════════════════════
idx_data = fetch_indices()
if idx_data:
    parts=[]
    for n,(v,c) in idx_data.items():
        cc="mcg" if c>=0 else "mcr"; sg="▲" if c>=0 else "▼"
        vs=f"${v:,.2f}" if n=="GOLD" else f"{v:,.2f}"
        parts.append(f'<div class="mi"><span class="mn">{n}</span><span class="mv2">{vs}</span><span class="{cc}">{sg}{abs(c):.2f}%</span></div>')
    ts=now_ist().strftime("%H:%M:%S IST")
    st.markdown(f'<div class="mbar">{"".join(parts)}<div class="mi" style="margin-left:auto;"><span class="mn">Updated</span><span class="mv2" style="font-size:12px;">{ts}</span></div></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<h2 style='color:#58a6ff;text-align:center;font-family:monospace;letter-spacing:2px;'>ALPHA TERMINAL</h2>", unsafe_allow_html=True)
    st.caption("v6.0 Pro+  •  AI-Powered")
    st.markdown("---")
    menu = st.radio("⚡ Navigation", [
        "🖥️ Overview Dashboard",
        "🤖 AI Portfolio Advisor",
        "📊 Technical Indicators",
        "⛓️ Options Chain",
        "💰 Mutual Fund Tracker",
        "📈 Advanced Analysis",
        "🔍 Single Stock Matrix",
        "🔎 Search Any Stock",
        "📰 Market News Feed",
        "💼 Transaction Ledger",
        "⚙️ Settings & Alerts",
    ])
    st.markdown("---")
    st.markdown("### 🔍 Filter")
    stock_filter = st.selectbox("Holdings:", ["All Holdings","🟢 Profit Only","🔴 Loss Only"])
    st.markdown("---")
    st.markdown("### 🎯 Risk Levels")
    target_pct    = st.slider("Take Profit %",  5, 100, 20, 5)
    stop_loss_pct = st.slider("Stop Loss %",   -50,  -5,-10, 5)
    market_shock  = st.slider("Stress Test %", -50,  50,  0, 5)
    st.markdown("---")
    if st.session_state.overrides:
        st.caption(f"🛠️ {len(st.session_state.overrides)} ticker override(s)")
        with st.expander("Manage overrides"):
            for k,v in list(st.session_state.overrides.items()):
                c1,c2=st.columns([4,1]); c1.caption(f"**{k[:22]}** → `{v}`")
                if c2.button("✕",key=f"do_{k}"):
                    st.session_state.overrides.pop(k,None)
                    save_overrides(st.session_state.overrides)
                    st.cache_data.clear(); st.rerun()

# ══════════════════════════════════════════════════════════════════════
# MAIN HEADER + FILE UPLOAD
# ══════════════════════════════════════════════════════════════════════
st.markdown("<h2 style='color:#e6edf3;'>📊 AlphaPortfolio Intelligence Terminal <span style='font-size:13px;color:#58a6ff;'>v6.0 Pro+ | AI-Powered</span></h2>", unsafe_allow_html=True)
uploaded_file = st.file_uploader("Upload your holdings file (CSV or Excel)", type=['csv','xlsx'])
df = pd.DataFrame()
if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    except Exception as e: st.error(f"File Error: {e}")

# ══════════════════════════════════════════════════════════════════════
# AI PORTFOLIO ADVISOR
# ══════════════════════════════════════════════════════════════════════
if "AI" in menu or "🤖" in menu:
    st.markdown("<h3>🤖 AI Portfolio Advisor</h3>", unsafe_allow_html=True)
    st.caption("Free rule-based investment advisor — analyzes your actual holdings data using financial rules (concentration, sector exposure, tax timing, momentum). No API key needed.")

    # Build portfolio context if file uploaded and processed
    port_ctx = build_portfolio_context(df if not df.empty else None)

    ai_tab1, ai_tab2 = st.tabs(["📋 Auto Portfolio Analysis", "💬 Chat with AI"])

    with ai_tab1:
        st.markdown("#### 📋 Instant AI Analysis of Your Portfolio")
        if df.empty:
            st.info("💡 Upload your portfolio file above to get an instant AI analysis of your holdings, risks, and rebalancing suggestions.")
        else:
            col_a1, col_a2 = st.columns([3,1])
            with col_a1:
                analysis_type = st.selectbox("Analysis type:", [
                    "🔍 Complete Portfolio Health Check",
                    "⚠️ Risk Assessment & Concentration Analysis",
                    "📈 Rebalancing Suggestions",
                    "💡 Buy/Sell Recommendations based on Holdings",
                    "🧾 Tax Optimization Strategy (STCG vs LTCG)",
                    "📊 Sector Diversification Review",
                ])
            with col_a2:
                st.markdown("<br>", unsafe_allow_html=True)
                run_analysis = st.button("🚀 Run Analysis", use_container_width=True, type="primary")

            if run_analysis or st.session_state.ai_portfolio_analysis:
                if run_analysis:
                    type_map = {
                        "🔍 Complete Portfolio Health Check": "health",
                        "⚠️ Risk Assessment & Concentration Analysis": "risk",
                        "📈 Rebalancing Suggestions": "rebalance",
                        "💡 Buy/Sell Recommendations based on Holdings": "buysell",
                        "🧾 Tax Optimization Strategy (STCG vs LTCG)": "tax",
                        "📊 Sector Diversification Review": "sector",
                    }
                    with st.spinner("🤖 Analyzing your portfolio..."):
                        result = rule_based_advisor(df, type_map.get(analysis_type, "health"))
                    st.session_state.ai_portfolio_analysis = result
                if st.session_state.ai_portfolio_analysis:
                    st.markdown(f'<div class="ai-msg">{st.session_state.ai_portfolio_analysis}</div>', unsafe_allow_html=True)
                    st.download_button("📥 Download Analysis", data=st.session_state.ai_portfolio_analysis.encode(),
                                       file_name="ai_portfolio_analysis.txt", mime="text/plain", use_container_width=True)
                    if st.button("🔄 Clear & Re-analyze", use_container_width=True):
                        st.session_state.ai_portfolio_analysis = ""; st.rerun()

    with ai_tab2:
        st.markdown("#### 💬 Ask About Your Portfolio")
        st.caption("Ask about risk, rebalancing, tax, sectors, or specific stocks — answers come from your actual holdings data using built-in financial rules (free, no API key).")

        # Chat history display
        for msg in st.session_state.ai_history:
            if msg["role"] == "user":
                st.markdown(f'<div class="ai-user">👤 <b>You:</b> {msg["content"]}</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="ai-msg">🤖 <b>Advisor:</b> {msg["content"]}</div>', unsafe_allow_html=True)

        # Quick prompt chips
        st.markdown("**Quick prompts:**")
        qp_cols = st.columns(4)
        quick_prompts = [
            "Which of my stocks should I consider selling?",
            "How can I reduce my tax liability?",
            "What are defensive stocks?",
            "Explain RSI and when to use it",
        ]
        triggered_prompt = None
        for i, qp in enumerate(quick_prompts):
            if qp_cols[i].button(qp[:30]+"…", key=f"qp_{i}", use_container_width=True):
                triggered_prompt = qp

        with st.form("ai_chat_form", clear_on_submit=True):
            user_input = st.text_area("Your question:", placeholder="e.g. Is my portfolio too concentrated in one sector?", height=80, label_visibility="collapsed")
            send_btn = st.form_submit_button("Send ➤", use_container_width=True)

        final_input = triggered_prompt or (user_input.strip() if send_btn and user_input.strip() else None)

        if final_input:
            with st.spinner("🤖 Analyzing..."):
                reply = rule_based_advisor(df if not df.empty else None, "qa", final_input)
            st.session_state.ai_history.append({"role":"user","content":final_input})
            st.session_state.ai_history.append({"role":"assistant","content":reply})
            if len(st.session_state.ai_history) > 20:
                st.session_state.ai_history = st.session_state.ai_history[-20:]
            st.rerun()

        if st.session_state.ai_history:
            if st.button("🗑️ Clear Chat", use_container_width=True):
                st.session_state.ai_history = []; st.rerun()

# ══════════════════════════════════════════════════════════════════════
# TECHNICAL INDICATORS
# ══════════════════════════════════════════════════════════════════════
elif "Technical" in menu or "📊" in menu:
    st.markdown("<h3>📊 Technical Analysis — RSI, MACD, Bollinger Bands, Moving Averages</h3>", unsafe_allow_html=True)

    ti_query = st.text_input("Enter ticker (e.g. RELIANCE.NS, TCS.NS, AAPL):", placeholder="RELIANCE.NS")
    ti_period = st.select_slider("Chart period:", options=["1mo","3mo","6mo","1y","2y"], value="6mo")

    if ti_query.strip():
        tk_ti = ti_query.strip().upper()
        with st.spinner(f"Fetching data for {tk_ti}..."):
            ti_df = fetch_technicals(tk_ti, ti_period)

        if ti_df is None:
            st.error(f"⚠️ Could not fetch data for {tk_ti}. Check the ticker and try again.")
        else:
            last = ti_df.iloc[-1]
            signals = get_technical_signal(ti_df)

            # Signal summary row
            st.markdown("#### ⚡ Signal Summary")
            sig_cols = st.columns(len(signals))
            for i,(ind,sig,col) in enumerate(signals):
                sig_cols[i].markdown(f'<div class="tc"><div class="mt">{ind}</div><div class="mv" style="font-size:14px;color:{col};">{sig}</div></div>', unsafe_allow_html=True)

            # KPI row
            kc1,kc2,kc3,kc4,kc5 = st.columns(5)
            kc1.markdown(f'<div class="tc"><div class="mt">LAST CLOSE</div><div class="mv">₹{last["Close"]:,.2f}</div></div>', unsafe_allow_html=True)
            kc2.markdown(f'<div class="tc"><div class="mt">RSI (14)</div><div class="mv" style="color:{"#f85149" if last["RSI"]>70 else "#3fb950" if last["RSI"]<30 else "#e6edf3"};">{last["RSI"]:.1f}</div></div>', unsafe_allow_html=True)
            kc3.markdown(f'<div class="tc"><div class="mt">MACD</div><div class="mv" style="color:{"#3fb950" if last["MACD"]>last["MACD_Signal"] else "#f85149"};">{last["MACD"]:.2f}</div></div>', unsafe_allow_html=True)
            kc4.markdown(f'<div class="tc"><div class="mt">MA 20</div><div class="mv">₹{last["MA20"]:,.2f}</div></div>', unsafe_allow_html=True)
            kc5.markdown(f'<div class="tc"><div class="mt">MA 50</div><div class="mv">₹{last["MA50"]:,.2f}</div></div>', unsafe_allow_html=True)

            # Chart 1: Price + Bollinger + MAs
            st.markdown("---")
            fig1 = go.Figure()
            fig1.add_trace(go.Candlestick(x=ti_df.index,open=ti_df['Open'],high=ti_df['High'],low=ti_df['Low'],close=ti_df['Close'],name='Price',increasing_line_color='#3fb950',decreasing_line_color='#f85149'))
            fig1.add_trace(go.Scatter(x=ti_df.index,y=ti_df['BB_Upper'],name='BB Upper',line=dict(color='#e3b341',width=1,dash='dot')))
            fig1.add_trace(go.Scatter(x=ti_df.index,y=ti_df['BB_Mid'],name='BB Mid (MA20)',line=dict(color='#8b949e',width=1)))
            fig1.add_trace(go.Scatter(x=ti_df.index,y=ti_df['BB_Lower'],name='BB Lower',line=dict(color='#e3b341',width=1,dash='dot'),fill='tonexty',fillcolor='rgba(227,179,65,0.05)'))
            if not ti_df['MA50'].isna().all():
                fig1.add_trace(go.Scatter(x=ti_df.index,y=ti_df['MA50'],name='MA 50',line=dict(color='#58a6ff',width=1.5)))
            if not ti_df['MA200'].isna().all():
                fig1.add_trace(go.Scatter(x=ti_df.index,y=ti_df['MA200'],name='MA 200',line=dict(color='#f85149',width=1.5)))
            fig1.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=30,b=10),title=f"{tk_ti} — Price + Bollinger Bands + Moving Averages",xaxis_rangeslider_visible=False,xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'),legend=dict(orientation="h",y=-0.15))
            st.plotly_chart(fig1, use_container_width=True)

            # Chart 2: RSI
            fig_rsi = go.Figure()
            fig_rsi.add_trace(go.Scatter(x=ti_df.index,y=ti_df['RSI'],name='RSI',line=dict(color='#58a6ff',width=2)))
            fig_rsi.add_hline(y=70,line_dash="dash",line_color="#f85149",annotation_text="Overbought (70)")
            fig_rsi.add_hline(y=30,line_dash="dash",line_color="#3fb950",annotation_text="Oversold (30)")
            fig_rsi.add_hrect(y0=30,y1=70,fillcolor="rgba(88,166,255,0.04)",line_width=0)
            fig_rsi.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=30,b=10),title="RSI (14-day)",yaxis=dict(range=[0,100],gridcolor='#21262d'),xaxis=dict(gridcolor='#21262d'),showlegend=False)
            st.plotly_chart(fig_rsi, use_container_width=True)

            # Chart 3: MACD
            colors_hist = ['#3fb950' if v>=0 else '#f85149' for v in ti_df['MACD_Hist']]
            fig_macd = go.Figure()
            fig_macd.add_trace(go.Bar(x=ti_df.index,y=ti_df['MACD_Hist'],name='MACD Histogram',marker_color=colors_hist))
            fig_macd.add_trace(go.Scatter(x=ti_df.index,y=ti_df['MACD'],name='MACD',line=dict(color='#58a6ff',width=2)))
            fig_macd.add_trace(go.Scatter(x=ti_df.index,y=ti_df['MACD_Signal'],name='Signal',line=dict(color='#e3b341',width=1.5,dash='dot')))
            fig_macd.add_hline(y=0,line_color="#30363d")
            fig_macd.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=30,b=10),title="MACD (12, 26, 9)",xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'),legend=dict(orientation="h",y=-0.2))
            st.plotly_chart(fig_macd, use_container_width=True)

            # Chart 4: Volume
            vol_colors = ['#3fb950' if ti_df['Close'].iloc[i]>=ti_df['Open'].iloc[i] else '#f85149' for i in range(len(ti_df))]
            fig_vol = go.Figure()
            fig_vol.add_trace(go.Bar(x=ti_df.index,y=ti_df['Volume'],name='Volume',marker_color=vol_colors,opacity=0.7))
            fig_vol.add_trace(go.Scatter(x=ti_df.index,y=ti_df['Vol_MA20'],name='Vol MA20',line=dict(color='#e3b341',width=1.5)))
            fig_vol.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=30,b=10),title="Volume",xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'),legend=dict(orientation="h",y=-0.2))
            st.plotly_chart(fig_vol, use_container_width=True)
    else:
        st.info("💡 Enter a ticker above to see RSI, MACD, Bollinger Bands, and Moving Averages charts.")

# ══════════════════════════════════════════════════════════════════════
# OPTIONS CHAIN
# ══════════════════════════════════════════════════════════════════════
elif "Options" in menu or "⛓️" in menu:
    st.markdown("<h3>⛓️ Options Chain Viewer</h3>", unsafe_allow_html=True)
    st.caption("Live F&O data — Calls & Puts with Strike, Last Price, Bid, Ask, Volume, Open Interest, and Implied Volatility.")

    oc_query = st.text_input("Enter ticker:", placeholder="RELIANCE.NS, TCS.NS, NIFTY (use ^NSEI for Nifty index)")
    if oc_query.strip():
        tk_oc = oc_query.strip().upper()
        with st.spinner(f"Fetching options chain for {tk_oc}..."):
            calls, puts, exp_dates = fetch_options(tk_oc)

        if calls is None or calls.empty:
            st.error(f"⚠️ Options data not available for {tk_oc}. Note: F&O data requires a valid options-eligible ticker (e.g. RELIANCE.NS, NIFTY50=F.NS). Try AAPL or SPY for US options.")
        else:
            # Expiry selector
            if len(exp_dates) > 1:
                sel_exp = st.selectbox("Select Expiry Date:", exp_dates)
                if sel_exp != exp_dates[0]:
                    with st.spinner("Loading..."):
                        try:
                            chain2 = yf.Ticker(tk_oc).option_chain(sel_exp)
                            calls = chain2.calls[['strike','lastPrice','bid','ask','volume','openInterest','impliedVolatility']].copy()
                            puts  = chain2.puts[['strike','lastPrice','bid','ask','volume','openInterest','impliedVolatility']].copy()
                            calls.columns = puts.columns = ['Strike','Last','Bid','Ask','Volume','OI','IV']
                            calls['IV'] = (calls['IV']*100).round(2)
                            puts['IV']  = (puts['IV']*100).round(2)
                        except: pass
            else:
                st.caption(f"Expiry: **{exp_dates[0]}**")

            # Summary metrics
            oc1,oc2,oc3,oc4 = st.columns(4)
            total_call_oi = calls['OI'].sum(); total_put_oi = puts['OI'].sum()
            pcr = total_put_oi/total_call_oi if total_call_oi>0 else 0
            oc1.markdown(f'<div class="tc"><div class="mt">TOTAL CALL OI</div><div class="mv">{int(total_call_oi):,}</div></div>', unsafe_allow_html=True)
            oc2.markdown(f'<div class="tc"><div class="mt">TOTAL PUT OI</div><div class="mv">{int(total_put_oi):,}</div></div>', unsafe_allow_html=True)
            pcr_color = "#3fb950" if pcr < 0.7 else ("#e3b341" if pcr < 1.2 else "#f85149")
            oc3.markdown(f'<div class="tc"><div class="mt">PUT/CALL RATIO</div><div class="mv" style="color:{pcr_color};">{pcr:.2f}</div><div class="mb">{"Bullish" if pcr<0.7 else "Neutral" if pcr<1.2 else "Bearish"}</div></div>', unsafe_allow_html=True)
            max_pain_strike = calls.loc[calls['OI'].idxmax(),'Strike'] if not calls.empty else 0
            oc4.markdown(f'<div class="tc"><div class="mt">MAX PAIN (CALL OI)</div><div class="mv">₹{max_pain_strike:,.0f}</div></div>', unsafe_allow_html=True)

            st.markdown("---")
            opt_tab1, opt_tab2, opt_tab3 = st.tabs(["📞 Calls","📉 Puts","📈 OI Chart"])
            with opt_tab1:
                st.dataframe(calls.style.format({"Strike":"₹{:,.2f}","Last":"₹{:,.2f}","Bid":"₹{:,.2f}","Ask":"₹{:,.2f}","Volume":"{:,.0f}","OI":"{:,.0f}","IV":"{:.1f}%"}).background_gradient(subset=['OI'],cmap='Greens'),use_container_width=True,height=400)
            with opt_tab2:
                st.dataframe(puts.style.format({"Strike":"₹{:,.2f}","Last":"₹{:,.2f}","Bid":"₹{:,.2f}","Ask":"₹{:,.2f}","Volume":"{:,.0f}","OI":"{:,.0f}","IV":"{:.1f}%"}).background_gradient(subset=['OI'],cmap='Reds'),use_container_width=True,height=400)
            with opt_tab3:
                fig_oi = go.Figure()
                fig_oi.add_trace(go.Bar(x=calls['Strike'],y=calls['OI'],name='Call OI',marker_color='#3fb950',opacity=0.8))
                fig_oi.add_trace(go.Bar(x=puts['Strike'],y=puts['OI'],name='Put OI',marker_color='#f85149',opacity=0.8))
                fig_oi.update_layout(barmode='group',plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=30,b=10),title="Open Interest by Strike",xaxis=dict(gridcolor='#21262d',title='Strike Price'),yaxis=dict(gridcolor='#21262d',title='Open Interest'),legend=dict(orientation="h",y=-0.2))
                st.plotly_chart(fig_oi, use_container_width=True)
    else:
        st.info("💡 Enter a ticker above to see its live options chain data.")

# ══════════════════════════════════════════════════════════════════════
# MUTUAL FUND TRACKER
# ══════════════════════════════════════════════════════════════════════
elif "Mutual Fund" in menu or "💰" in menu:
    st.markdown("<h3>💰 Mutual Fund Tracker</h3>", unsafe_allow_html=True)
    st.caption("NAV data via AMFI India API (free, no auth needed). Search by fund name and add to your watchlist.")

    mf_tab1, mf_tab2 = st.tabs(["🔍 Search & Add Funds","📋 My MF Watchlist"])

    with mf_tab1:
        mf_query = st.text_input("Search fund name:", placeholder="e.g. Mirae Asset, SBI Blue Chip, HDFC Top 100")
        if mf_query.strip():
            with st.spinner("Searching..."):
                results = search_mf(mf_query.strip())
            if results:
                for fund in results[:15]:
                    fc1,fc2,fc3 = st.columns([5,2,1])
                    fc1.write(f"**{fund.get('schemeName','')[:60]}**")
                    fc2.caption(f"Code: {fund.get('schemeCode','')}")
                    if fc3.button("➕ Add", key=f"add_mf_{fund.get('schemeCode','')}"):
                        current = st.session_state.mf_list or []
                        entry = {"code":str(fund['schemeCode']),"name":fund.get('schemeName',''),"units":0,"avg_nav":0}
                        if not any(x['code']==entry['code'] for x in current):
                            current.append(entry)
                            st.session_state.mf_list = current
                            save_mf_list(current)
                            st.success(f"Added: {entry['name'][:40]}"); st.rerun()
                        else:
                            st.info("Already in watchlist.")
            else:
                st.info("No results. Try a broader search term.")

    with mf_tab2:
        mf_list = st.session_state.mf_list or []
        if not mf_list:
            st.info("💡 No funds in watchlist yet. Search and add funds in the '🔍 Search' tab.")
        else:
            # Edit units/avg_nav for P&L calculation
            with st.expander("✏️ Set your Units & Average NAV (for P&L calculation)"):
                for i,fund in enumerate(mf_list):
                    ec1,ec2,ec3,ec4 = st.columns([3,1.5,1.5,0.8])
                    ec1.caption(fund['name'][:45])
                    new_units = ec2.number_input("Units",value=float(fund.get('units',0)),min_value=0.0,step=0.01,key=f"mu_{i}",label_visibility="collapsed")
                    new_nav   = ec3.number_input("Avg NAV ₹",value=float(fund.get('avg_nav',0)),min_value=0.0,step=0.01,key=f"mn_{i}",label_visibility="collapsed")
                    mf_list[i]['units'] = new_units; mf_list[i]['avg_nav'] = new_nav
                    if ec4.button("🗑️",key=f"rm_{i}"):
                        mf_list.pop(i); st.session_state.mf_list=mf_list; save_mf_list(mf_list); st.rerun()
                if st.button("💾 Save Units & NAV",use_container_width=True):
                    st.session_state.mf_list=mf_list; save_mf_list(mf_list); st.success("Saved!")

            # Fetch live NAV for all watchlist funds
            st.markdown("---")
            st.markdown("#### 📊 Live NAV & Performance")
            mf_rows=[]
            for fund in mf_list:
                with st.spinner(f"Loading {fund['name'][:30]}..."):
                    nav_data = fetch_mf_nav(fund['code'])
                if nav_data:
                    units = float(fund.get('units',0)); avg_n = float(fund.get('avg_nav',0))
                    curr_val = units * nav_data['nav']
                    inv_val  = units * avg_n
                    pnl      = curr_val - inv_val if units>0 and avg_n>0 else None
                    pnl_pct  = (pnl/inv_val*100) if (pnl is not None and inv_val>0) else None
                    mf_rows.append({"Fund Name":nav_data['scheme_name'][:50],"Fund House":nav_data['fund_house'][:25],"Type":nav_data['scheme_type'][:20],
                                    "Current NAV":nav_data['nav'],"NAV Date":nav_data['nav_date'],
                                    "1M Ret%":nav_data['1m_return'],"3M Ret%":nav_data['3m_return'],"1Y Ret%":nav_data['1y_return'],
                                    "Your Units":units,"Avg NAV":avg_n,"Current Val":curr_val if units>0 else None,
                                    "P&L":pnl,"P&L%":pnl_pct})
                    # Mini chart
                    if not nav_data['history'].empty:
                        fig_mf = go.Figure(go.Scatter(x=nav_data['history']['date'],y=nav_data['history']['nav'],line=dict(color='#58a6ff',width=2),fill='tozeroy',fillcolor='rgba(88,166,255,0.06)'))
                        fig_mf.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=30,b=10),title=dict(text=f"{nav_data['scheme_name'][:40]} — 1Y NAV",font=dict(color='#e6edf3',size=12)),height=200,xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'))
                        st.plotly_chart(fig_mf, use_container_width=True)
                else:
                    st.warning(f"Could not fetch data for {fund['name'][:40]}")

            if mf_rows:
                mf_df = pd.DataFrame(mf_rows)
                fmt={}
                for col in ['Current NAV','Avg NAV']: fmt[col]='₹{:,.2f}'
                for col in ['1M Ret%','3M Ret%','1Y Ret%','P&L%']: fmt[col]='{:+.2f}%'
                for col in ['Current Val','P&L']: fmt[col]='₹{:,.2f}'
                st.dataframe(mf_df.style.format({k:v for k,v in fmt.items() if k in mf_df.columns}).map(cpnl,subset=[c for c in ['P&L','P&L%'] if c in mf_df.columns]),use_container_width=True,height=300)

# ══════════════════════════════════════════════════════════════════════
# SETTINGS & ALERTS
# ══════════════════════════════════════════════════════════════════════
elif "Settings" in menu or "⚙️" in menu:
    st.markdown("<h3>⚙️ Settings & Alert Configuration</h3>", unsafe_allow_html=True)
    s1,s2,s3 = st.tabs(["📧 Email","📱 Telegram","🎯 Price Alerts"])

    with s1:
        st.markdown("#### Gmail Email Alerts")
        st.caption("Requires a Gmail **App Password** — generate at myaccount.google.com → Security → App Passwords.")
        em_en  = st.checkbox("Enable Email Alerts", value=_cfg.get("email_enabled",False))
        em_s   = st.text_input("Sender Gmail",    value=_cfg.get("email_sender",""),    placeholder="you@gmail.com")
        em_p   = st.text_input("App Password",    value=_cfg.get("email_password",""),  type="password")
        em_r   = st.text_input("Recipient Email", value=_cfg.get("email_recipient",""), placeholder="you@gmail.com")
        if st.button("💾 Save Email Settings", use_container_width=True):
            _cfg.update({"email_enabled":em_en,"email_sender":em_s,"email_password":em_p,"email_recipient":em_r})
            save_settings(_cfg); st.session_state.settings=_cfg; st.success("✅ Saved!")
        if st.button("🧪 Test Email", use_container_width=True):
            ok,msg = send_email(em_s,em_p,em_r or em_s,"AlphaPortfolio Test","✅ Email alerts are working!")
            st.success("Test sent!") if ok else st.error(f"Failed: {msg}")

    with s2:
        st.markdown("#### Telegram Bot Alerts")
        st.caption("Create a bot via @BotFather → get token. Message your bot once, then get Chat ID from @userinfobot.")
        tg_en  = st.checkbox("Enable Telegram Alerts", value=_cfg.get("telegram_enabled",False))
        tg_tok = st.text_input("Bot Token",  value=_cfg.get("telegram_token",""),  placeholder="123456:ABC-DEF…")
        tg_cid = st.text_input("Chat ID",    value=_cfg.get("telegram_chat_id",""),placeholder="123456789")
        if st.button("💾 Save Telegram Settings", use_container_width=True):
            _cfg.update({"telegram_enabled":tg_en,"telegram_token":tg_tok,"telegram_chat_id":tg_cid})
            save_settings(_cfg); st.session_state.settings=_cfg; st.success("✅ Saved!")
        if st.button("🧪 Test Telegram", use_container_width=True):
            ok,msg = send_telegram(tg_tok,tg_cid,"✅ <b>AlphaPortfolio</b> Telegram alerts working!")
            st.success("Sent!") if ok else st.error(f"Failed: {msg}")

    with s3:
        st.markdown("#### 🎯 Price Target & Stop-Loss Alerts")
        existing = load_price_alerts()
        with st.form("pa_form",clear_on_submit=True):
            pa1,pa2,pa3,pa4 = st.columns(4)
            pa_tk = pa1.text_input("Yahoo Ticker",placeholder="RELIANCE.NS")
            pa_nm = pa2.text_input("Label",placeholder="Reliance")
            pa_tg = pa3.number_input("Target ₹",min_value=0.0,step=1.0,format="%.2f")
            pa_st = pa4.number_input("Stop ₹",  min_value=0.0,step=1.0,format="%.2f")
            if st.form_submit_button("➕ Add Alert",use_container_width=True):
                if pa_tk.strip():
                    existing[pa_tk.strip().upper()]={"name":pa_nm.strip() or pa_tk,"target":pa_tg or None,"stop":pa_st or None}
                    save_price_alerts(existing); st.success("Alert added!"); st.rerun()
        if existing:
            for tk,al in existing.items():
                ac1,ac2,ac3,ac4=st.columns([2,2,2,1])
                ac1.write(f"**{tk}**"); ac2.caption(f"🎯 ₹{al.get('target','—')}" if al.get('target') else "🎯 No target")
                ac3.caption(f"🛑 ₹{al.get('stop','—')}" if al.get('stop') else "🛑 No stop")
                if ac4.button("🗑️",key=f"da_{tk}"):
                    existing.pop(tk,None); save_price_alerts(existing); st.rerun()

# ══════════════════════════════════════════════════════════════════════
# NEWS FEED
# ══════════════════════════════════════════════════════════════════════
elif "News" in menu or "📰" in menu:
    st.markdown("<h3>📰 Market News Feed</h3>", unsafe_allow_html=True)
    st.caption("Google News + Economic Times + Business Standard + Moneycontrol | Last 14 days only")

    news_q = st.text_input("Search news for any ticker or company:", placeholder="e.g. Reliance Industries, TCS.NS, Infosys")
    news_tickers = []
    if news_q.strip():
        tk_ = news_q.strip().upper() if _is_ticker(news_q.strip()) else _yahoo_search(news_q.strip())
        if tk_: news_tickers=[tk_]
    elif not df.empty:
        df_n = df.copy(); df_n.columns = df_n.columns.str.strip(); nc=list(df_n.columns)
        saved_pm = st.session_state.mappings.get("portfolio",{})
        tc_n = saved_pm.get("ticker",nc[0]) if saved_pm.get("ticker") in nc else nc[0]
        raw_n=[str(v).strip() for v in df_n[tc_n].dropna().unique() if str(v).strip()][:60]
        raw_n=[v for v in raw_n if v and not any(x in v.upper() for x in ['TOTAL','GRAND'])]
        if raw_n:
            with st.spinner("Resolving tickers..."):
                res_n=resolve_tickers(tuple(raw_n),tuple(sorted(st.session_state.overrides.items())))
            news_tickers=sorted({t for t in res_n.values() if t})

    if news_tickers:
        with st.spinner(f"Fetching news for {len(news_tickers)} stock(s)..."):
            news_items = fetch_news(tuple(news_tickers[:20]))
        if news_items:
            st.caption(f"📅 Last 14 days | **{len(news_items)} articles**")
            ftk = st.selectbox("Filter:", ["All"]+sorted(set(n['ticker'] for n in news_items)))
            for n in [x for x in news_items if ftk=="All" or x['ticker']==ftk]:
                summary_html = f'<div style="color:#8b949e;font-size:12px;margin-top:4px;">{n["summary"]}…</div>' if n.get("summary") else ""
                card_html = (
                    f'<div class="nc"><a href="{n["link"]}" target="_blank" style="text-decoration:none;">'
                    f'<div class="nt">{n["title"]}</div></a>'
                    f'<div class="nm">📌 <b>{n["ticker"]}</b> | 🗞️ {n.get("source","")} | 🕐 {n.get("published","")}</div>'
                    f'{summary_html}</div>'
                )
                st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.warning("No news found in last 14 days. Try searching a specific company name above.")
    else:
        st.info("💡 Upload portfolio file, or search for a company/ticker above.")

# ══════════════════════════════════════════════════════════════════════
# SEARCH ANY STOCK
# ══════════════════════════════════════════════════════════════════════
elif "Search Any Stock" in menu or "🔎" in menu:
    st.markdown("<h3>🔎 Search Any Stock</h3>", unsafe_allow_html=True)
    sq = st.text_input("Company name or ticker:", placeholder="Reliance, TCS, Apple, INFY.NS…", key="sbox")
    ct = st.session_state.search_ticker
    if not sq and ct: st.session_state.search_ticker=""; ct=""
    if sq and len(sq.strip())>=2:
        suggs=fetch_suggestions(sq.strip())
        if suggs:
            opts=[s["label"] for s in suggs]; tks=[s["ticker"] for s in suggs]
            prev=next((s["label"] for s in suggs if s["ticker"]==ct),None)
            cho=st.selectbox(f"{len(suggs)} match(es):",opts,index=opts.index(prev) if prev else 0,key=f"sd_{sq[:15]}")
            atk=tks[opts.index(cho)]
            if atk!=ct: st.session_state.search_ticker=atk; ct=atk
        else: st.info("No suggestions."); ct=""
    if ct:
        _,cc=st.columns([5,1])
        if cc.button("✖ Clear",use_container_width=True): st.session_state.search_ticker=""; st.rerun()
        with st.spinner(f"Loading {ct}…"): res=search_stock_full(ct)
        if res is None: st.error(f"Could not fetch {ct}.")
        else:
            st.markdown(f"#### {res['company_name']}  `{res['ticker']}`")
            c1,c2,c3=st.columns(3)
            c1.markdown(f'<div class="tc"><div class="mt">LIVE PRICE</div><div class="mv">{res["currency"]} {res["live_price"]:,.2f}</div></div>', unsafe_allow_html=True)
            c2.markdown(f'<div class="tc"><div class="mt">52W HIGH</div><div class="mv" style="color:#3fb950;">{res["currency"]} {res["high_52w"]:,.2f}</div></div>' if res["high_52w"] else '<div class="tc"><div class="mt">52W HIGH</div><div class="mv">N/A</div></div>', unsafe_allow_html=True)
            c3.markdown(f'<div class="tc"><div class="mt">52W LOW</div><div class="mv" style="color:#f85149;">{res["currency"]} {res["low_52w"]:,.2f}</div></div>' if res["low_52w"] else '<div class="tc"><div class="mt">52W LOW</div><div class="mv">N/A</div></div>', unsafe_allow_html=True)
            if not res["history"].empty:
                fig_s=go.Figure(go.Scatter(x=res["history"].index,y=res["history"]['Close'],line=dict(color='#58a6ff'),fill='tozeroy',fillcolor='rgba(88,166,255,0.08)'))
                fig_s.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=36,b=10),title="1-Year Price",xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_s,use_container_width=True)
    elif not sq: st.info("💡 Start typing above.")

# ══════════════════════════════════════════════════════════════════════
# TRANSACTION LEDGER
# ══════════════════════════════════════════════════════════════════════
elif "Transaction" in menu or "💼" in menu:
    st.markdown("<h2 style='color:#e6edf3;'>💼 Transaction Ledger & P&L Analytics</h2>", unsafe_allow_html=True)
    tx_t1,tx_t2,tx_t3,tx_t4 = st.tabs(["📊 P&L Dashboard","📤 Upload Trade File","➕ Manual Entry","📜 Full Ledger"])

    with tx_t1:
        rpt=st.session_state.get("rpt_trades",pd.DataFrame())
        if rpt.empty:
            st.markdown("<div style='text-align:center;padding:50px;'><div style='font-size:56px;'>📂</div><h3 style='color:#8b949e;'>No trades loaded</h3><p style='color:#6e7681;'>Go to <b>📤 Upload Trade File</b> tab.</p></div>",unsafe_allow_html=True)
        else:
            tb=rpt["buy_value"].sum(); ts=rpt["sell_value"].sum(); tp=rpt["realized_pnl"].sum()
            sd=rpt[rpt["tax_term"]=="STCG (<1yr)"]; ld=rpt[rpt["tax_term"]=="LTCG (>1yr)"]
            sp=sd["realized_pnl"].sum(); lp=ld["realized_pnl"].sum()
            pw=(rpt["realized_pnl"]>0).sum(); pl=(rpt["realized_pnl"]<0).sum()
            wr=pw/len(rpt)*100 if len(rpt)>0 else 0
            aw=rpt[rpt["realized_pnl"]>0]["realized_pnl"].mean() if pw>0 else 0
            al_=rpt[rpt["realized_pnl"]<0]["realized_pnl"].mean() if pl>0 else 0
            bt=rpt.loc[rpt["realized_pnl"].idxmax()] if len(rpt)>0 else None
            wt=rpt.loc[rpt["realized_pnl"].idxmin()] if len(rpt)>0 else None
            etx=max(0,sp)*0.20+(max(0,lp-100000)*0.125 if lp>100000 else 0)
            st.markdown("### 📈 P&L Summary")
            k1,k2,k3,k4,k5,k6=st.columns(6)
            pc="#3fb950" if tp>=0 else "#f85149"
            k1.markdown(f'<div class="tc"><div class="mt">TOTAL P&L</div><div class="mv" style="color:{pc};">₹{tp:,.0f}</div></div>',unsafe_allow_html=True)
            k2.markdown(f'<div class="tc"><div class="mt">BUY VALUE</div><div class="mv">₹{tb:,.0f}</div></div>',unsafe_allow_html=True)
            k3.markdown(f'<div class="tc"><div class="mt">SELL VALUE</div><div class="mv">₹{ts:,.0f}</div></div>',unsafe_allow_html=True)
            k4.markdown(f'<div class="tc"><div class="mt">WIN RATE</div><div class="mv" style="color:#58a6ff;">{wr:.1f}%</div><div class="mb">{pw}W / {pl}L</div></div>',unsafe_allow_html=True)
            k5.markdown(f'<div class="tc"><div class="mt">STCG</div><div class="mv" style="color:{"#3fb950" if sp>=0 else "#f85149"};">₹{sp:,.0f}</div><div class="mb">Tax ₹{max(0,sp)*0.20:,.0f}</div></div>',unsafe_allow_html=True)
            k6.markdown(f'<div class="tc"><div class="mt">LTCG</div><div class="mv" style="color:{"#3fb950" if lp>=0 else "#f85149"};">₹{lp:,.0f}</div><div class="mb">Tax ₹{max(0,lp-100000)*0.125 if lp>100000 else 0:,.0f}</div></div>',unsafe_allow_html=True)
            st.markdown("---")
            b1,b2,b3,b4=st.columns(4)
            b1.markdown(f'<div class="tc"><div class="mt">EST. TAX</div><div class="mv" style="color:#e3b341;">₹{etx:,.0f}</div></div>',unsafe_allow_html=True)
            b2.markdown(f'<div class="tc"><div class="mt">AVG WIN</div><div class="mv" style="color:#3fb950;">₹{aw:,.0f}</div></div>',unsafe_allow_html=True)
            b3.markdown(f'<div class="tc"><div class="mt">AVG LOSS</div><div class="mv" style="color:#f85149;">₹{al_:,.0f}</div></div>',unsafe_allow_html=True)
            rr=abs(aw/al_) if al_!=0 else 0
            b4.markdown(f'<div class="tc"><div class="mt">RISK:REWARD</div><div class="mv" style="color:#58a6ff;">1:{rr:.2f}</div></div>',unsafe_allow_html=True)
            if bt is not None and wt is not None:
                bw1,bw2=st.columns(2)
                bw1.markdown(f'<div class="ah">🏆 <b>BEST</b> — {bt["share_name"]}<br>Buy ₹{bt["buy_price"]:,.2f} → Sell ₹{bt["sell_price"]:,.2f} × {bt["quantity"]:.0f}<br><b>P&L: ₹{bt["realized_pnl"]:,.2f}</b></div>',unsafe_allow_html=True)
                bw2.markdown(f'<div class="al">📉 <b>WORST</b> — {wt["share_name"]}<br>Buy ₹{wt["buy_price"]:,.2f} → Sell ₹{wt["sell_price"]:,.2f} × {wt["quantity"]:.0f}<br><b>P&L: ₹{wt["realized_pnl"]:,.2f}</b></div>',unsafe_allow_html=True)
            st.caption("⚠️ Tax indicative only. LTCG exempt ₹1L/year. Consult a CA.")
            st.markdown("---")
            ch1,ch2=st.columns(2)
            with ch1:
                st.markdown("#### 📅 Monthly P&L")
                rm=rpt.copy(); rm["month"]=rm["sell_date"].dt.to_period("M").astype(str)
                mo=rm.groupby("month")["realized_pnl"].sum().reset_index()
                fig_m=go.Figure(go.Bar(x=mo["month"],y=mo["realized_pnl"],marker_color=["#3fb950" if v>=0 else "#f85149" for v in mo["realized_pnl"]],text=mo["realized_pnl"].apply(lambda v:f"₹{v:,.0f}"),textposition="auto"))
                fig_m.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d',tickangle=-45),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_m,use_container_width=True)
            with ch2:
                st.markdown("#### 📈 Cumulative P&L")
                rs=rpt.sort_values("sell_date").copy(); rs["cum"]=rs["realized_pnl"].cumsum()
                fig_c=go.Figure(go.Scatter(x=rs["sell_date"],y=rs["cum"],line=dict(color='#58a6ff',width=2),fill='tozeroy',fillcolor='rgba(88,166,255,0.08)'))
                fig_c.add_hline(y=0,line_dash="dot",line_color="#8b949e")
                fig_c.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'),showlegend=False)
                st.plotly_chart(fig_c,use_container_width=True)
            ch3,ch4=st.columns(2)
            with ch3:
                st.markdown("#### 🏆 Top Gainers & Losers")
                bs=rpt.groupby("share_name",as_index=False)["realized_pnl"].sum().sort_values("realized_pnl")
                tn=pd.concat([bs.head(5),bs.tail(5)]).drop_duplicates()
                fig_gl=go.Figure(go.Bar(x=tn["realized_pnl"],y=tn["share_name"],orientation='h',marker_color=["#3fb950" if v>=0 else "#f85149" for v in tn["realized_pnl"]],text=tn["realized_pnl"].apply(lambda v:f"₹{v:,.0f}"),textposition="auto"))
                fig_gl.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_gl,use_container_width=True)
            with ch4:
                st.markdown("#### 🥧 STCG vs LTCG")
                fig_tax=go.Figure(go.Pie(labels=["STCG","LTCG"],values=[max(0.01,len(sd)),max(0.01,len(ld))],hole=0.55,marker=dict(colors=["#58a6ff","#3fb950"]),textinfo="label+percent"))
                fig_tax.update_layout(paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10))
                st.plotly_chart(fig_tax,use_container_width=True)
            st.markdown("---")
            alls=["All Stocks"]+sorted(rpt["share_name"].unique().tolist())
            ss=st.selectbox("Filter by stock:",alls)
            rf=rpt if ss=="All Stocks" else rpt[rpt["share_name"]==ss]
            if ss!="All Stocks":
                fs1,fs2,fs3=st.columns(3)
                sp_=rf["realized_pnl"].sum()
                fs1.markdown(f'<div class="tc"><div class="mt">P&L</div><div class="mv" style="color:{"#3fb950" if sp_>=0 else "#f85149"};">₹{sp_:,.2f}</div></div>',unsafe_allow_html=True)
                fs2.markdown(f'<div class="tc"><div class="mt">TRADES</div><div class="mv">{len(rf)}</div></div>',unsafe_allow_html=True)
                fs3.markdown(f'<div class="tc"><div class="mt">WIN RATE</div><div class="mv" style="color:#58a6ff;">{(rf["realized_pnl"]>0).sum()/len(rf)*100:.1f}%</div></div>',unsafe_allow_html=True)
            sr=rf.copy()
            for dc in ['buy_date','sell_date']:
                if dc in sr.columns: sr[dc]=pd.to_datetime(sr[dc],errors='coerce').dt.strftime("%d %b %Y")
            sr=sr.rename(columns={"share_name":"Company","quantity":"Qty","buy_date":"Buy Date","buy_price":"Buy ₹","buy_value":"Buy Value","sell_date":"Sell Date","sell_price":"Sell ₹","sell_value":"Sell Value","realized_pnl":"P&L (₹)","holding_days":"Days","tax_term":"Term"})
            dcols=[c for c in ["Company","Qty","Buy Date","Buy ₹","Buy Value","Sell Date","Sell ₹","Sell Value","P&L (₹)","Days","Term"] if c in sr.columns]
            st.dataframe(sr[dcols].style.format({"Buy ₹":"₹{:,.2f}","Buy Value":"₹{:,.2f}","Sell ₹":"₹{:,.2f}","Sell Value":"₹{:,.2f}","P&L (₹)":"₹{:,.2f}"}).map(cpnl,subset=["P&L (₹)"]),use_container_width=True,height=350)
            st.download_button("📥 Download CSV",data=sr[dcols].to_csv(index=False).encode("utf-8"),file_name="trades.csv",mime="text/csv",use_container_width=True)

    with tx_t2:
        st.caption("Upload your broker's P&L export. Map columns below — saved mapping applied automatically.")
        rpt_file=st.file_uploader("Upload trade file",type=['csv','xlsx'],key="rpt_up")
        if rpt_file:
            try:
                rdf=pd.read_excel(rpt_file) if rpt_file.name.endswith('.xlsx') else pd.read_csv(rpt_file)
                rcols=[c.strip() for c in rdf.columns]; rdf.columns=rcols; rl=[c.lower() for c in rcols]
                srpt=st.session_state.mappings.get("rpt",{})
                def _ri(k,kws,fb=0):
                    if k in srpt and srpt[k] in rcols: return rcols.index(srpt[k])+1
                    m=next((i for i,c in enumerate(rl) if any(kw in c for kw in kws)),-1)
                    return m+1 if m>=0 else 0
                NONE="(None)"; opts=[NONE]+rcols; sn=" ✅ saved" if srpt else ""
                st.markdown(f"#### 🗺️ Column Mapping{sn}")
                r1,r2,r3=st.columns(3); r4,r5,r6=st.columns(3); r7,r8,r9=st.columns(3); r10,_,sc=st.columns([3,1,1])
                with r1: mn=st.selectbox("🏢 Company *",opts,index=_ri("name",["instrument","name","company","stock","scrip"]))
                with r2: mq=st.selectbox("📦 Qty *",opts,index=_ri("qty",["qty","quantity","shares","units","volume"]))
                with r3: mi_=st.selectbox("🔖 ISIN",opts,index=_ri("isin",["isin"]))
                with r4: mbd=st.selectbox("📅 Buy Date *",opts,index=_ri("buy_date",["purchase date","buy date","purchasedate","purchase_date"]))
                with r5: mbp=st.selectbox("💰 Buy Price *",opts,index=_ri("buy_price",["purchase price","buy price","purchaseprice","purchase_price"]))
                with r6: mbv=st.selectbox("💵 Buy Value",opts,index=_ri("buy_value",["purchase value","purchase cost","purchasevalue","purchase_value","purchase_cost"]))
                with r7: msd=st.selectbox("📅 Sell Date *",opts,index=_ri("sell_date",["sell date","selldate","sell_date"]))
                with r8: msp=st.selectbox("💸 Sell Price *",opts,index=_ri("sell_price",["sell price","sellprice","sell_price"]))
                with r9: msv=st.selectbox("💵 Sell Value",opts,index=_ri("sell_value",["sell value","sellvalue","sell_value"]))
                with r10: mpnl=st.selectbox("📈 P&L col",opts,index=_ri("pnl",["long term","g/l","gain","loss","pnl","profit","p&l","p / l"]))
                with sc:
                    st.markdown("<br><br>",unsafe_allow_html=True)
                    if st.button("💾 Save",use_container_width=True,key="srv"):
                        pm=st.session_state.mappings
                        pm["rpt"]={"name":mn,"qty":mq,"isin":mi_,"buy_date":mbd,"buy_price":mbp,"buy_value":mbv,"sell_date":msd,"sell_price":msp,"sell_value":msv,"pnl":mpnl}
                        save_mappings(pm); st.session_state.mappings=pm; st.toast("✅ Saved!",icon="💾"); st.rerun()
                miss=[k for k,v in {"Company":mn,"Buy Date":mbd,"Buy Price":mbp,"Sell Date":msd,"Sell Price":msp,"Qty":mq}.items() if v==NONE]
                if miss: st.warning(f"Map required fields: **{', '.join(miss)}**")
                else:
                    trd=pd.DataFrame()
                    trd["share_name"]=rdf[mn].astype(str).str.strip()
                    trd["quantity"]=pd.to_numeric(rdf[mq],errors='coerce').fillna(0)
                    trd["buy_date"]=pd.to_datetime(rdf[mbd],errors='coerce')
                    trd["buy_price"]=pd.to_numeric(rdf[mbp],errors='coerce').fillna(0)
                    trd["sell_date"]=pd.to_datetime(rdf[msd],errors='coerce')
                    trd["sell_price"]=pd.to_numeric(rdf[msp],errors='coerce').fillna(0)
                    trd["buy_value"]=pd.to_numeric(rdf[mbv],errors='coerce').fillna(0) if mbv!=NONE else trd["quantity"]*trd["buy_price"]
                    trd["sell_value"]=pd.to_numeric(rdf[msv],errors='coerce').fillna(0) if msv!=NONE else trd["quantity"]*trd["sell_price"]
                    trd["isin"]=rdf[mi_].astype(str).str.strip() if mi_!=NONE else ""
                    trd["realized_pnl"]=pd.to_numeric(rdf[mpnl],errors='coerce').fillna(0) if mpnl!=NONE else trd["sell_value"]-trd["buy_value"]
                    trd["holding_days"]=(trd["sell_date"]-trd["buy_date"]).dt.days.fillna(0).astype(int)
                    trd["tax_term"]=trd["holding_days"].apply(lambda d:"LTCG (>1yr)" if d>365 else "STCG (<1yr)")
                    trd=trd.dropna(subset=["buy_date","sell_date"]); trd=trd[trd["quantity"]>0]
                    st.markdown(f"#### 📋 Preview — {len(trd)} trades")
                    pv=trd.copy()
                    for dc in ['buy_date','sell_date']: pv[dc]=pd.to_datetime(pv[dc],errors='coerce').dt.strftime("%d %b %Y")
                    st.dataframe(pv[["share_name","quantity","buy_date","buy_price","sell_date","sell_price","realized_pnl","holding_days","tax_term"]].rename(columns={"share_name":"Company","quantity":"Qty","buy_date":"Buy","buy_price":"Buy ₹","sell_date":"Sell","sell_price":"Sell ₹","realized_pnl":"P&L","holding_days":"Days","tax_term":"Term"}).style.format({"Buy ₹":"₹{:,.2f}","Sell ₹":"₹{:,.2f}","P&L":"₹{:,.2f}"}).map(cpnl,subset=["P&L"]),use_container_width=True,height=240)
                    if st.button("✅ Confirm & Load",use_container_width=True,key="cr"):
                        st.session_state["rpt_trades"]=trd; st.success(f"✅ {len(trd)} trades loaded!"); st.rerun()
            except Exception as e: st.error(f"Error: {e}")
        elif "rpt_trades" in st.session_state and not st.session_state["rpt_trades"].empty:
            st.success(f"✅ {len(st.session_state['rpt_trades'])} trades loaded. Switch to 📊 P&L Dashboard.")

    with tx_t3:
        with st.form("tx_form",clear_on_submit=True):
            tc1,tc2=st.columns(2)
            with tc1:
                tx_sn=st.text_input("Company Name",placeholder="Reliance Industries")
                tx_tk=st.text_input("Yahoo Ticker (optional)",placeholder="RELIANCE.NS")
                tx_tp=st.radio("Type",["BUY","SELL"],horizontal=True)
            with tc2:
                tx_dt=st.date_input("Date",value=now_ist().date())
                tx_q=st.number_input("Quantity",min_value=0.0,step=1.0,format="%.2f")
                tx_p=st.number_input("Price ₹",min_value=0.0,step=0.01,format="%.2f")
            if st.form_submit_button("💾 Add",use_container_width=True):
                if not tx_sn or tx_q<=0 or tx_p<=0: st.error("Fill Company, Qty, Price.")
                else:
                    nr=pd.DataFrame([{"date":pd.to_datetime(tx_dt),"share_name":tx_sn.strip(),"ticker":tx_tk.strip().upper(),"txn_type":tx_tp,"quantity":tx_q,"price":tx_p}])
                    st.session_state.transactions=append_transactions(nr)
                    st.success(f"✅ {tx_tp} {tx_q} × {tx_sn} @ ₹{tx_p:,.2f}"); st.rerun()

    with tx_t4:
        txdf=st.session_state.transactions
        if txdf.empty: st.info("No manual transactions yet.")
        else:
            dp=txdf.copy().sort_values('date',ascending=False)
            dp['date']=pd.to_datetime(dp['date'],errors='coerce').dt.strftime('%d %b %Y')
            st.dataframe(dp,use_container_width=True,height=250)
            c1,c2=st.columns([3,1])
            with c1: st.download_button("📥 Download",data=txdf.to_csv(index=False).encode(),file_name="ledger.csv",mime="text/csv",use_container_width=True)
            with c2:
                if st.button("🗑️ Clear",use_container_width=True):
                    st.session_state.transactions=pd.DataFrame(columns=TX_COLS); save_transactions(st.session_state.transactions); st.rerun()
            rd,old=compute_fifo(txdf)
            if not rd.empty:
                tr=rd['realized_pnl'].sum(); sr_=rd[rd['tax_term'].str.contains('STCG')]['realized_pnl'].sum(); lr_=rd[rd['tax_term'].str.contains('LTCG')]['realized_pnl'].sum()
                r1,r2,r3=st.columns(3)
                r1.markdown(f'<div class="tc"><div class="mt">REALIZED P&L</div><div class="mv" style="color:{"#3fb950" if tr>=0 else "#f85149"};">₹{tr:,.2f}</div></div>',unsafe_allow_html=True)
                r2.markdown(f'<div class="tc"><div class="mt">STCG</div><div class="mv" style="color:#58a6ff;">₹{sr_:,.2f}</div></div>',unsafe_allow_html=True)
                r3.markdown(f'<div class="tc"><div class="mt">LTCG</div><div class="mv" style="color:#58a6ff;">₹{lr_:,.2f}</div></div>',unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# PORTFOLIO PAGES (require uploaded file)
# ══════════════════════════════════════════════════════════════════════
elif not df.empty:
    df.columns = df.columns.str.strip()
    all_cols = list(df.columns)
    spm = st.session_state.mappings.get("portfolio",{})

    def _ci(sk, kws, fp=0):
        if sk in spm and spm[sk] in all_cols: return all_cols.index(spm[sk])
        return next((i for i,c in enumerate(all_cols) if c.lower() in kws), fp)

    note=" ✅ (saved)" if spm else ""
    st.markdown(f'<div class="mb-box">🗺️ <b>Portfolio Column Mapping{note}</b></div>', unsafe_allow_html=True)
    mc1,mc2,mc3,mc4=st.columns([2,2,2,1])
    with mc1: tc_=st.selectbox("🌐 Ticker/Company:",all_cols,index=_ci("ticker",[],0))
    with mc2: qc_=st.selectbox("📦 Quantity:",all_cols,index=_ci("qty",['quantity','qty','volume','shares'],0))
    with mc3: pc_=st.selectbox("💰 Buy Price:",all_cols,index=_ci("price",['buy_price','buy price','avg_price','avg price','rate','price'],min(2,len(all_cols)-1)))
    with mc4:
        st.markdown("<br>",unsafe_allow_html=True)
        if st.button("💾 Save",use_container_width=True):
            pm=st.session_state.mappings; pm["portfolio"]={"ticker":tc_,"qty":qc_,"price":pc_}
            save_mappings(pm); st.session_state.mappings=pm; st.toast("✅ Mapping saved!",icon="💾")
    st.markdown("---")

    df=df.dropna(subset=[tc_])
    df[tc_]=df[tc_].astype(str).str.strip()
    df=df[(df[tc_]!='') & (~df[tc_].str.contains('Total|TOTAL|Grand',case=False,na=False))]
    df['quantity']=pd.to_numeric(df[qc_],errors='coerce').fillna(0)
    df['buy_price']=pd.to_numeric(df[pc_],errors='coerce').fillna(0)
    df['Invested']=df['quantity']*df['buy_price']
    df=df[df['Invested']>0].copy()

    uniq=df[tc_].unique().tolist()
    ov_t=tuple(sorted(st.session_state.overrides.items()))
    with st.spinner('🔎 Resolving tickers…'):
        trmap=resolve_tickers(tuple(uniq),ov_t)
    df['resolved_ticker']=df[tc_].map(trmap)
    unresolved=sorted({r for r,v in trmap.items() if not v})
    resolved_t=sorted({t for t in trmap.values() if t})

    with st.spinner('🗲 Fetching live prices…'):    prices=fetch_prices(tuple(resolved_t))
    with st.spinner('📊 Fetching 52W range…'):     rng=fetch_52w(tuple(resolved_t))

    df['live_price']=df['resolved_ticker'].map(prices).fillna(0)
    df['share_name']=df[tc_]
    df['high_52w']=df['resolved_ticker'].map(lambda t: rng.get(t,(0,0))[0] if t else 0).fillna(0)
    df['low_52w'] =df['resolved_ticker'].map(lambda t: rng.get(t,(0,0))[1] if t else 0).fillna(0)

    if unresolved:
        st.markdown(f'<div class="rw">⚠️ <b>No ticker for {len(unresolved)} companies.</b> Fill below and click Save.</div>',unsafe_allow_html=True)
        with st.expander(f"✏️ Fix {len(unresolved)} entries",expanded=True):
            with st.form("fix_t"):
                fi={}
                for e in unresolved:
                    c1,c2=st.columns([3,2]); c1.write(e)
                    fi[e]=c2.text_input("Yahoo ticker",key=f"fx_{e}",placeholder="e.g. TATAMOTORS.NS",label_visibility="collapsed")
                if st.form_submit_button("💾 Save All",use_container_width=True):
                    ns=0
                    for e,tv in fi.items():
                        tv=tv.strip()
                        if tv: st.session_state.overrides[e]=tv.upper(); ns+=1
                    if ns>0:
                        save_overrides(st.session_state.overrides); st.cache_data.clear(); st.success(f"✅ Saved {ns}"); st.rerun()

    df['Simulated_Live']=df['live_price']*(1+market_shock/100)
    df['Current']=df['quantity']*df['Simulated_Live']
    df['PnL']=df['Current']-df['Invested']
    df['Returns_Pct']=(df['PnL']/df['Invested'])*100
    df['Weight']=(df['Invested']/df['Invested'].sum())*100
    df['Action']=df.apply(lambda r: f"🎯 PROFIT (+{target_pct}%)" if r['Returns_Pct']>=target_pct else (f"⚠️ STOP ({stop_loss_pct}%)" if r['Returns_Pct']<=stop_loss_pct else "🟢 HOLD"), axis=1)
    df['Range_Status']=df.apply(lambda r: "📈 AT 52W HIGH" if r['high_52w'] and r['live_price']>=r['high_52w'] else ("📉 AT 52W LOW" if r['low_52w'] and r['live_price']<=r['low_52w'] else ""), axis=1)

    ti=df['Invested'].sum(); tc_v=df['Current'].sum(); tp=df['PnL'].sum()
    wr_=(tp/ti*100) if ti>0 else 0; ns=len(df); ps=(df['PnL']>0).sum()
    wr2=(ps/ns*100) if ns>0 else 0
    append_history_snap(ti,tc_v,tp)

    # Alert checks
    for _,row in df[df['Range_Status']!=""].iterrows():
        dispatch(f"{row['Range_Status']}: {row['share_name']} ₹{row['live_price']:,.2f}",
                 f"{row['share_name']} has touched {row['Range_Status']} at ₹{row['live_price']:,.2f}", _cfg)
    # 52W banners
    for _,row in df[df['Range_Status']!=""].iterrows():
        st.markdown(f'<div class="{"ah" if "HIGH" in row["Range_Status"] else "al"}">{row["Range_Status"]}: <b>{row["share_name"]}</b> ₹{row["live_price"]:,.2f}</div>',unsafe_allow_html=True)

    df_f=df.copy()
    if stock_filter=="🟢 Profit Only":   df_f=df[df['PnL']>0]
    elif stock_filter=="🔴 Loss Only":   df_f=df[df['PnL']<=0]

    # ═══ OVERVIEW ════════════════════════════════════════════════════
    if "Overview" in menu or "🖥️" in menu:
        st.caption(f"🔄 Auto-refresh 1s | {now_ist().strftime('%H:%M:%S')} IST" + (f" | ⚠️ Stress: {market_shock:+.0f}%" if market_shock!=0 else ""))
        for _,row in df[df['Weight']>25].iterrows():
            st.markdown(f'<div class="rw">⚠️ <b>Concentration:</b> {row["Weight"]:.1f}% in <b>{row["share_name"]}</b></div>',unsafe_allow_html=True)

        bench_ret,bench_hist=fetch_benchmark("1y")
        sc_=scorecard(df,bench_ret)

        # Scorecard banner
        alpha_html=""
        if sc_["alpha"] is not None:
            ac="#3fb950" if sc_["alpha"]>=0 else "#f85149"
            alpha_html=f'<div style="flex:1;min-width:130px;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;"><div style="font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;">Alpha vs Nifty</div><div style="font-size:18px;font-weight:700;color:{ac};font-family:monospace;">{sc_["alpha"]:+.2f}%</div></div>'
        st.markdown(f"""<div style='background:linear-gradient(135deg,#161b22,#1c2128);border:1px solid #30363d;border-radius:12px;padding:16px 20px;margin-bottom:16px;'>
        <div style='display:flex;align-items:center;gap:14px;margin-bottom:12px;'>
          <div style='font-size:38px;font-weight:900;color:{sc_["color"]};font-family:monospace;'>{sc_["score"]}</div>
          <div><div style='font-size:10px;color:#8b949e;font-weight:700;text-transform:uppercase;'>HEALTH SCORE / 100</div>
          <div style='font-size:16px;color:{sc_["color"]};font-weight:700;'>{sc_["label"]}</div></div>
        </div>
        <div style='display:flex;gap:10px;flex-wrap:wrap;'>
          <div style='flex:1;min-width:130px;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;'><div style='font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;'>Stocks</div><div style='font-size:18px;font-weight:700;color:#58a6ff;font-family:monospace;'>{sc_["n"]}</div></div>
          <div style='flex:1;min-width:130px;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;'><div style='font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;'>Win Rate</div><div style='font-size:18px;font-weight:700;color:{"#3fb950" if sc_["wr"]>=50 else "#f85149"};font-family:monospace;'>{sc_["wr"]:.1f}%</div></div>
          <div style='flex:1;min-width:130px;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;'><div style='font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;'>Return</div><div style='font-size:18px;font-weight:700;color:{"#3fb950" if sc_["ret"]>=0 else "#f85149"};font-family:monospace;'>{sc_["ret"]:+.2f}%</div></div>
          <div style='flex:1;min-width:130px;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;'><div style='font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;'>Sharpe</div><div style='font-size:18px;font-weight:700;color:{"#3fb950" if sc_["sharpe"]>0.5 else "#e3b341"};font-family:monospace;'>{sc_["sharpe"]:.2f}</div></div>
          <div style='flex:1;min-width:130px;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;'><div style='font-size:9px;color:#8b949e;font-weight:700;text-transform:uppercase;'>Max DD</div><div style='font-size:18px;font-weight:700;color:#f85149;font-family:monospace;'>{sc_["mdd"]:+.1f}%</div></div>
          {alpha_html}
        </div></div>""", unsafe_allow_html=True)

        # XIRR
        xv=None
        txd=st.session_state.transactions
        if not txd.empty:
            try:
                cfs=[(r['date'].to_pydatetime() if hasattr(r['date'],'to_pydatetime') else r['date'],
                      -(r['quantity']*r['price']) if str(r['txn_type']).upper()=='BUY' else (r['quantity']*r['price']))
                     for _,r in txd.iterrows()]
                cfs.append((now_ist().replace(tzinfo=None),tc_v))
                xv=xirr(cfs)
            except: pass

        st.markdown("<h4 style='color:#e6edf3;margin:8px 0;'>📈 Performance Matrix</h4>",unsafe_allow_html=True)
        k1,k2,k3,k4,k5,k6=st.columns(6)
        k1.markdown(f'<div class="tc"><div class="mt">INVESTED</div><div class="mv">₹{ti:,.0f}</div><div class="mb">● Base</div></div>',unsafe_allow_html=True)
        k2.markdown(f'<div class="tc"><div class="mt">CURRENT VALUE</div><div class="mv">₹{tc_v:,.0f}</div><div class="mb">Live</div></div>',unsafe_allow_html=True)
        pc=("#3fb950" if tp>=0 else "#f85149")
        k3.markdown(f'<div class="tc"><div class="mt">UNREALIZED P&L</div><div class="mv" style="color:{pc};">{"+" if tp>=0 else ""}₹{tp:,.0f}</div><div class="mb">{wr_:+.2f}%</div></div>',unsafe_allow_html=True)
        k4.markdown(f'<div class="tc"><div class="mt">WIN RATE</div><div class="mv" style="color:#58a6ff;">{wr2:.1f}%</div><div class="mb">{ps}G / {ns-ps}L</div></div>',unsafe_allow_html=True)
        if xv is not None:
            xc="#3fb950" if xv>=0 else "#f85149"
            k5.markdown(f'<div class="tc"><div class="mt">XIRR</div><div class="mv" style="color:{xc};">{xv:.2f}%</div><div class="mb">Annualized</div></div>',unsafe_allow_html=True)
        else:
            k5.markdown(f'<div class="tc"><div class="mt">XIRR</div><div class="mv" style="color:#8b949e;font-size:12px;">Add in Ledger</div></div>',unsafe_allow_html=True)
        k6.markdown(f'<div class="tc"><div class="mt">HEALTH</div><div class="mv" style="color:{sc_["color"]};">{sc_["score"]}/100</div><div class="mb">{sc_["label"][:12]}</div></div>',unsafe_allow_html=True)

        if not df_f.empty:
            cl,cr=st.columns([3,2])
            with cl:
                st.markdown("<h4>📊 Stock P&L</h4>",unsafe_allow_html=True)
                db=df_f.groupby('share_name',as_index=False).agg({'PnL':'sum'}).sort_values('PnL')
                fig_b=go.Figure(go.Bar(x=db['share_name'],y=db['PnL'],marker_color=['#3fb950' if v>=0 else '#f85149' for v in db['PnL']],text=db['PnL'].apply(lambda x:f"₹{x:,.0f}"),textposition='auto'))
                fig_b.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(showgrid=False,tickangle=-45),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_b,use_container_width=True)
            with cr:
                st.markdown("<h4>📦 Allocation</h4>",unsafe_allow_html=True)
                dp_=df_f.groupby('share_name',as_index=False)['Invested'].sum()
                fig_p=go.Figure(go.Pie(labels=dp_['share_name'],values=dp_['Invested'],hole=.55,hoverinfo="label+percent+value",textinfo="none"))
                fig_p.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),legend=dict(orientation="h",y=-0.15))
                st.plotly_chart(fig_p,use_container_width=True)

            # Benchmark comparison
            st.markdown("---")
            st.markdown("#### 📊 Portfolio vs Nifty 50 Benchmark")
            if bench_ret is not None:
                bc1,bc2,bc3=st.columns(3)
                bc1.markdown(f'<div class="tc"><div class="mt">YOUR RETURN</div><div class="mv" style="color:{"#3fb950" if wr_>=0 else "#f85149"};">{wr_:+.2f}%</div></div>',unsafe_allow_html=True)
                bc2.markdown(f'<div class="tc"><div class="mt">NIFTY 50 (1Y)</div><div class="mv" style="color:{"#3fb950" if bench_ret>=0 else "#f85149"};">{bench_ret:+.2f}%</div></div>',unsafe_allow_html=True)
                alp=(wr_-bench_ret)
                bc3.markdown(f'<div class="tc"><div class="mt">ALPHA</div><div class="mv" style="color:{"#3fb950" if alp>=0 else "#f85149"};">{alp:+.2f}%</div></div>',unsafe_allow_html=True)

            # 52W meter
            st.markdown("---")
            st.markdown("#### 📏 52-Week Position Meter")
            df52=df_f[df_f['high_52w']>0].groupby('share_name').agg({'live_price':'last','high_52w':'last','low_52w':'last','PnL':'sum'}).reset_index()
            df52=df52[df52['high_52w']>df52['low_52w']].copy()
            df52['pos']=((df52['live_price']-df52['low_52w'])/(df52['high_52w']-df52['low_52w'])*100).clip(0,100)
            for _,r in df52.sort_values('pos').head(20).iterrows():
                pos=r['pos']; bc="#f85149" if pos<30 else ("#e3b341" if pos<60 else "#3fb950")
                ns_=r['share_name'][:27]+"…" if len(r['share_name'])>29 else r['share_name']
                st.markdown(f"""<div style='margin-bottom:5px;'>
                <div style='display:flex;justify-content:space-between;font-size:11px;color:#8b949e;margin-bottom:2px;'>
                  <span><b style='color:#e6edf3;'>{ns_}</b> ₹{r['live_price']:,.2f}</span>
                  <span>52W: ₹{r['low_52w']:,.0f}—₹{r['high_52w']:,.0f} <b style='color:{"#3fb950" if r["PnL"]>=0 else "#f85149"};'>₹{r["PnL"]:+,.0f}</b></span>
                </div>
                <div style='background:#21262d;border-radius:4px;height:9px;position:relative;'>
                  <div style='width:{pos:.1f}%;background:{bc};border-radius:4px;height:9px;'></div>
                  <div style='position:absolute;left:{pos:.1f}%;top:-2px;width:2px;height:13px;background:#fff;border-radius:2px;'></div>
                </div></div>""", unsafe_allow_html=True)

            # Sector + History
            st.markdown("---")
            cs,ch_=st.columns([2,3])
            with cs:
                st.markdown("<h4>🏭 Sector Allocation</h4>",unsafe_allow_html=True)
                with st.spinner("Fetching sectors…"):
                    sm=fetch_sectors(tuple(resolved_t))
                df_s=df_f.copy(); df_s['Sector']=df_s['resolved_ticker'].map(sm).fillna('Unknown')
                sg=df_s.groupby('Sector',as_index=False)['Invested'].sum().sort_values('Invested',ascending=False)
                fig_sec=go.Figure(go.Pie(labels=sg['Sector'],values=sg['Invested'],hole=.5,hoverinfo="label+percent+value",textinfo="percent"))
                fig_sec.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),legend=dict(orientation="h",y=-0.2))
                st.plotly_chart(fig_sec,use_container_width=True)
            with ch_:
                st.markdown("<h4>📈 Portfolio Value Trend</h4>",unsafe_allow_html=True)
                hd=load_history()
                if len(hd)<2: st.info("📊 Trend builds day by day. Check back tomorrow!")
                else:
                    fig_h=go.Figure()
                    fig_h.add_trace(go.Scatter(x=hd['date'],y=hd['total_current'],name='Current',line=dict(color='#58a6ff'),fill='tozeroy',fillcolor='rgba(88,166,255,0.06)'))
                    fig_h.add_trace(go.Scatter(x=hd['date'],y=hd['total_invested'],name='Invested',line=dict(color='#8b949e',dash='dot')))
                    fig_h.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d',title='₹'),legend=dict(orientation="h",y=-0.2))
                    st.plotly_chart(fig_h,use_container_width=True)

            # Live Positions Table
            st.markdown("---")
            st.markdown("<h4>📋 Live Positions</h4>",unsafe_allow_html=True)
            ddi=df_f.copy()
            ddi['↑ from Low%']=((ddi['Simulated_Live']-ddi['low_52w'])/ddi['low_52w'].replace(0,1)*100)
            ddi['↓ from High%']=((ddi['Simulated_Live']-ddi['high_52w'])/ddi['high_52w'].replace(0,1)*100)
            dd=ddi[['share_name','resolved_ticker','quantity','buy_price','Simulated_Live','high_52w','low_52w','↑ from Low%','↓ from High%','Invested','Current','PnL','Returns_Pct','Action']].copy()
            dd.columns=['Stock','Ticker','Qty','Buy ₹','Live ₹','52W H','52W L','↑Low%','↓High%','Invested','Current','P&L','Ret%','Signal']
            st.dataframe(dd.style.format({'Buy ₹':'₹{:,.2f}','Live ₹':'₹{:,.2f}','52W H':'₹{:,.2f}','52W L':'₹{:,.2f}','↑Low%':'{:+.1f}%','↓High%':'{:+.1f}%','Invested':'₹{:,.0f}','Current':'₹{:,.0f}','P&L':'₹{:,.2f}','Ret%':'{:+.2f}%'}).map(cpnl,subset=['P&L','Ret%']),use_container_width=True,height=380)

            # Top5 + Drawdown
            st.markdown("---")
            t1,t2=st.columns(2)
            with t1:
                st.markdown("#### 🏆 Top 5 by Weight")
                t5=df_f.groupby('share_name',as_index=False).agg({'Invested':'sum','Current':'sum','PnL':'sum','Weight':'sum'}).nlargest(5,'Weight')
                t5['Ret%']=(t5['PnL']/t5['Invested']*100)
                st.dataframe(t5[['share_name','Weight','Invested','Current','PnL','Ret%']].rename(columns={'share_name':'Stock','Weight':'W%','Invested':'Inv ₹','Current':'Cur ₹','PnL':'P&L'}).style.format({'W%':'{:.1f}%','Inv ₹':'₹{:,.0f}','Cur ₹':'₹{:,.0f}','P&L':'₹{:,.0f}','Ret%':'{:+.1f}%'}).map(cpnl,subset=['P&L','Ret%']),use_container_width=True,height=210)
            with t2:
                st.markdown("#### 📉 Drawdown from Buy")
                ddd=df_f.copy(); ddd['DD%']=((ddd['Simulated_Live']-ddd['buy_price'])/ddd['buy_price'].replace(0,1)*100)
                dg=ddd.groupby('share_name',as_index=False).agg({'DD%':'mean'}).sort_values('DD%').head(10)
                fig_dd=go.Figure(go.Bar(x=dg['DD%'],y=dg['share_name'],orientation='h',marker_color=['#f85149' if v<0 else '#3fb950' for v in dg['DD%']],text=dg['DD%'].apply(lambda v:f"{v:+.1f}%"),textposition='auto'))
                fig_dd.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_dd,use_container_width=True)

            st.markdown("---")
            tc1_,tc2_=st.columns(2)
            with tc1_:
                st.markdown("<h4>💸 Tax Estimator</h4>",unsafe_allow_html=True)
                hd_=st.radio("Duration:",["STCG (<1yr)","LTCG (>1yr)"],horizontal=True)
                if tp>0:
                    if "STCG" in hd_: st.warning(f"STCG @20%: ₹{tp*0.20:,.2f}")
                    else: st.success(f"LTCG @12.5% (after ₹1L): ₹{max(0,tp-100000)*0.125:,.2f}")
                else: st.info("In loss — no tax.")
            with tc2_:
                st.markdown("<h4>📥 Export</h4>",unsafe_allow_html=True)
                st.download_button("📥 Download CSV",data=dd.to_csv(index=False).encode(),file_name="portfolio_report.csv",mime="text/csv",use_container_width=True)
        else: st.warning("No data for selected filter.")

    # ═══ ADVANCED ANALYSIS ═══════════════════════════════════════════
    elif "Advanced Analysis" in menu or "📈" in menu:
        st.markdown("<h3>📊 Advanced Analysis</h3>",unsafe_allow_html=True)
        txd2=st.session_state.transactions
        total_r=0
        if not txd2.empty:
            rd2,_=compute_fifo(txd2)
            total_r=rd2['realized_pnl'].sum() if not rd2.empty else 0
        ru1,ru2,ru3=st.columns(3)
        ru1.markdown(f'<div class="tc"><div class="mt">REALIZED P&L</div><div class="mv" style="color:{"#3fb950" if total_r>=0 else "#f85149"};">₹{total_r:,.2f}</div><div class="mb">From Ledger</div></div>',unsafe_allow_html=True)
        ru2.markdown(f'<div class="tc"><div class="mt">UNREALIZED P&L</div><div class="mv" style="color:{"#3fb950" if tp>=0 else "#f85149"};">₹{tp:,.2f}</div><div class="mb">Live Portfolio</div></div>',unsafe_allow_html=True)
        comb=total_r+tp
        ru3.markdown(f'<div class="tc"><div class="mt">TOTAL P&L</div><div class="mv" style="color:{"#3fb950" if comb>=0 else "#f85149"};">₹{comb:,.2f}</div><div class="mb">Combined</div></div>',unsafe_allow_html=True)
        st.markdown("---")
        bs=df.loc[df['Returns_Pct'].idxmax()]; ws=df.loc[df['Returns_Pct'].idxmin()]; mw=df.loc[df['Weight'].idxmax()]
        a1,a2,a3=st.columns(3)
        a1.markdown(f'<div class="tc"><div class="mt">🔥 TOP GAINER</div><div class="mv" style="color:#3fb950;">{bs["share_name"]}</div><div class="mg">{bs["Returns_Pct"]:+.2f}%</div></div>',unsafe_allow_html=True)
        a2.markdown(f'<div class="tc"><div class="mt">⚠️ UNDERPERFORMER</div><div class="mv" style="color:#f85149;">{ws["share_name"]}</div><div class="mr">{ws["Returns_Pct"]:+.2f}%</div></div>',unsafe_allow_html=True)
        a3.markdown(f'<div class="tc"><div class="mt">🏢 MAX WEIGHT</div><div class="mv" style="color:#58a6ff;">{mw["share_name"]}</div><div class="mb">{mw["Weight"]:.2f}%</div></div>',unsafe_allow_html=True)
        ca1,ca2=st.columns(2)
        with ca1:
            st.markdown("<h4>🗺️ Heatmap</h4>",unsafe_allow_html=True)
            dt_=df.groupby('share_name',as_index=False).agg({'Invested':'sum','PnL':'sum'})
            dt_['Ret']=(dt_['PnL']/dt_['Invested'].replace(0,1)*100)
            fig_tr=px.treemap(dt_,path=['share_name'],values='Invested',color='Ret',color_continuous_scale='RdYlGn',color_continuous_midpoint=0,template="plotly_dark")
            fig_tr.update_layout(margin=dict(l=10,r=10,t=10,b=10),paper_bgcolor='#0d1117')
            st.plotly_chart(fig_tr,use_container_width=True)
        with ca2:
            st.markdown("<h4>🔵 Risk vs Return</h4>",unsafe_allow_html=True)
            fig_sc=px.scatter(df,x='Invested',y='Returns_Pct',size='quantity',color='PnL',hover_name='share_name',color_continuous_scale='RdYlGn',template="plotly_dark",size_max=40)
            fig_sc.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(title="Investment ₹",gridcolor='#21262d'),yaxis=dict(title="Returns %",gridcolor='#21262d'))
            st.plotly_chart(fig_sc,use_container_width=True)

    # ═══ SINGLE STOCK DEEP-DIVE ═══════════════════════════════════════
    elif "Single Stock" in menu or "🔍" in menu:
        st.markdown("<h3>🔍 Single Stock Deep-Dive</h3>",unsafe_allow_html=True)
        ss_=st.selectbox("Select stock:",sorted(df['share_name'].unique()))
        sr=df[df['share_name']==ss_]; sd=sr.iloc[0]
        tq_=sr['quantity'].sum(); ti_=sr['Invested'].sum()
        ab_=ti_/tq_ if tq_>0 else 0; tc_2=sr['Current'].sum(); tp_s=sr['PnL'].sum()
        rp_=(tp_s/ti_*100) if ti_>0 else 0
        sc1,sc2,sc3,sc4,sc5,sc6=st.columns(6)
        sc1.markdown(f'<div class="tc"><div class="mt">AVG BUY</div><div class="mv">₹{ab_:,.2f}</div></div>',unsafe_allow_html=True)
        sc2.markdown(f'<div class="tc"><div class="mt">LIVE PRICE</div><div class="mv">₹{sd["Simulated_Live"]:,.2f}</div></div>',unsafe_allow_html=True)
        sc3.markdown(f'<div class="tc"><div class="mt">NET P&L</div><div class="mv" style="color:{"#3fb950" if tp_s>=0 else "#f85149"};">₹{tp_s:,.0f}</div></div>',unsafe_allow_html=True)
        sc4.markdown(f'<div class="tc"><div class="mt">RETURN</div><div class="mv" style="color:{"#3fb950" if rp_>=0 else "#f85149"};">{rp_:+.2f}%</div></div>',unsafe_allow_html=True)
        sc5.markdown(f'<div class="tc"><div class="mt">52W HIGH</div><div class="mv" style="color:#3fb950;">₹{sd["high_52w"]:,.2f}</div></div>',unsafe_allow_html=True)
        sc6.markdown(f'<div class="tc"><div class="mt">52W LOW</div><div class="mv" style="color:#f85149;">₹{sd["low_52w"]:,.2f}</div></div>',unsafe_allow_html=True)
        rtk=sd.get('resolved_ticker','')
        if rtk:
            try: h1y_=yf.Ticker(rtk).history(period="1y")
            except: h1y_=pd.DataFrame()
            if not h1y_.empty:
                fig_ss=go.Figure()
                fig_ss.add_trace(go.Scatter(x=h1y_.index,y=h1y_['Close'],line=dict(color='#58a6ff',width=2),fill='tozeroy',fillcolor='rgba(88,166,255,0.06)'))
                fig_ss.add_hline(y=ab_,line_dash="dash",line_color="#e3b341",annotation_text=f"Avg Buy ₹{ab_:,.2f}",annotation_dict=dict(font=dict(color="#e3b341")))
                if sd['high_52w']>0:
                    fig_ss.add_hline(y=sd['high_52w'],line_dash="dot",line_color="#3fb950",annotation_text=f"52W Hi",annotation_dict=dict(font=dict(color="#3fb950")))
                    fig_ss.add_hline(y=sd['low_52w'],line_dash="dot",line_color="#f85149",annotation_text=f"52W Lo",annotation_dict=dict(font=dict(color="#f85149")))
                fig_ss.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=40,b=10),title=dict(text=f"{ss_} — 1-Year Chart",font=dict(color='#e6edf3')),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d',title='₹'),showlegend=False)
                st.plotly_chart(fig_ss,use_container_width=True)
        fig_g=go.Figure(go.Indicator(mode="gauge+number+delta",value=rp_,delta={'reference':0,'suffix':'%'},domain={'x':[0,1],'y':[0,1]},title={'text':f"Return — {ss_}",'font':{'color':'#e6edf3'}},number={'suffix':'%','font':{'color':'#58a6ff'}},gauge={'axis':{'range':[-50,100]},'bar':{'color':'#58a6ff'},'steps':[{'range':[-50,0],'color':'rgba(248,81,73,0.15)'},{'range':[0,100],'color':'rgba(63,185,80,0.12)'}],'threshold':{'line':{'color':'#e3b341','width':3},'thickness':0.75,'value':target_pct}}))
        fig_g.update_layout(paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=20,r=20,t=50,b=20))
        st.plotly_chart(fig_g,use_container_width=True)

else:
    st.info("💡 Terminal ready! Upload your portfolio file, or explore any menu option above — AI Advisor, Technical Indicators, Options Chain, and MF Tracker all work without a portfolio file.")
