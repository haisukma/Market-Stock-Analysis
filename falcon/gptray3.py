import base64
import fitz
import re
import openai
import requests
import finnhub
import yfinance as yf
import time
import os
import pandas as pd
import io
from playwright.sync_api import sync_playwright
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from datetime import datetime, timezone
    
client = openai.OpenAI(api_key="sk-pr")
finnhub_client = finnhub.Client(api_key="d1")

def get_halal_stocks():
    try:
        spus_url = "https://www.sp-funds.com/data/TidalETF_Services.40ZZ.UP_Holdings_SPUS.csv"
        gsheet_url = "https://docs.google.com/spreadsheets/d/1UC1Bk67bGuYsos_i8y_HQpNoHpVHAvqf71MbgrafJOQ/export?format=csv"
        local_excel_path = "./files/Index Member ISSI_DKHH.xlsx"

        spus_df = pd.read_csv(
            io.BytesIO(requests.get(spus_url, headers={"User-Agent": "Mozilla/5.0"}).content)
        )
        spus = spus_df["StockTicker"].dropna().str.upper().tolist()

        hlal_df = pd.read_csv(gsheet_url)
        hlal = hlal_df["StockTicker"].dropna().str.upper().tolist()

        if os.path.exists(local_excel_path):
            des_df = pd.read_excel(local_excel_path, skiprows=5)
            des = des_df["Kode"].dropna().astype(str).str.upper().tolist()
        else:
            des = []

        return list(set(spus + hlal + des))

    except Exception as e:
        print(f"⚠️ Error loading halal stock data: {e}")
        return []
    
def check_halal_stock(ticker: str):
    halal_list = get_halal_stocks()
    ticker_upper = ticker.upper()

    found = [code for code in halal_list if ticker_upper in code or code in ticker_upper]

    return {
        "is_halal": bool(found),
        "matched_with": found
    }

def take_tradingview_screenshots(symbol, intervals):
    chrome_options = Options()
    chrome_options.add_argument(r'--user-data-dir="/Users/diajeng/Library/Application Support/Google/Chrome"')
    chrome_options.add_argument('--profile-directory=Default')
    chrome_options.add_argument("--start-maximized")
    chrome_options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=chrome_options)

    image_bytes_list = []

    try:
        for interval in intervals:
            driver.get(f"https://www.tradingview.com/chart/?symbol={symbol}&interval={interval}")
            time.sleep(4)
            image_bytes_list.append(driver.get_screenshot_as_png())
            print(f"📸 Screenshot {symbol} {interval} diambil (RAM)")
    finally:
        driver.quit()

    return image_bytes_list

def utc_timestamp():
    utc_now = datetime.now(timezone.utc)
    return {
        "date": utc_now.strftime("%Y-%m-%d"),
        "time": utc_now.strftime("%H:%M UTC"),
    }

def get_tradingview_full_data(ticker):
    def get_keystats_value(page):
        try:
            info_map = {}

            # Ambil container khusus company info
            company_section = page.locator('div[data-an-widget-id="key-stats-id"]')
            blocks = company_section.locator('div[class^="blockContent-"]')
            count = blocks.count()

            # Label urutan yang benar (sesuai HTML-nya)
            label_map = {
                0: "Market capitalization",
                1: "Dividend yield (indicated)",
                2: "Price to earning Ratio (TTM)",
                3: "Basic EPS (TTM)",
                4: "Net Income (FY)",
                5: "Revenue (FY)",
                6: "Shares float",
                7: "Beta (1Y)"
            }

            for i in range(count):
                try:
                    block = blocks.nth(i)
                    value_node = block.locator('div[class^="apply-overflow-tooltip value-"]').first
                    value = value_node.inner_text().strip()
                    label = label_map.get(i, f"Unknown_{i}")
                    info_map[label] = value
                except:
                    continue

            return info_map
        except Exception as e:
            print(f"⚠️ Gagal ambil info:", e)
            return {}
        
    def get_employees_value(page):
        try:
            company_section = page.locator('div[data-an-widget-id="employees-section"]')
            blocks = company_section.locator('div[class^="blockContent-"]')
            value_node = blocks.nth(0).locator('div[class^="apply-overflow-tooltip value-"]').first
            return value_node.inner_text().strip()
        except Exception as e:
            print(f"⚠️ Gagal ambil employees info: {e}")
            return "N/A"

    def extract_company_info(page):
        try:
            company_section = page.locator('div[data-an-widget-id="company-info-id"]')
            blocks = company_section.locator('div[class^="blockContent-"]')
            info_map = {}
            label_map = {
                0: "Sector",
                1: "Industry"
            }
            for i in range(2):
                block = blocks.nth(i)
                value_node = block.locator('div[class^="apply-overflow-tooltip value-"]').first
                value = value_node.inner_text().strip()
                label = label_map.get(i)
                if label:
                    info_map[label] = value
            return info_map
        except Exception as e:
            print(f"⚠️ Gagal ambil company info: {e}")
            return {"Sector": "N/A", "Industry": "N/A"}

    def get_description(page):
        try:
            # scroll agar tombol tampak
            page.mouse.wheel(0, 2000)
            time.sleep(1)

            # klik tombol Show more jika ada
            show_more = page.locator('//button[contains(@class,"toggleDescriptionButton-")]')
            
            if show_more.count():
                show_more.first.click()
                time.sleep(1)

            desc = page.locator('div[class*="truncatedBlockText"]').first.inner_text().strip()
            return desc
        except Exception as e:
            print(f"⚠️  Gagal ambil deskripsi: {e}")
            return "N/A"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        url = f"https://www.tradingview.com/symbols/{ticker}/"
        print(f"🔍 Mengunjungi: {url}")
        page.goto(url, timeout=60000)
        time.sleep(3)

        description = get_description(page)
        company_info = extract_company_info(page)
        sector = company_info.get("Sector", "N/A")
        industry = company_info.get("Industry", "N/A")
        employees = get_employees_value(page)
        key_stats_info = get_keystats_value(page)
        market_capitalization = key_stats_info.get("Market capitalization", "N/A")
        dividend_yield = key_stats_info.get("Dividend yield (indicated)", "N/A")
        price_earning = key_stats_info.get("Price to earning Ratio (TTM)", "N/A")
        basic_EPS = key_stats_info.get("Basic EPS (TTM)", "N/A")
        net_income = key_stats_info.get("Net Income (FY)", "N/A")
        revenue = key_stats_info.get("Revenue (FY)", "N/A")
        shares_float = key_stats_info.get("Shares float", "N/A")
        beta = key_stats_info.get("Beta (1Y)", "N/A")

        browser.close()

        return {
            "ticker": ticker,
            "company_info": {
                "description": description,
                "sector": sector,
                "industry": industry,
                "employees": employees,
                "market_capitalization": market_capitalization,
                "dividend_yield": dividend_yield,
                "price_earning": price_earning,
                "basic_EPS": basic_EPS,
                "net_income": net_income,
                "revenue": revenue,
                "shares_float": shares_float,
                "beta": beta
            }
        }
    
def get_company_info_for_streamlit(ticker):
    data = get_tradingview_full_data(ticker)
    company_info = data.get("company_info", {})
    return {
        "about": company_info.get("description", "-"),
        "employees": company_info.get("employees", "-"),
        "sector": company_info.get("sector", "-"),
        "industry": company_info.get("industry", "-"),
        "market_capitalization": company_info.get("market_capitalization", "-"),
        "dividend_yield": company_info.get("dividend_yield", "-"),
        "price_earning": company_info.get("price_earning", "-"),
        "basic_EPS": company_info.get("basic_EPS", "-"),
        "net_income": company_info.get("net_income", "-"),
        "revenue": company_info.get("revenue", "-"),
        "shares_float": company_info.get("shares_float", "-"),
        "beta": company_info.get("beta", "-")
    }
    
def get_company_info_finnhub(symbol):
    try:
        profile = finnhub_client.company_profile2(symbol=symbol)
        metrics = finnhub_client.company_basic_financials(symbol=symbol, metric='all')
        recommendation = finnhub_client.recommendation_trends(symbol=symbol)
        if recommendation and isinstance(recommendation, list):
            latest = recommendation[0]
        else:
            latest = {}
        return {
            "ipo": profile.get("ipo", "0"),
            "country": profile.get("country", "-"),
            "rating_consensus": {
                "strongBuy": latest.get("strongBuy", "0"),
                "buy": latest.get("buy", "0"),
                "hold": latest.get("hold", "0"),
                "sell": latest.get("sell", "0"),
                "strongSell": latest.get("strongSell", "0"),
                "period": latest.get("period", "0"),
            }
        }
    
    except Exception as e:
        print(f":x: Error Finnhub: {e}")
        return {
            "ipo": "-",
            "country": "-",
            "rating_consensus": {
                "strongBuy": 0,
                "buy": 0,
                "hold": 0,
                "sell": 0,
                "strongSell": 0,
                "period": "-"
            }
        }
    
def translate_prompt(prompt_text: str, target_lang: str):
    print(f"🔁 Menerjemahkan ke: {target_lang}")  # Tambah ini
    if target_lang.lower() in ["en", "english"]:
        print("⏩ Skip translasi, karena English")
        return prompt_text

    translate_instruction = f"""
    Please translate the following prompt into {target_lang.title()} in a formal, professional tone for financial/technical analysis. Keep the structure and bullet points intact.
    """

    messages = [
        {"role": "system", "content": "You are a professional financial translator."},
        {"role": "user", "content": translate_instruction + "\n\n" + prompt_text}
    ]

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        temperature=0,
        max_tokens=1500
    )

    return response.choices[0].message.content

def analyze_chart(image_bytes_list, ticker, company_info, finnhub_info, is_halal, timestamp, lang="id"):
    base_prompt = f"""
You are a professional technical stock analyst.

---

I will upload 6 stock charts of {ticker} from TradingView with various timeframes:

1. Chart 1 = 1-minute timeframe (1m)
2. Chart 2 = 3-minute timeframe (3m)
3. Chart 3 = 5-minute timeframe (5m)
4. Chart 4 = 15-minute timeframe (15m)
5. Chart 5 = 1-hour timeframe (1h)
6. Chart 6 = 1-day timeframe (1d)

Each chart includes technical indicators like RSI, MACD, Volume, candlestick patterns, and support/resistance.

---

Your task:

Based on observation of all images, provide a **concise overall analysis and summary only**. Do not analyze each timeframe separately.

Suggest a Buy or Sell if there's a clear direction. Use Hold **only if there's truly no signal or it's too risky to enter**.

Respond in this format:

- Current Price:
- Action: (Buy / Sell / Hold)
- Volume:
- Timeframe Entry:
- Buy Zone:
- Target Profit:
- Stop Loss:
- Smart Score (1–10):
- Strategy:
- Analyst Insights: (1–2 paragraphs summarizing analysis)

Use professional, concise tone.
"""

    translated_prompt = translate_prompt(base_prompt, lang)

    messages = [
        {"role": "user", "content": [{"type": "text", "text": translated_prompt}]}
    ]

    for img_bytes in image_bytes_list:
        base64_img = base64.b64encode(img_bytes).decode()
        messages[0]["content"].append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{base64_img}"
            }
        })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=1000,
        temperature=0
    )

    return response.choices[0].message.content

def run_full_analysis(ticker, intervals):
    try:
        screenshots = take_tradingview_screenshots(ticker, intervals)
        info = get_tradingview_full_data(ticker)
        company_info = info.get("company_info", {})
        result = analyze_chart(screenshots, ticker, company_info, {}, {}, {}, lang="english")
        return {
            "ticker": ticker,
            "timestamp": utc_timestamp(),
            "analysis": result,
            "company_info": company_info
        }
    except Exception as e:
        print(f"❌ Error in run_full_analysis for {ticker}: {e}")
        raise

if __name__ == "__main__":
    intervals = ["15", "60", "D"]
    tickers = ["NASDAQ:TSLA", "NASDAQ:AAPL"]

    import concurrent.futures
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tickers)) as executor:
        futures = [executor.submit(run_full_analysis, ticker, intervals) for ticker in tickers]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            print(f"\n=== Analyst Insights: {result['ticker']} ===")
            print(result["analysis"])
