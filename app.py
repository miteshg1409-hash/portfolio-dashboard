import streamlit as st
import pandas as pd
import re
import os
import json
import smtplib
import ssl
import feedparser
import requests as _requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import yfinance as yf
from streamlit_autorefresh import st_autorefresh
import google.generativeai as genai

# ── Gemini AI Configuration ───────────────────────────────────────────
GOOGLE_API_KEY = "YOUR_GEMINI_API_KEY_HERE"  # Replace with your actual Gemini API Key
if GOOGLE_API_KEY != "YOUR_GEMINI_API_KEY_HERE":
    genai.configure(api_key=GOOGLE_API_KEY)

# ── IST timezone ──────────────────────────────────────────────────────
IST = timezone(timedelta(hours=5, minutes=30))
def now_ist():
    return datetime.now(IST)

# ── Persistent file paths ─────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
OVERRIDES_FILE   = os.path.join(_BASE, "ticker_overrides.json")
MAPPING_FILE     = os.path.join(_BASE, "column_mappings.json")
TRANSACTIONS_FILE= os.path.join(_BASE, "transactions.csv")
HISTORY_FILE     = os.path.join(_BASE, "portfolio_history.csv")
ALERTS_FILE      = os.path.join(_BASE, "price_alerts.json")
SETTINGS_FILE    = os.path.join(_BASE, "app_settings.json")

TX_COLUMNS       = ["date","share_name","ticker","txn_type","quantity","price"]
HISTORY_COLUMNS  = ["date","total_invested","total_current","total_pnl"]

# ── Generic load/save helpers ─────────────────────────────────────────
def _load_json(path, default):
    try:
        if os.path.exists(path):
            with open(path,"r",encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return default

def _save_json(path, data):
    try:
        with open(path,"w",encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def load_overrides():    return _load_json(OVERRIDES_FILE, {})
def save_overrides(d):   return _save_json(OVERRIDES_FILE, d)
def load_mappings():     return _load_json(MAPPING_FILE, {})
def save_mappings(d):    return _save_json(MAPPING_FILE, d)
def load_price_alerts(): return _load_json(ALERTS_FILE, {})
def save_price_alerts(d):return _save_json(ALERTS_FILE, d)
def load_settings():     return _load_json(SETTINGS_FILE, {})
def save_settings(d):    return _save_json(SETTINGS_FILE, d)

# ── Transaction helpers ───────────────────────────────────────────────
def load_transactions():
    try:
        if os.path.exists(TRANSACTIONS_FILE):
            df_tx = pd.read_csv(TRANSACTIONS_FILE)
            df_tx['date'] = pd.to_datetime(df_tx['date'], errors='coerce')
            return df_tx
    except Exception:
        pass
    return pd.DataFrame(columns=TX_COLUMNS)

def save_transactions(df_tx):
    try:
        out = df_tx.copy()
        out['date'] = pd.to_datetime(out['date']).dt.strftime('%Y-%m-%d')
        out.to_csv(TRANSACTIONS_FILE, index=False)
        return True
    except Exception:
        return False

def append_transactions(new_rows):
    combined = pd.concat([load_transactions(), new_rows], ignore_index=True)
    save_transactions(combined)
    return combined

def append_history_snapshot(total_invested, total_current, total_pnl):
    try:
        today = now_ist().strftime('%Y-%m-%d')
        hist = pd.read_csv(HISTORY_FILE) if os.path.exists(HISTORY_FILE) else pd.DataFrame(columns=HISTORY_COLUMNS)
        hist = hist[hist['date'] != today]
        hist = pd.concat([hist, pd.DataFrame([{"date":today,"total_invested":total_invested,"total_current":total_current,"total_pnl":total_pnl}])], ignore_index=True)
        hist.to_csv(HISTORY_FILE, index=False)
    except Exception:
        pass

def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            h = pd.read_csv(HISTORY_FILE)
            h['date'] = pd.to_datetime(h['date'])
            return h.sort_values('date')
    except Exception:
        pass
    return pd.DataFrame(columns=HISTORY_COLUMNS)

# ══════════════════════════════════════════════════════════════════════
# PAGE CONFIG + THEME
# ══════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="AlphaPortfolio Terminal Pro+", layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
.stApp{background-color:#0d1117;color:#cdd9e5;}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#161b22 0%,#0d1117 100%);border-right:1px solid #30363d;}
[data-testid="stSidebar"] *{color:#cdd9e5!important;}
.stTabs [data-baseweb="tab-list"]{background-color:#161b22;border-radius:8px 8px 0 0;padding:4px 6px 0;gap:4px;border-bottom:2px solid #30363d;}
.stTabs [data-baseweb="tab"]{background-color:#21262d;color:#8b949e!important;border-radius:6px 6px 0 0;padding:8px 16px;font-weight:600;font-size:13px;border:1px solid #30363d;border-bottom:none;transition:all .2s;}
.stTabs [aria-selected="true"]{background-color:#1f6feb!important;color:#fff!important;border-color:#1f6feb!important;}
.stTabs [data-baseweb="tab"]:hover{background-color:#30363d!important;color:#e6edf3!important;}
.stTabs [data-baseweb="tab-panel"]{background-color:#161b22;border:1px solid #30363d;border-top:none;border-radius:0 0 8px 8px;padding:18px;}
.terminal-card{background:linear-gradient(135deg,#161b22 0%,#1c2128 100%);padding:18px 20px;border-radius:10px;border:1px solid #30363d;box-shadow:0 2px 12px rgba(0,0,0,.4);margin-bottom:14px;transition:border-color .2s;}
.terminal-card:hover{border-color:#1f6feb;}
.metric-title{font-size:11px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:1.2px;}
.metric-value{font-size:22px;color:#e6edf3;font-weight:700;margin-top:6px;font-family:'Courier New',monospace;}
.metric-status-green{color:#3fb950;font-size:12px;font-weight:600;margin-top:4px;}
.metric-status-red{color:#f85149;font-size:12px;font-weight:600;margin-top:4px;}
.metric-status-blue{color:#58a6ff;font-size:12px;font-weight:600;margin-top:4px;}
.risk-warning{background-color:rgba(248,81,73,.12);border:1px solid #f85149;padding:12px 16px;border-radius:8px;color:#ffa198;margin-bottom:14px;font-size:13px;line-height:1.6;}
.alert-box-high{background-color:rgba(63,185,80,.12);border:1px solid #3fb950;padding:10px 14px;border-radius:8px;color:#56d364;margin-bottom:10px;font-size:13px;}
.alert-box-low{background-color:rgba(248,81,73,.12);border:1px solid #f85149;padding:10px 14px;border-radius:8px;color:#ffa198;margin-bottom:10px;font-size:13px;}
.map-box{background-color:#1c2128;padding:14px 18px;border-radius:8px;border:1px dashed #58a6ff;margin-bottom:18px;color:#cdd9e5;}
.market-bar{background:#161b22;border-bottom:1px solid #30363d;padding:10px 16px;display:flex;gap:24px;align-items:center;flex-wrap:wrap;font-size:13px;}
.market-item{display:flex;flex-direction:column;align-items:flex-start;}
.market-name{font-size:10px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.8px;}
.market-val{font-family:'Courier New',monospace;font-weight:700;color:#e6edf3;}
.market-chg-pos{color:#3fb950;font-size:11px;font-weight:600;}
.market-chg-neg{color:#f85149;font-size:11px;font-weight:600;}
.news-card{background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:12px 14px;margin-bottom:8px;transition:border-color .2s;}
.news-card:hover{border-color:#58a6ff;}
.news-title{color:#e6edf3;font-weight:600;font-size:13px;line-height:1.4;}
.news-meta{color:#8b949e;font-size:11px;margin-top:4px;}
.scorecard-row{display:flex;gap:12px;margin-bottom:10px;flex-wrap:wrap;}
.scorecard-item{flex:1;min-width:140px;background:#1c2128;border:1px solid #30363d;border-radius:8px;padding:10px 14px;}
.scorecard-label{font-size:10px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:.8px;}
.scorecard-val{font-size:18px;font-weight:700;font-family:'Courier New',monospace;margin-top:4px;}
.stTextInput>div>div>input,.stSelectbox>div>div>div{background-color:#21262d!important;color:#e6edf3!important;border:1px solid #30363d!important;border-radius:6px!important;}
.stDataFrame{border:1px solid #30363d!important;border-radius:8px;}
.stButton>button{background-color:#21262d;color:#cdd9e5;border:1px solid #30363d;border-radius:6px;font-weight:600;transition:all .2s;}
.stButton>button:hover{background-color:#1f6feb;color:#fff;border-color:#1f6feb;}
::-webkit-scrollbar{width:6px;height:6px;}
::-webkit-scrollbar-track{background:#0d1117;}
::-webkit-scrollbar-thumb{background:#30363d;border-radius:3px;}
::-webkit-scrollbar-thumb:hover{background:#58a6ff;}
h1,h2,h3,h4{color:#e6edf3!important;}
</style>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# AUTO-REFRESH every 1 second
# ══════════════════════════════════════════════════════════════════════
st_autorefresh(interval=1000, key="live_price_autorefresh")

# ══════════════════════════════════════════════════════════════════════
# TICKER RESOLVER
# ══════════════════════════════════════════════════════════════════════
_TICKER_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9.\-&]*$')

def _looks_like_ticker(value):
    v = value.strip()
    if not v: return False
    vu = v.upper()
    if vu.endswith('.NS') or vu.endswith('.BO') or vu.endswith('.BSE'): return True
    if ' ' in v or any(c.islower() for c in v): return False
    return len(vu) <= 12 and bool(_TICKER_PATTERN.match(vu))

def _search_yahoo_symbol(query):
    quotes = []
    try:
        r = _requests.get("https://query2.finance.yahoo.com/v1/finance/search",
            params={"q":query,"quotesCount":8,"newsCount":0},
            headers={"User-Agent":"Mozilla/5.0"}, timeout=6)
        if r.status_code == 200:
            quotes = r.json().get("quotes",[])
    except Exception:
        pass
    if not quotes:
        try:
            quotes = yf.Search(query, max_results=8).quotes or []
        except Exception:
            pass
    if not quotes: return None
    eq = [q for q in quotes if q.get("quoteType") in ("EQUITY","ETF",None)] or quotes
    for q in eq:
        if q.get("symbol","").endswith(".NS"): return q["symbol"]
    for q in eq:
        if q.get("symbol","").endswith(".BO"): return q["symbol"]
    return eq[0].get("symbol")

@st.cache_data(ttl=43200, show_spinner=False)
def resolve_tickers(raw_names_tuple, manual_overrides_tuple):
    overrides = dict(manual_overrides_tuple)
    resolved = {}
    for raw in raw_names_tuple:
        rc = str(raw).strip()
        if raw in overrides and overrides[raw]:
            resolved[raw] = overrides[raw].strip().upper(); continue
        if not rc:
            resolved[raw] = None; continue
        resolved[raw] = rc.upper() if _looks_like_ticker(rc) else _search_yahoo_symbol(rc)
    return resolved

@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_prices_from_yahoo(tickers_list):
    d = {}
    for t in tickers_list:
        if not t: continue
        try:
            h = yf.Ticker(t).history(period="2d")
            d[t] = h['Close'].iloc[-1] if not h.empty else 0
        except Exception:
            d[t] = 0
    return d

@st.cache_data(ttl=60, show_spinner=False)
def fetch_day_change(tickers_list):
    d = {}
    for t in tickers_list:
        if not t: continue
        try:
            h = yf.Ticker(t).history(period="2d")
            if len(h) >= 2:
                prev,curr,vol = h['Close'].iloc[-2],h['Close'].iloc[-1],h['Volume'].iloc[-1]
                d[t] = (round((curr-prev)/prev*100,2) if prev>0 else 0, round(prev,2), int(vol))
            else:
                d[t] = (0.0,0.0,0)
        except Exception:
            d[t] = (0.0,0.0,0)
    return d

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_52week_range(tickers_list):
    d = {}
    for t in tickers_list:
        if not t: continue
        try:
            h = yf.Ticker(t).history(period="1y")
            d[t] = (h['High'].max(), h['Low'].min()) if not h.empty else (0,0)
        except Exception:
            d[t] = (0,0)
    return d

@st.cache_data(ttl=21600, show_spinner=False)
def fetch_sector_info(tickers_list):
    d = {}
    for t in tickers_list:
        if not t: continue
        try:
            d[t] = yf.Ticker(t).info.get('sector') or 'Unknown'
        except Exception:
            d[t] = 'Unknown'
    return d

# ══════════════════════════════════════════════════════════════════════
# INDICES, NEWS FEED & BENCHMARKS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=120, show_spinner=False)
def fetch_market_indices():
    indices = {"NIFTY 50":"^NSEI","SENSEX":"^BSESN","BANK NIFTY":"^NSEBANK","NIFTY IT":"^CNXIT","GOLD (MCX)":"GC=F"}
    result = {}
    for name, sym in indices.items():
        try:
            h = yf.Ticker(sym).history(period="2d")
            if len(h) >= 2:
                curr,prev = h['Close'].iloc[-1],h['Close'].iloc[-2]
                result[name] = (round(curr,2), round((curr-prev)/prev*100,2))
            elif len(h)==1:
                result[name] = (round(h['Close'].iloc[-1],2), 0.0)
        except Exception:
            pass
    return result

@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_news(tickers_list, max_per_ticker=4):
    from email.utils import parsedate_to_datetime
    two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
    all_news = []
    seen_titles = set()

    for ticker in list(tickers_list)[:20]:
        if not ticker: continue
        clean_name = ticker.replace(".NS", "").replace(".BO", "").replace(".BSE", "")
        search_terms = [
            f"https://news.google.com/rss/search?q={clean_name}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en",
            f"https://news.google.com/rss/search?q={clean_name}+shares&hl=en-IN&gl=IN&ceid=IN:en",
        ]
        for url in search_terms:
            try:
                feed = feedparser.parse(url)
                for entry in feed.entries[:max_per_ticker]:
                    title = entry.get("title", "").strip()
                    if not title or title in seen_titles: continue
                    pub_str = entry.get("published", "")
                    try:
                        pub_dt = parsedate_to_datetime(pub_str) if pub_str else None
                        if pub_dt and pub_dt < two_weeks_ago: continue
                        pub_display = pub_dt.strftime("%d %b %Y, %H:%M") if pub_dt else pub_str[:16]
                    except Exception:
                        pub_display = pub_str[:16]; pub_dt = None
                    seen_titles.add(title)
                    all_news.append({
                        "ticker": ticker, "title": title, "link": entry.get("link", "#"),
                        "published": pub_display, "pub_dt": pub_dt,
                        "source": entry.get("source", {}).get("title", "Google News") if hasattr(entry.get("source", ""), "get") else "Google News",
                        "summary": entry.get("summary", "")[:200] if entry.get("summary") else "",
                    })
            except Exception: pass

    indian_feeds = [
        ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/stocks/rss.cms"),
        ("Moneycontrol News",       "https://www.moneycontrol.com/rss/latestnews.xml"),
        ("LiveMint Markets",        "https://www.livemint.com/rss/markets"),
    ]
    for source_name, url in indian_feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles: continue
                pub_str = entry.get("published", "")
                try:
                    pub_dt = parsedate_to_datetime(pub_str) if pub_str else None
                    if pub_dt and pub_dt < two_weeks_ago: continue
                    pub_display = pub_dt.strftime("%d %b %Y, %H:%M") if pub_dt else pub_str[:16]
                except Exception:
                    pub_display = pub_str[:16]; pub_dt = None
                seen_titles.add(title)
                all_news.append({
                    "ticker": "📰 Market", "title": title, "link": entry.get("link", "#"),
                    "published": pub_display, "pub_dt": pub_dt, "source": source_name,
                    "summary": entry.get("summary", "")[:200] if entry.get("summary") else "",
                })
        except Exception: pass

    all_news.sort(key=lambda x: x["pub_dt"] if x["pub_dt"] else datetime(2000, 1, 1, tzinfo=timezone.utc), reverse=True)
    return all_news[:60]

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark_returns(period="1y"):
    try:
        h = yf.Ticker("^NSEI").history(period=period)
        if not h.empty:
            start,end = h['Close'].iloc[0], h['Close'].iloc[-1]
            return round((end-start)/start*100, 2), h
    except Exception: pass
    return None, pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════
# ALERTS SYSTEM
# ══════════════════════════════════════════════════════════════════════
def send_telegram_alert(bot_token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = _requests.post(url, json={"chat_id":chat_id,"text":message,"parse_mode":"HTML"}, timeout=8)
        return r.status_code == 200, r.text
    except Exception as e: return False, str(e)

def send_email_alert(sender_email, app_password, recipient_email, subject, body):
    try:
        msg = MIMEMultipart("alternative")
        msg['Subject'] = subject; msg['From'] = sender_email; msg['To'] = recipient_email
        msg.attach(MIMEText(body, "plain"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
            s.login(sender_email, app_password)
            s.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent"
    except Exception as e: return False, str(e)

def _dispatch_alert(subject, body, settings):
    if settings.get("email_enabled") and settings.get("email_sender") and settings.get("email_password"):
        send_email_alert(settings["email_sender"], settings["email_password"], settings.get("email_recipient", settings["email_sender"]), subject, body)
    if settings.get("telegram_enabled") and settings.get("telegram_token") and settings.get("telegram_chat_id"):
        send_telegram_alert(settings["telegram_token"], settings["telegram_chat_id"], f"<b>{subject}</b>\n\n{body}")

def check_52week_alerts(df_pos, already_alerted_set, settings):
    for _, row in df_pos.iterrows():
        ticker = row.get('resolved_ticker')
        live = row.get('live_price', 0)
        h52, l52 = row.get('high_52w',0), row.get('low_52w',0)
        name = row.get('share_name', ticker)
        if not ticker or live==0: continue
        for key, flag, price_key, label, emoji in [
            (f"{ticker}_52H", h52 and live>=h52, h52, "52-WEEK HIGH", "📈"),
            (f"{ticker}_52L", l52 and live<=l52, l52, "52-WEEK LOW",  "📉"),
        ]:
            if flag and key not in already_alerted_set:
                subj = f"{emoji} {label} Alert: {name} ({ticker})"
                body = f"{name} touched its {label}.\nPrice: ₹{live:,.2f}\nTime: {now_ist().strftime('%Y-%m-%d %H:%M:%S')}"
                _dispatch_alert(subj, body, settings)
                already_alerted_set.add(key)

def check_price_alerts(live_prices_map, already_alerted_set, settings):
    alerts = load_price_alerts()
    for ticker, al in alerts.items():
        live = live_prices_map.get(ticker, 0)
        if live == 0: continue
        for kind, threshold, emoji in [("target", al.get("target"), "🎯"), ("stop", al.get("stop"), "🛑")]:
            if not threshold: continue
            key = f"{ticker}_{kind}_{threshold}"
            hit = (kind=="target" and live >= threshold) or (kind=="stop" and live <= threshold)
            if hit and key not in already_alerted_set:
                label = "TARGET HIT" if kind=="target" else "STOP LOSS HIT"
                subj = f"{emoji} {label}: {ticker}"
                body = f"{ticker} has {label}.\nTrigger: ₹{threshold:,.2f}\nLive: ₹{live:,.2f}"
                _dispatch_alert(subj, body, settings)
                already_alerted_set.add(key)

# ══════════════════════════════════════════════════════════════════════
# FIFO + XIRR CALCULATIONS
# ══════════════════════════════════════════════════════════════════════
def compute_fifo_realized_pnl(df_tx):
    if df_tx.empty: return pd.DataFrame(), pd.DataFrame()
    realized_rows, open_lots_rows = [], []
    for share_name, group in df_tx.sort_values('date').groupby('share_name'):
        buy_queue = []
        for _, row in group.iterrows():
            qty = float(row['quantity']); price = float(row['price']); date = row['date']
            ticker = row.get('ticker','')
            if str(row['txn_type']).upper() == 'BUY':
                buy_queue.append({"date":date,"qty":qty,"price":price})
            elif str(row['txn_type']).upper() == 'SELL':
                qty_to_sell = qty
                while qty_to_sell > 1e-9 and buy_queue:
                    lot = buy_queue[0]
                    matched_qty = min(lot['qty'], qty_to_sell)
                    holding_days = (date-lot['date']).days if pd.notna(date) and pd.notna(lot['date']) else 0
                    realized_rows.append({"share_name":share_name,"ticker":ticker,"sell_date":date,"buy_date":lot['date'],
                        "quantity":matched_qty,"buy_price":lot['price'],"sell_price":price,
                        "realized_pnl":(price-lot['price'])*matched_qty,"holding_days":holding_days,
                        "tax_term":"LTCG (>1yr)" if holding_days>365 else "STCG (<1yr)"})
                    lot['qty'] -= matched_qty; qty_to_sell -= matched_qty
                    if lot['qty'] <= 1e-9: buy_queue.pop(0)
        for lot in buy_queue:
            if lot['qty'] > 1e-9:
                open_lots_rows.append({"share_name":share_name,"buy_date":lot['date'],"quantity":lot['qty'],"buy_price":lot['price']})
    return pd.DataFrame(realized_rows), pd.DataFrame(open_lots_rows)

def calculate_xirr(cashflows):
    if len(cashflows) < 2: return None
    dates = [c[0] for c in cashflows]; amounts = [c[1] for c in cashflows]; t0 = min(dates)
    def xnpv(rate): return sum(a/((1+rate)**((d-t0).days/365.0)) for d,a in zip(dates,amounts))
    def xnpv_d(rate): return sum(-((d-t0).days/365.0)*a/((1+rate)**(((d-t0).days/365.0)+1)) for d,a in zip(dates,amounts))
    rate = 0.1
    for _ in range(100):
        try:
            f, fp = xnpv(rate), xnpv_d(rate)
            if abs(fp)<1e-10: break
            nr = rate - f/fp
            if abs(nr-rate)<1e-7: rate=nr; break
            rate = nr
        except: break
    return rate * 100

# ══════════════════════════════════════════════════════════════════════
# SEARCH & SUGGESTIONS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=10, show_spinner=False)
def fetch_search_suggestions(query):
    if not query or len(query.strip())<2: return []
    suggestions = []
    try:
        r = _requests.get("https://query2.finance.yahoo.com/v1/finance/search", params={"q":query,"quotesCount":10,"newsCount":0}, headers={"User-Agent":"Mozilla/5.0"},timeout=4)
        if r.status_code==200:
            for q in r.json().get("quotes",[]):
                suggestions.append({"label":f"{q.get('longname') or q.get('shortname')} — {q.get('symbol')}", "ticker":q.get("symbol",""),"name":q.get("longname") or q.get("shortname")})
    except Exception: pass
    return suggestions[:10]

# ══════════════════════════════════════════════════════════════════════
# ★ NEW MOD: OPTIONS CHAIN VIEWER
# ══════════════════════════════════════════════════════════════════════
def render_options_chain(ticker):
    st.subheader(f"📊 Live Options Chain — {ticker}")
    try:
        t = yf.Ticker(ticker)
        expirations = t.options
        if not expirations:
            st.info("F&O Data available only for Index and selected derivative stocks.")
            return
        expiry = st.selectbox("Select Expiry Date", expirations)
        opt = t.option_chain(expiry)
        calls, puts = opt.calls[['strike', 'lastPrice', 'openInterest', 'impliedVolatility']], opt.puts[['strike', 'lastPrice', 'openInterest', 'impliedVolatility']]
        chain = pd.merge(calls, puts, on='strike', suffixes=('_Call', '_Put')).rename(columns={'strike':'Strike'})
        st.dataframe(chain.style.format({c: "₹{:,.2f}" if 'Price' in c else "{:,.2f}%" if 'Volatility' in c else "{:,.0f}" for c in chain.columns if c!='Strike'}), use_container_width=True)
    except Exception as e:
        st.error(f"Could not load Options Chain: {e}")

# ══════════════════════════════════════════════════════════════════════
# ★ NEW MOD: MUTUAL FUND PERFORMANCE TRACKER
# ══════════════════════════════════════════════════════════════════════
def render_mutual_fund_tracker():
    st.header("🏢 Mutual Fund Tracker & Comparison")
    mf_query = st.text_input("🔍 Search Mutual Fund (e.g., Parag Parikh, SBI Bluechip)", "")
    if len(mf_query) >= 3:
        try:
            r = _requests.get(f"https://api.mfapi.in/mf/search?q={mf_query}").json()
            if r:
                schemes = {s['schemeName']: s['schemeCode'] for s in r[:15]}
                sel_scheme = st.selectbox("Select Mutual Fund Scheme", list(schemes.keys()))
                code = schemes[sel_scheme]
                data = _requests.get(f"https://api.mfapi.in/mf/{code}").json()
                meta, nav_list = data['meta'], data['data']
                st.markdown(f"**Fund House:** {meta['fund_house']} | **Category:** {meta['scheme_category']}")
                df_nav = pd.DataFrame(nav_list)
                df_nav['nav'] = pd.to_numeric(df_nav['nav'])
                df_nav['date'] = pd.to_datetime(df_nav['date'], format='%d-%m-%Y')
                df_nav = df_nav.sort_values('date')
                
                latest_nav = df_nav['nav'].iloc[-1]
                prev_nav = df_nav['nav'].iloc[-2] if len(df_nav)>1 else latest_nav
                chg = latest_nav - prev_nav
                pct = (chg/prev_nav)*100
                
                c1, c2 = st.columns(2)
                c1.metric("Latest NAV", f"₹{latest_nav:,.4f}", f"{chg:+,.4f} ({pct:+.2f}%)")
                
                fig = px.line(df_nav, x='date', y='nav', title=f"{meta['scheme_name']} NAV Growth")
                fig.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'))
                st.plotly_chart(fig, use_container_width=True)
            else: st.info("No funds matched your search.")
        except Exception as e: st.error(f"Error fetching MF data: {e}")

# ══════════════════════════════════════════════════════════════════════
# MAIN APP INTERFACE
# ══════════════════════════════════════════════════════════════════════
# TOP TICKER BANNER
indices_data = fetch_market_indices()
if indices_data:
    cols = st.columns(len(indices_data))
    for i, (name, (val, chg)) in enumerate(indices_data.items()):
        with cols[i]:
            chg_style = "market-chg-pos" if chg>=0 else "market-chg-neg"
            st.markdown(f"""<div class="market-item">
                <span class="market-name">{name}</span>
                <span class="market-val">₹{val:,.2f}</span>
                <span class="{chg_style}">{chg:+.2f}%</span>
            </div>""", unsafe_allow_html=True)

st.title("AlphaPortfolio Terminal Pro+")

tabs = st.tabs(["📊 Portfolio Dashboard", "🔍 Search & Advanced Charts", "🤖 AI Portfolio Advisor", "🎯 Derivatives (Options)", "🏢 Mutual Funds", "⚙️ Settings"])

df_tx = load_transactions()
realized_df, open_lots = compute_fifo_realized_pnl(df_tx)

# Process Holdings Data
holdings_summary = []
if not open_lots.empty:
    for name, group in open_lots.groupby('share_name'):
        total_qty = group['quantity'].sum()
        avg_price = (group['buy_price'] * group['quantity']).sum() / total_qty
        holdings_summary.append({"share_name": name, "quantity": total_qty, "avg_price": avg_price})

df_holdings = pd.DataFrame(holdings_summary)
raw_names = tuple(df_holdings['share_name'].tolist()) if not df_holdings.empty else ()
overrides_dict = load_overrides()
resolved_map = resolve_tickers(raw_names, tuple(overrides_dict.items()))

if not df_holdings.empty:
    df_holdings['resolved_ticker'] = df_holdings['share_name'].map(resolved_map)
    live_map = fetch_live_prices_from_yahoo(list(resolved_map.values()))
    chg_map = fetch_day_change(list(resolved_map.values()))
    range_52w = fetch_52week_range(list(resolved_map.values()))
    sec_map = fetch_sector_info(list(resolved_map.values()))
    
    df_holdings['live_price'] = df_holdings['resolved_ticker'].map(live_map).fillna(0)
    df_holdings['Invested'] = df_holdings['quantity'] * df_holdings['avg_price']
    df_holdings['Current'] = df_holdings['quantity'] * df_holdings['live_price']
    df_holdings['PnL'] = df_holdings['Current'] - df_holdings['Invested']
    df_holdings['Return_%'] = (df_holdings['PnL'] / df_holdings['Invested'] * 100).fillna(0)
    df_holdings['sector'] = df_holdings['resolved_ticker'].map(sec_map)
    
    # Background background background alert dispatch
    if 'alerted_cache' not in st.session_state: st.session_state.alerted_cache = set()
    app_settings = load_settings()
    check_52week_alerts(df_holdings, st.session_state.alerted_cache, app_settings)
    check_price_alerts(live_map, st.session_state.alerted_cache, app_settings)

# TAB 1: DASHBOARD
with tabs[0]:
    if df_holdings.empty:
        st.info("No active holdings found. Please log transactions in Settings.")
    else:
        t_inv = df_holdings['Invested'].sum()
        t_cur = df_holdings['Current'].sum()
        t_pnl = t_cur - t_inv
        t_ret = (t_pnl / t_inv * 100) if t_inv > 0 else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Invested", f"₹{t_inv:,.2f}")
        c2.metric("Current Portfolio Value", f"₹{t_cur:,.2f}")
        c3.metric("Total Return P&L", f"₹{t_pnl:,.2f}", f"{t_ret:+.2f}%")
        
        st.subheader("Current Holdings Ledger")
        st.dataframe(df_holdings.style.format({"avg_price":"₹{:.2f}","live_price":"₹{:.2f}","Invested":"₹{:.2f}","Current":"₹{:.2f}","PnL":"₹{:.2f}","Return_%":"{:.2f}%"}), use_container_width=True)

# TAB 2: SEARCH & ADVANCED TECHNICAL INDICATORS CHART
with tabs[1]:
    st.header("📈 Technical Analysis Terminal")
    search_query = st.text_input("🔍 Stock Lookup (Name or Ticker Symbol)", "RELIANCE")
    if search_query:
        resolved_s = resolve_tickers((search_query,), tuple(overrides_dict.items())).get(search_query)
        if resolved_s:
            st.subheader(f"Displaying: {resolved_s}")
            try:
                hist_data = yf.Ticker(resolved_s).history(period="1y")
                if not hist_data.empty:
                    # Calculations for Technical Indicators
                    hist_data['MA20'] = hist_data['Close'].rolling(window=20).mean()
                    hist_data['MA50'] = hist_data['Close'].rolling(window=50).mean()
                    
                    # RSI Calculation
                    delta = hist_data['Close'].diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / loss
                    hist_data['RSI'] = 100 - (100 / (1 + rs))
                    
                    # Create Plotly Advanced Subplot Chart
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.7, 0.3], vertical_spacing=0.05)
                    fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['Close'], name='Price', line=dict(color='#58a6ff')), row=1, col=1)
                    fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['MA20'], name='MA20', line=dict(color='#3fb950', width=1)), row=1, col=1)
                    fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['MA50'], name='MA50', line=dict(color='#e3b341', width=1)), row=1, col=1)
                    
                    # RSI subplot
                    fig.add_trace(go.Scatter(x=hist_data.index, y=hist_data['RSI'], name='RSI (14)', line=dict(color='#ffa198')), row=2, col=1)
                    fig.add_hline(y=70, line_dash="dash", line_color="#f85149", row=2, col=1)
                    fig.add_hline(y=30, line_dash="dash", line_color="#3fb950", row=2, col=1)
                    
                    fig.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'), height=600, showlegend=True)
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e: st.error(f"Error drawing indicators chart: {e}")
        else: st.warning("Ticker could not be resolved.")

# TAB 3: ★ AI PORTFOLIO ADVISOR
with tabs[2]:
    st.header("🤖 AI Generation Portfolio Advisor (Gemini)")
    if GOOGLE_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        st.warning("AI Insights चा वापर करण्यासाठी आधी 'app.py' फाईलच्या सुरुवातीला तुमची **Gemini API Key** जोडा.")
    elif df_holdings.empty:
        st.info("तुमचा पोर्टफोलिओ रिकामा आहे. सल्ला घेण्यासाठी आधी व्यवहार जोडा.")
    else:
        if st.button("✨ Run Portfolio Deep AI Audit"):
            with st.spinner("AI तुमच्या पोर्टफोलिओचे विश्लेषण करत आहे..."):
                try:
                    summary_json = df_holdings[['share_name', 'quantity', 'avg_price', 'live_price', 'PnL', 'sector']].to_json(orient='records')
                    prompt = f"""You are an elite financial wealth advisor. Analyze this retail stock portfolio and suggest tactical asset allocation, rebalancing, sector mitigation risks, and optimization insights based on this data:
                    {summary_json}
                    Provide clear, modular suggestions structured cleanly with bold headings."""
                    model = genai.GenerativeModel("gemini-pro")
                    response = model.generate_content(prompt)
                    st.markdown(response.text)
                except Exception as e:
                    st.error(f"AI Advisor system error: {e}")

# TAB 4: OPTIONS CHAIN
with tabs[3]:
    opt_search = st.text_input("🔍 F&O Asset Underlying Lookup (e.g., RELIANCE, SBIN, ^NSEI)", "^NSEI")
    if opt_search:
        resolved_o = resolve_tickers((opt_search,), tuple(overrides_dict.items())).get(opt_search)
        if resolved_o: render_options_chain(resolved_o)

# TAB 5: MUTUAL FUNDS
with tabs[4]:
    render_mutual_fund_tracker()

# TAB 6: SETTINGS & LEDGER LOGGING
with tabs[5]:
    st.header("🛠️ Operations Ledger & System Config")
    with st.expander("📝 Add New Transaction Record", expanded=True):
        with st.form("tx_add_form"):
            c1,c2,c3 = st.columns(3)
            tx_date = c1.date_input("Transaction Date")
            tx_name = c2.text_input("Company Name / Asset Name", placeholder="e.g. Tata Motors")
            tx_tick = c3.text_input("Yahoo Ticker (Optional)", placeholder="e.g. TATAMOTORS.NS")
            c4,c5,c6 = st.columns(3)
            tx_type = c4.selectbox("Type", ["BUY", "SELL"])
            tx_qty  = c5.number_input("Quantity", min_value=0.0, step=1.0)
            tx_prc  = c6.number_input("Execution Price (₹)", min_value=0.0, step=0.05)
            
            if st.form_submit_button("Commit Transaction to CSV"):
                if not tx_name: st.error("Asset name is mandatory.")
                else:
                    final_ticker = tx_tick.strip().upper() if tx_tick.strip() else None
                    new_row = pd.DataFrame([{"date":tx_date, "share_name":tx_name.strip(), "ticker":final_ticker, "txn_type":tx_type, "quantity":tx_qty, "price":tx_prc}])
                    append_transactions(new_row)
                    st.success("Transaction committed successfully!")
                    st.rerun()