import os
import threading
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7 with Gemini AI!"

# Telegram & Gemini Kurulumu
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None

# Haber Analiz Fonksiyonu
def haber_analiz_et(haber_metni):
    if not gemini_model:
        return "🟢 Etki: Analiz Edilemedi (API Key Eksik)"
    
    prompt = f"""
    Aşağıdaki finans haberini analiz et ve tam olarak şu formatta kısa bir yanıt ver:
    Olumlu (Önem Yüksek) VEYA Olumsuz VEYA Nötr
    
    Haber: {haber_metni}
    """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini hatası: {e}")
        return "Nötr"

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
        bot.reply_to(message, "Piyasa Takip & AI Haber Analiz Sistemine Hoş Geldiniz. Bir kategori seçin:", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        if call.data == "bist":
            bot.answer_callback_query(call.id, "Haber Gemini AI ile analiz ediliyor...")
            
            ornek_haber = "Türk Hava Yolları, 10 yeni geniş gövdeli uçak alımı için Airbus ile resmi anlaşma imzaladı."
            ai_analiz = haber_analiz_et(ornek_haber)

            mesaj = (
                "🚨 **#THYAO Türk Hava Yolları - Yeni Haber**\n\n"
                f"📢 **Haber:** {ornek_haber}\n"
                f"🟢 **Haber:** {ai_analiz}\n"
                "⏳ **Piyasa Durumu:** Teyit Edildi 🟢\n"
                "🛡 **Teknik Destek:** 305,50 TL\n"
                "🎯 **Teknik Direnç:** 318,00 TL\n"
                "📊 **Güncel Fiyat:** 312,25 TL | Günlük Değişim: **+%3,4**\n\n"
                "⏱ **Haber Zamanı:** Canlı"
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
            bot.answer_callback_query(call.id, "Döviz ve Makro Haberler Analiz Ediliyor...")
            
            ornek_haber = "ABD Merkez Bankası (FED), politika faizini 50 baz puan indirerek faiz indirim döngüsünü başlattı."
            ai_analiz = haber_analiz_et(ornek_haber)

            mesaj = (
                "🚨 **#USDTRY Dolar/TL - Makro Haber**\n\n"
                f"📢 **Haber:** {ornek_haber}\n"
                f"🤖 **AI Analizi:** {ai_analiz}\n"
                "🛡 **Teknik Destek:** 34,10 TL\n"
                "🎯 **Teknik Direnç:** 34,50 TL\n"
                "📊 **Güncel Fiyat:** 34,22 TL | Günlük Değişim: **+%0,12**"
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
