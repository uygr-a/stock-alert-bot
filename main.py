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
# BIST TÜM HİSSELER HACİM VE PARA GİRİŞİ RADARI
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("BIST-RADAR")

# BİST'in geniş kapsamlı hisse listesi
TICKERS = [
    "A1CAP.IS", "ADEL.IS", "ADESE.IS", "AEFES.IS", "AFYON.IS", "AGESA.IS",
    "AGHOL.IS", "AGROT.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKFYE.IS",
    "AKSA.IS", "AKSEN.IS", "ALARK.IS", "ALBRK.IS", "ALFAS.IS", "ALTNY.IS",
    "ANSGR.IS", "ARCLK.IS", "ARDYZ.IS", "ASELS.IS", "ASTOR.IS", "AYDEM.IS",
    "BAGFS.IS", "BANVT.IS", "BASGZ.IS", "BERA.IS", "BIMAS.IS", "BIOEN.IS",
    "BOBET.IS", "BRISA.IS", "BRSAN.IS", "BUCIM.IS", "CANTE.IS", "CCOLA.IS",
    "CEMTS.IS", "CIMSA.IS", "CLEBI.IS", "CWENE.IS", "DOAS.IS", "DOHOL.IS",
    "ECILC.IS", "EGEEN.IS", "EGGUB.IS", "EKGYO.IS", "ENJSA.IS", "ENKAI.IS",
    "EREGL.IS", "EUPWR.IS", "EVYRN.IS", "FROTO.IS", "GARAN.IS", "GEDIK.IS",
    "GESAN.IS", "GLYHO.IS", "GUBRF.IS", "GWIND.IS", "HALKB.IS", "HEKTS.IS",
    "IPEKE.IS", "ISCTR.IS", "ISDMR.IS", "ISMEN.IS", "IZMDC.IS", "KCAER.IS",
    "KCHOL.IS", "KMPUR.IS", "KONTR.IS", "KONYA.IS", "KORDS.IS", "KOZAA.IS",
    "KOZAL.IS", "KRDMD.IS", "KZBGY.IS", "MAVI.IS", "MGROS.IS", "MIATK.IS",
    "ODAS.IS", "ONCSM.IS", "OTKAR.IS", "OYAKC.IS", "PАЗAL.IS", "PETKM.IS",
    "PGSUS.IS", "QUAGR.IS", "REEDR.IS", "SAHOL.IS", "SASA.IS", "SISE.IS",
    "SKBNK.IS", "SMRTG.IS", "SOKM.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS",
    "TKFEN.IS", "TMSN.IS", "TOASO.IS", "TSKB.IS", "TTKOM.IS", "TTRAK.IS",
    "TUPRS.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS",
    "YKBNK.IS", "ZOREN.IS"
]

app = Flask(__name__)

@app.route("/")
def home():
    return "BIST Full Market Radar Active", 200

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

session = requests_cffi.Session(impersonate="chrome110")

def is_bist_open() -> bool:
    tz = pytz.timezone("Europe/Istanbul")
    now = datetime.now(tz)
    if now.weekday() >= 5: return False
    start_time = now.replace(hour=9, minute=50, second=0, microsecond=0)
    end_time = now.replace(hour=18, minute=10, second=0, microsecond=0)
    return start_time <= now <= end_time

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

def download_data(ticker: str) -> pd.DataFrame:
    try:
        data = yf.download(
            ticker, period="1mo", interval="15m",
            auto_adjust=False, progress=False, threads=False, session=session, timeout=4
        )
        return clean_dataframe(data)
    except Exception:
        return pd.DataFrame()

def scan_single_stock(ticker: str):
    df = download_data(ticker)
    if df.empty or len(df) < 20: return None

    close = df["close"]
    open_p = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    c_close = float(close.iloc[-1])
    c_open = float(open_p.iloc[-1])
    curr_vol = volume.iloc[-1]
    avg_vol = volume.rolling(20).mean().iloc[-1]
    
    rvol = (curr_vol / avg_vol) if avg_vol > 0 else 1.0

    # Hacim ortalamanın en az 2 katına çıkmış olmalı
    if rvol < 2.0: return None

    # Güçlü yeşil mum şartı
    candle_range = high.iloc[-1] - low.iloc[-1]
    body_size = c_close - c_open
    if candle_range <= 0 or body_size <= 0: return None
    body_ratio = body_size / candle_range
    if body_ratio < 0.60: return None

    score = int(min(rvol * 30 + body_ratio * 20, 99))

    # ATR Risk ve Hedef Hesaplama
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/10, adjust=False).mean().iloc[-1]

    stop_price = c_close - (1.1 * atr)
    risk = c_close - stop_price
    if risk <= 0: return None

    tp1 = c_close + (risk * 1.5)
    tp2 = c_close + (risk * 2.5)

    return {
        "ticker": ticker,
        "price": c_close,
        "stop": stop_price,
        "tp1": tp1,
        "tp2": tp2,
        "rvol": rvol,
        "score": score
    }

def scan_all_bist():
    results = []
    with ThreadPoolExecutor(max_workers=15) as executor:
        future_to_ticker = {executor.submit(scan_single_stock, t): t for t in TICKERS}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:3] # En güçlü ilk 3 hisse

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔍 Tüm BİST'i Tara ve Hisse Bul", callback_data="btn_scan"),
        ],
        [
            InlineKeyboardButton("ℹ️ Piyasa Durumu", callback_data="btn_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👑 *BİST TÜM HİSSELER PARA GİRİŞİ RADARI* 👑\n\n"
        "Yüzlerce BİST hissesini anlık tarayarak hacim patlaması yaşayan "
        "ve yükseliş potansiyeli olan hisseleri net fiyatıyla raporlar.\n\n"
        "Aşağıdaki butona basarak taramayı başlatabilirsin:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_scan":
        await query.message.reply_text("🔍 *Tüm BİST Hisseleri Paralel Olarak Taranıyor...*", parse_mode="Markdown")
        signals = scan_all_bist()
        
        if not signals:
            await query.message.reply_text("⚠️ Şu an hacim kriterini sağlayan belirgin bir hisse bulunamadı.")
        else:
            for sig in signals:
                symbol = sig["ticker"].replace(".IS", "")
                text = (
                    f"🎯 *BİST HACİM & PARA GİRİŞİ SİNYALİ* 🎯\n\n"
                    f"📌 *Hisse:* #{symbol}\n"
                    f"📊 *Güç Skoru:* %{sig['score']} / 100\n"
                    f"🚀 *Hacim Artışı:* {sig['rvol']:.1f}x Kat\n\n"
                    f"💵 *Anlık Alım Fiyatı:* {sig['price']:.2f} TL\n"
                    f"🛑 *Stop-Loss (Zarar Kes):* {sig['stop']:.2f} TL\n"
                    f"🎯 *Hedef 1 (TP1):* {sig['tp1']:.2f} TL\n"
                    f"🎯 *Hedef 2 (TP2):* {sig['tp2']:.2f} TL\n\n"
                    f"💡 _Botun önerdiği fiyattan alıp stop seviyesine mutlaka dikkat ediniz._"
                )
                await query.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif query.data == "btn_status":
        status_txt = "🟢 *CANLI SEANS AKTİF*" if is_bist_open() else "🔴 *PİYASA KAPALI*"
        await query.message.reply_text(
            f"ℹ️ *Sistem Durumu:* {status_txt}\n\n"
            f"Taranan Toplam Hisse Sayısı: {len(TICKERS)} Adet",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard()
        )

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app_bot = Application.builder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(CallbackQueryHandler(button_handler))

    logger.info("BIST Tüm Hisseler Radarı Başlatıldı.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
