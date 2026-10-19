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
# BIST PATLAMA ÖNCESİ DİP VE SIKIŞMA RADARI (BREAKOUT BEFORE MOVE)
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("SQUEEZE-RADAR")

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
    return "Pre-Breakout Squeeze Radar Active", 200

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

def download_data(ticker: str) -> pd.DataFrame:
    try:
        data = yf.download(
            ticker, period="1mo", interval="1d",
            auto_adjust=False, progress=False, threads=False, session=session, timeout=4
        )
        return clean_dataframe(data)
    except Exception:
        return pd.DataFrame()

def scan_pre_breakout(ticker: str):
    df = download_data(ticker)
    if df.empty or len(df) < 20: return None

    close = df["close"]
    open_p = df["open"]
    high = df["high"]
    low = df["low"]

    c_close = float(close.iloc[-1])
    c_open = float(open_p.iloc[-1])
    
    # 1. KRİTİK ŞART: Hisse bugün henüz yükselmemiş olmalı (Günlük Değişim %0 ile %2 arasında)
    daily_change = ((c_close - close.iloc[-2]) / close.iloc[-2]) * 100.0
    if not (0.0 <= daily_change <= 2.0):
        return None  # Zaten prim yapmış hisseleri direkt ele!

    # 2. BOLLINGER BANT SIKIŞMASI (PATLAMA İŞARETİ)
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper_band = ma20 + (std20 * 2)
    lower_band = ma20 - (std20 * 2)
    
    bandwidth = (upper_band - lower_band) / ma20
    c_bandwidth = bandwidth.iloc[-1]
    
    # Bant genişliği son 20 günün en dar seviyesinde mi?
    is_squeezed = c_bandwidth <= bandwidth.iloc[-20:].min() * 1.15
    if not is_squeezed:
        return None

    # Stop ve Hedef
    stop_price = c_close * 0.97 # %3 Stop
    tp1 = c_close * 1.05        # %5 İlk Hedef
    tp2 = c_close * 1.10        # %10 İkinci Hedef

    return {
        "ticker": ticker,
        "price": c_close,
        "daily_change": daily_change,
        "bandwidth": c_bandwidth,
        "stop": stop_price,
        "tp1": tp1,
        "tp2": tp2,
    }

def scan_all_squeeze():
    results = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        future_to_ticker = {executor.submit(scan_pre_breakout, t): t for t in TICKERS}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x["bandwidth"]) # En çok sıkışan hisseyi en başa al
    return results[:2]

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("💣 Patlamaya Hazır Dip Hisseleri Bul", callback_data="btn_scan"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "💣 *PATLAMA ÖNCESİ DİP VE SIKIŞMA RADARI* 💣\n\n"
        "Yükselmiş hisseleri eler! Henüz *yükselmemiş (%0-%1.5 primli)*, "
        "ancak bantları iyice sıkışmış ve sert patlamaya hazır dip hisseleri tespit eder.\n\n"
        "Aşağıdaki butona basarak taratabilirsiniz:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_scan":
        await query.message.reply_text("🔍 *Henüz Yükselmemiş, Dipte Sıkışan Hisseler Taranıyor...*", parse_mode="Markdown")
        signals = scan_all_squeeze()
        
        if not signals:
            await query.message.reply_text("⚠️ Şu an dipte patlama sıkışması gösteren hisse bulunamadı.")
        else:
            for sig in signals:
                symbol = sig["ticker"].replace(".IS", "")
                text = (
                    f"💣 *PATLAMA ÖNCESİ DİP HİSSE TESPİT EDİLDİ* 💣\n\n"
                    f"📌 *Hisse:* #{symbol}\n"
                    f"📊 *Bugünkü Prim:* %{sig['daily_change']:.2f} (Henüz Yükselmedi!)\n"
                    f"⚙️ *Sıkışma Seviyesi:* En Yüksek Düzey (Bollinger Squeeze)\n\n"
                    f"💵 *Dip Alış Fiyatı:* {sig['price']:.2f} TL\n"
                    f"🛑 *Zarar-Kes (Stop):* {sig['stop']:.2f} TL\n"
                    f"🎯 *Hedef 1 (TP1):* {sig['tp1']:.2f} TL\n"
                    f"🚀 *Hedef 2 (TP2):* {sig['tp2']:.2f} TL\n\n"
                    f"💡 _Bu hisse henüz prim yapmamıştır. Patlama öncesi dip fiyattadır._"
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

    logger.info("Pre-Breakout Squeeze Bot Başlatıldı.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
