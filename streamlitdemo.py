import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from supabase import create_client

INDEX_OPTIONS = {"S&P 500"}

# ----------------------
# read secrets
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

# create supabase client
supabase = create_client(url, key)

# ----------------------
# Helpers to fetch data
# ----------------------
@st.cache_data(ttl=300)  # cache for 5 minutes
def load_stocks(index_list):
    resp = supabase.table("stocks").select("*").execute()
    df = pd.DataFrame(resp.data)
    df = df[df["ticker"].isin(index_list)]
    return df

@st.cache_data(ttl=300)  # cache for 5 minutes
def get_index_list(ref_date: str, index_name):
    # supabase expects ISO date strings for filtering
    resp = (
        supabase
        .table("constituents_history")
        .select("*")
        .eq("index", index_name)
        .execute()
    )
    df = pd.DataFrame(resp.data)
    df = df[df["included_start"] <= ref_date]
    df = df[df["included_end"] >= ref_date]
    df = df.drop_duplicates(subset=["ticker"])
    return df["ticker"].to_list()

@st.cache_data(ttl=300)  # cache for 5 minutes
def load_fundamentals_for_date(ref_date, index_name) -> pd.DataFrame:
    index_list = get_index_list(ref_date, index_name)
    stocks = load_stocks(index_list)["ticker"].tolist()
    
    # supabase expects ISO date strings for filtering
    resp = (
        supabase
        .table("fundamentals_daily")
        .select("*")
        .eq("dt", ref_date)
        .in_("ticker", stocks)
        .execute()
    )
    return pd.DataFrame(resp.data)

def load_fundamentals_available_dates():
    resp = (
        supabase
        .table("fundamentals_daily")
        .select("dt", count="exact")
        .group("dt")
        .order("dt", desc=True)
        .execute()
    )
    df = pd.DataFrame(resp.data)
    df["dt"] = pd.to_datetime(df["dt"]).dt.date
    return df


# -------------------------------------------------------
# 🖥️ Streamlit UI
# -------------------------------------------------------
st.title("📊 Fundalytics — Index Fundamentals Dashboard")

available_dates = ["2025-09-30","2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30"]

# --- Inputs ---
col1, col2 = st.columns([1, 1])

with col1:
    index_choice = st.selectbox("Select Index", list(INDEX_OPTIONS))

with col2:
    ref_date = st.selectbox("Reference date", available_dates)

st.write(f"Using reference date: {ref_date}")

# --- Fetch Data Button ---
if st.button("Load Fundamentals"):
    with st.spinner("Fetching data... this may take a minute"):
        df = load_fundamentals_for_date(ref_date, index_choice)

        # --- Formatting Columns ---
        df_display = df.copy()

        # Rename columns
        df_display.rename(columns={
            "perf_1m": "1M Perf",
            "perf_3m": "3M Perf",
            "perf_6m": "6M Perf",
            "perf_1y": "1Y Perf",
            "perf_3y": "3Y Perf",
            "perf_5y": "5Y Perf",
            "rev_earnings": "Revenue / Earnings",
            "revenue_1y": "Revenue 1Y",
            "revenue_5y": "Revenue 5Y",
            "earning_1y": "Earnings 1Y",
            "earning_5y": "Earnings 5Y",
            "net_margin": "Net Margin",
            "cash_to_dept": "Cash/Dept",
            "growth_1y": "Growth 1Y",
            "price": "Price",
        }, inplace=True)

        # Convert performance columns to X-notation
        x_notation_cols = ["Revenue 1Y", "Revenue 5Y", "Earnings 1Y", "Earnings 5Y"]
        percentage_cols = ["1M Perf","3M Perf","6M Perf","1Y Perf","3Y Perf","5Y Perf"]

        for col in percentage_cols:
            df_display[col] = (df_display[col] * 100).round(2)  # e.g., 0.1234 → 12.34%
        for col in x_notation_cols:
            df_display[col] = (df_display[col] * 100).round(2) / 100  # e.g., 1.25 → 1.25x

        # Hide unwanted columns
        df_display.drop(columns=["fpe", "ibd_score", "dt"], inplace=True, errors='ignore')

        # --- Display Individual Stocks ---
        st.subheader("Individual Stock Fundamentals")
        st.dataframe(df_display, use_container_width=True)

        # --- Compute Index Average ---
        avg_row = df_display.mean(numeric_only=True).to_frame().T
        avg_row.insert(0, "ticker", "Index Average")

        # Append index average row
        df_avg_display = pd.concat([df_display, avg_row], ignore_index=True)

        # --- Color scale function ---
        def color_scale(val, col_mean):
            if val < col_mean:
                # interpolate red to white
                intensity = min(1, abs(val - col_mean) / col_mean)
                return f"background-color: rgba(255, 0, 0, {intensity})"
            elif val > col_mean:
                # interpolate white to green
                intensity = min(1, abs(val - col_mean) / col_mean)
                return f"background-color: rgba(0, 255, 0, {intensity})"
            else:
                return ""

        # Apply coloring relative to index average
        means = df_display.mean(numeric_only=True)
        styled_df = df_avg_display.apply(lambda x: [color_scale(v, means[col]) if pd.api.types.is_number(v) else '' 
                                                                          for col,v in zip(df_avg_display.columns, x)], axis=1)

        st.subheader("Fundamentals with Index Average")
        st.dataframe(styled_df)
        st.caption(f"Data as of {ref_date} (latest available from Yahoo Finance)")