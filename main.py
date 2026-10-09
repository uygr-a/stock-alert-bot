import asyncio
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
# BIST ADVANCED WHALE AUTO-ALERT & SCANNER ENGINE
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("BALENA-QUANT-AUTO")

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
    return "Auto-Notification Whale Engine Active", 200

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
            auto_adjust=False, progress=False, threads=False, session=session, timeout=5
        )
        return clean_dataframe(data)
    except Exception:
        return pd.DataFrame()

def detect_whale_footprint(ticker: str):
    df = download_data(ticker)
    if df.empty or len(df) < 30: return None

    close = df["close"]
    open_p = df["open"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    c_close = float(close.iloc[-1])
    c_open = float(open_p.iloc[-1])
    curr_vol = volume.iloc[-1]
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    
    rvol = (curr_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

    if rvol < 2.0: return None

    candle_range = high.iloc[-1] - low.iloc[-1]
    body_size = c_close - c_open
    if candle_range <= 0 or body_size <= 0: return None
    body_ratio = body_size / candle_range
    
    if body_ratio < 0.60: return None

    recent_low = low.iloc[-10:-1].min()
    swept_liquidity = low.iloc[-1] <= recent_low or low.iloc[-2] <= recent_low

    whale_score = int(min(rvol * 25 + body_ratio * 30, 99))
    
    tags = [f"🐋 Kurumsal Hacim Patlaması ({rvol:.1f}x)"]
    if swept_liquidity:
        tags.append("🎯 Balina Likidite Tuzağı (Stoplar Süpürüldü)")
    tags.append(f"🟢 Güçlü Gövde Baskısı (%{int(body_ratio*100)})")

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

    return {
        "ticker": ticker,
        "entry": c_close,
        "stop": stop_price,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "quantity": quantity,
        "score": whale_score,
        "tags": tags,
    }

def scan_all_whales():
    results = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_ticker = {executor.submit(detect_whale_footprint, ticker): ticker for ticker in TICKERS}
        for future in as_completed(future_to_ticker):
            res = future.result()
            if res:
                results.append(res)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:2]

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🐋 Anlık Balina Taraması", callback_data="btn_scan"),
        ],
        [
            InlineKeyboardButton("ℹ️ Motor Durumu", callback_data="btn_status")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def format_whale_msg(sig):
    symbol = sig["ticker"].replace(".IS", "")
    tags_str = "\n• ".join(sig["tags"])
    return (
        f"🚨 *ANLIK OTOMATİK BALİNA UYARISI* 🚨\n\n"
        f"📌 *Hisse:* #{symbol}\n"
        f"🐋 *Balina İz Skor:* %{sig['score']} / 100\n\n"
        f"💡 *Tespit Edilen Kurumsal Ayak İzi:*\n• {tags_str}\n\n"
        f"💵 *Balina Giriş Fiyatı:* {sig['entry']:.2f} TL\n"
        f"🛑 *Balina Stop-Loss:* {sig['stop']:.2f} TL\n\n"
        f"🎯 *Hedef 1 (TP1):* {sig['tp1']:.2f} TL\n"
        f"🎯 *Hedef 2 (TP2):* {sig['tp2']:.2f} TL\n"
        f"🚀 *Hedef 3 (TP3):* {sig['tp3']:.2f} TL\n\n"
        f"📦 *Önerilen Adet:* {sig['quantity']} Lot\n"
        f"⚡ _Sinyal Anında Taranıp Otomatik Gönderilmiştir._"
    )

async def auto_whale_scanner(application: Application):
    """Arka planda her 3 dakikada bir otomatik tarama yapıp Telegram'a bildirim atar."""
    sent_signals = set()
    
    while True:
        try:
            if is_bist_open() and CHAT_ID:
                signals = scan_all_whales()
                for sig in signals:
                    sig_id = f"{sig['ticker']}_{sig['entry']:.2f}"
                    if sig_id not in sent_signals and sig["score"] >= 85:
                        msg = format_whale_msg(sig)
                        await application.bot.send_message(
                            chat_id=CHAT_ID, text=msg, parse_mode="Markdown", reply_markup=get_main_keyboard()
                        )
                        sent_signals.add(sig_id)
            await asyncio.sleep(180) # 3 dakikada bir döngü
        except Exception as e:
            logger.error(f"Auto scanner error: {e}")
            await asyncio.sleep(60)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👑 *BALİNA & KURUMSAL TAKİP BOTU (OTOMATİK BİLDİRİMLİ)* 👑\n\n"
        "Bot seans boyunca BİST'i otomatik tarar ve balina tespiti yaptığı an "
        "mesajı cebinize atar."
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "btn_scan":
        await query.message.reply_text("🔍 *Kurumsal Hacimler ve Balina Ayak İzleri Taranıyor...*", parse_mode="Markdown")
        signals = scan_all_whales()
        if not signals:
            await query.message.reply_text("⚠️ Şu an tahtasında sıradışı balina alımı olan hisse tespit edilmedi.")
        else:
            for sig in signals:
                msg = format_whale_msg(sig)
                await query.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif query.data == "btn_status":
        status_txt = "🟢 *CANLI SEANS & OTO BİLDİRİM AKTİF*" if is_bist_open() else "🔴 *PİYASA KAPALI (BEKLEMEDE)*"
        await query.message.reply_text(
            f"ℹ️ *Motor Durumu:* {status_txt}\n\n"
            f"BİST Otomatik Tarama Aralığı: 3 Dakika",
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

    # Otomatik Bildirim Arka Plan Görevini Başlat
    asyncio.get_event_loop().create_task(auto_whale_scanner(app_bot))

    logger.info("Balina Takip ve Oto-Bildirim Botu Çalışıyor.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
