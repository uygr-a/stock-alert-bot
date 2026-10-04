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

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def start_telegram_bot():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("HATA: TELEGRAM_TOKEN bulunamadı!")
        return

    # Bot kurulumu
    tg_app = ApplicationBuilder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📈 BIST 100", callback_data='bist'), InlineKeyboardButton("💵 Dolar / Euro", callback_data='doviz')],
            [InlineKeyboardButton("📰 Son Haberler", callback_data='haberler')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Merhaba! Piyasa ve haber takip botuna hoş geldiniz. Seçim yapın:", reply_markup=reply_markup)

    tg_app.add_handler(CommandHandler("start", start))

    print("Telegram Botu başlatılıyor...")
    # Polling işlemini başlat
    tg_app.run_polling(drop_pending_updates=True, close_loop=False)

# Telegram botunu ayrı bir thread (iş parçacığı) olarak başlat
bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
bot_thread.start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
