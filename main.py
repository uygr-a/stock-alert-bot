import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from flask import Flask
import tvDatafeed
from tvDatafeed import TvDatafeed, Interval
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging Ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask Web Sunucusu (Render Health Check)
app_flask = Flask(__name__)

@app_flask.route('/')
def home():
    return "BIST Quant Engine v2 is Live!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    app_flask.run(host='0.0.0.0', port=port)

# Telegram Token
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# TradingView İstemcisi
tv = TvDatafeed()

# BIST Sembol Listesi
BIST_SYMBOLS = [
    "AEFES", "AGHOL", "AHGAZ", "AKBNK", "AKCNS", "AKFGY", "AKSA", "AKSEN", "ALARK", "ALBRK",
    "ALEVT", "ALFAS", "ANSGR", "ARCLK", "ARDYZ", "ASELS", "ASTOR", "BERA", "BIMAS", "BRSAN",
    "BRYAT", "BUCIM", "CANTE", "CCOLA", "CIMSA", "CWENE", "DOAS", "DOHOL", "ECILC", "EGEEN",
    "EKGYO", "ENJSA", "ENKAI", "EREGL", "EUPWR", "FROTO", "GARAN", "GESAN", "GUBRF", "HALKB",
    "HEKTS", "ISCTR", "KCHOL", "KONTR", "KORDS", "KOZAL", "KOZAA", "KRDMD", "MIATK", "MGROS",
    "ODAS", "OTKAR", "OYAKC", "PETKM", "PGSUS", "SAHOL", "SASA", "SISE", "SKBNK", "SOKM",
    "TAVHL", "TCHAM", "THYAO", "TKFEN", "TOASO", "TSKB", "TTKOM", "TUPRS", "TURSG", "ULKER",
    "VAKBN", "VESTL", "YEOTK", "YKBNK", "ZOREN"
]

def analyze_symbol(symbol):
    """Tek bir sembol için teknik analiz gerçekleştirir."""
    try:
        df = tv.get_hist(symbol=symbol, exchange='BIST', interval=Interval.in_daily, n_bars=100)
        if df is None or df.empty or len(df) < 50:
            return None
        
        close = df['close']
        last_close = close.iloc[-1]
        
        # Basit Hareketli Ortalamalar (SMA)
        sma20 = close.rolling(window=20).mean().iloc[-1]
        sma50 = close.rolling(window=50).mean().iloc[-1]
        
        # Göreceli Güç Endeksi (RSI)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = (100 - (100 / (1 + rs))).iloc[-1]

        # Puanlama Mantığı
        score = 50
        if last_close > sma20: score += 15
        if last_close > sma50: score += 15
        if 40 <= rsi <= 65: score += 20

        if score >= 80:
            return {
                'symbol': symbol,
                'score': score,
                'price': last_close,
                'rsi': round(rsi, 2),
                'sma20': round(sma20, 2)
            }
    except Exception as e:
        logger.error(f"{symbol} analiz hatası: {e}")
    return None

def run_full_scan():
    """Tüm sembolleri tarar ve yüksek puanlıları döndürür."""
    results = []
    for sym in BIST_SYMBOLS:
        res = analyze_symbol(sym)
        if res:
            results.append(res)
        time.sleep(0.1)  # Rate-limit koruması
    return sorted(results, key=lambda x: x['score'], reverse=True)

# Telegram Komutları
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Manuel Tarama Yap (/scan)", callback_data='run_scan')],
        [InlineKeyboardButton("📊 Sistem Durumu (/status)", callback_data='run_status')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📈 **BIST Quant Engine v2** Sistemine Hoş Geldiniz!\n\n"
        "Aşağıdaki butonları kullanarak tarama başlatabilir veya sistem durumunu kontrol edebilirsiniz.",
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
    time_str = tr_time.strftime('%Y-%m-%d %H:%M:%S')
    await update.message.reply_text(f"✅ Bot Aktif!\n🕒 Türkiye Saati: {time_str}")

async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ BIST hisseleri taranıyor, lütfen bekleyin...")
    signals = run_full_scan()
    
    if not signals:
        await msg.edit_text("❌ Şu an kriterlere uyan yüksek puanlı hisse bulunamadı.")
        return

    text = "🚀 **BIST Yüksek Puanlı Sinyaller:**\n\n"
    for s in signals[:10]:
        text += f"🔹 **{s['symbol']}** | Puan: `{s['score']}` | Fiyat: `{s['price']:.2f} TL` | RSI: `{s['rsi']}`\n"
    
    await msg.edit_text(text, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == 'run_scan':
        await query.message.reply_text("⏳ Manuel tarama başlatıldı...")
        signals = run_full_scan()
        if not signals:
            await query.message.reply_text("❌ Kriterlere uyan hisse bulunamadı.")
            return
        
        text = "🚀 **BIST Yüksek Puanlı Sinyaller:**\n\n"
        for s in signals[:10]:
            text += f"🔹 **{s['symbol']}** | Puan: `{s['score']}` | Fiyat: `{s['price']:.2f} TL` | RSI: `{s['rsi']}`\n"
        await query.message.reply_text(text, parse_mode='Markdown')
        
    elif query.data == 'run_status':
        tr_time = datetime.now(timezone.utc) + timedelta(hours=3)
        time_str = tr_time.strftime('%Y-%m-%d %H:%M:%S')
        await query.message.reply_text(f"✅ Bot Aktif!\n🕒 Türkiye Saati: {time_str}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Botta bir hata oluştu:", exc_info=context.error)

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
        
        # Hata yakalayıcı
        app.add_error_handler(error_handler)

        logger.info("BIST Quant Engine v2 Polling Başlatıldı!")
        app.run_polling(drop_pending_updates=True)
