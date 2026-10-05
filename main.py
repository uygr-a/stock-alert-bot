import os
import threading
import requests
import yfinance as yf
import pandas as pd
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "AI-Powered Market Intelligence Bot Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Gemini / OpenAI API Key entegrasyonu için:
AI_API_KEY = os.environ.get("GEMINI_API_KEY") 

# Otomatik bildirim gönderilecek Telegram Chat ID'si
USER_CHAT_ID = None

# --- GELİŞMİŞ HABER VE SENTIMENT ANALİZİ ---
def analyze_news_impact(ticker, news_headline):
    """
    Haber metnini ve başlığını Yapay Zeka / Kurallı NLP analizi ile değerlendirir.
    Satın alma, birleşme, büyük anlaşma gibi anahtar kelimeleri tespit eder.
    """
    critical_keywords = ["satın al", "acquisition", "merger", "anlaşma", "contract", "buyout", "kar artışı", "patents"]
    headline_lower = news_headline.lower()
    
    score = 0
    is_critical = False
    
    for kw in critical_keywords:
        if kw in headline_lower:
            score += 5
            is_critical = True
            break
            
    return {"score": score, "is_critical": is_critical}

# --- ARKA PLAN OTOMATİK HABER VE FIRSAT DİNLEYİCİSİ ---
def auto_market_scanner(app):
    global USER_CHAT_ID
    if not USER_CHAT_ID:
        return # Kullanıcı henüz /start demediği için ID yok
        
    print("Arka plan AI & Haber taraması yapılıyor...")
    
    # 1. Taranacak hisselerin haber akışı kontrol edilir
    # 2. Kritik bir haber veya hacim patlaması bulunursa bildirim atılır
    
    # Örnek kritik bildirim senaryosu:
    # app.bot.send_message(chat_id=USER_CHAT_ID, text="🚨 KRİTİK HABER SİNYALİ! ...")

# --- MAIN ---
if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        
        # Arka plan otomatik tarayıcı (Her 5 dakikada bir çalışır)
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=lambda: auto_market_scheduler(app), trigger="interval", minutes=5)
        scheduler.start()
        
        app.run_polling(drop_pending_updates=True, close_loop=False)
