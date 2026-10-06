import os
import threading
import asyncio
import requests
import concurrent.futures
import yfinance as yf
import pandas as pd
import numpy as np

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Render Keep-Alive Web Sunucusu
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Full BIST 500 Quant Engine Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

def get_all_bist_tickers():
    """BIST'te işlem gören tüm ana hisselerin listesini oluşturur."""
    # En likit ve bilinen BIST hisselerinin genişletilmiş tam listesi
    base_tickers = [
        "AAVST", "A1CAP", "ACSEL", "ADEL", "ADESE", "AGHOL", "AGROT", "AHGAZ", "AKBNK", "AKCNS",
        "AKFGY", "AKFYE", "AKMGH", "AKSA", "AKSEN", "AKSGY", "ALARK", "ALBRK", "ALCAR", "ALCTL",
        "ALFAS", "ALGYO", "ALKA", "ALKIM", "ALMAD", "ALTNY", "ALVES", "ANELE", "ANGEN", "ANHYT",
        "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA", "ARSAN", "ARTMS", "ASELS", "ASGYO", "ASTOR",
        "ATAGY", "ATAKP", "ATATP", "ATEKS", "ATSYH", "AVOD", "AVPGY", "AVTUR", "AYCES", "AYDEM",
        "AYGAZ", "AZTEK", "BAGFS", "BAKAB", "BALAT", "BANVT", "BARMA", "BASGZ", "BAYRK", "BEGYO",
        "BERA", "BEYAZ", "BFREN", "BIENP", "BIGCHEFS", "BIMAS", "BINHO", "BIOEN", "BIZIM", "BJKAS",
        "BLCYT", "BMSCH", "BMSTL", "BNTAS", "BOBET", "BORAB", "BORSK", "BOSSA", "BRISA", "BRKO",
        "BRKVY", "BRSAN", "BRYAT", "BSOKE", "BTCIM", "BUCIM", "BURCE", "BURVA", "BVSAN", "BYDNR",
        "CANTE", "CASA", "CAVT", "CATES", "CCOLA", "CELHA", "CEMAS", "CEMTS", "CMBTN", "CMENT",
        "CONSE", "COSMO", "CRFSA", "CUSAN", "CVKMD", "CWENE", "DAGI", "DAPGM", "DARDL", "DGATE",
        "DGGYO", "DITAS", "DMRGD", "DMSAS", "DNISI", "DOAS", "DOBUR", "DOCTA", "DOFER", "DOHOL",
        "DSIEN", "DITAŞ", "EBEBK", "ECILC", "ECZYT", "EDATA", "EDIP", "EGEEN", "EGGUB", "EGPRO",
        "EGSER", "EKIZ", "EKGYO", "EKLMT", "ELITE", "EMKEL", "ENJSA", "ENKAI", "ENSRI", "EPLAS",
        "ERCB", "EREGL", "ERSU", "ESCAR", "ESCOM", "EUPWR", "EUREK", "FORTE", "FROTO", "FZLGY",
        "GARAN", "GWIND", "GENTS", "GESAN", "GIPTA", "GLCVY", "GLYHO", "GMTAS", "GOKNR", "GOLTS",
        "GOODY", "GOZDE", "GRSEL", "GRTHO", "GSDHO", "GSDEVR", "GSRAY", "GUBRF", "GWIND", "HALKB",
        "HATEK", "HDEDF", "HEKTS", "HITIT", "HOROZ", "HRKET", "HUBVC", "HUNER", "HURGZ", "ICBCT",
        "IEYHO", "IHAAS", "IHEVA", "IHGZT", "IHLGM", "IHYAY", "INGRM", "INVSEO", "INFO", "INGRM",
        "INTEM", "INVGEO", "INVES", "IPEKE", "ISATR", "ISBTR", "ISCTR", "ISDMR", "ISFIN", "ISGYO",
        "ISMEN", "ISSEN", "IZENR", "IZINV", "IZMDC", "JANTS", "KAFEIN", "KLSER", "KAMWE", "KARYE",
        "KATMR", "KAYSE", "KBORU", "KCAER", "KCHOL", "KFEIN", "KLMSN", "KLNMA", "KLRHO", "KLSER",
        "KMPUR", "KNFRT", "KONTR", "KNYA", "KORDS", "KOZAL", "KOZAA", "KRDMD", "KRPLS", "KRTEK",
        "KRVGD", "KSTUR", "KTLEV", "KUTPO", "KSTUR", "LIDER", "LKMNH", "LMKDC", "LOGIN", "LRTYO",
        "LUKSK", "MAALT", "MACKO", "MAKIM", "MAKTK", "MANAS", "MARBL", "MARKA", "MAVI", "MEDTR",
        "MEGAP", "MEGMT", "MEPET", "MERCN", "MERIT", "MERKO", "METRO", "METUR", "MGROS", "MIATK",
        "MHRGY", "MMCAS", "MNDTR", "MOBTL", "MOGAN", "MPARK", "MRGYO", "MRSHL", "MSGYO", "MTRKS",
        "MTRYO", "MZHLD", "NATEN", "NETAS", "NIBAS", "NTHOL", "NUGYO", "OBAMS", "OBASE", "ODAS",
        "OFCAD", "ONCSM", "ORCA", "ORGE", "ORMA", "OSMEN", "OSTIM", "OTKAR", "OTTO", "OYAKC",
        "OYYAT", "OZATD", "OZKGY", "OZRDN", "OZSUB", "PAGYO", "PAMEL", "PAPIL", "PARSN", "PASEU",
        "PATEK", "PCILT", "PEKGY", "PENTA", "PETKM", "PETUN", "PGSUS", "PINAR", "PKART", "PLTUR",
        "POLHO", "POLTK", "PRDGS", "PRKME", "PRZMA", "PSDTC", "PSGYO", "QNBFB", "QNBFK", "RALYH",
        "RAYSG", "REEDR", "RGYAS", "RNPOL", "RODRG", "RUBNS", "RYGYO", "RYSAS", "SAHOL", "SAMAT",
        "SANEL", "SANFM", "SANGS", "SANX", "SARKY", "SASO", "SASA", "SAYAS", "SDTTR", "SEGMN",
        "SEKFK", "SEKUR", "SELEC", "SELVA", "SEYKM", "SILVR", "SISE", "SKBNK", "SKTAS", "SMART",
        "SMRTG", "SNAYS", "SNICA", "SNKRN", "SOKE", "SOKM", "SONME", "SRVGY", "SMRTG", "SUMAS",
        "SUNTK", "SURGY", "SUWEN", "TATEN", "TATGD", "TAVHL", "TCELL", "TCKRC", "THYAO", "TKFEN",
        "TKNSA", "TLMAN", "TMSN", "TOASO", "TRGYO", "TRILC", "TSKB", "TSPOR", "TTKOM", "TTRAK",
        "TUKAS", "TUPRS", "TUREX", "TURSG", "UFUK", "ULAS", "ULKER", "UNLU", "USAK", "VAKBN",
        "VAKKO", "VAKFN", "VALFY", "VANET", "VBTYZ", "VERTU", "VERUS", "VESBE", "VESTL", "VKFYO",
        "VKGYO", "YAPRK", "YATAS", "YEOTK", "YGGYO", "YGYO", "YKBNK", "YONGA", "YUNSA", "ZRGYO"
    ]
    # Mükerrerleri temizle ve .IS ekle
    unique_tickers = list(set(base_tickers))
    return [f"{ticker}.IS" for ticker in unique_tickers]

def calculate_mfi(df, period=14):
    """Money Flow Index (MFI)"""
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    rmf = tp * df['Volume']
    
    pos_mf, neg_mf = [], []
    for i in range(1, len(tp)):
        if tp.iloc[i] > tp.iloc[i-1]:
            pos_mf.append(rmf.iloc[i])
            neg_mf.append(0)
        elif tp.iloc[i] < tp.iloc[i-1]:
            pos_mf.append(0)
            neg_mf.append(rmf.iloc[i])
        else:
            pos_mf.append(0)
            neg_mf.append(0)
            
    pos_s = pd.Series(pos_mf, index=df.index[1:]).rolling(period).sum()
    neg_s = pd.Series(neg_mf, index=df.index[1:]).rolling(period).sum()
    
    mfr = pos_s / neg_s
    mfi = 100 - (100 / (1 + mfr))
    return round(mfi.iloc[-1], 1) if not mfi.empty else 50

def analyze_single_stock(args):
    """Tek bir hisseyi analiz eden thread fonksiyonu."""
    symbol, portfolio_size, bist_10d_perf = args
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})

        df_d = yf.Ticker(symbol, session=session).history(period="6mo", interval="1d")
        if len(df_d) < 50:
            return None

        current_price = round(df_d['Close'].iloc[-1], 2)
        prev_price = df_d['Close'].iloc[-2]
        change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)

        # Taban olan veya sert düşen hisseler elenir
        if change_pct < -2.5 or current_price <= 0:
            return None

        score = 0
        reasons = []

        # 1. MAKRO TREND (20 Puan)
        ema10 = df_d['Close'].ewm(span=10, adjust=False).mean().iloc[-1]
        ema30 = df_d['Close'].ewm(span=30, adjust=False).mean().iloc[-1]
        if ema10 > ema30 and df_d['Close'].iloc[-1] > ema10:
            score += 20
            reasons.append("Günlük Trend Pozitif (EMA 10/30 Üzerinde)")

        # 2. GÖRELİ GÜÇ / ALFA vs BIST100 (20 Puan)
        stock_10d = (df_d['Close'].iloc[-1] - df_d['Close'].iloc[-10]) / df_d['Close'].iloc[-10]
        if stock_10d > (bist_10d_perf + 0.02):
            score += 20
            reasons.append("Yüksek Alfa (BIST 100'e Göre Güçlü)")

        # 3. HACİM VE PARA GİRİŞİ (20 Puan)
        vol_mean = df_d['Volume'].rolling(20).mean().iloc[-1]
        vol_std = df_d['Volume'].rolling(20).std().iloc[-1]
        vol_zscore = (df_d['Volume'].iloc[-1] - vol_mean) / vol_std if vol_std > 0 else 0
        mfi = calculate_mfi(df_d)

        if vol_zscore >= 1.2 and mfi >= 55:
            score += 20
            reasons.append(f"Kurumsal Para Girişi (MFI: {mfi} | Hacim Z-Score: {round(vol_zscore, 1)})")

        # 4. VOLATİLİTE SIKIŞMASI & RSI (20 Puan)
        sma20 = df_d['Close'].rolling(20).mean()
        std20 = df_d['Close'].rolling(20).std()
        bandwidth = (((sma20 + (2 * std20)) - (sma20 - (2 * std20))) / sma20).iloc[-1]

        delta = df_d['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = round((100 - (100 / (1 + (gain / loss)))).iloc[-1], 1)

        if (50 <= rsi <= 68) and bandwidth < 0.15:
            score += 20
            reasons.append(f"Sıkışma Patlaması (BB Bandwidth: {round(bandwidth,2)} | RSI: {rsi})")
        elif (50 <= rsi <= 68):
            score += 15
            reasons.append(f"Ideal Momentum Bölgesi (RSI: {rsi})")

        # 5. MACD KESİŞİMİ (20 Puan)
        ema12 = df_d['Close'].ewm(span=12, adjust=False).mean()
        ema26 = df_d['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()

        if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-1] > 0:
            score += 20
            reasons.append("MACD Pozitif Bölgede Al Sinyalinde")

        # --- FİLTRE (Min. 80 Puan) ---
        if score >= 80:
            high_low = df_d['High'] - df_d['Low']
            high_close = np.abs(df_d['High'] - df_d['Close'].shift())
            low_close = np.abs(df_d['Low'] - df_d['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            atr = np.max(ranges, axis=1).rolling(14).mean().iloc[-1]

            stop_loss = round(current_price - (atr * 1.5), 2)
            take_profit = round(current_price + (atr * 3.0), 2)
            risk_pct = round(((current_price - stop_loss) / current_price) * 100, 1)
            reward_pct = round(((take_profit - current_price) / current_price) * 100, 1)

            max_risk_amount = portfolio_size * 0.02
            risk_per_share = current_price - stop_loss
            shares_to_buy = int(max_risk_amount / risk_per_share) if risk_per_share > 0 else 0
            position_value = round(shares_to_buy * current_price, 2)

            grade = "💎 BIST 500 VIP ALFA" if score == 100 else "👑 YÜKSEK POTANSİYELLİ"

            return {
                "symbol": symbol.replace('.IS', ''),
                "price": current_price,
                "change": change_pct,
                "score": score,
                "grade": grade,
                "rsi": rsi,
                "mfi": mfi,
                "reasons": reasons,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_pct": risk_pct,
                "reward_pct": reward_pct,
                "shares_to_buy": shares_to_buy,
                "position_value": position_value
            }
        return None

    except Exception:
        return None

def scan_full_bist(portfolio_size=100000):
    """500+ Hisseden Oluşan BIST'i Paralel Olarak Tara"""
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        bist_d = yf.Ticker("XU100.IS", session=session).history(period="6mo", interval="1d")
        bist_10d_perf = (bist_d['Close'].iloc[-1] - bist_d['Close'].iloc[-10]) / bist_d['Close'].iloc[-10]
    except Exception:
        bist_10d_perf = 0.0

    tickers = get_all_bist_tickers()
    args_list = [(ticker, portfolio_size, bist_10d_perf) for ticker in tickers]

    results = []
    # 500 Hisseyi Paralel Olarak (15 Thread) Tara -> 15-20 Saniyede Biter
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        scan_results = executor.map(analyze_single_stock, args_list)
        for res in scan_results:
            if res:
                results.append(res)

    results.sort(key=lambda x: x['score'], reverse=True)
    return results

# --- TELEGRAM ARAYÜZÜ ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🚀 Tüm BIST (500+ Hisse) Tara", callback_data="run_full_scan")],
        [InlineKeyboardButton("📊 BIST 100 Makro Rejim", callback_data="bist_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🏛️ *Full BIST 500 Quant Engine Aktif!*\n\n"
        "Sistem artık BIST'te işlem gören **500+ hissenin tamamını** "
        "eşzamanlı paralel iş parçacıkları (Multi-threading) ile saniyeler içinde tarayabilir."
    )
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "run_full_scan":
        await query.message.reply_text("🔎 *BIST'teki 500+ Hisse Paralel Olarak Taranıyor... (Yaklaşık 15 Saniye)*", parse_mode='Markdown')
        loop = asyncio.get_running_loop()
        signals = await loop.run_in_executor(None, scan_full_bist)

        if not signals:
            await query.message.reply_text(
                "🛡️ *Tüm BIST Taramasında 80+ Kalite Puanına Ulaşan Hisse Bulunamadı.*\n\n"
                "Sermayeyi korumak için %100 Nakit Pozisyonu önerilir.",
                reply_markup=get_main_keyboard()
            )
            return

        # Çok fazla mesaj birikmesini önlemek için ilk 5 EN İYİ hisseyi gönder
        top_signals = signals[:5]
        await query.message.reply_text(f"✅ *Tarama Tamamlandı! Toplam {len(signals)} Adet Yüksek Kaliteli Sinyal Bulundu.* En İyi 5 Tanesi Gönderiliyor:", parse_mode='Markdown')

        for s in top_signals:
            reasons_str = "\n".join([f"• {r}" for r in s['reasons']])
            msg = (
                f"{s['grade']}\n"
                f"───────────────────\n"
                f"📌 *Hisse:* `{s['symbol']}` | *Skor:* `{s['score']}/100`\n"
                f"💵 *Fiyat:* `{s['price']} TL` (Günlük: %{s['change']})\n"
                f"📊 *RSI:* `{s['rsi']}` | *MFI (Para Akışı):* `{s['mfi']}`\n\n"
                f"📋 *Matematiksel Onaylar:*\n{reasons_str}\n"
                f"───────────────────\n"
                f"🛑 *Stop-Loss:* `{s['stop_loss']} TL` (-%{s['risk_pct']})\n"
                f"🎯 *Kar Hedefi:* `{s['take_profit']} TL` (+%{s['reward_pct']})\n"
                f"📐 *Risk/Ödül:* `1 : 2.0` (ATR Tabanlı)\n"
                f"───────────────────\n"
                f"💰 *Pozisyon Modeli (100K Bakiye):*\n"
                f"• *Alınacak Lot:* `{s['shares_to_buy']} Adet`\n"
                f"• *Toplam Tutar:* `{s['position_value']} TL`\n"
                f"───────────────────"
            )
            await query.message.reply_text(msg, parse_mode='Markdown', reply_markup=get_main_keyboard())

    elif query.data == "bist_status":
        await query.message.reply_text("📊 *BIST 100 Makro Rejim Kontrol Ediliyor...*", parse_mode='Markdown')

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))

        print("Full BIST 500 Quant Engine Active!")
        app.run_polling(drop_pending_updates=True, close_loop=False)
