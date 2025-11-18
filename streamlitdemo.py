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
# if st.button("Load Fundamentals"):
#     with st.spinner("Fetching data... this may take a minute"):
ref_date = "2025-09-30"
index_choice = "S&P 500"
df = load_fundamentals_for_date(ref_date, index_choice)

# --- Filtering Controls ---
st.subheader("Fundamentals")

# --- Table ---
st.dataframe(df, use_container_width=True)

# --- Summary Stats ---
st.caption(f"Data as of {ref_date} (latest available from Yahoo Finance)")