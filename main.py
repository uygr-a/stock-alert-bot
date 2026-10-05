import os
import threading
import requests
import yfinance as yf
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Render Port Kontrolü
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "BIST Sinyal Botu 7/24 Aktif!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

# BIST Hisseleri
STOCKS = ["THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "SASA.IS", "KCHOL.IS", "AKBNK.IS", "TUPRS.IS", "SISE.IS", "BIMAS.IS"]

def get_hisse_detay(ticker_symbol):
    try:
        # Engellemeleri aşmak için özel requests oturumu oluşturuyoruz
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        stock = yf.Ticker(ticker_symbol, session=session)
        hist = stock.history(period="5d")
        
        if len(hist) >= 2:
            prev_close = hist['Close'].iloc[-2]
            current_price = hist['Close'].iloc[-1]
            change = ((current_price - prev_close) / prev_close) * 100
            clean_symbol = ticker_symbol.replace('.IS', '')
            return {
                "symbol": clean_symbol,
                "price": round(current_price, 2),
                "change": round(change, 2)
            }
        elif len(hist) == 1:
            current_price = hist['Close'].iloc[-1]
            clean_symbol = ticker_symbol.replace('.IS', '')
            return {
                "symbol": clean_symbol,
                "price": round(current_price, 2),
                "change": 0.0
            }
    except Exception as e:
        print(f"Hata {ticker_symbol}: {e}")
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
    elif change < -1.5:
        action = "🔴 SAT (SELL) / İZLE"
        confidence = 80
        tp = round(price * 0.95, 2)
        sl = round(price * 1.02, 2)
        yorum = "Satış baskısı hakim. Destek seviyesine dikkat edilmeli."
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
        await update.message.reply_text("❌ Veri alınamadı. Lütfen birkaç saniye sonra tekrar deneyin.")
        return

    msg = "🚀 *BIST FIRSAT VE SİNYAL RAPORU*\n───────────────────\n\n"
    for f in fırsatlar:
        msg += f"📌 *{f['symbol']}* | Fiyat: `{f['price']} TL` (%{f['change']})\n"
        msg += f"🎯 *Sinyal:* {f['action']} (Güven: `%{f['confidence']}`)\n"
        msg += f"🎯 *Hedef (TP):* `{f['tp']} TL` | 🛑 *Stop (SL):* `{f['sl']} TL`\n"
        msg += f"💡 *Analiz:* _{f['yorum']}_\n───────────────────\n"

    await update.message.reply_text(msg, parse_mode='Markdown')

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    if not TOKEN:
        print("CRITICAL HATA: TELEGRAM_BOT_TOKEN ayarlanmamış!")
    else:
        print("Sinyal Botu Dinlemeye Başlıyor...")
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("bist", bist_fırsat_tara))
        app.add_handler(CommandHandler("start", bist_fırsat_tara))
        app.run_polling(drop_pending_updates=True, close_loop=False)
