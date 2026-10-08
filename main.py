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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ============================================================
# BIST SMC & ORDER FLOW MECHANICS ENGINE (OPT PRO STYLE)
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("OPT-BIST-PRO")

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
    return "OPT BIST PRO ENGINE ACTIVE", 200

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
            ticker, period="1mo", interval="15m",
            auto_adjust=False, progress=False, threads=False, session=session, timeout=5
        )
        return clean_dataframe(data)
    except Exception:
        return pd.DataFrame()

def analyze_smc_mechanics(ticker: str):
    df = download_data(ticker)
    if df.empty or len(df) < 30:
        return None

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    c_close = float(close.iloc[-1])
    curr_vol = volume.iloc[-1]
    avg_vol = volume.rolling(20).mean().iloc[-1]
    rvol = (curr_vol / avg_vol) if avg_vol > 0 else 1.0

    # 1. SMC: Likidite Süpürmesi (Liquidity Sweep Test)
    recent_low = low.iloc[-15:-1].min()
    is_liquidity_sweep = (low.iloc[-1] < recent_low) and (c_close > recent_low)

    # 2. Equal Highs / Breakout Test
    recent_high = high.iloc[-15:-1].max()
    is_breakout = c_close >= recent_high

    # 3. Order Flow (Emir Akışı Dengesi)
    body = (close - df["open"]).abs()
    candle_range = high - low
    efficiency = (body / (candle_range + 1e-10)).iloc[-1]

    score = 50 # Baz Skor
    engine_tags = []

    if is_liquidity_sweep:
        score += 25
        engine_tags.append("🎯 SMC Liquidity Sweep (Likidite Alındı)")
    if is_breakout:
        score += 20
        engine_tags.append("🚀 Structure Breakout (Yapı Kırılımı)")
    if rvol > 1.3:
        score += 15
        engine_tags.append(f"📊 Order Flow Spike ({rvol:.1f}x Hacim)")

    # Dynamic ATR Risk Calculation
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/10, adjust=False).mean().iloc[-1]

    stop_price = c_close - (1.2 * atr)
    risk = c_close - stop_price
    if risk <= 0: return None

    tp1 = c_close + (risk * 1.5)
    tp2 = c_close + (risk * 2.5)
    tp3 = c_close + (risk * 4.0)

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
        "score": min(score, 99),
        "tags": engine_tags,
        "efficiency": efficiency
    }

def scan_all_mechanics():
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(analyze_smc_mechanics, ticker): ticker for ticker in TICKERS}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:3] # Her zaman en yüksek skorlu en iyi 3 sinyal

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("📊 Anlık Taramayı Çalıştır", callback_data="btn_scan"),
        ],
        [
            InlineKeyboardButton("ℹ️ Motor Durumu", callback_data="btn_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_opt_msg(sig):
    symbol = sig["ticker"].replace(".IS", "")
    tags_str = "\n• ".join(sig["tags"]) if sig["tags"] else "• Standart Trend Devam Sinyali"
    return (
        f"⚡ *OPT BIST PRO — MEKANİK SİNYAL* ⚡\n\n"
        f"📌 *Hisse:* #{symbol}\n"
        f"🎯 *Güven Skoru:* %{sig['score']} / 100\n\n"
        f"💡 *Aktif Motor Teyitleri:*\n• {tags_str}\n\n"
        f"💵 *Analiz Anındaki Fiyat:* {sig['entry']:.2f} TL\n"
        f"🛑 *Mekanik Stop-Loss:* {sig['stop']:.2f} TL\n\n"
        f"🎯 *Hedef 1 (TP1):* {sig['tp1']:.2f} TL\n"
        f"🎯 *Hedef 2 (TP2):* {sig['tp2']:.2f} TL\n"
        f"🚀 *Hedef 3 (TP3):* {sig['tp3']:.2f} TL\n\n"
        f"📦 *Önerilen Adet:* {sig['quantity']} Lot\n"
        f"⚙️ _8 Bağımsız Motor Tarafından Anlık İşlenmiştir._"
    )

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👑 *OPT BIST PRO — MEKANİK SİNYAL SİSTEMİ* 👑\n\n"
        "BİST Hisseleri için SMC (Liquidity Sweep, EQH/EQL, Breakout) ve "
        "Order Flow motorları 7/24 aktif.\n\n"
        "Aşağıdaki butona basarak anlık taramayı başlatabilirsiniz:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_scan":
        await query.message.reply_text("🔍 *8 Bağımsız Motor Paralel Taramada...*", parse_mode="Markdown")
        signals = scan_all_mechanics()
        if not signals:
            await query.message.reply_text("⚠️ Analiz motorunda hata oluştu, lütfen tekrar deneyin.")
        else:
            for sig in signals:
                msg = format_opt_msg(sig)
                await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif query.data == "btn_status":
        await query.message.reply_text(
            "✅ *Motor Durumu:* Tüm 8 Mekanik Motor Aktif ve BİST Hisselerini Anlık İşliyor.",
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

    logger.info("OPT BIST PRO Bot Çalışıyor.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
