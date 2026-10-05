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

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Institutional Grade BIST Scanner Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None

BIST_TICKERS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "AKBNK.IS", "ISCTR.IS", "KCHOL.IS",
    "SAHOL.IS", "TUPRS.IS", "BIMAS.IS", "SISE.IS", "PETKM.IS", "EKGYO.IS", "KOZAL.IS",
    "HEKTS.IS", "SASA.IS", "PGSUS.IS", "TCELL.IS", "TTKOM.IS", "YKBNK.IS", "GUBRF.IS",
    "ARCLK.IS", "TOASO.IS", "FROTO.IS", "KONTR.IS", "SMRTG.IS", "ASTOR.IS", "ALARK.IS",
    "ODAS.IS", "OYAKC.IS", "SOKM.IS", "MGROS.IS"
]

def analyze_institutional(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        stock = yf.Ticker(symbol, session=session)
        df = stock.history(period="2mo", interval="1d")
        
        if len(df) < 25:
            return None

        current_price = round(df['Close'].iloc[-1], 2)
        prev_price = df['Close'].iloc[-2]
        change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)
        
        # KURAL 1: Düşen (%-2.5 üzeri) veya Taban Hisseler Kesinlikle Engellenir
        if change_pct < -2.0:
            return None

        # RSI Hesaplama
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(rsi.iloc[-1], 1)

        # Hacim Analizi (Alım Hacmi Kontrolü)
        vol_10_avg = df['Volume'].rolling(10).mean().iloc[-1]
        current_vol = df['Volume'].iloc[-1]
        green_candle = df['Close'].iloc[-1] > df['Open'].iloc[-1]  # Mum yeşil mi?
        bullish_volume = (current_vol > vol_10_avg * 1.25) and green_candle

        # Hareketli Ortalamalar (SMA 5, SMA 20, SMA 50)
        sma5 = df['Close'].rolling(5).mean().iloc[-1]
        sma20 = df['Close'].rolling(20).mean().iloc[-1]

        # MACD Hesaplama
        ema12 = df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9, adjust=False).mean()
        macd_bullish = macd.iloc[-1] > signal_line.iloc[-1]

        signal = None
        reason = ""

        # KURAL 2 & 3: Çift Onaylı Trend Dönüşü (ALIM SİNYALİ)
        # Fiyat ortalamaların üstünde + Hacimli Yeşil Mum + MACD Pozitif + Değişim Artıda
        if current_price > sma5 and current_price > sma20 and bullish_volume and macd_bullish and change_pct > 1.0:
            signal = "🟢 YÜKSEK GÜVENİLİRLİKLİ AL (TREND DÖNÜŞÜ)"
            reason = f"Hacimli Yeşil Mum (%{change_pct}) + MA5/MA20 Üzerinde + MACD Pozitif Onaylı"

        # Dip Dönüş Onayı (Sadece Yeşile Döndüyse)
        elif current_rsi < 40 and bullish_volume and change_pct > 0.5:
            signal = "🟢 GÜÇLÜ AL (DİPTEN TEPKİ + ALIM HACMİ)"
            reason = f"RSI Dip Bölgesinde ({current_rsi}) + Pozitif Hacimli Alım Mumu"

        # SIKI SATIŞ SİNYALİ
        elif current_rsi > 72 or (current_price < sma5 and change_pct < -3.0):
            signal = "🔴 SAT / KAR AL (DOYUM ORTAMI)"
            reason = f"RSI Așırı Alımda ({current_rsi}) veya Kısa Vadeli Trend Kırıldı"

        if signal:
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

def scan_bist_institutional():
    results = []
    for ticker in BIST_TICKERS:
        res = analyze_institutional(ticker)
        if res:
            results.append(res)
    return results

# --- TELEGRAM KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    msg = (
        "🏛️ *Kurumsal Seviye BIST Analiz Botu Aktif!*\n\n"
        "Sistem düşen hisseleri filtreler; sadece MACD, Yeşil Hacim Mumu ve Trend Kesişimlerinin onay verdiği fırsatları bildirir.\n\n"
        "🔍 *Anlık Tarama:* /tarama"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def tarama_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    
    await update.message.reply_text("🔎 *BIST Kurumsal Filtrelerle Taranıyor (MACD + Yeşil Hacim + Trend)...*", parse_mode='Markdown')
    
    loop = asyncio.get_running_loop()
    signals = await loop.run_in_executor(None, scan_bist_institutional)
    
    if not signals:
        await update.message.reply_text("📌 *Şu anda riski düşük, kurumsal kriterleri karşılayan net bir alım fırsatı yok.* Piyasa izlemede.")
        return

    for s in signals:
        icon = "🚨" if "AL" in s['signal'] else "⚠️"
        msg = (
            f"{icon} *KURUMSAL BİST SİNYALİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}`\n"
            f"💵 *Fiyat:* `{s['price']} TL` (Günlük: %{s['change']})\n"
            f"📊 *RSI:* `{s['rsi']}`\n"
            f"🎯 *Karar:* *{s['signal']}*\n"
            f"💡 *Gerekçe:* _{s['reason']}_\n───────────────────"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

def auto_scan_job(app):
    global USER_CHAT_ID
    if not USER_CHAT_ID:
        return

    signals = scan_bist_institutional()
    for s in signals:
        icon = "🚨" if "AL" in s['signal'] else "⚠️️"
        msg = (
            f"{icon} *OTOMATİK KURUMSAL BİST BİLDİRİMİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}` | Fiyat: `{s['price']} TL`\n"
            f"🎯 *Sinyal:* *{s['signal']}*\n"
            f"💡 *Gerekçe:* _{s['reason']}_\n───────────────────"
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
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=lambda: auto_scan_job(app), trigger="interval", minutes=15)
        scheduler.start()
        
        print("Kurumsal seviye bot aktif!")
        app.run_polling(drop_pending_updates=True, close_loop=False)
