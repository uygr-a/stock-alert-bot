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

# Render Keep-Alive Sunucusu
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "BIST Technical Scanner Running!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None

# BIST Hisseleri Listesi (En Likit ve Popüler BIST Hisseleri)
BIST_TICKERS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "AKBNK.IS", "ISCTR.IS", "KCHOL.IS",
    "SAHOL.IS", "TUPRS.IS", "BIMAS.IS", "SISE.IS", "PETKM.IS", "EKGYO.IS", "KOZAL.IS",
    "HEKTS.IS", "SASA.IS", "DOHOL.IS", "PGSUS.IS", "TCELL.IS", "TTKOM.IS", "YKBNK.IS",
    "GUBRF.IS", "ARCLK.IS", "TOASO.IS", "FROTO.IS", "KONTR.IS", "SMRTG.IS", "ASTOR.IS",
    "EUPWR.IS", "ALARK.IS", "ODAS.IS", "OYAKC.IS", "CANTE.IS", "SOKM.IS", "MGROS.IS"
]

# --- TEKNİK ANALİZ ENGINE ---
def analyze_stock(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        stock = yf.Ticker(symbol, session=session)
        df = stock.history(period="1mo", interval="1d")
        
        if len(df) < 15:
            return None

        # RSI Hesaplama
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(rsi.iloc[-1], 1)

        # Fiyat & Değişim
        current_price = round(df['Close'].iloc[-1], 2)
        prev_price = df['Close'].iloc[-2]
        change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)

        # Hareketli Ortalamalar (SMA 10 & SMA 20)
        sma10 = df['Close'].rolling(10).mean().iloc[-1]
        sma20 = df['Close'].rolling(20).mean().iloc[-1]

        # Sinyal Mantığı
        signal = "PAS"
        reason = ""

        if current_rsi < 35:
            signal = "🟢 AL (DİP)"
            reason = f"RSI Dip Bölgesinde ({current_rsi}) - Tepki Alımı Beklentisi"
        elif current_price > sma10 and current_price > sma20 and change_pct > 2.5:
            signal = "🟢 AL (GÜÇLÜ TREND)"
            reason = f"Ortalamaların Üzerinde + Günlük Yükseliş (%{change_pct})"
        elif current_rsi > 70:
            signal = "🔴 SAT (AŞIRI ALIM)"
            reason = f"RSI Doyum Noktasında ({current_rsi}) - Kar Satışı Riski"

        if signal != "PAS":
            return {
                "symbol": symbol.replace('.IS', ''),
                "price": current_price,
                "change": change_pct,
                "rsi": current_rsi,
                "signal": signal,
                "reason": reason
            }
        return None

    except Exception as e:
        return None

def scan_entire_bist():
    results = []
    for ticker in BIST_TICKERS:
        res = analyze_stock(ticker)
        if res:
            results.append(res)
    return results

# --- TELEGRAM BOT KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    msg = (
        "📈 *BIST Otomatik Teknik Analiz Botu Aktif!*\n\n"
        "Sistem BIST hisselerini teknik göstergelerle (RSI, Trend, MA) sürekli tarar.\n\n"
        "🔍 *Anlık BIST Taraması Yapmak İçin:* /tarama"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def tarama_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    
    await update.message.reply_text("🔎 *BIST Hisseleri Taranıyor (RSI + Trend + Ortalamalar)...*", parse_mode='Markdown')
    
    loop = asyncio.get_running_loop()
    signals = await loop.run_in_executor(None, scan_entire_bist)
    
    if not signals:
        await update.message.reply_text("📌 *Şu an net AL/SAT sinyali veren hisse bulunamadı (Piyasa nötr).*")
        return

    for s in signals:
        icon = "🚨" if "AL" in s['signal'] else "⚠️"
        msg = (
            f"{icon} *BİST SİNYAL BİLDİRİMİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}`\n"
            f"💵 *Fiyat:* `{s['price']} TL` (Değişim: %{s['change']})\n"
            f"📊 *RSI Değeri:* `{s['rsi']}`\n"
            f"🎯 *Sinyal:* *{s['signal']}*\n"
            f"💡 *Nedeni:* _{s['reason']}_\n───────────────────"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

# Arka planda her 15 dakikada bir otomatik sinyal üretir
def auto_scan_job(app):
    global USER_CHAT_ID
    if not USER_CHAT_ID:
        return

    signals = scan_entire_bist()
    for s in signals:
        icon = "🚨" if "AL" in s['signal'] else "⚠️"
        msg = (
            f"{icon} *OTOMATİK BİST AL/SAT BİLDİRİMİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}`\n"
            f"💵 *Fiyat:* `{s['price']} TL` (Değişim: %{s['change']})\n"
            f"📊 *RSI:* `{s['rsi']}` | *Sinyal:* *{s['signal']}*\n"
            f"💡 *Neden:* _{s['reason']}_\n───────────────────"
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
        app.add_handler(CommandHandler("tarama", tarama_command))
        
        # Her 15 dakikada bir BIST'i otomatik tara
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=lambda: auto_scan_job(app), trigger="interval", minutes=15)
        scheduler.start()
        
        print("Bot başarıyla başlatıldı.")
        app.run_polling(drop_pending_updates=True, close_loop=False)
