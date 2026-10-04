import os
import time
import telebot
from telebot import types
import yfinance as yf
import google.generativeai as genai
import feedparser

# Bot ve API Tanımlamaları
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

bot = telebot.TeleBot(TOKEN)

# Gemini AI Yapılandırması
gemini_model = None
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    try:
        gemini_model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception:
        gemini_model = genai.GenerativeModel('gemini-pro')

# --- HİSSE HAVUZU ---
BIST_HISSELERI = [
    "THYAO.IS", "GARAN.IS", "EREGL.IS", "AKBNK.IS", "ISCTR.IS",
    "SAHOL.IS", "KCHOL.IS", "ASELS.IS", "SISE.IS", "TUPRS.IS",
    "BIMAS.IS", "EKGYO.IS", "KRDMD.IS", "HEKTS.IS", "SASA.IS",
    "KONTR.IS", "ASTOR.IS", "EUPWR.IS", "ALARK.IS", "ODAS.IS"
]

ABD_HISSELERI = [
    "AAPL", "NVDA", "TSLA", "MSFT", "AMZN",
    "GOOGL", "META", "AMD", "NFLX", "INTC"
]

def get_live_price_data(symbol):
    """Anlık fiyat ve teknik destek/direnç verisi çeker."""
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info
        last_price = info.get('lastPrice', 0.0)
        prev_close = info.get('previousClose', 0.0)
        
        if last_price == 0.0 or prev_close == 0.0:
            return None
            
        change = ((last_price - prev_close) / prev_close) * 100
        return {
            "price": round(last_price, 2),
            "change": round(change, 2),
            "support": round(last_price * 0.95, 2), # %5 Stop Seviyesi
            "resistance": round(last_price * 1.08, 2) # %8 Hedef Seviye
        }
    except Exception as e:
        print(f"Fiyat çekilemedi ({symbol}): {e}")
        return None

def fetch_latest_news(symbol, pazar="BIST"):
    """Hisseye ait en son haber başlığını yakalar."""
    try:
        clean_symbol = symbol.replace('.IS', '')
        if pazar == "BIST":
            rss_url = f"https://news.google.com/rss/search?q={clean_symbol}+hisse+anlasma+kap+borsa&hl=tr&gl=TR&ceid=TR:tr"
        else:
            rss_url = f"https://news.google.com/rss/search?q={clean_symbol}+stock+news+contract+earnings&hl=en-US&gl=US&ceid=US:en"
            
        feed = feedparser.parse(rss_url)
        if feed.entries:
            return feed.entries[0].title
        return f"{clean_symbol} için son dönemde kritik yeni gelişme veya haber bulunamadı."
    except Exception as e:
        print(f"Haber çekme hatası ({symbol}): {e}")
        return "Canlı haber akışı alınamadı."

def deep_gemini_analysis(symbol, price_data, news_title, pazar="BIST"):
    """Gemini AI ile Derin Fırsat ve Anlaşma/Haber Etki Analizi Yaparak Sinyal Üretir."""
    if not gemini_model:
        return "⚠️ AI Analiz Motoru Bağlanamadı."

    para = "TL" if pazar == "BIST" else "USD"
    clean_symbol = symbol.replace('.IS', '')

    prompt = f"""
    Sen dünyaca ünlü, fon yöneten kıdemli bir Borsa Analistisiniz.
    Görevin: Aşağıda verilen haber ve fiyat verisine göre yatırımcıya Anlık Fırsat Sinyali üretmek.

    Pazar: {pazar}
    Hisse: #{clean_symbol}
    Mevcut Fiyat: {price_data['price']} {para} (Günlük Değişim: %{price_data['change']})
    Son Yakalanan Haber/Anlaşma: "{news_title}"

    Lütfen bu haberi derinlemesine değerlendir ve tam olarak aşağıdaki ŞABLONA uygun analiz üret:

    🚨 SİNYAL: [GÜÇLÜ AL / AL / PAS / SAT]
    📰 HABER ETKİSİ: [Çok Olumlu / Olumlu / Nötr / Olumsuz]
    🚀 YÜKSELİŞ POTANSİYELİ: [Örn: %6.5]
    🛡 AI GÜVEN SKORU: [Örn: %88]
    📍 HEDEF FİYAT (TP): [Fiyat] {para}
    🛑 STOP-LOSS (SL): [Fiyat] {para}
    
    💡 NEDEN BU SİNYAL (ÖZET ANALİZ):
    [Haberin hisseye/şirket bilançosuna ve fiyatına olası etkisini 2-3 cümleyle net açıkla.]
    """

    try:
        response = gemini_model.generate_content(prompt)
        if response and hasattr(response, 'text') and response.text:
            return response.text.strip()
        return "⚠️ Gemini AI Analizi tam üretemedi."
    except Exception as e:
        print(f"Gemini Hata ({symbol}): {e}")
        return f"⚠️ AI Analiz Hatası: {e}"

# --- TELEGRAM MENÜSÜ ---
def main_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_bist = types.InlineKeyboardButton("🇹🇷 BIST Haber & Fırsat Tara", callback_data="tara_bist")
    btn_abd = types.InlineKeyboardButton("🇺🇸 ABD Haber & Fırsat Tara", callback_data="tara_abd")
    markup.add(btn_bist, btn_abd)
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "🔥 **Borsa Anlık Haber & AI Fırsat Yakalayıcıya Hoş Geldiniz!**\n\n"
        "Aşağıdaki butonları kullanarak BIST veya ABD hisselerinde **son haberleri, anlaşmaları ve AI destekli AL/SAT/TP/SL fırsatlarını** anında tarayabilirsiniz:",
        reply_markup=main_keyboard(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_listener(call):
    if call.data == "tara_bist":
        bot.answer_callback_query(call.id, "🇹🇷 BIST Haber ve Fırsat Taraması Başladı...")
        bot.send_message(call.message.chat.id, "⚡ **BIST Hisseleri ve Canlı Haber Akışı Taranıyor...**")
        
        for symbol in BIST_HISSELERI:
            price_data = get_live_price_data(symbol)
            if price_data:
                news = fetch_latest_news(symbol, pazar="BIST")
                ai_analysis = deep_gemini_analysis(symbol, price_data, news, pazar="BIST")
                clean_symbol = symbol.replace('.IS', '')
                
                msg = (
                    f"📊 **#{clean_symbol} BIST CANLI FIRSAT KART**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 **Fiyat:** {price_data['price']} TL (Günlük: %{price_data['change']})\n"
                    f"📣 **Son Haber:** {news}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 **GEMINI AI DERİN DERECELENDİRME:**\n\n"
                    f"{ai_analysis}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏰ **Tarih:** Canlı Piyasa Verisi"
                )
                bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
                time.sleep(1) # Telegram spam engelleyici
                
    elif call.data == "tara_abd":
        bot.answer_callback_query(call.id, "🇺🇸 ABD Borsası Fırsat Taraması Başladı...")
        bot.send_message(call.message.chat.id, "⚡ **ABD Borsası (Nasdaq / S&P 500) Haberleri Taranıyor...**")
        
        for symbol in ABD_HISSELERI:
            price_data = get_live_price_data(symbol)
            if price_data:
                news = fetch_latest_news(symbol, pazar="ABD")
                ai_analysis = deep_gemini_analysis(symbol, price_data, news, pazar="ABD")
                
                msg = (
                    f"🇺🇸 **#{symbol} ABD BORSASI FIRSAT KARTI**\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"💰 **Fiyat:** {price_data['price']} USD (Günlük: %{price_data['change']})\n"
                    f"📣 **Son Haber:** {news}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🤖 **GEMINI AI DERİN DERECELENDİRME:**\n\n"
                    f"{ai_analysis}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏰ **Tarih:** Canlı Piyasa Verisi"
                )
                bot.send_message(call.message.chat.id, msg, parse_mode="Markdown")
                time.sleep(1)

if __name__ == "__main__":
    bot.polling(none_stop=True)
