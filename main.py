import os
import threading
import asyncio
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging yapılandırması
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Render / UptimeRobot için Keep-Alive Flask Sunucusu
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "BIST Quant Engine v2 Active!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# Gönderilen sinyallerin tekrar etmemesi için hafıza (Symbol -> Son Gönderim Zamanı)
SENT_SIGNALS = {}

def get_bist_tickers():
    """BIST 500 Ana Hisse Evreni"""
    base_tickers = [
        "AAVST", "A1CAP", "ACSEL", "ADEL", "ADESE", "AGHOL", "AGROT", "AHGAZ", "AKBNK", "AKCNS",
        "AKFGY", "AKFYE", "AKMGH", "AKSA", "AKSEN", "AKSGY", "ALARK", "ALBRK", "ALCAR", "ALCTL",
        "ALFAS", "ALGYO", "ALKA", "ALKIM", "ALMAD", "ALTNY", "ALVES", "ANELE", "ANGEN", "ANHYT",
        "ANSGR", "ARASE", "ARCLK", "ARDYZ", "ARENA", "ARSAN", "ARTMS", "ASELS", "ASGYO", "ASTOR",
        "ATAGY", "ATAKP", "ATATP", "ATEKS", "AVOD", "AVPGY", "AVTUR", "AYCES", "AYDEM", "AYGAZ",
        "AZTEK", "BAGFS", "BAKAB", "BANVT", "BARMA", "BASGZ", "BAYRK", "BEGYO", "BERA", "BEYAZ",
        "BFREN", "BIENP", "BIGCHEFS", "BIMAS", "BINHO", "BIOEN", "BIZIM", "BJKAS", "BLCYT", "BMSCH",
        "BMSTL", "BNTAS", "BOBET", "BORAB", "BORSK", "BOSSA", "BRISA", "BRSAN", "BRYAT", "BSOKE",
        "BTCIM", "BUCIM", "BURCE", "BURVA", "BVSAN", "BYDNR", "CANTE", "CATES", "CCOLA", "CELHA",
        "CEMAS", "CEMTS", "CMBTN", "CMENT", "CONSE", "COSMO", "CRFSA", "CUSAN", "CVKMD", "CWENE",
        "DAGI", "DAPGM", "DARDL", "DGATE", "DGGYO", "DITAS", "DMRGD", "DMSAS", "DNISI", "DOAS",
        "DOBUR", "DOCTA", "DOFER", "DOHOL", "EBEBK", "ECILC", "ECZYT", "EDATA", "EDIP", "EGEEN",
        "EGGUB", "EGPRO", "EGSER", "EKGYO", "ELITE", "EMKEL", "ENJSA", "ENKAI", "ENSRI", "EPLAS",
        "ERCB", "EREGL", "ERSU", "ESCAR", "ESCOM", "EUPWR", "FORTE", "FROTO", "FZLGY", "GARAN",
        "GWIND", "GENTS", "GESAN", "GIPTA", "GLCVY", "GLYHO", "GMTAS", "GOKNR", "GOLTS", "GOODY",
        "GOZDE", "GRSEL", "GRTHO", "GSDHO", "GSRAY", "GUBRF", "HALKB", "HATEK", "HEKTS", "HITIT",
        "HOROZ", "HRKET", "HUBVC", "HUNER", "HURGZ", "ICBCT", "IEYHO", "IHAAS", "IHEVA", "IHGZT",
        "IHLGM", "IHYAY", "INGRM", "INFO", "INTEM", "INVES", "IPEKE", "ISCTR", "ISDMR", "ISFIN",
        "ISGYO", "ISMEN", "ISSEN", "IZENR", "IZINV", "IZMDC", "JANTS", "KAFEIN", "KLSER", "KARYE",
        "KATMR", "KAYSE", "KBORU", "KCAER", "KCHOL", "KFEIN", "KLMSN", "KLNMA", "KLRHO", "KMPUR",
        "KNFRT", "KONTR", "KNYA", "KORDS", "KOZAL", "KOZAA", "KRDMD", "KRPLS", "KRTEK", "KRVGD",
        "KSTUR", "KTLEV", "KUTPO", "LIDER", "LKMNH", "LMKDC", "LUKSK", "MAALT", "MACKO", "MAKIM",
        "MANAS", "MARBL", "MARKA", "MAVI", "MEDTR", "MEGAP", "MEGMT", "MEPET", "MERCN", "MERIT",
        "MERKO", "METRO", "METUR", "MGROS", "MIATK", "MHRGY", "MNDTR", "MOBTL", "MOGAN", "MPARK",
        "MRGYO", "MRSHL", "MSGYO", "MTRKS", "NATEN", "NETAS", "NIBAS", "NTHOL", "NUGYO", "OBAMS",
        "OBASE", "ODAS", "ONCSM", "ORGE", "ORMA", "OSMEN", "OSTIM", "OTKAR", "OTTO", "OYAKC",
        "OYYAT", "OZATD", "OZKGY", "OZRDN", "OZSUB", "PAGYO", "PAMEL", "PAPIL", "PARSN", "PASEU",
        "PATEK", "PCILT", "PEKGY", "PENTA", "PETKM", "PETUN", "PGSUS", "PINAR", "PKART", "PLTUR",
        "POLHO", "POLTK", "PRDGS", "PRKME", "PRZMA", "PSDTC", "PSGYO", "QNBFB", "RALYH", "RAYSG",
        "REEDR", "RGYAS", "RNPOL", "RODRG", "RUBNS", "RYGYO", "RYSAS", "SAHOL", "SAMAT", "SANEL",
        "SANFM", "SARKY", "SASA", "SAYAS", "SDTTR", "SEGMN", "SEKFK", "SEKUR", "SELEC", "SELVA",
        "SEYKM", "SILVR", "SISE", "SKBNK", "SKTAS", "SMART", "SMRTG", "SNICA", "SNKRN", "SOKE",
        "SOKM", "SONME", "SRVGY", "SUMAS", "SUNTK", "SURGY", "SUWEN", "TATEN", "TATGD", "TAVHL",
        "TCELL", "TCKRC", "THYAO", "TKFEN", "TKNSA", "TLMAN", "TMSN", "TOASO", "TRGYO", "TRILC",
        "TSKB", "TSPOR", "TTKOM", "TTRAK", "TUKAS", "TUPRS", "TUREX", "TURSG", "UFUK", "ULAS",
        "ULKER", "UNLU", "USAK", "VAKBN", "VAKKO", "VBTYZ", "VERTU", "VERUS", "VESBE", "VESTL",
        "VKGYO", "YAPRK", "YATAS", "YEOTK", "YGGYO", "YKBNK", "YUNSA", "ZRGYO"
    ]
    return list(set([f"{t}.IS" for t in base_tickers]))

def calculate_adx(df, period=14):
    """ADX İndikatörü Hesaplama"""
    try:
        df = df.copy()
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
        df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)

        df['+DM'] = np.where((df['High'] - df['High'].shift(1)) > (df['Low'].shift(1) - df['Low']), 
                             np.maximum(df['High'] - df['High'].shift(1), 0), 0)
        df['-DM'] = np.where((df['Low'].shift(1) - df['Low']) > (df['High'] - df['High'].shift(1)), 
                             np.maximum(df['Low'].shift(1) - df['Low'], 0), 0)

        tr_smooth = df['TR'].rolling(period).sum()
        plus_di = 100 * (df['+DM'].rolling(period).sum() / (tr_smooth + 1e-9))
        minus_di = 100 * (df['-DM'].rolling(period).sum() / (tr_smooth + 1e-9))
        
        dx = 100 * (abs(plus_di - minus_di) / (plus_di + minus_di + 1e-9))
        adx = dx.rolling(period).mean()
        return round(adx.iloc[-1], 1)
    except Exception:
        return 20.0

def run_quant_batch_scan(portfolio_size=100000, risk_per_trade_pct=0.01):
    """
    v2 BATCH ENGINE:
    Tekil istekler yerine yf.download ile 500 hisseyi TOPLU indirir.
    15 Dakikalık Veri Üzerinden İnce Ölçekli (Granular) Skorlama Yapar.
    """
    tickers = get_bist_tickers()
    
    # 1. BIST100 Göreli Güç İncelemesi İçin XU100 Verisi
    try:
        xu100 = yf.download("XU100.IS", period="1mo", interval="15m", progress=False)
        if isinstance(xu100.columns, pd.MultiIndex):
            xu100 = xu100.xs("XU100.IS", axis=1, level=1)
        xu100_perf = (xu100['Close'].iloc[-1] - xu100['Close'].iloc[-20]) / xu100['Close'].iloc[-20]
    except Exception:
        xu100_perf = 0.0

    # 2. TOPLU (BATCH) VERİ İNDİRME - Network ve Timeout Darboğazını Çözen Kısım
    logger.info("Batch veri indirme başlatıldı...")
    data = yf.download(tickers, period="1mo", interval="15m", group_by="ticker", progress=False, threads=True)
    logger.info("Batch veri tamamlandı, analizler yapılıyor...")

    signals = []

    for ticker in tickers:
        try:
            # MultiIndex'ten ilgili hissenin verisini süzme
            if ticker in data.columns.levels[0]:
                df = data[ticker].dropna()
            else:
                continue

            if len(df) < 60:
                continue

            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']

            curr_price = round(close.iloc[-1], 2)
            if curr_price <= 0:
                continue

            # --- TEKNİK İNDİKATÖR HESAPLAMALARI ---
            ema20 = close.ewm(span=20, adjust=False).mean()
            ema50 = close.ewm(span=50, adjust=False).mean()
            ema200 = close.ewm(span=200, adjust=False).mean()

            # RSI (14)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi = round((100 - (100 / (1 + (gain / (loss + 1e-9))))).iloc[-1], 1)

            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal_line = macd.ewm(span=9, adjust=False).mean()

            # ATR (14)
            tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]

            # ADX
            adx_val = calculate_adx(df)

            # Hacim Anomalisi
            vol_mean = volume.rolling(20).mean().iloc[-1]
            vol_mult = round(volume.iloc[-1] / (vol_mean + 1e-9), 1)

            # 20 Bar Direnç Kırılımı
            res_20 = high.iloc[-21:-1].max()
            is_breakout = close.iloc[-1] > res_20

            # Göreli Güç (Alfa)
            stock_perf = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
            alfa_pct = round((stock_perf - xu100_perf) * 100, 1)

            # --- İNCE ÖLÇEKLİ SKORLAMA MOTORU (MAX 100) ---
            score = 0
            reasons = []

            # 1. Trend Hizalaması (Max 25 Puan)
            if close.iloc[-1] > ema20.iloc[-1] and ema20.iloc[-1] > ema50.iloc[-1]:
                score += 15
                reasons.append("Fiyat EMA20 üzerinde ve EMA20 > EMA50")
            if close.iloc[-1] > ema200.iloc[-1]:
                score += 10
                reasons.append("Orta/uzun vadeli trend pozitif (EMA200 Üzerinde)")

            # 2. Hacim anomalisi (Max 15 Puan)
            if vol_mult >= 2.0:
                score += 15
                reasons.append(f"Hacim normalin {vol_mult}x üzerinde")
            elif vol_mult >= 1.4:
                score += 8
                reasons.append(f"Hacimde artış var ({vol_mult}x)")

            # 3. Momentum & RSI (Max 15 Puan)
            if 52 <= rsi <= 68:
                score += 15
                reasons.append(f"RSI sağlıklı momentum bölgesinde ({rsi})")
            elif 45 <= rsi < 52:
                score += 7

            # 4. MACD Gücü (Max 15 Puan)
            if macd.iloc[-1] > signal_line.iloc[-1]:
                score += 10
                reasons.append("MACD sinyal çizgisinin üzerinde")
                if macd.iloc[-1] > macd.iloc[-2]:
                    score += 5
                    reasons.append("MACD histogramı güçleniyor")

            # 5. Breakout Kırılımı (Max 15 Puan)
            if is_breakout:
                score += 15
                reasons.append("20 barlık direnç yukarı kırıldı")

            # 6. Trend Gücü ADX (Max 10 Puan)
            if adx_val >= 25:
                score += 10
                reasons.append(f"ADX güçlü trend gösteriyor ({adx_val})")

            # 7. Alfa vs BIST100 (Max 5 Puan)
            if alfa_pct > 2.0:
                score += 5

            # --- SİNYAL EŞİĞİ VE RİSK PLANLAMASI ---
            # Varsayılan Alarm Eşiği: 85 Puan
            if score >= 85:
                stop_loss = round(curr_price - (atr * 1.5), 2)
                tp1 = round(curr_price + (atr * 2.0), 2)
                tp2 = round(curr_price + (atr * 3.5), 2)

                risk_per_share = curr_price - stop_loss
                if risk_per_share <= 0:
                    continue

                risk_rr = round((tp1 - curr_price) / risk_per_share, 1)

                # Risk Hesaplama (100K TL için %1 Risk = 1000 TL Max Risk)
                max_risk_amount = portfolio_size * risk_per_trade_pct
                shares_to_buy = int(max_risk_amount / risk_per_share)
                position_size = round(shares_to_buy * curr_price, 2)

                clean_symbol = ticker.replace('.IS', '')

                signals.append({
                    "symbol": clean_symbol,
                    "score": score,
                    "price": curr_price,
                    "reasons": reasons,
                    "sl": stop_loss,
                    "tp1": tp1,
                    "tp2": tp2,
                    "rr": f"1:{risk_rr}",
                    "rsi": rsi,
                    "adx": adx_val,
                    "vol_mult": vol_mult,
                    "alfa": alfa_pct,
                    "shares": shares_to_buy,
                    "position_size": position_size
                })

        except Exception as ex:
            continue

    signals.sort(key=lambda x: x['score'], reverse=True)
    return signals

def format_signal_message(s):
    """Yeni Sinyal Telegram Mesaj Şablonu"""
    reasons_str = "\n".join([f"• {r}" for r in s['reasons']])
    
    msg = (
        f"🚨 *BIST QUANT FIRSATI*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Hisse:* `{s['symbol']}`\n"
        f"⭐ *Skor:* `{s['score']}/100`\n"
        f"💵 *Fiyat:* `{s['price']} TL`\n\n"
        f"🧠 *Neden?*\n{reasons_str}\n\n"
        f"📐 *Risk Planı*\n"
        f"🛑 *SL:* `{s['sl']} TL`\n"
        f"🎯 *TP1:* `{s['tp1']} TL`\n"
        f"🎯 *TP2:* `{s['tp2']} TL`\n"
        f"⚖️ *Risk/Ödül:* `{s['rr']}`\n\n"
        f"📊 *RSI:* `{s['rsi']}` | *ADX:* `{s['adx']}` | *Hacim:* `{s['vol_mult']}x`\n"
        f"📈 *Alfa vs BIST100:* `+{s['alfa']}%`\n\n"
        f"💰 *100K TL Model / %1 Risk:*\n"
        f"• *Lot:* `{s['shares']} Adet`\n"
        f"• *Pozisyon:* `{s['position_size']} TL`"
    )
    return msg

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔍 Manuel Tarama Yap (/scan)", callback_data="run_scan")],
        [InlineKeyboardButton("📊 Sistem Durumu (/status)", callback_data="run_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Telegram Komutları
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "🏛️ *BIST Quant Engine v2 - Batch Scanner Aktif!*\n\n"
        "⚡ *Yenilikler:*\n"
        "• 500 Hisse Batch/Toplu Veri İndirme ile Taranır (Işık Hızında).\n"
        "• 15-Dakikalık Grafikler ve 100 Üzerinden İnce Puanlama Motoru.\n"
        "• Otomatik Dinamik SL, TP1, TP2 ve Lot Hesaplaması.\n"
        "• Spam/Tekrar Sinyal Engelleme Filtresi.\n\n"
        "Komutlar: /scan , /status"
    )
    await update.message.reply_text(welcome, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "✅ *Sistem Aktif.* 15 dakikalık BIST Batch Engine hazır ve taranamaya uygun."
    if update.message:
        await update.message.reply_text(msg, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode='Markdown')

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = None
    if update.message:
        status_msg = await update.message.reply_text("⚡ *BIST 500 Batch Taraması Başlatıldı... (5-10 Saniye)*", parse_mode='Markdown')
    elif update.callback_query:
        status_msg = await update.callback_query.message.reply_text("⚡ *BIST 500 Batch Taraması Başlatıldı... (5-10 Saniye)*", parse_mode='Markdown')

    loop = asyncio.get_running_loop()
    signals = await loop.run_in_executor(None, run_quant_batch_scan)

    if not signals:
        await status_msg.edit_text("🛡️ *Tüm BIST Taramasında 85+ Skor Alan Hisse Bulunamadı.*\nSistem risk almamak için nakit pozisyonunu koruyor.", reply_markup=get_main_keyboard())
        return

    await status_msg.edit_text(f"✅ *Tarama Tamamlandı! Toplam {len(signals)} Adet High-Conviction Sinyal Bulundu:*", parse_mode='Markdown')

    for s in signals[:5]: # En iyi ilk 5 sinyali gönder
        # Tekrar gönderim kontrolü (Son 2 saat içinde atıldıysa atma)
        now = datetime.now()
        last_sent = SENT_SIGNALS.get(s['symbol'])
        if last_sent and (now - last_sent) < timedelta(hours=2):
            continue

        SENT_SIGNALS[s['symbol']] = now
        msg = format_signal_message(s)
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "run_scan":
        await scan_cmd(update, context)
    elif query.data == "run_status":
        await status_cmd(update, context)

if __name__ == '__main__':
    # 1. Flask Web Server Başlat
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    # 2. Telegram Bot Polling Başlat
    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CommandHandler("scan", scan_cmd))
        app.add_handler(CommandHandler("status", status_cmd))
        app.add_handler(CallbackQueryHandler(button_handler))

        logger.info("BIST Quant Engine v2 Polling Başlatıldı!")
        app.run_polling(drop_pending_updates=True)
