from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import plotly.graph_objects as go
import base64
from io import BytesIO
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
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
import os
import traceback

app = FastAPI()

finnhub_client = FinnhubClient(api_key=os.getenv("FINNHUB_API_KEY", "xxx"))
INTERVALS = ["15", "60", "D"]

class SymbolRequest(BaseModel):
    symbol: str

def get_language(request: Request) -> str:
    lang = request.headers.get("accept-language", "id").lower()
    mapping = {
        "id": "indonesian",
        "en": "english",
        "ar": "arabic",
        "da": "danish",
        "nl": "dutch",
        "de": "german",
        "it": "italian",
        "ja": "japanese",
        "pl": "polish",
        "pt": "portuguese",
        "fr": "french",
        "ru": "russian",
        "es": "spanish",
    }
    for code, lang_name in mapping.items():
        if code in lang:
            return lang_name
    return "english"

def utc_timestamp():
    utc_now = datetime.now(timezone.utc)
    return utc_now.strftime("%Y-%m-%d %H:%M UTC")

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
                page.wait_for_timeout(8000)
                screenshot = page.screenshot(full_page=True)
                image_bytes_list.append(screenshot)
                print(f"📸 Screenshot {symbol} interval {interval} berhasil.")
            except Exception as e:
                print(f"⚠️ Gagal memuat chart {interval}: {e}")
                image_bytes_list.append(None)

        browser.close()
    return image_bytes_list

def create_rating_donut(rating_data: dict, lang: str = "english") -> str | None:
    strong_buy = int(rating_data.get("strongBuy", 0))
    buy = int(rating_data.get("buy", 0))
    hold = int(rating_data.get("hold", 0))
    sell = int(rating_data.get("sell", 0))
    strong_sell = int(rating_data.get("strongSell", 0))
    total = strong_buy + buy + hold + sell + strong_sell

    if total == 0:
        return None

    # 🌐 Alih bahasa label
    label_map = {
        "english": {"Buy": "Buy", "Hold": "Hold", "Sell": "Sell"},
        "indonesian": {"Buy": "Beli", "Hold": "Tahan", "Sell": "Jual"},
        "dutch": {"Buy": "Kopen", "Hold": "Vasthouden", "Sell": "Verkopen"},
        "arabic": {"Buy": "شراء", "Hold": "احتفاظ", "Sell": "بيع"},
        "french": {"Buy": "Acheter", "Hold": "Conserver", "Sell": "Vendre"},
        "german": {"Buy": "Kaufen", "Hold": "Halten", "Sell": "Verkaufen"},
        "spanish": {"Buy": "Comprar", "Hold": "Mantener", "Sell": "Vender"},
        "russian": {"Buy": "Покупать", "Hold": "Удерживать","Sell": "Продавать"},
        "italian": {"Buy": "Acquistare", "Hold": "Mantenere", "Sell": "Vendere"},
        "danish": {"Buy": "Køb", "Hold": "Behold", "Sell": "Sælg"},
        "portuguese" :{"Buy": "Comprar", "Hold": "Manter","Sell": "Vender"},
        "japanese":{"Buy": "買い", "Hold": "保有","Sell": "売り"},
        "polish":{"Buy": "Kup", "Hold": "Trzymaj", "Sell": "Sprzedaj"},

        # tambahkan bahasa lain jika perlu
    }

    labels_dict = label_map.get(lang.lower(), label_map["english"])

    labels = [
        labels_dict["Buy"],
        labels_dict["Hold"],
        labels_dict["Sell"]
    ]
    values = [strong_buy + buy, hold, sell + strong_sell]
    colors = ["#2ECC71", "#95A5A6", "#E74C3C"]

    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        hole=0.6,
        marker=dict(colors=colors),
        textinfo="label+percent"
    )])

    fig.update_layout(height=400, width=400, margin=dict(t=10, b=10, l=10, r=10))
    img_bytes = fig.to_image(format="png", engine="kaleido")
    base64_img = base64.b64encode(img_bytes).decode("utf-8")
    return f"data:image/png;base64,{base64_img}"

@app.post("/analyze")
def analyze(req: SymbolRequest, request: Request):
    symbol = req.symbol.strip()
    lang = get_language(request)

    if ":" not in symbol:
        raise HTTPException(
            status_code=400,
            detail="Format simbol salah. Gunakan format 'EXCHANGE:SYMBOL', contoh 'NASDAQ:TSLA'."
        )

    try:
        print(f"🔍 Simbol: {symbol} | Bahasa: {lang}")

        company_info = get_tradingview_full_data(symbol)
        raw_symbol = symbol.split(":")[-1]
        finnhub_info = get_company_info_finnhub(raw_symbol)
        is_halal = check_halal_stock(symbol)
        screenshots = take_tradingview_screenshots(symbol, INTERVALS)
        timestamp = utc_timestamp()

        result = analyze_chart(
            screenshots,
            symbol,
            company_info.get("company_info", {}),
            finnhub_info,
            is_halal,
            timestamp,
            lang
        )

        base64_url = create_rating_donut(finnhub_info.get("rating_consensus", {}), lang=lang) or None

        return {
            "result": result,
            "timestamp": timestamp,
            "is_halal": is_halal,
            "rating_consensus_graph_url": base64_url
        }

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"❌ Gagal menganalisa simbol '{symbol}': {str(e)}"
        )

@app.get("/rating-chart")
def get_rating_chart(symbol: str, request: Request):
    try:
        lang = get_language(request)
        raw_symbol = symbol.split(":")[-1]
        finnhub_info = get_company_info_finnhub(raw_symbol)
        rating = finnhub_info.get("rating_consensus", {})

        base64_url = create_rating_donut(rating, lang=lang)
        if not base64_url:
            raise HTTPException(status_code=404, detail="Rating data tidak tersedia.")

        return {"symbol": symbol, "chart_url": base64_url}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Gagal membuat grafik: {str(e)}")
