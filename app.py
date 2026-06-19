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

# 1. PAGE CONFIG + PREMIUM DARK THEME
st.set_page_config(page_title="AlphaPortfolio Terminal Pro+", layout="wide", initial_sidebar_state="expanded")

# Premium neon UI styling
st.markdown("""
    <style>
    .stApp {background-color: #080c10; color: #e1e7ed;}

    .terminal-card {
        background: linear-gradient(135deg, #0f141c 0%, #0b0f15 100%);
        padding: 20px;
        border-radius: 8px;
        border: 1px solid #1f2937;
        box-shadow: 0 4px 25px rgba(0, 0, 0, 0.5);
        margin-bottom: 15px;
    }
    .metric-title { font-size: 11px; color: #76808c; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; }
    .metric-value { font-size: 24px; color: #ffffff; font-weight: 700; margin-top: 5px; font-family: 'Courier New', monospace; }
    .metric-status-green { color: #00ff66; font-size: 12px; font-weight: 600; margin-top: 5px; }
    .metric-status-red { color: #ff3333; font-size: 12px; font-weight: 600; margin-top: 5px; }
    .metric-status-blue { color: #00bfff; font-size: 12px; font-weight: 600; margin-top: 5px; }

    .risk-warning {
        background-color: rgba(255, 51, 51, 0.1);
        border: 1px solid #ff3333;
        padding: 12px;
        border-radius: 6px;
        color: #ff9999;
        margin-bottom: 15px;
        font-size: 13px;
    }

    .map-box {
        background-color: #0f141c;
        padding: 15px;
        border-radius: 8px;
        border: 1px dashed #00bfff;
        margin-bottom: 20px;
    }

    .alert-box-high {
        background-color: rgba(0, 255, 102, 0.1);
        border: 1px solid #00ff66;
        padding: 10px;
        border-radius: 6px;
        color: #b6ffd1;
        margin-bottom: 10px;
        font-size: 13px;
    }
    .alert-box-low {
        background-color: rgba(255, 51, 51, 0.1);
        border: 1px solid #ff3333;
        padding: 10px;
        border-radius: 6px;
        color: #ff9999;
        margin-bottom: 10px;
        font-size: 13px;
    }

    [data-testid="stSidebar"] { background-color: #0b0f15; border-right: 1px solid #1f2937; }
    </style>
    """, unsafe_allow_html=True)

# ===================================================================
# AUTO-REFRESH: refresh live data every 60 seconds
# ===================================================================
st_autorefresh(interval=60 * 1000, key="live_price_autorefresh")

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
            hist = stock.history(period="1d")
            if not hist.empty:
                prices_dict[ticker] = hist['Close'].iloc[-1]
            else:
                prices_dict[ticker] = 0
        except Exception:
            prices_dict[ticker] = 0
    return prices_dict


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


# Session state init
if "alerted_keys" not in st.session_state:
    st.session_state.alerted_keys = set()
if "manual_ticker_overrides" not in st.session_state:
    st.session_state.manual_ticker_overrides = load_overrides()  # load any previously saved overrides from disk

# ==================== SIDEBAR (TERMINAL CONTROLS) ====================
with st.sidebar:
    st.markdown("<h2 style='color: #00bfff; text-align: center; font-family: monospace;'>ALPHA TERMINAL</h2>", unsafe_allow_html=True)
    st.markdown("---")
    menu = st.radio("⚡ Terminal Monitor", [
        "🖥️ Overview Dashboard",
        "📈 Advanced Analysis",
        "🔍 Single Stock Matrix",
        "🔎 Search Any Stock"
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
if "Search Any Stock" in menu or "🔎" in menu:
    st.markdown("<h3>🔎 Search Any Stock</h3>", unsafe_allow_html=True)
    st.caption("Type a company name (e.g. 'Tata Motors') or a ticker (e.g. 'AAPL', 'INFY.NS') to get its live price and 52-week range — independent of your uploaded portfolio.")

    search_query = st.text_input("Company name or ticker:", placeholder="e.g. Reliance, Apple, INFY.NS")

    if search_query:
        with st.spinner(f"Searching for '{search_query}'..."):
            result = search_any_stock(search_query)

        if result is None:
            st.error(f"⚠️ Could not find a matching stock for '{search_query}'. Try the exact Yahoo ticker instead (e.g. TCS.NS).")
        else:
            st.markdown(f"#### {result['company_name']} ({result['ticker']})")
            sc1, sc2, sc3 = st.columns(3)
            with sc1:
                st.markdown(f'<div class="terminal-card"><div class="metric-title">LIVE PRICE</div><div class="metric-value">{result["currency"]} {result["live_price"]:,.2f}</div></div>', unsafe_allow_html=True)
            with sc2:
                high_txt = f'{result["currency"]} {result["high_52w"]:,.2f}' if result["high_52w"] else "N/A"
                st.markdown(f'<div class="terminal-card"><div class="metric-title">52-WEEK HIGH</div><div class="metric-value" style="color:#00ff66;">{high_txt}</div></div>', unsafe_allow_html=True)
            with sc3:
                low_txt = f'{result["currency"]} {result["low_52w"]:,.2f}' if result["low_52w"] else "N/A"
                st.markdown(f'<div class="terminal-card"><div class="metric-title">52-WEEK LOW</div><div class="metric-value" style="color:#ff3333;">{low_txt}</div></div>', unsafe_allow_html=True)

            if not result["history"].empty:
                fig_search = go.Figure(data=[go.Scatter(x=result["history"].index, y=result["history"]['Close'], line=dict(color='#00bfff'))])
                fig_search.update_layout(
                    plot_bgcolor='#0b0f15', paper_bgcolor='#080c10', font=dict(color='#76808c'),
                    margin=dict(l=10, r=10, t=30, b=10), title="1-Year Price Trend",
                    xaxis=dict(gridcolor='#1f2937'), yaxis=dict(gridcolor='#1f2937')
                )
                st.plotly_chart(fig_search, use_container_width=True)
    else:
        st.info("💡 Enter a company name or ticker above to see its live price and 52-week range.")

elif not df.empty:
    # Strip whitespace from column names
    df.columns = df.columns.str.strip()
    all_columns = list(df.columns)

    # Manual Column Mapping interface
    st.markdown('<div class="map-box">🗺️ <b>Portfolio Column Mapping</b><br><small style="color:#76808c;">Select the correct columns from your file so the system can calculate accurately.</small></div>', unsafe_allow_html=True)

    map_col1, map_col2, map_col3 = st.columns(3)

    with map_col1:
        ticker_col = st.selectbox("🌐 Yahoo Symbol (Ticker) column:", all_columns, index=0)

    with map_col2:
        qty_options = ['quantity', 'qty', 'volume', 'shares']
        default_qty_idx = next((i for i, c in enumerate(all_columns) if c.lower() in qty_options), 0)
        qty_col = st.selectbox("📦 Quantity column:", all_columns, index=default_qty_idx)

    with map_col3:
        price_options = ['buy_price', 'buy price', 'avg_price', 'avg price', 'rate', 'price']
        default_price_idx = next((i for i, c in enumerate(all_columns) if c.lower() in price_options), min(2, len(all_columns)-1))
        price_col = st.selectbox("💰 Buy Price column:", all_columns, index=default_price_idx)

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
        st.caption(f"🔄 Live data auto-refreshes every 60 seconds. Last refreshed: {now_ist().strftime('%H:%M:%S')} IST")

        if market_shock != 0:
            st.info(f"⚠️ **Simulation Mode Active:** A {market_shock}% market change is being simulated.")

        if not high_risk_stocks.empty:
            for idx, row in high_risk_stocks.iterrows():
                st.markdown(f'<div class="risk-warning">⚠️ **Concentration Risk Alert:** **{row["Weight"]:.1f}%** of your total capital is invested in **{row["share_name"]}** alone.</div>', unsafe_allow_html=True)

        st.markdown("<h4 style='color: #76808c; margin-bottom: 10px;'>📈 Terminal Performance Matrix</h4>", unsafe_allow_html=True)

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        with kpi1:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">TOTAL CAPITAL INVESTED</div><div class="metric-value">₹ {total_invested:,.2f}</div><div class="metric-status-blue">● Net Asset Base</div></div>', unsafe_allow_html=True)
        with kpi2:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">CURRENT VALUE (YAHOO)</div><div class="metric-value">₹ {total_current:,.2f}</div><div class="metric-status-blue">Yahoo Real-time Synced</div></div>', unsafe_allow_html=True)
        with kpi3:
            pnl_color_class = "metric-status-green" if total_pnl >= 0 else "metric-status-red"
            pnl_sign = "+" if total_pnl >= 0 else ""
            st.markdown(f'<div class="terminal-card"><div class="metric-title">WEIGHTED RETURNS</div><div class="metric-value" style="color: {"#00ff66" if total_pnl >= 0 else "#ff3333"}">{pnl_sign}{weighted_return:.2f}%</div><div class="{pnl_color_class}">PnL: ₹ {total_pnl:,.2f}</div></div>', unsafe_allow_html=True)
        with kpi4:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">PORTFOLIO WIN RATE</div><div class="metric-value" style="color: #00bfff;">{win_rate:.1f}%</div><div class="metric-status-blue">{profit_stocks} Gainer / {total_stocks - profit_stocks} Loser</div></div>', unsafe_allow_html=True)

        if not df_filtered.empty:
            col_left, col_right = st.columns([3, 2])
            with col_left:
                st.markdown("<h4>📊 Stock Performance Chart (Net PnL Impact)</h4>", unsafe_allow_html=True)
                colors = ['#00ff66' if val >= 0 else '#ff3333' for val in df_filtered['PnL']]
                fig_bar = go.Figure(data=[go.Bar(x=df_filtered['share_name'], y=df_filtered['PnL'], marker_color=colors, text=df_filtered['PnL'].apply(lambda x: f"₹{x:,.0f}"), textposition='auto')])
                fig_bar.update_layout(plot_bgcolor='#0b0f15', paper_bgcolor='#080c10', font=dict(color='#76808c'), margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(showgrid=False), yaxis=dict(gridcolor='#1f2937'))
                st.plotly_chart(fig_bar, use_container_width=True)

            with col_right:
                st.markdown("<h4>📦 Asset Allocation Weightage (Weight %)</h4>", unsafe_allow_html=True)
                fig_pie = go.Figure(data=[go.Pie(labels=df_filtered['share_name'], values=df_filtered['Invested'], hole=.6, hoverinfo="label+percent+value", textinfo="none")])
                fig_pie.update_layout(plot_bgcolor='#0b0f15', paper_bgcolor='#080c10', font=dict(color='#76808c'), margin=dict(l=10, r=10, t=10, b=10), legend=dict(orientation="h", y=-0.1))
                st.plotly_chart(fig_pie, use_container_width=True)

            st.markdown("<h4>📋 Live Positions (Yahoo Synced Price)</h4>", unsafe_allow_html=True)
            display_df = df_filtered[['share_name', 'resolved_ticker', 'quantity', 'buy_price', 'Simulated_Live', 'high_52w', 'low_52w', 'Invested', 'Current', 'PnL', 'Returns_Pct', 'Action']].copy()
            display_df.columns = ['Stock Name', 'Yahoo Ticker', 'Quantity', 'Buy Price', 'Live Price (Sim)', '52W High', '52W Low', 'Total Invested', 'Current Value', 'PnL (₹)', 'Returns (%)', 'Terminal Signal/Action']

            st.dataframe(display_df.style.format({
                'Buy Price': '₹{:,.2f}', 'Live Price (Sim)': '₹{:,.2f}',
                '52W High': '₹{:,.2f}', '52W Low': '₹{:,.2f}',
                'Total Invested': '₹{:,.2f}', 'Current Value': '₹{:,.2f}',
                'PnL (₹)': '₹{:,.2f}', 'Returns (%)': '{:.2f}%'
            }).map(color_pnl, subset=['PnL (₹)', 'Returns (%)']), use_container_width=True, height=350)

            # ---- Advanced Tools ----
            st.markdown("---")
            st.markdown("### 🛠️ Advanced Terminal Tools")
            tool_col1, tool_col2 = st.columns([1, 1])

            with tool_col1:
                st.markdown("<h4>💸 Tax Liability Estimator (Tentative Tax)</h4>", unsafe_allow_html=True)
                hold_duration = st.radio("Select holding duration:", ["Less than 1 year (STCG)", "More than 1 year (LTCG)"], horizontal=True)
                if total_pnl > 0:
                    if "STCG" in hold_duration:
                        estimated_tax = total_pnl * 0.20
                        st.warning(f"💼 Estimated Short-Term Tax (STCG @20%): ₹ {estimated_tax:,.2f}")
                    else:
                        taxable_pnl = max(0, total_pnl - 100000)
                        estimated_tax = taxable_pnl * 0.125
                        st.success(f"💼 Estimated Long-Term Tax (LTCG @12.5%): ₹ {estimated_tax:,.2f} (after ₹1 lakh exemption)")
                else:
                    st.info("📉 Portfolio is currently in loss, so no tax is applicable.")

            with tool_col2:
                st.markdown("<h4>📥 Terminal Report Export</h4>", unsafe_allow_html=True)
                st.write("Save the current Yahoo Finance data and system signals as an Excel (CSV) file.")
                csv_data = display_df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Download Exported Report (CSV)",
                    data=csv_data,
                    file_name="AlphaPortfolio_Yahoo_Report.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        else:
            st.warning("No data available to display for the selected filter.")

    # ==================== MENU 2: ADVANCED ANALYSIS ====================
    elif "Advanced Analysis" in menu or "📈" in menu:
        st.markdown("<h3>📊 Advanced Analysis & Performance Matrix</h3>", unsafe_allow_html=True)

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
            fig_tree.update_layout(margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor='#080c10')
            st.plotly_chart(fig_tree, use_container_width=True)

        with col_adv2:
            st.markdown("<h4>🔵 Risk vs Return Scatter Map</h4>", unsafe_allow_html=True)
            fig_scatter = px.scatter(df, x='Invested', y='Returns_Pct', size='quantity', color='PnL', hover_name='share_name', color_continuous_scale='RdYlGn', template="plotly_dark", size_max=40)
            fig_scatter.update_layout(plot_bgcolor='#0b0f15', paper_bgcolor='#080c10', font=dict(color='#76808c'), margin=dict(l=10, r=10, t=10, b=10), xaxis=dict(title="Investment (₹)", gridcolor='#1f2937'), yaxis=dict(title="Returns (%)", gridcolor='#1f2937'))
            st.plotly_chart(fig_scatter, use_container_width=True)

    # ==================== MENU 3: SINGLE STOCK DEEP-DIVE ====================
    elif "Single Stock" in menu or "🔍" in menu:
        st.markdown("<h3>🔍 Single Stock Deep-Dive Analysis</h3>", unsafe_allow_html=True)
        selected_stock = st.selectbox("Select a stock to analyze:", df['share_name'].unique())

        stock_data = df[df['share_name'] == selected_stock].iloc[0]

        sc1, sc2, sc3, sc4, sc5, sc6 = st.columns(6)
        with sc1:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">Buy Price</div><div class="metric-value">₹ {stock_data["buy_price"]:,.2f}</div></div>', unsafe_allow_html=True)
        with sc2:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">Yahoo Live Price</div><div class="metric-value">₹ {stock_data["Simulated_Live"]:,.2f}</div></div>', unsafe_allow_html=True)
        with sc3:
            s_color = "#00ff66" if stock_data["PnL"] >= 0 else "#ff3333"
            st.markdown(f'<div class="terminal-card"><div class="metric-title">Net PnL</div><div class="metric-value" style="color: {s_color}">₹ {stock_data["PnL"]:,.2f}</div></div>', unsafe_allow_html=True)
        with sc4:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">Portfolio Weight</div><div class="metric-value" style="color: #00bfff;">{stock_data["Weight"]:.2f}%</div></div>', unsafe_allow_html=True)
        with sc5:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">52-Week High</div><div class="metric-value" style="color: #00ff66;">₹ {stock_data["high_52w"]:,.2f}</div></div>', unsafe_allow_html=True)
        with sc6:
            st.markdown(f'<div class="terminal-card"><div class="metric-title">52-Week Low</div><div class="metric-value" style="color: #ff3333;">₹ {stock_data["low_52w"]:,.2f}</div></div>', unsafe_allow_html=True)

        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = stock_data['Returns_Pct'],
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': f"{selected_stock} Overall Returns (%)", 'font': {'color': "#ffffff"}},
            gauge = {
                'axis': {'range': [-50, 100], 'tickcolor': "#76808c"},
                'bar': {'color': "#00bfff"},
                'steps': [
                    {'range': [-50, 0], 'color': "rgba(255, 51, 51, 0.2)"},
                    {'range': [0, 100], 'color': "rgba(0, 255, 102, 0.2)"}
                ],
                'threshold': {
                    'line': {'color': "red", 'width': 4},
                    'thickness': 0.75,
                    'value': target_pct
                }
            }
        ))
        fig_gauge.update_layout(paper_bgcolor='#080c10', font=dict(color='#76808c'), margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)
else:
    st.info("💡 Terminal is ready! Please upload your file (CSV or Excel), or use the '🔎 Search Any Stock' tab in the sidebar to look up any stock without uploading a file.")
