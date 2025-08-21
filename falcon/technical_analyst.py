import streamlit as st
import requests
import pandas as pd
import time
import random
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from redis_cache import redis_get, redis_set

load_dotenv()
ALPHA_KEY = os.getenv("ALPHA_KEY")

def get_listing_symbols(limit=50):
    cache_key = f"symbols:{limit}"
    cached = redis_get(cache_key)
    if cached:
        return cached

    url = f"https://www.alphavantage.co/query?function=LISTING_STATUS&apikey={ALPHA_KEY}"
    response = requests.get(url)
    if response.status_code != 200:
        return []

    lines = response.text.splitlines()
    symbols = [line.split(",")[0] for line in lines[1:]]
    result = symbols[:limit]
    redis_set(cache_key, result, ttl=2592000)  # 30 hari
    return result

def get_overview(symbol):
    cache_key = f"overview:{symbol}"
    cached = redis_get(cache_key)
    if cached:
        return cached
    
    url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={ALPHA_KEY}"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        redis_set(cache_key, data, ttl=86400)
        return data

    return {}

def get_news_sentiment(symbol):
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={symbol}&apikey={ALPHA_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        return data.get("feed", [])
    except:
        return []

def calculate_news_sentiment_score(news_feed, days=7):
    now = datetime.now()
    threshold_date = now - timedelta(days=days)
    
    sentiment_scores = []

    for item in news_feed:
        try:
            pub_date = datetime.strptime(item["time_published"], "%Y%m%dT%H%M%S")
            if pub_date >= threshold_date:
                score = float(item.get("overall_sentiment_score", 0))
                sentiment_scores.append(score)
        except:
            continue

    if not sentiment_scores:
        return 0.5 

    avg_score = sum(sentiment_scores) / len(sentiment_scores)
    
    normalized_score = (avg_score + 1) / 2
    return round(normalized_score, 2)

def calculate_fundamental_score(data):
    score = 0

    # PERatio: Idealnya antara 10–25 (bukan over/undervalued ekstrem)
    try:
        pe = float(data["PERatio"])
        if 10 <= pe <= 25:
            score += 1
    except: pass

    # PEG Ratio < 1 menandakan pertumbuhan bagus
    try:
        peg = float(data["PEGRatio"])
        if peg < 1:
            score += 1
    except: pass

    # EPS positif
    try:
        eps = float(data["EPS"])
        if eps > 0:
            score += 1
    except: pass

    # Profit Margin > 5%
    try:
        pm = float(data["ProfitMargin"])
        if pm > 0.05:
            score += 1
    except: pass

    # Operating Margin > 5%
    try:
        opm = float(data["OperatingMarginTTM"])
        if opm > 0.05:
            score += 1
    except: pass

    # ROA > 3%
    try:
        roa = float(data["ReturnOnAssetsTTM"])
        if roa > 0.03:
            score += 1
    except: pass

    # ROE > 5%
    try:
        roe = float(data["ReturnOnEquityTTM"])
        if roe > 0.05:
            score += 1
    except: pass

    # Revenue growth YoY > 0
    try:
        rev_growth = float(data["QuarterlyRevenueGrowthYOY"])
        if rev_growth > 0:
            score += 1
    except: pass

    # Earnings growth YoY > 0
    try:
        earn_growth = float(data["QuarterlyEarningsGrowthYOY"])
        if earn_growth > 0:
            score += 1
    except: pass

    # Optional: Market Cap > threshold
    try:
        mc = float(data["MarketCapitalization"])
        if mc > 2_000_000_000:
            score += 1
    except: pass

    return score

def get_latest_price(symbol):
    cache_key = f"price:{symbol}"
    cached = redis_get(cache_key)
    if cached:
        return cached

    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&apikey={ALPHA_KEY}"
    r = requests.get(url)
    if r.status_code != 200:
        return None
    try:
        data = r.json()
        latest_day = list(data["Time Series (Daily)"].keys())[0]
        price = float(data["Time Series (Daily)"][latest_day]["4. close"])
        redis_set(cache_key, price, ttl=86400)
        return price
    except:
        return None

def get_oscillators(symbol):
    cache_key = f"oscillators:{symbol}"
    cached = redis_get(cache_key)
    if cached:
        return cached
    
    base = "https://www.alphavantage.co/query"
    params = {
        "apikey": ALPHA_KEY,
        "interval": "daily",
        "symbol": symbol
    }

    def get_latest_value(function, key_name, time_period=None):
        p = params.copy()
        p["function"] = function
        if time_period:
            p["time_period"] = time_period
        p["series_type"] = "close"
        r = requests.get(base, params=p)
        data = r.json()

        try:
            technicals = data[list(data.keys())[1]]
            latest_date = sorted(technicals.keys())[-1]
            return float(technicals[latest_date][key_name])
        except:
            return None

    result = {
        "rsi": get_latest_value("RSI", "RSI", time_period=14),
        "stoch": get_latest_value("STOCH", "SlowD"),
        "williams": get_latest_value("WILLR", "WILLR", time_period=14),
        "cci": get_latest_value("CCI", "CCI", time_period=20)
    }
    redis_set(cache_key, result, ttl=86400)
    return result

def get_oscillator_score(latest):
    score = 0
    total = 0

    if latest['rsi'] is not None:
        rsi = latest['rsi']
        if rsi < 30:
            score += 1
        elif rsi > 70:
            score -= 1
        total += 1

    if latest['stoch'] is not None:
        stoch = latest['stoch']
        if stoch < 20:
            score += 1
        elif stoch > 80:
            score -= 1
        total += 1

    if latest['williams'] is not None:
        williams = latest['williams']
        if williams < -80:
            score += 1
        elif williams > -20:
            score -= 1
        total += 1

    if latest['cci'] is not None:
        cci = latest['cci']
        if cci < -100:
            score += 1
        elif cci > 100:
            score -= 1
        total += 1

    if total == 0:
        return "❓ Unknown"

    if score == total:
        return "Strong Buy"
    elif score > 0:
        return "Buy"
    elif score < 0 and abs(score) < total:
        return "Sell"
    elif score == -total:
        return "Strong Sell"
    else:
        return "Neutral"
    
def get_technicals(symbol):
    cache_key = f"technicals:{symbol}"
    cached = redis_get(cache_key)
    if cached:
        return cached
    
    base = "https://www.alphavantage.co/query"
    params = {
        "apikey": ALPHA_KEY,
        "symbol": symbol,
        "interval": "daily"
    }

    def get_macd():
        p = params.copy()
        p["function"] = "MACD"
        p["series_type"] = "close"
        p["fastperiod"] = 12
        p["slowperiod"] = 26
        p["signalperiod"] = 9
        r = requests.get(base, params=p)
        try:
            data = r.json()["Technical Analysis: MACD"]
            latest_date = sorted(data.keys())[-1]
            macd = float(data[latest_date]["MACD"])
            signal = float(data[latest_date]["MACD_Signal"])
            return macd, signal
        except:
            return None, None

    def get_bbands():
        p = params.copy()
        p["function"] = "BBANDS"
        p["series_type"] = "close"
        p["time_period"] = 20
        r = requests.get(base, params=p)
        try:
            data = r.json()["Technical Analysis: BBANDS"]
            latest_date = sorted(data.keys())[-1]
            upper = float(data[latest_date]["Real Upper Band"])
            lower = float(data[latest_date]["Real Lower Band"])
            close = get_latest_price(symbol)
            return close, lower, upper
        except:
            return None, None, None

    def get_obv():
        p = params.copy()
        p["function"] = "OBV"
        r = requests.get(base, params=p)
        try:
            data = r.json()["Technical Analysis: OBV"]
            latest_date = sorted(data.keys())[-1]
            return float(data[latest_date]["OBV"])
        except:
            return None

    macd, signal = get_macd()
    close, lower, upper = get_bbands()
    obv = get_obv()

    result = {
        "macd": macd,
        "macd_signal": signal,
        "close": close,
        "bb_lower": lower,
        "bb_upper": upper,
        "obv": obv
    }
    redis_set(cache_key, result, ttl=86400)
    return result

def get_insider_score(symbol, months=3):
    url = f"https://www.alphavantage.co/query?function=INSIDER_TRANSACTIONS&symbol={symbol}&apikey={ALPHA_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        transactions = data.get("data", [])
    except Exception as e:
        print(f"Gagal ambil data insider: {e}")
        return 0.5

    now = datetime.now()
    threshold_date = now - timedelta(days=30 * months)

    acquisition = 0
    disposal = 0

    for tx in transactions:
        try:
            tx_date = datetime.strptime(tx["transaction_date"], "%Y-%m-%d")
            if tx_date >= threshold_date:
                action = tx["acquisition_or_disposal"]
                shares = float(tx.get("shares", 0))
                if action == "A":
                    acquisition += shares
                elif action == "D":
                    disposal += shares
        except:
            continue

    if acquisition == 0 and disposal == 0:
        return 0.5
    if acquisition >= 2 * disposal:
        return 1.0
    elif acquisition > disposal:
        return 0.75
    elif disposal > acquisition >= 0.5 * disposal:
        return 0.25
    elif disposal >= 2 * acquisition:
        return 0.0
    else:
        return 0.5

def calculate_analyst_consensus(overview):
    try:
        strong_buy = int(overview.get("AnalystRatingStrongBuy", 0))
        buy = int(overview.get("AnalystRatingBuy", 0))
        hold = int(overview.get("AnalystRatingHold", 0))
        sell = int(overview.get("AnalystRatingSell", 0))
        strong_sell = int(overview.get("AnalystRatingStrongSell", 0))

        total = strong_buy + buy + hold + sell + strong_sell
        if total == 0:
            return None

        score = (strong_buy * 2 + buy * 1 - sell * 1 - strong_sell * 2) / total

        if score >= 1.2 and (sell + strong_sell == 0 or (strong_buy + buy) > (sell + strong_sell + hold)):
            return "Strong Buy"
        elif 0.4 <= score < 1.2:
            return "Buy"
        elif -0.3 <= score < 0.4:
            return "Hold"
        elif -1.2 <= score < -0.3:
            return "Sell"
        else:
            return "Strong Sell"
    except:
        return None

def get_technical_analysis_score(ta):
    score = 0
    reasons = []

    # RSI
    if ta.get("rsi") is not None:
        if ta["rsi"] > 70:
            score -= 1
            reasons.append("RSI: Overbought")
        elif ta["rsi"] < 30:
            score += 1
            reasons.append("RSI: Oversold")
        else:
            reasons.append("RSI: Neutral")
    else:
        reasons.append("RSI: ?")

    # MACD
    if ta.get("macd") is not None and ta.get("macd_signal") is not None:
        if ta["macd"] > ta["macd_signal"]:
            score += 1
            reasons.append("MACD: Bullish")
        else:
            score -= 1
            reasons.append("MACD: Bearish")
    else:
        reasons.append("MACD: ?")

    # Bollinger Bands
    if ta.get("close") is not None and ta.get("bb_lower") is not None and ta.get("bb_upper") is not None:
        if ta["close"] < ta["bb_lower"]:
            score += 1
            reasons.append("BB: Oversold")
        elif ta["close"] > ta["bb_upper"]:
            score -= 1
            reasons.append("BB: Overbought")
        else:
            reasons.append("BB: Neutral")
    else:
        reasons.append("BB: ?")

    # Stochastic Oscillator
    if ta.get("stoch_k") is not None and ta.get("stoch_d") is not None:
        if ta["stoch_k"] < 20:
            score += 1
            reasons.append("Stoch: Oversold")
        elif ta["stoch_k"] > 80:
            score -= 1
            reasons.append("Stoch: Overbought")
        else:
            reasons.append("Stoch: Neutral")
    else:
        reasons.append("Stoch: ?")

    # OBV
    if ta.get("obv") is not None:
        score += 1
        reasons.append("OBV: OK")
    else:
        reasons.append("OBV: ?")

    if score >= 4:
        decision = "Strong Buy"
    elif score >= 2:
        decision = "Buy"
    elif score >= -1:
        decision = "Neutral"
    elif score >= -3:
        decision = "Sell"
    else:
        decision = "Strong Sell"

    return {
        "decision": decision,
        "score": score,
        "reasons": " | ".join(reasons)
    }

def is_valid_ma(ma):
    try:
        return ma and float(ma) > 0
    except:
        return False
    
def market_cap(value):

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
    
def get_moving_avg_score(price, ma50, ma200):
    try:
        price = float(price)
        ma50 = float(ma50)
        ma200 = float(ma200)
    except:
        return "❓"
    
    if price > ma50 and price > ma200:
        return "Strong Buy"
    elif price > ma50 and price < ma200:
        return "Buy"
    elif price < ma50 and price > ma200:
        return "Neutral"
    else:
        return "Sell"

st.set_page_config(page_title="Oscillators + MA Dashboard", layout="wide")
st.title("Technical Analysis Screener")

data = []
symbols = get_listing_symbols(limit=50)

market_cap_ranges = {
    "Any": (0, float("inf")),
    "Mega (Over 200B)": (200e9, float("inf")),
    "Large (10B - 200B)": (10e9, 200e9),
    "Medium (2B - 10B)": (2e9, 10e9),
    "Small (300M - 2B)": (300e6, 2e9),
    "Micro (Under 300M)": (0, 300e6),
}

selected_market = st.selectbox(
    "Market Cap",
    options=list(market_cap_ranges.keys()),
    index=0,
    help="Select a market cap range to filter the data.",
)

technical_analysis_options ={
    "Any",
    "Strong Buy",
    "Buy",
    "Neutral",
    "Sell",
    "Strong Sell"
}

selected_ta = st.selectbox(
    "Technical Analysis Score",
    options=technical_analysis_options,
    index=0,
    help="Select a technical analysis score to filter the data."
)

osci_options = {
    "Any",
    "Strong Sell",
    "Sell",
    "Neutral",
    "Buy",
    "Strong Buy"
}

selected_osci = st.selectbox(
    "Oscillators Score",
    options=osci_options,
    index=0,
    help="Select an oscillators score to filter the data."
)

ma_options = {
    "Any",
    "Strong Buy",
    "Buy",
    "Neutral",
    "Sell",
    "Strong Sell"
}

selected_ma = st.selectbox(
    "Moving Average Score",
    options=ma_options,
    index=0
)

consensus = ["Any", "Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]

selected_cons = st.selectbox(
    "Analyst Consensus",
    options=consensus,
    index=0
)

def parse_market_cap(cap_str):
    try:
        cap_str = cap_str.replace("$", "").upper()
        if "B" in cap_str:
            return float(cap_str.replace("B", "")) * 1e9
        elif "M" in cap_str:
            return float(cap_str.replace("M", "")) * 1e6
        else:
            return float(cap_str)
    except:
        return None
    
def calculate_smart_score(
    ma_score,
    oscillator_score,
    ta_decision,
    analyst_rating,
    insider_score,
    news_sentiment_score,
    fundamental_score
):
    label_to_score = {
        "Strong Buy": 1.0,
        "Buy": 0.75,
        "Neutral": 0.5,
        "Sell": 0.25,
        "Strong Sell": 0.0
    }

    ma = label_to_score.get(ma_score, 0.5)
    osci = label_to_score.get(oscillator_score, 0.5)
    ta = label_to_score.get(ta_decision, 0.5)
    analyst = label_to_score.get(analyst_rating, 0.5)
    insider = insider_score if insider_score is not None else 0.5
    news = news_sentiment_score if news_sentiment_score is not None else 0.5
    fundamental = (fundamental_score if fundamental_score is not None else 5) / 10

    raw_score = (
        0.15 * ma +
        0.15 * osci +
        0.15 * ta +
        0.15 * analyst +
        0.1 * insider +
        0.1 * news +
        0.2 * fundamental
    )

    smart_score_10 = round(raw_score * 9 + 1)

    return smart_score_10

def get_screener_data(symbols):
    cache_key = f"screener_data:{','.join(symbols)}"
    cached = redis_get(cache_key)
    if cached:
        return cached
    
    data = []
    for symbol in symbols:
        overview = get_overview(symbol)
        name = overview.get("Name")
        ma50 = overview.get("50DayMovingAverage")
        ma200 = overview.get("200DayMovingAverage")
        if not is_valid_ma(ma50) or not is_valid_ma(ma200):
            continue

        price = get_latest_price(symbol)
        if price is None:
            continue

        ma_score = get_moving_avg_score(price, ma50, ma200)
        oscillators = get_oscillators(symbol)
        oscillator_score = get_oscillator_score(oscillators)

        ta = get_technicals(symbol)
        ta_score = get_technical_analysis_score(ta)

        target = overview.get("AnalystTargetPrice")
        analyst_label = "_"
        try:
            target_price = float(target)
            analyst_diff = (target_price - price) / price * 100
            if analyst_diff > 0:
                analyst_label = f"${target_price:.2f} ({analyst_diff:.1f}% upside)"
            elif analyst_diff < 0:
                analyst_label = f"${target_price:.2f} ({abs(analyst_diff):.1f}% downside)"
        except:
            pass

        raw_market_cap = overview.get("MarketCapitalization", "")
        formatted_market_cap = market_cap(raw_market_cap)
        analyst_rating = calculate_analyst_consensus(overview)
        insider_score = get_insider_score(symbol)
        news_feed = get_news_sentiment(symbol)
        news_sentiment_score = calculate_news_sentiment_score(news_feed)
        fundamental = calculate_fundamental_score(overview)
        smart_val = calculate_smart_score(
            ma_score, oscillator_score, ta_score["decision"],
            analyst_rating, insider_score, news_sentiment_score, fundamental
        )

        data.append({
            "Symbol": symbol,
            "Name": name,
            "Price": f"${price:.2f}",
            "Moving Average Score": ma_score,
            "Technical Analysis Score": ta_score["decision"],
            "Oscillators Score": oscillator_score,
            "Analyst Price Target": analyst_label,
            "Smart Score": smart_val,
            "Analyst Consensus": analyst_rating,
            "Market Cap": formatted_market_cap
        })

        time.sleep(random.uniform(0.5, 1.0))

    redis_set(cache_key, data, ttl=86400)
    return data

symbols = get_listing_symbols(limit=50)
with st.spinner("⏳ Loading data..."):
    data = get_screener_data(symbols)

low, high = market_cap_ranges[selected_market]
if selected_market != "Any":
    filtered_data = [item for item in data if (
        (cap := parse_market_cap(item.get("Market Cap", ""))) is not None and low <= cap < high
    )]
else:
    filtered_data = data

if selected_ta != "Any":
    filtered_data = [item for item in filtered_data if item.get("Technical Analysis Score") == selected_ta]

if selected_osci != "Any":
    filtered_data = [item for item in filtered_data if item.get("Oscillators Score") == selected_osci]

if selected_ma != "Any":
    filtered_data = [item for item in filtered_data if item.get("Moving Average Score") == selected_ma]

if selected_cons != "Any":
    filtered_data = [
        item for item in filtered_data
        if item.get("Analyst Consensus", "").strip() == selected_cons
    ]

df = pd.DataFrame(filtered_data)
st.dataframe(df.reset_index(drop=True), use_container_width=True)