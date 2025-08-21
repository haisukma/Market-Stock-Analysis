import streamlit as st
import pandas as pd
import requests
from dotenv import load_dotenv
import os
import time
import json
from datetime import datetime, timedelta
from io import StringIO
import redis

# --- Setup ---
st.set_page_config(page_title="Market Movers", layout="wide")
st.title("📈 Market Movers")
load_dotenv()

ALPHA_KEY = os.getenv("ALPHA_KEY")
REDIS_TTL_TICKERS = 2592000  # 1 bulan
REDIS_TTL_OVERVIEW = 86400  # 1 hari
REDIS_TTL_DAILY = 3600     # 1 jam

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    decode_responses=True
)

# --- Utils ---
def redis_get_json(key):
    cached = r.get(key)
    if cached:
        return json.loads(cached)
    return None


def redis_set_json(key, value, ex=3600):
    r.set(key, json.dumps(value), ex=ex)


def format_market_cap(cap):
    try:
        cap = float(cap)
        if cap >= 1e12:
            return f"${cap / 1e12:.2f}T"
        elif cap >= 1e9:
            return f"${cap / 1e9:.2f}B"
        elif cap >= 1e6:
            return f"${cap / 1e6:.2f}M"
        else:
            return f"${cap:,.0f}"
    except:
        return "-"

# --- Data Fetching ---
def get_active_tickers():
    cache_key = "market_mover:active_tickers"
    cached = redis_get_json(cache_key)
    if cached:
        print("📦 Loaded active tickers from Redis cache")
        return cached

    url = f"https://www.alphavantage.co/query?function=LISTING_STATUS&apikey={ALPHA_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return []

    df = pd.read_csv(StringIO(res.text))

    def is_valid_stock(row):
        symbol = str(row["symbol"]).upper()
        name = str(row["name"]).lower()
        if row["status"] != "Active":
            return False
        if row["assetType"].lower() != "stock":
            return False
        if any(x in symbol for x in ["-WS", "-W", "-WT", "-U", "-UN", "-RT"]):
            return False
        if any(x in name for x in ["warrant", "unit", "right", "spac", "acquisition", "capital", "holdings", "corp"]):
            return False
        return True

    df_filtered = df[df.apply(is_valid_stock, axis=1)]
    tickers = df_filtered["symbol"].tolist()
    redis_set_json(cache_key, tickers, ex=REDIS_TTL_TICKERS)
    return tickers

@st.cache_data(ttl=300)
def fetch_market_movers():
    url = f"https://www.alphavantage.co/query?function=TOP_GAINERS_LOSERS&apikey={ALPHA_KEY}"
    res = requests.get(url)
    return res.json() if res.status_code == 200 else None


def get_company_info(symbol):
    cache_key = f"market_mover:company_info:{symbol}"
    # cache_key = f"cache_company_info:{symbol}"
    cached = redis_get_json(cache_key)
    if cached:
        return cached

    url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={ALPHA_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return {"Name": "-", "MarketCap": "-"}

    data = res.json()
    info = {
        "Name": data.get("Name", "-"),
        "MarketCap": format_market_cap(data.get("MarketCapitalization", "0"))
    }

    redis_set_json(cache_key, info, ex=REDIS_TTL_OVERVIEW)
    return info


def extract_stock_info_from_daily(symbol):
    cache_key = f"market_mover:daily_info:{symbol}"
    cached = redis_get_json(cache_key)
    if cached:
        return cached

    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={ALPHA_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return None

    data = res.json()
    ts = data.get("Time Series (Daily)", {})
    if len(ts) < 2:
        return None

    try:
        dates = sorted(ts.keys(), reverse=True)
        today = ts[dates[0]]
        yesterday = ts[dates[1]]
        today_close = float(today["4. close"])
        yesterday_close = float(yesterday["4. close"])
        volume = int(today["6. volume"])
        change_amount = today_close - yesterday_close
        change_percentage = (change_amount / yesterday_close) * 100

        info = {
            "price": f"{today_close:.4f}",
            "change_amount": f"{change_amount:.4f}",
            "change_percentage": f"{change_percentage:.4f}%",
            "volume": volume
        }

        redis_set_json(cache_key, info, ex=REDIS_TTL_DAILY)
        return info
    except:
        return None

def get_daily_series(symbol):
    cache_key = f"market_mover:daily_series:{symbol}"
    cached = redis_get_json(cache_key)
    if cached:
        return cached

    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={ALPHA_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return None

    data = res.json()
    ts = data.get("Time Series (Daily)", {})
    if not ts:
        return None

    redis_set_json(cache_key, ts, ex=REDIS_TTL_DAILY)
    return ts

def get_after_hours_data(symbol):
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol={symbol}&interval=15min&outputsize=full&apikey={ALPHA_KEY}"
    res = requests.get(url)
    if res.status_code != 200:
        return None

    data = res.json()
    if "Time Series (15min)" not in data:
        print(f"⚠️ No intraday data for {symbol}")
        return None

    ts = data["Time Series (15min)"]

    parsed = []
    for t, v in ts.items():
        dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        parsed.append((dt, v))

    parsed.sort(reverse=True)

    today = parsed[0][0].date()
    close_16 = None
    close_19 = None
    close_yesterday_19 = None
    after_hours_volume = 0

    for t, v in parsed:
        date = t.date()

        # Hari ini
        if date == today:
            if t.hour == 16 and t.minute == 0:
                close_16 = float(v["4. close"])
            elif t.hour == 19 and t.minute == 0:
                close_19 = float(v["4. close"])
                after_hours_volume += int(v["5. volume"])
            elif (t.hour == 16 and t.minute in [15, 30, 45]) or (t.hour in [17, 18]):
                after_hours_volume += int(v["5. volume"])

        elif date < today and t.hour == 19 and t.minute == 0 and close_yesterday_19 is None:
            close_yesterday_19 = float(v["4. close"])

    if close_16 is None or close_19 is None:
        print(f"⚠️ Data missing for {symbol} — close_16: {close_16}, close_19: {close_19}")
        return None

    if close_yesterday_19 is not None:
        pct_change = ((close_19 - close_yesterday_19) / close_yesterday_19) * 100
    else:
        pct_change = None

    return {
        "symbol": symbol,
        "regular_close": close_16,
        "after_hours_close": close_19,
        "change_pct": round(pct_change, 2) if pct_change is not None else None,
        "after_hours_volume": after_hours_volume,
        "yesterday_ah_close": close_yesterday_19
    }

def run_after_hours_screener():
    tickers = get_active_tickers()
    gainers = []
    losers = []

    for i, symbol in enumerate(tickers[:50]):
        try:
            info = get_after_hours_data(symbol)
            if info and info["after_hours_volume"] > 100000:
                if info["change_pct"] is not None:
                    formatted_info = {
                        "ticker": info["symbol"],
                        "price": info["after_hours_close"],
                        "change_percentage": f"{info['change_pct']:.2f}%",
                        "volume": info["after_hours_volume"]
                    }
                    if info["change_pct"] > 1:
                        gainers.append(formatted_info)
                    elif info["change_pct"] < -1:
                        losers.append(formatted_info)
        except Exception as e:
            print(f"⚠️ Error processing {symbol}: {e}")

    return gainers, losers


# --- Table Rendering ---
@st.cache_data(ttl=600)
def render_table(raw_data):
    df = pd.DataFrame(raw_data)

    # Format
    df["price"] = df["price"].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["volume"] = df["volume"].apply(lambda x: f"{x/1e6:.2f}M" if x > 1e6 else f"{x/1e3:.0f}K")

    if "change_percentage" in df.columns:
        df["change_percentage"] = df["change_percentage"].astype(str).str.replace('%', '', regex=False)
        df["change_percentage"] = pd.to_numeric(df["change_percentage"], errors="coerce")

    company_infos = {ticker: get_company_info(ticker) for ticker in df["ticker"]}
    df["Company Name"] = df["ticker"].apply(lambda x: company_infos[x]["Name"])
    df["Market Cap"] = df["ticker"].apply(lambda x: company_infos[x]["MarketCap"])

    return df.rename(columns={
        "ticker": "Symbol",
        "price": "Price",
        "change_percentage": "% Today",
        "volume": "Volume"
    })[["Symbol", "Company Name", "Price", "% Today", "Volume", "Market Cap"]]

def process_52_week_data(high=True):
    label = "high" if high else "low"
    st.subheader(f"52-Week {'High' if high else 'Low'}")
    tickers = get_active_tickers()
    # st.write(f"{len(tickers)} valid active stocks loaded.")
    result = []

    for symbol in tickers[:50]:
        try:
            # overview_key = f"market_mover:company_overview:{symbol}"
            overview_key = f"market_mover:company_info:{symbol}"
            data = redis_get_json(overview_key)
            if not data:
                continue

            level = float(data.get(f"52Week{label.capitalize()}", 0))
            if level == 0:
                continue

            info = redis_get_json(f"market_mover:daily_info:{symbol}")
            if not info or "price" not in info:
                continue

            price = float(info["price"])
            tolerance = 0.01
            if (high and price >= level * (1 - tolerance)) or (not high and price <= level * (1 + tolerance)):
                result.append({"ticker": symbol, **info})
        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    if result:
        df_result = render_table(result)
        st.dataframe(df_result, use_container_width=True)
    else:
        st.info(f"Tidak ada saham yang menyentuh 52-week {label}.")

def get_unusual_volume_stocks(volume_ratio_threshold=3.0):
    tickers = get_active_tickers()
    unusual_stocks = []

    for symbol in tickers[:200]:
        try:
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={ALPHA_KEY}"
            res = requests.get(url)
            if res.status_code != 200:
                continue

            # data = res.json()
            ts = get_daily_series(symbol)
            if not ts or len(ts) < 51:
                continue

            dates = sorted(ts.keys(), reverse=True)
            today = ts[dates[0]]
            today_volume = int(today["6. volume"])
            close_price = float(today["4. close"])

            past_30_volumes = [int(ts[d]["6. volume"]) for d in dates[1:51]]
            avg_volume = sum(past_30_volumes) / len(past_30_volumes)

            ratio = today_volume / avg_volume if avg_volume > 0 else 0
            if ratio >= volume_ratio_threshold:
                info = extract_stock_info_from_daily(symbol)
                if info and float(info["price"]) > 10:
                    info["volume_ratio"] = round(ratio, 2)
                    info["ticker"] = symbol
                    unusual_stocks.append(info)

        except Exception as e:
            print(f"Error processing {symbol}: {e}")
            continue

    return unusual_stocks

# --- MAIN ---
data = fetch_market_movers()
if not data:
    st.error("Gagal mengambil data dari Alpha Vantage")
    st.stop()

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["Gainers", "Losers", "Active", "52-Week High", "52-Week Low", "Unusual Volume", "After Hours"])

with tab1:
    st.subheader("Top Gainers Today")
    st.dataframe(render_table(data["top_gainers"]), use_container_width=True)

with tab2:
    st.subheader("Top Losers Today")
    st.dataframe(render_table(data["top_losers"]), use_container_width=True)

with tab3:
    st.subheader("Most Active Today")
    st.dataframe(render_table(data["most_actively_traded"]), use_container_width=True)

with tab4:
    process_52_week_data(high=True)

with tab5:
    process_52_week_data(high=False)
with tab6:
    st.subheader("Unusual Volume")
    unusual_stocks = get_unusual_volume_stocks()
    if unusual_stocks:
        df_unusual = render_table(unusual_stocks)
        st.dataframe(df_unusual, use_container_width=True)
    else:
        st.info("Tidak ada saham dengan volume tidak biasa hari ini.")
with tab7:
    st.subheader("After Hours")
    gainers, losers = run_after_hours_screener()

    if gainers:
        st.markdown("Gainers")
        df_gainers = render_table(gainers)
        st.dataframe(df_gainers, use_container_width=True)
    else:
        st.info("Tidak ada after-hours gainers.")

    if losers:
        st.markdown("Losers")
        df_losers = render_table(losers)
        st.dataframe(df_losers, use_container_width=True)
    else:
        st.info("Tidak ada after-hours losers.")