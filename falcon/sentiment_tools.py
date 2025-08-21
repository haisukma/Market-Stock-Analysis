from textblob import TextBlob

def analyze_sentiment(text):
    blob = TextBlob(text)
    polarity = blob.sentiment.polarity
    subjectivity = blob.sentiment.subjectivity

    if polarity > 0.1:
        sentiment_label = "Positive"
        emoji = "😊"
    elif polarity < -0.1:
        sentiment_label = "Negative"
        emoji = "😠"
    else:
        sentiment_label = "Neutral"
        emoji = "😐"

    return polarity, subjectivity, sentiment_label, emoji

def calculate_combined_sentiment(article_texts):
    combined_text = " ".join(article_texts)
    if not combined_text.strip():
        return None

    polarity, subjectivity, sentiment_label, emoji = analyze_sentiment(combined_text)
    return {
        'polarity': round(polarity, 3),
        'subjectivity': round(subjectivity, 3),
        'sentiment': sentiment_label,
        'emoji': emoji
    }
