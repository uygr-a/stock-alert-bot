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
# EARLY BREAKOUT & ANTI-FOMO QUANT ENGINE
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

# TEPEDEN ALIM ENGELLERİ (FOMO GUARD)
MAX_DAILY_CHANGE_PCT = 3.8   # Günlük değişimi %3.8'i geçen hisseye ASLA GİRİLMEZ!
MIN_DAILY_CHANGE_PCT = -1.0  # Günlük çok düşen hisseler elenir (Düşen bıçak tutulmaz)

DB_FILE = "bist_bot.db"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("EARLY-QUANT")

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
    return "Early Breakout Anti-FOMO Engine Active"

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
    # 1. Günlük Yüzde Kontrolü (Tepeden Alımı Engelleme)
    df_daily = download_data(ticker, "1mo", "1d")
    if df_daily.empty or len(df_daily) < 5:
        return None

    c_daily_close = float(df_daily["close"].iloc[-1])
    p_daily_close = float(df_daily["close"].iloc[-2])
    daily_pct = ((c_daily_close - p_daily_close) / p_daily_close) * 100.0

    # KESİN FİLTRE: Eğer %3.8'den fazla primliyse (Örn %7) veya çok düşüyorsa ELE!
    if daily_pct > MAX_DAILY_CHANGE_PCT or daily_pct < MIN_DAILY_CHANGE_PCT:
        return None

    # 2. 15 Dakikalık Erken İvme Taraması
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

    # Sadece hacmin tam şu an patladığı (%1.4x ve üstü) hisseler
    if rvol < 1.4:
        return None

    # VWAP Hesabı
    vwap = (volume * (high + low + close) / 3).cumsum() / (volume.cumsum() + 1e-10)
    c_vwap = float(vwap.iloc[-1])

    if c_close < c_vwap:
        return None # Fiyat VWAP altındaysa güçsüzdür, ele.

    # ATR Tabanlı Risk Yapısı
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/10, adjust=False).mean().iloc[-1]

    stop_price = c_close - (1.1 * atr)
    risk = c_close - stop_price
    if risk <= 0: return None

    tp1 = c_close + (risk * 1.5)
    tp2 = c_close + (risk * 2.5)
    tp3 = c_close + (risk * 4.0)

    money_risk = PORTFOLIO_SIZE * RISK_PER_TRADE
    quantity = int(money_risk / risk)
    if quantity <= 0: quantity = 10

    score = 60 + int(rvol * 10)

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
        "daily_pct": daily_pct
    }

def scan_all_fast():
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(analyze_ticker, ticker): ticker for ticker in TICKERS}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)
    
    # En taze ivmeli hisseleri sırala
    results.sort(key=lambda x: (x["rvol"], x["score"]), reverse=True)
    return results[:3] # En ideal 3 hisse

async def send_telegram_msg(app_bot: Application, text: str):
    if not CHAT_ID: return
    try:
        await app_bot.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.error(f"Telegram mesaj hatası: {exc}")

def format_signal_msg(sig):
    symbol = sig["ticker"].replace(".IS", "")
    return (
        f"🎯 *ERKEN AŞAMA ALIM SİNYALİ* (Dip/Sıkışma Kırılımı)\n\n"
        f"📌 *Hisse:* #{symbol}\n"
        f"📈 *Günün Yüzdesi:* %{sig['daily_pct']:.2f} (Henüz Yükselmedi!)\n"
        f"🚀 *Anlık Hacim Şiddeti:* {sig['rvol']:.1f}x\n\n"
        f"💵 *Giriş (BUY):* {sig['entry']:.2f} TL\n"
        f"🛑 *Stop-Loss:* {sig['stop']:.2f} TL\n\n"
        f"🎯 *TP1 (Hedef 1):* {sig['tp1']:.2f} TL\n"
        f"🎯 *TP2 (Hedef 2):* {sig['tp2']:.2f} TL\n"
        f"🚀 *TP3 (Hedef 3):* {sig['tp3']:.2f} TL\n\n"
        f"📦 *Önerilen Adet:* {sig['quantity']} Lot\n\n"
        f"⚠️ _Not: Bu hisse henüz %3.8 prim barajını aşmamış taze ivmeli hissedir._"
    )

async def scan_market(application: Application):
    top_stocks = scan_all_fast()
    for sig in top_stocks:
        msg = format_signal_msg(sig)
        await send_telegram_msg(application, msg)
    return len(top_stocks)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Anti-FOMO Erken Aşama Quant Bot Aktif.\n/scan - Hızlı Tarama Başlat")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Henüz prim yapmamış, patlamaya hazır taze hisseler taranıyor...")
    found = await scan_market(context.application)
    if found == 0:
        await update.message.reply_text("✅ Tarama Bitti.\n\n⚠️ Günün bu saatinde tepeden alım riski olmayan taze hisse kalmadığı için sinyal verilmedi.")
    else:
        await update.message.reply_text(f"✅ Tarama bitti. Erken aşamadaki {found} hisse paylaşıldı.")

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
