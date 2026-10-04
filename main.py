import os
import threading
import logging
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Logging ayarları
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Render heartbeat için Flask uygulaması
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

# Telegram Bot Başlatıcı Fonksiyon
def run_bot():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("HATA: TELEGRAM_TOKEN bulunamadı!")
        return

    # python-telegram-bot v20+ yapısı
    application = ApplicationBuilder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📈 BIST 100", callback_data='bist'), InlineKeyboardButton("💵 Dolar / Euro", callback_data='doviz')],
            [InlineKeyboardButton("📰 Son Haberler", callback_data='haberler')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Merhaba! Piyasa ve haber takip botuna hoş geldiniz. Seçim yapın:", reply_markup=reply_markup)

    application.add_handler(CommandHandler("start", start))
    
    print("Telegram Bot Polling Başlatılıyor...")
    application.run_polling(drop_pending_updates=True)

# Botu ayrı bir Thread içinde başlat
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
