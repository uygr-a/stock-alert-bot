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

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "BIST Dip Hunter Active!", 200

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
SENT_SIGNALS = {}

def get_bist_tickers():
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

def run_dip_hunter_scan(portfolio_size=100000, risk_per_trade_pct=0.01):
    tickers = get_bist_tickers()
    logger.info("Batch veri indirme başlatıldı...")
    data = yf.download(tickers, period="1mo", interval="15m", group_by="ticker", progress=False, threads=True)
    
    signals = []

    for ticker in tickers:
        try:
            if ticker in data.columns.levels[0]:
                df = data[ticker].dropna()
            else:
                continue

            if len(df) < 40:
                continue

            close = df['Close']
            high = df['High']
            low = df['Low']
            volume = df['Volume']

            curr_price = round(close.iloc[-1], 2)
            if curr_price <= 0:
                continue

            # Hareketli Ortalamalar
            ema8 = close.ewm(span=8, adjust=False).mean()
            ema20 = close.ewm(span=20, adjust=False).mean()

            # RSI Hesaplama
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rsi_series = 100 - (100 / (1 + (gain / (loss + 1e-9))))
            rsi_curr = round(rsi_series.iloc[-1], 1)
            rsi_prev = round(rsi_series.iloc[-2], 1)

            # MACD
            ema12 = close.ewm(span=12, adjust=False).mean()
            ema26 = close.ewm(span=26, adjust=False).mean()
            macd = ema12 - ema26
            signal = macd.ewm(span=9, adjust=False).mean()

            # ATR (Dinamik Stop için)
            tr = pd.concat([high - low, abs(high - close.shift()), abs(low - close.shift())], axis=1).max(axis=1)
            atr = tr.rolling(14).mean().iloc[-1]

            vol_mean = volume.rolling(20).mean().iloc[-1]
            vol_mult = round(volume.iloc[-1] / (vol_mean + 1e-9), 1)

            # ---------------- DİP DÖNÜŞ ŞARTLARI (2. RESİM MANTIĞI) ----------------
            
            # KATI FİLTRE 1: Kesinlikle Tepede Olmayacak (RSI 65 üzeriyse ELE)
            if rsi_curr > 62:
                continue

            score = 0
            reasons = []

            # 1. RSI DİPTEN YUKARI BÜKÜLME (V Yapma Hareketi)
            if rsi_prev <= 40 and rsi_curr > rsi_prev:
                score += 35
                reasons.append(f"RSI dipten yukarı döndü ({rsi_prev} -> {rsi_curr})")

            # 2. İLK YEŞİL DÖNÜŞ ÇUBUĞU VE HACİM İVMESİ
            if close.iloc[-1] > close.iloc[-2] and vol_mult >= 1.3:
                score += 30
                reasons.append(f"Dipten hacimli kalkış ({vol_mult}x Hacim)")

            # 3. EMA8 (KISA VADELİ MENTUM) ÜZERİNE ATMA
            if close.iloc[-2] < ema8.iloc[-2] and close.iloc[-1] >= ema8.iloc[-1]:
                score += 25
                reasons.append("Fiyat EMA8 ortalamasının üzerine kırdı")

            # 4. MACD DİPTE TAZE ALIM KESİŞİMİ
            if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]:
                score += 20
                reasons.append("MACD dip bölgesinde alım kesti")

            # Min 70 Puan Üzeri Tam Dip Dönüşü Sinyali
            if score >= 70:
                # Stop loss dip seviyenin hemen altına konur
                recent_low = low.iloc[-5:].min()
                stop_loss = round(min(recent_low, curr_price - (atr * 1.2)), 2)
                
                tp1 = round(curr_price + (atr * 2.2), 2)
                tp2 = round(curr_price + (atr * 4.0), 2)

                risk_per_share = curr_price - stop_loss
                if risk_per_share <= 0:
                    continue

                risk_rr = round((tp1 - curr_price) / risk_per_share, 1)

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
                    "rsi": rsi_curr,
                    "vol_mult": vol_mult,
                    "shares": shares_to_buy,
                    "position_size": position_size
                })

        except Exception:
            continue

    signals.sort(key=lambda x: x['score'], reverse=True)
    return signals

def format_signal_message(s):
    reasons_str = "\n".join([f"• {r}" for r in s['reasons']])
    
    msg = (
        f"🎯 *DİP DÖNÜŞ FIRSATI (Erken Giriş)*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 *Hisse:* `{s['symbol']}`\n"
        f"⭐ *Dip Skoru:* `{s['score']}/100`\n"
        f"💵 *Giriş Fiyatı:* `{s['price']} TL`\n\n"
        f"🧠 *Neden Dip Sinyali?*\n{reasons_str}\n\n"
        f"📐 *Risk / Ödül Planı*\n"
        f"🛑 *Stop Loss (SL):* `{s['sl']} TL`\n"
        f"🎯 *Hedef 1 (TP1):* `{s['tp1']} TL`\n"
        f"🎯 *Hedef 2 (TP2):* `{s['tp2']} TL`\n"
        f"⚖️ *Oran:* `{s['rr']}`\n\n"
        f"📊 *RSI:* `{s['rsi']}` | *Hacim:* `{s['vol_mult']}x`\n\n"
        f"💰 *100K TL Model / %1 Risk:*\n"
        f"• *Lot:* `{s['shares']} Adet`\n"
        f"• *Pozisyon:* `{s['position_size']} TL`"
    )
    return msg

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🔍 Dip Taraması Yap (/scan)", callback_data="run_scan")],
        [InlineKeyboardButton("📊 Sistem Durumu (/status)", callback_data="run_status")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        "🏛️ *BIST Quant Engine - Dip Hunter Modu Aktif!*\n\n"
        "🎯 *Çalışma Prensibi:*\n"
        "• Artık tepedeki (RSI > 62) hisselere 'AL' demez.\n"
        "• Tam dip yapıp hacimle yukarı dönen (2. Resim) hisseleri yakalar.\n\n"
        "Komutlar: /scan , /status"
    )
    await update.message.reply_text(welcome, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "✅ *Sistem Aktif.* Dip avcısı tarama motoru hazır."
    if update.message:
        await update.message.reply_text(msg, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.message.reply_text(msg, parse_mode='Markdown')

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    status_msg = None
    if update.message:
        status_msg = await update.message.reply_text("⚡ *BIST Dip Dönüş Taraması Yapılıyor...*", parse_mode='Markdown')
    elif update.callback_query:
        status_msg = await update.callback_query.message.reply_text("⚡ *BIST Dip Dönüş Taraması Yapılıyor...*", parse_mode='Markdown')

    loop = asyncio.get_running_loop()
    signals = await loop.run_in_executor(None, run_dip_hunter_scan)

    if not signals:
        await status_msg.edit_text("🛡️ *Şu an dipten yukarı dönüş yapan uygun hisse bulunamadı.*", reply_markup=get_main_keyboard())
        return

    await status_msg.edit_text(f"✅ *Tarama Tamamlandı! Bulunan Dip Dönüş Sinyalleri:*", parse_mode='Markdown')

    for s in signals[:5]:
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

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Botta hata:", exc_info=context.error)

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start_cmd))
        app.add_handler(CommandHandler("scan", scan_cmd))
        app.add_handler(CommandHandler("status", status_cmd))
        app.add_handler(CallbackQueryHandler(button_handler))
        app.add_error_handler(error_handler)

        logger.info("BIST Dip Hunter Polling Başlatıldı!")
        app.run_polling(drop_pending_updates=True)
