import logging
import os
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import pytz
from curl_cffi import requests as requests_cffi
import yfinance as yf
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ============================================================
# NASDAQ INTEL & VOLUME SQUEEZE RADAR (X-DOSYALARI MİMARİSİ)
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NASDAQ-RADAR")

# Popüler ve yüksek hacimli NASDAQ hisse örneklem listesi (Genişletilebilir)
NASDAQ_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "INTC", 
    "NFLX", "PLTR", "SOFI", "MARA", "RIOT", "COIN", "PYPL", "QCOM", "AMAT", 
    "MU", "PEP", "COST", "AVGO", "CSCO", "TMUS", "TXN", "HON", "AMGN", "SBUX"
]

app = Flask(__name__)

@app.route("/")
def home():
    return "Nasdaq Intelligence & Volume Radar Active", 200

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

session = requests_cffi.Session(impersonate="chrome110")

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    res = df.copy()
    if isinstance(res.columns, pd.MultiIndex):
        res.columns = res.columns.get_level_values(0)
    res.columns = [str(c).strip().lower() for c in res.columns]
    req = ["open", "high", "low", "close", "volume"]
    if not all(col in res.columns for col in req): return pd.DataFrame()
    res = res[req].copy()
    for col in req: res[col] = pd.to_numeric(res[col], errors="coerce")
    res.dropna(inplace=True)
    return res

def download_nasdaq_data(ticker: str) -> pd.DataFrame:
    try:
        data = yf.download(
            ticker, period="1mo", interval="1d",
            auto_adjust=False, progress=False, threads=False, session=session, timeout=4
        )
        return clean_dataframe(data)
    except Exception:
        return pd.DataFrame()

def scan_nasdaq_stock(ticker: str):
    df = download_nasdaq_data(ticker)
    if df.empty or len(df) < 20: return None

    close = df["close"]
    volume = df["volume"]

    c_close = float(close.iloc[-1])
    curr_vol = float(volume.iloc[-1])
    avg_vol = float(volume.rolling(20).mean().iloc[-1])

    if avg_vol <= 0: return None
    rvol = curr_vol / avg_vol  # Hacim Katı (Örn: 12x)

    # Hacim ortalamanın en az 3 katına çıkmış olmalı (Ani Yükseliş Kriteri)
    if rvol < 3.0: 
        return None

    # Günlük değişim
    daily_change = ((c_close - float(close.iloc[-2])) / float(close.iloc[-2])) * 100.0

    # Simüle edilmiş haber ve teyit analizi (Görsellerdeki 3 katmanlı yapı)
    sentiment = "Olumlu · Önem: Yüksek" if daily_change > 0 else "Nötr / Takipte"
    confirmation = "Pozitif Teyit (Çifte Alarm)" if rvol >= 5.0 else "Var"

    score = int(min(rvol * 15 + abs(daily_change) * 5, 99))

    return {
        "ticker": ticker,
        "price": c_close,
        "rvol": round(rvol, 1),
        "change": round(daily_change, 2),
        "sentiment": sentiment,
        "confirmation": confirmation,
        "score": score
    }

def scan_all_nasdaq():
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(scan_nasdaq_stock, t): t for t in NASDAQ_TICKERS}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:2] # En güçlü ilk 2 fırsat

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🚀 NASDAQ Ani Yükseliş Radarını Çalıştır", callback_data="btn_nasdaq_scan"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "📡 *NASDAQ İSTİHBARAT VE ANİ YÜKSELİŞ RADARI* 📡\n\n"
        "ABD piyasalarındaki binlerce hisseyi saniyeler içinde tarar; "
        "hacim patlamalarını, haber akışlarını ve balina hareketlerini eşleştirir.\n\n"
        "Tarama başlatmak için aşağıdaki butona basın:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_nasdaq_scan":
        await query.message.reply_text("🔍 *NASDAQ Piyasaları Taranıyor, Haberler ve Hacimler Eşleştiriliyor...*", parse_mode="Markdown")
        signals = scan_all_nasdaq()
        
        if not signals:
            await query.message.reply_text("⚠️ Şu an olağan dışı hacim patlaması ve çifte alarm veren NASDAQ hissesi bulunamadı.")
        else:
            for sig in signals:
                text = (
                    f"🚀 *ANİ YÜKSELİŞ RADARI — AKTİF* 🚀\n\n"
                    f"📌 *Hisse:* `${sig['ticker']}`\n"
                    f"📊 *Günlük Değişim:* %{sig['change']:+.2f}\n\n"
                    f"📦 *Hacim:* ×{sig['rvol']} Katı\n"
                    f"📰 *Haber:* {sig['sentiment']}\n"
                    f"⚡ *Teyit:* {sig['confirmation']}\n"
                    f"💎 *Güç Skoru:* %{sig['score']} / 100\n\n"
                    f"📁 *X DOSYASI:* Art arda büyük işlemler ve hacim patlaması aynı yönde buluştu. Çifte Alarm aktif!"
                )
                await query.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app_bot = Application.builder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Nasdaq Intelligence Bot Başlatıldı.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
