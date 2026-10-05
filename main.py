import os
import threading
import requests
from bs4 import BeautifulSoup
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Render Port Kontrolü İçin Flask Web Sunucusu
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "BIST Sinyal Botu 7/24 Aktif!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host='0.0.0.0', port=port)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
STOCKS = ["THYAO", "GARAN", "ASELS", "EREGL", "SASA", "KCHOL", "AKBNK", "TUPRS", "SISE", "BIMAS"]

def get_hisse_detay(symbol):
    try:
        url = f"https://m.doviz.com/hisse-senetleri/{symbol.lower()}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            soup = BeautifulSoup(res.content, 'html.parser')
            price_elem = soup.find('div', {'data-socket-key': symbol.lower(), 'data-socket-attr': 's'})
            change_elem = soup.find('div', {'data-socket-key': symbol.lower(), 'data-socket-attr': 'c'})
            price = float(price_elem.text.strip().replace('.', '').replace(',', '.')) if price_elem else 0.0
            change = float(change_elem.text.strip().replace('%', '').replace(',', '.')) if change_elem else 0.0
            return {"symbol": symbol, "price": price, "change": change}
    except Exception as e:
        print(f"Hata {symbol}: {e}")
    return None

def hisse_analiz_et(data):
    price = data["price"]
    change = data["change"]
    symbol = data["symbol"]
    
    if change > 1.5:
        action = "🟢 AL (BUY)"
        confidence = min(70 + int(change * 5), 92)
        tp = round(price * 1.05, 2)
        sl = round(price * 0.97, 2)
        yorum = "Kuvvetli alım hacmi ve pozitif momentum tespit edildi."
    elif change < -2.0:
        action = "🔴 SAT (SELL) / İZLE"
        confidence = 80
        tp = round(price * 0.95, 2)
        sl = round(price * 1.02, 2)
        yorum = "Sert satış baskısı var. Destek seviyesine dikkat edilmeli."
    else:
        action = "🟡 NÖTR / BEKLE"
        confidence = 55
        tp = round(price * 1.02, 2)
        sl = round(price * 0.98, 2)
        yorum = "Yatay seyir hakim. Belirgin kırılım bekleniyor."

    return {
        "symbol": symbol, "price": price, "change": change,
        "action": action, "confidence": confidence, "tp": tp, "sl": sl, "yorum": yorum
    }

async def bist_fırsat_tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 *BIST Hisseleri Taranıyor ve Sinyal Analizi Yapılıyor...*", parse_mode='Markdown')
    fırsatlar = []
    for symbol in STOCKS:
        data = get_hisse_detay(symbol)
        if data and data["price"] > 0:
            fırsatlar.append(hisse_analiz_et(data))
    
    if not fırsatlar:
        await update.message.reply_text("❌ Veri alınamadı.")
        return

    msg = "🚀 *BIST FIRSAT VE SİNYAL RAPORU*\n───────────────────\n\n"
    for f in fırsatlar:
        msg += f"📌 *{f['symbol']}* | Fiyat: `{f['price']} TL` (%{f['change']})\n"
        msg += f"🎯 *Sinyal:* {f['action']} (Güven: `%{f['confidence']}`)\n"
        msg += f"🎯 *Hedef (TP):* `{f['tp']} TL` | 🛑 *Stop (SL):* `{f['sl']} TL`\n"
        msg += f"💡 *Analiz:* _{f['yorum']}_\n───────────────────\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

def main():
    # Flask sunucusunu arka planda başlat
    threading.Thread(target=run_flask, daemon=True).start()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("bist", bist_fırsat_tara))
    app.add_handler(CommandHandler("start", bist_fırsat_tara))
    print("Sinyal Botu Aktif...")
    app.run_polling()

if __name__ == '__main__':
    main()
