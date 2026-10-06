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

# İşlem başına maksimum risk
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))

# Minimum sinyal skoru
MIN_SCORE = int(os.getenv("MIN_SCORE", "82"))

# Kaç dakikada bir taransın
SCAN_MINUTES = int(os.getenv("SCAN_MINUTES", "15"))

# Aynı hissede tekrar sinyal vermeden önce
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "6"))

# Günlük minimum işlem hacmi TL
MIN_DAILY_VALUE = float(os.getenv("MIN_DAILY_VALUE", "15000000"))

DB_FILE = "bist_bot.db"


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("BIST-BOT")


# ============================================================
# BIST HİSSE LİSTESİ (530+ HİSSE)
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
    "BRISA.IS", "BRKO.IS", "BRKSN.IS", "BRMEN.IS", "BRSAN.IS", "BRYAT.IS", "BSOKE.IS", "BTCIM.IS",
    "BUCIM.IS", "BURCE.IS", "BURVA.IS", "BVSAN.IS", "BYDNR.IS", "CANTE.IS", "CASA.IS", "CATES.IS",
    "CCOLA.IS", "CELHA.IS", "CEMAS.IS", "CEMTS.IS", "CMBTN.IS", "CMENT.IS", "CONSE.IS", "COSMO.IS",
    "CRDFA.IS", "CRFSA.IS", "CUSAN.IS", "CVKMD.IS", "CWENE.IS", "DAGI.IS", "DAGHL.IS", "DAPGM.IS",
    "DARDL.IS", "DGATE.IS", "DGGYO.IS", "DGNMO.IS", "DITAS.IS", "DMRGD.IS", "DMSAS.IS", "DNISI.IS",
    "DOAS.IS", "DOBUR.IS", "COEUR.IS", "DOGUB.IS", "DOHOL.IS", "DOKTA.IS", "DURDO.IS", "DURKN.IS",
    "DYOBY.IS", "DZGYO.IS", "EBEBK.IS", "ECILC.IS", "ECZYT.IS", "EDATA.IS", "EDIP.IS", "EGGUB.IS",
    "EGPRO.IS", "EGSER.IS", "EKGYO.IS", "EKIZ.IS", "EKSUN.IS", "ELITE.IS", "EMKEL.IS", "EMNIS.IS",
    "ENJSA.IS", "ENSRI.IS", "ENKAI.IS", "EPLAS.IS", "ERCB.IS", "EREGL.IS", "ERACB.IS", "ERSU.IS",
    "ESCAR.IS", "ESEN.IS", "ETILR.IS", "ETYAT.IS", "EUHOL.IS", "EUKYO.IS", "EUPWR.IS", "EUREK.IS",
    "EURO.IS", "EYGYO.IS", "FADE.IS", "FANSM.IS", "FLAP.IS", "FMIZP.IS", "FONET.IS", "FORMT.IS", "FORTE.IS",
    "FRIGO.IS", "FROTO.IS", "FZLGY.IS", "GARAN.IS", "GARFA.IS", "GEDIK.IS", "GEDZA.IS", "GOKNR.IS",
    "GOLTS.IS", "GOODY.IS", "GOZDE.IS", "GRNYO.IS", "GRAVI.IS", "GRSEL.IS", "GRTR.IS", "GSDHO.IS",
    "GSDEW.IS", "GUBRF.IS", "GWIND.IS", "GVT.IS", "GSDDE.IS", "GZNMI.IS", "HALKB.IS", "HATSN.IS",
    "HDFGS.IS", "HEDEF.IS", "HEKTS.IS", "HKTM.IS", "HLGYO.IS", "HUBVC.IS", "HUNER.IS", "HURGZ.IS",
    "ICBCT.IS", "IEYHO.IS", "IHAAS.IS", "IHEVA.IS", "IHGZT.IS", "IHYAY.IS", "IMASM.IS", "INDES.IS",
    "INFO.IS", "INGRM.IS", "INVES.IS", "IPEKE.IS", "ISATR.IS", "ISBTR.IS", "ISCTR.IS", "ISDMR.IS",
    "ISFIN.IS", "ISGSY.IS", "ISGYO.IS", "ISKPL.IS", "ISMEN.IS", "ISSEN.IS", "IZINV.IS", "IZMDC.IS",
    "JANTS.IS", "KAPLM.IS", "KFEIN.IS", "KARYA.IS", "KATMR.IS", "KAYSE.IS", "KCAER.IS", "KCHOL.IS",
    "KENT.IS", "KRTEK.IS", "KGYO.IS", "KIMMR.IS", "KLGYO.IS", "KLMSN.IS", "KLSER.IS", "KLRHO.IS",
    "KMPUR.IS", "KNFRT.IS", "KONTR.IS", "KONYA.IS", "KORDS.IS", "KOZAL.IS", "KOZAA.IS", "KRDMD.IS",
    "KRDMA.IS", "KRDMB.IS", "KRGYO.IS", "KRPLS.IS", "KRSTL.IS", "KRONT.IS", "KTLEV.IS", "KTSKR.IS",
    "KUTPO.IS", "KUYAS.IS", "KZBGY.IS", "LIDER.IS", "LKMNH.IS", "LINK.IS", "LMKDC.IS", "LOGO.IS",
    "LRSHA.IS", "LUKSK.IS", "MAALT.IS", "MACKO.IS", "MAKIM.IS", "MAKTK.IS", "MANAS.IS", "MARKA.IS",
    "MAVI.IS", "MEDTR.IS", "MEGAP.IS", "MEGMT.IS", "MEPET.IS", "MERCN.IS", "MERIT.IS", "MERKO.IS",
    "METRO.IS", "METUR.IS", "MHRGY.IS", "MIATK.IS", "MIPAZ.IS", "MMCAS.IS", "MNDRS.IS", "MNDTR.IS",
    "MOBTL.IS", "MOGAN.IS", "MPARK.IS", "MRGYO.IS", "MRSHL.IS", "MSGYO.IS", "MTRKS.IS", "MTURG.IS",
    "MZHLD.IS", "NATEN.IS", "NETAS.IS", "NIBAS.IS", "NTGAZ.IS", "NTHOL.IS", "NUGYO.IS", "NUHCM.IS",
    "OBAMS.IS", "OBASE.IS", "ODAS.IS", "OFSYM.IS", "ONCSM.IS", "ORCA.IS", "ORGE.IS", "ORMA.IS",
    "OSMEN.IS", "OSTIM.IS", "OTKAR.IS", "OTTO.IS", "OYAKC.IS", "OYYAT.IS", "OYLUM.IS", "OZATD.IS",
    "OZKGY.IS", "OZRDN.IS", "OZSUB.IS", "PAGYO.IS", "PAMEL.IS", "PAPIL.IS", "PARSN.IS", "PASEU.IS",
    "PATEK.IS", "PCILT.IS", "PEGAS.IS", "PEKGY.IS", "PENGD.IS", "PETKM.IS", "PETUN.IS", "PGSUS.IS",
    "PINSU.IS", "PKART.IS", "PKENT.IS", "PLTUR.IS", "PNLSN.IS", "PNSUT.IS", "POLHO.IS", "POLTK.IS",
    "PRDGS.IS", "PRKME.IS", "PRKAB.IS", "PRZMA.IS", "PSDTC.IS", "PSGYO.IS", "QUAGR.IS", "RALYH.IS",
    "RAYSG.IS", "REEDR.IS", "RGYAS.IS", "RHGHO.IS", "RIAS.IS", "RNPOL.IS", "RODRG.IS", "ROYAL.IS",
    "RTALB.IS", "RUBNS.IS", "RYGYO.IS", "RYSAS.IS", "SAFKR.IS", "SAHOL.IS", "SAMAT.IS", "SANEL.IS",
    "SANFM.IS", "SANKO.IS", "SARKY.IS", "SASA.IS", "SAYAS.IS", "SDTTR.IS", "SELEC.IS", "SELVA.IS",
    "SEYKM.IS", "SILVR.IS", "SISE.IS", "SKBNK.IS", "SKYMD.IS", "SMART.IS", "SMRTG.IS", "SMARTG.IS",
    "SNAI.IS", "SNICA.IS", "SNKRN.IS", "SOKE.IS", "SONME.IS", "SRVGY.IS", "SUMAS.IS", "SUWEN.IS",
    "SUNTK.IS", "SURGY.IS", "TABGD.IS", "TAKEY.IS", "TARKM.IS", "TATEN.IS", "TATGD.IS", "TAVHL.IS",
    "TCBKN.IS", "TCELL.IS", "TCKRC.IS", "TDGYO.IS", "TEKTU.IS", "TERA.IS", "TFX.IS", "THYAO.IS",
    "TIRE.IS", "TKFEN.IS", "TKNSA.IS", "TLMAN.IS", "TMPOL.IS", "TMSN.IS", "TNZTP.IS", "TOASO.IS",
    "TRGYO.IS", "TLRHO.IS", "TRCAS.IS", "TRILC.IS", "TSKB.IS", "TSPOR.IS", "TTKOM.IS", "TTRAK.IS",
    "TUCLK.IS", "TUPRS.IS", "TURGG.IS", "TURSG.IS", "UFUK.IS", "ULAS.IS", "ULKER.IS", "UNLU.IS",
    "USAK.IS", "VAKBN.IS", "VAKFN.IS", "VAKKO.IS", "VANGD.IS", "VBTYZ.IS", "VERTU.IS", "VERUS.IS",
    "VESBE.IS", "VESTL.IS", "VKFYO.IS", "VKGYO.IS", "VKING.IS", "VRGYO.IS", "YAPRK.IS", "YATAS.IS",
    "YAYLA.IS", "YGGYO.IS", "YEOTK.IS", "YGYO.IS", "YKBNK.IS", "YLIMF.IS", "YONGA.IS", "YUNSA.IS",
    "YYLGD.IS", "ZOREN.IS", "ZRGYO.IS"
]


# ============================================================
# FLASK - RENDER KEEP ALIVE
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return "BIST Quant Bot ACTIVE"


@app.route("/health")
def health():
    return "OK"


def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(
        host="0.0.0.0",
        port=port,
    )


# ============================================================
# DATABASE
# ============================================================

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
                score INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                status TEXT DEFAULT 'OPEN',
                exit_price REAL,
                result REAL,
                closed_at TEXT
            )
            """
        )

        conn.commit()
        conn.close()


# ============================================================
# YFINANCE YARDIMCI FONKSİYONLARI
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


def download_one(ticker: str, period: str, interval: str) -> pd.DataFrame:
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
        logger.warning("Veri alınamadı %s: %s", ticker, exc)
        return pd.DataFrame()


# ============================================================
# TEKNİK İNDİKATÖRLER
# ============================================================

def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    return 100 - (100 / (1 + rs))


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]

    previous_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - previous_close).abs()
    tr3 = (low - previous_close).abs()

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    return true_range.ewm(alpha=1 / period, adjust=False).mean()


def macd(series: pd.Series):
    fast = ema(series, 12)
    slow = ema(series, 26)

    macd_line = fast - slow
    signal = ema(macd_line, 9)
    histogram = macd_line - signal

    return macd_line, signal, histogram


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0),
        index=df.index,
    )

    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0),
        index=df.index,
    )

    atr_value = atr(df, period)

    plus_di = 100 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_value
    minus_di = 100 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_value

    denominator = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denominator

    return dx.ewm(alpha=1 / period, adjust=False).mean()


# ============================================================
# MARKET REGIME
# ============================================================

def get_market_regime():
    df = download_one("XU100.IS", "1y", "1d")

    if df.empty or len(df) < 220:
        return {"regime": "NEUTRAL", "score": 7}

    close = df["close"]

    ema20 = ema(close, 20)
    ema50 = ema(close, 50)
    ema200 = ema(close, 200)

    last = float(close.iloc[-1])

    e20 = float(ema20.iloc[-1])
    e50 = float(ema50.iloc[-1])
    e200 = float(ema200.iloc[-1])

    if last > e20 and e20 > e50 and e50 > e200:
        return {"regime": "RISK_ON", "score": 15}

    if last < e50 and e50 < e200:
        return {"regime": "RISK_OFF", "score": 0}

    return {"regime": "NEUTRAL", "score": 7}


# ============================================================
# GÜNLÜK TREND
# ============================================================

def daily_analysis(df: pd.DataFrame):
    if df.empty or len(df) < 220:
        return None

    close = df["close"]

    e20 = ema(close, 20)
    e50 = ema(close, 50)
    e200 = ema(close, 200)

    last = float(close.iloc[-1])

    score = 0

    if last > float(e20.iloc[-1]):
        score += 5

    if last > float(e50.iloc[-1]):
        score += 7

    if float(e50.iloc[-1]) > float(e200.iloc[-1]):
        score += 8

    trend = last > float(e50.iloc[-1]) and float(e50.iloc[-1]) > float(e200.iloc[-1])

    return {"score": score, "trend": trend, "close": last}


# ============================================================
# LIQUIDITY
# ============================================================

def liquidity_analysis(df: pd.DataFrame):
    if df.empty or len(df) < 30:
        return None

    value = df["close"] * df["volume"]
    median_value = float(value.tail(20).median())

    return {
        "value": median_value,
        "liquid": (median_value >= MIN_DAILY_VALUE),
    }


# ============================================================
# RELATIVE STRENGTH
# ============================================================

def relative_strength(stock_df: pd.DataFrame, market_df: pd.DataFrame):
    if stock_df.empty or market_df.empty:
        return 0

    if len(stock_df) < 60 or len(market_df) < 60:
        return 0

    stock_now = float(stock_df["close"].iloc[-1])
    stock_old = float(stock_df["close"].iloc[-21])

    market_now = float(market_df["close"].iloc[-1])
    market_old = float(market_df["close"].iloc[-21])

    stock_return = (stock_now / stock_old) - 1
    market_return = (market_now / market_old) - 1

    alpha = stock_return - market_return

    if alpha > 0.08:
        return 15
    if alpha > 0.04:
        return 10
    if alpha > 0:
        return 5

    return 0


# ============================================================
# 15 DAKİKALIK SİNYAL
# ============================================================

def analyze_intraday(
    df: pd.DataFrame,
    daily_info,
    market_score: int,
    relative_score: int,
):
    if df.empty or len(df) < 100:
        return None

    # Son bar tamamlanmamış olabileceği için hariç tutuyoruz
    df = df.iloc[:-1].copy()

    if len(df) < 80:
        return None

    close = df["close"]

    e8 = ema(close, 8)
    e20 = ema(close, 20)
    e50 = ema(close, 50)

    rsi_value = rsi(close, 14)
    atr_value = atr(df, 14)
    adx_value = adx(df, 14)

    macd_line, macd_signal, _ = macd(close)
    volume_average = df["volume"].rolling(20).median()

    last = float(close.iloc[-1])

    current_e8 = float(e8.iloc[-1])
    current_e20 = float(e20.iloc[-1])
    current_e50 = float(e50.iloc[-1])

    current_rsi = float(rsi_value.iloc[-1])
    current_atr = float(atr_value.iloc[-1])
    current_adx = float(adx_value.iloc[-1])

    current_macd = float(macd_line.iloc[-1])
    current_signal = float(macd_signal.iloc[-1])
    previous_macd = float(macd_line.iloc[-2])
    previous_signal = float(macd_signal.iloc[-2])

    current_volume = float(df["volume"].iloc[-1])
    avg_volume = float(volume_average.iloc[-1])

    if avg_volume <= 0:
        return None

    volume_ratio = current_volume / avg_volume

    score = 0
    reasons = []

    # Market Rejimi
    score += market_score
    if market_score >= 15:
        reasons.append("BIST ana trendi pozitif")
    elif market_score >= 7:
        reasons.append("BIST nötr/pozitif")
    else:
        return None

    # Daily Trend
    if daily_info["trend"]:
        score += 20
        reasons.append("Günlük trend yukarı")
    else:
        return None

    # 15M Trend
    if last > current_e8 > current_e20 > current_e50:
        score += 15
        reasons.append("15D trend güçlü")
    elif last > current_e20 and current_e20 > current_e50:
        score += 10
        reasons.append("15D trend pozitif")
    else:
        return None

    # Relative Strength
    score += relative_score
    if relative_score >= 10:
        reasons.append("XU100'e göre güçlü")
    elif relative_score >= 5:
        reasons.append("XU100'e göre pozitif")

    # Breakout
    previous_high = float(df["high"].iloc[-21:-1].max())
    breakout = last > previous_high

    if breakout:
        score += 20
        reasons.append("20 mumluk direnç kırıldı")

    # Hacim
    if volume_ratio >= 2.0:
        score += 10
        reasons.append(f"Hacim {volume_ratio:.1f}x")
    elif volume_ratio >= 1.4:
        score += 7
        reasons.append(f"Hacim {volume_ratio:.1f}x")
    elif volume_ratio >= 1.15:
        score += 3

    # MACD
    fresh_cross = previous_macd <= previous_signal and current_macd > current_signal
    if fresh_cross:
        score += 8
        reasons.append("MACD bullish kesişim")
    elif current_macd > current_signal:
        score += 4

    # RSI
    if 52 <= current_rsi <= 68:
        score += 7
        reasons.append(f"RSI {current_rsi:.1f}")
    elif 68 < current_rsi <= 74:
        score += 2
    elif current_rsi > 78:
        return None

    # ADX
    if current_adx >= 25:
        score += 5
        reasons.append(f"ADX güçlü {current_adx:.1f}")
    elif current_adx >= 18:
        score += 3

    # EMA Uzaklık Kontrolü
    distance_atr = (last - current_e20) / current_atr
    if distance_atr > 2.2:
        return None

    # Kurulum Güvenilirliği
    if not breakout:
        strong_setup = (
            current_macd > current_signal
            and volume_ratio >= 1.4
            and current_adx >= 20
        )
        if not strong_setup:
            return None

    # Stop & TP Hesabı
    recent_low = float(df["low"].tail(12).min())
    stop_atr = last - 1.5 * current_atr
    stop = min(recent_low, stop_atr)

    risk_distance = last - stop
    if risk_distance <= 0:
        return None

    risk_percent = (risk_distance / last) * 100
    if risk_percent > 6:
        return None

    tp1 = last + risk_distance * 1.8
    tp2 = last + risk_distance * 3.0

    if score < MIN_SCORE:
        return None

    money_risk = PORTFOLIO_SIZE * RISK_PER_TRADE
    quantity = int(money_risk / risk_distance)

    if quantity <= 0:
        return None

    position_value = quantity * last
    if position_value > (PORTFOLIO_SIZE * 0.20):
        quantity = int((PORTFOLIO_SIZE * 0.20) / last)

    return {
        "score": score,
        "entry": last,
        "stop": stop,
        "tp1": tp1,
        "tp2": tp2,
        "quantity": quantity,
        "risk_percent": risk_percent,
        "reasons": reasons,
        "volume_ratio": volume_ratio,
        "rsi": current_rsi,
        "adx": current_adx,
    }


# ============================================================
# COOLDOWN & DATABASE KAYIT
# ============================================================

def recently_signaled(ticker: str) -> bool:
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        row = conn.execute(
            """
            SELECT created_at FROM trades
            WHERE ticker = ? ORDER BY id DESC LIMIT 1
            """,
            (ticker,),
        ).fetchone()
        conn.close()

    if not row:
        return False

    try:
        created = datetime.fromisoformat(row[0])
        now = datetime.now(timezone.utc)
        hours = (now - created).total_seconds() / 3600
        return hours < COOLDOWN_HOURS
    except Exception:
        return False


def save_trade(ticker: str, signal):
    created = datetime.now(timezone.utc).isoformat()
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            """
            INSERT INTO trades (
                ticker, entry, stop, tp1, tp2, quantity, score, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                signal["entry"],
                signal["stop"],
                signal["tp1"],
                signal["tp2"],
                signal["quantity"],
                signal["score"],
                created,
            ),
        )
        conn.commit()
        conn.close()


# ============================================================
# TELEGRAM BİLDİRİMLERİ
# ============================================================

async def send_message(application: Application, message: str):
    if not CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID ayarlı değil.")
        return

    try:
        await application.bot.send_message(
            chat_id=CHAT_ID,
            text=message,
        )
    except Exception as exc:
        logger.error("Telegram gönderim hatası: %s", exc)


def create_signal_message(ticker: str, signal, regime: str):
    symbol = ticker.replace(".IS", "")
    reasons = "\n".join(f"• {reason}" for reason in signal["reasons"])

    return (
        "🚨 BIST GÜÇLÜ AL SİNYALİ\n\n"
        f"📌 Hisse: {symbol}\n"
        f"⭐ Skor: {signal['score']}/100\n"
        f"🌐 Piyasa: {regime}\n\n"
        f"💰 Giriş: {signal['entry']:.2f}\n"
        f"🛑 Stop: {signal['stop']:.2f}\n"
        f"🎯 TP1: {signal['tp1']:.2f}\n"
        f"🎯 TP2: {signal['tp2']:.2f}\n\n"
        f"📊 Risk: %{signal['risk_percent']:.2f}\n"
        f"📦 Adet: {signal['quantity']}\n"
        f"📈 RSI: {signal['rsi']:.1f}\n"
        f"💪 ADX: {signal['adx']:.1f}\n"
        f"🔊 Hacim: {signal['volume_ratio']:.1f}x\n\n"
        "NEDEN?\n"
        f"{reasons}\n\n"
        "⚠️ Bu bir otomatik araştırma/sinyal sistemidir; garanti kâr değildir."
    )


# ============================================================
# ANA TARAMA
# ============================================================

async def run_scan(application: Application):
    logger.info("BIST taraması başladı...")
    market = get_market_regime()

    logger.info("Piyasa rejimi: %s", market["regime"])
    if market["regime"] == "RISK_OFF":
        logger.info("Piyasa risk-off. BUY sinyali yok.")
        return

    market_df = download_one("XU100.IS", "1y", "1d")
    candidates = []

    # 1. AŞAMA: Günlük Tarama
    for ticker in TICKERS:
        try:
            if recently_signaled(ticker):
                continue

            daily = download_one(ticker, "1y", "1d")
            if daily.empty:
                continue

            liquidity = liquidity_analysis(daily)
            if not liquidity or not liquidity["liquid"]:
                continue

            daily_info = daily_analysis(daily)
            if not daily_info or not daily_info["trend"]:
                continue

            relative_score = relative_strength(daily, market_df)

            if daily_info["score"] + relative_score < 20:
                continue

            candidates.append((ticker, daily, daily_info, relative_score))

        except Exception as exc:
            logger.warning("Günlük analiz hatası %s: %s", ticker, exc)

    logger.info("Günlük filtreden geçen: %d", len(candidates))

    # 2. AŞAMA: 15 Dakikalık Tarama
    candidates = sorted(
        candidates, key=lambda x: (x[2]["score"] + x[3]), reverse=True
    )[:120]

    signals = []

    for ticker, daily, daily_info, relative_score in candidates:
        try:
            intraday = download_one(ticker, "60d", "15m")
            if intraday.empty:
                continue

            signal = analyze_intraday(
                intraday, daily_info, market["score"], relative_score
            )
            if signal is None:
                continue

            signals.append((ticker, signal))

        except Exception as exc:
            logger.warning("15m analiz hatası %s: %s", ticker, exc)

    signals.sort(key=lambda x: x[1]["score"], reverse=True)
    signals = signals[:3]

    logger.info("Bulunan güçlü sinyal: %d", len(signals))

    for ticker, signal in signals:
        save_trade(ticker, signal)
        message = create_signal_message(ticker, signal, market["regime"])
        await send_message(application, message)


# ============================================================
# OPEN TRADE GÜNCELLE
# ============================================================

def get_open_trades():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            """
            SELECT id, ticker, entry, stop, tp1, tp2, quantity
            FROM trades WHERE status = 'OPEN'
            """
        ).fetchall()
        conn.close()

    return rows


def close_trade(trade_id: int, exit_price: float, result: float):
    closed = datetime.now(timezone.utc).isoformat()
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            """
            UPDATE trades
            SET status = 'CLOSED', exit_price = ?, result = ?, closed_at = ?
            WHERE id = ?
            """,
            (exit_price, result, closed, trade_id),
        )
        conn.commit()
        conn.close()


async def update_open_trades(application: Application):
    trades = get_open_trades()
    if not trades:
        return

    for trade in trades:
        trade_id, ticker, entry, stop, tp1, tp2, quantity = trade
        try:
            df = download_one(ticker, "5d", "15m")
            if df.empty:
                continue

            candle = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]
            high, low = float(candle["high"]), float(candle["low"])

            if low <= stop:
                result = (stop - entry) * quantity
                close_trade(trade_id, stop, result)
                symbol = ticker.replace(".IS", "")
                await send_message(
                    application,
                    f"🛑 STOP\n\n{symbol}\nÇıkış: {stop:.2f}\nSonuç: {result:.2f} TL",
                )
            elif high >= tp2:
                result = (tp2 - entry) * quantity
                close_trade(trade_id, tp2, result)
                symbol = ticker.replace(".IS", "")
                await send_message(
                    application,
                    f"🏆 TP2\n\n{symbol}\nÇıkış: {tp2:.2f}\nSonuç: +{result:.2f} TL",
                )

        except Exception as exc:
            logger.warning("Trade güncelleme hatası %s: %s", ticker, exc)


# ============================================================
# PERFORMANS VE KOMUTLAR
# ============================================================

def performance_text():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        rows = conn.execute(
            """
            SELECT result FROM trades
            WHERE status = 'CLOSED' AND result IS NOT NULL
            """
        ).fetchall()
        conn.close()

    if not rows:
        return "📊 Henüz kapanmış işlem yok."

    results = [float(row[0]) for row in rows]
    total = len(results)
    wins = [x for x in results if x > 0]
    losses = [x for x in results if x <= 0]

    win_rate = (len(wins) / total) * 100
    total_profit = sum(results)
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))

    profit_factor = (
        gross_profit / gross_loss if gross_loss > 0 else float("inf")
    )

    return (
        "📊 BIST BOT PERFORMANS\n\n"
        f"İşlem: {total}\n"
        f"Kazanma: %{win_rate:.1f}\n"
        f"Toplam: {total_profit:.2f} TL\n"
        f"Profit Factor: {profit_factor:.2f}\n"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 BIST Quant Bot aktif.\n\n"
        "/scan - Manuel tarama\n"
        "/status - Sistem durumu\n"
        "/performance - Performans"
    )


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 BIST taraması başlıyor...")
    await run_scan(context.application)
    await update.message.reply_text("✅ Tarama tamamlandı.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    market = get_market_regime()
    open_trades = get_open_trades()

    await update.message.reply_text(
        "🤖 BIST QUANT BOT\n\n"
        f"🌐 Piyasa: {market['regime']}\n"
        f"📊 Hisse evreni: {len(TICKERS)}\n"
        f"📂 Açık işlemler: {len(open_trades)}\n"
        f"🎯 Minimum skor: {MIN_SCORE}\n"
        f"⏱ Tarama: {SCAN_MINUTES} dk"
    )


async def performance_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(performance_text())


async def scheduled_scan(context: ContextTypes.DEFAULT_TYPE):
    try:
        await update_open_trades(context.application)
        await run_scan(context.application)
    except Exception as exc:
        logger.exception("Otomatik tarama hatası: %s", exc)


# ============================================================
# MAIN
# ============================================================

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN bulunamadı.")

    init_db()

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("performance", performance_command))

    if application.job_queue is not None:
        application.job_queue.run_repeating(
            scheduled_scan,
            interval=SCAN_MINUTES * 60,
            first=30,
        )
        logger.info("Otomatik tarama aktif: %d dakika", SCAN_MINUTES)
    else:
        logger.error(
            "JobQueue aktif değil. requirements.txt içinde python-telegram-bot[job-queue] olmalı."
        )

    logger.info("BIST Quant Bot başlatılıyor...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
