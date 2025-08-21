from collections import Counter
import requests
import time
import re

ALPHA_KEY = "F8A2XKW6MPZ3239Z"

tickers = [
    "IBM", "AAPL", "MSFT", "AMZN", "TSLA", "NVDA", "GOOGL", "META", "BA", "JPM",
    "PLTR", "PRGO", "AMD", "NFLX", "DIS", "VZ", "INTC", "CSCO", "WMT", "KO"
]

titles = []

def normalize_title(title):
    title = title.lower().strip()
    title = re.sub(r'[^\w\s]', '', title)  # hapus tanda baca
    title = re.sub(r'\s+', ' ', title)     # hapus spasi berlebih
    
    replacements = {
        "admin": "administrative",
        "exec": "executive",
        "vp": "vice president",
        "ceo": "chief executive officer",
        "president and ceo": "chief executive officer and president",
        "cfo": "chief financial officer",
        "coo": "chief operating officer",
        "cto": "chief technology officer",
        "cio": "chief information officer",
        "cao": "chief accounting officer",
        "vp": "vice president",
    }
    words = title.split()
    words = [replacements.get(w, w) for w in words]
    return " ".join(words)

for t in tickers:
    url = f"https://www.alphavantage.co/query?function=INSIDER_TRANSACTIONS&symbol={t}&apikey={ALPHA_KEY}"
    r = requests.get(url).json()

    if "data" not in r:
        print(f"{t} - no data:", r)
        time.sleep(15)
        continue

    for trx in r["data"]:
        raw_titles = trx.get("executive_title", "")
        for part in raw_titles.split(","):
            title = normalize_title(part)
            if title:
                titles.append(title)

    time.sleep(1) 

for title, count in Counter(titles).most_common():
    print(f"{title}: {count}")

unique_titles = sorted(set(titles))
print("\nUnique titles:", unique_titles)