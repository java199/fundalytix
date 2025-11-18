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
def get_index_list(ref_date: datetime.date, index_name) -> pd.DataFrame:
    # supabase expects ISO date strings for filtering
    ref_date_str = ref_date.isoformat()
    resp = (
        supabase
        .table("constituents_history")
        .select("ticker")
        .eq("index", index_name)
        .gte("included_start", ref_date_str)
        .lte("included_end", ref_date_str)
        .distinct()
        .execute()
    )
    return pd.DataFrame(resp.data)

@st.cache_data(ttl=300)  # cache for 5 minutes
def load_fundamentals_for_date(ref_date: datetime.date, index_name) -> pd.DataFrame:
    index_list = get_index_list(ref_date, index_name)["ticker"].tolist()
    stocks = load_stocks(index_list)["ticker"].tolist()
    
    # supabase expects ISO date strings for filtering
    ref_date_str = ref_date.isoformat()
    resp = (
        supabase
        .table("fundamentals_daily")
        .select("*")
        .eq("dt", ref_date_str)
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

available_dates = load_fundamentals_available_dates()

# --- Inputs ---
col1, col2 = st.columns([1, 1])

with col1:
    index_choice = st.selectbox("Select Index", list(INDEX_OPTIONS))

with col2:
    ref_date = st.date_input("Reference date", value=datetime.today().date(), options=available_dates["dt"].tolist())

st.write(f"Using reference date: {ref_date}")

# --- Fetch Data Button ---
if st.button("Load Fundamentals"):
    with st.spinner("Fetching data... this may take a minute"):
        df = load_fundamentals_for_date(ref_date, index_choice)

        # --- Filtering Controls ---
        st.subheader("Fundamentals")

        # --- Table ---
        st.dataframe(df, use_container_width=True)

        # --- Summary Stats ---
        st.caption(f"Data as of {ref_date.strftime('%Y-%m-%d')} (latest available from Yahoo Finance)")