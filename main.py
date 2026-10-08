import logging
import os
import sqlite3
import threading
from flask import Flask, request, jsonify
from telegram import Bot
import asyncio

# ============================================================
# TRADINGVIEW WEBHOOK RECEIVER BOT
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("WEBHOOK-BOT")

app = Flask(__name__)
bot = Bot(token=TOKEN)

def send_telegram_sync(text):
    """TradingView'den gelen sinyali Telegram'a iletir."""
    if not TOKEN or not CHAT_ID:
        logger.error("TOKEN veya CHAT_ID eksik!")
        return
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(bot.send_message(chat_id=CHAT_ID, text=text, parse_mode="Markdown"))
        loop.close()
    except Exception as e:
        logger.error(f"Telegram gönderme hatası: {e}")

@app.route("/", methods=["GET"])
def home():
    return "TradingView Webhook Listener Active", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """TradingView'den gelen anlık alarmları yakalar."""
    data = request.json or {}
    logger.info(f"Gelen Webhook Verisi: {data}")

    ticker = data.get("ticker", "BELİRSİZ")
    price = data.get("price", "0.0")
    message = data.get("message", "Canlı Alım Sinyali Geldi!")

    telegram_msg = (
        f"🚨 *CANLI TRADINGVIEW SİNYALİ* 🚨\n\n"
        f"📌 *Hisse:* #{ticker}\n"
        f"💵 *Anlık Fiyat:* {price} TL\n"
        f"📝 *Sinyal Detayı:* {message}\n\n"
        f"⚡ _Bu sinyal TradingView tarafından milisaniyesinde canlı olarak tetiklendi._"
    )

    # Arka planda Telegram'a mesaj at
    threading.Thread(target=send_telegram_sync, args=(telegram_msg,)).start()

    return jsonify({"status": "success"}), 200

def main():
    port = int(os.getenv("PORT", "10000"))
    logger.info(f"Server {port} portunda başlatılıyor...")
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
