import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model
from datetime import datetime, timezone
from sklearn.preprocessing import MinMaxScaler
import os

def load_lstm_model():
    model_path = "models/lstm_model.h5"
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"LSTM model not found at {model_path}")
    return load_model(model_path, compile=False) 

# def load_recent_prices(csv_path="AAPL.csv", window_size=30):
#     if not os.path.exists(csv_path):
#         raise FileNotFoundError(f"CSV file not found at {csv_path}")

#     df = pd.read_csv(csv_path)
    
#     if 'Close' not in df.columns:
#         raise ValueError("Kolom 'Close' tidak ditemukan dalam file CSV.")

#     close_prices = df['Close'].dropna().values

#     if len(close_prices) < window_size:
#         raise ValueError(f"Butuh minimal {window_size} data harga untuk prediksi.")

#     return close_prices[-window_size:]
def load_recent_prices(csv_path="AAPL.csv", window_size=30):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found at {csv_path}")

    df = pd.read_csv(csv_path)

    if 'Close/Last' not in df.columns:
        raise ValueError(f"Kolom 'Close/Last' tidak ditemukan dalam file CSV. Kolom yang ada: {df.columns.tolist()}")

    # Bersihkan simbol dolar dan konversi ke float
    close_prices = (
        df['Close/Last']
        .astype(str)
        .str.replace('$', '', regex=False)
        .astype(float)
        .dropna()
        .values
    )

    if len(close_prices) < window_size:
        raise ValueError(f"Butuh minimal {window_size} data harga untuk prediksi.")

    return close_prices[-window_size:]

def predict_next_price(model, recent_prices):
    scaler = MinMaxScaler()
    prices_scaled = scaler.fit_transform(recent_prices.reshape(-1, 1))

    input_sequence = np.expand_dims(prices_scaled, axis=0)  # (1, 30, 1)
    prediction_scaled = model.predict(input_sequence)
    prediction = scaler.inverse_transform(prediction_scaled)

    return float(prediction[0][0])

def main():
    model = load_lstm_model()
    recent_prices = load_recent_prices()
    predicted_price = predict_next_price(model, recent_prices)
    today = datetime.now(timezone.utc).date().isoformat()

    print(f"📅 Tanggal prediksi: {today}")
    print(f"📈 Prediksi harga berikutnya: ${predicted_price:.2f}")

if __name__ == "__main__":
    main()
