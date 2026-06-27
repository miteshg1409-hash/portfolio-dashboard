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
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

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
# ★ NEW: MARKET INDICES (Nifty, Sensex, Bank Nifty, Gold)
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

# ══════════════════════════════════════════════════════════════════════
# ★ NEW: NEWS FEED via Yahoo Finance RSS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def fetch_stock_news(tickers_list, max_per_ticker=4):
    """Fetch news using Google News RSS (best Indian stock coverage) + ET Markets RSS.
    Returns articles from the last 2 weeks only, sorted newest first."""
    from email.utils import parsedate_to_datetime
    import time

    two_weeks_ago = datetime.now(timezone.utc) - timedelta(days=14)
    all_news = []
    seen_titles = set()

    # 1. Google News RSS per ticker (best for Indian stocks)
    for ticker in list(tickers_list)[:20]:
        if not ticker:
            continue
        # Strip exchange suffix for more natural search
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
                    if not title or title in seen_titles:
                        continue
                    # Parse date and filter last 2 weeks
                    pub_str = entry.get("published", "")
                    try:
                        pub_dt = parsedate_to_datetime(pub_str) if pub_str else None
                        if pub_dt and pub_dt < two_weeks_ago:
                            continue  # skip older than 2 weeks
                        pub_display = pub_dt.strftime("%d %b %Y, %H:%M") if pub_dt else pub_str[:16]
                    except Exception:
                        pub_display = pub_str[:16]
                        pub_dt = None

                    seen_titles.add(title)
                    all_news.append({
                        "ticker": ticker,
                        "title": title,
                        "link": entry.get("link", "#"),
                        "published": pub_display,
                        "pub_dt": pub_dt,
                        "source": entry.get("source", {}).get("title", "Google News") if hasattr(entry.get("source", ""), "get") else "Google News",
                        "summary": entry.get("summary", "")[:200] if entry.get("summary") else "",
                    })
            except Exception:
                pass

    # 2. Indian Finance RSS Feeds (broad market coverage)
    indian_feeds = [
        ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/stocks/rss.cms"),
        ("ET Corporate News",       "https://economictimes.indiatimes.com/news/company/corporate-trends/rssfeeds/2143429.cms"),
        ("Business Standard",       "https://www.business-standard.com/rss/markets-106.rss"),
        ("Moneycontrol News",       "https://www.moneycontrol.com/rss/latestnews.xml"),
        ("LiveMint Markets",        "https://www.livemint.com/rss/markets"),
    ]
    for source_name, url in indian_feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                title = entry.get("title", "").strip()
                if not title or title in seen_titles:
                    continue
                pub_str = entry.get("published", "")
                try:
                    pub_dt = parsedate_to_datetime(pub_str) if pub_str else None
                    if pub_dt and pub_dt < two_weeks_ago:
                        continue
                    pub_display = pub_dt.strftime("%d %b %Y, %H:%M") if pub_dt else pub_str[:16]
                except Exception:
                    pub_display = pub_str[:16]
                    pub_dt = None
                seen_titles.add(title)
                all_news.append({
                    "ticker": "📰 Market",
                    "title": title,
                    "link": entry.get("link", "#"),
                    "published": pub_display,
                    "pub_dt": pub_dt,
                    "source": source_name,
                    "summary": entry.get("summary", "")[:200] if entry.get("summary") else "",
                })
        except Exception:
            pass

    # Sort by date newest first, put None dates at end
    all_news.sort(
        key=lambda x: x["pub_dt"] if x["pub_dt"] else datetime(2000, 1, 1, tzinfo=timezone.utc),
        reverse=True
    )
    return all_news[:60]

# ══════════════════════════════════════════════════════════════════════
# ★ NEW: BENCHMARK COMPARISON (Portfolio vs Nifty 50)
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_benchmark_returns(period="1y"):
    try:
        h = yf.Ticker("^NSEI").history(period=period)
        if not h.empty:
            start,end = h['Close'].iloc[0], h['Close'].iloc[-1]
            return round((end-start)/start*100, 2), h
    except Exception:
        pass
    return None, pd.DataFrame()

# ══════════════════════════════════════════════════════════════════════
# ★ NEW: TELEGRAM ALERT
# ══════════════════════════════════════════════════════════════════════
def send_telegram_alert(bot_token, chat_id, message):
    """Send a Telegram message via Bot API. Returns (success, msg)."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        r = _requests.post(url, json={"chat_id":chat_id,"text":message,"parse_mode":"HTML"}, timeout=8)
        if r.status_code == 200:
            return True, "Telegram sent"
        return False, r.text
    except Exception as e:
        return False, str(e)

# ══════════════════════════════════════════════════════════════════════
# EMAIL
# ══════════════════════════════════════════════════════════════════════
def send_email_alert(sender_email, app_password, recipient_email, subject, body):
    try:
        msg = MIMEMultipart("alternative")
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg.attach(MIMEText(body, "plain"))
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
            s.login(sender_email, app_password)
            s.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent"
    except Exception as e:
        return False, str(e)

def _dispatch_alert(subject, body, settings, ticker=""):
    """Send via Email and/or Telegram based on saved settings."""
    sent = []
    if settings.get("email_enabled") and settings.get("email_sender") and settings.get("email_password"):
        ok, msg = send_email_alert(settings["email_sender"], settings["email_password"],
                                   settings.get("email_recipient", settings["email_sender"]), subject, body)
        sent.append(("Email", ok, msg))
    if settings.get("telegram_enabled") and settings.get("telegram_token") and settings.get("telegram_chat_id"):
        ok, msg = send_telegram_alert(settings["telegram_token"], settings["telegram_chat_id"], f"<b>{subject}</b>\n\n{body}")
        sent.append(("Telegram", ok, msg))
    return sent

# ══════════════════════════════════════════════════════════════════════
# 52-WEEK ALERTS
# ══════════════════════════════════════════════════════════════════════
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
                body = (f"{name} has touched its {label}.\n"
                        f"Current Price: ₹{live:,.2f}\n"
                        f"{label}: ₹{price_key:,.2f}\n"
                        f"Time (IST): {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
                _dispatch_alert(subj, body, settings)
                already_alerted_set.add(key)

# ══════════════════════════════════════════════════════════════════════
# ★ NEW: PRICE ALERTS (target/stop)
# ══════════════════════════════════════════════════════════════════════
def check_price_alerts(live_prices_map, already_alerted_set, settings):
    """Check user-set target/stop alerts against current live prices."""
    alerts = load_price_alerts()
    triggered = []
    for ticker, al in alerts.items():
        live = live_prices_map.get(ticker, 0)
        if live == 0: continue
        for kind, threshold, emoji in [
            ("target", al.get("target"), "🎯"),
            ("stop",   al.get("stop"),   "🛑"),
        ]:
            if not threshold: continue
            key = f"{ticker}_{kind}_{threshold}"
            hit = (kind=="target" and live >= threshold) or (kind=="stop" and live <= threshold)
            if hit and key not in already_alerted_set:
                label = "TARGET HIT" if kind=="target" else "STOP LOSS HIT"
                subj = f"{emoji} {label}: {ticker}"
                body = (f"{ticker} has {label}.\n"
                        f"Alert Price: ₹{threshold:,.2f}\n"
                        f"Current Price: ₹{live:,.2f}\n"
                        f"Time (IST): {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
                _dispatch_alert(subj, body, settings)
                already_alerted_set.add(key)
                triggered.append((ticker, label, live, threshold))
    return triggered

# ══════════════════════════════════════════════════════════════════════
# FIFO + XIRR
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
    def xnpv(rate):
        return sum(a/((1+rate)**((d-t0).days/365.0)) for d,a in zip(dates,amounts))
    def xnpv_d(rate):
        return sum(-((d-t0).days/365.0)*a/((1+rate)**(((d-t0).days/365.0)+1)) for d,a in zip(dates,amounts))
    rate = 0.1
    for _ in range(100):
        try:
            f,fp = xnpv(rate),xnpv_d(rate)
            if abs(fp)<1e-10: break
            nr = rate-f/fp
            if abs(nr-rate)<1e-7: rate=nr; break
            rate = nr
        except: break
    if rate<=-1 or rate>100:
        lo,hi = -0.99,10.0
        for _ in range(200):
            mid=(lo+hi)/2
            try: val=xnpv(mid)
            except: val=float('inf')
            if abs(val)<1e-3: return mid*100
            if val>0: lo=mid
            else: hi=mid
        return None
    return rate*100

# ══════════════════════════════════════════════════════════════════════
# SEARCH SUGGESTIONS
# ══════════════════════════════════════════════════════════════════════
@st.cache_data(ttl=10, show_spinner=False)
def fetch_search_suggestions(query):
    if not query or len(query.strip())<2: return []
    suggestions = []
    try:
        r = _requests.get("https://query2.finance.yahoo.com/v1/finance/search",
            params={"q":query,"quotesCount":10,"newsCount":0},
            headers={"User-Agent":"Mozilla/5.0"},timeout=4)
        if r.status_code==200:
            for q in r.json().get("quotes",[]):
                if q.get("quoteType") not in ("EQUITY","ETF","MUTUALFUND",None): continue
                suggestions.append({"label":f"{q.get('longname') or q.get('shortname') or q.get('symbol')}  —  {q.get('symbol')}  [{q.get('exchange','')}]",
                    "ticker":q.get("symbol",""),"name":q.get("longname") or q.get("shortname") or q.get("symbol","")})
    except Exception:
        pass
    if not suggestions:
        try:
            for q in (yf.Search(query,max_results=10).quotes or []):
                suggestions.append({"label":f"{q.get('longname') or q.get('shortname') or q.get('symbol')}  —  {q.get('symbol')}",
                    "ticker":q.get("symbol",""),"name":q.get("longname") or q.get("shortname") or q.get("symbol","")})
        except Exception:
            pass
    return suggestions[:10]

@st.cache_data(ttl=60, show_spinner=False)
def search_any_stock(query):
    if not query or not query.strip(): return None
    ticker = query.strip().upper() if _looks_like_ticker(query.strip()) else _search_yahoo_symbol(query.strip())
    if not ticker: return None
    try:
        stock = yf.Ticker(ticker)
        h1d = stock.history(period="1d"); h1y = stock.history(period="1y")
        if h1d.empty: return None
        try: cname = stock.info.get('longName') or stock.info.get('shortName') or ticker; curr = stock.info.get('currency','')
        except: cname = ticker; curr = ''
        return {"ticker":ticker,"company_name":cname,"currency":curr,"live_price":h1d['Close'].iloc[-1],
                "high_52w":h1y['High'].max() if not h1y.empty else None,
                "low_52w":h1y['Low'].min() if not h1y.empty else None,"history":h1y}
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════
# ★ NEW: PORTFOLIO SCORECARD (detailed health metrics)
# ══════════════════════════════════════════════════════════════════════
def build_scorecard(df_h, benchmark_ret=None):
    """Returns a dict of advanced portfolio metrics."""
    n_stocks    = len(df_h['share_name'].unique())
    total_inv   = df_h['Invested'].sum()
    total_cur   = df_h['Current'].sum()
    total_pnl   = df_h['PnL'].sum()
    overall_ret = (total_pnl / total_inv * 100) if total_inv > 0 else 0
    win_rate    = (df_h['PnL'] > 0).sum() / max(len(df_h),1) * 100
    max_weight  = df_h['Weight'].max()
    max_dd      = ((df_h['Simulated_Live'] - df_h['buy_price']) / df_h['buy_price'].replace(0,1) * 100).min()
    avg_ret     = df_h['Returns_Pct'].mean()
    vol         = df_h['Returns_Pct'].std()
    sharpe      = (avg_ret / vol) if vol and vol > 0 else 0
    alpha       = (overall_ret - benchmark_ret) if benchmark_ret is not None else None

    # Scoring (100 pts total)
    score = 0
    score += 20 if n_stocks >= 15 else (15 if n_stocks >= 10 else (10 if n_stocks >= 5 else 4))
    score += min(20, int(win_rate / 5))
    score += 20 if max_weight < 10 else (14 if max_weight < 20 else (8 if max_weight < 30 else 2))
    score += 20 if overall_ret >= 20 else (15 if overall_ret >= 10 else (10 if overall_ret >= 0 else 2))
    score += 10 if sharpe > 1 else (7 if sharpe > 0.5 else (4 if sharpe > 0 else 1))
    score += 10 if max_dd > -10 else (6 if max_dd > -20 else 2)

    label = ("Outstanding 🌟" if score >= 85 else "Excellent 💪" if score >= 70 else
             "Good 👍" if score >= 55 else "Moderate ⚠️" if score >= 40 else "Needs Work 🔴")
    color = ("#3fb950" if score >= 70 else "#e3b341" if score >= 45 else "#f85149")
    return {"score":score,"label":label,"color":color,"n_stocks":n_stocks,
            "win_rate":win_rate,"max_weight":max_weight,"overall_ret":overall_ret,
            "sharpe":sharpe,"alpha":alpha,"max_dd":max_dd,"volatility":vol}

def color_pnl(val):
    if isinstance(val, str): return ''
    return 'color:#3fb950;font-weight:bold;' if val>=0 else 'color:#f85149;font-weight:bold;'

# ══════════════════════════════════════════════════════════════════════
# SESSION STATE INIT
# ══════════════════════════════════════════════════════════════════════
if "alerted_keys"            not in st.session_state: st.session_state.alerted_keys = set()
if "manual_ticker_overrides" not in st.session_state: st.session_state.manual_ticker_overrides = load_overrides()
if "transactions_df"         not in st.session_state: st.session_state.transactions_df = load_transactions()
if "saved_mappings"          not in st.session_state: st.session_state.saved_mappings = load_mappings()
if "app_settings"            not in st.session_state: st.session_state.app_settings = load_settings()
if "search_selected_ticker"  not in st.session_state: st.session_state.search_selected_ticker = ""
if "search_last_query"       not in st.session_state: st.session_state.search_last_query = ""

_s = st.session_state.app_settings  # shorthand

# ══════════════════════════════════════════════════════════════════════
# ★ MARKET OVERVIEW BAR (top of every page)
# ══════════════════════════════════════════════════════════════════════
indices_data = fetch_market_indices()
if indices_data:
    parts = []
    for name,(val,chg) in indices_data.items():
        chg_cls = "market-chg-pos" if chg>=0 else "market-chg-neg"
        sign    = "▲" if chg>=0 else "▼"
        is_gold = "GOLD" in name
        val_str = f"${val:,.2f}" if is_gold else f"{val:,.2f}"
        parts.append(f"""<div class="market-item">
            <span class="market-name">{name}</span>
            <span class="market-val">{val_str}</span>
            <span class="{chg_cls}">{sign} {abs(chg):.2f}%</span>
        </div>""")
    ts = now_ist().strftime("%H:%M:%S IST")
    st.markdown(
        f'<div class="market-bar">{"".join(parts)}'
        f'<div class="market-item" style="margin-left:auto;"><span class="market-name">Last Updated</span>'
        f'<span class="market-val" style="font-size:12px;">{ts}</span></div></div>',
        unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<h2 style='color:#58a6ff;text-align:center;font-family:monospace;letter-spacing:2px;'>ALPHA TERMINAL</h2>", unsafe_allow_html=True)
    st.markdown("---")
    menu = st.radio("⚡ Terminal Monitor", [
        "🖥️ Overview Dashboard",
        "📈 Advanced Analysis",
        "🔍 Single Stock Matrix",
        "🔎 Search Any Stock",
        "💼 Transaction Ledger (Buy/Sell)",
        "📰 Market News Feed",
        "⚙️ Settings & Alerts",
    ])
    st.markdown("---")

    st.markdown("### 🔍 Quick Filter")
    stock_filter = st.selectbox("Filter:", ["All Holdings","🟢 Profit Only","🔴 Loss Only"])
    st.markdown("---")

    st.markdown("### 🎯 Risk Management")
    target_pct    = st.slider("Take Profit (%)",  5, 100,  20, 5)
    stop_loss_pct = st.slider("Stop Loss (%)",   -50,  -5, -10, 5)
    st.markdown("---")

    st.markdown("### 📉 Market Stress Test")
    market_shock  = st.slider("Simulate crash/rally (%)", -50, 50, 0, 5)
    st.markdown("---")

    st.markdown("### 🛠️ Ticker Overrides")
    if st.session_state.manual_ticker_overrides:
        st.caption(f"✅ {len(st.session_state.manual_ticker_overrides)} override(s) saved.")
        with st.expander("View / Delete"):
            for k,v in list(st.session_state.manual_ticker_overrides.items()):
                c1,c2 = st.columns([3,1])
                c1.write(f"**{k[:25]}** → `{v}`")
                if c2.button("❌", key=f"del_{k}"):
                    st.session_state.manual_ticker_overrides.pop(k, None)
                    save_overrides(st.session_state.manual_ticker_overrides)
                    st.cache_data.clear(); st.rerun()
    else:
        st.caption("No overrides saved yet.")

# ══════════════════════════════════════════════════════════════════════
# HEADER + FILE UPLOAD
# ══════════════════════════════════════════════════════════════════════
st.markdown("<h2 style='color:#e6edf3;'>📊 AlphaPortfolio Intelligence Terminal <span style='font-size:14px;color:#58a6ff;'>v5.0 Pro+</span></h2>", unsafe_allow_html=True)
uploaded_file = st.file_uploader("Drag and drop your holdings file (CSV or Excel)", type=['csv','xlsx'])

df = pd.DataFrame()
if uploaded_file is not None:
    try:
        df = pd.read_excel(uploaded_file) if uploaded_file.name.endswith('.xlsx') else pd.read_csv(uploaded_file)
    except Exception as e:
        st.error(f"⚠️ File Error: {e}")

# ══════════════════════════════════════════════════════════════════════
# ★ SETTINGS & ALERTS PAGE
# ══════════════════════════════════════════════════════════════════════
if "Settings" in menu or "⚙️" in menu:
    st.markdown("<h3>⚙️ Settings & Alert Configuration</h3>", unsafe_allow_html=True)
    set_tab1, set_tab2, set_tab3 = st.tabs(["📧 Email Alerts","📱 Telegram Alerts","🎯 Price Alerts"])

    with set_tab1:
        st.markdown("#### Gmail Email Alerts")
        st.caption("You need a Gmail **App Password** (not your normal password). Generate at myaccount.google.com → Security → App Passwords.")
        em_en  = st.checkbox("Enable Email Alerts", value=_s.get("email_enabled", False))
        em_sndr= st.text_input("Sender Gmail", value=_s.get("email_sender",""), placeholder="you@gmail.com")
        em_pwd = st.text_input("Gmail App Password", value=_s.get("email_password",""), type="password")
        em_rcpt= st.text_input("Recipient Email", value=_s.get("email_recipient",""), placeholder="you@gmail.com")
        if st.button("💾 Save Email Settings", use_container_width=True):
            _s.update({"email_enabled":em_en,"email_sender":em_sndr,"email_password":em_pwd,"email_recipient":em_rcpt})
            save_settings(_s); st.session_state.app_settings = _s
            st.success("✅ Email settings saved!")
        if st.button("🧪 Send Test Email", use_container_width=True):
            ok,msg = send_email_alert(em_sndr, em_pwd, em_rcpt or em_sndr, "AlphaPortfolio Test", "✅ Email alerts are working correctly!")
            st.success("Test email sent!") if ok else st.error(f"Failed: {msg}")

    with set_tab2:
        st.markdown("#### Telegram Bot Alerts")
        st.caption("Create a bot via [@BotFather](https://t.me/BotFather) → get token. Then message your bot once, and get your Chat ID from [@userinfobot](https://t.me/userinfobot).")
        tg_en  = st.checkbox("Enable Telegram Alerts", value=_s.get("telegram_enabled", False))
        tg_tok = st.text_input("Bot Token", value=_s.get("telegram_token",""), placeholder="123456:ABC-DEF...")
        tg_cid = st.text_input("Chat ID", value=_s.get("telegram_chat_id",""), placeholder="123456789")
        if st.button("💾 Save Telegram Settings", use_container_width=True):
            _s.update({"telegram_enabled":tg_en,"telegram_token":tg_tok,"telegram_chat_id":tg_cid})
            save_settings(_s); st.session_state.app_settings = _s
            st.success("✅ Telegram settings saved!")
        if st.button("🧪 Send Test Telegram Message", use_container_width=True):
            ok,msg = send_telegram_alert(tg_tok, tg_cid, "✅ <b>AlphaPortfolio</b> Telegram alerts are working!")
            st.success("Test message sent!") if ok else st.error(f"Failed: {msg}")

    with set_tab3:
        st.markdown("#### 🎯 Price Target & Stop-Loss Alerts")
        st.caption("Set a target price (alert when stock hits or crosses above) and/or a stop price (alert when it drops to or below). Alerts fire once per session.")
        existing_alerts = load_price_alerts()
        with st.form("price_alert_form", clear_on_submit=True):
            pa1,pa2,pa3,pa4 = st.columns(4)
            with pa1: pa_ticker = st.text_input("Yahoo Ticker", placeholder="e.g. RELIANCE.NS")
            with pa2: pa_name   = st.text_input("Label (optional)", placeholder="e.g. Reliance")
            with pa3: pa_target = st.number_input("Target Price ₹", min_value=0.0, step=1.0, format="%.2f")
            with pa4: pa_stop   = st.number_input("Stop Price ₹",   min_value=0.0, step=1.0, format="%.2f")
            if st.form_submit_button("➕ Add Alert", use_container_width=True):
                if pa_ticker.strip():
                    existing_alerts[pa_ticker.strip().upper()] = {
                        "name": pa_name.strip() or pa_ticker.strip().upper(),
                        "target": pa_target if pa_target > 0 else None,
                        "stop":   pa_stop   if pa_stop   > 0 else None,
                    }
                    save_price_alerts(existing_alerts)
                    st.success(f"✅ Alert added for {pa_ticker.strip().upper()}")
                    st.rerun()

        if existing_alerts:
            st.markdown("**Current Price Alerts:**")
            for tk, al in existing_alerts.items():
                ac1,ac2,ac3,ac4 = st.columns([2,2,2,1])
                ac1.write(f"**{tk}** ({al.get('name','')})")
                ac2.write(f"🎯 Target: ₹{al['target']:,.2f}" if al.get('target') else "🎯 Target: —")
                ac3.write(f"🛑 Stop: ₹{al['stop']:,.2f}"   if al.get('stop')   else "🛑 Stop: —")
                if ac4.button("🗑️", key=f"del_al_{tk}"):
                    existing_alerts.pop(tk, None)
                    save_price_alerts(existing_alerts); st.rerun()
        else:
            st.info("No price alerts set yet.")

# ══════════════════════════════════════════════════════════════════════
# ★ NEWS FEED PAGE
# ══════════════════════════════════════════════════════════════════════
elif "News Feed" in menu or "📰" in menu:
    st.markdown("<h3>📰 Market News Feed</h3>", unsafe_allow_html=True)

    news_query = st.text_input("Search news for any ticker or company:", placeholder="e.g. RELIANCE.NS, TCS, Infosys")
    news_tickers = []

    if news_query.strip():
        # Manual search
        tk = news_query.strip().upper() if _looks_like_ticker(news_query.strip()) else _search_yahoo_symbol(news_query.strip())
        if tk:
            news_tickers = [tk]

    elif not df.empty:
        # Auto-load from uploaded file — resolve tickers on the fly if not already done
        if 'resolved_ticker' in df.columns:
            # Already resolved (user visited Overview tab first)
            news_tickers = [t for t in df['resolved_ticker'].dropna().unique() if t]
        else:
            # File uploaded but not yet processed — resolve tickers now
            df_news = df.copy()
            df_news.columns = df_news.columns.str.strip()
            news_cols = list(df_news.columns)

            # Pick the ticker/company column using saved mapping or first column
            saved_pm_news = st.session_state.saved_mappings.get("portfolio", {})
            ticker_col_news = saved_pm_news.get("ticker", news_cols[0]) if saved_pm_news.get("ticker") in news_cols else news_cols[0]

            st.caption(f"📋 Auto-loading news for holdings from column: **{ticker_col_news}** — uses saved mapping or first column. Go to Overview Dashboard to change column mapping.")

            raw_names = [str(v).strip() for v in df_news[ticker_col_news].dropna().unique() if str(v).strip()]
            raw_names = [v for v in raw_names if v and not any(x in v.upper() for x in ['TOTAL','GRAND'])][:60]

            if raw_names:
                manual_ov = tuple(sorted(st.session_state.manual_ticker_overrides.items()))
                with st.spinner(f"🔎 Resolving {len(raw_names)} company names to Yahoo tickers for news..."):
                    resolution = resolve_tickers(tuple(raw_names), manual_ov)
                news_tickers = sorted({t for t in resolution.values() if t})

    if news_tickers:
        st.caption(f"Loading news for {len(news_tickers)} stock(s)...")
        with st.spinner("Fetching latest news (Google News + Economic Times)..."):
            news_items = fetch_stock_news(tuple(news_tickers[:20]))

        if news_items:
            st.caption(f"📅 Showing last **14 days** of news only | Source: Google News + Economic Times")
            st.markdown(f"**{len(news_items)} articles** across {len(set(n['ticker'] for n in news_items))} source(s).")
            filter_ticker = st.selectbox("Filter by stock:", ["All"] + sorted(set(n['ticker'] for n in news_items)))
            filtered = [n for n in news_items if filter_ticker == "All" or n['ticker'] == filter_ticker]
            for n in filtered:
                st.markdown(f"""<div class="news-card">
                    <a href="{n['link']}" target="_blank" style="text-decoration:none;">
                    <div class="news-title">{n['title']}</div></a>
                    <div class="news-meta">
                        📌 <b>{n['ticker']}</b> &nbsp;|&nbsp;
                        🗞️ {n.get('source','News')} &nbsp;|&nbsp;
                        🕐 {n.get('published','')}
                    </div>
                    {f'<div style="color:#8b949e;font-size:12px;margin-top:6px;">{n["summary"]}…</div>' if n.get('summary') else ''}
                </div>""", unsafe_allow_html=True)
        else:
            st.warning("⚠️ No news found in the last 2 weeks for your portfolio stocks. Try searching a specific company name in the box above (e.g. 'Reliance Industries' or 'Infosys').")
    else:
        if df.empty:
            st.info("💡 Upload your portfolio file above, or type a ticker/company name to search for news.")

# ══════════════════════════════════════════════════════════════════════
# SEARCH ANY STOCK
# ══════════════════════════════════════════════════════════════════════
elif "Search Any Stock" in menu or "🔎" in menu:
    st.markdown("<h3>🔎 Search Any Stock</h3>", unsafe_allow_html=True)
    st.caption("Type 2+ letters — suggestions appear automatically.")

    search_query = st.text_input("🔍 Type company name or ticker:", placeholder="e.g. Reliance, TCS, Apple…", key="search_box_input")
    confirmed_ticker = st.session_state.search_selected_ticker
    if not search_query and confirmed_ticker:
        st.session_state.search_selected_ticker = ""; confirmed_ticker = ""

    if search_query and len(search_query.strip()) >= 2:
        suggestions = fetch_search_suggestions(search_query.strip())
        if suggestions:
            options = [s["label"] for s in suggestions]; tickers=[s["ticker"] for s in suggestions]
            prev_label = next((s["label"] for s in suggestions if s["ticker"]==confirmed_ticker), None)
            chosen_label = st.selectbox(f"📋 {len(suggestions)} match(es):", options, index=options.index(prev_label) if prev_label else 0, key=f"sd_{search_query[:20]}")
            auto_ticker = tickers[options.index(chosen_label)]
            if auto_ticker != confirmed_ticker:
                st.session_state.search_selected_ticker = auto_ticker; confirmed_ticker = auto_ticker
        else:
            st.info("No suggestions found."); confirmed_ticker = ""

    if confirmed_ticker:
        _,clr_col = st.columns([5,1])
        if clr_col.button("✖ Clear", use_container_width=True):
            st.session_state.search_selected_ticker = ""; st.rerun()
        with st.spinner(f"Loading {confirmed_ticker}…"):
            result = search_any_stock(confirmed_ticker)
        if result is None:
            st.error(f"⚠️ Could not fetch data for {confirmed_ticker}.")
        else:
            st.markdown(f"#### {result['company_name']}  `{result['ticker']}`")
            sc1,sc2,sc3 = st.columns(3)
            sc1.markdown(f'<div class="terminal-card"><div class="metric-title">LIVE PRICE</div><div class="metric-value">{result["currency"]} {result["live_price"]:,.2f}</div></div>', unsafe_allow_html=True)
            sc2.markdown(f'<div class="terminal-card"><div class="metric-title">52W HIGH</div><div class="metric-value" style="color:#3fb950;">{result["currency"]} {result["high_52w"]:,.2f}</div></div>' if result["high_52w"] else '<div class="terminal-card"><div class="metric-title">52W HIGH</div><div class="metric-value">N/A</div></div>', unsafe_allow_html=True)
            sc3.markdown(f'<div class="terminal-card"><div class="metric-title">52W LOW</div><div class="metric-value" style="color:#f85149;">{result["currency"]} {result["low_52w"]:,.2f}</div></div>' if result["low_52w"] else '<div class="terminal-card"><div class="metric-title">52W LOW</div><div class="metric-value">N/A</div></div>', unsafe_allow_html=True)
            if not result["history"].empty:
                fig_s = go.Figure(go.Scatter(x=result["history"].index, y=result["history"]['Close'], line=dict(color='#58a6ff'), fill='tozeroy', fillcolor='rgba(88,166,255,0.08)'))
                fig_s.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=36,b=10),title=dict(text="1-Year Price Trend",font=dict(color='#e6edf3')),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_s, use_container_width=True)
    elif not search_query:
        st.info("💡 Start typing above — suggestions appear automatically.")

# ══════════════════════════════════════════════════════════════════════
# TRANSACTION LEDGER
# ══════════════════════════════════════════════════════════════════════
elif "Transaction Ledger" in menu or "💼" in menu:
    st.markdown("<h2 style='color:#e6edf3;'>💼 Transaction Ledger & P&L Analytics</h2>", unsafe_allow_html=True)
    tx_tab4, tx_tab1, tx_tab2, tx_tab3 = st.tabs(["📊 P&L Dashboard","📤 Upload Trade File","➕ Manual Entry","📜 Full Ledger"])

    with tx_tab4:
        rpt = st.session_state.get("rpt_trades", pd.DataFrame())
        if rpt.empty:
            st.markdown("<div style='text-align:center;padding:60px 20px;'><div style='font-size:64px;'>📂</div><h3 style='color:#8b949e;margin-top:16px;'>No trades loaded yet</h3><p style='color:#6e7681;'>Go to <b>📤 Upload Trade File</b>, upload your broker's export, map columns, click Confirm.</p></div>", unsafe_allow_html=True)
        else:
            tb  = rpt["buy_value"].sum();  ts_  = rpt["sell_value"].sum()
            tp  = rpt["realized_pnl"].sum()
            sdf = rpt[rpt["tax_term"]=="STCG (<1yr)"]; ldf = rpt[rpt["tax_term"]=="LTCG (>1yr)"]
            sp  = sdf["realized_pnl"].sum();  lp  = ldf["realized_pnl"].sum()
            pw  = (rpt["realized_pnl"]>0).sum(); pl = (rpt["realized_pnl"]<0).sum()
            wr  = pw/len(rpt)*100 if len(rpt)>0 else 0
            aw  = rpt[rpt["realized_pnl"]>0]["realized_pnl"].mean() if pw>0 else 0
            al  = rpt[rpt["realized_pnl"]<0]["realized_pnl"].mean() if pl>0 else 0
            bt  = rpt.loc[rpt["realized_pnl"].idxmax()] if len(rpt)>0 else None
            wt  = rpt.loc[rpt["realized_pnl"].idxmin()] if len(rpt)>0 else None
            etx = max(0,sp)*0.20 + (max(0,lp-100000)*0.125 if lp>100000 else 0)

            st.markdown("### 📈 Realized P&L Summary")
            k1,k2,k3,k4,k5,k6 = st.columns(6)
            pc = "#3fb950" if tp>=0 else "#f85149"
            k1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL REALIZED P&L</div><div class="metric-value" style="color:{pc};">₹{tp:,.0f}</div></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL BUY VALUE</div><div class="metric-value">₹{tb:,.0f}</div></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL SELL VALUE</div><div class="metric-value">₹{ts_:,.0f}</div></div>', unsafe_allow_html=True)
            k4.markdown(f'<div class="terminal-card"><div class="metric-title">WIN RATE</div><div class="metric-value" style="color:#58a6ff;">{wr:.1f}%</div><div class="metric-status-blue">{pw}W / {pl}L / {len(rpt)}T</div></div>', unsafe_allow_html=True)
            k5.markdown(f'<div class="terminal-card"><div class="metric-title">STCG P&L</div><div class="metric-value" style="color:{"#3fb950" if sp>=0 else "#f85149"};">₹{sp:,.0f}</div><div class="metric-status-blue">Tax ₹{max(0,sp)*0.20:,.0f}</div></div>', unsafe_allow_html=True)
            k6.markdown(f'<div class="terminal-card"><div class="metric-title">LTCG P&L</div><div class="metric-value" style="color:{"#3fb950" if lp>=0 else "#f85149"};">₹{lp:,.0f}</div><div class="metric-status-blue">Tax ₹{max(0,lp-100000)*0.125 if lp>100000 else 0:,.0f}</div></div>', unsafe_allow_html=True)

            st.markdown("---")
            b1,b2,b3,b4 = st.columns(4)
            b1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL EST. TAX</div><div class="metric-value" style="color:#e3b341;">₹{etx:,.0f}</div></div>', unsafe_allow_html=True)
            b2.markdown(f'<div class="terminal-card"><div class="metric-title">AVG WINNING TRADE</div><div class="metric-value" style="color:#3fb950;">₹{aw:,.0f}</div></div>', unsafe_allow_html=True)
            b3.markdown(f'<div class="terminal-card"><div class="metric-title">AVG LOSING TRADE</div><div class="metric-value" style="color:#f85149;">₹{al:,.0f}</div></div>', unsafe_allow_html=True)
            rr = abs(aw/al) if al!=0 else 0
            b4.markdown(f'<div class="terminal-card"><div class="metric-title">RISK:REWARD</div><div class="metric-value" style="color:#58a6ff;">1 : {rr:.2f}</div></div>', unsafe_allow_html=True)

            if bt is not None and wt is not None:
                bw1,bw2 = st.columns(2)
                bw1.markdown(f'<div class="alert-box-high">🏆 <b>BEST TRADE</b> — {bt["share_name"]}<br>Buy ₹{bt["buy_price"]:,.2f} → Sell ₹{bt["sell_price"]:,.2f} × {bt["quantity"]:.0f}<br><b style="font-size:18px;">P&L: ₹{bt["realized_pnl"]:,.2f}</b> | {bt["tax_term"]}</div>', unsafe_allow_html=True)
                bw2.markdown(f'<div class="alert-box-low">📉 <b>WORST TRADE</b> — {wt["share_name"]}<br>Buy ₹{wt["buy_price"]:,.2f} → Sell ₹{wt["sell_price"]:,.2f} × {wt["quantity"]:.0f}<br><b style="font-size:18px;">P&L: ₹{wt["realized_pnl"]:,.2f}</b> | {wt["tax_term"]}</div>', unsafe_allow_html=True)

            st.caption("⚠️ Tax estimate is indicative. LTCG exempt up to ₹1 lakh/year. Consult a CA.")
            st.markdown("---")
            ch1,ch2 = st.columns(2)
            with ch1:
                st.markdown("#### 📅 Monthly Realized P&L")
                rpt_m = rpt.copy(); rpt_m["month"] = rpt_m["sell_date"].dt.to_period("M").astype(str)
                monthly = rpt_m.groupby("month")["realized_pnl"].sum().reset_index()
                fig_m = go.Figure(go.Bar(x=monthly["month"],y=monthly["realized_pnl"],marker_color=["#3fb950" if v>=0 else "#f85149" for v in monthly["realized_pnl"]],text=monthly["realized_pnl"].apply(lambda v:f"₹{v:,.0f}"),textposition="auto"))
                fig_m.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d',tickangle=-45),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_m, use_container_width=True)
            with ch2:
                st.markdown("#### 📈 Cumulative P&L")
                rs = rpt.sort_values("sell_date").copy(); rs["cumulative_pnl"] = rs["realized_pnl"].cumsum()
                fig_c = go.Figure()
                fig_c.add_trace(go.Scatter(x=rs["sell_date"],y=rs["cumulative_pnl"],line=dict(color='#58a6ff',width=2),fill='tozeroy',fillcolor='rgba(88,166,255,0.08)'))
                fig_c.add_hline(y=0,line_dash="dot",line_color="#8b949e")
                fig_c.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'),showlegend=False)
                st.plotly_chart(fig_c, use_container_width=True)
            ch3,ch4 = st.columns(2)
            with ch3:
                st.markdown("#### 🏆 Top Gainers & Losers")
                by_s = rpt.groupby("share_name",as_index=False)["realized_pnl"].sum().sort_values("realized_pnl")
                tn = pd.concat([by_s.head(5),by_s.tail(5)]).drop_duplicates()
                fig_gl = go.Figure(go.Bar(x=tn["realized_pnl"],y=tn["share_name"],orientation='h',marker_color=["#3fb950" if v>=0 else "#f85149" for v in tn["realized_pnl"]],text=tn["realized_pnl"].apply(lambda v:f"₹{v:,.0f}"),textposition="auto"))
                fig_gl.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_gl, use_container_width=True)
            with ch4:
                st.markdown("#### 🥧 STCG vs LTCG")
                fig_tax = go.Figure(go.Pie(labels=["STCG (<1yr)","LTCG (>1yr)"],values=[max(0.01,len(sdf)),max(0.01,len(ldf))],hole=0.55,marker=dict(colors=["#58a6ff","#3fb950"]),textinfo="label+percent"))
                fig_tax.update_layout(paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10))
                st.plotly_chart(fig_tax, use_container_width=True)
            st.markdown("---")
            st.markdown("#### 🔍 Stock-wise P&L Filter")
            all_stk = ["All Stocks"] + sorted(rpt["share_name"].unique().tolist())
            sel_stk = st.selectbox("Select stock:", all_stk)
            rpt_f = rpt if sel_stk=="All Stocks" else rpt[rpt["share_name"]==sel_stk]
            if sel_stk!="All Stocks":
                fs1,fs2,fs3 = st.columns(3)
                spnl=rpt_f["realized_pnl"].sum()
                fs1.markdown(f'<div class="terminal-card"><div class="metric-title">{sel_stk[:20]} P&L</div><div class="metric-value" style="color:{"#3fb950" if spnl>=0 else "#f85149"};">₹{spnl:,.2f}</div></div>', unsafe_allow_html=True)
                fs2.markdown(f'<div class="terminal-card"><div class="metric-title">TRADES</div><div class="metric-value">{len(rpt_f)}</div></div>', unsafe_allow_html=True)
                fs3.markdown(f'<div class="terminal-card"><div class="metric-title">WIN RATE</div><div class="metric-value" style="color:#58a6ff;">{(rpt_f["realized_pnl"]>0).sum()/len(rpt_f)*100:.1f}%</div></div>', unsafe_allow_html=True)
            sr = rpt_f.copy()
            sr["buy_date"]  = pd.to_datetime(sr["buy_date"],  errors='coerce').dt.strftime("%d %b %Y")
            sr["sell_date"] = pd.to_datetime(sr["sell_date"], errors='coerce').dt.strftime("%d %b %Y")
            sr = sr.rename(columns={"share_name":"Company","quantity":"Qty","buy_date":"Purchase Date","buy_price":"Buy Price","buy_value":"Buy Value","sell_date":"Sell Date","sell_price":"Sell Price","sell_value":"Sell Value","realized_pnl":"P&L (₹)","holding_days":"Days Held","tax_term":"Tax Term"})
            dcols = [c for c in ["Company","Qty","Purchase Date","Buy Price","Buy Value","Sell Date","Sell Price","Sell Value","P&L (₹)","Days Held","Tax Term"] if c in sr.columns]
            st.dataframe(sr[dcols].style.format({"Buy Price":"₹{:,.2f}","Buy Value":"₹{:,.2f}","Sell Price":"₹{:,.2f}","Sell Value":"₹{:,.2f}","P&L (₹)":"₹{:,.2f}"}).map(color_pnl,subset=["P&L (₹)"]),use_container_width=True,height=380)
            st.download_button("📥 Download CSV",data=sr[dcols].to_csv(index=False).encode("utf-8"),file_name=f"trades_{sel_stk.replace(' ','_')}.csv",mime="text/csv",use_container_width=True)

    with tx_tab1:
        st.caption("Upload your broker's trade export. Map columns below — saved mapping is applied automatically.")
        rpt_file = st.file_uploader("Upload trade file", type=['csv','xlsx'], key="rpt_upload")
        if rpt_file is not None:
            try:
                rpt_df = pd.read_excel(rpt_file) if rpt_file.name.endswith('.xlsx') else pd.read_csv(rpt_file)
                rpt_cols = [c.strip() for c in rpt_df.columns]; rpt_df.columns = rpt_cols
                rpt_lower = [c.lower() for c in rpt_cols]
                saved_rpt = st.session_state.saved_mappings.get("rpt",{})
                def _rpt_idx(key,kws,fb=0):
                    if key in saved_rpt and saved_rpt[key] in rpt_cols: return rpt_cols.index(saved_rpt[key])+1
                    m = next((i for i,c in enumerate(rpt_lower) if any(kw in c for kw in kws)),-1)
                    return m+1 if m>=0 else 0
                NONE="(None / Not in file)"; opts=[NONE]+rpt_cols
                sn = " ✅ saved mapping applied" if saved_rpt else ""
                st.markdown(f"#### 🗺️ Column Mapping{sn}")
                r1,r2,r3=st.columns(3); r4,r5,r6=st.columns(3); r7,r8,r9=st.columns(3); r10,_,sc=st.columns([3,1,1])
                with r1:  m_name=st.selectbox("🏢 Company Name *",opts,index=_rpt_idx("name",["instrument","name","company","stock","scrip"]))
                with r2:  m_qty=st.selectbox("📦 Quantity *",opts,index=_rpt_idx("qty",["qty","quantity","shares","units","volume"]))
                with r3:  m_isin=st.selectbox("🔖 ISIN (optional)",opts,index=_rpt_idx("isin",["isin"]))
                with r4:  m_buy_date=st.selectbox("📅 Purchase Date *",opts,index=_rpt_idx("buy_date",["purchase date","buy date","purchasedate","purchase_date"]))
                with r5:  m_buy_price=st.selectbox("💰 Purchase Price *",opts,index=_rpt_idx("buy_price",["purchase price","buy price","purchaseprice","purchase_price"]))
                with r6:  m_buy_value=st.selectbox("💵 Purchase Value",opts,index=_rpt_idx("buy_value",["purchase value","purchase cost","purchasevalue","purchase_value","purchase_cost"]))
                with r7:  m_sell_date=st.selectbox("📅 Sell Date *",opts,index=_rpt_idx("sell_date",["sell date","selldate","sell_date"]))
                with r8:  m_sell_price=st.selectbox("💸 Sell Price *",opts,index=_rpt_idx("sell_price",["sell price","sellprice","sell_price"]))
                with r9:  m_sell_value=st.selectbox("💵 Sell Value",opts,index=_rpt_idx("sell_value",["sell value","sellvalue","sell_value"]))
                with r10: m_pnl=st.selectbox("📈 P&L column (pre-calc)",opts,index=_rpt_idx("pnl",["long term","g/l","gain","loss","pnl","profit","p&l","p / l"]))
                with sc:
                    st.markdown("<br><br>",unsafe_allow_html=True)
                    if st.button("💾 Save",use_container_width=True,key="save_rpt_map"):
                        pm=st.session_state.saved_mappings
                        pm["rpt"]={"name":m_name,"qty":m_qty,"isin":m_isin,"buy_date":m_buy_date,"buy_price":m_buy_price,"buy_value":m_buy_value,"sell_date":m_sell_date,"sell_price":m_sell_price,"sell_value":m_sell_value,"pnl":m_pnl}
                        save_mappings(pm); st.session_state.saved_mappings=pm; st.toast("✅ Mapping saved!",icon="💾"); st.rerun()
                req={"Company Name":m_name,"Purchase Date":m_buy_date,"Purchase Price":m_buy_price,"Sell Date":m_sell_date,"Sell Price":m_sell_price,"Quantity":m_qty}
                miss=[k for k,v in req.items() if v==NONE]
                if miss:
                    st.warning(f"⚠️ Map these required fields first: **{', '.join(miss)}**")
                else:
                    trades=pd.DataFrame()
                    trades["share_name"]=rpt_df[m_name].astype(str).str.strip()
                    trades["quantity"]=pd.to_numeric(rpt_df[m_qty],errors='coerce').fillna(0)
                    trades["buy_date"]=pd.to_datetime(rpt_df[m_buy_date],errors='coerce')
                    trades["buy_price"]=pd.to_numeric(rpt_df[m_buy_price],errors='coerce').fillna(0)
                    trades["sell_date"]=pd.to_datetime(rpt_df[m_sell_date],errors='coerce')
                    trades["sell_price"]=pd.to_numeric(rpt_df[m_sell_price],errors='coerce').fillna(0)
                    trades["buy_value"]=pd.to_numeric(rpt_df[m_buy_value],errors='coerce').fillna(0) if m_buy_value!=NONE else trades["quantity"]*trades["buy_price"]
                    trades["sell_value"]=pd.to_numeric(rpt_df[m_sell_value],errors='coerce').fillna(0) if m_sell_value!=NONE else trades["quantity"]*trades["sell_price"]
                    trades["isin"]=rpt_df[m_isin].astype(str).str.strip() if m_isin!=NONE else ""
                    trades["realized_pnl"]=pd.to_numeric(rpt_df[m_pnl],errors='coerce').fillna(0) if m_pnl!=NONE else trades["sell_value"]-trades["buy_value"]
                    trades["holding_days"]=(trades["sell_date"]-trades["buy_date"]).dt.days.fillna(0).astype(int)
                    trades["tax_term"]=trades["holding_days"].apply(lambda d:"LTCG (>1yr)" if d>365 else "STCG (<1yr)")
                    trades=trades.dropna(subset=["buy_date","sell_date"]); trades=trades[trades["quantity"]>0]
                    st.markdown(f"#### 📋 Preview — {len(trades)} trades")
                    prev=trades.copy()
                    prev["buy_date"]=pd.to_datetime(prev["buy_date"],errors='coerce').dt.strftime("%d %b %Y")
                    prev["sell_date"]=pd.to_datetime(prev["sell_date"],errors='coerce').dt.strftime("%d %b %Y")
                    st.dataframe(prev[["share_name","quantity","buy_date","buy_price","sell_date","sell_price","realized_pnl","holding_days","tax_term"]].rename(columns={"share_name":"Company","quantity":"Qty","buy_date":"Buy Date","buy_price":"Buy ₹","sell_date":"Sell Date","sell_price":"Sell ₹","realized_pnl":"P&L (₹)","holding_days":"Days","tax_term":"Term"}).style.format({"Buy ₹":"₹{:,.2f}","Sell ₹":"₹{:,.2f}","P&L (₹)":"₹{:,.2f}"}).map(color_pnl,subset=["P&L (₹)"]),use_container_width=True,height=260)
                    if st.button("✅ Confirm & Load to P&L Dashboard",use_container_width=True,key="confirm_rpt"):
                        st.session_state["rpt_trades"]=trades; st.success(f"✅ {len(trades)} trades loaded!"); st.rerun()
            except Exception as e:
                st.error(f"⚠️ Could not read file: {e}")
        elif "rpt_trades" in st.session_state and not st.session_state["rpt_trades"].empty:
            st.success(f"✅ {len(st.session_state['rpt_trades'])} trades already loaded. Switch to 📊 P&L Dashboard.")

    with tx_tab2:
        st.caption("Add individual BUY/SELL transactions manually for FIFO P&L tracking.")
        with st.form("add_tx_form", clear_on_submit=True):
            tc1,tc2=st.columns(2)
            with tc1:
                tx_sn=st.text_input("Company Name",placeholder="e.g. Reliance Industries")
                tx_tk=st.text_input("Yahoo Ticker (optional)",placeholder="e.g. RELIANCE.NS")
                tx_tp=st.radio("Type",["BUY","SELL"],horizontal=True)
            with tc2:
                tx_dt=st.date_input("Date",value=now_ist().date())
                tx_q=st.number_input("Quantity",min_value=0.0,step=1.0,format="%.2f")
                tx_p=st.number_input("Price per share (₹)",min_value=0.0,step=0.01,format="%.2f")
            if st.form_submit_button("💾 Add Transaction",use_container_width=True):
                if not tx_sn or tx_q<=0 or tx_p<=0:
                    st.error("⚠️ Fill Company Name, Quantity, and Price.")
                else:
                    nr=pd.DataFrame([{"date":pd.to_datetime(tx_dt),"share_name":tx_sn.strip(),"ticker":tx_tk.strip().upper(),"txn_type":tx_tp,"quantity":tx_q,"price":tx_p}])
                    st.session_state.transactions_df=append_transactions(nr)
                    st.success(f"✅ {tx_tp} {tx_q} × {tx_sn} @ ₹{tx_p:,.2f}"); st.rerun()

    with tx_tab3:
        tx_df=st.session_state.transactions_df
        if tx_df.empty:
            st.info("💡 No manual transactions yet. Use ➕ Manual Entry tab.")
        else:
            st.markdown("#### 📜 Manual Transaction Ledger")
            disp=tx_df.copy().sort_values('date',ascending=False)
            disp['date']=pd.to_datetime(disp['date'],errors='coerce').dt.strftime('%d %b %Y')
            st.dataframe(disp,use_container_width=True,height=260)
            dl_col,cl_col=st.columns([3,1])
            with dl_col: st.download_button("📥 Download CSV",data=tx_df.to_csv(index=False).encode('utf-8'),file_name="transaction_ledger.csv",mime="text/csv",use_container_width=True)
            with cl_col:
                if st.button("🗑️ Clear All",use_container_width=True):
                    st.session_state.transactions_df=pd.DataFrame(columns=TX_COLUMNS); save_transactions(st.session_state.transactions_df); st.rerun()
            st.markdown("---")
            st.markdown("#### 💰 FIFO Realized P&L")
            rd,old=compute_fifo_realized_pnl(tx_df)
            if rd.empty:
                st.info("No SELL transactions yet.")
            else:
                tr=rd['realized_pnl'].sum(); sr_=rd[rd['tax_term'].str.contains('STCG')]['realized_pnl'].sum(); lr_=rd[rd['tax_term'].str.contains('LTCG')]['realized_pnl'].sum()
                rc1,rc2,rc3=st.columns(3)
                rc1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL REALIZED P&L</div><div class="metric-value" style="color:{"#3fb950" if tr>=0 else "#f85149"};">₹{tr:,.2f}</div></div>', unsafe_allow_html=True)
                rc2.markdown(f'<div class="terminal-card"><div class="metric-title">STCG P&L</div><div class="metric-value" style="color:#58a6ff;">₹{sr_:,.2f}</div></div>', unsafe_allow_html=True)
                rc3.markdown(f'<div class="terminal-card"><div class="metric-title">LTCG P&L</div><div class="metric-value" style="color:#58a6ff;">₹{lr_:,.2f}</div></div>', unsafe_allow_html=True)
            if not old.empty:
                st.markdown("#### 📦 Open Lots")
                ol=old.copy(); ol['buy_date']=pd.to_datetime(ol['buy_date']).dt.strftime('%d %b %Y')
                st.dataframe(ol.rename(columns={'share_name':'Stock','buy_date':'Buy Date','quantity':'Qty','buy_price':'Buy ₹'}),use_container_width=True,height=200)

# ══════════════════════════════════════════════════════════════════════
# PORTFOLIO PAGES (require uploaded file)
# ══════════════════════════════════════════════════════════════════════
elif not df.empty:
    df.columns = df.columns.str.strip()
    all_columns = list(df.columns)
    saved_pm = st.session_state.saved_mappings.get("portfolio",{})

    def _col_idx(sk, kws, fp=0):
        if sk in saved_pm and saved_pm[sk] in all_columns: return all_columns.index(saved_pm[sk])
        return next((i for i,c in enumerate(all_columns) if c.lower() in kws), fp)

    pmap_notice = " ✅ (saved mapping)" if saved_pm else ""
    st.markdown(f'<div class="map-box">🗺️ <b>Portfolio Column Mapping{pmap_notice}</b><br><small style="color:#8b949e;">Select columns and click Save Mapping — remembered for next time.</small></div>', unsafe_allow_html=True)

    mc1,mc2,mc3,mc4 = st.columns([2,2,2,1])
    with mc1: ticker_col = st.selectbox("🌐 Ticker/Company:",all_columns, index=_col_idx("ticker",[],0))
    with mc2: qty_col    = st.selectbox("📦 Quantity:",all_columns,    index=_col_idx("qty",['quantity','qty','volume','shares'],0))
    with mc3: price_col  = st.selectbox("💰 Buy Price:",all_columns,   index=_col_idx("price",['buy_price','buy price','avg_price','avg price','rate','price'],min(2,len(all_columns)-1)))
    with mc4:
        st.markdown("<br>",unsafe_allow_html=True)
        if st.button("💾 Save",use_container_width=True):
            pm=st.session_state.saved_mappings; pm["portfolio"]={"ticker":ticker_col,"qty":qty_col,"price":price_col}
            save_mappings(pm); st.session_state.saved_mappings=pm; st.toast("✅ Portfolio mapping saved!",icon="💾")

    st.markdown("---")

    df = df.dropna(subset=[ticker_col])
    df[ticker_col] = df[ticker_col].astype(str).str.strip()
    df = df[(df[ticker_col]!='') & (~df[ticker_col].str.contains('Total|TOTAL|Grand',case=False,na=False))]
    df['quantity']  = pd.to_numeric(df[qty_col],  errors='coerce').fillna(0)
    df['buy_price'] = pd.to_numeric(df[price_col],errors='coerce').fillna(0)
    df['Invested']  = df['quantity'] * df['buy_price']
    df = df[df['Invested']>0].copy()

    unique_tickers = df[ticker_col].unique().tolist()
    manual_overrides_tuple = tuple(sorted(st.session_state.manual_ticker_overrides.items()))

    with st.spinner('🔎 Resolving tickers…'):
        ticker_resolution_map = resolve_tickers(tuple(unique_tickers), manual_overrides_tuple)
    df['resolved_ticker'] = df[ticker_col].map(ticker_resolution_map)

    unresolved_entries = sorted({raw for raw,res in ticker_resolution_map.items() if not res})
    resolved_unique_tickers = sorted({t for t in ticker_resolution_map.values() if t})

    with st.spinner('🗲 Fetching live prices…'):
        live_prices_map = fetch_live_prices_from_yahoo(tuple(resolved_unique_tickers))
    with st.spinner('📊 Fetching 52-week range…'):
        range_map = fetch_52week_range(tuple(resolved_unique_tickers))

    df['live_price'] = df['resolved_ticker'].map(live_prices_map).fillna(0)
    df['share_name'] = df[ticker_col]
    df['high_52w'] = df['resolved_ticker'].map(lambda t: range_map.get(t,(0,0))[0] if t else 0).fillna(0)
    df['low_52w']  = df['resolved_ticker'].map(lambda t: range_map.get(t,(0,0))[1] if t else 0).fillna(0)

    if unresolved_entries:
        st.markdown(f'<div class="risk-warning">⚠️ <b>No ticker found for {len(unresolved_entries)} compan(ies).</b> Type exact Yahoo tickers below and click Save.</div>', unsafe_allow_html=True)
        with st.expander(f"✏️ Fix {len(unresolved_entries)} unresolved compan(ies)", expanded=True):
            with st.form("fix_unresolved"):
                fix_inputs = {}
                for entry in unresolved_entries:
                    c1,c2 = st.columns([3,2]); c1.write(entry)
                    fix_inputs[entry] = c2.text_input("Yahoo ticker",key=f"fix_{entry}",placeholder="e.g. TATAMOTORS.NS",label_visibility="collapsed")
                if st.form_submit_button("💾 Save All",use_container_width=True):
                    ns=0
                    for e,tv in fix_inputs.items():
                        tv=tv.strip()
                        if tv: st.session_state.manual_ticker_overrides[e]=tv.upper(); ns+=1
                    if ns>0:
                        save_overrides(st.session_state.manual_ticker_overrides); st.cache_data.clear(); st.success(f"✅ Saved {ns} ticker(s)."); st.rerun()
                    else:
                        st.warning("Enter at least one ticker before saving.")

    df['Simulated_Live'] = df['live_price'] * (1 + market_shock/100)
    df['Current']   = df['quantity'] * df['Simulated_Live']
    df['PnL']       = df['Current'] - df['Invested']
    df['Returns_Pct'] = (df['PnL'] / df['Invested']) * 100
    df['Weight']    = (df['Invested'] / df['Invested'].sum()) * 100
    df['Action']    = df.apply(lambda r: f"🎯 TAKE PROFIT (+{target_pct}%)" if r['Returns_Pct']>=target_pct else (f"⚠️ STOP LOSS ({stop_loss_pct}%)" if r['Returns_Pct']<=stop_loss_pct else "🟢 HOLD (Safe)"), axis=1)
    df['Range_Status'] = df.apply(lambda r: "📈 AT 52W HIGH" if r['high_52w'] and r['live_price']>=r['high_52w'] else ("📉 AT 52W LOW" if r['low_52w'] and r['live_price']<=r['low_52w'] else ""), axis=1)

    total_invested = df['Invested'].sum(); total_current = df['Current'].sum()
    total_pnl = df['PnL'].sum(); weighted_return = (total_pnl/total_invested*100) if total_invested>0 else 0
    total_stocks = len(df); profit_stocks = (df['PnL']>0).sum()
    win_rate = (profit_stocks/total_stocks*100) if total_stocks>0 else 0
    high_risk_stocks = df[df['Weight']>25]

    append_history_snapshot(total_invested, total_current, total_pnl)

    # ── Alert checks (every refresh) ──────────────────────────────────
    _cfg = st.session_state.app_settings
    check_52week_alerts(df, st.session_state.alerted_keys, _cfg)
    triggered_price = check_price_alerts(live_prices_map, st.session_state.alerted_keys, _cfg)
    for ticker,label,live,threshold in triggered_price:
        st.toast(f"🔔 {ticker}: {label} @ ₹{live:,.2f}", icon="🔔")

    # ── 52W banners ────────────────────────────────────────────────────
    for _,row in df[df['Range_Status']!=""].iterrows():
        css = "alert-box-high" if "HIGH" in row['Range_Status'] else "alert-box-low"
        st.markdown(f'<div class="{css}">{row["Range_Status"]}: <b>{row["share_name"]}</b> ₹{row["live_price"]:,.2f}</div>', unsafe_allow_html=True)

    df_filtered = df.copy()
    if stock_filter == "🟢 Profit Only":   df_filtered = df[df['PnL']>0]
    elif stock_filter == "🔴 Loss Only":   df_filtered = df[df['PnL']<=0]

    # ════════════════ OVERVIEW ════════════════════════════════════════
    if "Overview" in menu or "🖥️" in menu:
        st.caption(f"🔄 Auto-refreshes every 1 second | Last refreshed: {now_ist().strftime('%H:%M:%S')} IST")

        if market_shock != 0:
            st.info(f"⚠️ Simulation Mode: {market_shock:+.0f}% market change applied.")

        for _,row in high_risk_stocks.iterrows():
            st.markdown(f'<div class="risk-warning">⚠️ <b>Concentration Risk:</b> {row["Weight"]:.1f}% of capital in <b>{row["share_name"]}</b></div>', unsafe_allow_html=True)

        # ── ★ PORTFOLIO SCORECARD ────────────────────────────────────
        bench_ret, bench_hist = fetch_benchmark_returns("1y")
        sc_data = build_scorecard(df, bench_ret)

        st.markdown(f"""
        <div style='background:linear-gradient(135deg,#161b22,#1c2128);border:1px solid #30363d;border-radius:12px;padding:18px 24px;margin-bottom:18px;'>
        <div style='display:flex;align-items:center;gap:16px;margin-bottom:14px;'>
            <div style='font-size:40px;font-weight:900;color:{sc_data["color"]};font-family:monospace;'>{sc_data["score"]}</div>
            <div>
                <div style='font-size:11px;color:#8b949e;font-weight:700;text-transform:uppercase;letter-spacing:1px;'>PORTFOLIO HEALTH SCORE / 100</div>
                <div style='font-size:18px;color:{sc_data["color"]};font-weight:700;'>{sc_data["label"]}</div>
            </div>
        </div>
        <div class="scorecard-row">
            <div class="scorecard-item"><div class="scorecard-label">Stocks Held</div><div class="scorecard-val" style="color:#58a6ff;">{sc_data["n_stocks"]}</div></div>
            <div class="scorecard-item"><div class="scorecard-label">Win Rate</div><div class="scorecard-val" style="color:{'#3fb950' if sc_data['win_rate']>=50 else '#f85149'};">{sc_data["win_rate"]:.1f}%</div></div>
            <div class="scorecard-item"><div class="scorecard-label">Max Weight</div><div class="scorecard-val" style="color:{'#f85149' if sc_data['max_weight']>25 else '#3fb950'};">{sc_data["max_weight"]:.1f}%</div></div>
            <div class="scorecard-item"><div class="scorecard-label">Overall Return</div><div class="scorecard-val" style="color:{'#3fb950' if sc_data['overall_ret']>=0 else '#f85149'};">{sc_data["overall_ret"]:+.2f}%</div></div>
            <div class="scorecard-item"><div class="scorecard-label">Sharpe Ratio</div><div class="scorecard-val" style="color:{'#3fb950' if sc_data['sharpe']>0.5 else '#e3b341'};">{sc_data["sharpe"]:.2f}</div></div>
            <div class="scorecard-item"><div class="scorecard-label">Max Drawdown</div><div class="scorecard-val" style="color:#f85149;">{sc_data["max_dd"]:+.1f}%</div></div>
            <div class="scorecard-item"><div class="scorecard-label">Volatility (std%)</div><div class="scorecard-val" style="color:#e3b341;">{sc_data["volatility"]:.1f}%</div></div>
            {'<div class="scorecard-item"><div class="scorecard-label">Alpha vs Nifty</div><div class="scorecard-val" style="color:' + ("#3fb950" if sc_data["alpha"] and sc_data["alpha"]>=0 else "#f85149") + ';">' + (f'{sc_data["alpha"]:+.2f}%' if sc_data["alpha"] is not None else "N/A") + '</div></div>' if sc_data["alpha"] is not None else ""}
        </div></div>""", unsafe_allow_html=True)

        # ── XIRR ─────────────────────────────────────────────────────
        xirr_value = None
        tx_xirr = st.session_state.get("transactions_df", pd.DataFrame())
        if not tx_xirr.empty:
            try:
                cfs = [(r['date'].to_pydatetime() if hasattr(r['date'],'to_pydatetime') else r['date'],
                        -(r['quantity']*r['price']) if str(r['txn_type']).upper()=='BUY' else (r['quantity']*r['price']))
                       for _,r in tx_xirr.iterrows()]
                cfs.append((now_ist().replace(tzinfo=None), total_current))
                xirr_value = calculate_xirr(cfs)
            except Exception:
                pass

        st.markdown("<h4 style='color:#e6edf3;margin:10px 0;'>📈 Terminal Performance Matrix</h4>", unsafe_allow_html=True)
        k1,k2,k3,k4,k5,k6 = st.columns(6)
        k1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL INVESTED</div><div class="metric-value">₹{total_invested:,.0f}</div><div class="metric-status-blue">● Net Asset Base</div></div>', unsafe_allow_html=True)
        k2.markdown(f'<div class="terminal-card"><div class="metric-title">CURRENT VALUE</div><div class="metric-value">₹{total_current:,.0f}</div><div class="metric-status-blue">Yahoo Live</div></div>', unsafe_allow_html=True)
        pc=("#3fb950" if total_pnl>=0 else "#f85149")
        k3.markdown(f'<div class="terminal-card"><div class="metric-title">UNREALIZED P&L</div><div class="metric-value" style="color:{pc};">{"+" if total_pnl>=0 else ""}₹{total_pnl:,.0f}</div><div class="metric-status-blue">{weighted_return:+.2f}%</div></div>', unsafe_allow_html=True)
        k4.markdown(f'<div class="terminal-card"><div class="metric-title">WIN RATE</div><div class="metric-value" style="color:#58a6ff;">{win_rate:.1f}%</div><div class="metric-status-blue">{profit_stocks}G / {total_stocks-profit_stocks}L</div></div>', unsafe_allow_html=True)
        if xirr_value is not None:
            xc = "#3fb950" if xirr_value>=0 else "#f85149"
            k5.markdown(f'<div class="terminal-card"><div class="metric-title">XIRR</div><div class="metric-value" style="color:{xc};">{xirr_value:.2f}%</div><div class="metric-status-blue">Annualized</div></div>', unsafe_allow_html=True)
        else:
            k5.markdown(f'<div class="terminal-card"><div class="metric-title">XIRR</div><div class="metric-value" style="color:#8b949e;font-size:13px;">Add trades in Ledger</div></div>', unsafe_allow_html=True)
        k6.markdown(f'<div class="terminal-card"><div class="metric-title">HEALTH SCORE</div><div class="metric-value" style="color:{sc_data["color"]};">{sc_data["score"]}/100</div><div class="metric-status-blue">{sc_data["label"]}</div></div>', unsafe_allow_html=True)

        if not df_filtered.empty:
            col_left,col_right = st.columns([3,2])
            with col_left:
                st.markdown("<h4>📊 Stock P&L Impact</h4>", unsafe_allow_html=True)
                df_bar=df_filtered.groupby('share_name',as_index=False).agg({'PnL':'sum'}).sort_values('PnL')
                fig_bar=go.Figure(go.Bar(x=df_bar['share_name'],y=df_bar['PnL'],marker_color=['#3fb950' if v>=0 else '#f85149' for v in df_bar['PnL']],text=df_bar['PnL'].apply(lambda x:f"₹{x:,.0f}"),textposition='auto'))
                fig_bar.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(showgrid=False,tickangle=-45),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_bar, use_container_width=True)
            with col_right:
                st.markdown("<h4>📦 Asset Allocation</h4>", unsafe_allow_html=True)
                df_pie=df_filtered.groupby('share_name',as_index=False)['Invested'].sum()
                fig_pie=go.Figure(go.Pie(labels=df_pie['share_name'],values=df_pie['Invested'],hole=.55,hoverinfo="label+percent+value",textinfo="none"))
                fig_pie.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),legend=dict(orientation="h",y=-0.15))
                st.plotly_chart(fig_pie, use_container_width=True)

            # ── ★ BENCHMARK COMPARISON ───────────────────────────────
            st.markdown("---")
            st.markdown("#### 📊 Portfolio vs Nifty 50 Benchmark")
            if bench_ret is not None and not bench_hist.empty:
                bc1,bc2,bc3 = st.columns(3)
                alpha_val = sc_data.get("alpha")
                bc1.markdown(f'<div class="terminal-card"><div class="metric-title">YOUR PORTFOLIO RETURN</div><div class="metric-value" style="color:{"#3fb950" if weighted_return>=0 else "#f85149"};">{weighted_return:+.2f}%</div></div>', unsafe_allow_html=True)
                bc2.markdown(f'<div class="terminal-card"><div class="metric-title">NIFTY 50 RETURN (1Y)</div><div class="metric-value" style="color:{"#3fb950" if bench_ret>=0 else "#f85149"};">{bench_ret:+.2f}%</div></div>', unsafe_allow_html=True)
                alpha_color = "#3fb950" if alpha_val and alpha_val>=0 else "#f85149"
                alpha_txt = f"{alpha_val:+.2f}%" if alpha_val is not None else "N/A"
                bc3.markdown(f'<div class="terminal-card"><div class="metric-title">ALPHA (Your Return − Nifty)</div><div class="metric-value" style="color:{alpha_color};">{alpha_txt}</div></div>', unsafe_allow_html=True)

                # Normalised comparison chart (base 100)
                nifty_series = bench_hist['Close'] / bench_hist['Close'].iloc[0] * 100
                fig_bm = go.Figure()
                fig_bm.add_trace(go.Scatter(x=bench_hist.index, y=nifty_series, name="NIFTY 50", line=dict(color="#e3b341", width=2)))
                # Portfolio normalised line from history
                hist_data_bm = load_history()
                if len(hist_data_bm) >= 2:
                    port_norm = hist_data_bm['total_current'] / hist_data_bm['total_current'].iloc[0] * 100
                    fig_bm.add_trace(go.Scatter(x=hist_data_bm['date'], y=port_norm, name="Your Portfolio", line=dict(color="#58a6ff", width=2)))
                fig_bm.add_hline(y=100, line_dash="dot", line_color="#8b949e", annotation_text="Start (base 100)")
                fig_bm.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=20,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d',title="Normalised (base 100)"),legend=dict(orientation="h",y=-0.2))
                st.plotly_chart(fig_bm, use_container_width=True)
                st.caption("Portfolio trend requires multiple days of data. Nifty comparison shown immediately.")
            else:
                st.info("Benchmark data temporarily unavailable.")

            # ── 52W Position Meter ────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 📏 52-Week Price Position Meter")
            df_52=df_filtered[df_filtered['high_52w']>0].copy()
            df_52=df_52.groupby('share_name').agg({'live_price':'last','high_52w':'last','low_52w':'last','PnL':'sum'}).reset_index()
            df_52=df_52[df_52['high_52w']>df_52['low_52w']].copy()
            df_52['position_pct']=((df_52['live_price']-df_52['low_52w'])/(df_52['high_52w']-df_52['low_52w'])*100).clip(0,100)
            for _,r52 in df_52.sort_values('position_pct').head(20).iterrows():
                pos=r52['position_pct']; bc="#f85149" if pos<30 else ("#e3b341" if pos<60 else "#3fb950")
                ns=r52['share_name'][:28]+"…" if len(r52['share_name'])>30 else r52['share_name']
                st.markdown(f"""<div style='margin-bottom:6px;'>
                  <div style='display:flex;justify-content:space-between;font-size:12px;color:#8b949e;margin-bottom:2px;'>
                    <span><b style='color:#e6edf3;'>{ns}</b> ₹{r52['live_price']:,.2f}</span>
                    <span>52W: ₹{r52['low_52w']:,.0f}—₹{r52['high_52w']:,.0f} <b style='color:{"#3fb950" if r52["PnL"]>=0 else "#f85149"};'>₹{r52["PnL"]:+,.0f}</b></span>
                  </div>
                  <div style='background:#21262d;border-radius:4px;height:10px;position:relative;'>
                    <div style='width:{pos:.1f}%;background:{bc};border-radius:4px;height:10px;'></div>
                    <div style='position:absolute;left:{pos:.1f}%;top:-2px;width:3px;height:14px;background:#fff;border-radius:2px;'></div>
                  </div></div>""", unsafe_allow_html=True)

            # ── Sector + History ──────────────────────────────────────
            st.markdown("---")
            col_sec,col_hist = st.columns([2,3])
            with col_sec:
                st.markdown("<h4>🏭 Sector Allocation</h4>", unsafe_allow_html=True)
                with st.spinner("Fetching sector…"):
                    sm = fetch_sector_info(tuple(resolved_unique_tickers))
                df_sec=df_filtered.copy(); df_sec['Sector']=df_sec['resolved_ticker'].map(sm).fillna('Unknown')
                sg=df_sec.groupby('Sector',as_index=False)['Invested'].sum().sort_values('Invested',ascending=False)
                fig_sec=go.Figure(go.Pie(labels=sg['Sector'],values=sg['Invested'],hole=.5,hoverinfo="label+percent+value",textinfo="percent"))
                fig_sec.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),legend=dict(orientation="h",y=-0.2))
                st.plotly_chart(fig_sec, use_container_width=True)
            with col_hist:
                st.markdown("<h4>📈 Portfolio Value Trend</h4>", unsafe_allow_html=True)
                hd=load_history()
                if len(hd)<2:
                    st.info("📊 Trend builds up day by day. Check back tomorrow!")
                else:
                    fig_h=go.Figure()
                    fig_h.add_trace(go.Scatter(x=hd['date'],y=hd['total_current'],name='Current Value',line=dict(color='#58a6ff'),fill='tozeroy',fillcolor='rgba(88,166,255,0.06)'))
                    fig_h.add_trace(go.Scatter(x=hd['date'],y=hd['total_invested'],name='Invested',line=dict(color='#8b949e',dash='dot')))
                    fig_h.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d',title='₹'),legend=dict(orientation="h",y=-0.2))
                    st.plotly_chart(fig_h, use_container_width=True)

            # ── Live Positions Table ──────────────────────────────────
            st.markdown("---"); st.markdown("<h4>📋 Live Positions</h4>", unsafe_allow_html=True)
            df_disp=df_filtered.copy()
            df_disp['From 52W Low']  = ((df_disp['Simulated_Live']-df_disp['low_52w'])/df_disp['low_52w'].replace(0,1)*100)
            df_disp['From 52W High'] = ((df_disp['Simulated_Live']-df_disp['high_52w'])/df_disp['high_52w'].replace(0,1)*100)
            display_df=df_disp[['share_name','resolved_ticker','quantity','buy_price','Simulated_Live','high_52w','low_52w','From 52W Low','From 52W High','Invested','Current','PnL','Returns_Pct','Action']].copy()
            display_df.columns=['Stock','Yahoo Ticker','Qty','Buy ₹','Live ₹','52W High','52W Low','↑ from Low%','↓ from High%','Invested','Current','P&L (₹)','Return%','Signal']
            st.dataframe(display_df.style.format({'Buy ₹':'₹{:,.2f}','Live ₹':'₹{:,.2f}','52W High':'₹{:,.2f}','52W Low':'₹{:,.2f}','↑ from Low%':'{:+.1f}%','↓ from High%':'{:+.1f}%','Invested':'₹{:,.0f}','Current':'₹{:,.0f}','P&L (₹)':'₹{:,.2f}','Return%':'{:+.2f}%'}).map(color_pnl,subset=['P&L (₹)','Return%']),use_container_width=True,height=380)

            # ── Top 5 + Drawdown ─────────────────────────────────────
            st.markdown("---"); t5c1,t5c2=st.columns(2)
            with t5c1:
                st.markdown("#### 🏆 Top 5 by Weight")
                top5=df_filtered.groupby('share_name',as_index=False).agg({'Invested':'sum','Current':'sum','PnL':'sum','Weight':'sum'}).nlargest(5,'Weight')
                top5['Return%']=(top5['PnL']/top5['Invested']*100)
                st.dataframe(top5[['share_name','Weight','Invested','Current','PnL','Return%']].rename(columns={'share_name':'Stock','Weight':'Weight%','Invested':'Invested ₹','Current':'Current ₹','PnL':'P&L ₹'}).style.format({'Weight%':'{:.1f}%','Invested ₹':'₹{:,.0f}','Current ₹':'₹{:,.0f}','P&L ₹':'₹{:,.0f}','Return%':'{:+.1f}%'}).map(color_pnl,subset=['P&L ₹','Return%']),use_container_width=True,height=220)
            with t5c2:
                st.markdown("#### 📉 Drawdown from Buy Price")
                df_dd=df_filtered.copy(); df_dd['Drawdown%']=((df_dd['Simulated_Live']-df_dd['buy_price'])/df_dd['buy_price'].replace(0,1)*100)
                ddg=df_dd.groupby('share_name',as_index=False).agg({'Drawdown%':'mean'}).sort_values('Drawdown%').head(10)
                fig_dd=go.Figure(go.Bar(x=ddg['Drawdown%'],y=ddg['share_name'],orientation='h',marker_color=['#f85149' if v<0 else '#3fb950' for v in ddg['Drawdown%']],text=ddg['Drawdown%'].apply(lambda v:f"{v:+.1f}%"),textposition='auto'))
                fig_dd.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(gridcolor='#21262d',title='% Change'),yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_dd, use_container_width=True)

            # ── Tools ─────────────────────────────────────────────────
            st.markdown("---"); st.markdown("### 🛠️ Advanced Tools")
            tc1,tc2=st.columns(2)
            with tc1:
                st.markdown("<h4>💸 Tax Estimator</h4>", unsafe_allow_html=True)
                hold_dur=st.radio("Holding duration:",["STCG (<1yr)","LTCG (>1yr)"],horizontal=True)
                if total_pnl>0:
                    if "STCG" in hold_dur: st.warning(f"STCG @20%: ₹{total_pnl*0.20:,.2f}")
                    else: st.success(f"LTCG @12.5% (after ₹1L exemption): ₹{max(0,total_pnl-100000)*0.125:,.2f}")
                else: st.info("Portfolio in loss — no tax.")
            with tc2:
                st.markdown("<h4>📥 Export</h4>", unsafe_allow_html=True)
                st.download_button("📥 Download Portfolio CSV", data=display_df.to_csv(index=False).encode('utf-8'), file_name="AlphaPortfolio_Report.csv", mime="text/csv", use_container_width=True)
        else:
            st.warning("No data for selected filter.")

    # ════════════════ ADVANCED ANALYSIS ══════════════════════════════
    elif "Advanced Analysis" in menu or "📈" in menu:
        st.markdown("<h3>📊 Advanced Analysis & Performance Matrix</h3>", unsafe_allow_html=True)

        tx_df_adv = st.session_state.get("transactions_df", pd.DataFrame())
        if not tx_df_adv.empty:
            rd_adv,_ = compute_fifo_realized_pnl(tx_df_adv)
            total_realized_adv = rd_adv['realized_pnl'].sum() if not rd_adv.empty else 0
        else:
            total_realized_adv = 0
        total_unrealized_adv = df['PnL'].sum()
        combined_pnl = total_realized_adv + total_unrealized_adv

        st.markdown("<h4>💵 Realized vs Unrealized P&L</h4>", unsafe_allow_html=True)
        ru1,ru2,ru3=st.columns(3)
        ru1.markdown(f'<div class="terminal-card"><div class="metric-title">REALIZED P&L</div><div class="metric-value" style="color:{"#3fb950" if total_realized_adv>=0 else "#f85149"};">₹{total_realized_adv:,.2f}</div><div class="metric-status-blue">From Ledger</div></div>', unsafe_allow_html=True)
        ru2.markdown(f'<div class="terminal-card"><div class="metric-title">UNREALIZED P&L</div><div class="metric-value" style="color:{"#3fb950" if total_unrealized_adv>=0 else "#f85149"};">₹{total_unrealized_adv:,.2f}</div><div class="metric-status-blue">From Live Portfolio</div></div>', unsafe_allow_html=True)
        ru3.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL P&L</div><div class="metric-value" style="color:{"#3fb950" if combined_pnl>=0 else "#f85149"};">₹{combined_pnl:,.2f}</div><div class="metric-status-blue">Combined</div></div>', unsafe_allow_html=True)
        st.markdown("---")

        best_s=df.loc[df['Returns_Pct'].idxmax()]; worst_s=df.loc[df['Returns_Pct'].idxmin()]; mw_s=df.loc[df['Weight'].idxmax()]
        ac1,ac2,ac3=st.columns(3)
        ac1.markdown(f'<div class="terminal-card"><div class="metric-title">🔥 TOP GAINER</div><div class="metric-value" style="color:#3fb950;">{best_s["share_name"]}</div><div class="metric-status-green">{best_s["Returns_Pct"]:+.2f}%</div></div>', unsafe_allow_html=True)
        ac2.markdown(f'<div class="terminal-card"><div class="metric-title">⚠️ UNDERPERFORMER</div><div class="metric-value" style="color:#f85149;">{worst_s["share_name"]}</div><div class="metric-status-red">{worst_s["Returns_Pct"]:+.2f}%</div></div>', unsafe_allow_html=True)
        ac3.markdown(f'<div class="terminal-card"><div class="metric-title">🏢 CONCENTRATION</div><div class="metric-value" style="color:#58a6ff;">{mw_s["share_name"]}</div><div class="metric-status-blue">{mw_s["Weight"]:.2f}%</div></div>', unsafe_allow_html=True)

        ca1,ca2=st.columns(2)
        with ca1:
            st.markdown("<h4>🗺️ Portfolio Heatmap</h4>", unsafe_allow_html=True)
            df_tree=df.groupby('share_name',as_index=False).agg({'Invested':'sum','PnL':'sum'})
            df_tree['Returns_Pct']=(df_tree['PnL']/df_tree['Invested'].replace(0,1)*100)
            fig_tree=px.treemap(df_tree,path=['share_name'],values='Invested',color='Returns_Pct',color_continuous_scale='RdYlGn',color_continuous_midpoint=0,template="plotly_dark")
            fig_tree.update_layout(margin=dict(l=10,r=10,t=10,b=10),paper_bgcolor='#0d1117')
            st.plotly_chart(fig_tree, use_container_width=True)
        with ca2:
            st.markdown("<h4>🔵 Risk vs Return</h4>", unsafe_allow_html=True)
            fig_sc=px.scatter(df,x='Invested',y='Returns_Pct',size='quantity',color='PnL',hover_name='share_name',color_continuous_scale='RdYlGn',template="plotly_dark",size_max=40)
            fig_sc.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=10,b=10),xaxis=dict(title="Investment (₹)",gridcolor='#21262d'),yaxis=dict(title="Returns (%)",gridcolor='#21262d'))
            st.plotly_chart(fig_sc, use_container_width=True)

    # ════════════════ SINGLE STOCK DEEP-DIVE ═════════════════════════
    elif "Single Stock" in menu or "🔍" in menu:
        st.markdown("<h3>🔍 Single Stock Deep-Dive</h3>", unsafe_allow_html=True)
        sel_s=st.selectbox("Select stock:",sorted(df['share_name'].unique()))
        sr=df[df['share_name']==sel_s]; sd=sr.iloc[0]
        tq=sr['quantity'].sum(); ti=sr['Invested'].sum(); ab=ti/tq if tq>0 else 0
        tc_=sr['Current'].sum(); tp_s=sr['PnL'].sum(); rp_=(tp_s/ti*100) if ti>0 else 0

        sc1,sc2,sc3,sc4,sc5,sc6=st.columns(6)
        sc1.markdown(f'<div class="terminal-card"><div class="metric-title">AVG BUY PRICE</div><div class="metric-value">₹{ab:,.2f}</div></div>', unsafe_allow_html=True)
        sc2.markdown(f'<div class="terminal-card"><div class="metric-title">LIVE PRICE</div><div class="metric-value">₹{sd["Simulated_Live"]:,.2f}</div></div>', unsafe_allow_html=True)
        sc3.markdown(f'<div class="terminal-card"><div class="metric-title">NET P&L</div><div class="metric-value" style="color:{"#3fb950" if tp_s>=0 else "#f85149"};">₹{tp_s:,.0f}</div></div>', unsafe_allow_html=True)
        sc4.markdown(f'<div class="terminal-card"><div class="metric-title">RETURN</div><div class="metric-value" style="color:{"#3fb950" if rp_>=0 else "#f85149"};">{rp_:+.2f}%</div></div>', unsafe_allow_html=True)
        sc5.markdown(f'<div class="terminal-card"><div class="metric-title">52W HIGH</div><div class="metric-value" style="color:#3fb950;">₹{sd["high_52w"]:,.2f}</div></div>', unsafe_allow_html=True)
        sc6.markdown(f'<div class="terminal-card"><div class="metric-title">52W LOW</div><div class="metric-value" style="color:#f85149;">₹{sd["low_52w"]:,.2f}</div></div>', unsafe_allow_html=True)

        rtk=sd.get('resolved_ticker','')
        if rtk:
            try: h1y_=yf.Ticker(rtk).history(period="1y")
            except: h1y_=pd.DataFrame()
            if not h1y_.empty:
                fig_ss=go.Figure()
                fig_ss.add_trace(go.Scatter(x=h1y_.index,y=h1y_['Close'],name='Price',line=dict(color='#58a6ff',width=2),fill='tozeroy',fillcolor='rgba(88,166,255,0.06)'))
                fig_ss.add_hline(y=ab,line_dash="dash",line_color="#e3b341",annotation_text=f"Avg Buy ₹{ab:,.2f}",annotation_position="top left",annotation=dict(font=dict(color="#e3b341")))
                if sd['high_52w']>0:
                    fig_ss.add_hline(y=sd['high_52w'],line_dash="dot",line_color="#3fb950",annotation_text=f"52W High ₹{sd['high_52w']:,.2f}",annotation_position="top right",annotation=dict(font=dict(color="#3fb950")))
                    fig_ss.add_hline(y=sd['low_52w'],line_dash="dot",line_color="#f85149",annotation_text=f"52W Low ₹{sd['low_52w']:,.2f}",annotation_position="bottom right",annotation=dict(font=dict(color="#f85149")))
                fig_ss.update_layout(plot_bgcolor='#161b22',paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=10,r=10,t=40,b=10),title=dict(text=f"{sel_s} — 1-Year Chart",font=dict(color='#e6edf3',size=14)),xaxis=dict(gridcolor='#21262d'),yaxis=dict(gridcolor='#21262d',title='₹'),showlegend=False)
                st.plotly_chart(fig_ss, use_container_width=True)

        fig_g=go.Figure(go.Indicator(mode="gauge+number+delta",value=rp_,delta={'reference':0,'valueformat':'.2f','suffix':'%'},domain={'x':[0,1],'y':[0,1]},title={'text':f"Return — {sel_s}",'font':{'color':'#e6edf3'}},number={'suffix':'%','font':{'color':'#58a6ff'}},gauge={'axis':{'range':[-50,100],'tickcolor':'#8b949e'},'bar':{'color':'#58a6ff'},'steps':[{'range':[-50,0],'color':'rgba(248,81,73,0.15)'},{'range':[0,100],'color':'rgba(63,185,80,0.12)'}],'threshold':{'line':{'color':'#e3b341','width':3},'thickness':0.75,'value':target_pct}}))
        fig_g.update_layout(paper_bgcolor='#0d1117',font=dict(color='#8b949e'),margin=dict(l=20,r=20,t=50,b=20))
        st.plotly_chart(fig_g, use_container_width=True)

else:
    st.info("💡 Terminal ready! Upload your portfolio file, or use '🔎 Search Any Stock' — both work independently.")
