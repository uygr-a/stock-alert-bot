import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ============================================================
# AYARLAR
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))
SCAN_MINUTES = int(os.getenv("SCAN_MINUTES", "15"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "4"))
MIN_DAILY_VALUE = float(os.getenv("MIN_DAILY_VALUE", "15000000"))

# Maksimum İzin Verilen Günlük Prim (%2.5 üzerini bot kesinlikle almaz)
MAX_DAILY_CHANGE_PCT = 2.5 

DB_FILE = "bist_bot.db"


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("BIST-BUYSELL-BOT")


# ============================================================
# BIST HİSSE LİSTESİ
# ============================================================

TICKERS = [
    "AAVT.IS", "A1CAP.IS", "ACSEL.IS", "ADEL.IS", "ADESE.IS", "ADGYO.IS", "AEFES.IS", "AFYON.IS",
    "AGESA.IS", "AGHOL.IS", "AGROT.IS", "AHGAZ.IS", "AKBNK.IS", "AKCNS.IS", "AKENR.IS", "AKFGY.IS",
    "AKFYE.IS", "AKGRT.IS", "AKMGY.IS", "AKSA.IS", "AKSEN.IS", "AKSGY.IS", "AKSUE.IS", "AKTIF.IS",
    "AKYHO.IS", "ALARK.IS", "ALBRK.IS", "ALCAR.IS", "ALCTL.IS", "ALFAS.IS", "ALGYO.IS", "ALKA.IS",
    "ALKIM.IS", "ALKLC.IS", "ALTNY.IS", "ALMAD.IS", "ALTIN.IS", "ANELE.IS", "ANGEN.IS", "ANHYT.IS",
    "ANSGR.IS", "ARASE.IS", "ARCLK.IS", "ARDYZ.IS", "ARENA.IS", "ARSAN.IS", "ARTMS.IS", "ARZUM.IS",
    "ASELS.IS", "ASGYO.IS", "ASTOR.IS", "ASUZU.IS", "ATAGY.IS", "ATAKP.IS", "ATATP.IS", "ATEKS.IS",
    "ATSYH.IS", "ATLAS.IS", "AVOD.IS", "AVPGY.IS", "AVTUR.IS", "AYCES.IS", "AYDEM.IS", "AYEN.IS",
    "AYGAZ.IS", "AZTEK.IS", "BAGFS.IS", "BAKAB.IS", "BALAT.IS", "BANVT.IS", "BARMA.IS", "BATIS.IS",
    "BTCIM.IS", "BAYRK.IS", "BEGYO.IS", "BEVT.IS", "BERA.IS", "BEYAZ.IS", "BFREN.IS", "BIENY.IS",
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
    "HATSN.IS", "HEKTS.IS", "HKTM.IS", "HOLDR.IS", "HUBVC.IS", "HUNER.IS", "IEYHO.IS", "IHAAS.IS",
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
# SERVER & DB
# ============================================================

app = Flask(__name__)

@app.route("/")
def home():
    return "BUY/SELL SIGNAL BOT ACTIVE"

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
# TEKNİK VERİ ÇEKME & TEMİZLEME
# ============================================================

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
        data = yf.download(
            ticker,
            period=period,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
        return clean_dataframe(data)
    except Exception as exc:
        logger.warning("Veri hatası %s: %s", ticker, exc)
        return pd.DataFrame()


# ============================================================
# "BUY / SELL" İNDİKATÖR HESAPLAMALARI
# ============================================================

def calculate_atr(df: pd.DataFrame, period: int = 10) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    atr = calculate_atr(df, period)
    hl2 = (df["high"] + df["low"]) / 2

    basic_upperband = hl2 + (multiplier * atr)
    basic_lowerband = hl2 - (multiplier * atr)

    upperband = np.zeros(len(df))
    lowerband = np.zeros(len(df))
    supertrend = np.zeros(len(df))

    close = df["close"].values

    for i in range(1, len(df)):
        if basic_upperband.iloc[i] < upperband[i-1] or close[i-1] > upperband[i-1]:
            upperband[i] = basic_upperband.iloc[i]
        else:
            upperband[i] = upperband[i-1]

        if basic_lowerband.iloc[i] > lowerband[i-1] or close[i-1] < lowerband[i-1]:
            lowerband[i] = basic_lowerband.iloc[i]
        else:
            lowerband[i] = lowerband[i-1]

        if supertrend[i-1] == upperband[i-1]:
            supertrend[i] = upperband[i] if close[i] <= upperband[i] else lowerband[i]
        else:
            supertrend[i] = lowerband[i] if close[i] >= lowerband[i] else upperband[i]

    direction = np.where(close >= supertrend, 1, -1) # 1 = BEYAZ/YEŞİL (AL), -1 = KIRMIZI (SAT)
    return direction, supertrend, atr


# ============================================================
# BAYS/SELL SİNYAL KONTROLÜ
# ============================================================

def analyze_buy_signal(df_15m: pd.DataFrame, daily_change: float):
    if len(df_15m) < 50:
        return None

    # Tamamlanmamış son canlı mumu devre dışı bırak
    df = df_15m.iloc[:-1].copy()

    direction, supertrend, atr = calculate_supertrend(df, period=10, multiplier=3.0)
    rsi_series = calculate_rsi(df["close"], 14)
    vol_avg = df["volume"].rolling(20).mean()

    curr_dir = direction[-1]
    prev_dir = direction[-2]

    curr_close = float(df["close"].iloc[-1])
    curr_rsi = float(rsi_series.iloc[-1])
    curr_vol = float(df["volume"].iloc[-1])
    avg_vol = float(vol_avg.iloc[-1])
    curr_atr = float(atr.iloc[-1])

    # KURAL 1: Tam bu mumda Supertrend KIRMIZI'dan YEŞİL'e geçmiş olmalı ("BUY" Oku Çıktığı An)
    is_buy_arrow = (prev_dir == -1) and (curr_dir == 1)

    if not is_buy_arrow:
        return None

    # KURAL 2: Fiyat Bugün %2.5'ten Fazla Yükselmişse GİRME (Geç kalmış sinyal)
    if daily_change >= MAX_DAILY_CHANGE_PCT:
        return None

    # KURAL 3: RSI Filtresi (42 ile 64 arasında olmalı - Ne ölü ne aşırı şişmiş)
    if curr_rsi < 42 or curr_rsi > 64:
        return None

    # KURAL 4: Hacim Onayı (Ortalamanın en az 1.1 katı hacim girişi olmalı)
    if avg_vol > 0 and (curr_vol / avg_vol) < 1.1:
        return None

    # RISK VE HEDEF HESAPLAMA
    stop_price = curr_close - (1.5 * curr_atr)
    risk = curr_close - stop_price

    if risk <= 0: return None

    tp1 = curr_close + (risk * 1.5)
    tp2 = curr_close + (risk * 2.5)

    money_risk = PORTFOLIO_SIZE * RISK_PER_TRADE
    quantity = int(money_risk / risk)

    if quantity <= 0: return None
    if (quantity * curr_close) > (PORTFOLIO_SIZE * 0.20):
        quantity = int((PORTFOLIO_SIZE * 0.20) / curr_close)

    return {
        "entry": curr_close,
        "stop": stop_price,
        "tp1": tp1,
        "tp2": tp2,
        "quantity": quantity,
        "rsi": curr_rsi,
        "vol_ratio": (curr_vol / avg_vol) if avg_vol > 0 else 1.0,
        "daily_change": daily_change
    }


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
# TELEGRAM BİLDİRİMİ
# ============================================================

async def send_telegram_msg(app_bot: Application, text: str):
    if not CHAT_ID: return
    try:
        await app_bot.bot.send_message(chat_id=CHAT_ID, text=text)
    except Exception as exc:
        logger.error("Telegram mesaj hatası: %s", exc)


def format_signal_msg(ticker: str, sig):
    symbol = ticker.replace(".IS", "")
    return (
        "🟢🟢 **BUY (AL) SİNYALİ GELDİ** 🟢🟢\n\n"
        f"📌 **Hisse:** #{symbol}\n"
        f"📈 **Günün Primi:** %{sig['daily_change']:.2f} (DİPTE/BAŞLANGIÇTA)\n\n"
        f"💵 **Giriş Fiyatı:** {sig['entry']:.2f} TL\n"
        f"🛑 **Stop-Loss:** {sig['stop']:.2f} TL\n"
        f"🎯 **Hedef 1 (TP1):** {sig['tp1']:.2f} TL\n"
        f"🎯 **Hedef 2 (TP2):** {sig['tp2']:.2f} TL\n\n"
        f"📦 **Alınacak Adet:** {sig['quantity']} Lot\n"
        f"📊 **RSI:** {sig['rsi']:.1f}\n"
        f"🔊 **Hacim Girişi:** {sig['vol_ratio']:.1f}x Katı\n\n"
        "🚨 *Sinyal İndikatör Tarafından İLK MUMDA Yakalanmıştır.*"
    )


# ============================================================
# TARAMA MOTORU
# ============================================================

async def scan_market(application: Application):
    logger.info("Piyasa 'BUY' Sinyali İçin Taranıyor...")

    for ticker in TICKERS:
        try:
            if is_recently_signaled(ticker): continue

            # Günlük Veri İncelemesi
            df_daily = download_data(ticker, "1y", "1d")
            if df_daily.empty or len(df_daily) < 30: continue

            close_d = df_daily["close"]
            last_p = float(close_d.iloc[-1])
            prev_p = float(close_d.iloc[-2])
            daily_change = ((last_p - prev_p) / prev_p) * 100

            # Yükselmiş Hisseleri Direkt Ele
            if daily_change >= MAX_DAILY_CHANGE_PCT: continue

            # 15 Dakikalık Grafiğe İnim
            df_15m = download_data(ticker, "30d", "15m")
            if df_15m.empty: continue

            sig = analyze_buy_signal(df_15m, daily_change)

            if sig:
                save_signal(ticker, sig)
                msg = format_signal_msg(ticker, sig)
                await send_telegram_msg(application, msg)

        except Exception as exc:
            logger.warning("Tarama hatası %s: %s", ticker, exc)


# ============================================================
# BOT KOMUTLARI
# ============================================================

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 BUY/SELL İndikatör Botu Aktif.\n/scan - Manuel Tarama Başlat")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Taze 'BUY' sinyalleri taranıyor...")
    await scan_market(context.application)
    await update.message.reply_text("✅ Tarama bitti.")

async def scheduled_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        await scan_market(context.application)
    except Exception as exc:
        logger.exception("Zamanlanmış tarama hatası: %s", exc)

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    init_db()

    # Flask Sunucusu
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    # Telegram Bot
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
