import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from sentiment_tools import calculate_combined_sentiment

def scrape_finviz_news(ticker):
    url = f'https://finviz.com/quote.ashx?t={ticker}'
    headers = {'User-Agent': 'Mozilla/5.0'}

    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')

    news_table = soup.find('table', {'id': 'news-table'})
    rows = news_table.find_all('tr') if news_table else []

    articles = []
    last_date = None

    for row in rows:
        cols = row.find_all('td')
        if len(cols) >= 2:
            dt_text = cols[0].get_text(strip=True)
            title = cols[1].get_text(strip=True)
            a_tag = cols[1].find('a')
            link = a_tag['href'] if a_tag else ''

            # Format bisa "Jul-14-25 03:44PM" atau hanya waktu
            if len(dt_text.split()) == 2:
                date_str, time_str = dt_text.split()
                last_date = date_str
            else:
                time_str = dt_text
                date_str = last_date

            articles.append({
                'ticker': ticker,
                'date': date_str,
                'time': time_str,
                'title': title,
                'url': link
            })

    return articles

def save_to_laravel_storage(ticker, articles):
    today = datetime.today().strftime('%Y-%m-%d')
    base_dir = os.path.join('storage', 'app', 'public', 'FINVIZ')
    os.makedirs(base_dir, exist_ok=True)

    # Ambil daftar judul berita saja (atau bisa juga digabung dengan deskripsi jika tersedia)
    article_texts = [article['title'] for article in articles if 'title' in article]

    sentiment_summary = calculate_combined_sentiment(article_texts) or {
        "sentiment": "-",
        "emoji": "",
        "polarity": "-",
        "subjectivity": "-"
    }

    data = {
        "ticker": ticker,
        "scraped_at": today,
        "sentiment_summary": sentiment_summary,
        "articles": articles
    }

    filepath = os.path.join(base_dir, f'{ticker}_{today}.json')

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"✅ Data saved to {filepath}")

if __name__ == '__main__':
    ticker = 'AAPL'
    print(f"🔍 Scraping Finviz news for {ticker}...")
    articles = scrape_finviz_news(ticker)
    save_to_laravel_storage(ticker, articles)
