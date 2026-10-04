import os
import asyncio
import logging
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import hypercorn.asyncio
from hypercorn.config import Config

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Flask uygulaması (Heartbeat için)
app = Flask(__name__)

@app.route('/')
async def home():
    return "Bot is running!"

async def main():
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        print("HATA: TELEGRAM_TOKEN bulunamadı!")
        return

    # Telegram Bot Kurulumu
    tg_app = ApplicationBuilder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📈 BIST 100", callback_data='bist'), InlineKeyboardButton("💵 Dolar / Euro", callback_data='doviz')],
            [InlineKeyboardButton("📰 Son Haberler", callback_data='haberler')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Merhaba! Piyasa ve haber takip botuna hoş geldiniz. Seçim yapın:", reply_markup=reply_markup)

    tg_app.add_handler(CommandHandler("start", start))

    # Botu ve Polling'i başlat
    await tg_app.initialize()
    await tg_app.start()
    await tg_app.updater.start_polling(drop_pending_updates=True)
    print("Telegram Bot Polling Başlatıldı!")

    # Flask Sunucusunu Async olarak çalıştır
    config = Config()
    port = int(os.environ.get('PORT', 10000))
    config.bind = [f"0.0.0.0:{port}"]

    # Hem Flask hem Bot aynı event loop üzerinde çalışsın
    await hypercorn.asyncio.serve(app, config)

if __name__ == '__main__':
    asyncio.run(main())
