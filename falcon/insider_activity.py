import streamlit as st
import requests
import pandas as pd
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import io

# === CONFIG ===
load_dotenv()
ALPHA_KEY = os.getenv("ALPHA_KEY")
BASE_URL = "https://www.alphavantage.co/query"


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
    return df["symbol"].tolist()

def get_insider_transactions(symbol):
    url = f"{BASE_URL}?function=INSIDER_TRANSACTIONS&symbol={symbol}&apikey={ALPHA_KEY}"
    r = requests.get(url)
    data = r.json()
    return data.get("data", [])

def get_price_change(symbol):
    url = f"{BASE_URL}?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={ALPHA_KEY}"
    r = requests.get(url)
    data = r.json().get("Time Series (Daily)", {})
    if not data:
        return None, None, None, "-"
    dates = sorted(data.keys(), reverse=True)
    latest_close = float(data[dates[0]]['4. close'])
    date_12d_ago = (datetime.strptime(dates[0], "%Y-%m-%d") - timedelta(days=12)).date()
    past_date = next((d for d in dates if datetime.strptime(d, "%Y-%m-%d").date() <= date_12d_ago), None)
    if not past_date:
        return latest_close, None, None, "-"
    old_close = float(data[past_date]['4. close'])
    change_abs = latest_close - old_close
    change_pct = (change_abs / old_close) * 100
    arrow = "↑" if change_abs >= 0 else "↓"
    price_change_display = f"{arrow} {abs(change_abs):.2f} ({abs(change_pct):.2f}%)"
    return latest_close, old_close, round(change_pct, 2), price_change_display

def get_market_cap(symbol):
    url = f"{BASE_URL}?function=OVERVIEW&symbol={symbol}&apikey={ALPHA_KEY}"
    r = requests.get(url)
    return r.json().get("MarketCapitalization")

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

def get_trending_since(date_str):
    tx_date = datetime.strptime(date_str, "%Y-%m-%d")
    delta_days = (datetime.now() - tx_date).days
    if delta_days == 0:
        return "Today"
    elif delta_days == 1:
        return "Yesterday"
    else:
        return f"{delta_days} Days Ago"

def calculate_insider_signal(tx, market_cap, insider_count):
    score = 0
    if tx["acquisition_or_disposal"] == "A": score += 2
    else: score -= 2
    try:
        pct = (float(tx["shares"]) * float(tx["share_price"]) / float(market_cap)) * 100
    except: pct = 0
    score += 3 if pct > 0.5 else 2 if pct > 0.1 else 1
    if insider_count > 1: score += 2
    days_ago = (datetime.now() - datetime.strptime(tx["transaction_date"], "%Y-%m-%d")).days
    score += 2 if days_ago <= 7 else 1 if days_ago <= 12 else 0
    title = tx["executive_title"].lower()
    score += max([
        3 if k in title else 0 for k in ["ceo", "chief executive", "chairman"]
    ] + [
        2 if k in title else 0 for k in ["cfo", "coo", "cto", "cio", "evp"]
    ] + [
        1.5 if k in title else 0 for k in ["vp", "svp", "director"]
    ] + [
        1 if k in title else 0 for k in ["10% owner", "see remarks", "former"]
    ])
    return "Very Positive" if score >= 8 else "Positive" if score >= 5 else "Neutral" if score >= 0 else "Negative"

def classify_insider_strategy(tx_list):
    roles = [tx["executive_title"].lower() for tx in tx_list]
    buys = [tx for tx in tx_list if tx["acquisition_or_disposal"] == "A"]
    sells = [tx for tx in tx_list if tx["acquisition_or_disposal"] == "D"]

    # 1. Transaction Strategy 
    if len(buys) >= 5 and len(sells) == 0:
        return ["Transaction Strategy"]

    # 2. Major Event Strategy
    major_keywords = ["owner", "see remarks", "former"]
    if any(any(k in role for k in major_keywords) for role in roles):
        return ["Major Event Strategy"]

    # 3. C-Level Strategy
    return ["C-Level Strategy"]

def is_valid_date(d):
    try:
        datetime.strptime(d, "%Y-%m-%d")
        return True
    except:
        return False

st.set_page_config(page_title="Insider Transactions", layout="wide")
st.title("Insider Transactions")

summary_rows = []
detail_dict = {}
sample_tickers = get_all_listed_tickers()[:75]

for symbol in sample_tickers:
    transactions = get_insider_transactions(symbol)
    if not transactions:
        continue

    recent_tx = [tx for tx in transactions if is_valid_date(tx.get("transaction_date")) and datetime.strptime(tx["transaction_date"], "%Y-%m-%d") >= datetime.now() - timedelta(days=12)]
    if not recent_tx:
        continue

    try:
        insider_roles = list(set(tx["executive_title"] for tx in recent_tx))
        insider_str = ", ".join(insider_roles)
        reasoning_text = f"There were {len(recent_tx)} transaction(s) by {insider_str} in the past few days"
        latest_tx_date = max(tx["transaction_date"] for tx in recent_tx)
        trending_since = get_trending_since(latest_tx_date)
        latest_price, old_price, change_pct, price_change_display = get_price_change(symbol)
        market_cap = get_market_cap(symbol)
        if not market_cap:
            continue
        market_cap_val = float(market_cap)
        top_tx = max(recent_tx, key=lambda x: float(x["shares"]) * float(x["share_price"]))
        signal = calculate_insider_signal(top_tx, market_cap_val, len(set(t["executive"] for t in recent_tx)))
        strategies = classify_insider_strategy(recent_tx)
        summary_rows.append({
            "Ticker": symbol,
            "Trending Since": trending_since,
            "Price": latest_price,
            "Price Change": price_change_display,
            "Signal Insider": signal,
            "Strategies": ", ".join(strategies),
            "Market Cap": format_market_cap(market_cap),
            "Signal Reason": reasoning_text
        })
        detail_rows = []
        for tx in recent_tx:
            shares = float(tx["shares"])
            price = float(tx["share_price"])
            total_value = shares * price
            detail_rows.append({
                "Date": get_trending_since(tx["transaction_date"]),
                "Executive": tx["executive"],
                "Title": tx["executive_title"],
                "Action": "Buy" if tx["acquisition_or_disposal"] == "A" else "Sell",
                "Shares": f"{shares:,.0f}",
                "Value": f"${total_value:,.0f}",
            })
        detail_dict[symbol] = detail_rows
    except:
        continue

if summary_rows:
    st.subheader("Trending Insider Activity")
    st.dataframe(pd.DataFrame(summary_rows))
else:
    st.info("No insider activity found in the last 12 days.")

st.subheader("Insider Transaction Details")
for symbol, rows in detail_dict.items():
    with st.expander(f"{symbol} — {len(rows)} transaction(s)"):
        st.dataframe(pd.DataFrame(rows))
