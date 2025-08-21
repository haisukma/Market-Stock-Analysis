import base64
import time
import os
from datetime import datetime, timezone
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from playwright.sync_api import sync_playwright
import openai
import finnhub

# 🔐 Config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "YOUR_OPENAI_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "YOUR_FINNHUB_KEY")

client = openai.OpenAI(api_key="sk-pr")
finnhub_client = finnhub.Client(api_key="d1")

# ✅ Screenshot dari TradingView
def take_tradingview_screenshots(symbol, intervals):
    chrome_options = Options()
    chrome_options.add_argument('--user-data-dir=/Users/diajeng/Library/Application Support/Google/Chrome')
    chrome_options.add_argument('--profile-directory=Default')
    chrome_options.add_argument("--start-maximized")
    
    driver = webdriver.Chrome(options=chrome_options)
    image_bytes_list = []

    try:
        for interval in intervals:
            driver.get(f"https://www.tradingview.com/chart/?symbol={symbol}&interval={interval}")
            time.sleep(8)
            image_bytes_list.append(driver.get_screenshot_as_png())
            print(f"📸 Screenshot {symbol} - {interval} diambil")
    finally:
        driver.quit()

    return image_bytes_list

# 🧠 Ambil deskripsi dan info dari TradingView
def get_tradingview_full_data(ticker):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"https://www.tradingview.com/symbols/{ticker}/", timeout=60000)
        time.sleep(3)

        def safe_text(locator):
            try:
                return locator.inner_text().strip()
            except:
                return "N/A"

        def get_description():
            try:
                page.mouse.wheel(0, 2000)
                time.sleep(1)
                if page.locator('//button[contains(@class,"toggleDescriptionButton-")]').count():
                    page.locator('//button[contains(@class,"toggleDescriptionButton-")]').first.click()
                    time.sleep(1)
                return safe_text(page.locator('div[class*="truncatedBlockText"]').first)
            except:
                return "N/A"

        def get_info_map(widget_id, labels):
            try:
                section = page.locator(f'div[data-an-widget-id="{widget_id}"]')
                blocks = section.locator('div[class^="blockContent-"]')
                return {
                    labels[i]: safe_text(blocks.nth(i).locator('div[class^="apply-overflow-tooltip value-"]').first)
                    for i in range(len(labels))
                }
            except:
                return {}

        description = get_description()
        company_info = get_info_map("company-info-id", ["Sector", "Industry"])
        stats_info = get_info_map("key-stats-id", [
            "Market capitalization", "Dividend yield (indicated)", "Price to earning Ratio (TTM)",
            "Basic EPS (TTM)", "Net Income (FY)", "Revenue (FY)", "Shares float", "Beta (1Y)"
        ])
        employees = get_info_map("employees-section", ["Employees"]).get("Employees", "N/A")

        browser.close()

        return {
            "ticker": ticker,
            "company_info": {
                "description": description,
                "sector": company_info.get("Sector", "N/A"),
                "industry": company_info.get("Industry", "N/A"),
                "employees": employees,
                **stats_info
            }
        }

# 📊 Analisis dengan OpenAI Vision
def analyze_chart(image_bytes_list, ticker, company_info):
    full_prompt = f"""
Anda adalah seorang analis teknikal saham profesional.

---

Saya akan mengunggah {len(image_bytes_list)} gambar grafik saham {ticker} dari TradingView dengan berbagai time frame.

Setiap gambar berisi indikator teknikal seperti RSI, MACD, Volume, pola candlestick, dan support/resistance.

---

Tugas Anda:

Berdasarkan pengamatan terhadap seluruh gambar, berikan **analisis menyeluruh dan ringkasan akhir saja** tanpa membahas setiap timeframe satu per satu.

Berikan aksi Buy atau Sell jika ada indikasi arah yang dominan.
Gunakan “Hold” **hanya jika benar-benar tidak ada sinyal teknikal yang mendukung arah tertentu**, dan entry dianggap terlalu berisiko atau tidak jelas.

Berikan kesimpulan analisis teknikal dalam format berikut:

- Current Price: Harga saat ini
- Action: (Buy / Sell / Hold)
- Volume: Volume yang terlihat di chart
- Timeframe Entry: (timeframe paling optimal untuk entry saat ini)
- Buy Zone: (zona harga entry ideal)
- Target Profit: (target realistis berdasarkan analisis teknikal)
- Stop Loss: (level cut-loss berdasarkan support teknikal)
- Smart Score: (penilaian peluang dari skala 1-10)
- Strategy: (jelaskan pendekatan seperti buy on breakout, buy on pullback, scalping, dll)
- Analyst Insights: Penjelasan singkat (1-2 paragraf) yang menyimpulkan analisis secara profesional dan ringkas

Gunakan gaya penulisan profesional dan ringkas, seperti seorang analis teknikal yang berpengalaman.
"""

    messages = [
        {"role": "user", "content": [{"type": "text", "text": full_prompt}]}
    ]

    for img in image_bytes_list:
        base64_img = base64.b64encode(img).decode()
        messages[0]["content"].append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{base64_img}"}
        })

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        max_tokens=1000,
        temperature=0
    )

    return response.choices[0].message.content

# 🕓 Timestamp UTC
def utc_timestamp():
    now = datetime.now(timezone.utc)
    return {"date": now.strftime("%Y-%m-%d"), "time": now.strftime("%H:%M UTC")}

# 🌍 Info dari Finnhub (tambahan)
def get_company_info_finnhub(symbol):
    try:
        profile = finnhub_client.company_profile2(symbol=symbol)
        recommendation = finnhub_client.recommendation_trends(symbol=symbol)
        latest = recommendation[0] if recommendation else {}

        return {
            "ipo": profile.get("ipo", "-"),
            "country": profile.get("country", "-"),
            "rating_consensus": {
                "strongBuy": latest.get("strongBuy", "-"),
                "buy": latest.get("buy", "-"),
                "hold": latest.get("hold", "-"),
                "sell": latest.get("sell", "-"),
                "strongSell": latest.get("strongSell", "-"),
                "period": latest.get("period", "-")
            }
        }
    except Exception as e:
        print(f"❌ Finnhub error: {e}")
        return {}

# 🧪 Untuk test manual
if __name__ == "__main__":
    ticker = "NASDAQ:TSLA"
    intervals = ["5m", "15m", "30m", "1h", "1d"]  # Simulasi input dari form Laravel

    print("📥 Ambil screenshot...")
    screenshots = take_tradingview_screenshots(ticker, intervals)
    
    print("📊 Ambil info perusahaan...")
    company_info = get_tradingview_full_data(ticker)

    print("🧠 Analisa AI...")
    result = analyze_chart(screenshots, ticker, company_info["company_info"])

    print("\n=== Hasil Analisa ===\n")
    print(result)
