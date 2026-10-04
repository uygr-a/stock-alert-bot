import os
import threading
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot 7/24 Aktif!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [
            InlineKeyboardButton("📰 Haberli Hisseler", callback_data="news_stocks"),
            InlineKeyboardButton("⚡ Son Haberler", callback_data="latest_news")
        ],
        [
            InlineKeyboardButton("🔥 Önemliler", callback_data="important_news")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_msg = (
        "🚨 **$SSTI SoundThinking** - Yeni Haber\n"
        "Sound Thinking, Transom Capital Group tarafından satın alınacak.\n\n"
        "🟢 **Haber:** Olumlu - Şirket satın alınıyor (Önem Yüksek)\n"
        "⏳ **Piyasa:** Henüz veri yok ⚪ Teyit yok\n"
        "Teknik Destek: **8,19$**\n"
        "Fiyat: **8,33$** | Gün: **+%52,3**\n\n"
        "ℹ️ *Aşağıdaki butonları kullanarak filtreleme yapabilirsiniz:*"
    )

    await update.message.reply_text(welcome_msg, parse_mode="Markdown", reply_markup=reply_markup)

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "news_stocks":
        text = "📊 **Haberli Hisseler:**\n• $SSTI (+%52.3)\n• $NVDA (+%3.1)"
    elif query.data == "latest_news":
        text = "⚡ **Son Haberler:**\n1. $SSTI - Transom Capital satın alımı."
    elif query.data == "important_news":
        text = "🔥 **Önemli Duyurular:**\n• $SSTI - Satın Alma Anlaşması"
    else:
        text = "Bilinmeyen istek."

    await query.edit_message_text(text=text, parse_mode="Markdown")

def run_telegram_bot():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_click))
    application.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()

    run_telegram_bot()
