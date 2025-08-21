import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.preprocessing import MinMaxScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from tensorflow.keras.callbacks import EarlyStopping
import finnhub
import openai

# def fetch_price_data(symbol="AAPL", lookback_days=100):
#     client = finnhub.Client(api_key="d1eb2mhr01qjssrj0ahgd1eb2mhr01qjssrj0ai0")
#     finnhub_client = finnhub.Client(api_key="d1eb2mhr01qjssrj0ahgd1eb2mhr01qjssrj0ai0")
#     # client = finnhub.Client(api_key=os.getenv("FINNHUB_API_KEY", "demo"))
#     end_time = int(datetime.utcnow().timestamp())
#     start_time = int((datetime.utcnow() - timedelta(days=lookback_days)).timestamp())
#     candles = client.stock_candles(symbol, 'D', _from=start_time, to=end_time)

#     if candles['s'] != 'ok':
#         raise ValueError("Gagal ambil data harga dari Finnhub")

#     prices = candles['c']
#     return np.array(prices).reshape(-1, 1)


# def fetch_price_data(symbol):
#     filename = f"{symbol}.csv"
#     if not os.path.exists(filename):
#         raise FileNotFoundError(f"File {filename} tidak ditemukan. Silakan unduh dulu dari Yahoo Finance.")

#     df = pd.read_csv(filename)
#     if 'Close' not in df.columns:
#         raise ValueError("Kolom 'Close' tidak ditemukan dalam file CSV.")

#     prices = df['Close'].dropna().values.reshape(-1, 1)  # Penting: reshape untuk scaler dan LSTM
#     return prices
def fetch_price_data(symbol):
    df = pd.read_csv(f"{symbol}.csv")

    # Bersihkan nama kolom
    df.columns = [col.strip() for col in df.columns]

    if "Close/Last" not in df.columns:
        raise ValueError("Kolom 'Close/Last' tidak ditemukan dalam file CSV.")

    # Hilangkan simbol dollar dan konversi ke float
    df["Close/Last"] = df["Close/Last"].replace('[\$,]', '', regex=True).astype(float)

    prices = df["Close/Last"].dropna().values.reshape(-1, 1)
    return prices

def build_and_train_model(prices):
    scaler = MinMaxScaler()
    prices_scaled = scaler.fit_transform(prices)

    X, y = [], []
    for i in range(30, len(prices_scaled)):
        X.append(prices_scaled[i-30:i])
        y.append(prices_scaled[i])

    X, y = np.array(X), np.array(y)

    model = Sequential()
    model.add(LSTM(50, return_sequences=False, input_shape=(X.shape[1], 1)))
    model.add(Dense(1))
    model.compile(optimizer='adam', loss='mse')

    model.fit(X, y, epochs=20, batch_size=16, validation_split=0.2,
              callbacks=[EarlyStopping(patience=5)])

    return model

def main():
    symbol = "AAPL"  # Bisa diganti jadi input atau argumen
    prices = fetch_price_data(symbol)
    model = build_and_train_model(prices)

    os.makedirs("models", exist_ok=True)
    model.save("models/lstm_model.keras")
    print("✅ Model saved at models/lstm_model.h5")

if __name__ == "__main__":
    main()