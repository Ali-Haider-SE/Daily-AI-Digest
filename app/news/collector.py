from app.news.rss import collect_rss
from app.news.newsapi import collect_newsapi

def collect_news(settings):
    return (collect_rss()+collect_newsapi(settings.news_api_key,settings.request_timeout))[:settings.max_news_items]
