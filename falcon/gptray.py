import requests
import json
import openai
import time
import os
import io
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
ALPHA_KEY = os.getenv("ALPHA_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = openai.OpenAI(api_key=OPENAI_API_KEY)

SYMBOL = "NFLX"

INTERVALS = {
    # "15min": "15min",
    "30min": "30min",
    "1h": "60min",
    "1d": "daily"
}

BASE_URL = "https://www.alphavantage.co/query"

def fetch_data(symbol, function, interval, extra_params=None):
    params = {
        "function": function,
        "symbol": symbol,
        "apikey": ALPHA_KEY,
    }
    if interval != "daily":
        params["interval"] = interval
    if extra_params:
        params.update(extra_params)
    
    response = requests.get(BASE_URL, params=params)
    # time.sleep(12)
    return response.json()

def fetch_overview(symbol):
    params = {
        "function": "OVERVIEW",
        "symbol": symbol,
        "apikey": ALPHA_KEY
    }
    response = requests.get(BASE_URL, params=params)
    return response.json()

def extract_latest(data, key):
    if key not in data:
        return {}
    timestamps = sorted(data[key].keys(), reverse=True)
    return data[key][timestamps[0]] if timestamps else {}

def analyze_with_gpt(symbol, all_data):
    prompt = f"""
You are a stock analyst. Based on the following technical data for the stock {symbol}, provide a complete analysis in English. Use this format:
- Current Price: $xxx.xx
- Action: Buy / Sell / Hold
- Volume: [volume analysis]
- Timeframe Entry: [15min / 30min / 1h / 1d]
- Buy Zone: [ideal buying price range]
- Target Profit: [target price]
- Stop Loss: [cut loss level]
- Smart Score: [score from 1-10]
- Strategy: [recommended strategy, e.g., breakout / pullback]
  
Analyst Insights:
[A brief explanation (1-3 sentences) summarizing the analysis professionally and concisely]

Here is the data:
{json.dumps(all_data, indent=2)}
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=500,
    )
    return response.choices[0].message.content.strip()

def get_halal_stocks():
    spus = pd.read_csv(
        io.BytesIO(requests.get("https://www.sp-funds.com/data/TidalETF_Services.40ZZ.UP_Holdings_SPUS.csv",
        headers={"User-Agent": "Mozilla/5.0"}).content)
    )["StockTicker"].dropna().str.upper().tolist()
    hlal = pd.read_csv("https://docs.google.com/spreadsheets/d/1UC1Bk67bGuYsos_i8y_HQpNoHpVHAvqf71MbgrafJOQ/export?format=csv")["StockTicker"].dropna().str.upper().tolist()
    des_df = pd.read_excel("/Users/diajeng/Downloads/penambahan-konstituen-indeks-saham-syariah-indonesia-issi/Index Member ISSI_DKHH.xlsx", skiprows=5)
    des = des_df["Kode"].dropna().astype(str).str.upper().tolist()
    return list(set(spus + hlal + des))

def run_analysis(symbol, intervals=None):
    default_intervals = {
        "30min": "30min",
        "1h": "60min",
        "1d": "daily"
    }
    INTERVALS = intervals or default_intervals

    halal_list = get_halal_stocks()
    syariah_compliant = symbol.upper() in halal_list
    
    result = {}
    result["syariah_compliance"] = "Halal" if syariah_compliant else "Non-Halal"

    overview = fetch_overview(symbol)
    analyst_rating = {
        "Strong Buy": overview.get("AnalystRatingStrongBuy"),
        "Buy": overview.get("AnalystRatingBuy"),
        "Hold": overview.get("AnalystRatingHold"),
        "Sell": overview.get("AnalystRatingSell"),
        "Strong Sell": overview.get("AnalystRatingStrongSell"),
    }
    result["analyst_rating"] = analyst_rating

    result["technical"] = {}
    for label, interval in INTERVALS.items():
        result["technical"][label] = {}
        if interval == "daily":
            price_data = fetch_data(symbol, "TIME_SERIES_DAILY", interval)
            price_key = "Time Series (Daily)"
        else:
            price_data = fetch_data(symbol, "TIME_SERIES_INTRADAY", interval, {"outputsize": "compact"})
            price_key = f"Time Series ({interval})"
        result["technical"][label]["price_volume"] = extract_latest(price_data, price_key)
        result["technical"][label]["rsi"] = extract_latest(fetch_data(symbol, "RSI", interval, {"series_type": "close", "time_period": 14}), "Technical Analysis: RSI")
        result["technical"][label]["macd"] = extract_latest(fetch_data(symbol, "MACD", interval, {"series_type": "close"}), "Technical Analysis: MACD")
        result["technical"][label]["ema50"] = extract_latest(fetch_data(symbol, "EMA", interval, {"series_type": "close", "time_period": 50}), "Technical Analysis: EMA")
        result["technical"][label]["ema200"] = extract_latest(fetch_data(symbol, "EMA", interval, {"series_type": "close", "time_period": 200}), "Technical Analysis: EMA")

    result["gpt_analysis"] = analyze_with_gpt(symbol, result["technical"])
    return result