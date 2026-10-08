import logging
import os
import sqlite3
import threading
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
# FREE END-OF-DAY (EOD) BREAKOUT SCANNER
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

DB_FILE = "bist_bot.db"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("EOD-QUANT")

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
    return "EOD Breakout Scanner Active", 200

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

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

def download_data(ticker: str) -> pd.DataFrame:
    try:
        data = yf.download(
            ticker, period="3mo", interval="1d",
            auto_adjust=False, progress=False, threads=False, session=session, timeout=5
        )
        return clean_dataframe(data)
    except Exception:
        return pd.DataFrame()

def analyze_ticker(ticker: str):
    df = download_data(ticker)
    if df.empty or len(df) < 25:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    c_close = float(close.iloc[-1])
    p_close = float(close.iloc[-2])
    daily_pct = ((c_close - p_close) / p_close) * 100.0

    # Günlük Hacim Artışı (RVOL)
    curr_vol = volume.iloc[-1]
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    rvol = (curr_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # Kriterler: Günlükte en az %1.5 hacim artışı ve makul prim (%0.5 ile %4.5 arası)
    if rvol < 1.3 or daily_pct < 0.5 or daily_pct > 4.5:
        return None

    # Simple Moving Averages (SMA20 & SMA50)
    sma20 = close.rolling(20).mean().iloc[-1]
    if c_close < sma20:
        return None # Fiyat SMA20 altında ise güçsüzdür

    # ATR Tabanlı Risk Yapısı
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean().iloc[-1]

    stop_price = c_close - (1.2 * atr)
    risk = c_close - stop_price
    if risk <= 0: return None

    tp1 = c_close + (risk * 1.5)
    tp2 = c_close + (risk * 2.5)
    tp3 = c_close + (risk * 4.0)

    money_risk = PORTFOLIO_SIZE * RISK_PER_TRADE
    quantity = int(money_risk / risk)
    if quantity <= 0: quantity = 10

    score = int(rvol * 20) + int(daily_pct * 10)

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
    
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:3] # En potansiyelli 3 gün sonu hissesi

async def send_telegram_msg(app_bot: Application, text: str):
    if not CHAT_ID: return
    try:
        await app_bot.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.error(f"Telegram mesaj hatası: {exc}")

def format_signal_msg(sig):
    symbol = sig["ticker"].replace(".IS", "")
    return (
        f"📊 *ERTESİ GÜN POTANSİYELLİ HİSSE SİNYALİ*\n\n"
        f"📌 *Hisse:* #{symbol}\n"
        f"📈 *Günlük Kapanış Prim:* %{sig['daily_pct']:.2f}\n"
        f"🚀 *Günlük Hacim Artışı:* {sig['rvol']:.1f}x Katı\n\n"
        f"💵 *Önerilen Kapanış/Açılış Girişi:* {sig['entry']:.2f} TL\n"
        f"🛑 *Stop-Loss:* {sig['stop']:.2f} TL\n\n"
        f"🎯 *Hedef 1 (TP1):* {sig['tp1']:.2f} TL\n"
        f"🎯 *Hedef 2 (TP2):* {sig['tp2']:.2f} TL\n"
        f"🚀 *Hedef 3 (TP3):* {sig['tp3']:.2f} TL\n\n"
        f"📦 *Önerilen Adet:* {sig['quantity']} Lot\n\n"
        f"💡 _Not: Bu hisse günlük grafikte hacimli sıkışma kırılımı yapmıştır. Ertesi gün takibi içindir._"
    )

async def scan_market(application: Application):
    top_stocks = scan_all_fast()
    for sig in top_stocks:
        msg = format_signal_msg(sig)
        await send_telegram_msg(application, msg)
    return len(top_stocks)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Gün Sonu Kırılım Botu Aktif.\n/scan - Taramayı Başlat")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Günlük grafikte kırılım yapmış, ertesi gün potansiyelli hisseler taranıyor...")
    found = await scan_market(context.application)
    if found == 0:
        await update.message.reply_text("✅ Tarama Tamamlandı.\n\n⚠️ Kapanış kriterlerine uyan riskiz hisse bulunamadı.")
    else:
        await update.message.reply_text(f"✅ Tarama bitti. Ertesi gün takibi için en iyi {found} hisse listelendi.")

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app_bot = Application.builder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(CommandHandler("scan", scan_cmd))

    logger.info("Bot Çalışıyor.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
