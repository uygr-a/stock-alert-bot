import os
import threading
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7!"

TOKEN = os.environ.get("TELEGRAM_TOKEN")
bot = telebot.TeleBot(TOKEN) if TOKEN else None

if bot:
    try:
        bot.remove_webhook()
    except Exception as e:
        print(f"Webhook temizleme uyarısı: {e}")

    @bot.message_handler(commands=['start'])
    def send_welcome(message):
        markup = InlineKeyboardMarkup()
        markup.row_width = 1
        markup.add(
            InlineKeyboardButton("📈 BIST (Türk Hisseleri Haber & Sinyal)", callback_data='bist'),
            InlineKeyboardButton("💵 Dolar / Euro Sinyalleri", callback_data='doviz'),
            InlineKeyboardButton("📰 Son Haberli Hisseler", callback_data='haberler')
        )
        bot.reply_to(message, "Piyasa Takip & Haber Analiz Sistemine Hoş Geldiniz. Bir kategori seçin:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        if call.data == "bist":
            bot.answer_callback_query(call.id, "BIST 100 verisi ve son haberler analiz ediliyor...")
            
            # İstediğiniz bildirim şablonu formatı
            mesaj = (
                "🚨 **#THYAO Türk Hava Yolları - Yeni Haber**\n"
                "📢 **Haber:** THY, 10 yeni geniş gövdeli uçak alımı için anlaşma imzaladı.\n"
                "🟢 **Etki:** Olumlu (Önem Yüksek)\n"
                "⏳ **Piyasa Durumu:** Teyit Edildi 🟢\n"
                "🛡 **Teknik Destek:** 305,50 TL\n"
                "🎯 **Teknik Direnç:** 318,00 TL\n"
                "📊 **Güncel Fiyat:** 312,25 TL | Günlük Değişim: **+%3,4**\n"
                "⏱ **Haber Zamanı:** Bugün 14:35 TR (Canlı)"
            )
            
            sub_markup = InlineKeyboardMarkup()
            sub_markup.row_width = 3
            sub_markup.add(
                InlineKeyboardButton("🔥 Haberli Hisseler", callback_data='bist_haberli'),
                InlineKeyboardButton("📰 Son Haberler", callback_data='bist_son'),
                InlineKeyboardButton("⭐ Önemliler", callback_data='bist_onemli')
            )
            bot.send_message(call.message.chat.id, mesaj, parse_mode="Markdown", reply_markup=sub_markup)

        elif call.data == "doviz":
            bot.answer_callback_query(call.id, "Döviz ve Makro Haberler Çekiliyor...")
            
            mesaj = (
                "🚨 **#USDTRY Dolar/TL - Makro Haber**\n"
                "📢 **Haber:** ABD Merkez Bankası (FED) faiz indirim döngüsünü başlattı.\n"
                "🟡 **Etki:** Nötr / Sınırlı Olumlu\n"
                "🛡 **Teknik Destek:** 34,10 TL\n"
                "🎯 **Teknik Direnç:** 34,50 TL\n"
                "📊 **Güncel Fiyat:** 34,22 TL | Günlük Değişim: **+%0,12**\n"
                "⏱ **Haber Zamanı:** Bugün 15:00 TR"
            )
            bot.send_message(call.message.chat.id, mesaj, parse_mode="Markdown")

def run_bot():
    if bot:
        print("Telegram Bot Polling Başlatıldı!")
        bot.infinity_polling(none_stop=True)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
