from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time, os

def open_ticker(driver, wait, symbol: str):
    # 1️⃣ Klik tombol Search di header
    search_btn = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'button.js-header-search-button[aria-label="Search"]'))
    )
    search_btn.click()

    # 2️⃣ Ketik simbol
    input_box = wait.until(
        EC.presence_of_element_located(
            (By.CSS_SELECTOR, 'input[aria-label="Search"], input[data-role="search-input"]'))
    )
    input_box.clear()
    input_box.send_keys(symbol)
    time.sleep(0.4)                   # beri waktu dropdown terisi

    # 3️⃣ Klik baris pertama hasil dropdown
    first_item = wait.until(
        EC.element_to_be_clickable(
            (By.CSS_SELECTOR, 'div[data-role="list-item"]:first-child'))
    )
    first_item.click()

    # 4️⃣ Tunggu URL chart memuat ticker tsb
    wait.until(EC.url_contains(symbol.lower()))
    print(f"✅ Chart {symbol} terbuka")

# ──── SETUP WEBDRIVER DENGAN PROFIL YANG SUDAH LOGIN ───────────────────────────
opts = Options()
opts.add_argument(r'--user-data-dir="/Users/diajeng/Library/Application Support/Google/Chrome"')
opts.add_argument('--profile-directory=Default')
opts.add_argument('--start-maximized')

with webdriver.Chrome(options=opts) as driver:
    wait = WebDriverWait(driver, 20)

    driver.get("https://www.tradingview.com")
    if "accounts/signin" in driver.current_url.lower():
        raise RuntimeError("Profil belum login - login manual dulu.")

    driver.get("https://www.tradingview.com/chart/")   # buka canvas chart

    # ── GANTI TICKER DI SINI ───────────────────────────────────────────────────
    open_ticker(driver, wait, "PLTR")

    input("📈 Chart sudah di PLTR. Tekan Enter untuk quit …")
