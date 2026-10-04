import os
import threading
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from flask import Flask
import google.generativeai as genai
import yfinance as yf
import feedparser

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running 24/7 with Live BIST & Gemini AI Engine!"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

bot = telebot.TeleBot(TELEGRAM_TOKEN) if TELEGRAM_TOKEN else None

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
else:
    gemini_model = None

# Canlı Fiyat Çekme Fonksiyonu (BIST)
def get_live_bist_data(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.IS")
        df = ticker.history(period="5d")
        if df.empty:
            return None
        current_price = df['Close'].iloc[-1]
        prev_price = df['Close'].iloc[-2]
        change_pct = ((current_price - prev_price) / prev_price) * 100
        
        # Basit Destek/Direnç Hesaplaması
        high_price = df['High'].max()
        low_price = df['Low'].min()
        
        return {
            "price": round(current_price, 2),
            "change": round(change_pct, 2),
            "support": round(low_price, 2),
            "resistance": round(high_price, 2)
        }
    except Exception as e:
        print(f"Canlı veri hatası ({symbol}): {e}")
        return None

# Canlı Haber Çekme Fonksiyonu
def get_live_news(symbol):
    try:
        # Investing/Google News BIST RSS Akışı
        rss_url = f"https://news.google.com/rss/search?q={symbol}+bursa+hisse&hl=tr&gl=TR&ceid=TR:tr"
        feed = feedparser.parse(rss_url)
        if feed.entries:
            return feed.entries[0].title
        return f"{symbol} şirketinin son operasyonel ve finansal gelişmeleri."
    except Exception:
        return f"{symbol} için güncel piyasa akışı takip ediliyor."

# Gemini AI Canlı Sinyal ve % Analiz Motoru
def ai_bist_analiz(symbol, price_data, haber_title):
    if not gemini_model:
        return None

    prompt = f"""
    Sen profesyonel bir BIST 100 teknik ve temel analiz uzmanısın.
    Aşağıdaki CANLI verileri kullanarak yatırım analizi yap:
    
    Hisse kodu: #{symbol}
    Canlı Fiyat: {price_data['price']} TL
    Günlük Değişim: %{price_data['change']}
    En Son Haber/Gelişme: {haber_title}
    
    Lütfen yanıtı TAM OLARAK şu şablon formatında üret (açıklama ekleme, direkt bu formatı doldur):
    
    Haber Etkisi: [Olumlu / Olumsuz / Nötr]
    Sinyal: [AL (BUY) / SAT (SELL) / TUT (HOLD)]
    Yükseliş/Düşüş Potansiyeli: % [Sadece Rakam]
    AI Güven Skoru: % [Sadece Rakam]
    Hedef Fiyat (TP): [Rakam] TL
    Stop-Loss (SL): [Rakam] TL
    Özet Analiz: [1 Cümlelik Profesyonel Değerlendirme]
    """
    
    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini AI Analiz Hatası: {e}")
        return None

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
            InlineKeyboardButton("📈 BIST Canlı Haber & AI Sinyal Tara", callback_data='bist'),
            InlineKeyboardButton("💵 Dolar / Euro Canlı Sinyalleri", callback_data='doviz')
        )
        bot.reply_to(message, "🤖 **Canlı BIST & AI Finansal Analiz Motoru**\n\nPiyasayı taramak için bir kategori seçin:", parse_mode="Markdown", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        if call.data == "bist":
            bot.answer_callback_query(call.id, "Canlı BIST verileri taranıyor ve AI analizi yapılıyor...")
            
            # Canlı Taranacak BIST Hissesi Örneği
            target_symbol = "THYAO"
            live_data = get_live_bist_data(target_symbol)
            live_news = get_live_news(target_symbol)
            
            if live_data:
                ai_result = ai_bist_analiz(target_symbol, live_data, live_news)
                
                mesaj = (
                    f"🚨 **#{target_symbol} Türk Hava Yolları - CANLI ANALİZ**\n\n"
                    f"📢 **Son Canlı Haber:** {live_news}\n"
                    f"📊 **Canlı Fiyat:** {live_data['price']} TL (Günlük: %{live_data['change']})\n"
                    f"🛡 **Teknik Destek (SL Altı):** {live_data['support']} TL\n"
                    f"🎯 **Teknik Direnç:** {live_data['resistance']} TL\n\n"
                    f"🤖 **GEMINI AI CANLI SİNYAL VE YÜZDE ANALİZİ:**\n"
                    f"```text\n{ai_result}\n```\n"
                    "⏱ **Analiz Zamanı:** Canlı (Anlık Veri)"
                )
            else:
                mesaj = "⚠️ Canlı piyasa verisi çekilirken bir sorun oluştu. Lütfen tekrar deneyin."

            sub_markup = InlineKeyboardMarkup()
            sub_markup.row_width = 2
            sub_markup.add(
                InlineKeyboardButton("🔄 Yeniden Tara (Canlı)", callback_data='bist'),
                InlineKeyboardButton("⭐ Önemli Hisseler", callback_data='bist_onemli')
            )
            bot.send_message(call.message.chat.id, mesaj, parse_mode="Markdown", reply_markup=sub_markup)

def run_bot():
    if bot:
        print("Telegram Bot Polling Başlatıldı!")
        bot.infinity_polling(none_stop=True)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
