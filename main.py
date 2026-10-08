import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
import xml.etree.ElementTree as ET

from curl_cffi import requests as requests_cffi
import pandas as pd
import yfinance as yf
from flask import Flask
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ============================================================
# NEWS QUANT & SENTIMENT ENGINE (YAHOO FINANCE INTEGRATED)
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("NEWS-QUANT")

app = Flask(__name__)

@app.route("/")
def home():
    return "News Quant Engine Active", 200

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

session = requests_cffi.Session(impersonate="chrome110")

# OLUMLU / OLUMSUZ KELİME VERİ TABANI (SENTIMENT DICTIONARY)
POSITIVE_WORDS = [
    "profit", "growth", "record", "revenue", "agreement", "contract", "bull",
    "dividend", "surge", "up", "buy", "gain", "deal", "approval", "kar", "büyüme",
    "anlaşma", "ihale", "rekor", "temettü", "ortaklık", "onay", "yükseliş", "sözleşme"
]

NEGATIVE_WORDS = [
    "loss", "decline", "drop", "lawsuit", "fall", "down", "debt", "risk",
    "bankruptcy", "zarar", "düşüş", "dava", "borç", "iptal", "ceza", "soruşturma"
]

def analyze_sentiment(text: str) -> str:
    text_lower = text.lower()
    pos_score = sum(1 for word in POSITIVE_WORDS if word in text_lower)
    neg_score = sum(1 for word in NEGATIVE_WORDS if word in text_lower)

    if pos_score > neg_score:
        return "🟢 GÜÇLÜ OLUMLU"
    elif neg_score > pos_score:
        return "🔴 OLUMSUZ"
    else:
        return "⚪ NÖTR / BİLGİLENDİRME"

def fetch_yahoo_news():
    """Yahoo Finance RSS üzerinden en son BIST ve finans haberlerini çeker."""
    url = "https://news.google.com/rss/search?q=BIST+hisse+borsa&hl=tr&gl=TR&ceid=TR:tr"
    news_list = []
    
    try:
        resp = session.get(url, timeout=10)
        if resp.status_code == 200:
            root = ET.fromstring(resp.content)
            for item in root.findall(".//item")[:10]:
                title = item.find("title").text if item.find("title") is not None else ""
                pub_date_str = item.find("pubDate").text if item.find("pubDate") is not None else ""
                
                # Hisse sembolü ayıklama (Örn: THYAO, SASA, GARAN)
                match = re.search(r'\b([A-Z]{4,5})\b', title)
                ticker = match.group(1) if match else "BIST"

                sentiment = analyze_sentiment(title)
                
                news_list.append({
                    "title": title,
                    "ticker": ticker,
                    "pub_date": pub_date_str,
                    "sentiment": sentiment
                })
    except Exception as e:
        logger.error(f"Haber çekme hatası: {e}")

    return news_list

def get_stock_price_change(ticker: str):
    """Hissenin son fiyatını ve günlük değişimini getirir."""
    if ticker == "BIST":
        return "N/A", "%0.00"
    
    try:
        symbol = f"{ticker}.IS"
        data = yf.Ticker(symbol).history(period="2d")
        if len(data) >= 2:
            c_price = data["Close"].iloc[-1]
            p_price = data["Close"].iloc[-2]
            pct = ((c_price - p_price) / p_price) * 100.0
            return f"{c_price:.2f} TL", f"%{pct:+.2f}"
        elif len(data) == 1:
            c_price = data["Close"].iloc[-1]
            return f"{c_price:.2f} TL", "%0.00"
    except Exception:
        pass
    return "N/A", "%0.00"

def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔥 Önemliler", callback_data="btn_important"),
            InlineKeyboardButton("📰 Son Haberler", callback_data="btn_latest"),
        ],
        [
            InlineKeyboardButton("🚀 Haberli Hisseler", callback_data="btn_stocks"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 *FINANCIAL NEWS & SENTIMENT QUANT BOT* 🤖\n\n"
        "Yahoo Finance ve piyasa haber akışı anlık taranıyor.\n"
        "Aşağıdaki butonları kullanarak analizlere ulaşabilirsiniz:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    news_data = fetch_yahoo_news()

    if query.data == "btn_latest":
        response = "📰 *EN SON YAYINLANAN HABERLER*\n\n"
        for item in news_data[:5]:
            price, pct = get_stock_price_change(item["ticker"])
            response += (
                f"📌 *Hisse:* #{item['ticker']} ({price} | {pct})\n"
                f"📢 *Haber:* {item['title']}\n"
                f"🧠 *Analiz:* {item['sentiment']}\n"
                f"⏱️ *Yayınlanma:* Az Önce\n"
                "-----------------------------------\n"
            )
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif query.data == "btn_important":
        response = "🔥 *ÖNEMLİ VE OLUMLU HABERLER*\n\n"
        important_news = [n for n in news_data if "OLUMLU" in n["sentiment"]]
        
        if not important_news:
            response += "⚠️ Şu anda yüksek etkili olumlu haber tespit edilmedi."
        else:
            for item in important_news[:5]:
                price, pct = get_stock_price_change(item["ticker"])
                response += (
                    f"🔥 *Hisse:* #{item['ticker']} ({price} | {pct})\n"
                    f"📢 *Haber:* {item['title']}\n"
                    f"🧠 *Duygu Analizi:* {item['sentiment']}\n"
                    "-----------------------------------\n"
                )
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif query.data == "btn_stocks":
        response = "🚀 *HABER SONRASI HAREKETLENEN HİSSELER*\n\n"
        stocks_news = [n for n in news_data if n["ticker"] != "BIST"]
        
        if not stocks_news:
            response += "⚠️ Haber odaklı spesifik hisse tespiti yapılamadı."
        else:
            for item in stocks_news[:5]:
                price, pct = get_stock_price_change(item["ticker"])
                response += (
                    f"📌 *Hisse:* #{item['ticker']}\n"
                    f"💵 *Son Fiyat:* {price}\n"
                    f"📈 *Haber Sonrası/Günlük Değişim:* {pct}\n"
                    f"📢 *Haber:* {item['title'][:60]}...\n"
                    "-----------------------------------\n"
                )
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app_bot = Application.builder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Haber Botu Aktif.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
