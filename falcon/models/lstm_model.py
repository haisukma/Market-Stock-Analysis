import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model
from datetime import datetime
from sklearn.preprocessing import MinMaxScaler
import yfinance as yf 
import os

# Load model LSTM dari file lokal
def load_lstm_model():
    model_path = "models/lstm_model.h5"
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"LSTM model not found at {model_path}")
    return load_model(model_path, compile=False) 

# Ambil harga penutupan terakhir dari file CSV
def load_recent_prices(csv_path="AAPL.csv", window_size=30):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found at {csv_path}")

    df = pd.read_csv(csv_path)
    
    if 'Close' not in df.columns:
        raise ValueError("Kolom 'Close' tidak ditemukan dalam file CSV.")

    close_prices = df['Close'].dropna().values

    if len(close_prices) < window_size:
        raise ValueError(f"Butuh minimal {window_size} data harga untuk prediksi.")

    return close_prices[-window_size:]  # ambil 30 terakhir

# Prediksi harga berikutnya menggunakan model
def predict_next_price(model, recent_prices):
    scaler = MinMaxScaler()
    prices_scaled = scaler.fit_transform(recent_prices.reshape(-1, 1))

    input_sequence = np.expand_dims(prices_scaled, axis=0)  # bentuk: (1, 30, 1)
    prediction_scaled = model.predict(input_sequence)
    prediction = scaler.inverse_transform(prediction_scaled)

    return float(prediction[0][0])

def run_lstm_forecast(csv_path="data/AAPL.csv", model_path="models/lstm_model.h5", window_size=30):
    model = load_model(model_path, compile=False)
    df = pd.read_csv(csv_path)

    if 'Close' not in df.columns:
        if 'Close/Last' in df.columns:
            df.rename(columns={'Close/Last': 'Close'}, inplace=True)
        else:
            raise ValueError("Kolom 'Close' atau 'Close/Last' tidak ditemukan dalam file CSV.")

    df['Close'] = df['Close'].replace(r'[\$,]', '', regex=True)
    df['Close'] = pd.to_numeric(df['Close'], errors='coerce')  # ubah yang gagal jadi NaN
    close_prices = df['Close'].dropna().values  # hanya data numerik yang valid

    if len(close_prices) < window_size:
        raise ValueError(f"Butuh minimal {window_size} data harga untuk prediksi.")

    recent_prices = close_prices[-window_size:]
    scaler = MinMaxScaler()
    prices_scaled = scaler.fit_transform(recent_prices.reshape(-1, 1))

    input_sequence = np.expand_dims(prices_scaled, axis=0)
    prediction_scaled = model.predict(input_sequence)
    prediction = scaler.inverse_transform(prediction_scaled)

    return float(prediction[0][0])

def main():
    model = load_lstm_model()
    recent_prices = load_recent_prices()

    predicted_price = predict_next_price(model, recent_prices)
    today = datetime.utcnow().date().isoformat()

    print(f"📅 Tanggal prediksi: {today}")
    print(f"📈 Prediksi harga berikutnya: ${predicted_price:.2f}")
 


    
if __name__ == "__main__":
    main()
