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
    return "AI-Powered Signal Bot Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

# API VE TOKEN AYARLARI
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

USER_CHAT_ID = None
PROCESSED_NEWS = set()

STOCKS = ["THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "NVDA", "AAPL", "TSLA"]

# --- HABER & AI ANALİZİ ---
def analyze_news_with_gemini(symbol, headline):
    """Haberin hisseye etkisini Gemini AI ile analiz eder."""
    if not GEMINI_API_KEY:
        return {"is_positive": True, "text": "AI Key yok, temel haber tespiti yapıldı."}

    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = (
            f"Sen profesyonel bir borsa analistisin. {symbol} hissesi için şu haberi analiz et:\n"
            f"Haber: '{headline}'\n\n"
            "Kısa ve net yanıt ver:\n"
            "ETKİ: [POZİTİF / NEGATİF / NÖTR]\n"
            "ÖZET: [Haberin hisseye etkisini anlatan 1 cümle]"
        )
        response = model.generate_content(prompt)
        text = response.text
        return {"is_positive": "POZİTİF" in text.upper(), "text": text}
    except Exception as e:
        print(f"Gemini Hata: {e}")
        return None

def fetch_latest_news(symbol):
    clean_symbol = symbol.replace('.IS', '')
    rss_url = f"https://news.google.com/rss/search?q={clean_symbol}+hisse+or+KAP&hl=tr&gl=TR&ceid=TR:tr"
    feed = feedparser.parse(rss_url)
    
    if feed.entries:
        latest = feed.entries[0]
        return {"title": latest.title, "link": latest.link}
    return None

def check_technical_setup(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        stock = yf.Ticker(symbol, session=session)
        df = stock.history(period="5d", interval="1h")
        
        if len(df) < 5:
            return None
            
        current_price = df['Close'].iloc[-1]
        
        # RSI Hesaplama
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return {"price": round(current_price, 2), "rsi": round(rsi.iloc[-1], 1)}
    except Exception as e:
        print(f"Teknik analiz hatası ({symbol}): {e}")
        return None

# --- CANLI TARAMA MOTORU (MANUEL & OTOMATİK İÇİN) ---
async def run_market_scan(app_or_context, chat_id):
    signals_found = 0
    
    for symbol in STOCKS:
        clean_symbol = symbol.replace('.IS', '')
        news = fetch_latest_news(symbol)
        tech = check_technical_setup(symbol)
        
        if news and tech:
            ai_res = analyze_news_with_gemini(clean_symbol, news['title'])
            
            # Eğer haber olumluysa veya teknik değerler uygunsa sinyal üret
            if ai_res and (ai_res.get("is_positive") or tech['rsi'] < 40):
                signals_found += 1
                msg = (
                    f"🚨 *YAPAY ZEKÂ & HABER SİNYALİ*\n───────────────────\n"
                    f"📌 *Hisse:* `{clean_symbol}` | Fiyat: `{tech['price']}` TL | RSI: `{tech['rsi']}`\n\n"
                    f"📰 *Son Haber:* _{news['title']}_\n\n"
                    f"🤖 *AI Değerlendirmesi:*\n{ai_res['text']}\n───────────────────"
                )
                await app_or_context.bot.send_message(chat_id=chat_id, text=msg, parse_mode='Markdown')
    
    if signals_found == 0:
        await app_or_context.bot.send_message(
            chat_id=chat_id, 
            text="📌 *Şu anda haber ve teknik kriterlere uyan kritik bir fırsat bulunamadı.* Piyasa taranmaya devam ediyor.",
            parse_mode='Markdown'
        )

# --- TELEGRAM KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    msg = (
        "🤖 *Yapay Zekâ Destekli Borsa Sinyal Botu Aktif!*\n\n"
        "Sistem arka planda KAP/Haber akışını ve teknik indikatörleri sürekli tarar. "
        "Yüksek potansiyelli bir gelişme olduğunda size *otomatik bildirim* gönderir.\n\n"
        "📌 *Anlık Tarama Yapmak İçin:* /firsat"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def firsat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kullanıcı /firsat yazdığında tetiklenir."""
    await update.message.reply_text("🔎 *Canlı BIST & ABD Piyasası Taranıyor (Haberler + AI + Teknik)...*", parse_mode='Markdown')
    await run_market_scan(context, update.effective_chat.id)

# --- ARKA PLAN OTOMATİK TARAYICI ---
def auto_market_scanner(app):
    global USER_CHAT_ID
    if USER_CHAT_ID:
        # Arka planda otomatik tarama yapar
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_market_scan(app, USER_CHAT_ID))

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        
        # Komut İşleyicileri (Handlers)
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("firsat", firsat_command))
        
        # Arka plan zamanlayıcı (Her 5 dakikada bir otomatik tarama)
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=lambda: auto_market_scanner(app), trigger="interval", minutes=5)
        scheduler.start()
        
        print("Bot başarıyla başlatıldı!")
        app.run_polling(drop_pending_updates=True, close_loop=False)
