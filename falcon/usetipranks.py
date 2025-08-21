import base64
import fitz
import re
import openai
import requests
import finnhub
import yfinance as yf
import time
import os
from playwright.sync_api import sync_playwright
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
    
client = openai.OpenAI(api_key="sk-proj-e6")
finnhub_client = finnhub.Client(api_key="d1eb2")

TIP_USER = "diajengmahai@baliproject.id"   # ← e-mail TipRanks
TIP_PASS = "Komariyah70!"                  # ← password
LOGIN_URL = "https://www.tipranks.com"

def take_tipranks_screenshots(symbol:str,
                              output_folder:str="./screenshots"):
    """login → buka halaman forecast saham di TipRanks → screenshot"""
    opts = Options()
    opts.add_argument("--start-maximized")     # debug; ganti "--headless=new" jika perlu
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()),
                              options=opts)
    wait = WebDriverWait(driver, 20)
    os.makedirs(output_folder, exist_ok=True)

    try:
        # ── login ───────────────────────────────────────────────────────
        driver.get(LOGIN_URL)
        wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'button i.icon-manWithCircle2'))).click()
        wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//span[normalize-space()="Sign In" or normalize-space()="Sign in"]'))
        ).click()
        wait.until(EC.url_contains("/sign-in"))
        wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'input[type="email"][placeholder="Example: johndoe@gmail.com"]'))
        ).send_keys(TIP_USER)
        pwd = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'input[type="password"][placeholder="Enter Your Password"]'))
        )
        pwd.click(); pwd.send_keys(TIP_PASS)
        wait.until(EC.element_to_be_clickable(
            (By.XPATH, '//button[span[normalize-space()="Sign In"]]'))).click()
        wait.until(EC.url_contains("/dashboard"))

        # ── search ticker & buka forecast ──────────────────────────────
        # klik container search
        wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'div.css-1hwfws3.trselect__value-container'))).click()
        box = wait.until(EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'input[placeholder="Type Expert or Stock"]')))
        box.send_keys(symbol); time.sleep(0.5)
        first_opt = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'div.trselect__option, div.css-1n7v3ny-option')))
        first_opt.click()

        # tunggu konten forecast siap
        wait.until(EC.presence_of_element_located(
            (By.XPATH, '//*[@id="root"]/div[2]/div[4]/div[3]')))
        time.sleep(1)  # ekstra buffer untuk render

        # ── simpan screenshot ──────────────────────────────────────────
        fname = os.path.join(output_folder, f"{symbol.lower()}_forecast.png")
        driver.save_screenshot(fname)
        print("📸 Screenshot TipRanks disimpan:", fname)

        # ── klik tab Overview ───────────────────────────────────
        overview_link = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            f'//a[span[normalize-space()="Overview"] '
            f'and contains(@href,"/stocks/{symbol.lower()}")]')))
        overview_link.click()

        # 1️⃣  tunggu sampai benar-benar di halaman Overview
        wait.until(lambda d: d.current_url.rstrip('/') == 
                            f"https://www.tipranks.com/stocks/{symbol.lower()}")

        time.sleep(3)        # buffer kecil agar layout stabil

        # 2️⃣  screenshot Overview
        f_overview = os.path.join(output_folder,
                                f"{symbol.lower()}_overview.png")
        driver.save_screenshot(f_overview)
        print("📸 Overview disimpan:", f_overview)

    finally:
        driver.quit()

def load_screenshots(folder_path: str, ticker: str):
    """
    Kembalikan list bytes untuk forecast & overview (jika ada keduanya).
    """
    names = [f"{ticker.lower()}_forecast.png",
             f"{ticker.lower()}_overview.png"]
    images = []
    for nm in names:
        fp = os.path.join(folder_path, nm)
        if os.path.exists(fp):
            with open(fp, "rb") as f:
                images.append(f.read())
    if not images:
        raise FileNotFoundError("Tidak ada screenshot yang ditemukan.")
    return images

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


# def get_company_info_yfinance(ticker):
#     try:
#         stock = yf.Ticker(ticker)
#         print(f":inbox_tray: Mengambil data untuk ticker: {ticker}")
#         info = stock.info
#         company_info = {
#             "about": info.get("longBusinessSummary", "Tidak tersedia"),
#             "employees": info.get("fullTimeEmployees", "Tidak tersedia"),
#             "sector": info.get("sector", "Tidak tersedia"),
#             "eps_trailing": info.get("trailingEps", "Tidak tersedia")
#         }
#         return company_info
    
#     except Exception as e:
#         print(f":x: Gagal mengambil data untuk {ticker}: {e}")
#         return {
#             "about": "",
#             "employees": "",
#             "sector": "",
#             "eps_trailing": ""
#         }
    
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
            "ipo": profile.get("ipo", "-"),
            "country": profile.get("country", "-"),
            "rating_consensus": {
                "strongBuy": latest.get("strongBuy", "-"),
                "buy": latest.get("buy", "-"),
                "hold": latest.get("hold", "-"),
                "sell": latest.get("sell", "-"),
                "strongSell": latest.get("strongSell", "-"),
                "period": latest.get("period", "-"),
            }
        }
    
    except Exception as e:
        print(f":x: Error Finnhub: {e}")
        return {
            "ipo": "-",
            "country": "-",
            "rating_consensus": {}
        }
    
def analyze_chart(image_bytes_list, ticker, company_info):
    # zoya_info = check_zoya_api(ticker)

    full_prompt = f"""
    Anda adalah seorang analis teknikal saham profesional.

    ---

    Saya akan mengunggah 1 gambar grafik saham {ticker} dari TipRanks dengan berbagai time frame:

    Gambar ini mencakup pandangan analis terhadap saham, seperti konsensus (Buy/Hold/Sell), target harga, potensi upside, dan grafik distribusi rating. 

    ---

    Tugas Anda:

    Berdasarkan pengamatan terhadap seluruh gambar, berikan **analisis menyeluruh dan ringkasan akhir saja** tanpa membahas setiap timeframe satu per satu.

    Berikan aksi Buy atau Sell jika ada indikasi arah yang dominan.  
    Gunakan “Hold” **hanya jika benar-benar tidak ada sinyal teknikal yang mendukung arah tertentu**, dan entry dianggap terlalu berisiko atau tidak jelas.

    Berikan kesimpulan analisis teknikal dalam format berikut:

    - Aksi: (Buy / Sell / Hold)
    - Timeframe Entry: (timeframe paling optimal untuk entry saat ini)
    - Buy Zone: (zona harga entry ideal)
    - Target Profit: (target realistis berdasarkan analisis teknikal)
    - Stop Loss: (level cut-loss berdasarkan support teknikal)
    - Smart Score: (penilaian peluang dari skala 1-10)
    - Strategi: (jelaskan pendekatan seperti buy on breakout, buy on pullback, scalping, dll)

    Gunakan gaya penulisan profesional dan ringkas, seperti seorang analis teknikal yang berpengalaman.
    """

    messages = [
        {"role": "user", "content": [{"type": "text", "text": full_prompt}]}
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