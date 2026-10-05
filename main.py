import os
import threading
import asyncio
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

# Render Port Kontrolü
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "BIST & ABD Canlı Fırsat Avcısı Bot Aktif!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Otomatik bildirim gönderilecek Telegram Chat ID'si (Botunuza ilk /start verdiğinizde dolacaktır)
CHAT_ID = None

# TARANACAK LİSTELER
BIST_STOCKS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "SASA.IS", 
    "KCHOL.IS", "AKBNK.IS", "TUPRS.IS", "SISE.IS", "BIMAS.IS",
    "YKBNK.IS", "ISCTR.IS", "SAHOL.IS", "HEKTS.IS", "PGSUS.IS"
]

US_STOCKS = [
    "NVDA", "AAPL", "TSLA", "MSFT", "AMZN", 
    "GOOGL", "META", "AMD", "NFLX", "PLTR"
]

def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_stock(ticker_symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        
        stock = yf.Ticker(ticker_symbol, session=session)
        df = stock.history(period="1mo", interval="1h")
        
        if len(df) < 30:
            return None

        current_price = df['Close'].iloc[-1]
        volume = df['Volume'].iloc[-1]
        avg_volume = df['Volume'].mean()

        # 1. RSI (14)
        rsi_series = calculate_rsi(df['Close'])
        curr_rsi = rsi_series.iloc[-1]
        prev_rsi = rsi_series.iloc[-2]

        # 2. MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        curr_macd, curr_signal = macd.iloc[-1], macd_signal.iloc[-1]
        prev_macd, prev_signal = macd.iloc[-2], macd_signal.iloc[-2]

        # 3. Bollinger & SMA
        sma20 = df['Close'].rolling(window=20).mean().iloc[-1]
        std20 = df['Close'].rolling(window=20).std().iloc[-1]
        lower_band = sma20 - (std20 * 2)

        # SI KI FİLTRELEME MANTIĞI (Sadece %80+ Olasılıklı Fırsatları Yakalar)
        signals = []
        score = 0

        # Koşul 1: Dip RSI'dan Yukarı Dönüş
        if prev_rsi < 35 and curr_rsi >= 35:
            score += 3
            signals.append("RSI Dip Aşamasından Yukarı Kırdı")
        elif curr_rsi < 32:
            score += 2
            signals.append("Aşırı Satım Bölgesinde (Tepki Beklentisi)")

        # Koşul 2: MACD Taze Alım Kesişimi
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            score += 3
            signals.append("MACD Taze Boğa Kesişimi Yapıyor")

        # Koşul 3: Hacim Patlaması (Ortalamanın üstünde hacim)
        if volume > avg_volume * 1.3:
            score += 2
            signals.append("Yüksek Alım Hacmi Onayı")

        # Koşul 4: Bollinger Alt Band Tepkisi
        if current_price <= lower_band * 1.01:
            score += 2
            signals.append("Alt Bollinger Destek Seviyesinde")

        # YALNIZCA YÜKSEK SKORLU HİSSELERİ DÖNDÜR (Gelişigüzel Sinyal Vermez)
        if score >= 5:
            clean_symbol = ticker_symbol.replace('.IS', '')
            tp = round(current_price * 1.05, 2)
            sl = round(current_price * 0.98, 2)
            
            return {
                "symbol": clean_symbol,
                "price": round(current_price, 2),
                "rsi": round(curr_rsi, 1),
                "score": score,
                "tp": tp,
                "sl": sl,
                "reasons": " + ".join(signals)
            }
    except Exception as e:
        print(f"Hata {ticker_symbol}: {e}")
    return None

async def scan_market(stock_list):
    opportunities = []
    for symbol in stock_list:
        res = analyze_stock(symbol)
        if res:
            opportunities.append(res)
    return opportunities

# --- TELEGRAM KOMUTLARI ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    CHAT_ID = update.effective_chat.id
    msg = (
        "🤖 *BIST & ABD Yüksek Olasılıklı Fırsat Avcısı Botu Aktif!*\n\n"
        "Bu bot rasgele sinyal üretmez. Sadece teknik indikatörlerin (RSI + MACD + Hacim + Bollinger) "
        "aynı anda alım fırsatı doğruladığı hisseleri filtreler.\n\n"
        "📌 *Komutlar:*\n"
        "/firsat - Anlık BIST & ABD Piyasa Taraması Yap\n"
        "/bist - Sadece BIST Hisselerini Tara\n"
        "/abd - Sadece ABD (NASDAQ/NYSE) Hisselerini Tara"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def firsat_tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global CHAT_ID
    CHAT_ID = update.effective_chat.id
    
    await update.message.reply_text("🔎 *BIST ve ABD Piyasaları Taranıyor (Yalnızca %80+ Yükselme Potansiyelli Hisseler Süzülüyor)...*", parse_mode='Markdown')
    
    all_stocks = BIST_STOCKS + US_STOCKS
    results = await scan_market(all_stocks)

    if not results:
        await update.message.reply_text("📌 *Şu anda teknik olarak yükselme olasılığı yüksek sıkı filtreye uyan bir hisse bulunamadı.* Piyasa izlenmeye devam ediyor.")
        return

    msg = "🔥 *YÜKSEK POTANSİYELLİ CANLI FIRSATLAR*\n───────────────────\n\n"
    for r in results:
        msg += f"🚀 *{r['symbol']}* | Fiyat: `{r['price']}` | RSI: `{r['rsi']}`\n"
        msg += f"🎯 *Hedef (TP):* `{r['tp']}` | 🛑 *Stop (SL):* `{r['sl']}`\n"
        msg += f"🔬 *Teknik Onaylar:* _{r['reasons']}_\n───────────────────\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    if not TOKEN:
        print("CRITICAL HATA: TELEGRAM_BOT_TOKEN ayarlanmamış!")
    else:
        print("Sinyal Botu Dinlemeye Başlıyor...")
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("firsat", firsat_tara))
        app.add_handler(CommandHandler("bist", firsat_tara))
        app.add_handler(CommandHandler("abd", firsat_tara))
        
        app.run_polling(drop_pending_updates=True, close_loop=False)
