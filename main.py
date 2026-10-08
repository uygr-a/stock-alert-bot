import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

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
# INSTITUTIONAL SMART MONEY & BREAKOUT ENGINE
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))
SCAN_MINUTES = int(os.getenv("SCAN_MINUTES", "15"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "4"))

# OPTİMİZE EDİLMİŞ DENGELİ FİLTRELER
MIN_RVOL = 1.6                # Anlık hacim artış eşiği
MIN_SIGNAL_SCORE = 70         # En yüksek kaliteli sinyal eşiği
MAX_DAILY_CHANGE_PCT = 5.0    # %5.0 üstü tavan riski olanlar elenir

DB_FILE = "bist_bot.db"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("QUANT-PRO")

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
    return "Institutional Quant Engine Active"

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
        time.sleep(0.2)
        data = yf.download(
            ticker, period=period, interval=interval,
            auto_adjust=False, progress=False, threads=False, session=session
        )
        return clean_dataframe(data)
    except Exception as exc:
        logger.warning(f"Veri çekme hatası ({ticker}): {exc}")
        return pd.DataFrame()

# ============================================================
# Gelişmiş İndikatör Hesaplamaları
# ============================================================

def calculate_rsi(series: pd.Series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

def calculate_cmf(df: pd.DataFrame, period=20):
    mf_multiplier = ((df["close"] - df["low"]) - (df["high"] - df["close"])) / (df["high"] - df["low"] + 1e-10)
    mf_volume = mf_multiplier * df["volume"]
    return mf_volume.rolling(period).sum() / (df["volume"].rolling(period).sum() + 1e-10)

def analyze_institutional_setup(df_15m: pd.DataFrame):
    if len(df_15m) < 30:
        return None, 0

    close = df_15m["close"]
    high = df_15m["high"]
    low = df_15m["low"]
    volume = df_15m["volume"]

    c_close = float(close.iloc[-1])

    # 1. Hacim Şiddeti (RVOL)
    curr_vol = volume.iloc[-1]
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    rvol = (curr_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # 2. VWAP (Ağırlıklı Ortalama Fiyat)
    vwap = (volume * (high + low + close) / 3).cumsum() / (volume.cumsum() + 1e-10)
    c_vwap = float(vwap.iloc[-1])

    # 3. CMF (Chaikin Money Flow - Para Akışı)
    cmf = calculate_cmf(df_15m, 20)
    c_cmf = float(cmf.iloc[-1])

    # 4. RSI & Hareketli Ortalamalar
    rsi = calculate_rsi(close, 14)
    c_rsi = float(rsi.iloc[-1])

    ema9 = close.ewm(span=9, adjust=False).mean().iloc[-1]
    ema21 = close.ewm(span=21, adjust=False).mean().iloc[-1]

    # Zirve Kırılımı (Kısa Vadeli Direnç)
    prev_max_15 = high.iloc[-15:-1].max()
    is_breakout = c_close >= prev_max_15

    score = 0
    reasons = []

    # SİNYAL PUANLAMA
    if c_close > c_vwap:
        score += 25
        reasons.append("📊 Kurumsal VWAP Üzerinde (Güçlü Alıcı)")

    if c_cmf > 0.02:
        score += 25
        reasons.append(f"🐋 Net Para Girişi Var (CMF: {c_cmf:.2f})")

    if rvol >= MIN_RVOL:
        score += 25
        reasons.append(f"🔥 Hacim Patlaması ({rvol:.1f}x Katı)")

    if is_breakout:
        score += 15
        reasons.append("🚀 15 Mumluk Direnç Kırıldı")

    if 45 <= c_rsi <= 68:
        score += 10
        reasons.append(f"📈 Momentum Uygun (RSI: {c_rsi:.0f})")

    if score < MIN_SIGNAL_SCORE:
        return None, score

    # ATR TABANLI DİNAMİK RİSK MİMARİSİ
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/10, adjust=False).mean().iloc[-1]

    stop_price = c_close - (1.3 * atr)
    risk = c_close - stop_price
    if risk <= 0: return None, 0

    tp1 = c_close + (risk * 1.5)
    tp2 = c_close + (risk * 2.8)
    tp3 = c_close + (risk * 4.5)

    money_risk = PORTFOLIO_SIZE * RISK_PER_TRADE
    quantity = int(money_risk / risk)
    if quantity <= 0: return None, 0

    if (quantity * c_close) > (PORTFOLIO_SIZE * 0.15):
        quantity = int((PORTFOLIO_SIZE * 0.15) / c_close)

    return {
        "entry": c_close,
        "stop": stop_price,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "quantity": quantity,
        "score": score,
        "rvol": rvol,
        "reasons": reasons
    }, score

def is_recently_signaled(ticker: str) -> bool:
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        row = conn.execute(
            "SELECT created_at FROM trades WHERE ticker = ? ORDER BY id DESC LIMIT 1",
            (ticker,),
        ).fetchone()
        conn.close()

    if not row: return False
    try:
        created = datetime.fromisoformat(row[0])
        hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        return hours < COOLDOWN_HOURS
    except Exception:
        return False

def save_signal(ticker: str, sig):
    created = datetime.now(timezone.utc).isoformat()
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            """
            INSERT INTO trades (ticker, entry, stop, tp1, tp2, tp3, quantity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, sig["entry"], sig["stop"], sig["tp1"], sig["tp2"], sig["tp3"], sig["quantity"], created),
        )
        conn.commit()
        conn.close()

async def send_telegram_msg(app_bot: Application, text: str):
    if not CHAT_ID: return
    try:
        await app_bot.bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.error(f"Telegram mesaj hatası: {exc}")

def format_signal_msg(ticker: str, sig):
    symbol = ticker.replace(".IS", "")
    reasons_str = "\n• ".join(sig["reasons"])
    return (
        f"🎯 *KURUMSAL PATLAMA SİNYALİ* 🎯\n\n"
        f"📌 *Hisse:* #{symbol}\n"
        f"🔥 *Kalite Skoru:* %{sig['score']} / 100\n"
        f"📊 *Hacim Şiddeti:* {sig['rvol']:.1f}x Katı!\n\n"
        f"💡 *Sistem Teyitleri:*\n• {reasons_str}\n\n"
        f"💵 *BUY (Giriş Fiyatı):* {sig['entry']:.2f} TL\n"
        f"🛑 *STOP-LOSS:* {sig['stop']:.2f} TL\n\n"
        f"🎯 *TP1 (İlk Hedef):* {sig['tp1']:.2f} TL\n"
        f"🎯 *TP2 (Ana Hedef):* {sig['tp2']:.2f} TL\n"
        f"🚀 *TP3 (Trend Hedefi):* {sig['tp3']:.2f} TL\n\n"
        f"📦 *Önerilen Adet:* {sig['quantity']} Lot\n\n"
        "⚡ _Smart Money Flow algoritması tarafından tespit edilmiştir._"
    )

async def scan_market(application: Application):
    logger.info("Piyasa Taraması Başlıyor...")
    found_count = 0

    for ticker in TICKERS:
        try:
            if is_recently_signaled(ticker): continue

            df_daily = download_data(ticker, "1mo", "1d")
            if df_daily.empty or len(df_daily) < 10: continue

            close_d = df_daily["close"]
            last_p = float(close_d.iloc[-1])
            prev_p = float(close_d.iloc[-2])
            daily_change = ((last_p - prev_p) / prev_p) * 100

            if daily_change > MAX_DAILY_CHANGE_PCT or daily_change < -2.0: continue

            df_15m = download_data(ticker, "5d", "15m")
            if df_15m.empty: continue

            sig, score = analyze_institutional_setup(df_15m)

            if sig and score >= MIN_SIGNAL_SCORE:
                save_signal(ticker, sig)
                msg = format_signal_msg(ticker, sig)
                await send_telegram_msg(application, msg)
                found_count += 1

        except Exception as exc:
            logger.warning(f"Tarama hatası {ticker}: {exc}")

    return found_count

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Institutional Quant Bot Aktif.\n/scan - Taramayı Başlat")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Piyasa kurumsal para girişi ve hacim patlaması için taranıyor...")
    found = await scan_market(context.application)
    if found == 0:
        await update.message.reply_text("✅ Tarama Tamamlandı.\n\n⚠️ *Not:* Şu anki mum diliminde %70 kalite skorunu geçen alım fırsatı bulunamadı.")
    else:
        await update.message.reply_text(f"✅ Tarama Tamamlandı. Toplam {found} adet yüksek kaliteli sinyal gönderildi.")

async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await scan_market(context.application)
    except Exception as exc:
        logger.exception(f"Zamanlanmış tarama hatası: {exc}")

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    init_db()

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app_bot = Application.builder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(CommandHandler("scan", scan_cmd))

    if app_bot.job_queue is not None:
        app_bot.job_queue.run_repeating(
            scheduled_job,
            interval=SCAN_MINUTES * 60,
            first=10,
        )

    logger.info("Quant Bot Çalışıyor.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
