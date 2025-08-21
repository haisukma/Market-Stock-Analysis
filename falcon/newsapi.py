import requests

API_KEY = '82729f6513bb4edc8ec221983d75e7e3'

def get_news(query, language='en', page_size=5):
    url = 'https://newsapi.org/v2/everything'
    params = {
        'q': query, 
        'language': language, 
        'pageSize': page_size,
        'apiKey': API_KEY
    }
    response = requests.get(url, params=params)
    data = response.json()
    if data['status'] != 'ok':
        print("Error:", data.get('message'))
        return []
    return data['articles']

articles = get_news('ASII.JK')

for i, article in enumerate(articles):
    print(f"{i+1}. {article['title']}")
    print(f"   Source: {article['source']['name']}")
    print(f"   Published At: {article['publishedAt']}")
    print(f"   URL: {article['url']}\n")