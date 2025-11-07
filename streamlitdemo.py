import streamlit as st
import pandas as pd
import numpy as np
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from st_supabase_connection import SupabaseConnection, execute_query
from supabase import create_client

st.set_page_config(page_title="Fundalytix", layout="wide")
st.title("Stocks & Fundamentals — Reference-date metrics")

# ----------------------
# read secrets
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

# create supabase client
supabase = create_client(url, key)

# ----------------------
# Helpers to fetch data
# ----------------------
def load_stocks():
    resp = supabase.table("stocks").select("*").execute()
    return resp

@st.cache_data(ttl=300)  # cache for 5 minutes
def load_fundamentals_upto(ref_date: datetime.date) -> pd.DataFrame:
    # supabase expects ISO date strings for filtering
    ref_date_str = ref_date.isoformat()

    # PostgREST-style query: select, filter reported_date <= ref_date, order
    resp = (
        supabase
        .table("fundamentals_raw")
        .select("ticker,reported_date,field,value")
        .lte("reported_date", ref_date_str)
        .order("ticker")
        .order("reported_date")  # descending per ticker
        .execute()
    )
    return resp

def load_prices_since(start_date: datetime.date, end_date: datetime.date) -> pd.DataFrame:
    # supabase expects ISO date strings for filtering
    start_date_str = start_date.isoformat()
    end_date_str = end_date.isoformat()
    resp = (
        supabase
        .table("prices_daily_raw")
        .select("ticker,dt,close")
        .gte("dt", start_date_str)
        .lte("dt", end_date_str)
        .order("ticker")
        .order("dt")
        .execute()
    )
    return resp


# Perform query.
rows = load_stocks()
# Print results.
for row in rows.data:
    st.write(f"{row['ticker']} means :{row['name']}:")

fundamentals = load_fundamentals_upto(datetime.today().date())
st.write(f"Loaded {len(fundamentals)} fundamentals records.")

prices = load_prices_since(datetime.today().date() - timedelta(days=2), datetime.today().date())
st.write(f"Loaded {len(prices)} price records.")


# ----------------------
# Database connection
# ----------------------
# def get_engine():
#     # Prefer a single URI in secrets: st.secrets['db_uri']
#     # Alternatively provide host/db/user/password in secrets:
#     if "db_uri" in st.secrets:
#         uri = st.secrets["db_uri"]
#     else:
#         required = ["host", "port", "dbname", "user", "password"]
#         if all(k in st.secrets for k in required):
#             uri = (
#                 f"postgresql+psycopg2://{st.secrets['user']}:{st.secrets['password']}@"
#                 f"{st.secrets['host']}:{st.secrets['port']}/{st.secrets['dbname']}"
#             )
#         else:
#             st.error("Please set your DB connection in Streamlit secrets as `db_uri` or host/port/dbname/user/password")
#             st.stop()
#     return create_engine(uri)

# engine = get_engine()



# ----------------------
# Metric calculation helpers
# ----------------------

def pivot_latest_quarter(fund_df, ref_date):
    """For each ticker select the latest reported_date <= ref_date and pivot fields wide."""
    if fund_df.empty:
        return pd.DataFrame()
    # For each ticker get max reported_date
    fund_df["reported_date"] = pd.to_datetime(fund_df["reported_date"]).dt.date
    latest = (
        fund_df.groupby("ticker")["reported_date"].max().reset_index().rename(columns={"reported_date": "rd"})
    )
    merged = latest.merge(fund_df, left_on=["ticker", "rd"], right_on=["ticker", "reported_date"], how="left")
    wide = merged.pivot(index="ticker", columns="field", values="value")
    wide.columns.name = None
    return wide.reset_index()


def get_price_on_or_before(prices_df, ticker, target_date):
    # prices_df has dt as date
    sub = prices_df[prices_df["ticker"] == ticker]
    sub = sub.sort_values("dt")
    sub = sub[sub["dt"] <= target_date]
    if sub.empty:
        return np.nan, None
    row = sub.iloc[-1]
    return float(row["close"]), row["dt"]


def pct_change_from(prices_df, ticker, base_date, lookback_days):
    base_price, base_found = get_price_on_or_before(prices_df, ticker, base_date)
    if np.isnan(base_price):
        return np.nan
    target_date = base_date - timedelta(days=lookback_days)
    tgt_price, tgt_found = get_price_on_or_before(prices_df, ticker, target_date)
    if np.isnan(tgt_price):
        return np.nan
    return (base_price / tgt_price - 1) * 100

# ----------------------
# UI: reference date
# ----------------------
ref_date = st.date_input("Reference date", value=datetime.today().date())
st.write(f"Using reference date: {ref_date}")

# Load data ranges: to compute price returns up to 5y we need up to ref_date - 6y to be safe
max_lookback_days = 365 * 6
start_date = ref_date - timedelta(days=max_lookback_days)
prices = load_prices_since(start_date, ref_date)
funds = load_fundamentals_upto(ref_date)
stocks = load_stocks()

# Prepare fundamentals snapshot (latest quarter per ticker)
funds_latest = pivot_latest_quarter(funds, ref_date)

# For growth calculations we need values ~1y and ~5y prior to ref_date
# We'll extract the latest reported_date <= ref_date - 365 and <= ref_date - 5*365
funds["reported_date"] = pd.to_datetime(funds["reported_date"]).dt.date

def snapshot_at_offset(offset_days):
    cutoff = ref_date - timedelta(days=offset_days)
    df = funds[funds["reported_date"] <= cutoff]
    if df.empty:
        return pd.DataFrame()
    latest = (
        df.groupby("ticker")["reported_date"].max().reset_index().rename(columns={"reported_date": "rd"})
    )
    merged = latest.merge(df, left_on=["ticker", "rd"], right_on=["ticker", "reported_date"], how="left")
    wide = merged.pivot(index="ticker", columns="field", values="value")
    wide.columns.name = None
    return wide.reset_index()

funds_1y = snapshot_at_offset(365)
funds_5y = snapshot_at_offset(365*5)

# Merge snapshots
metrics = stocks[["ticker", "name", "sector", "industry"]].copy()
metrics = metrics.merge(funds_latest, on="ticker", how="left")

# Price-based performance columns
perf_cols = {
    "1M": 30,
    "3M": 90,
    "6M": 182,
    "1Y": 365,
    "5Y": 365*5,
}

for col, days in perf_cols.items():
    metrics[col + " %"] = metrics["ticker"].apply(lambda t: pct_change_from(prices, t, ref_date, days))

# Fundamentals metrics
# Net Margin = net_income / revenue
metrics["Net Margin"] = metrics.apply(lambda r: (r.get("net_income") / r.get("revenue") * 100)
                                       if pd.notna(r.get("net_income")) and pd.notna(r.get("revenue")) and r.get("revenue") != 0 else np.nan, axis=1)

# Revenue growth 1y and 5y
def growth(cur, prev):
    if pd.isna(cur) or pd.isna(prev) or prev == 0:
        return np.nan
    return (cur / prev - 1) * 100

# bring revenue from funds_1y and funds_5y
metrics = metrics.merge(funds_1y[["ticker", "revenue"]].rename(columns={"revenue": "revenue_1y"}), on="ticker", how="left")
metrics = metrics.merge(funds_5y[["ticker", "revenue"]].rename(columns={"revenue": "revenue_5y"}), on="ticker", how="left")
metrics["Revenue growth (1y) %"] = metrics.apply(lambda r: growth(r.get("revenue"), r.get("revenue_1y")), axis=1)
metrics["Revenue growth (5y) %"] = metrics.apply(lambda r: growth(r.get("revenue"), r.get("revenue_5y")), axis=1)

# Earnings growth (use net_income if available, else eps_basic)
metrics = metrics.merge(funds_1y[["ticker", "net_income", "eps_basic"]].rename(columns={"net_income": "net_income_1y", "eps_basic": "eps_basic_1y"}), on="ticker", how="left")
metrics = metrics.merge(funds_5y[["ticker", "net_income", "eps_basic"]].rename(columns={"net_income": "net_income_5y", "eps_basic": "eps_basic_5y"}), on="ticker", how="left")

metrics["Earnings growth (1y) %"] = metrics.apply(
    lambda r: growth(r.get("net_income"), r.get("net_income_1y")) if pd.notna(r.get("net_income")) and pd.notna(r.get("net_income_1y"))
    else growth(r.get("eps_basic"), r.get("eps_basic_1y")), axis=1)
metrics["Earnings growth (5y) %"] = metrics.apply(
    lambda r: growth(r.get("net_income"), r.get("net_income_5y")) if pd.notna(r.get("net_income")) and pd.notna(r.get("net_income_5y"))
    else growth(r.get("eps_basic"), r.get("eps_basic_5y")), axis=1)

# CASH-C / DEBT-D: use cash_on_hand / long_term_debt if available (cash-to-debt)
metrics["Cash_to_Debt"] = metrics.apply(lambda r: (r.get("cash_on_hand") / r.get("long_term_debt"))
                                         if pd.notna(r.get("cash_on_hand")) and pd.notna(r.get("long_term_debt")) and r.get("long_term_debt") != 0 else np.nan, axis=1)

# FPE (Forward P/E) -- we cannot compute analyst forward EPS; we approximate using trailing 12 months EPS if available
# We'll compute simple Trailing P/E using price / (eps_basic * shares) approximation if eps_basic is per-share
# Note: this is a best-effort approximation. If you have forward EPS estimates store them in fundamentals_raw and rename field 'eps_forward' etc.

# get price per ticker at ref_date
price_map = {}
for t in metrics["ticker"]:
    p, _ = get_price_on_or_before(prices, t, ref_date)
    price_map[t] = p
metrics["Price"] = metrics["ticker"].map(price_map)

# Trailing EPS: eps_basic assumed to be per-share. Trailing P/E = Price / eps_basic
metrics["FPE (approx)"] = metrics.apply(lambda r: (r.get("Price") / r.get("eps_basic")) if pd.notna(r.get("Price")) and pd.notna(r.get("eps_basic")) and r.get("eps_basic") != 0 else np.nan, axis=1)

# 1Y growth % (we'll show revenue growth 1y)
metrics["1Y growth%"] = metrics["Revenue growth (1y) %"]

# Select and format columns for display
display_cols = ["ticker", "name", "sector", "industry",
                "1M %", "3M %", "6M %", "1Y %", "5Y %",
                "Net Margin", "FPE (approx)", "Revenue growth (1y) %", "Revenue growth (5y) %",
                "Earnings growth (1y) %", "Earnings growth (5y) %", "Cash_to_Debt", "1Y growth%", "Price"]

out = metrics[display_cols].copy()
# round numeric
for c in out.columns:
    if out[c].dtype in ["float64", "int64"]:
        out[c] = out[c].round(2)

st.write("### Metrics table")
st.dataframe(out.set_index("ticker"), use_container_width=True)

st.download_button("Download CSV", out.to_csv(index=False), file_name=f"metrics_{ref_date}.csv")

st.info(
    "Notes: IBD Rating is a proprietary metric (Investor's Business Daily) and is not available from your DB unless you store it.\n"
    "FPE here is approximated as Price / eps_basic (trailing) if eps_basic is present. For true forward P/E you need forward EPS estimates.\n"
    "Cash_to_Debt uses cash_on_hand / long_term_debt."
)

# small summary cards
st.write("### Quick summary")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Universe size", len(out))
with col2:
    mean_1y = out["1Y %"].mean()
    st.metric("Avg 1Y perf %", f"{mean_1y:.2f}%" if pd.notna(mean_1y) else "n/a")
with col3:
    avg_net_margin = out["Net Margin"].mean()
    st.metric("Avg Net Margin %", f"{avg_net_margin:.2f}%" if pd.notna(avg_net_margin) else "n/a")

st.write("Done — adjust the reference date to recompute. If you'd like additional metrics (e.g. exact Forward EPS, IBD ratings), provide those fields in fundamentals_raw or a separate table and I will wire them in.")
