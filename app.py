import streamlit as st
import pandas as pd
import re
import os
import json
import smtplib
import ssl
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta
import plotly.graph_objects as go
import plotly.express as px
import yfinance as yf
from streamlit_autorefresh import st_autorefresh

# Indian Standard Time (UTC+5:30) -- used for all "last refreshed" / alert timestamps
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

# Where manual ticker overrides are stored permanently (survives app restarts)
OVERRIDES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticker_overrides.json")

def load_overrides():
    """Load saved manual ticker overrides from disk. Returns {} if file doesn't exist yet."""
    try:
        if os.path.exists(OVERRIDES_FILE):
            with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_overrides(overrides: dict):
    """Persist manual ticker overrides to disk so they survive app restarts/redeploys."""
    try:
        with open(OVERRIDES_FILE, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

# Column mapping settings — saved so user doesn't have to re-select every time
MAPPING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "column_mappings.json")

def load_mappings() -> dict:
    """Load saved column mapping preferences. Returns {} if none saved yet."""
    try:
        if os.path.exists(MAPPING_FILE):
            with open(MAPPING_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_mappings(mappings: dict):
    """Persist column mapping preferences to disk."""
    try:
        with open(MAPPING_FILE, "w", encoding="utf-8") as f:
            json.dump(mappings, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

# 1. PAGE CONFIG + PREMIUM DARK THEME
st.set_page_config(page_title="AlphaPortfolio Terminal Pro+", layout="wide", initial_sidebar_state="expanded")

# Premium UI styling — improved readability
st.markdown("""
    <style>
    /* ── Base ── */
    .stApp { background-color: #0d1117; color: #cdd9e5; }

    /* ── Sidebar ── */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #161b22 0%, #0d1117 100%);
        border-right: 1px solid #30363d;
    }
    [data-testid="stSidebar"] * { color: #cdd9e5 !important; }
    [data-testid="stSidebar"] .stRadio label { color: #cdd9e5 !important; }

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {
        background-color: #161b22;
        border-radius: 8px 8px 0 0;
        padding: 4px 6px 0 6px;
        gap: 4px;
        border-bottom: 2px solid #30363d;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #21262d;
        color: #8b949e !important;
        border-radius: 6px 6px 0 0;
        padding: 8px 16px;
        font-weight: 600;
        font-size: 13px;
        border: 1px solid #30363d;
        border-bottom: none;
        transition: all 0.2s;
    }
    .stTabs [aria-selected="true"] {
        background-color: #1f6feb !important;
        color: #ffffff !important;
        border-color: #1f6feb !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background-color: #30363d !important;
        color: #e6edf3 !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-top: none;
        border-radius: 0 0 8px 8px;
        padding: 18px;
    }

    /* ── KPI Cards ── */
    .terminal-card {
        background: linear-gradient(135deg, #161b22 0%, #1c2128 100%);
        padding: 18px 20px;
        border-radius: 10px;
        border: 1px solid #30363d;
        box-shadow: 0 2px 12px rgba(0,0,0,0.4);
        margin-bottom: 14px;
        transition: border-color 0.2s;
    }
    .terminal-card:hover { border-color: #1f6feb; }
    .metric-title {
        font-size: 11px; color: #8b949e; font-weight: 700;
        text-transform: uppercase; letter-spacing: 1.2px;
    }
    .metric-value {
        font-size: 22px; color: #e6edf3; font-weight: 700;
        margin-top: 6px; font-family: 'Courier New', monospace;
    }
    .metric-status-green { color: #3fb950; font-size: 12px; font-weight: 600; margin-top: 4px; }
    .metric-status-red   { color: #f85149; font-size: 12px; font-weight: 600; margin-top: 4px; }
    .metric-status-blue  { color: #58a6ff; font-size: 12px; font-weight: 600; margin-top: 4px; }

    /* ── Alerts / Banners ── */
    .risk-warning {
        background-color: rgba(248, 81, 73, 0.12);
        border: 1px solid #f85149;
        padding: 12px 16px; border-radius: 8px;
        color: #ffa198; margin-bottom: 14px; font-size: 13px; line-height: 1.6;
    }
    .alert-box-high {
        background-color: rgba(63, 185, 80, 0.12);
        border: 1px solid #3fb950;
        padding: 10px 14px; border-radius: 8px;
        color: #56d364; margin-bottom: 10px; font-size: 13px;
    }
    .alert-box-low {
        background-color: rgba(248, 81, 73, 0.12);
        border: 1px solid #f85149;
        padding: 10px 14px; border-radius: 8px;
        color: #ffa198; margin-bottom: 10px; font-size: 13px;
    }
    .map-box {
        background-color: #1c2128;
        padding: 14px 18px; border-radius: 8px;
        border: 1px dashed #58a6ff; margin-bottom: 18px; color: #cdd9e5;
    }

    /* ── Inputs & Selectboxes ── */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div {
        background-color: #21262d !important;
        color: #e6edf3 !important;
        border: 1px solid #30363d !important;
        border-radius: 6px !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #58a6ff !important;
        box-shadow: 0 0 0 3px rgba(88,166,255,0.15) !important;
    }

    /* ── Dataframe / Table ── */
    .stDataFrame { border: 1px solid #30363d !important; border-radius: 8px; }

    /* ── Buttons ── */
    .stButton > button {
        background-color: #21262d; color: #cdd9e5;
        border: 1px solid #30363d; border-radius: 6px;
        font-weight: 600; transition: all 0.2s;
    }
    .stButton > button:hover {
        background-color: #1f6feb; color: #ffffff; border-color: #1f6feb;
    }

    /* ── Autocomplete dropdown ── */
    .autocomplete-item {
        padding: 10px 14px; border-radius: 6px;
        background: #21262d; border: 1px solid #30363d;
        cursor: pointer; margin-bottom: 6px; color: #e6edf3;
        transition: background 0.15s;
    }
    .autocomplete-item:hover { background: #1f6feb; color: #fff; }
    .autocomplete-label { font-weight: 600; font-size: 14px; }
    .autocomplete-sub   { font-size: 11px; color: #8b949e; margin-top: 2px; }

    /* ── Scrollbar ── */
    ::-webkit-scrollbar { width: 6px; height: 6px; }
    ::-webkit-scrollbar-track { background: #0d1117; }
    ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #58a6ff; }

    /* ── Section headings ── */
    h1, h2, h3, h4 { color: #e6edf3 !important; }
    </style>
    """, unsafe_allow_html=True)

# ===================================================================
# AUTO-REFRESH: refresh live data every 60 seconds
# ===================================================================
st_autorefresh(interval=1000, key="live_price_autorefresh")

# ===================================================================
# AUTO-TICKER RESOLVER: Company Name -> correct Yahoo Ticker
# ===================================================================
# If the user already entered a valid ticker (e.g. RELIANCE.NS, TCS.BO, AAPL),
# it is detected and used as-is. Otherwise the company name is searched
# and the matching Yahoo ticker is resolved automatically.

_TICKER_PATTERN = re.compile(r'^[A-Z0-9][A-Z0-9.\-&]*$')

def _looks_like_ticker(value: str) -> bool:
    """Detect whether an entry already looks like a Yahoo ticker (e.g. RELIANCE.NS, AAPL, TCS.BO).
    Important: without an exchange suffix, a value is only treated as a ticker if it has
    no lowercase letters at all -- this avoids misclassifying company names like 'Reliance'."""
    v = value.strip()
    if not v:
        return False
    vu = v.upper()
    if vu.endswith('.NS') or vu.endswith('.BO') or vu.endswith('.BSE'):
        return True
    if ' ' in v:
        return False
    if any(c.islower() for c in v):
        return False
    if len(vu) <= 12 and _TICKER_PATTERN.match(vu):
        return True
    return False


def _search_yahoo_symbol(query: str):
    """Search Yahoo Finance for the correct ticker symbol matching a company name.
    Prefers NSE (.NS) results, then BSE (.BO), then any other matching result."""
    quotes = []
    try:
        import requests
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params={"q": query, "quotesCount": 8, "newsCount": 0}, headers=headers, timeout=6)
        if resp.status_code == 200:
            quotes = resp.json().get("quotes", [])
    except Exception:
        quotes = []

    if not quotes:
        try:
            s = yf.Search(query, max_results=8)
            quotes = s.quotes or []
        except Exception:
            quotes = []

    if not quotes:
        return None

    equity_quotes = [q for q in quotes if q.get("quoteType") in ("EQUITY", "ETF", None)] or quotes

    for q in equity_quotes:
        sym = q.get("symbol", "")
        if sym.endswith(".NS"):
            return sym
    for q in equity_quotes:
        sym = q.get("symbol", "")
        if sym.endswith(".BO"):
            return sym
    return equity_quotes[0].get("symbol")


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def resolve_tickers(raw_names_tuple, manual_overrides_tuple):
    """Convert a list of company names/tickers into {original_entry: resolved_ticker}.
    manual_overrides_tuple is a tuple of (raw_entry, manual_ticker) pairs supplied by the
    user for entries that auto-search could not resolve -- these always take priority.
    Results are cached for 12 hours so the same company isn't searched repeatedly."""
    manual_overrides = dict(manual_overrides_tuple)
    resolved = {}
    for raw in raw_names_tuple:
        raw_clean = str(raw).strip()
        if raw in manual_overrides and manual_overrides[raw]:
            resolved[raw] = manual_overrides[raw].strip().upper()
            continue
        if not raw_clean:
            resolved[raw] = None
            continue
        if _looks_like_ticker(raw_clean):
            resolved[raw] = raw_clean.upper()
        else:
            found = _search_yahoo_symbol(raw_clean)
            resolved[raw] = found
    return resolved


# Caching function for fast live price fetch from Yahoo Finance
@st.cache_data(ttl=60, show_spinner=False)
def fetch_live_prices_from_yahoo(tickers_list):
    prices_dict = {}
    for ticker in tickers_list:
        if not ticker:
            continue
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty:
                prices_dict[ticker] = hist['Close'].iloc[-1]
            else:
                prices_dict[ticker] = 0
        except Exception:
            prices_dict[ticker] = 0
    return prices_dict


@st.cache_data(ttl=60, show_spinner=False)
def fetch_day_change(tickers_list):
    """Returns {ticker: (day_change_pct, prev_close, volume)} for each ticker."""
    change_dict = {}
    for ticker in tickers_list:
        if not ticker:
            continue
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if len(hist) >= 2:
                prev  = hist['Close'].iloc[-2]
                curr  = hist['Close'].iloc[-1]
                vol   = hist['Volume'].iloc[-1]
                chg   = ((curr - prev) / prev * 100) if prev > 0 else 0
                change_dict[ticker] = (round(chg, 2), round(prev, 2), int(vol))
            else:
                change_dict[ticker] = (0.0, 0.0, 0)
        except Exception:
            change_dict[ticker] = (0.0, 0.0, 0)
    return change_dict


@st.cache_data(ttl=120, show_spinner=False)
def fetch_market_indices():
    """Fetch Nifty 50, Sensex, and Bank Nifty live values for the market overview bar."""
    indices = {
        "NIFTY 50": "^NSEI",
        "SENSEX":   "^BSESN",
        "BANK NIFTY": "^NSEBANK",
        "NIFTY IT": "^CNXIT",
    }
    result = {}
    for name, sym in indices.items():
        try:
            hist = yf.Ticker(sym).history(period="2d")
            if len(hist) >= 2:
                curr = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                chg  = (curr - prev) / prev * 100
                result[name] = (round(curr, 2), round(chg, 2))
            elif len(hist) == 1:
                result[name] = (round(hist['Close'].iloc[-1], 2), 0.0)
        except Exception:
            pass
    return result


# Caching function for 52-week high/low (fetched straight from Yahoo Finance's 1-year history)
@st.cache_data(ttl=60 * 30, show_spinner=False)
def fetch_52week_range(tickers_list):
    """Returns {ticker: (52w_high, 52w_low)} using 1 year of daily history from Yahoo Finance."""
    range_dict = {}
    for ticker in tickers_list:
        if not ticker:
            continue
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            if not hist.empty:
                range_dict[ticker] = (hist['High'].max(), hist['Low'].min())
            else:
                range_dict[ticker] = (0, 0)
        except Exception:
            range_dict[ticker] = (0, 0)
    return range_dict


@st.cache_data(ttl=60, show_spinner=False)
def search_any_stock(query: str):
    """Used by the 'Search Any Stock' tab -- resolves a free-text query to a ticker,
    then fetches live price + 52-week range + basic info for it."""
    if not query or not query.strip():
        return None
    ticker = query.strip().upper() if _looks_like_ticker(query.strip()) else _search_yahoo_symbol(query.strip())
    if not ticker:
        return None
    try:
        stock = yf.Ticker(ticker)
        hist_1d = stock.history(period="1d")
        hist_1y = stock.history(period="1y")
        if hist_1d.empty:
            return None
        live_price = hist_1d['Close'].iloc[-1]
        high_52w = hist_1y['High'].max() if not hist_1y.empty else None
        low_52w = hist_1y['Low'].min() if not hist_1y.empty else None
        try:
            company_name = stock.info.get('longName') or stock.info.get('shortName') or ticker
            currency = stock.info.get('currency', '')
        except Exception:
            company_name = ticker
            currency = ''
        return {
            "ticker": ticker,
            "company_name": company_name,
            "currency": currency,
            "live_price": live_price,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "history": hist_1y,
        }
    except Exception:
        return None


# ===================================================================
# EMAIL ALERTS: notify the user when a holding hits its 52-week high/low
# ===================================================================
def send_email_alert(sender_email, app_password, recipient_email, subject, body):
    """Sends an email via Gmail SMTP using an App Password. Returns (success, message)."""
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = recipient_email

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True, "Email sent successfully."
    except Exception as e:
        return False, f"Email failed: {e}"


def check_and_send_52week_alerts(df_with_ranges, sender_email, app_password, recipient_email, already_alerted_set):
    """Checks each holding against its 52-week high/low and emails an alert the first time
    it crosses that level in this session (tracked via already_alerted_set to avoid spam)."""
    sent_any = False
    messages = []
    for _, row in df_with_ranges.iterrows():
        ticker = row.get('resolved_ticker')
        live = row.get('live_price', 0)
        high_52w = row.get('high_52w', 0)
        low_52w = row.get('low_52w', 0)
        name = row.get('share_name', ticker)

        if not ticker or live == 0:
            continue

        alert_key_high = f"{ticker}_HIGH"
        alert_key_low = f"{ticker}_LOW"

        if high_52w and live >= high_52w and alert_key_high not in already_alerted_set:
            subject = f"📈 52-Week HIGH Alert: {name} ({ticker})"
            body = (f"{name} ({ticker}) has touched its 52-week HIGH.\n\n"
                    f"Current Price: {live:.2f}\n"
                    f"52-Week High: {high_52w:.2f}\n\n"
                    f"Time (IST): {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
            ok, msg = send_email_alert(sender_email, app_password, recipient_email, subject, body)
            if ok:
                already_alerted_set.add(alert_key_high)
                sent_any = True
            messages.append((name, "52W HIGH", ok, msg))

        if low_52w and live <= low_52w and alert_key_low not in already_alerted_set:
            subject = f"📉 52-Week LOW Alert: {name} ({ticker})"
            body = (f"{name} ({ticker}) has touched its 52-week LOW.\n\n"
                    f"Current Price: {live:.2f}\n"
                    f"52-Week Low: {low_52w:.2f}\n\n"
                    f"Time (IST): {now_ist().strftime('%Y-%m-%d %H:%M:%S')}")
            ok, msg = send_email_alert(sender_email, app_password, recipient_email, subject, body)
            if ok:
                already_alerted_set.add(alert_key_low)
                sent_any = True
            messages.append((name, "52W LOW", ok, msg))

    return sent_any, messages


# ===================================================================
# 💼 TRANSACTION LEDGER ENGINE (Buy/Sell tracking, FIFO realized P&L, XIRR)
# ===================================================================
TRANSACTIONS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "transactions.csv")
TX_COLUMNS = ["date", "share_name", "ticker", "txn_type", "quantity", "price"]

HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfolio_history.csv")
HISTORY_COLUMNS = ["date", "total_invested", "total_current", "total_pnl"]


def load_transactions() -> pd.DataFrame:
    """Load the saved buy/sell transaction ledger from disk. Returns an empty frame if none yet."""
    try:
        if os.path.exists(TRANSACTIONS_FILE):
            df_tx = pd.read_csv(TRANSACTIONS_FILE)
            df_tx['date'] = pd.to_datetime(df_tx['date'], errors='coerce')
            return df_tx
    except Exception:
        pass
    return pd.DataFrame(columns=TX_COLUMNS)


def save_transactions(df_tx: pd.DataFrame):
    """Persist the transaction ledger to disk so it survives app restarts."""
    try:
        out = df_tx.copy()
        out['date'] = pd.to_datetime(out['date']).dt.strftime('%Y-%m-%d')
        out.to_csv(TRANSACTIONS_FILE, index=False)
        return True
    except Exception:
        return False


def append_transactions(new_rows: pd.DataFrame):
    """Append new transaction rows to the existing ledger and persist."""
    existing = load_transactions()
    combined = pd.concat([existing, new_rows], ignore_index=True)
    save_transactions(combined)
    return combined


def compute_fifo_realized_pnl(df_tx: pd.DataFrame):
    """For each share_name, matches SELL transactions against earlier BUY lots using FIFO
    (First-In-First-Out -- the standard, tax-compliant method in India).

    Returns:
        realized_df: one row per SELL transaction with realized P&L, holding period, STCG/LTCG tag
        open_lots_df: remaining unsold BUY lots per share_name (used to cross-check open quantity)
    """
    if df_tx.empty:
        return pd.DataFrame(), pd.DataFrame()

    realized_rows = []
    open_lots_rows = []

    for share_name, group in df_tx.sort_values('date').groupby('share_name'):
        # FIFO queue of open buy lots: each lot = [date, qty_remaining, price]
        buy_queue = []
        for _, row in group.iterrows():
            qty = float(row['quantity'])
            price = float(row['price'])
            date = row['date']
            ticker = row.get('ticker', '')

            if str(row['txn_type']).upper() == 'BUY':
                buy_queue.append({"date": date, "qty": qty, "price": price})
            elif str(row['txn_type']).upper() == 'SELL':
                qty_to_sell = qty
                while qty_to_sell > 1e-9 and buy_queue:
                    lot = buy_queue[0]
                    matched_qty = min(lot['qty'], qty_to_sell)

                    holding_days = (date - lot['date']).days if pd.notna(date) and pd.notna(lot['date']) else 0
                    term = "LTCG (>1yr)" if holding_days > 365 else "STCG (<1yr)"

                    realized_pnl = (price - lot['price']) * matched_qty
                    realized_rows.append({
                        "share_name": share_name,
                        "ticker": ticker,
                        "sell_date": date,
                        "buy_date": lot['date'],
                        "quantity": matched_qty,
                        "buy_price": lot['price'],
                        "sell_price": price,
                        "realized_pnl": realized_pnl,
                        "holding_days": holding_days,
                        "tax_term": term
                    })

                    lot['qty'] -= matched_qty
                    qty_to_sell -= matched_qty
                    if lot['qty'] <= 1e-9:
                        buy_queue.pop(0)

        # Whatever is left in buy_queue is still held (open position)
        for lot in buy_queue:
            if lot['qty'] > 1e-9:
                open_lots_rows.append({
                    "share_name": share_name,
                    "buy_date": lot['date'],
                    "quantity": lot['qty'],
                    "buy_price": lot['price']
                })

    realized_df = pd.DataFrame(realized_rows)
    open_lots_df = pd.DataFrame(open_lots_rows)
    return realized_df, open_lots_df


def calculate_xirr(cashflows):
    """Calculates XIRR (annualized real rate of return) given a list of (date, amount) tuples.
    Negative amounts = money going out (buys), positive = money coming in (sells / current value).
    Uses Newton's method with a bisection fallback for robustness -- no external dependency needed."""
    if len(cashflows) < 2:
        return None

    dates = [c[0] for c in cashflows]
    amounts = [c[1] for c in cashflows]
    t0 = min(dates)

    def xnpv(rate):
        return sum(amt / ((1 + rate) ** ((d - t0).days / 365.0)) for d, amt in zip(dates, amounts))

    def xnpv_derivative(rate):
        return sum(-((d - t0).days / 365.0) * amt / ((1 + rate) ** (((d - t0).days / 365.0) + 1))
                   for d, amt in zip(dates, amounts))

    rate = 0.1
    for _ in range(100):
        try:
            f = xnpv(rate)
            f_prime = xnpv_derivative(rate)
            if abs(f_prime) < 1e-10:
                break
            new_rate = rate - f / f_prime
            if abs(new_rate - rate) < 1e-7:
                rate = new_rate
                break
            rate = new_rate
        except (OverflowError, ZeroDivisionError):
            break

    if rate <= -1 or rate > 100 or pd.isna(rate):
        # Fallback: bisection search between -99% and +1000% return
        lo, hi = -0.99, 10.0
        for _ in range(200):
            mid = (lo + hi) / 2
            try:
                val = xnpv(mid)
            except OverflowError:
                val = float('inf')
            if abs(val) < 1e-3:
                return mid * 100
            if val > 0:
                lo = mid
            else:
                hi = mid
        return None

    return rate * 100


def append_history_snapshot(total_invested, total_current, total_pnl):
    """Saves today's portfolio totals as a snapshot row (one row per day) for the trend chart."""
    try:
        today_str = now_ist().strftime('%Y-%m-%d')
        if os.path.exists(HISTORY_FILE):
            hist = pd.read_csv(HISTORY_FILE)
        else:
            hist = pd.DataFrame(columns=HISTORY_COLUMNS)

        hist = hist[hist['date'] != today_str]  # replace today's snapshot if it already exists
        new_row = pd.DataFrame([{
            "date": today_str, "total_invested": total_invested,
            "total_current": total_current, "total_pnl": total_pnl
        }])
        hist = pd.concat([hist, new_row], ignore_index=True)
        hist.to_csv(HISTORY_FILE, index=False)
    except Exception:
        pass


def load_history():
    try:
        if os.path.exists(HISTORY_FILE):
            hist = pd.read_csv(HISTORY_FILE)
            hist['date'] = pd.to_datetime(hist['date'])
            return hist.sort_values('date')
    except Exception:
        pass
    return pd.DataFrame(columns=HISTORY_COLUMNS)


@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def fetch_sector_info(tickers_list):
    """Fetches sector/industry classification for each ticker from Yahoo Finance."""
    sector_map = {}
    for ticker in tickers_list:
        if not ticker:
            continue
        try:
            info = yf.Ticker(ticker).info
            sector_map[ticker] = info.get('sector') or 'Unknown'
        except Exception:
            sector_map[ticker] = 'Unknown'
    return sector_map


# Session state init
if "alerted_keys" not in st.session_state:
    st.session_state.alerted_keys = set()
if "manual_ticker_overrides" not in st.session_state:
    st.session_state.manual_ticker_overrides = load_overrides()
if "transactions_df" not in st.session_state:
    st.session_state.transactions_df = load_transactions()
if "saved_mappings" not in st.session_state:
    st.session_state.saved_mappings = load_mappings()  # {portfolio: {ticker, qty, price}, tx: {date, name, ticker, type, qty, price}}

# ==================== SIDEBAR (TERMINAL CONTROLS) ====================
with st.sidebar:
    st.markdown("<h2 style='color: #00bfff; text-align: center; font-family: monospace;'>ALPHA TERMINAL</h2>", unsafe_allow_html=True)
    st.markdown("---")
    menu = st.radio("⚡ Terminal Monitor", [
        "🖥️ Overview Dashboard",
        "📈 Advanced Analysis",
        "🔍 Single Stock Matrix",
        "🔎 Search Any Stock",
        "💼 Transaction Ledger (Buy/Sell)"
    ])
    st.markdown("---")

    st.markdown("### 🔍 Quick Filter")
    stock_filter = st.selectbox("Filter holdings by status:", ["All Holdings", "🟢 Profit Only", "🔴 Loss Only"])
    st.markdown("---")

    st.markdown("### 🎯 Risk Management Levels")
    target_pct = st.slider("Profit Taking LIMIT (%)", min_value=5, max_value=100, value=20, step=5)
    stop_loss_pct = st.slider("Manual Stop Loss (%)", min_value=-50, max_value=-5, value=-10, step=5)
    st.markdown("---")

    st.markdown("### 📉 Stress Test (Market Shock)")
    market_shock = st.slider("Simulate Market Crash/Rally (%)", min_value=-50, max_value=50, value=0, step=5)
    st.markdown("---")

    # ---------------- EMAIL ALERT SETTINGS ----------------
    st.markdown("### 📧 Email Alerts (52-Week High/Low)")
    enable_email_alerts = st.checkbox("Enable email alerts", value=False)
    sender_email_input = ""
    app_password_input = ""
    recipient_email_input = ""
    if enable_email_alerts:
        st.caption("Uses Gmail SMTP. You need a Gmail **App Password** (not your normal password) — generate one at myaccount.google.com → Security → App Passwords.")
        sender_email_input = st.text_input("Your Gmail address (sender)", value="", placeholder="you@gmail.com")
        app_password_input = st.text_input("Gmail App Password", value="", type="password")
        recipient_email_input = st.text_input("Alert recipient email", value=sender_email_input, placeholder="you@gmail.com")
        st.caption("Alerts are checked and sent only while this app is open and running, on every auto-refresh (every 60 seconds).")

    st.markdown("---")
    st.markdown("### 🛠️ Manual Ticker Overrides")
    st.caption("Companies that couldn't be auto-found will show an input box right next to their name on the main dashboard (below the warning). Fill those in — they get saved here automatically.")
    if st.session_state.manual_ticker_overrides:
        st.caption(f"✅ {len(st.session_state.manual_ticker_overrides)} manual ticker(s) currently saved.")
        with st.expander("View / Clear saved overrides"):
            for k, v in list(st.session_state.manual_ticker_overrides.items()):
                ov_col1, ov_col2 = st.columns([3, 1])
                ov_col1.write(f"**{k}** → `{v}`")
                if ov_col2.button("❌", key=f"del_ov_{k}"):
                    st.session_state.manual_ticker_overrides.pop(k, None)
                    save_overrides(st.session_state.manual_ticker_overrides)
                    st.cache_data.clear()
                    st.rerun()
    else:
        st.caption("No manual overrides saved yet.")

# ==================== FILE UPLOAD INTERFACE ====================
st.markdown("<h2 style='text-align: left; color: #ffffff;'>📊 Portfolio Intelligence Terminal v4.0</h2>", unsafe_allow_html=True)
uploaded_file = st.file_uploader("Drag and drop any Excel or CSV file", type=['csv', 'xlsx'])

df = pd.DataFrame()

# Data load logic
if uploaded_file is not None:
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
    except Exception as e:
        st.error(f"⚠️ File Error: {e}")

def color_pnl(val):
    if isinstance(val, str): return ''
    return f'color: #00ff66; font-weight: bold;' if val >= 0 else f'color: #ff3333; font-weight: bold;'

# ==================== SEARCH ANY STOCK TAB (works even without a file) ====================
@st.cache_data(ttl=10, show_spinner=False)
def fetch_search_suggestions(query: str):
    """Fetch live company name + ticker suggestions from Yahoo Finance search API
    as the user types — returns list of {name, ticker, exchange, type} dicts."""
    if not query or len(query.strip()) < 2:
        return []
    suggestions = []
    try:
        import requests
        url = "https://query2.finance.yahoo.com/v1/finance/search"
        resp = requests.get(url,
            params={"q": query, "quotesCount": 10, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=4)
        if resp.status_code == 200:
            for q in resp.json().get("quotes", []):
                if q.get("quoteType") not in ("EQUITY", "ETF", "MUTUALFUND", None):
                    continue
                suggestions.append({
                    "label": f"{q.get('longname') or q.get('shortname') or q.get('symbol')}  —  {q.get('symbol')}  [{q.get('exchange','')}]",
                    "ticker": q.get("symbol", ""),
                    "name": q.get("longname") or q.get("shortname") or q.get("symbol", ""),
                })
    except Exception:
        pass
    if not suggestions:
        try:
            s = yf.Search(query, max_results=10)
            for q in (s.quotes or []):
                suggestions.append({
                    "label": f"{q.get('longname') or q.get('shortname') or q.get('symbol')}  —  {q.get('symbol')}",
                    "ticker": q.get("symbol", ""),
                    "name": q.get("longname") or q.get("shortname") or q.get("symbol", ""),
                })
        except Exception:
            pass
    return suggestions[:10]


if "Search Any Stock" in menu or "🔎" in menu:
    st.markdown("<h3>🔎 Search Any Stock</h3>", unsafe_allow_html=True)
    st.caption("Type 2+ letters — suggestions appear automatically. **Select from dropdown** or press Enter to load live price & 52-week data.")

    # Session state init for search
    if "search_selected_ticker" not in st.session_state:
        st.session_state.search_selected_ticker = ""
    if "search_last_query" not in st.session_state:
        st.session_state.search_last_query = ""

    # Step 1: Type to search
    search_query = st.text_input(
        "🔍 Type company name or ticker:",
        placeholder="e.g. Reliance, Dabur, TCS, Apple, INFY…",
        key="search_box_input"
    )

    confirmed_ticker = st.session_state.search_selected_ticker

    # If user cleared the box, reset confirmed ticker too
    if not search_query and confirmed_ticker:
        st.session_state.search_selected_ticker = ""
        confirmed_ticker = ""

    # Step 2: Show dropdown selectbox once 2+ chars typed
    if search_query and len(search_query.strip()) >= 2:
        suggestions = fetch_search_suggestions(search_query.strip())

        if suggestions:
            options = [s["label"] for s in suggestions]
            tickers = [s["ticker"] for s in suggestions]
            names   = [s["name"]   for s in suggestions]

            # Find if previously selected option is still in list
            prev_label = next(
                (s["label"] for s in suggestions if s["ticker"] == confirmed_ticker),
                None
            )
            default_idx = options.index(prev_label) if prev_label else 0

            chosen_label = st.selectbox(
                f"📋 {len(suggestions)} match(es) found — select one (or press Enter for top result):",
                options=options,
                index=default_idx,
                key=f"search_dropdown_{search_query[:20]}"
            )

            chosen_idx = options.index(chosen_label)
            auto_ticker = tickers[chosen_idx]
            auto_name   = names[chosen_idx]

            # Auto-load: whenever selection changes OR Enter pressed (query submitted)
            if auto_ticker != confirmed_ticker:
                st.session_state.search_selected_ticker = auto_ticker
                confirmed_ticker = auto_ticker

        else:
            st.info("No suggestions found — try a different spelling or use exact Yahoo ticker (e.g. RELIANCE.NS).")
            confirmed_ticker = ""

    # Step 3: Show stock data for confirmed ticker
    if confirmed_ticker:
        col_hdr, col_clr = st.columns([5, 1])
        with col_clr:
            if st.button("✖ New Search", use_container_width=True):
                st.session_state.search_selected_ticker = ""
                st.rerun()

        with st.spinner(f"Loading live data for **{confirmed_ticker}**..."):
            result = search_any_stock(confirmed_ticker)

        if result is None:
            st.error(f"⚠️ Could not fetch data for {confirmed_ticker}. Try another.")
        else:
            st.markdown(f"#### {result['company_name']}  `{result['ticker']}`")
            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                st.markdown(f'<div class="terminal-card"><div class="metric-title">LIVE PRICE</div><div class="metric-value">{result["currency"]} {result["live_price"]:,.2f}</div></div>', unsafe_allow_html=True)
            with sc2:
                high_txt = f'{result["currency"]} {result["high_52w"]:,.2f}' if result["high_52w"] else "N/A"
                st.markdown(f'<div class="terminal-card"><div class="metric-title">52-WEEK HIGH</div><div class="metric-value" style="color:#3fb950;">{high_txt}</div></div>', unsafe_allow_html=True)
            with sc3:
                low_txt = f'{result["currency"]} {result["low_52w"]:,.2f}' if result["low_52w"] else "N/A"
                st.markdown(f'<div class="terminal-card"><div class="metric-title">52-WEEK LOW</div><div class="metric-value" style="color:#f85149;">{low_txt}</div></div>', unsafe_allow_html=True)

            if not result["history"].empty:
                fig_search = go.Figure(data=[go.Scatter(
                    x=result["history"].index, y=result["history"]['Close'],
                    line=dict(color='#58a6ff'), fill='tozeroy',
                    fillcolor='rgba(88,166,255,0.08)'
                )])
                fig_search.update_layout(
                    plot_bgcolor='#161b22', paper_bgcolor='#0d1117',
                    font=dict(color='#8b949e'),
                    margin=dict(l=10, r=10, t=36, b=10),
                    title=dict(text="1-Year Price Trend", font=dict(color='#e6edf3')),
                    xaxis=dict(gridcolor='#21262d', color='#8b949e'),
                    yaxis=dict(gridcolor='#21262d', color='#8b949e')
                )
                st.plotly_chart(fig_search, use_container_width=True)
    elif not search_query:
        st.info("💡 Start typing above — company suggestions will appear automatically.")

# ==================== TRANSACTION LEDGER TAB ====================
elif "Transaction Ledger" in menu or "💼" in menu:
    st.markdown("<h2 style='color:#e6edf3;'>💼 Transaction Ledger & P&L Analytics</h2>", unsafe_allow_html=True)

    tx_tab4, tx_tab1, tx_tab2, tx_tab3 = st.tabs([
        "📊 P&L Dashboard",
        "📤 Upload Trade File",
        "➕ Manual Entry",
        "📜 Full Ledger",
    ])

    # ================================================================
    # TAB 1 (shown first): P&L DASHBOARD
    # ================================================================
    with tx_tab4:
        rpt = st.session_state.get("rpt_trades", pd.DataFrame())
        if rpt.empty:
            st.markdown("""
            <div style='text-align:center; padding:60px 20px;'>
                <div style='font-size:64px;'>📂</div>
                <h3 style='color:#8b949e; margin-top:16px;'>No trades loaded yet</h3>
                <p style='color:#6e7681;'>Go to the <b>📤 Upload Trade File</b> tab, upload your broker's P&L export, map the columns, and click Confirm.</p>
            </div>""", unsafe_allow_html=True)
        else:
            total_buy   = rpt["buy_value"].sum()
            total_sell  = rpt["sell_value"].sum()
            total_pnl   = rpt["realized_pnl"].sum()
            stcg_df     = rpt[rpt["tax_term"] == "STCG (<1yr)"]
            ltcg_df     = rpt[rpt["tax_term"] == "LTCG (>1yr)"]
            stcg_pnl    = stcg_df["realized_pnl"].sum()
            ltcg_pnl    = ltcg_df["realized_pnl"].sum()
            profit_trades = (rpt["realized_pnl"] > 0).sum()
            loss_trades   = (rpt["realized_pnl"] < 0).sum()
            win_rate_tx   = profit_trades / len(rpt) * 100 if len(rpt) > 0 else 0
            avg_win       = rpt[rpt["realized_pnl"] > 0]["realized_pnl"].mean() if profit_trades > 0 else 0
            avg_loss      = rpt[rpt["realized_pnl"] < 0]["realized_pnl"].mean() if loss_trades > 0 else 0
            best_trade    = rpt.loc[rpt["realized_pnl"].idxmax()] if len(rpt) > 0 else None
            worst_trade   = rpt.loc[rpt["realized_pnl"].idxmin()] if len(rpt) > 0 else None
            est_stcg_tax  = max(0, stcg_pnl) * 0.20
            est_ltcg_tax  = max(0, ltcg_pnl - 100000) * 0.125 if ltcg_pnl > 100000 else 0
            total_tax     = est_stcg_tax + est_ltcg_tax

            # ── Row 1: Main KPIs ──
            st.markdown("### 📈 Realized P&L Summary")
            k1,k2,k3,k4,k5,k6 = st.columns(6)
            pnl_color = "#3fb950" if total_pnl >= 0 else "#f85149"
            k1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL REALIZED P&L</div><div class="metric-value" style="color:{pnl_color};">₹{total_pnl:,.0f}</div></div>', unsafe_allow_html=True)
            k2.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL INVESTED (Buy)</div><div class="metric-value">₹{total_buy:,.0f}</div></div>', unsafe_allow_html=True)
            k3.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL RECEIVED (Sell)</div><div class="metric-value">₹{total_sell:,.0f}</div></div>', unsafe_allow_html=True)
            k4.markdown(f'<div class="terminal-card"><div class="metric-title">WIN RATE</div><div class="metric-value" style="color:#58a6ff;">{win_rate_tx:.1f}%</div><div class="metric-status-blue">{profit_trades}W / {loss_trades}L / {len(rpt)}T</div></div>', unsafe_allow_html=True)
            k5.markdown(f'<div class="terminal-card"><div class="metric-title">STCG P&L</div><div class="metric-value" style="color:{"#3fb950" if stcg_pnl>=0 else "#f85149"};">₹{stcg_pnl:,.0f}</div><div class="metric-status-blue">Tax ₹{est_stcg_tax:,.0f}</div></div>', unsafe_allow_html=True)
            k6.markdown(f'<div class="terminal-card"><div class="metric-title">LTCG P&L</div><div class="metric-value" style="color:{"#3fb950" if ltcg_pnl>=0 else "#f85149"};">₹{ltcg_pnl:,.0f}</div><div class="metric-status-blue">Tax ₹{est_ltcg_tax:,.0f}</div></div>', unsafe_allow_html=True)

            # ── Row 2: Tax + Avg Win/Loss + Best/Worst ──
            st.markdown("---")
            b1,b2,b3,b4 = st.columns(4)
            b1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL EST. TAX LIABILITY</div><div class="metric-value" style="color:#e3b341;">₹{total_tax:,.0f}</div><div class="metric-status-blue">STCG+LTCG combined</div></div>', unsafe_allow_html=True)
            b2.markdown(f'<div class="terminal-card"><div class="metric-title">AVG WINNING TRADE</div><div class="metric-value" style="color:#3fb950;">₹{avg_win:,.0f}</div></div>', unsafe_allow_html=True)
            b3.markdown(f'<div class="terminal-card"><div class="metric-title">AVG LOSING TRADE</div><div class="metric-value" style="color:#f85149;">₹{avg_loss:,.0f}</div></div>', unsafe_allow_html=True)
            rr = abs(avg_win/avg_loss) if avg_loss != 0 else 0
            b4.markdown(f'<div class="terminal-card"><div class="metric-title">RISK:REWARD RATIO</div><div class="metric-value" style="color:#58a6ff;">1 : {rr:.2f}</div></div>', unsafe_allow_html=True)

            # ── Best / Worst Trade highlight ──
            if best_trade is not None and worst_trade is not None:
                bw1, bw2 = st.columns(2)
                with bw1:
                    st.markdown(f"""<div class="alert-box-high">
                        🏆 <b>BEST TRADE</b> — {best_trade['share_name']}<br>
                        Buy ₹{best_trade['buy_price']:,.2f} → Sell ₹{best_trade['sell_price']:,.2f} × {best_trade['quantity']:.0f} shares<br>
                        <b style='font-size:18px;'>P&L: ₹{best_trade['realized_pnl']:,.2f}</b> &nbsp;|&nbsp; {best_trade['tax_term']}
                    </div>""", unsafe_allow_html=True)
                with bw2:
                    st.markdown(f"""<div class="alert-box-low">
                        📉 <b>WORST TRADE</b> — {worst_trade['share_name']}<br>
                        Buy ₹{worst_trade['buy_price']:,.2f} → Sell ₹{worst_trade['sell_price']:,.2f} × {worst_trade['quantity']:.0f} shares<br>
                        <b style='font-size:18px;'>P&L: ₹{worst_trade['realized_pnl']:,.2f}</b> &nbsp;|&nbsp; {worst_trade['tax_term']}
                    </div>""", unsafe_allow_html=True)

            st.caption("⚠️ Tax estimate is indicative only. LTCG exempt up to ₹1 lakh/year. Consult a CA for actual filing.")
            st.markdown("---")

            # ── Charts Row 1: Monthly trend + Cumulative P&L ──
            ch1, ch2 = st.columns(2)
            with ch1:
                st.markdown("#### 📅 Monthly Realized P&L")
                rpt_m = rpt.copy()
                rpt_m["month"] = rpt_m["sell_date"].dt.to_period("M").astype(str)
                monthly = rpt_m.groupby("month")["realized_pnl"].sum().reset_index()
                fig_m = go.Figure(go.Bar(
                    x=monthly["month"], y=monthly["realized_pnl"],
                    marker_color=["#3fb950" if v >= 0 else "#f85149" for v in monthly["realized_pnl"]],
                    text=monthly["realized_pnl"].apply(lambda v: f"₹{v:,.0f}"),
                    textposition="auto"
                ))
                fig_m.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117',
                    font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10),
                    xaxis=dict(gridcolor='#21262d', tickangle=-45),
                    yaxis=dict(gridcolor='#21262d', title="P&L (₹)"))
                st.plotly_chart(fig_m, use_container_width=True)

            with ch2:
                st.markdown("#### 📈 Cumulative P&L Over Time")
                rpt_sorted = rpt.sort_values("sell_date").copy()
                rpt_sorted["cumulative_pnl"] = rpt_sorted["realized_pnl"].cumsum()
                fig_cum = go.Figure()
                fig_cum.add_trace(go.Scatter(
                    x=rpt_sorted["sell_date"], y=rpt_sorted["cumulative_pnl"],
                    line=dict(color='#58a6ff', width=2), fill='tozeroy',
                    fillcolor='rgba(88,166,255,0.08)', name="Cumulative P&L"
                ))
                fig_cum.add_hline(y=0, line_dash="dot", line_color="#8b949e")
                fig_cum.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117',
                    font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10),
                    xaxis=dict(gridcolor='#21262d'),
                    yaxis=dict(gridcolor='#21262d', title="Cumulative P&L (₹)"),
                    showlegend=False)
                st.plotly_chart(fig_cum, use_container_width=True)

            # ── Charts Row 2: Top Gainers/Losers + STCG/LTCG pie ──
            ch3, ch4 = st.columns(2)
            with ch3:
                st.markdown("#### 🏆 Top Gainers & Losers (by stock)")
                by_stock = rpt.groupby("share_name", as_index=False)["realized_pnl"].sum().sort_values("realized_pnl")
                top_n = pd.concat([by_stock.head(5), by_stock.tail(5)]).drop_duplicates()
                fig_gl = go.Figure(go.Bar(
                    x=top_n["realized_pnl"], y=top_n["share_name"], orientation='h',
                    marker_color=["#3fb950" if v >= 0 else "#f85149" for v in top_n["realized_pnl"]],
                    text=top_n["realized_pnl"].apply(lambda v: f"₹{v:,.0f}"), textposition="auto"
                ))
                fig_gl.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117',
                    font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10),
                    xaxis=dict(gridcolor='#21262d'), yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_gl, use_container_width=True)

            with ch4:
                st.markdown("#### 🥧 STCG vs LTCG Breakdown")
                fig_tax = go.Figure(go.Pie(
                    labels=["STCG (<1yr)", "LTCG (>1yr)"],
                    values=[max(0.01,len(stcg_df)), max(0.01,len(ltcg_df))],
                    hole=0.55,
                    marker=dict(colors=["#58a6ff","#3fb950"]),
                    textinfo="label+percent"
                ))
                fig_tax.update_layout(paper_bgcolor='#0d1117', font=dict(color='#8b949e'),
                    margin=dict(l=10,r=10,t=10,b=10))
                st.plotly_chart(fig_tax, use_container_width=True)

            # ── Stock-wise filter + detail table ──
            st.markdown("---")
            st.markdown("#### 🔍 Stock-wise P&L Filter")
            all_stocks = ["All Stocks"] + sorted(rpt["share_name"].unique().tolist())
            sel_stock = st.selectbox("Select a specific stock to see its trades:", all_stocks)
            rpt_filtered = rpt if sel_stock == "All Stocks" else rpt[rpt["share_name"] == sel_stock]

            if sel_stock != "All Stocks":
                fs1, fs2, fs3 = st.columns(3)
                spnl = rpt_filtered["realized_pnl"].sum()
                fs1.markdown(f'<div class="terminal-card"><div class="metric-title">{sel_stock} — TOTAL P&L</div><div class="metric-value" style="color:{"#3fb950" if spnl>=0 else "#f85149"};">₹{spnl:,.2f}</div></div>', unsafe_allow_html=True)
                fs2.markdown(f'<div class="terminal-card"><div class="metric-title">TRADES</div><div class="metric-value">{len(rpt_filtered)}</div></div>', unsafe_allow_html=True)
                s_wr = (rpt_filtered["realized_pnl"]>0).sum()/len(rpt_filtered)*100
                fs3.markdown(f'<div class="terminal-card"><div class="metric-title">WIN RATE</div><div class="metric-value" style="color:#58a6ff;">{s_wr:.1f}%</div></div>', unsafe_allow_html=True)

            show_rpt = rpt_filtered.copy()
            show_rpt["buy_date"]  = pd.to_datetime(show_rpt["buy_date"],  errors='coerce').dt.strftime("%d %b %Y")
            show_rpt["sell_date"] = pd.to_datetime(show_rpt["sell_date"], errors='coerce').dt.strftime("%d %b %Y")
            show_rpt = show_rpt.rename(columns={
                "share_name":"Company","quantity":"Qty",
                "buy_date":"Purchase Date","buy_price":"Buy Price","buy_value":"Buy Value",
                "sell_date":"Sell Date","sell_price":"Sell Price","sell_value":"Sell Value",
                "realized_pnl":"P&L (₹)","holding_days":"Days Held","tax_term":"Tax Term"
            })
            dcols = [c for c in ["Company","Qty","Purchase Date","Buy Price","Buy Value",
                                  "Sell Date","Sell Price","Sell Value","P&L (₹)","Days Held","Tax Term"] if c in show_rpt.columns]
            st.dataframe(
                show_rpt[dcols].style
                .format({"Buy Price":"₹{:,.2f}","Buy Value":"₹{:,.2f}",
                         "Sell Price":"₹{:,.2f}","Sell Value":"₹{:,.2f}","P&L (₹)":"₹{:,.2f}"})
                .map(color_pnl, subset=["P&L (₹)"]),
                use_container_width=True, height=380
            )
            st.download_button("📥 Download Trade Analysis (CSV)",
                data=show_rpt[dcols].to_csv(index=False).encode("utf-8"),
                file_name=f"trade_pnl_{sel_stock.replace(' ','_')}.csv",
                mime="text/csv", use_container_width=True)

    # ================================================================
    # TAB 2: ROW-PER-TRADE UPLOAD
    # ================================================================
    with tx_tab1:
        st.markdown("**Upload your broker's trade export file** — each row should have Purchase Date, Purchase Price, Sell Date, Sell Price in the same row.")
        st.caption("Map your file's columns below. Click **Save Mapping** once — it will be remembered forever.")

        rpt_file = st.file_uploader("Upload trade file (CSV or Excel)", type=['csv','xlsx'], key="rpt_upload")

        if rpt_file is not None:
            try:
                rpt_df = pd.read_excel(rpt_file) if rpt_file.name.endswith('.xlsx') else pd.read_csv(rpt_file)
                rpt_cols  = [c.strip() for c in rpt_df.columns]
                rpt_df.columns = rpt_cols
                rpt_lower = [c.lower() for c in rpt_cols]
                saved_rpt = st.session_state.saved_mappings.get("rpt", {})

                def _rpt_idx(key, kws, fallback=0):
                    if key in saved_rpt and saved_rpt[key] in rpt_cols:
                        return rpt_cols.index(saved_rpt[key]) + 1
                    m = next((i for i,c in enumerate(rpt_lower) if any(kw in c for kw in kws)), -1)
                    return m + 1 if m >= 0 else 0

                NONE = "(None / Not in file)"
                opts = [NONE] + rpt_cols
                saved_notice = " ✅ saved mapping applied" if saved_rpt else ""

                st.markdown(f"#### 🗺️ Column Mapping{saved_notice}")
                r1,r2,r3 = st.columns(3)
                r4,r5,r6 = st.columns(3)
                r7,r8,r9 = st.columns(3)
                r10,_,save_col = st.columns([3,1,1])

                with r1: m_name      = st.selectbox("🏢 Company Name *", opts, index=_rpt_idx("name",["instrument","name","company","stock","scrip"]))
                with r2: m_qty       = st.selectbox("📦 Quantity *", opts, index=_rpt_idx("qty",["qty","quantity","shares","units","volume"]))
                with r3: m_isin      = st.selectbox("🔖 ISIN (optional)", opts, index=_rpt_idx("isin",["isin"]))
                with r4: m_buy_date  = st.selectbox("📅 Purchase Date *", opts, index=_rpt_idx("buy_date",["purchase date","buy date","purchasedate","purchase_date"]))
                with r5: m_buy_price = st.selectbox("💰 Purchase Price *", opts, index=_rpt_idx("buy_price",["purchase price","buy price","purchaseprice","purchase_price"]))
                with r6: m_buy_value = st.selectbox("💵 Purchase Value (optional)", opts, index=_rpt_idx("buy_value",["purchase value","purchase cost","purchasevalue","purchase_value","purchase_cost"]))
                with r7: m_sell_date = st.selectbox("📅 Sell Date *", opts, index=_rpt_idx("sell_date",["sell date","selldate","sell_date"]))
                with r8: m_sell_price= st.selectbox("💸 Sell Price *", opts, index=_rpt_idx("sell_price",["sell price","sellprice","sell_price"]))
                with r9: m_sell_value= st.selectbox("💵 Sell Value (optional)", opts, index=_rpt_idx("sell_value",["sell value","sellvalue","sell_value"]))
                with r10: m_pnl      = st.selectbox("📈 P&L column (if pre-calculated)", opts, index=_rpt_idx("pnl",["long term","g/l","gain","loss","pnl","profit","p&l","p / l"]))
                with save_col:
                    st.markdown("<br><br>", unsafe_allow_html=True)
                    if st.button("💾 Save Mapping", use_container_width=True, key="save_rpt_map"):
                        pm = st.session_state.saved_mappings
                        pm["rpt"] = {"name":m_name,"qty":m_qty,"isin":m_isin,"buy_date":m_buy_date,"buy_price":m_buy_price,"buy_value":m_buy_value,"sell_date":m_sell_date,"sell_price":m_sell_price,"sell_value":m_sell_value,"pnl":m_pnl}
                        save_mappings(pm); st.session_state.saved_mappings = pm
                        st.toast("✅ Mapping saved!", icon="💾"); st.rerun()

                required = {"Company Name":m_name,"Purchase Date":m_buy_date,"Purchase Price":m_buy_price,"Sell Date":m_sell_date,"Sell Price":m_sell_price,"Quantity":m_qty}
                missing_req = [k for k,v in required.items() if v == NONE]
                if missing_req:
                    st.warning(f"⚠️ Map these required fields first: **{', '.join(missing_req)}**")
                else:
                    trades = pd.DataFrame()
                    trades["share_name"]  = rpt_df[m_name].astype(str).str.strip()
                    trades["quantity"]    = pd.to_numeric(rpt_df[m_qty], errors='coerce').fillna(0)
                    trades["buy_date"]    = pd.to_datetime(rpt_df[m_buy_date], errors='coerce')
                    trades["buy_price"]   = pd.to_numeric(rpt_df[m_buy_price], errors='coerce').fillna(0)
                    trades["sell_date"]   = pd.to_datetime(rpt_df[m_sell_date], errors='coerce')
                    trades["sell_price"]  = pd.to_numeric(rpt_df[m_sell_price], errors='coerce').fillna(0)
                    trades["buy_value"]   = pd.to_numeric(rpt_df[m_buy_value], errors='coerce').fillna(0) if m_buy_value!=NONE else trades["quantity"]*trades["buy_price"]
                    trades["sell_value"]  = pd.to_numeric(rpt_df[m_sell_value], errors='coerce').fillna(0) if m_sell_value!=NONE else trades["quantity"]*trades["sell_price"]
                    trades["isin"]        = rpt_df[m_isin].astype(str).str.strip() if m_isin!=NONE else ""
                    trades["realized_pnl"]= pd.to_numeric(rpt_df[m_pnl], errors='coerce').fillna(0) if m_pnl!=NONE else trades["sell_value"]-trades["buy_value"]
                    trades["holding_days"]= (trades["sell_date"]-trades["buy_date"]).dt.days.fillna(0).astype(int)
                    trades["tax_term"]    = trades["holding_days"].apply(lambda d: "LTCG (>1yr)" if d>365 else "STCG (<1yr)")
                    trades = trades.dropna(subset=["buy_date","sell_date"])
                    trades = trades[trades["quantity"]>0]

                    st.markdown(f"#### 📋 Preview — {len(trades)} trades")
                    prev = trades.copy()
                    prev["buy_date"]  = pd.to_datetime(prev["buy_date"],  errors='coerce').dt.strftime("%d %b %Y")
                    prev["sell_date"] = pd.to_datetime(prev["sell_date"], errors='coerce').dt.strftime("%d %b %Y")
                    st.dataframe(
                        prev[["share_name","quantity","buy_date","buy_price","sell_date","sell_price","realized_pnl","holding_days","tax_term"]]
                        .rename(columns={"share_name":"Company","quantity":"Qty","buy_date":"Buy Date","buy_price":"Buy ₹","sell_date":"Sell Date","sell_price":"Sell ₹","realized_pnl":"P&L (₹)","holding_days":"Days","tax_term":"Term"})
                        .style.format({"Buy ₹":"₹{:,.2f}","Sell ₹":"₹{:,.2f}","P&L (₹)":"₹{:,.2f}"})
                        .map(color_pnl, subset=["P&L (₹)"]),
                        use_container_width=True, height=260
                    )
                    if st.button("✅ Confirm & Load to P&L Dashboard", use_container_width=True, key="confirm_rpt"):
                        st.session_state["rpt_trades"] = trades
                        st.success(f"✅ {len(trades)} trades loaded! Switch to 📊 P&L Dashboard tab.")
                        st.rerun()

            except Exception as e:
                st.error(f"⚠️ Could not read file: {e}")

        elif "rpt_trades" in st.session_state and not st.session_state["rpt_trades"].empty:
            n = len(st.session_state["rpt_trades"])
            st.success(f"✅ {n} trades already loaded. Switch to **📊 P&L Dashboard** to see analysis, or upload a new file to replace.")

    # ================================================================
    # TAB 3: MANUAL ENTRY
    # ================================================================
    with tx_tab2:
        st.caption("Add individual BUY or SELL transactions manually. These are tracked separately for open-position FIFO P&L.")
        with st.form("add_transaction_form", clear_on_submit=True):
            tcol1, tcol2 = st.columns(2)
            with tcol1:
                tx_share_name = st.text_input("Company Name", placeholder="e.g. Reliance Industries")
                tx_ticker     = st.text_input("Yahoo Ticker (optional)", placeholder="e.g. RELIANCE.NS")
                tx_type       = st.radio("Transaction Type", ["BUY","SELL"], horizontal=True)
            with tcol2:
                tx_date  = st.date_input("Transaction Date", value=now_ist().date())
                tx_qty   = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.2f")
                tx_price = st.number_input("Price per share (₹)", min_value=0.0, step=0.01, format="%.2f")
            if st.form_submit_button("💾 Add Transaction", use_container_width=True):
                if not tx_share_name or tx_qty<=0 or tx_price<=0:
                    st.error("⚠️ Fill in Company Name, Quantity, and Price.")
                else:
                    new_row = pd.DataFrame([{"date":pd.to_datetime(tx_date),"share_name":tx_share_name.strip(),"ticker":tx_ticker.strip().upper(),"txn_type":tx_type,"quantity":tx_qty,"price":tx_price}])
                    st.session_state.transactions_df = append_transactions(new_row)
                    st.success(f"✅ {tx_type} {tx_qty} × {tx_share_name} @ ₹{tx_price:,.2f}")
                    st.rerun()

    # ================================================================
    # TAB 4: FULL LEDGER (manual transactions + FIFO P&L)
    # ================================================================
    with tx_tab3:
        tx_df = st.session_state.transactions_df
        if tx_df.empty:
            st.info("💡 No manual transactions yet. Use the ➕ Manual Entry tab to add BUY/SELL rows.")
        else:
            st.markdown("#### 📜 Manual Transaction Ledger")
            disp = tx_df.copy().sort_values('date', ascending=False)
            disp['date'] = pd.to_datetime(disp['date'], errors='coerce').dt.strftime('%d %b %Y')
            st.dataframe(disp, use_container_width=True, height=260)
            dl_col, cl_col = st.columns([3,1])
            with dl_col:
                st.download_button("📥 Download Ledger (CSV)", data=tx_df.to_csv(index=False).encode('utf-8'), file_name="transaction_ledger.csv", mime="text/csv", use_container_width=True)
            with cl_col:
                if st.button("🗑️ Clear All", use_container_width=True):
                    st.session_state.transactions_df = pd.DataFrame(columns=TX_COLUMNS)
                    save_transactions(st.session_state.transactions_df); st.rerun()
            st.markdown("---")
            st.markdown("#### 💰 FIFO Realized P&L (from manual entries)")
            realized_df, open_lots_df = compute_fifo_realized_pnl(tx_df)
            if realized_df.empty:
                st.info("No SELL transactions yet — P&L will appear once you add a SELL.")
            else:
                total_r = realized_df['realized_pnl'].sum()
                stcg_r  = realized_df[realized_df['tax_term'].str.contains('STCG')]['realized_pnl'].sum()
                ltcg_r  = realized_df[realized_df['tax_term'].str.contains('LTCG')]['realized_pnl'].sum()
                rc1,rc2,rc3 = st.columns(3)
                rc1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL REALIZED P&L</div><div class="metric-value" style="color:{"#3fb950" if total_r>=0 else "#f85149"};">₹{total_r:,.2f}</div></div>', unsafe_allow_html=True)
                rc2.markdown(f'<div class="terminal-card"><div class="metric-title">STCG P&L</div><div class="metric-value" style="color:#58a6ff;">₹{stcg_r:,.2f}</div></div>', unsafe_allow_html=True)
                rc3.markdown(f'<div class="terminal-card"><div class="metric-title">LTCG P&L</div><div class="metric-value" style="color:#58a6ff;">₹{ltcg_r:,.2f}</div></div>', unsafe_allow_html=True)
            if not open_lots_df.empty:
                st.markdown("#### 📦 Open Lots (still held)")
                ol = open_lots_df.copy()
                ol['buy_date'] = pd.to_datetime(ol['buy_date']).dt.strftime('%d %b %Y')
                st.dataframe(ol.rename(columns={'share_name':'Stock','buy_date':'Buy Date','quantity':'Qty','buy_price':'Buy ₹'}), use_container_width=True, height=200)


elif not df.empty:
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    all_columns = list(df.columns)

    # ---- Load saved portfolio mapping (if any) ----
    saved_pm = st.session_state.saved_mappings.get("portfolio", {})

    def _col_idx(saved_key, fallback_keywords, fallback_pos=0):
        """Pick the index of a column: prefer saved mapping, then keyword match, then fallback position."""
        if saved_key in saved_pm and saved_pm[saved_key] in all_columns:
            return all_columns.index(saved_pm[saved_key])
        match = next((i for i, c in enumerate(all_columns) if c.lower() in fallback_keywords), fallback_pos)
        return match

    # Portfolio Column Mapping interface
    pmap_saved_notice = " ✅ (using saved mapping)" if saved_pm else ""
    st.markdown(f'<div class="map-box">🗺️ <b>Portfolio Column Mapping{pmap_saved_notice}</b><br><small style="color:#76808c;">Select the correct columns from your file. Click <b>Save Mapping</b> to remember this for next time — you won\'t need to select again.</small></div>', unsafe_allow_html=True)

    map_col1, map_col2, map_col3, map_col4 = st.columns([2, 2, 2, 1])

    with map_col1:
        ticker_col = st.selectbox("🌐 Ticker/Company column:", all_columns,
                                   index=_col_idx("ticker", [], 0))
    with map_col2:
        qty_col = st.selectbox("📦 Quantity column:", all_columns,
                                index=_col_idx("qty", ['quantity', 'qty', 'volume', 'shares'], 0))
    with map_col3:
        price_col = st.selectbox("💰 Buy Price column:", all_columns,
                                  index=_col_idx("price", ['buy_price', 'buy price', 'avg_price', 'avg price', 'rate', 'price'], min(2, len(all_columns)-1)))
    with map_col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 Save Mapping", use_container_width=True, help="Remember these column selections so you don't have to pick them again next time"):
            pm = st.session_state.saved_mappings
            pm["portfolio"] = {"ticker": ticker_col, "qty": qty_col, "price": price_col}
            save_mappings(pm)
            st.session_state.saved_mappings = pm
            st.toast("✅ Portfolio column mapping saved!", icon="💾")

    st.markdown("---")

    # Process data according to the selected columns
    df = df.dropna(subset=[ticker_col])
    df[ticker_col] = df[ticker_col].astype(str).str.strip()
    df = df[df[ticker_col] != '']
    df = df[~df[ticker_col].str.contains('Total|TOTAL|Grand', case=False, na=False)]

    # Convert data to numeric
    df['quantity'] = pd.to_numeric(df[qty_col], errors='coerce').fillna(0)
    df['buy_price'] = pd.to_numeric(df[price_col], errors='coerce').fillna(0)

    # Calculate original investment
    df['Invested'] = df['quantity'] * df['buy_price']
    df = df[df['Invested'] > 0].copy()

    # Fetch live prices directly from Yahoo Finance
    unique_tickers = df[ticker_col].unique().tolist()

    # 🔎 First resolve each entry (company name or ticker) into the correct Yahoo ticker
    manual_overrides_tuple = tuple(sorted(st.session_state.manual_ticker_overrides.items()))
    with st.spinner('🔎 Identifying company names as Yahoo tickers...'):
        ticker_resolution_map = resolve_tickers(tuple(unique_tickers), manual_overrides_tuple)

    df['resolved_ticker'] = df[ticker_col].map(ticker_resolution_map)

    # List of entries that couldn't be resolved (to show the user)
    unresolved_entries = sorted({
        raw for raw, resolved in ticker_resolution_map.items() if not resolved
    })

    resolved_unique_tickers = sorted({t for t in ticker_resolution_map.values() if t})

    with st.spinner('🗲 Fetching real-time live prices from Yahoo Finance...'):
        live_prices_map = fetch_live_prices_from_yahoo(tuple(resolved_unique_tickers))

    with st.spinner('📊 Fetching 52-week high/low range...'):
        range_map = fetch_52week_range(tuple(resolved_unique_tickers))

    df['live_price'] = df['resolved_ticker'].map(live_prices_map).fillna(0)
    df['share_name'] = df[ticker_col]
    df['high_52w'] = df['resolved_ticker'].map(lambda t: range_map.get(t, (0, 0))[0] if t else 0).fillna(0)
    df['low_52w'] = df['resolved_ticker'].map(lambda t: range_map.get(t, (0, 0))[1] if t else 0).fillna(0)

    if unresolved_entries:
        st.markdown(
            f'<div class="risk-warning">⚠️ <b>No Yahoo ticker could be found for {len(unresolved_entries)} compan(ies) below, so their live price shows as ₹0.</b><br>'
            'Type the exact Yahoo ticker next to each company (e.g. <code>TATAMOTORS.NS</code> for Tata Motors, <code>RELIANCE.NS</code> for Reliance) and click Save below. '
            'These will be remembered for next time too.</div>',
            unsafe_allow_html=True
        )
        with st.expander(f"✏️ Fix {len(unresolved_entries)} unresolved compan(ies) now", expanded=True):
            with st.form(key="fix_unresolved_form"):
                fix_inputs = {}
                for entry in unresolved_entries:
                    fcol1, fcol2 = st.columns([3, 2])
                    fcol1.write(entry)
                    fix_inputs[entry] = fcol2.text_input(
                        "Yahoo ticker", key=f"fix_{entry}", placeholder="e.g. TATAMOTORS.NS",
                        label_visibility="collapsed"
                    )
                submitted = st.form_submit_button("💾 Save All Tickers Entered Above", use_container_width=True)
                if submitted:
                    newly_saved = 0
                    for entry, ticker_val in fix_inputs.items():
                        ticker_val = ticker_val.strip()
                        if ticker_val:
                            st.session_state.manual_ticker_overrides[entry] = ticker_val.upper()
                            newly_saved += 1
                    if newly_saved > 0:
                        save_overrides(st.session_state.manual_ticker_overrides)
                        st.cache_data.clear()
                        st.success(f"✅ Saved {newly_saved} ticker(s). Refreshing data now...")
                        st.rerun()
                    else:
                        st.warning("No tickers were entered. Type at least one ticker before saving.")

    # Market stress test calculations
    df['Simulated_Live'] = df['live_price'] * (1 + (market_shock / 100))
    df['Current'] = df['quantity'] * df['Simulated_Live']
    df['PnL'] = df['Current'] - df['Invested']
    df['Returns_Pct'] = (df['PnL'] / df['Invested']) * 100
    df['Weight'] = (df['Invested'] / df['Invested'].sum()) * 100

    # Smart action alerts
    def calculate_action(row):
        if row['Returns_Pct'] >= target_pct: return f"🎯 TAKE PROFIT (+{target_pct}%)"
        elif row['Returns_Pct'] <= stop_loss_pct: return f"⚠️ STOP LOSS ({stop_loss_pct}%)"
        return "🟢 HOLD (Safe)"
    df['Action'] = df.apply(calculate_action, axis=1)

    # 52-week high/low proximity flags
    def calculate_52w_status(row):
        if row['high_52w'] and row['live_price'] >= row['high_52w']:
            return "📈 AT 52W HIGH"
        elif row['low_52w'] and row['live_price'] <= row['low_52w']:
            return "📉 AT 52W LOW"
        return ""
    df['Range_Status'] = df.apply(calculate_52w_status, axis=1)

    # Headline figures
    total_invested = df['Invested'].sum()
    total_current = df['Current'].sum()
    total_pnl = df['PnL'].sum()
    weighted_return = (total_pnl / total_invested) * 100 if total_invested > 0 else 0

    total_stocks = len(df)
    profit_stocks = (df['PnL'] > 0).sum()
    win_rate = (profit_stocks / total_stocks) * 100 if total_stocks > 0 else 0
    high_risk_stocks = df[df['Weight'] > 25]

    # Save today's portfolio snapshot for the history/trend chart (one row per day, overwritten on each refresh)
    append_history_snapshot(total_invested, total_current, total_pnl)

    # ---------------- EMAIL ALERT CHECK (runs every auto-refresh) ----------------
    if enable_email_alerts and sender_email_input and app_password_input and recipient_email_input:
        sent_any, alert_msgs = check_and_send_52week_alerts(
            df, sender_email_input, app_password_input, recipient_email_input, st.session_state.alerted_keys
        )
        if sent_any:
            for name, kind, ok, msg in alert_msgs:
                if ok:
                    st.toast(f"📧 Email sent: {name} hit {kind}", icon="✅")

    at_52w_now = df[df['Range_Status'] != ""]
    if not at_52w_now.empty:
        for _, row in at_52w_now.iterrows():
            css_class = "alert-box-high" if "HIGH" in row['Range_Status'] else "alert-box-low"
            st.markdown(f'<div class="{css_class}">{row["Range_Status"]}: <b>{row["share_name"]}</b> is currently at its 52-week {"high" if "HIGH" in row["Range_Status"] else "low"} (₹{row["live_price"]:,.2f}).</div>', unsafe_allow_html=True)

    # Quick filters logic
    df_filtered = df.copy()
    if stock_filter == "🟢 Profit Only":
        df_filtered = df[df['PnL'] > 0]
    elif stock_filter == "🔴 Loss Only":
        df_filtered = df[df['PnL'] <= 0]

    # ==================== MENU 1: OVERVIEW ====================
    if "Overview" in menu or "🖥️" in menu:
        st.caption(f"🔄 Live data auto-refreshes every 1 second. Last refreshed: {now_ist().strftime('%H:%M:%S')} IST")

        if market_shock != 0:
            st.info(f"⚠️ **Simulation Mode Active:** A {market_shock}% market change is being simulated.")

        if not high_risk_stocks.empty:
            for idx, row in high_risk_stocks.iterrows():
                st.markdown(f'<div class="risk-warning">⚠️ <b>Concentration Risk:</b> <b>{row["Weight"]:.1f}%</b> of total capital is in <b>{row["share_name"]}</b> alone.</div>', unsafe_allow_html=True)

        # ── Portfolio Health Score ──────────────────────────────────────────
        def calc_health_score(df_h):
            score = 0
            # 1. Diversification (max 25 pts): 10+ stocks = 25, 5-9 = 15, <5 = 5
            n = len(df_h['share_name'].unique())
            score += 25 if n >= 10 else (15 if n >= 5 else 5)
            # 2. Win rate (max 25 pts)
            wr = (df_h['PnL'] > 0).sum() / max(len(df_h),1) * 100
            score += min(25, int(wr / 4))
            # 3. Concentration (max 25 pts): no stock > 15% = 25, > 25% = 0
            max_w = df_h['Weight'].max()
            score += 25 if max_w < 15 else (15 if max_w < 25 else 0)
            # 4. Overall return (max 25 pts)
            ret = (df_h['PnL'].sum() / df_h['Invested'].sum() * 100) if df_h['Invested'].sum() > 0 else 0
            score += 25 if ret >= 15 else (18 if ret >= 5 else (10 if ret >= 0 else 0))
            return min(100, score)

        health = calc_health_score(df)
        health_color = "#3fb950" if health >= 70 else ("#e3b341" if health >= 45 else "#f85149")
        health_label = "Excellent 💪" if health >= 70 else ("Moderate ⚠️" if health >= 45 else "Needs Attention 🔴")

        st.markdown("<h4 style='color:#e6edf3; margin-bottom:10px;'>📈 Terminal Performance Matrix</h4>", unsafe_allow_html=True)

        # XIRR calculation
        xirr_value = None
        tx_df_for_xirr = st.session_state.get("transactions_df", pd.DataFrame())
        if not tx_df_for_xirr.empty:
            cashflows = []
            for _, r in tx_df_for_xirr.iterrows():
                amt = -(r['quantity'] * r['price']) if str(r['txn_type']).upper() == 'BUY' else (r['quantity'] * r['price'])
                cashflows.append((r['date'].to_pydatetime() if hasattr(r['date'], 'to_pydatetime') else r['date'], amt))
            cashflows.append((now_ist().replace(tzinfo=None), total_current))
            try:
                xirr_value = calculate_xirr(cashflows)
            except Exception:
                xirr_value = None

        kpi1, kpi2, kpi3, kpi4, kpi5, kpi6 = st.columns(6)
        kpi1.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL INVESTED</div><div class="metric-value">₹{total_invested:,.0f}</div><div class="metric-status-blue">● Net Asset Base</div></div>', unsafe_allow_html=True)
        kpi2.markdown(f'<div class="terminal-card"><div class="metric-title">CURRENT VALUE</div><div class="metric-value">₹{total_current:,.0f}</div><div class="metric-status-blue">Yahoo Live</div></div>', unsafe_allow_html=True)
        pnl_c = "#3fb950" if total_pnl >= 0 else "#f85149"
        kpi3.markdown(f'<div class="terminal-card"><div class="metric-title">UNREALIZED P&L</div><div class="metric-value" style="color:{pnl_c};">{"+" if total_pnl>=0 else ""}₹{total_pnl:,.0f}</div><div class="metric-status-blue">{weighted_return:+.2f}%</div></div>', unsafe_allow_html=True)
        kpi4.markdown(f'<div class="terminal-card"><div class="metric-title">WIN RATE</div><div class="metric-value" style="color:#58a6ff;">{win_rate:.1f}%</div><div class="metric-status-blue">{profit_stocks}G / {total_stocks-profit_stocks}L</div></div>', unsafe_allow_html=True)
        if xirr_value is not None:
            xc = "#3fb950" if xirr_value >= 0 else "#f85149"
            kpi5.markdown(f'<div class="terminal-card"><div class="metric-title">XIRR</div><div class="metric-value" style="color:{xc};">{xirr_value:.2f}%</div><div class="metric-status-blue">Annualized</div></div>', unsafe_allow_html=True)
        else:
            kpi5.markdown(f'<div class="terminal-card"><div class="metric-title">XIRR</div><div class="metric-value" style="color:#8b949e;font-size:13px;">Add trades<br>in Ledger</div></div>', unsafe_allow_html=True)
        kpi6.markdown(f'<div class="terminal-card"><div class="metric-title">HEALTH SCORE</div><div class="metric-value" style="color:{health_color};">{health}/100</div><div class="metric-status-blue">{health_label}</div></div>', unsafe_allow_html=True)

        if not df_filtered.empty:
            # ── Row 1: Bar chart + Pie ────────────────────────────────────
            col_left, col_right = st.columns([3, 2])
            with col_left:
                st.markdown("<h4>📊 Stock P&L Impact</h4>", unsafe_allow_html=True)
                df_bar = df_filtered.groupby('share_name', as_index=False).agg({'PnL':'sum','Invested':'sum'})
                df_bar = df_bar.sort_values('PnL')
                fig_bar = go.Figure(go.Bar(
                    x=df_bar['share_name'], y=df_bar['PnL'],
                    marker_color=['#3fb950' if v>=0 else '#f85149' for v in df_bar['PnL']],
                    text=df_bar['PnL'].apply(lambda x: f"₹{x:,.0f}"), textposition='auto'
                ))
                fig_bar.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10), xaxis=dict(showgrid=False, tickangle=-45), yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_bar, use_container_width=True)

            with col_right:
                st.markdown("<h4>📦 Asset Allocation</h4>", unsafe_allow_html=True)
                df_pie = df_filtered.groupby('share_name', as_index=False)['Invested'].sum()
                fig_pie = go.Figure(go.Pie(labels=df_pie['share_name'], values=df_pie['Invested'], hole=.55, hoverinfo="label+percent+value", textinfo="none"))
                fig_pie.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10), legend=dict(orientation="h", y=-0.15))
                st.plotly_chart(fig_pie, use_container_width=True)

            # ── Row 2: 52W Position Meter ─────────────────────────────────
            st.markdown("---")
            st.markdown("#### 📏 52-Week Price Position Meter")
            st.caption("Shows where each stock's current price sits within its 52-week Low → High range. Left = near low, Right = near high.")

            df_52 = df_filtered[df_filtered['high_52w'] > 0].copy()
            df_52 = df_52.groupby('share_name').agg({'live_price':'last','high_52w':'last','low_52w':'last','PnL':'sum'}).reset_index()
            df_52 = df_52[df_52['high_52w'] > df_52['low_52w']].copy()
            df_52['position_pct'] = ((df_52['live_price'] - df_52['low_52w']) / (df_52['high_52w'] - df_52['low_52w']) * 100).clip(0, 100)

            if not df_52.empty:
                for _, row52 in df_52.sort_values('position_pct').head(20).iterrows():
                    pos = row52['position_pct']
                    bar_color = "#f85149" if pos < 30 else ("#e3b341" if pos < 60 else "#3fb950")
                    pnl_txt = f"₹{row52['PnL']:+,.0f}"
                    name_short = row52['share_name'][:28] + "…" if len(row52['share_name']) > 30 else row52['share_name']
                    st.markdown(f"""
                    <div style='margin-bottom:6px;'>
                      <div style='display:flex; justify-content:space-between; font-size:12px; color:#8b949e; margin-bottom:2px;'>
                        <span><b style='color:#e6edf3;'>{name_short}</b> &nbsp; ₹{row52['live_price']:,.2f}</span>
                        <span>52W: ₹{row52['low_52w']:,.0f} — ₹{row52['high_52w']:,.0f} &nbsp; <b style='color:{"#3fb950" if row52["PnL"]>=0 else "#f85149"};'>{pnl_txt}</b></span>
                      </div>
                      <div style='background:#21262d; border-radius:4px; height:10px; position:relative;'>
                        <div style='width:{pos:.1f}%; background:{bar_color}; border-radius:4px; height:10px;'></div>
                        <div style='position:absolute; left:{pos:.1f}%; top:-2px; width:3px; height:14px; background:#fff; border-radius:2px;'></div>
                      </div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.info("52-week range data not available yet — it loads in the background.")

            # ── Row 3: Sector + History ──────────────────────────────────
            st.markdown("---")
            col_sec, col_hist = st.columns([2, 3])
            with col_sec:
                st.markdown("<h4>🏭 Sector Allocation</h4>", unsafe_allow_html=True)
                with st.spinner("Fetching sector data..."):
                    sector_map = fetch_sector_info(tuple(resolved_unique_tickers))
                df_sector = df_filtered.copy()
                df_sector['Sector'] = df_sector['resolved_ticker'].map(sector_map).fillna('Unknown')
                sec_grp = df_sector.groupby('Sector', as_index=False)['Invested'].sum().sort_values('Invested', ascending=False)
                fig_sec = go.Figure(go.Pie(labels=sec_grp['Sector'], values=sec_grp['Invested'], hole=.5, hoverinfo="label+percent+value", textinfo="percent"))
                fig_sec.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10), legend=dict(orientation="h", y=-0.2))
                st.plotly_chart(fig_sec, use_container_width=True)

            with col_hist:
                st.markdown("<h4>📈 Portfolio Value Trend</h4>", unsafe_allow_html=True)
                hist_data = load_history()
                if len(hist_data) < 2:
                    st.info("📊 Trend chart builds up day by day. Come back tomorrow to see it grow!")
                else:
                    fig_hist = go.Figure()
                    fig_hist.add_trace(go.Scatter(x=hist_data['date'], y=hist_data['total_current'], name='Current Value', line=dict(color='#58a6ff'), fill='tozeroy', fillcolor='rgba(88,166,255,0.06)'))
                    fig_hist.add_trace(go.Scatter(x=hist_data['date'], y=hist_data['total_invested'], name='Invested', line=dict(color='#8b949e', dash='dot')))
                    fig_hist.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10), xaxis=dict(gridcolor='#21262d'), yaxis=dict(gridcolor='#21262d', title='₹'), legend=dict(orientation="h", y=-0.2))
                    st.plotly_chart(fig_hist, use_container_width=True)

            # ── Row 4: Live Positions Table ───────────────────────────────
            st.markdown("---")
            st.markdown("<h4>📋 Live Positions</h4>", unsafe_allow_html=True)

            # Add % from 52W Low/High columns
            df_disp = df_filtered.copy()
            df_disp['From 52W Low'] = ((df_disp['Simulated_Live'] - df_disp['low_52w']) / df_disp['low_52w'].replace(0,1) * 100)
            df_disp['From 52W High'] = ((df_disp['Simulated_Live'] - df_disp['high_52w']) / df_disp['high_52w'].replace(0,1) * 100)

            display_df = df_disp[['share_name','resolved_ticker','quantity','buy_price','Simulated_Live','high_52w','low_52w','From 52W Low','From 52W High','Invested','Current','PnL','Returns_Pct','Action']].copy()
            display_df.columns = ['Stock','Yahoo Ticker','Qty','Buy ₹','Live ₹','52W High','52W Low','↑ from Low%','↓ from High%','Invested','Current','P&L (₹)','Return%','Signal']

            st.dataframe(
                display_df.style.format({
                    'Buy ₹':'₹{:,.2f}','Live ₹':'₹{:,.2f}',
                    '52W High':'₹{:,.2f}','52W Low':'₹{:,.2f}',
                    '↑ from Low%':'{:+.1f}%','↓ from High%':'{:+.1f}%',
                    'Invested':'₹{:,.0f}','Current':'₹{:,.0f}',
                    'P&L (₹)':'₹{:,.2f}','Return%':'{:+.2f}%'
                }).map(color_pnl, subset=['P&L (₹)','Return%']),
                use_container_width=True, height=380
            )

            # ── Row 5: Top 5 Holdings risk table ─────────────────────────
            st.markdown("---")
            t5col1, t5col2 = st.columns([1, 1])
            with t5col1:
                st.markdown("#### 🏆 Top 5 Holdings by Weight")
                top5 = df_filtered.groupby('share_name', as_index=False).agg({'Invested':'sum','Current':'sum','PnL':'sum','Weight':'sum'}).nlargest(5,'Weight')
                top5['Return%'] = (top5['PnL'] / top5['Invested'] * 100)
                st.dataframe(
                    top5[['share_name','Weight','Invested','Current','PnL','Return%']]
                    .rename(columns={'share_name':'Stock','Weight':'Weight%','Invested':'Invested ₹','Current':'Current ₹','PnL':'P&L ₹'})
                    .style.format({'Weight%':'{:.1f}%','Invested ₹':'₹{:,.0f}','Current ₹':'₹{:,.0f}','P&L ₹':'₹{:,.0f}','Return%':'{:+.1f}%'})
                    .map(color_pnl, subset=['P&L ₹','Return%']),
                    use_container_width=True, height=220
                )

            with t5col2:
                st.markdown("#### 📉 Drawdown from Buy Price")
                df_dd = df_filtered.copy()
                df_dd['Drawdown%'] = ((df_dd['Simulated_Live'] - df_dd['buy_price']) / df_dd['buy_price'].replace(0,1) * 100)
                df_dd_grp = df_dd.groupby('share_name', as_index=False).agg({'Drawdown%':'mean'}).sort_values('Drawdown%').head(10)
                fig_dd = go.Figure(go.Bar(
                    x=df_dd_grp['Drawdown%'], y=df_dd_grp['share_name'], orientation='h',
                    marker_color=['#f85149' if v < 0 else '#3fb950' for v in df_dd_grp['Drawdown%']],
                    text=df_dd_grp['Drawdown%'].apply(lambda v: f"{v:+.1f}%"), textposition='auto'
                ))
                fig_dd.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=10,b=10), xaxis=dict(gridcolor='#21262d',title='% Change'), yaxis=dict(gridcolor='#21262d'))
                st.plotly_chart(fig_dd, use_container_width=True)

            # ── Row 6: Tools ──────────────────────────────────────────────
            st.markdown("---")
            st.markdown("### 🛠️ Advanced Terminal Tools")
            tool_col1, tool_col2 = st.columns(2)
            with tool_col1:
                st.markdown("<h4>💸 Tax Liability Estimator</h4>", unsafe_allow_html=True)
                hold_duration = st.radio("Holding duration:", ["Less than 1 year (STCG)", "More than 1 year (LTCG)"], horizontal=True)
                if total_pnl > 0:
                    if "STCG" in hold_duration:
                        estimated_tax = total_pnl * 0.20
                        st.warning(f"💼 STCG Tax @20%: ₹{estimated_tax:,.2f}")
                    else:
                        taxable_pnl = max(0, total_pnl - 100000)
                        estimated_tax = taxable_pnl * 0.125
                        st.success(f"💼 LTCG Tax @12.5% (after ₹1L exemption): ₹{estimated_tax:,.2f}")
                else:
                    st.info("📉 Portfolio in loss — no tax applicable.")
            with tool_col2:
                st.markdown("<h4>📥 Export Report</h4>", unsafe_allow_html=True)
                st.write("Download the full live positions table as CSV.")
                st.download_button("📥 Download Portfolio Report (CSV)",
                    data=display_df.to_csv(index=False).encode('utf-8'),
                    file_name="AlphaPortfolio_Report.csv", mime="text/csv", use_container_width=True)
        else:
            st.warning("No data to display for selected filter.")

    # ==================== MENU 2: ADVANCED ANALYSIS ====================
    elif "Advanced Analysis" in menu or "📈" in menu:
        st.markdown("<h3>📊 Advanced Analysis & Performance Matrix</h3>", unsafe_allow_html=True)

        # ---- Realized vs Unrealized P&L split (from Transaction Ledger) ----
        st.markdown("<h4>💵 Realized vs Unrealized P&L</h4>", unsafe_allow_html=True)
        tx_df_adv = st.session_state.get("transactions_df", pd.DataFrame())
        if tx_df_adv.empty:
            st.info("💡 No transactions recorded yet. Visit the '💼 Transaction Ledger' tab to log your buys/sells and see Realized vs Unrealized P&L here.")
        else:
            realized_df_adv, _ = compute_fifo_realized_pnl(tx_df_adv)
            total_realized_adv = realized_df_adv['realized_pnl'].sum() if not realized_df_adv.empty else 0
            total_unrealized_adv = df['PnL'].sum()  # current holdings, from live portfolio file
            combined_pnl = total_realized_adv + total_unrealized_adv

            ru1, ru2, ru3 = st.columns(3)
            with ru1:
                rcolor = "#00ff66" if total_realized_adv >= 0 else "#ff3333"
                st.markdown(f'<div class="terminal-card"><div class="metric-title">REALIZED P&L (Sold Shares)</div><div class="metric-value" style="color:{rcolor};">₹ {total_realized_adv:,.2f}</div><div class="metric-status-blue">From Transaction Ledger</div></div>', unsafe_allow_html=True)
            with ru2:
                ucolor = "#00ff66" if total_unrealized_adv >= 0 else "#ff3333"
                st.markdown(f'<div class="terminal-card"><div class="metric-title">UNREALIZED P&L (Current Holdings)</div><div class="metric-value" style="color:{ucolor};">₹ {total_unrealized_adv:,.2f}</div><div class="metric-status-blue">From Uploaded Portfolio File</div></div>', unsafe_allow_html=True)
            with ru3:
                ccolor = "#00ff66" if combined_pnl >= 0 else "#ff3333"
                st.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL P&L (Realized + Unrealized)</div><div class="metric-value" style="color:{ccolor};">₹ {combined_pnl:,.2f}</div><div class="metric-status-blue">Overall Performance</div></div>', unsafe_allow_html=True)
            st.caption("⚠️ Note: Realized P&L comes from your manually-logged Transaction Ledger, while Unrealized P&L comes from your uploaded portfolio file — keep both updated for an accurate combined total.")

        st.markdown("---")

        best_stock = df.loc[df['Returns_Pct'].idxmax()]
        worst_stock = df.loc[df['Returns_Pct'].idxmin()]
        max_weight_stock = df.loc[df['Weight'].idxmax()]

        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">🔥 TOP GAINER (Alpha)</div><div class="metric-value" style="color: #00ff66;">{best_stock["share_name"]}</div><div class="metric-status-green">+{best_stock["Returns_Pct"]:.2f}%</div></div>', unsafe_allow_html=True)
        with ac2:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">⚠️ MAXIMUM UNDERPERFORMER</div><div class="metric-value" style="color: #ff3333;">{worst_stock["share_name"]}</div><div class="metric-status-red">{worst_stock["Returns_Pct"]:.2f}%</div></div>', unsafe_allow_html=True)
        with ac3:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">🏢 PORTFOLIO CONCENTRATION</div><div class="metric-value" style="color: #00bfff;">{max_weight_stock["share_name"]}</div><div class="metric-status-blue">Total Share: {max_weight_stock["Weight"]:.2f}%</div></div>', unsafe_allow_html=True)

        col_adv1, col_adv2 = st.columns([1, 1])
        with col_adv1:
            st.markdown("<h4>🗺️ Portfolio Heat-Map (Treemap)</h4>", unsafe_allow_html=True)
            df_tree = df.groupby('share_name', as_index=False).agg({'Invested': 'sum', 'PnL': 'sum'})
            df_tree['Returns_Pct'] = (df_tree['PnL'] / df_tree['Invested'].replace(0, 1)) * 100

            fig_tree = px.treemap(
                df_tree, path=['share_name'],
                values='Invested', color='Returns_Pct',
                color_continuous_scale='RdYlGn', color_continuous_midpoint=0, template="plotly_dark"
            )
            fig_tree.update_layout(margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='#0d1117')
            st.plotly_chart(fig_tree, use_container_width=True)

        with col_adv2:
            st.markdown("<h4>🔵 Risk vs Return Scatter Map</h4>", unsafe_allow_html=True)
            fig_scatter = px.scatter(df, x='Invested', y='Returns_Pct', size='quantity', color='PnL', hover_name='share_name', color_continuous_scale='RdYlGn', template="plotly_dark", size_max=40)
            fig_scatter.update_layout(plot_bgcolor='#161b22', paper_bgcolor='#0d1117', font=dict(color='#8b949e'), margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(title="Investment (₹)", gridcolor='#21262d'), yaxis=dict(title="Returns (%)", gridcolor='#21262d'))
            st.plotly_chart(fig_scatter, use_container_width=True)

    # ==================== MENU 3: SINGLE STOCK DEEP-DIVE ====================
    elif "Single Stock" in menu or "🔍" in menu:
        st.markdown("<h3>🔍 Single Stock Deep-Dive Analysis</h3>", unsafe_allow_html=True)
        selected_stock = st.selectbox("Select a stock to analyze:", sorted(df['share_name'].unique()))

        stock_rows = df[df['share_name'] == selected_stock]
        stock_data = stock_rows.iloc[0]
        total_qty   = stock_rows['quantity'].sum()
        total_inv   = stock_rows['Invested'].sum()
        avg_buy     = total_inv / total_qty if total_qty > 0 else 0
        total_cur   = stock_rows['Current'].sum()
        total_pnl_s = stock_rows['PnL'].sum()
        ret_pct_s   = (total_pnl_s / total_inv * 100) if total_inv > 0 else 0

        sc1,sc2,sc3,sc4,sc5,sc6 = st.columns(6)
        sc1.markdown(f'<div class="terminal-card"><div class="metric-title">AVG BUY PRICE</div><div class="metric-value">₹{avg_buy:,.2f}</div></div>', unsafe_allow_html=True)
        sc2.markdown(f'<div class="terminal-card"><div class="metric-title">LIVE PRICE</div><div class="metric-value">₹{stock_data["Simulated_Live"]:,.2f}</div></div>', unsafe_allow_html=True)
        sc3.markdown(f'<div class="terminal-card"><div class="metric-title">NET P&L</div><div class="metric-value" style="color:{"#3fb950" if total_pnl_s>=0 else "#f85149"};">₹{total_pnl_s:,.0f}</div></div>', unsafe_allow_html=True)
        sc4.markdown(f'<div class="terminal-card"><div class="metric-title">RETURN</div><div class="metric-value" style="color:{"#3fb950" if ret_pct_s>=0 else "#f85149"};">{ret_pct_s:+.2f}%</div></div>', unsafe_allow_html=True)
        sc5.markdown(f'<div class="terminal-card"><div class="metric-title">52W HIGH</div><div class="metric-value" style="color:#3fb950;">₹{stock_data["high_52w"]:,.2f}</div></div>', unsafe_allow_html=True)
        sc6.markdown(f'<div class="terminal-card"><div class="metric-title">52W LOW</div><div class="metric-value" style="color:#f85149;">₹{stock_data["low_52w"]:,.2f}</div></div>', unsafe_allow_html=True)

        # Live 1-year chart from Yahoo + buy price line
        resolved_tk = stock_data.get('resolved_ticker','')
        if resolved_tk:
            with st.spinner(f"Loading 1-year chart for {resolved_tk}..."):
                try:
                    hist_1y = yf.Ticker(resolved_tk).history(period="1y")
                except Exception:
                    hist_1y = pd.DataFrame()
            if not hist_1y.empty:
                fig_ss = go.Figure()
                fig_ss.add_trace(go.Scatter(
                    x=hist_1y.index, y=hist_1y['Close'],
                    name='Price', line=dict(color='#58a6ff', width=2),
                    fill='tozeroy', fillcolor='rgba(88,166,255,0.06)'
                ))
                fig_ss.add_hline(y=avg_buy, line_dash="dash", line_color="#e3b341",
                    annotation_text=f"Avg Buy ₹{avg_buy:,.2f}", annotation_position="top left",
                    annotation=dict(font=dict(color="#e3b341")))
                if stock_data['high_52w'] > 0:
                    fig_ss.add_hline(y=stock_data['high_52w'], line_dash="dot", line_color="#3fb950",
                        annotation_text=f"52W High ₹{stock_data['high_52w']:,.2f}", annotation_position="top right",
                        annotation=dict(font=dict(color="#3fb950")))
                    fig_ss.add_hline(y=stock_data['low_52w'], line_dash="dot", line_color="#f85149",
                        annotation_text=f"52W Low ₹{stock_data['low_52w']:,.2f}", annotation_position="bottom right",
                        annotation=dict(font=dict(color="#f85149")))
                fig_ss.update_layout(
                    plot_bgcolor='#161b22', paper_bgcolor='#0d1117',
                    font=dict(color='#8b949e'), margin=dict(l=10,r=10,t=40,b=10),
                    title=dict(text=f"{selected_stock} — 1-Year Price Chart", font=dict(color='#e6edf3',size=14)),
                    xaxis=dict(gridcolor='#21262d', color='#8b949e'),
                    yaxis=dict(gridcolor='#21262d', color='#8b949e', title='₹'),
                    showlegend=False
                )
                st.plotly_chart(fig_ss, use_container_width=True)

        # Gauge
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=ret_pct_s,
            delta={'reference': 0, 'valueformat': '.2f', 'suffix': '%'},
            domain={'x':[0,1],'y':[0,1]},
            title={'text': f"Overall Return — {selected_stock}", 'font':{'color':'#e6edf3'}},
            number={'suffix':'%','font':{'color':'#58a6ff'}},
            gauge={
                'axis':{'range':[-50,100],'tickcolor':'#8b949e'},
                'bar':{'color':'#58a6ff'},
                'steps':[
                    {'range':[-50,0],'color':'rgba(248,81,73,0.15)'},
                    {'range':[0,100],'color':'rgba(63,185,80,0.12)'}
                ],
                'threshold':{'line':{'color':'#e3b341','width':3},'thickness':0.75,'value':target_pct}
            }
        ))
        fig_gauge.update_layout(paper_bgcolor='#0d1117', font=dict(color='#8b949e'), margin=dict(l=20,r=20,t=50,b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)
else:
    st.info("💡 Terminal is ready! Please upload your file (CSV or Excel), or use the '🔎 Search Any Stock' tab in the sidebar to look up any stock without uploading a file.")
