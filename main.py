import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from curl_cffi import requests as requests_cffi
import yfinance as yf
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ============================================================
# HIGH-SPEED QUANT & MOMENTUM SCANNER ENGINE
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))
SCAN_MINUTES = int(os.getenv("SCAN_MINUTES", "15"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "3"))

DB_FILE = "bist_bot.db"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("SPEED-QUANT")

TICKERS = [
    "A1CAP.IS", "ADEL.IS", "ADESE.IS", "AEFES.IS", "AFYON.IS", "AGESA.IS",
    "AGHOL.IS", "AGROT.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKFYE.IS",
    "AKSA.IS", "AKSEN.IS", "ALARK.IS", "ALBRK.IS", "ALFAS.IS", "ALTNY.IS",
    "ANSGR.IS", "ARCLK.IS", "ARDYZ.IS", "ASELS.IS", "ASTOR.IS", "AYDEM.IS",
    "BERA.IS", "BIMAS.IS", "BIOEN.IS", "BOBET.IS", "BRSAN.IS", "CANTE.IS", "CCOLA.IS",
    "CWENE.IS", "DOAS.IS", "DOHOL.IS", "ECILC.IS", "EGGUB.IS", "EKGYO.IS",
    "ENJSA.IS", "ENKAI.IS", "EREGL.IS", "EUPWR.IS", "FROTO.IS", "GARAN.IS", "GESAN.IS",
    "GUBRF.IS", "GWIND.IS", "HALKB.IS", "HEKTS.IS", "ISCTR.IS", "ISDMR.IS", "ISMEN.IS",
    "KCAER.IS", "KCHOL.IS", "KLSER.IS", "KONTR.IS", "KORDS.IS", "KOZAL.IS", "KOZAA.IS",
    "KRDMD.IS", "MAVI.IS", "MIATK.IS", "MOGAN.IS", "MPARK.IS", "ODAS.IS",
    "OTKAR.IS", "OYAKC.IS", "PETKM.IS", "PGSUS.IS", "QUAGR.IS", "REEDR.IS",
    "SAHOL.IS", "SASA.IS", "SISE.IS", "SKBNK.IS", "SMRTG.IS", "TABGD.IS", "TAVHL.IS",
    "TCELL.IS", "THYAO.IS", "TKFEN.IS", "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TTRAK.IS",
    "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS", "YKBNK.IS", "ZOREN.IS"
]

app = Flask(__name__)

@app.route("/")
def home():
    return "High Speed Quant Engine Active"

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

db_lock = threading.Lock()

def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                entry REAL NOT NULL,
                stop REAL NOT NULL,
                tp1 REAL NOT NULL,
                tp2 REAL NOT NULL,
                tp3 REAL NOT NULL,
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

session = requests_cffi.Session(impersonate="chrome110")

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    res = df.copy()
    if isinstance(res.columns, pd.MultiIndex):
        res.columns = res.columns.get_level_values(0)
    res.columns = [str(c).strip().lower() for c in res.columns]
    req = ["open", "high", "low", "close", "volume"]
    if not all(col in res.columns for col in req):
        return pd.DataFrame()
    res = res[req].copy()
    for col in req:
        res[col] = pd.to_numeric(res[col], errors="coerce")
    res.dropna(inplace=True)
    return res

def download_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        data = yf.download(
            ticker, period=period, interval=interval,
            auto_adjust=False, progress=False, threads=False, session=session, timeout=5
        )
        return clean_dataframe(data)
    except Exception:
        return pd.DataFrame()

def analyze_ticker(ticker: str):
    df_15m = download_data(ticker, "5d", "15m")
    if df_15m.empty or len(df_15m) < 20:
        return None

    close = df_15m["close"]
    high = df_15m["high"]
    low = df_15m["low"]
    volume = df_15m["volume"]

    c_close = float(close.iloc[-1])
    curr_vol = volume.iloc[-1]
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    rvol = (curr_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # VWAP & CMF
    vwap = (volume * (high + low + close) / 3).cumsum() / (volume.cumsum() + 1e-10)
    c_vwap = float(vwap.iloc[-1])

    mf_multiplier = ((close - low) - (high - close)) / (high - low + 1e-10)
    mf_volume = mf_multiplier * volume
    cmf = (mf_volume.rolling(20).sum() / (volume.rolling(20).sum() + 1e-10)).iloc[-1]

    # Skoring
    score = 50 # Baz puan
    reasons = []

    if c_close > c_vwap:
        score += 20
        reasons.append("VWAP Üzerinde Pozitif Trend")
    if cmf > 0.0:
        score += 15
        reasons.append(f"Para Girişi Pozitif (CMF: {cmf:.2f})")
    if rvol >= 1.5:
        score += 15
        reasons.append(f"Hacim Sıçraması ({rvol:.1f}x)")

    # ATR Tabanlı Hesaplama
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/10, adjust=False).mean().iloc[-1]

    stop_price = c_close - (1.2 * atr)
    risk = c_close - stop_price
    if risk <= 0: return None

    tp1 = c_close + (risk * 1.5)
    tp2 = c_close + (risk * 2.8)
    tp3 = c_close + (risk * 4.5)

    money_risk = PORTFOLIO_SIZE * RISK_PER_TRADE
    quantity = int(money_risk / risk)
    if quantity <= 0: quantity = 10

    return {
        "ticker": ticker,
        "entry": c_close,
        "stop": stop_price,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "quantity": quantity,
        "score": score,
        "rvol": rvol,
        "reasons": reasons
    }

def scan_all_fast():
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(analyze_ticker, ticker): ticker for ticker in TICKERS}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)
    
    # Skora ve RVOL'e göre sırala
    results.sort(key=lambda x: (x["score"], x["rvol"]), reverse=True)
    return results[:3] # En iyi 3 hisseyi döndür

async def send_telegram_msg(app_bot: Application, text: str):
    if not CHAT_ID: return
    try:
        await app_bot.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.error(f"Telegram mesaj hatası: {exc}")

def format_signal_msg(sig):
    symbol = sig["ticker"].replace(".IS", "")
    reasons_str = "\n• ".join(sig["reasons"])
    return (
        f"🔥 *GÜNÜN EN YÜKSEK POTANSİYELLİ HİSSESİ* 🔥\n\n"
        f"📌 *Hisse:* #{symbol}\n"
        f"📊 *Sinyal Skor:* %{sig['score']} / 100\n"
        f"🚀 *Hacim İvmesi:* {sig['rvol']:.1f}x\n\n"
        f"💡 *Teyitler:*\n• {reasons_str}\n\n"
        f"💵 *Giriş (BUY):* {sig['entry']:.2f} TL\n"
        f"🛑 *Stop-Loss:* {sig['stop']:.2f} TL\n\n"
        f"🎯 *TP1:* {sig['tp1']:.2f} TL\n"
        f"🎯 *TP2:* {sig['tp2']:.2f} TL\n"
        f"🚀 *TP3:* {sig['tp3']:.2f} TL\n\n"
        f"📦 *Önerilen Adet:* {sig['quantity']} Lot"
    )

async def scan_market(application: Application):
    top_stocks = scan_all_fast()
    for sig in top_stocks:
        msg = format_signal_msg(sig)
        await send_telegram_msg(application, msg)
    return len(top_stocks)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Fast Quant Bot Aktif.\n/scan - Hızlı Tarama Başlat")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Piyasadaki en yüksek ivmeli hisseler taranıyor (Yaklaşık 10 sn)...")
    found = await scan_market(context.application)
    await update.message.reply_text(f"✅ Tarama bitti. En yüksek ivmeli {found} hisse yukarıda paylaşıldı.")

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    init_db()

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app_bot = Application.builder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(CommandHandler("scan", scan_cmd))

    logger.info("Bot Çalışıyor.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
