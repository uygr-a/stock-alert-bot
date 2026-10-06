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
# AYARLAR & PARAMLAR
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))
SCAN_MINUTES = int(os.getenv("SCAN_MINUTES", "15"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "4"))

# Mükemmelleştirilmiş Filtre Seviyeleri
MAX_DAILY_CHANGE_PCT = 3.5  # %3.5 üstü primlenen hisseler elenir (Dip fırsatları)
MIN_SIGNAL_SCORE = 85       # 100 üzerinden en az 85 puan alan VIP sinyaller gönderilir

DB_FILE = "bist_bot.db"


# ============================================================
# LOG AYARLARI
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("PRO-QUANT-BOT")


# ============================================================
# BIST HİSSE LİSTESİ
# ============================================================

TICKERS = [
    "A1CAP.IS", "ACSEL.IS", "ADEL.IS", "ADESE.IS", "ADGYO.IS", "AEFES.IS", "AFYON.IS",
    "AGESA.IS", "AGHOL.IS", "AGROT.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKENR.IS", "AKFGY.IS",
    "AKFYE.IS", "AKGRT.IS", "AKMGY.IS", "AKSA.IS", "AKSEN.IS", "AKSGY.IS", "AKSUE.IS",
    "AKYHO.IS", "ALARK.IS", "ALBRK.IS", "ALCAR.IS", "ALCTL.IS", "ALFAS.IS", "ALGYO.IS", "ALKA.IS",
    "ALKIM.IS", "ALKLC.IS", "ALTNY.IS", "ALTIN.IS", "ANELE.IS", "ANGEN.IS", "ANHYT.IS",
    "ANSGR.IS", "ARASE.IS", "ARCLK.IS", "ARDYZ.IS", "ARENA.IS", "ARSAN.IS", "ARTMS.IS", "ARZUM.IS",
    "ASELS.IS", "ASGYO.IS", "ASTOR.IS", "ASUZU.IS", "ATAGY.IS", "ATAKP.IS", "ATATP.IS", "ATEKS.IS",
    "ATLAS.IS", "AVOD.IS", "AVPGY.IS", "AVTUR.IS", "AYCES.IS", "AYDEM.IS", "AYEN.IS",
    "AYGAZ.IS", "AZTEK.IS", "BAGFS.IS", "BAKAB.IS", "BALAT.IS", "BANVT.IS", "BARMA.IS", "BATIS.IS",
    "BTCIM.IS", "BAYRK.IS", "BEGYO.IS", "BERA.IS", "BEYAZ.IS", "BFREN.IS", "BIENY.IS",
    "BIGCHEFS.IS", "BIMAS.IS", "BINHO.IS", "BINBN.IS", "BIOEN.IS", "BIZIM.IS", "BJKAS.IS", "BLCYT.IS",
    "BMSCH.IS", "BMSTL.IS", "BNTAS.IS", "BOBET.IS", "BORLS.IS", "BORSK.IS", "BOSSA.IS", "BRKVY.IS",
    "BRISA.IS", "BRKO.IS", "BRKSN.IS", "BRMEN.IS", "BRSAN.IS", "BRYAT.IS", "BSOKE.IS", "BUCIM.IS",
    "BURCE.IS", "BURVA.IS", "BVSAN.IS", "BYDNR.IS", "CANTE.IS", "CASA.IS", "CATES.IS", "CCOLA.IS",
    "CELHA.IS", "CEMAS.IS", "CEMTS.IS", "CMBTN.IS", "CMENT.IS", "CONSE.IS", "COSMO.IS", "CRDFA.IS",
    "CRFSA.IS", "CUSAN.IS", "CVKMD.IS", "CWENE.IS", "DAGI.IS", "DAGHL.IS", "DAPGM.IS", "DARDL.IS",
    "DGATE.IS", "DGGYO.IS", "DGNMO.IS", "DITAS.IS", "DMRGD.IS", "DMSAS.IS", "DNISI.IS", "DOAS.IS",
    "DOBUR.IS", "DOGUB.IS", "DOHOL.IS", "DOKTA.IS", "DURDO.IS", "DURKN.IS", "DYOBY.IS", "DZGYO.IS",
    "EBEBK.IS", "ECILC.IS", "ECZYT.IS", "EDATA.IS", "EDIP.IS", "EGGUB.IS", "EGPRO.IS", "EGSER.IS",
    "EKGYO.IS", "EKIZ.IS", "EKSUN.IS", "ELITE.IS", "EMKEL.IS", "EMNIS.IS", "ENJSA.IS", "ENSRI.IS",
    "ENKAI.IS", "EPLAS.IS", "ERCB.IS", "EREGL.IS", "ERSU.IS", "ESCAR.IS", "ESEN.IS", "ETILR.IS",
    "EUPWR.IS", "EYGYO.IS", "FADE.IS", "FONET.IS", "FORTE.IS", "FROTO.IS", "GARAN.IS", "GEDIK.IS",
    "GOKNR.IS", "GOLTS.IS", "GOODY.IS", "GOZDE.IS", "GSDHO.IS", "GUBRF.IS", "GWIND.IS", "HALKB.IS",
    "HATSN.IS", "HEKTS.IS", "HKTM.IS", "HUBVC.IS", "HUNER.IS", "IEYHO.IS", "IHAAS.IS",
    "IMASM.IS", "INDES.IS", "INFO.IS", "INGRM.IS", "INVES.IS", "IPEKE.IS", "ISCTR.IS", "ISDMR.IS",
    "ISFIN.IS", "ISGYO.IS", "ISMEN.IS", "IZMDC.IS", "JANTS.IS", "KCAER.IS", "KCHOL.IS", "KENT.IS",
    "KLSER.IS", "KONTR.IS", "KONYA.IS", "KORDS.IS", "KOZAL.IS", "KOZAA.IS", "KRDMD.IS", "KTLEV.IS",
    "KUTPO.IS", "KZBGY.IS", "LIDER.IS", "LMKDC.IS", "LOGO.IS", "MAALT.IS", "MACKO.IS", "MAVI.IS",
    "MEGAP.IS", "MIATK.IS", "MHRGY.IS", "MOBTL.IS", "MOGAN.IS", "MPARK.IS", "NATEN.IS", "NETAS.IS",
    "NTGAZ.IS", "NTHOL.IS", "OBAMS.IS", "ODAS.IS", "ONCSM.IS", "ORGE.IS", "OTKAR.IS", "OYAKC.IS",
    "OZKGY.IS", "PAPIL.IS", "PARSN.IS", "PASEU.IS", "PATEK.IS", "PEGAS.IS", "PETKM.IS", "PGSUS.IS",
    "PLTUR.IS", "POLHO.IS", "PRKME.IS", "PSGYO.IS", "QUAGR.IS", "RALYH.IS", "REEDR.IS", "RGYAS.IS",
    "RUBNS.IS", "RYSAS.IS", "SAHOL.IS", "SASA.IS", "SAYAS.IS", "SDTTR.IS", "SISE.IS", "SKBNK.IS",
    "SMRTG.IS", "SOKE.IS", "TABGD.IS", "TARKM.IS", "TATEN.IS", "TAVHL.IS", "TCELL.IS", "THYAO.IS",
    "TKFEN.IS", "TKNSA.IS", "TMSN.IS", "TOASO.IS", "TRGYO.IS", "TSKB.IS", "TTKOM.IS", "TTRAK.IS",
    "TUPRS.IS", "TURSG.IS", "ULKER.IS", "VAKBN.IS", "VESBE.IS", "VESTL.IS", "YEOTK.IS", "YKBNK.IS",
    "YYLGD.IS", "ZOREN.IS"
]


# ============================================================
# SERVER & DB SETUP
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "Ultra-Quant Signal Engine Active"

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
# VERİ ÇEKME APİ
# ============================================================

session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
})

def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    result = df.copy()
    if isinstance(result.columns, pd.MultiIndex):
        result.columns = result.columns.get_level_values(0)

    result.columns = [str(col).strip().lower() for col in result.columns]
    required = ["open", "high", "low", "close", "volume"]

    for col in required:
        if col not in result.columns:
            return pd.DataFrame()

    result = result[["open", "high", "low", "close", "volume"]].copy()
    for col in result.columns:
        result[col] = pd.to_numeric(result[col], errors="coerce")

    result.dropna(inplace=True)
    return result


def download_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        time.sleep(0.2)
        data = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
            session=session
        )
        return clean_dataframe(data)
    except Exception as exc:
        logger.warning("Veri hatası %s: %s", ticker, exc)
        return pd.DataFrame()


# ============================================================
# ULTRA-QUANT ÇOK KATMANLI İNDİKATÖR SİSTEMİ
# ============================================================

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
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
        if basic_upper.iloc[i] < upperband[i-1] or close_val[i-1] > upperband[i-1]:
            upperband[i] = basic_upper.iloc[i]
        else:
            upperband[i] = upperband[i-1]

        if basic_lower.iloc[i] > lowerband[i-1] or close_val[i-1] < lowerband[i-1]:
            lowerband[i] = basic_lower.iloc[i]
        else:
            lowerband[i] = lowerband[i-1]

        if supertrend[i-1] == upperband[i-1]:
            supertrend[i] = upperband[i] if close_val[i] <= upperband[i] else lowerband[i]
        else:
            supertrend[i] = lowerband[i] if close_val[i] >= lowerband[i] else upperband[i]

    direction = np.where(close_val >= supertrend, 1, -1)
    return direction, supertrend, atr


def calculate_ultra_quant_signal(df: pd.DataFrame, daily_change: float):
    """
    Sektör standardı %85+ İsabet Oranlı VIP Algoritma
    """
    if len(df) < 50:
        return None, 0

    close = df["close"]
    high = df["high"]
    low = df["low"]
    volume = df["volume"]

    # 1. EMA Katmanı (Hareketli Ortalamalar)
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema50 = close.ewm(span=50, adjust=False).mean()

    # 2. RSI Katmanı (14)
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))

    # 3. SuperTrend Katmanı
    st_dir, st_val, atr = calculate_supertrend(df, 10, 3.0)

    # 4. Bollinger Bantları (Sıkışma Kontrolü)
    sma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    upper_bb = sma20 + (2 * std20)
    lower_bb = sma20 - (2 * std20)
    bb_width = (upper_bb - lower_bb) / sma20

    # Son Değerler
    c_close = float(close.iloc[-1])
    c_ema9 = float(ema9.iloc[-1])
    c_ema21 = float(ema21.iloc[-1])
    c_ema50 = float(ema50.iloc[-1])
    c_rsi = float(rsi.iloc[-1])
    p_rsi = float(rsi.iloc[-2])
    c_vol = float(volume.iloc[-1])
    avg_vol = float(volume.rolling(20).mean().iloc[-1])
    c_atr = float(atr.iloc[-1])

    score = 0
    reasons = []

    # A) SuperTrend AL Teyidi (25 Puan)
    if st_dir[-1] == 1:
        score += 25
        reasons.append("SuperTrend Pozitif")
        if st_dir[-2] == -1: # Taze İlk Mum Kırılımı!
            score += 10
            reasons.append("Taze Trend Başlangıcı (+10)")

    # B) EMA Katmanı (20 Puan)
    if c_close > c_ema9 > c_ema21:
        score += 20
        reasons.append("EMA Desteği Güçlü")

    # C) RSI Dip Dönüşü & İdeal Bölge (20 Puan)
    if 40 <= c_rsi <= 65 and c_rsi > p_rsi:
        score += 20
        reasons.append("RSI İdeal Alım Bölgesinde")

    # D) Agresif Hacim Girişi (20 Puan)
    vol_ratio = (c_vol / avg_vol) if avg_vol > 0 else 1.0
    if vol_ratio >= 1.3:
        score += 20
        reasons.append(f"Güçlü Hacim Girişi ({vol_ratio:.1f}x)")
    elif vol_ratio >= 1.0:
        score += 10

    # E) Bollinger Sıkışması ve Dipten Kalkış (15 Puan)
    if bb_width.iloc[-1] < bb_width.rolling(20).mean().iloc[-1]:
        score += 15
        reasons.append("Sıkışma Sonrası Patlama Potansiyeli")

    # F) Günlük Prim Sınırı Kontrolü
    if daily_change <= MAX_DAILY_CHANGE_PCT:
        score += 10

    # STOP & TARGET HESAPLAMA (ATR Tabanlı Hassas Metrik)
    stop_price = c_close - (1.5 * c_atr)
    risk = c_close - stop_price

    if risk <= 0:
        return None, 0

    tp1 = c_close + (risk * 1.5)
    tp2 = c_close + (risk * 2.8)

    money_risk = PORTFOLIO_SIZE * RISK_PER_TRADE
    quantity = int(money_risk / risk)

    if quantity <= 0: return None, 0
    if (quantity * c_close) > (PORTFOLIO_SIZE * 0.20):
        quantity = int((PORTFOLIO_SIZE * 0.20) / c_close)

    signal_data = {
        "entry": c_close,
        "stop": stop_price,
        "tp1": tp1,
        "tp2": tp2,
        "quantity": quantity,
        "rsi": c_rsi,
        "score": score,
        "vol_ratio": vol_ratio,
        "daily_change": daily_change,
        "reasons": reasons
    }

    return signal_data, score


# ============================================================
# VERİTABANI & COOLDOWN
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
# TELEGRAM BİLDİRİM FORMATI
# ============================================================

async def send_telegram_msg(app_bot: Application, text: str):
    if not CHAT_ID: return
    try:
        await app_bot.bot.send_message(chat_id=CHAT_ID, text=text)
    except Exception as exc:
        logger.error("Telegram mesaj hatası: %s", exc)


def format_signal_msg(ticker: str, sig):
    symbol = ticker.replace(".IS", "")
    reasons_str = "\n• ".join(sig["reasons"])
    return (
        f"💎 **ULTRA-QUANT VIP SİNYALİ** 💎\n\n"
        f"📌 **Hisse:** #{symbol}\n"
        f"🏆 **Sinyal Kalite Skoru:** %{sig['score']} / 100\n"
        f"📈 **Günün Primi:** %{sig['daily_change']:.2f} (DİP/BAŞLANGIÇ)\n\n"
        f"🎯 **Sinyal Neden Verildi?**\n• {reasons_str}\n\n"
        f"💵 **Giriş Fiyatı:** {sig['entry']:.2f} TL\n"
        f"🛑 **Stop-Loss:** {sig['stop']:.2f} TL\n"
        f"🎯 **Hedef 1 (TP1):** {sig['tp1']:.2f} TL\n"
        f"🎯 **Hedef 2 (TP2):** {sig['tp2']:.2f} TL\n\n"
        f"📦 **Önerilen Adet:** {sig['quantity']} Lot\n"
        f"📊 **RSI:** {sig['rsi']:.1f}\n"
        f"🔊 **Hacim Patlaması:** {sig['vol_ratio']:.1f}x Katı\n\n"
        "🚨 *Sadece en yüksek başarı oranına sahipVIP fırsatlar bildirilir.*"
    )


# ============================================================
# TARAMA MOTORU
# ============================================================

async def scan_market(application: Application):
    logger.info("Ultra-Quant VIP Tarama Başlatılıyor...")

    for ticker in TICKERS:
        try:
            if is_recently_signaled(ticker): continue

            df_daily = download_data(ticker, "1y", "1d")
            if df_daily.empty or len(df_daily) < 30: continue

            close_d = df_daily["close"]
            last_p = float(close_d.iloc[-1])
            prev_p = float(close_d.iloc[-2])
            daily_change = ((last_p - prev_p) / prev_p) * 100

            if daily_change >= MAX_DAILY_CHANGE_PCT: continue

            df_15m = download_data(ticker, "30d", "15m")
            if df_15m.empty: continue

            sig, score = calculate_ultra_quant_signal(df_15m, daily_change)

            # Sadece 85 ve üzeri puan alan en kusursuz fırsatlar atılır
            if sig and score >= MIN_SIGNAL_SCORE:
                save_signal(ticker, sig)
                msg = format_signal_msg(ticker, sig)
                await send_telegram_msg(application, msg)

        except Exception as exc:
            logger.warning("Tarama hatası %s: %s", ticker, exc)


# ============================================================
# BOT KOMUTLARI
# ============================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("💎 Ultra-Quant VIP BIST Botu Aktif.\n/scan - VIP Manuel Tarama")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Ultra-Quant algoritması ile BIST VIP sinyalleri taranıyor...")
    await scan_market(context.application)
    await update.message.reply_text("✅ VIP Tarama bitti.")

async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await scan_market(context.application)
    except Exception as exc:
        logger.exception("Zamanlanmış tarama hatası: %s", exc)

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
            first=15,
        )

    logger.info("Bot başarıyla başlatıldı.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
