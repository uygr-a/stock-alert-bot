import os
import threading
import requests
import feedparser
import yfinance as yf
import pandas as pd
import google.generativeai as genai
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# Render Keep-Alive Sunucusu
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "AI-Powered Free Signal Bot Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

# API VE TOKEN AYARLARI
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") # Render Environment Variable kısmından ekleyebilirsiniz

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

USER_CHAT_ID = None
PROCESSED_NEWS = set() # Tekrar eden haberleri engellemek için

STOCKS = ["THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "NVDA", "AAPL", "TSLA"]

# --- 1. ÜCRETSİZ GEMINI AI HABER ANALİZİ ---
def analyze_news_with_gemini(symbol, headline):
    """Haberin hisseye etkisini tamamen ücretsiz Gemini AI ile puanlar."""
    if not GEMINI_API_KEY:
        return {"impact": "NÖTR", "score": 5, "summary": "Gemini API Key tanımlanmamış."}

    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = (
            f"Sen profesyonel bir borsa analistisin. {symbol} hissesi için şu haberi analiz et:\n"
            f"Haber: '{headline}'\n\n"
            "Lütfen şu formatta kısa ve net yanıt ver:\n"
            "ETKİ: [POZİTİF / NEGATİF / NÖTR]\n"
            "PUAN: [1-10 arası bir sayı]\n"
            "ÖZET: [Haberin hisseye etkisini anlatan 1 cümle]"
        )
        response = model.generate_content(prompt)
        text = response.text

        is_positive = "POZİTİF" in text.upper()
        return {
            "is_positive": is_positive,
            "text": text
        }
    except Exception as e:
        print(f"Gemini Hata: {e}")
        return None

# --- 2. BIST VE ABD ÜCRETSİZ HABER TARAYICI ---
def fetch_latest_news(symbol):
    clean_symbol = symbol.replace('.IS', '')
    rss_url = f"https://news.google.com/rss/search?q={clean_symbol}+hisse+or+KAP&hl=tr&gl=TR&ceid=TR:tr"
    feed = feedparser.parse(rss_url)
    
    if feed.entries:
        latest = feed.entries[0]
        news_id = latest.link
        if news_id not in PROCESSED_NEWS:
            PROCESSED_NEWS.add(news_id)
            return {"title": latest.title, "link": latest.link}
    return None

# --- 3. TEKNİK MANTIK İLE HABER BİRLEŞTİRME ---
def check_technical_setup(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        stock = yf.Ticker(symbol, session=session)
        df = stock.history(period="5d", interval="1h")
        
        if len(df) < 10:
            return None
            
        current_price = df['Close'].iloc[-1]
        rsi = 100 - (100 / (1 + (df['Close'].diff().where(df['Close'].diff() > 0, 0).rolling(14).mean() / 
                                 (-df['Close'].diff().where(df['Close'].diff() < 0, 0)).rolling(14).mean()).iloc[-1]))
        
        return {"price": round(current_price, 2), "rsi": round(rsi, 1)}
    except:
        return None

# --- 4. ARKA PLAN OTOMATİK BİLDİRİM MOTORU ---
def auto_market_scanner(app):
    global USER_CHAT_ID
    if not USER_CHAT_ID:
        return

    for symbol in STOCKS:
        news = fetch_latest_news(symbol)
        if news:
            clean_symbol = symbol.replace('.IS', '')
            ai_res = analyze_news_with_gemini(clean_symbol, news['title'])
            
            if ai_res and ai_res.get("is_positive"):
                tech = check_technical_setup(symbol)
                if tech:
                    msg = (
                        f"🚨 *YAPAY ZEKÂ & HABER SİNYALİ (KRİTİK)*\n───────────────────\n"
                        f"📌 *Hisse:* `{clean_symbol}` | Fiyat: `{tech['price']}` | RSI: `{tech['rsi']}`\n\n"
                        f"📰 *Haber:* _{news['title']}_\n\n"
                        f"🤖 *AI Değerlendirmesi:*\n{ai_res['text']}\n───────────────────"
                    )
                    # Telegram'a Otomatik Bildirim Gönder
                    app.loop.create_task(app.bot.send_message(chat_id=USER_CHAT_ID, text=msg, parse_mode='Markdown'))

# --- TELEGRAM KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    msg = (
        "🤖 *Yapay Zekâ Destekli Borsa Sinyal Botu Aktif!*\n\n"
        "Sistem arka planda KAP/Haber akışını ve teknik indikatörleri sürekli tarar. "
        "Yüksek potansiyelli bir gelişme olduğunda size *otomatik bildirim* gönderir.\n\n"
        "📌 *Manuel Tarama:* /firsat"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        
        # Arka planda her 3 dakikada bir haber ve teknik tarama yapar
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=lambda: auto_market_scanner(app), trigger="interval", minutes=3)
        scheduler.start()
        
        print("Bot ve Haber Dinleyici Aktif...")
        app.run_polling(drop_pending_updates=True, close_loop=False)
