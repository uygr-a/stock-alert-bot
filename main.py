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
    return "BIST Smart Trading Bot Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None

# Likit ve Hacimli BIST Hisseleri
BIST_TICKERS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "AKBNK.IS", "ISCTR.IS", "KCHOL.IS",
    "SAHOL.IS", "TUPRS.IS", "BIMAS.IS", "SISE.IS", "PETKM.IS", "EKGYO.IS", "KOZAL.IS",
    "HEKTS.IS", "SASA.IS", "PGSUS.IS", "TCELL.IS", "TTKOM.IS", "YKBNK.IS", "GUBRF.IS",
    "ARCLK.IS", "TOASO.IS", "FROTO.IS", "KONTR.IS", "SMRTG.IS", "ASTOR.IS", "ALARK.IS",
    "ODAS.IS", "OYAKC.IS", "SOKM.IS", "MGROS.IS"
]

def analyze_stock_strict(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        stock = yf.Ticker(symbol, session=session)
        df = stock.history(period="1mo", interval="1d")
        
        if len(df) < 20:
            return None

        current_price = round(df['Close'].iloc[-1], 2)
        prev_price = df['Close'].iloc[-2]
        change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)

        # 1. RSI Hesaplama
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = round(rsi.iloc[-1], 1)

        # 2. Hacim Analizi (Son gün hacmi > 10 günlük ortalama hacim)
        vol_10_avg = df['Volume'].rolling(10).mean().iloc[-1]
        current_vol = df['Volume'].iloc[-1]
        volume_spike = current_vol > (vol_10_avg * 1.2)  # %20 üzeri hacim artışı

        # 3. Hareketli Ortalamalar
        sma5 = df['Close'].rolling(5).mean().iloc[-1]
        sma20 = df['Close'].rolling(20).mean().iloc[-1]

        signal = None
        reason = ""

        # --- SIKI ALİM FİLTRESİ ---
        # Şart A: RSI Dipte + Hacim Patlaması Var (Para Girişi)
        if current_rsi < 38 and volume_spike:
            signal = "🟢 GÜÇLÜ AL (DİP + HACİM PATLAMASI)"
            reason = f"RSI Dipte ({current_rsi}) ve İşlem Hacmi Ortalama Üzerinde (%20+ Artış)"

        # Şart B: Trend Dönüşü (Fiyat MA5 ve MA20 Üzerinde + Hacim Artışı)
        elif current_price > sma5 and current_price > sma20 and volume_spike and change_pct > 1.5:
            signal = "🟢 GÜÇLÜ AL (TREND DÖNÜŞÜ)"
            reason = f"Hareketli Ortalamalar Yukarı Kırıldı + Hacim Destekli Yükseliş (%{change_pct})"

        # --- SIKI SATIŞ FİLTRESİ ---
        elif current_rsi > 72:
            signal = "🔴 SAT (AŞIRI ALIM / DOYUM)"
            reason = f"RSI 72 Üzerinde ({current_rsi}) - Kar Satışı Riski Yüksek"

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

def scan_bist_strict():
    results = []
    for ticker in BIST_TICKERS:
        res = analyze_stock_strict(ticker)
        if res:
            results.append(res)
    return results

# --- TELEGRAM KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    msg = (
        "🛡️ *BIST Sıkı Onaylı Teknik Analiz Botu Aktif!*\n\n"
        "Sistem sadece hacim artışı, trend dönüşü ve RSI dip onayının *aynı anda* sağlandığı kaliteli sinyalleri yakalar.\n\n"
        "🔍 *Anlık Tarama Yapmak İçin:* /tarama"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def tarama_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    
    await update.message.reply_text("🔎 *BIST Sıkı Filtreden Geçiriliyor (Hacim + Ortalamalar + RSI)...*", parse_mode='Markdown')
    
    loop = asyncio.get_running_loop()
    signals = await loop.run_in_executor(None, scan_bist_strict)
    
    if not signals:
        await update.message.reply_text("📌 *Şu anda tüm sıkı kriterleri (Hacim + Trend) karşılayan riski düşük bir fırsat bulunamadı.* Piyasa nötr/izlemede.")
        return

    for s in signals:
        icon = "🚨" if "AL" in s['signal'] else "⚠️"
        msg = (
            f"{icon} *PROFESYONEL BİST SİNYALİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}`\n"
            f"💵 *Fiyat:* `{s['price']} TL` (%{s['change']})\n"
            f"📊 *RSI Değeri:* `{s['rsi']}`\n"
            f"🎯 *Karar:* *{s['signal']}*\n"
            f"💡 *Gerekçe:* _{s['reason']}_\n───────────────────"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

# Arka planda her 15 dakikada bir tarama
def auto_scan_job(app):
    global USER_CHAT_ID
    if not USER_CHAT_ID:
        return

    signals = scan_bist_strict()
    for s in signals:
        icon = "🚨" if "AL" in s['signal'] else "⚠️"
        msg = (
            f"{icon} *OTOMATİK BİST SİNYAL BİLDİRİMİ*\n───────────────────\n"
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
        
        print("Sıkı filtreli bot aktif!")
        app.run_polling(drop_pending_updates=True, close_loop=False)
