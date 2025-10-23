import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import date
import requests
from io import StringIO

st.set_page_config(page_title="EquiScope Fundamentals Dashboard", layout="wide")

# -------------------------------------------------------
# 📌 CONFIG
# -------------------------------------------------------
INDEX_OPTIONS = {
    "NASDAQ 100": "^NDX",
    "S&P 500": "^GSPC",
}

# Default columns — easy to extend later
DEFAULT_COLUMNS = [
    "Ticker", "Company", "Market Cap",
    "PE Ratio", "Profit Margin", "Revenue"
]

# -------------------------------------------------------
# 🧩 Helper Functions
# -------------------------------------------------------



@st.cache_data
def get_index_tickers(index_name):
    """Fetch list of tickers for an index (using Wikipedia as source)."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        if index_name == "S&P 500":
            url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
            html = requests.get(url, headers=headers).text
            table = pd.read_html(StringIO(html))[0]
            table.columns = [c.strip() for c in table.columns]
            return table["Symbol"].to_list(), table[["Symbol", "Security"]]

        elif index_name == "NASDAQ 100":
            url = "https://en.wikipedia.org/wiki/NASDAQ-100"
            html = requests.get(url, headers=headers).text
            table = pd.read_html(StringIO(html))[4]
            table.columns = [c.strip() for c in table.columns]
            return table["Ticker"].to_list(), table[["Ticker", "Company"]]

        else:
            return [], pd.DataFrame()

    except Exception as e:
        st.error(f"Error fetching tickers for {index_name}: {e}")
        return [], pd.DataFrame()

@st.cache_data
def fetch_fundamentals(tickers, tickermap, n=None):
    """
    Fetch key fundamentals and returns efficiently using yfinance bulk calls.
    """
    data = []

    # --- Bulk fetch for all tickers ---
    tickers_obj = yf.Tickers(" ".join(tickers))

    # --- Bulk price history (for returns) ---
    price_hist = yf.download(tickers, period="5y", group_by="ticker", progress=False)

    for i in range(len(tickers)):
        try:
            symbol = tickers[i]
            company = tickermap["Company"].iloc[i]
            info = tickers_obj.tickers[symbol].info
            hist = price_hist[symbol]
            current_val = hist["Close"].iloc[-1]
            data.append({
                "Ticker": symbol,
                "Company":company,
                "Market Cap": info.get("marketCap", None),
                "Index Weight": None,  # Placeholder (can add true weight later)
                "PE Ratio": info.get("trailingPE", None),
                "Profit Margin": info.get("profitMargins", None),
                "Revenue": info.get("totalRevenue", None),
                "5Y Return": (current_val/ hist["Close"].iloc[0] - 1) if len(hist) >= 20 else None,
                "3Y Return": (current_val / hist["Close"].iloc[-12] - 1) if len(hist) >= 12 else None,
                "1Y Return": (current_val / hist["Close"].iloc[-4] - 1) if len(hist) >= 4 else None,
                "IBO Score": None  # Placeholder for custom metric
            })
        except Exception:
            continue
    df = pd.DataFrame(data)
    return df

# -------------------------------------------------------
# 🖥️ Streamlit UI
# -------------------------------------------------------

st.title("📊 Fundalytics — Index Fundamentals Dashboard")

# --- Inputs ---
col1, col2 = st.columns([1, 1])

with col1:
    index_choice = st.selectbox("Select Index", list(INDEX_OPTIONS.keys()))

with col2:
    reference_date = st.date_input(
        "Select Reference Date (Quarter End, last 3 years)",
        value=date.today(),
        min_value=date(date.today().year - 3, 1, 1),
        max_value=date.today()
    )

tickers, tickermap = get_index_tickers(index_choice)

st.info(f"Loaded {len(tickers)} tickers for {index_choice}.")

# --- Fetch Data Button ---
if st.button("Load Fundamentals"):
    with st.spinner("Fetching data... this may take a minute"):
        df = fetch_fundamentals(tickers, tickermap)
        df = df.sort_values(by="Market Cap", ascending=False, ignore_index=True)

        # --- Filtering Controls ---
        st.subheader("Fundamentals")

        # --- Table ---
        st.dataframe(df, use_container_width=True)

        # --- Summary Stats ---
        st.caption(f"Data as of {reference_date.strftime('%Y-%m-%d')} (latest available from Yahoo Finance)")
