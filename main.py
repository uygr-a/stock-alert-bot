import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ============================================================
# CANAVAR SİSTEM PARAMETRELERİ (MONSTER QUANT ENGINE)
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.01"))  # Trade başı %1 risk
SCAN_MINUTES = int(os.getenv("SCAN_MINUTES", "15"))           # Rate limit yememek için 15 dk idealdir
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "6"))        # Aynı hisse için 6 saat soğuma

# Sert Filtreler (Aynı Gün İvme Yakalama)
MIN_RVOL = 2.0                # Anlık hacim, kendi ortalamasının en az 2 katı olmalı
MIN_SIGNAL_SCORE = 90         # 100 üzerinden minimum 90 puan alan KUSURSUZ sinyaller
MAX_DAILY_CHANGE_PCT = 4.5    # %4.5 üzeri primlenen hisseler kaçmıştır, girilmez

DB_FILE = "bist_bot.db"

# ============================================================
# LOG AYARLARI
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("MONSTER-QUANT")

# ============================================================
# BIST HİSSE LİSTESİ (HATALI BİST KODLARI TEMİZLENDİ)
# ============================================================

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

# ============================================================
# SERVER & DB
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Monster High-Frequency Momentum Engine Active"

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
                quantity INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

# ============================================================
# GÜVENLİ & ANTİ-BLOCK VERİ ÇEKME MOTORU
# ============================================================

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
    """Rate limit (HTTP 429) engeline takılmamak için beklemeli indirme"""
    for attempt in range(2):
        try:
            time.sleep(0.4) # Yahoo Finance engelini aşmak için gecikme artırıldı
            t = yf.Ticker(ticker)
            data = t.history(period=period, interval=interval, auto_adjust=False)
            cleaned = clean_dataframe(data)
            if not cleaned.empty:
                return cleaned
        except Exception as exc:
            logger.warning(f"Veri çekme denemesi {attempt+1} başarısız ({ticker}): {exc}")
            time.sleep(1)
    return pd.DataFrame()

# ============================================================
# CANAVAR ALGORİTMA ENGINE (MOMENTUM BREAKOUT)
# ============================================================

def calculate_supertrend(df: pd.DataFrame, period=10, multiplier=2.5):
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (high + low) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    upperband = np.zeros(len(df))
    lowerband = np.zeros(len(df))
    supertrend = np.zeros(len(df))
    close_val = close.values

    for i in range(1, len(df)):
        upperband[i] = basic_upper.iloc[i] if basic_upper.iloc[i] < upperband[i-1] or close_val[i-1] > upperband[i-1] else upperband[i-1]
        lowerband[i] = basic_lower.iloc[i] if basic_lower.iloc[i] > lowerband[i-1] or close_val[i-1] < lowerband[i-1] else lowerband[i-1]
        
        if supertrend[i-1] == upperband[i-1]:
            supertrend[i] = upperband[i] if close_val[i] <= upperband[i] else lowerband[i]
        else:
            supertrend[i] = lowerband[i] if close_val[i] >= lowerband[i] else upperband[i]

    direction = np.where(close_val >= supertrend, 1, -1)
    return direction, supertrend, atr

def analyze_monster_momentum(df_15m: pd.DataFrame, daily_change: float):
    if len(df_15m) < 40:
        return None, 0

    close = df_15m["close"]
    high = df_15m["high"]
    low = df_15m["low"]
    volume = df_15m["volume"]

    # 1. ANLIK SAAT-BAŞI LİKİDİTE PATLAMASI (RVOL)
    curr_vol = volume.iloc[-1]
    avg_vol_20 = volume.rolling(20).mean().iloc[-1]
    rvol = (curr_vol / avg_vol_20) if avg_vol_20 > 0 else 1.0

    # 2. VWAP (Hacim Ağırlıklı Ortalama Fiyat)
    vwap = (volume * (high + low + close) / 3).cumsum() / volume.cumsum()

    # 3. EMA & SuperTrend
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    st_dir, st_val, atr = calculate_supertrend(df_15m, 10, 2.5)

    # 4. Günlük En Yüksek (HOD) Seviyesi
    hod_20 = high.iloc[-20:-1].max()

    c_close = float(close.iloc[-1])
    c_vwap = float(vwap.iloc[-1])
    c_ema9 = float(ema9.iloc[-1])
    c_ema21 = float(ema21.iloc[-1])
    c_atr = float(atr.iloc[-1])

    score = 0
    reasons = []

    # --- KRİTİK KOŞULLAR VE PUANLAMA ---

    # A) Kurumsal Hacim İstilası (35 Puan)
    if rvol >= MIN_RVOL and c_close > c_vwap:
        score += 35
        reasons.append(f"🔥 Kurumsal Balina Girişi (RVOL: {rvol:.1f}x Katı)")
    elif rvol >= 1.4 and c_close > c_vwap:
        score += 20
        reasons.append(f"⚡ Güçlü Hacim Artışı ({rvol:.1f}x)")

    # B) Günün En Yüksek (HOD) Kırılımı (25 Puan)
    if c_close >= hod_20:
        score += 25
        reasons.append("🚀 Günün En Yükseği (HOD) Kırıldı - Patlama Başladı")

    # C) Hızlı EMA Cross ve SuperTrend (20 Puan)
    if c_close > c_ema9 > c_ema21 and st_dir[-1] == 1:
        score += 20
        reasons.append("📈 Mükemmel İvme ve Trend Uyumum")

    # D) Sıkışma Sonrası Fırlama (10 Puan)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    bb_width = ((sma20 + 2*std20) - (sma20 - 2*std20)) / sma20
    if bb_width.iloc[-1] < bb_width.rolling(20).mean().iloc[-1]:
        score += 10
        reasons.append("💥 Volatiliteli Sıkışma Patlaması")

    # E) İdeal Dip/Erken Giriş Filtresi (10 Puan)
    if 0.2 <= daily_change <= MAX_DAILY_CHANGE_PCT:
        score += 10
        reasons.append(f"🎯 Erken Momentum Girişi (Tavan Değil: %{daily_change:.2f})")

    if score < MIN_SIGNAL_SCORE:
        return None, score

    # --- ANLIK DİNAMİK STOP VE HEDEF ---
    stop_price = c_close - (1.3 * c_atr)  # Çok dar ve güvenli stop
    risk = c_close - stop_price
    if risk <= 0: return None, 0

    tp1 = c_close + (risk * 1.8)   # İvmenin ilk durağı (%2 - %4)
    tp2 = c_close + (risk * 3.2)   # İkinci büyük dalga (%5 - %8)

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
        "quantity": quantity,
        "score": score,
        "rvol": rvol,
        "daily_change": daily_change,
        "reasons": reasons
    }, score

# ============================================================
# DB & COOLDOWN
# ============================================================

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
            INSERT INTO trades (ticker, entry, stop, tp1, tp2, quantity, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (ticker, sig["entry"], sig["stop"], sig["tp1"], sig["tp2"], sig["quantity"], created),
        )
        conn.commit()
        conn.close()

# ============================================================
# TELEGRAM MESAJ FORMATI
# ============================================================

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
        f"⚡ *CANAVAR MOMENTUM SİNYALİ* ⚡\n\n"
        f"📌 *Hisse:* #{symbol}\n"
        f"🔥 *Sinyal Gücü:* %{sig['score']} / 100\n"
        f"📈 *Günlük Prim:* %{sig['daily_change']:.2f}\n"
        f"📊 *Hacim Şiddeti (RVOL):* {sig['rvol']:.1f}x Katı Hacim!\n\n"
        f"🎯 *Kırılım Teyitleri:*\n• {reasons_str}\n\n"
        f"💵 *Anlık Giriş:* {sig['entry']:.2f} TL\n"
        f"🛑 *Dar Stop-Loss:* {sig['stop']:.2f} TL\n"
        f"🚀 *Hedef 1 (Aynı Gün):* {sig['tp1']:.2f} TL\n"
        f"🎯 *Hedef 2 (Ana Hedef):* {sig['tp2']:.2f} TL\n\n"
        f"📦 *Pozisyon:* {sig['quantity']} Lot\n\n"
        "🚨 _Bu sinyal hacim patlaması ve HOD kırılımı ile anlık ivme için üretilmiştir!_"
    )

# ============================================================
# SCANNER ENGINE
# ============================================================

async def scan_market(application: Application):
    logger.info("Monster Momentum Taraması Başlıyor...")

    for ticker in TICKERS:
        try:
            if is_recently_signaled(ticker): continue

            # Günlük Kontrol
            df_daily = download_data(ticker, "1mo", "1d")
            if df_daily.empty or len(df_daily) < 10: continue

            close_d = df_daily["close"]
            last_p = float(close_d.iloc[-1])
            prev_p = float(close_d.iloc[-2])
            daily_change = ((last_p - prev_p) / prev_p) * 100

            if daily_change > MAX_DAILY_CHANGE_PCT or daily_change < -1.5: continue

            # 15 Dakikalık Canavar Taraması
            df_15m = download_data(ticker, "5d", "15m")
            if df_15m.empty: continue

            sig, score = analyze_monster_momentum(df_15m, daily_change)

            if sig and score >= MIN_SIGNAL_SCORE:
                save_signal(ticker, sig)
                msg = format_signal_msg(ticker, sig)
                await send_telegram_msg(application, msg)

        except Exception as exc:
            logger.warning(f"Tarama hatası {ticker}: {exc}")

# ============================================================
# BOT MAIN
# ============================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Monster Quant Engine Aktif.\n/scan - Canavar Manuel Tarama")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ Hacim patlaması yaşayan ve patlamaya hazır hisseler taranıyor...")
    await scan_market(context.application)
    await update.message.reply_text("✅ Canavar Tarama Tamamlandı.")

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

    logger.info("Monster Quant Engine Çalışıyor.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
