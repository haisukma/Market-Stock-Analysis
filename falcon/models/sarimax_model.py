import numpy as np
from statsmodels.tsa.statespace.sarimax import SARIMAX
from datetime import datetime
import yfinance as yf

# Tidak perlu load model file, SARIMAX diproses on-the-fly
def load_sarimax_model():
    return None

def run_sarimax_forecast(symbol, lookback):
    # Ambil data historis penutupan harian
    df = yf.download(symbol, period=f"{lookback}d")
    
    if 'Close' not in df.columns or df['Close'].dropna().empty:
         raise ValueError("Data penutupan tidak tersedia dari Yahoo Finance.")

    prices = df['Close'].dropna().values

    if len(prices) < 10:
        raise ValueError("Insufficient data for SARIMAX")

    # Fit SARIMAX dan prediksi satu langkah ke depan
    model = SARIMAX(prices, order=(1, 1, 1), seasonal_order=(0, 0, 0, 0))
    result = model.fit(disp=False)
    forecast = result.forecast(steps=1)

    return {
        "prediction": float(forecast[0]),
        "forecast": [float(forecast[0])],
        "dates": [datetime.utcnow().date().isoformat()]
    }
