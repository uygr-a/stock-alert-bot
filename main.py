import os
import threading
import asyncio
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
    return "AI-Powered Market Intelligence Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

USER_CHAT_ID = None
PROCESSED_NEWS = set()  # İşlenen haberleri saklar

# Takip edilecek BIST ve ABD Hisseleri
STOCKS = ["THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "NVDA", "AAPL", "TSLA"]

# --- 1. GEMINI AI İLE HABER ANALİZİ ---
def analyze_news_with_gemini(symbol, headline):
    if not GEMINI_API_KEY:
        return {"is_positive": True, "text": "⚠️ Gemini API Key eksik. Temel haber tespiti yapıldı."}

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            f"Sen profesyonel bir borsa analistisin. {symbol} hissesi için şu haberi analiz et:\n"
            f"Haber: '{headline}'\n\n"
            "Kısa ve öz yanıt ver:\n"
            "ETKİ: [POZİTİF / NEGATİF / NÖTR]\n"
            "ÖZET: [Haberin hisse fiyatına olası etkisini anlatan 1 cümle]"
        )
        response = model.generate_content(prompt)
        text = response.text
        return {"is_positive": "POZİTİF" in text.upper(), "text": text}
    except Exception as e:
        print(f"Gemini Hata: {e}")
        return {"is_positive": True, "text": "Haber tespit edildi (AI servisi yanıt vermedi)."}

# --- 2. HASSAS HABER VE KAP TARAMASI ---
def fetch_latest_news(symbol):
    clean_symbol = symbol.replace('.IS', '')
    
    # BIST için doğrudan KAP / Şirket araması, ABD için borsa araması
    if ".IS" in symbol:
        query = f"%22{clean_symbol}%22+KAP+hisse"
    else:
        query = f"%22{clean_symbol}%22+stock+news"
        
    rss_url = f"https://news.google.com/rss/search?q={query}&hl=tr&gl=TR&ceid=TR:tr"
    feed = feedparser.parse(rss_url)
    
    if feed.entries:
        latest = feed.entries[0]
        news_id = latest.link
        
        # Daha önce bildirilen haberi tekrar atma
        if news_id not in PROCESSED_NEWS:
            PROCESSED_NEWS.add(news_id)
            return {"title": latest.title, "link": latest.link, "is_new": True}
        return {"title": latest.title, "link": latest.link, "is_new": False}
    return None

# --- 3. TEKNİK VERİ (RSI + FİYAT) ---
def check_technical_setup(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        stock = yf.Ticker(symbol, session=session)
        df = stock.history(period="5d", interval="1h")
        
        if len(df) < 5:
            return None
            
        current_price = df['Close'].iloc[-1]
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return {"price": round(current_price, 2), "rsi": round(rsi.iloc[-1], 1)}
    except Exception as e:
        print(f"Teknik analiz hatası ({symbol}): {e}")
        return None

# --- 4. SENKRON PIYASA TARAMA MOTORU ---
def execute_market_scan(only_new_news=False):
    found_signals = []
    
    for symbol in STOCKS:
        clean_symbol = symbol.replace('.IS', '')
        news = fetch_latest_news(symbol)
        tech = check_technical_setup(symbol)
        
        if news and tech:
            if only_new_news and not news['is_new']:
                continue  # Otomatik bildirimde eski haberi atma
                
            ai_res = analyze_news_with_gemini(clean_symbol, news['title'])
            
            # Sinyal Koşulu: Haber AI tarafından olumlu bulunduysa VEYA RSI aşırı satımdaysa (<38)
            if ai_res and (ai_res.get("is_positive") or tech['rsi'] < 38):
                found_signals.append({
                    "symbol": clean_symbol,
                    "price": tech['price'],
                    "rsi": tech['rsi'],
                    "news_title": news['title'],
                    "ai_text": ai_res['text']
                })
    return found_signals

# --- TELEGRAM KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    msg = (
        "🤖 *Yapay Zekâ Destekli Borsa Avcısı Aktif!*\n\n"
        "Sistem arka planda KAP haberlerini ve teknik göstergeleri sürekli tarar. "
        "Kritik bir gelişme veya fırsat olduğunda size *otomatik bildirim* gönderir.\n\n"
        "📌 *Anlık Canlı Tarama:* /firsat"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def firsat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    
    await update.message.reply_text("🔎 *BIST & ABD Piyasası Taranıyor (KAP + AI + Teknik)...*", parse_mode='Markdown')
    
    loop = asyncio.get_running_loop()
    signals = await loop.run_in_executor(None, lambda: execute_market_scan(only_new_news=False))
    
    if not signals:
        await update.message.reply_text("📌 *Şu anda sıkı filtreden geçen kritik bir fırsat bulunamadı.*")
        return

    for s in signals:
        msg = (
            f"🚨 *YAPAY ZEKÂ & HABER SİNYALİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}` | Fiyat: `{s['price']}` TL | RSI: `{s['rsi']}`\n\n"
            f"📰 *Haber:* _{s['news_title']}_\n\n"
            f"🤖 *AI Değerlendirmesi:*\n{s['ai_text']}\n───────────────────"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

# --- ARKA PLAN OTOMATİK BİLDİRİM BİRİMİ ---
def background_auto_scanner(app):
    global USER_CHAT_ID
    if not USER_CHAT_ID:
        return

    # Arka planda sadece YENİ düşen olumlu haberleri filtreler
    signals = execute_market_scan(only_new_news=True)
    for s in signals:
        msg = (
            f"🔔 *OTOMATİK PİYASA BİLDİRİMİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}` | Fiyat: `{s['price']}` TL | RSI: `{s['rsi']}`\n\n"
            f"📰 *Yeni Haber:* _{s['news_title']}_\n\n"
            f"🤖 *AI Yorumu:*\n{s['ai_text']}\n───────────────────"
        )
        asyncio.run_coroutine_threadsafe(
            app.bot.send_message(chat_id=USER_CHAT_ID, text=msg, parse_mode='Markdown'),
            app.loop
        )

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("firsat", firsat_command))
        
        # Her 3 dakikada bir otomatik arka plan taraması
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=lambda: background_auto_scanner(app), trigger="interval", minutes=3)
        scheduler.start()
        
        print("Bot başarıyla başlatıldı.")
        app.run_polling(drop_pending_updates=True, close_loop=False)
