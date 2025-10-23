import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import date

st.set_page_config(page_title="EquiScope Fundamentals Dashboard", layout="wide")

# -------------------------------------------------------
# 📌 CONFIG
# -------------------------------------------------------
INDEX_OPTIONS = {
    "S&P 500": "^GSPC",
    "NASDAQ 100": "^NDX"
}

# Default columns — easy to extend later
DEFAULT_COLUMNS = [
    "Ticker", "Company", "Market Cap", "Index Weight",
    "PE Ratio", "Profit Margin", "Revenue",
    "5Y Return", "3Y Return", "1Y Return", "IBO Score"
]

# -------------------------------------------------------
# 🧩 Helper Functions
# -------------------------------------------------------

@st.cache_data
def get_index_tickers(index_name):
    """Fetch list of tickers for an index (using Yahoo Finance)."""
    if index_name == "S&P 500":
        table = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
        return table["Symbol"].to_list(), table[["Symbol", "Security"]]
    elif index_name == "NASDAQ 100":
        table = pd.read_html("https://en.wikipedia.org/wiki/NASDAQ-100")[4]
        return table["Ticker"].to_list(), table[["Ticker", "Company"]]
    else:
        return [], pd.DataFrame()

@st.cache_data
def fetch_fundamentals(tickers):
    """Fetch basic financial data from yfinance."""
    data = []
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            hist = stock.history(period="5y")

            def total_return(period_days):
                if len(hist) < period_days:
                    return None
                start = hist["Close"].iloc[-period_days]
                end = hist["Close"].iloc[-1]
                return (end - start) / start

            data.append({
                "Ticker": ticker,
                "Company": info.get("shortName", ""),
                "Market Cap": info.get("marketCap", None),
                "Index Weight": None,  # Placeholder (can add true weight later)
                "PE Ratio": info.get("trailingPE", None),
                "Profit Margin": info.get("profitMargins", None),
                "Revenue": info.get("totalRevenue", None),
                "5Y Return": total_return(252*5),
                "3Y Return": total_return(252*3),
                "1Y Return": total_return(252*1),
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
        df = fetch_fundamentals(tickers)
        df = df.merge(tickermap, left_on="Ticker", right_on=tickermap.columns[0], how="left")
        df = df[DEFAULT_COLUMNS]
        df = df.sort_values(by="Market Cap", ascending=False, ignore_index=True)

        # --- Filtering Controls ---
        st.subheader("Table Filters")
        show_top_n = st.number_input("Show top N by IBO Score", min_value=5, max_value=100, value=30)
        # Placeholder: if IBO score existed, sort; otherwise, show largest market caps
        df_display = df.head(show_top_n)

        hide_cols = st.multiselect("Hide columns", [c for c in DEFAULT_COLUMNS if c not in ["Ticker", "Company"]])
        df_display = df_display.drop(columns=hide_cols)

        # --- Table ---
        st.dataframe(df_display, use_container_width=True)

        # --- Summary Stats ---
        st.caption(f"Data as of {reference_date.strftime('%Y-%m-%d')} (latest available from Yahoo Finance)")
