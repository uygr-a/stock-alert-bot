import os
import telebot
import yfinance as yf
import feedparser
from urllib.parse import quote

# Render üzerindeki Telegram Bot Token'ı alıyoruz
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN çevre değişkeni bulunamadı!")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# BIST Hisseleri (Genişletilebilir Liste)
BIST_STOCKS = {
    "THYAO": "THYAO.IS",
    "GARAN": "GARAN.IS",
    "ASELS": "ASELS.IS",
    "EREGL": "EREGL.IS",
    "SASA": "SASA.IS",
    "KCHOL": "KCHOL.IS",
    "AKBNK": "AKBNK.IS",
    "TUPRS": "TUPRS.IS",
    "SISE": "SISE.IS",
    "BIMAS": "BIMAS.IS"
}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "📊 **BIST Hisse Analiz ve Haber Botuna Hoş Geldiniz!**\n\n"
        "Kullanabileceğiniz komutlar:\n"
        "🔹 `/hisse THYAO` - Anlık BIST hisse fiyatı ve teknik göstergeler\n"
        "🔹 `/haber THYAO` - Hisse hakkındaki son haberler\n"
        "🔹 `/bist` - Popüler BIST hisselerinin özet takibi"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown")

@bot.message_handler(commands=['hisse'])
def get_stock_info(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Lütfen bir hisse kodu girin. Örn: `/hisse THYAO`", parse_mode="Markdown")
            return

        symbol = args[1].upper().replace(".IS", "")
        ticker_symbol = f"{symbol}.IS"
        
        bot.reply_to(message, f"⏳ `{symbol}` için veriler çekiliyor...", parse_mode="Markdown")
        
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="5d")

        if hist.empty:
            bot.send_message(message.chat.id, f"❌ `{symbol}` için veri bulunamadı. Lütfen BIST kodunu doğru girdiğinizden emin olun.", parse_mode="Markdown")
            return

        last_price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else last_price
        change = ((last_price - prev_price) / prev_price) * 100
        
        high = hist['High'].iloc[-1]
        low = hist['Low'].iloc[-1]
        volume = hist['Volume'].iloc[-1]

        emoji = "🟢" if change >= 0 else "🔴"
        
        response = (
            f"📈 **BIST Hisse Analizi: {symbol}**\n\n"
            f"💵 **Son Fiyat:** {last_price:.2f} TL\n"
            f"{emoji} **Günlük Değişim:** %{change:.2f}\n"
            f"🔺 **En Yüksek:** {high:.2f} TL\n"
            f"🔻 **En Düşük:** {low:.2f} TL\n"
            f"📊 **Hacim:** {volume:,} adet"
        )
        bot.send_message(message.chat.id, response, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Veri alınırken bir hata oluştu: {str(e)}")

@bot.message_handler(commands=['haber'])
def get_stock_news(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "Lütfen haberini istediğiniz hisse kodunu girin. Örn: `/haber THYAO`", parse_mode="Markdown")
            return

        symbol = args[1].upper().replace(".IS", "")
        bot.reply_to(message, f"📰 `{symbol}` hakkındaki son haberler taranıyor...", parse_mode="Markdown")

        # Google News RSS üzerinden BIST haberi arama (Ücretsiz & Anahtarsız)
        query = quote(f"{symbol} hisse borsası")
        rss_url = f"https://news.google.com/rss/search?q={query}&hl=tr&gl=TR&ceid=TR:tr"
        feed = feedparser.parse(rss_url)

        if not feed.entries:
            bot.send_message(message.chat.id, f"ℹ️ `{symbol}` için güncel haber bulunamadı.", parse_mode="Markdown")
            return

        news_text = f"📰 **{symbol} Hakkındaki Son Haberler:**\n\n"
        for entry in feed.entries[:5]: # İlk 5 haberi alıyoruz
            news_text += f"▪️ [{entry.title}]({entry.link})\n\n"

        bot.send_message(message.chat.id, news_text, parse_mode="Markdown", disable_web_page_preview=True)

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Haberler çekilirken hata oluştu: {str(e)}")

@bot.message_handler(commands=['bist'])
def get_bist_summary(message):
    try:
        bot.reply_to(message, "📊 Popüler BIST hisseleri taranıyor, lütfen bekleyin...")
        summary = "🇹🇷 **Popüler BIST Hisseleri Özeti**\n\n"
        
        for name, ticker in BIST_STOCKS.items():
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty and len(hist) >= 2:
                last = hist['Close'].iloc[-1]
                prev = hist['Close'].iloc[-2]
                chg = ((last - prev) / prev) * 100
                emoji = "🟢" if chg >= 0 else "🔴"
                summary += f"{emoji} **{name}:** {last:.2f} TL ( %{chg:.2f} )\n"
            elif not hist.empty:
                last = hist['Close'].iloc[-1]
                summary += f"⚪ **{name}:** {last:.2f} TL\n"

        bot.send_message(message.chat.id, summary, parse_mode="Markdown")

    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Özet çekilirken hata oluştu: {str(e)}")

if __name__ == "__main__":
    print("Bot çalışıyor...")
    bot.infinity_polling()
