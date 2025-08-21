from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import plotly.graph_objects as go
import base64
from io import BytesIO
import json
import os
import traceback
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

from tradingv import get_tradingview_full_data
from gptray3 import (
    take_tradingview_screenshots,
    analyze_chart,
    get_tradingview_full_data,
    utc_timestamp,
    check_halal_stock,
    get_company_info_finnhub
)
from finnhub import Client as FinnhubClient


app = FastAPI()

# === Konstanta ===
INTERVALS = ["15", "60", "D"]
DATA_DIR = "/app/storage/app/public/FINVIZ"

# === Dummy key jika .env tidak tersedia ===
finnhub_client = FinnhubClient(api_key=os.getenv("FINNHUB_API_KEY", "xxx"))

class SymbolRequest(BaseModel):
    symbol: str

def take_tradingview_screenshots(symbol, intervals):
    image_bytes_list = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-extensions",
                "--disable-features=VizDisplayCompositor"
            ]
        )
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        for interval in intervals:
            url = f"https://www.tradingview.com/chart/?symbol={symbol}&interval={interval}"
            print(f"🌐 Membuka chart: {url}")
            try:
                page.goto(url, timeout=60000)
                page.wait_for_timeout(8000)  # Delay untuk menunggu chart render
                screenshot = page.screenshot(full_page=True)
                image_bytes_list.append(screenshot)
                print(f"📸 Screenshot {symbol} interval {interval} berhasil.")
            except Exception as e:
                print(f"⚠️ Gagal memuat chart {interval}: {e}")
                image_bytes_list.append(None)

        browser.close()

    return image_bytes_list

def create_rating_donut(rating_data: dict) -> str | None:
    strong_buy = int(rating_data.get("strongBuy", 0))
    buy = int(rating_data.get("buy", 0))
    hold = int(rating_data.get("hold", 0))
    sell = int(rating_data.get("sell", 0))
    strong_sell = int(rating_data.get("strongSell", 0))

    total = strong_buy + buy + hold + sell + strong_sell
    if total == 0:
        return None

    labels = ["Buy", "Hold", "Sell"]
    values = [strong_buy + buy, hold, sell + strong_sell]
    colors = ["#2ECC71", "#95A5A6", "#E74C3C"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.6,
        marker=dict(colors=colors),
        textinfo="label+percent"
    )])

    fig.update_layout(
        height=400,
        width=400,
        margin=dict(t=10, b=10, l=10, r=10)
    )

    img_bytes = fig.to_image(format="png", engine="kaleido")
    base64_img = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/png;base64,{base64_img}"


@app.post("/analyze")
def analyze(req: SymbolRequest):
    symbol = req.symbol.strip()

    if ":" not in symbol:
        raise HTTPException(
            status_code=400,
            detail="Format simbol salah. Gunakan format 'EXCHANGE:SYMBOL', contoh 'NASDAQ:TSLA'."
        )

    try:
        print(f"🔍 Menganalisis simbol: {symbol}")

        # 1. Ambil data perusahaan dari TradingView
        print("📊 Mengambil data perusahaan (TradingView)...")
        company_info_data = get_tradingview_full_data(symbol)
        print("✅ Data perusahaan diperoleh.")

        # 2. Ambil data Finnhub
        print("📊 Mengambil data Finnhub...")
        raw_symbol = symbol.split(":")[-1]
        finnhub_info = get_company_info_finnhub(raw_symbol)
        print("✅ Data Finnhub diperoleh.")

        # 3. Cek status halal
        print("🧠 Mengecek status halal saham...")
        is_halal = check_halal_stock(symbol)
        print(f"✅ Status halal: {is_halal}")

        # 4. Ambil chart screenshot
        print("📸 Mengambil screenshot chart...")
        screenshots = take_tradingview_screenshots(symbol, INTERVALS)
        print("✅ Screenshot berhasil.")

        # 5. Timestamp
        timestamp = utc_timestamp()
        print(f"🕒 Timestamp sekarang: {timestamp}")

        # 6. Kirim ke GPT untuk analisis teknikal
        print("🤖 Mengirim ke AI untuk analisis...")
        result = analyze_chart(
            screenshots,
            symbol,
            company_info_data.get("company_info", {}),
            finnhub_info,
            is_halal,
            timestamp
        )
        print("✅ Analisis AI selesai.")

        # 7. Chart rating dari Finnhub
        rating_chart = create_rating_donut(finnhub_info.get("rating_consensus", {}))

        return {
            "result": result,
            "timestamp": timestamp,
            "is_halal": is_halal,
            "rating_consensus_graph_url": rating_chart
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"❌ Gagal menganalisis simbol '{symbol}': {str(e)}"
        )


@app.get("/sentiment/{ticker}")
def get_latest_sentiment(ticker: str):
    try:
        ticker = ticker.upper()
        files = [f for f in os.listdir(DATA_DIR) if f.startswith(ticker) and f.endswith(".json")]
        if not files:
            raise HTTPException(status_code=404, detail="Data tidak ditemukan untuk ticker ini.")

        latest_file = sorted(files, reverse=True)[0]
        filepath = os.path.join(DATA_DIR, latest_file)

        with open(filepath, "r", encoding="utf-8") as f:
            raw = json.load(f)

        data = raw[0] if isinstance(raw, list) else raw

        return {
            "ticker": data.get("ticker"),
            "scraped_at": data.get("scraped_at"),
            "sentiment": data.get("sentiment_summary"),
            "articles": data.get("articles")
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Terjadi kesalahan: {str(e)}")


@app.get("/rating-chart")
def get_rating_chart(symbol: str):
    try:
        raw_symbol = symbol.split(":")[-1]
        finnhub_info = get_company_info_finnhub(raw_symbol)
        rating = finnhub_info.get("rating_consensus", {})

        base64_url = create_rating_donut(rating)
        if not base64_url:
            raise HTTPException(status_code=404, detail="Rating data tidak tersedia.")

        return {"symbol": symbol, "chart_url": base64_url}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Gagal membuat grafik: {str(e)}")
