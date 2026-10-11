import logging
import os
import re
import sqlite3
import threading
import xml.etree.ElementTree as ET
from datetime import datetime

from curl_cffi import requests as requests_cffi
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
# FREE NEWS & KAP SENTIMENT QUANT ENGINE (STABLE)
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DB_FILE = "news_bot.db"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("FREE-NEWS-QUANT")

app = Flask(__name__)

@app.route("/")
def home():
    return "Free News & KAP Sentiment Quant Engine Active", 200

def run_flask():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

session = requests_cffi.Session(impersonate="chrome110")

# ============================================================
# 1. SQLITE VERİTABANI VE TEKRAR ENGELLEME YÖNETİMİ
# ============================================================
db_lock = threading.Lock()

def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_news (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                news_title TEXT UNIQUE NOT NULL,
                ticker TEXT,
                sentiment TEXT,
                initial_price TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        conn.close()

def is_news_processed(title: str) -> bool:
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_news WHERE news_title = ?", (title,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

def save_news_to_db(title: str, ticker: str, sentiment: str, price: str):
    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        try:
            conn.execute(
                "INSERT OR IGNORE INTO processed_news (news_title, ticker, sentiment, initial_price, created_at) VALUES (?, ?, ?, ?, ?)",
                (title, ticker, sentiment, price, datetime.now().isoformat())
            )
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

# ============================================================
# 2. FIYAT VE HİSSE AYRIŞTIRMA MOTORU (YFINANCE)
# ============================================================
def get_stock_price(ticker: str):
    if not ticker or ticker == "BIST":
        return "N/A", "%0.00"
    try:
        symbol = f"{ticker}.IS"
        data = yf.Ticker(symbol).history(period="2d", timeout=3)
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

# ============================================================
# 3. YEREL DUYGU ANALİZİ (SENTIMENT ENGINE)
# ============================================================
POSITIVE_KEYWORDS = [
    "profit", "growth", "record", "revenue", "agreement", "contract", "bull",
    "dividend", "surge", "up", "buy", "gain", "deal", "approval", "kar", "büyüme",
    "anlaşma", "ihale", "rekor", "temettü", "ortaklık", "onay", "yükseliş", "sözleşme",
    "ihale kazandı", "sermaye artırımı", "başvuru"
]

NEGATIVE_KEYWORDS = [
    "loss", "decline", "drop", "lawsuit", "fall", "down", "debt", "risk",
    "bankruptcy", "zarar", "düşüş", "dava", "borç", "iptal", "ceza", "soruşturma",
    "istifa", "istifa etti", "açığa satış"
]

def analyze_sentiment(text: str) -> str:
    text_lower = text.lower()
    pos_score = sum(1 for word in POSITIVE_KEYWORDS if word in text_lower)
    neg_score = sum(1 for word in NEGATIVE_KEYWORDS if word in text_lower)

    if pos_score > neg_score:
        return "🟢 GÜÇLÜ OLUMLU"
    elif neg_score > pos_score:
        return "🔴 OLUMSUZ"
    else:
        return "⚪ NÖTR / BİLGİLENDİRME"

# ============================================================
# 4. HABER VE KAP RSS KAYNAKLARI
# ============================================================
def fetch_all_financial_news():
    feeds = [
        "https://news.google.com/rss/search?q=BIST+hisse+borsa&hl=tr&gl=TR&ceid=TR:tr",
        "https://news.google.com/rss/search?q=KAP+bildirimi+hisse&hl=tr&gl=TR&ceid=TR:tr"
    ]
    
    for feed_url in feeds:
        try:
            resp = session.get(feed_url, timeout=8)
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.findall(".//item")[:10]:
                    title = item.find("title").text if item.find("title") is not None else ""
                    
                    match = re.search(r'\b([A-Z]{4,5})\b', title)
                    ticker = match.group(1) if match else "BIST"

                    if not is_news_processed(title):
                        price, _ = get_stock_price(ticker)
                        sentiment = analyze_sentiment(title)
                        save_news_to_db(title, ticker, sentiment, price)
        except Exception as e:
            logger.error(f"RSS çekme hatası: {e}")

# ============================================================
# 5. TELEGRAM BUTONLARI VE ARAYÜZ
# ============================================================
def get_main_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔥 Önemli & Olumlu", callback_data="btn_important"),
            InlineKeyboardButton("📰 Son Akış", callback_data="btn_latest"),
        ],
        [
            InlineKeyboardButton("🚀 Şirket / Hisse Haberleri", callback_data="btn_stocks"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Komut geldiğinde arka planda hemen haberleri tazele
    threading.Thread(target=fetch_all_financial_news, daemon=True).start()
    
    msg = (
        "🤖 *ÜCRETSİZ HABER & KAP SENTIMENT QUANT BOT* 🤖\n\n"
        "Yahoo Finance & KAP akışları taranıyor, yerel yapay zekâ duygu analizi ve SQLite filtrelemesi devrede.\n\n"
        "Aşağıdaki butonları kullanarak analizlere ulaşabilirsiniz:"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Butona basıldığında güncel haberleri çek
    fetch_all_financial_news()

    with db_lock:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT news_title, ticker, sentiment, initial_price, created_at FROM processed_news ORDER BY id DESC LIMIT 15")
        rows = cursor.fetchall()
        conn.close()

    if query.data == "btn_latest":
        response = "📰 *EN SON YAYINLANAN HABERLER & KAP AKIŞI*\n\n"
        if not rows:
            response += "⚠️ Henüz yeni haber taranmadı."
        else:
            for r in rows[:5]:
                title, ticker, sentiment, init_price, _ = r
                curr_price, pct = get_stock_price(ticker)
                response += (
                    f"📌 *Hisse:* #{ticker} | *Anlık:* {curr_price} ({pct})\n"
                    f"📢 *Haber/KAP:* {title}\n"
                    f"🧠 *Analiz:* {sentiment}\n"
                    f"💵 *Haber Anındaki Fiyat:* {init_price}\n"
                    "-----------------------------------\n"
                )
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif query.data == "btn_important":
        response = "🔥 *ÖNEMLİ VE OLUMLU HABERLER*\n\n"
        important_rows = [r for r in rows if "OLUMLU" in r[2]]
        
        if not important_rows:
            response += "⚠️ Şu anda yüksek etkili olumlu haber bulunmuyor."
        else:
            for r in important_rows[:5]:
                title, ticker, sentiment, init_price, _ = r
                curr_price, pct = get_stock_price(ticker)
                response += (
                    f"🔥 *Hisse:* #{ticker} | *Anlık:* {curr_price} ({pct})\n"
                    f"📢 *Haber:* {title}\n"
                    f"🧠 *Analiz:* {sentiment}\n"
                    f"💵 *Haber Anındaki Fiyat:* {init_price}\n"
                    "-----------------------------------\n"
                )
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

    elif query.data == "btn_stocks":
        response = "🚀 *ŞİRKET ODAKLI HİSSE HABERLERİ*\n\n"
        stock_rows = [r for r in rows if r[1] != "BIST"]
        
        if not stock_rows:
            response += "⚠️ Şirket kodlu spesifik haber bulunamadı."
        else:
            for r in stock_rows[:5]:
                title, ticker, sentiment, init_price, _ = r
                curr_price, pct = get_stock_price(ticker)
                response += (
                    f"📌 *Hisse:* #{ticker} | *Anlık Fiyat:* {curr_price} ({pct})\n"
                    f"🧠 *Analiz:* {sentiment}\n"
                    f"📢 *İçerik:* {title[:70]}...\n"
                    "-----------------------------------\n"
                )
        await query.edit_message_text(response, parse_mode="Markdown", reply_markup=get_main_keyboard())

def main():
    if not TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN ayarlanmamış!")

    init_db()

    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app_bot = Application.builder().token(TOKEN).build()

    app_bot.add_handler(CommandHandler("start", start_cmd))
    app_bot.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Ücretsiz Haber & KAP Botu Başlatıldı.")
    app_bot.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
