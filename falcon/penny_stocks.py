import streamlit as st
import requests
import pandas as pd
import io
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
BASE_URL = "https://www.alphavantage.co/query"
ALPHA_KEY = os.getenv("ALPHA_KEY")

# --- API Functions ---
def get_all_listed_tickers():
    url = f"{BASE_URL}?function=LISTING_STATUS&apikey={ALPHA_KEY}"
    r = requests.get(url)
    df = pd.read_csv(io.StringIO(r.text))

    def is_valid_stock(row):
        symbol = str(row["symbol"])
        name = str(row["name"]).lower()
        if str(row["assetType"]).lower() != "stock":
            return False
        if any(x in symbol for x in ["-WS", "-W", "-WT", "-U", "-UN", "-RT"]):
            return False
        if any(x in name for x in ["warrant", "unit", "right", "spac", "acquisition", "capital", "holdings", "corp"]):
            return False
        return True

    df = df[df["status"] == "Active"]
    df = df[df.apply(is_valid_stock, axis=1)]
    return df[["symbol", "name"]].head(30).to_dict("records")

def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def get_price_data(symbol):
    url = f"{BASE_URL}?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={ALPHA_KEY}&outputsize=full"
    r = requests.get(url).json()
    try:
        ts = r["Time Series (Daily)"]

        dates = sorted(ts.keys(), reverse=True)
        last_date = dates[0]
        prev_date = dates[1]

        last_close = float(ts[last_date]["4. close"])
        prev_close = float(ts[prev_date]["4. close"])
        volume = int(ts[last_date]["6. volume"])

        price_change = ((last_close - prev_close) / prev_close) * 100
        dollar_volume = last_close * volume

        last_datetime = datetime.strptime(last_date, "%Y-%m-%d")
        one_month_ago = last_datetime - timedelta(days=22)

        one_month_date = max(
            [d for d in dates if datetime.strptime(d, "%Y-%m-%d") <= one_month_ago],
            default=None
        )

        if one_month_date:
            price_1month_ago = float(ts[one_month_date]["4. close"])
            one_month_change = ((last_close - price_1month_ago) / price_1month_ago) * 100
        else:
            one_month_change = 0

        return {
            "price": last_close,
            "price_change": price_change,
            "dollar_volume": dollar_volume,
            "one_month_change": one_month_change
        }
    except:
        return {
            "price": 0,
            "price_change": 0,
            "dollar_volume": 0,
            "one_month_change": 0
        }
    
def get_overview(symbol):
    url = f"{BASE_URL}?function=OVERVIEW&symbol={symbol}&apikey={ALPHA_KEY}"
    r = requests.get(url).json()
    price_data = get_price_data(symbol)
    price = price_data["price"]

    # Market Cap
    market_cap = safe_float(r.get("MarketCapitalization"), 0)

    # Analyst Target Price (formatted with upside/downside)
    target_price_val = safe_float(r.get("AnalystTargetPrice"), 0)
    if target_price_val > 0 and price > 0:
        diff_pct = (target_price_val - price) / price * 100
        if diff_pct > 0:
            target_price = f"${target_price_val:.2f} ({diff_pct:.1f}% upside)"
        elif diff_pct < 0:
            target_price = f"${target_price_val:.2f} ({abs(diff_pct):.1f}% downside)"
        else:
            target_price = f"${target_price_val:.2f} (no change)"
    else:
        target_price = "No Data"

    # Analyst Consensus Calculation
    try:
        sb = int(r.get("AnalystRatingStrongBuy", 0))
        b = int(r.get("AnalystRatingBuy", 0))
        h = int(r.get("AnalystRatingHold", 0))
        s = int(r.get("AnalystRatingSell", 0))
        ss = int(r.get("AnalystRatingStrongSell", 0))

        total = sb + b + h + s + ss
        if total == 0:
            analyst_consensus = "No Data"
        else:
            score = (sb * 2 + b) - (s + ss * 2)
            score = (sb * 2 + b * 1 - s * 1 - ss * 2)
            score_ratio = score / total

            if score_ratio >= 1.2:
                analyst_consensus = "Strong Buy"
            elif 0.4 <= score_ratio < 1.2:
                analyst_consensus = "Moderate Buy"
            elif -0.3 <= score_ratio < 0.4:
                analyst_consensus = "Hold"
            elif -1.2 <= score_ratio < -0.3:
                analyst_consensus = "Moderate Sell"
            else:
                analyst_consensus = "Strong Sell"
    except Exception:
        analyst_consensus = "No Data"

    return {
        "market_cap": market_cap,
        "analyst_consensus": analyst_consensus,
        "target_price": target_price,
        "name": r.get("Name", symbol)
    }
    
def format_number(value):

    try:
        val = float(value)
    except:
        return ""
    if val >= 1e9:
        return f"${val/1e9:.2f}B"
    elif val >= 1e6:
        return f"${val/1e6:.2f}M"
    elif val >= 1e3:
        return f"${val/1e3:.2f}K"
    else:
        return f"${val:.0f}"

# --- Penny Stock Filter ---
def find_penny_stocks():
    tickers = get_all_listed_tickers()
    results = []

    for t in tickers:
        ov = get_overview(t["symbol"])
        raw_market_cap = ov.get("market_cap", 0)
        price_data = get_price_data(t["symbol"])

        if price_data["price"] <= 0 or raw_market_cap <= 0:
            continue

        formatted_market_cap = format_number(raw_market_cap)
        formatted_dollar_volume = format_number(price_data["dollar_volume"])

        if price_data["price"] < 5 and raw_market_cap < 300_000_000:
            results.append({
                "Symbol": t["symbol"],
                "Name": ov["name"],
                "Price": price_data["price"],
                "Analyst Consensus": ov["analyst_consensus"],
                "Analyst Price Target": ov["target_price"],
                "Market Cap": formatted_market_cap,
                "Dollar Volume": formatted_dollar_volume,
                "1 Month %": f"{price_data['one_month_change']:.2f}%"
            })
    return results

st.set_page_config(page_title="Penny Stocks", layout="wide")
st.title("Penny Stocks")

with st.spinner("Fetching data..."):
    stocks = find_penny_stocks()
    df = pd.DataFrame(stocks)

st.dataframe(df)