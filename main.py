import os
import threading
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

# Logging ayarları
logging.basicConfig(level=logging.INFO)

# Flask uygulaması (Render Heartbeat)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

# Telegram Bot Kurulumu
TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TOKEN) if TOKEN else None

if bot:
    # /start komutu
    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("📈 BIST 100", callback_data='bist'),
            InlineKeyboardButton("💵 Dolar / Euro", callback_data='doviz'),
            InlineKeyboardButton("📰 Son Haberler", callback_data='haberler')
        )
        bot.reply_to(message, "Merhaba! Piyasa ve haber takip botuna hoş geldiniz. Seçim yapın:", reply_markup=markup)

    # BUTON TIKLAMALARINI YANITLAYAN KISIM
    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        if call.data == "bist":
            bot.answer_callback_query(call.id, "BIST 100 verisi sorgulanıyor...")
            bot.send_message(call.message.chat.id, "📈 **BIST 100:** 9.850,20 (%1,12 🟢)")
        
        elif call.data == "doviz":
            bot.answer_callback_query(call.id, "Döviz kurları alınıyor...")
            bot.send_message(call.message.chat.id, "💵 **Dolar:** 34.20 TL\n💶 **Euro:** 37.50 TL")
            
        elif call.data == "haberler":
            bot.answer_callback_query(call.id, "Haberler getiriliyor...")
            bot.send_message(call.message.chat.id, "📰 **Son Piyasa Haberleri:**\n- Merkez Bankası faiz kararı açıklandı.\n- Borsa haftayı primli kapattı.")

def run_bot():
    if bot:
        print("Telegram Bot Polling Başlatıldı!")
        bot.infinity_polling(none_stop=True)
    else:
        print("HATA: TELEGRAM_TOKEN bulunamadı!")

# Botu arka planda çalıştır
threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
