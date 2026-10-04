import os
import logging
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

# Telegram Bot Yapılandırması
token = os.environ.get("TELEGRAM_TOKEN")
if token:
    tg_app = ApplicationBuilder().token(token).build()

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton("📈 BIST 100", callback_data='bist'), InlineKeyboardButton("💵 Dolar / Euro", callback_data='doviz')],
            [InlineKeyboardButton("📰 Son Haberler", callback_data='haberler')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Merhaba! Piyasa ve haber takip botuna hoş geldiniz. Seçim yapın:", reply_markup=reply_markup)

    tg_app.add_handler(CommandHandler("start", start))

    # Gunicorn başlatılırken bot döngüsünü çalıştır
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.create_task(tg_app.initialize())
    loop.create_task(tg_app.updater.start_polling(drop_pending_updates=True))
    loop.create_task(tg_app.start())
