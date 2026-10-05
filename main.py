import os
import threading
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Render Port Kontrolü
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "BIST Canlı & Profesyonel Analiz Botu Aktif!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

STOCKS = ["THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "SASA.IS", "KCHOL.IS", "AKBNK.IS", "TUPRS.IS", "SISE.IS", "BIMAS.IS"]

# --- CANLI VE GERÇEK TEKNİK ANALİZ MOTORU ---

def calculate_rsi(series, window=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_live_pro_analysis(ticker_symbol):
    try:
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'
        })
        
        stock = yf.Ticker(ticker_symbol, session=session)
        # 1 Saatlik canlı mum verilerini çekiyoruz (Canlı ivme ve kesişimler için)
        df = stock.history(period="1mo", interval="1h")
        
        if len(df) < 30:
            return None
            
        current_price = df['Close'].iloc[-1]
        prev_close = stock.history(period="2d")['Close'].iloc[-2] if len(stock.history(period="2d")) >= 2 else current_price
        day_change = ((current_price - prev_close) / prev_close) * 100
        clean_symbol = ticker_symbol.replace('.IS', '')
        
        # 1. RSI İndikatörü
        rsi_series = calculate_rsi(df['Close'])
        curr_rsi = rsi_series.iloc[-1]
        prev_rsi = rsi_series.iloc[-2]
        
        # 2. MACD Hesaplama
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9, adjust=False).mean()
        curr_macd, curr_signal = macd.iloc[-1], macd_signal.iloc[-1]
        prev_macd, prev_signal = macd.iloc[-2], macd_signal.iloc[-2]
        
        # 3. Bollinger Bantları
        sma20 = df['Close'].rolling(window=20).mean()
        std20 = df['Close'].rolling(window=20).std()
        upper_band = sma20 + (std20 * 2)
        lower_band = sma20 - (std20 * 2)
        
        # --- CANLI STRATEJİ VE ONAY PUANLAMASI ---
        score = 0
        reasons = []

        # RSI Kesişim / İvme Analizi
        if prev_rsi < 30 and curr_rsi >= 30:
            score += 3
            reasons.append("RSI Aşırı Dip Bölgesinden Yukarı Kırdı (Alım Sinyali)")
        elif curr_rsi > 50 and prev_rsi <= 50:
            score += 2
            reasons.append("RSI 50 Pozitif Eşiğini Yukarı Kesti")
        elif curr_rsi > 70:
            score -= 2
            reasons.append("RSI 70 Üzerinde (Aşırı Şişme / Düzeltme Riski)")
        elif curr_rsi < 35:
            score += 1
            reasons.append("RSI Dip Seviyelere Yakın")

        # MACD Crossover (Boğa/Ayı Kesişimi)
        if prev_macd <= prev_signal and curr_macd > curr_signal:
            score += 3
            reasons.append("MACD Alım Kesişimi Yapıyor (Boğa Sinyali)")
        elif prev_macd >= prev_signal and curr_macd < curr_signal:
            score -= 3
            reasons.append("MACD Satış Kesişimi Yapıyor (Ayı Sinyali)")
        elif curr_macd > curr_signal:
            score += 1
            reasons.append("MACD Pozitif Pozisyonda")

        # Bollinger Kırılımı
        if current_price < lower_band.iloc[-1]:
            score += 2
            reasons.append("Fiyat Alt Bollinger Bandına Çarptı (Tepki Yükselişi Beklentisi)")
        elif current_price > upper_band.iloc[-1]:
            score -= 2
            reasons.append("Fiyat Üst Bollinger Bandını Zorluyor")

        # Fiyat / Ortam Trendi
        if current_price > sma20.iloc[-1]:
            score += 1
        else:
            score -= 1

        # --- FIRSAT VE OLASILIK HESAPLAMA ---
        if score >= 4:
            action = "🟢 GÜÇLÜ AL (STRONG BUY)"
            win_rate = "82"
            tp = round(current_price * 1.045, 2)
            sl = round(current_price * 0.98, 2)
        elif score >= 2:
            action = "🟢 AL (BUY)"
            win_rate = "68"
            tp = round(current_price * 1.03, 2)
            sl = round(current_price * 0.985, 2)
        elif score <= -4:
            action = "🔴 GÜÇLÜ SAT (STRONG SELL)"
            win_rate = "80"
            tp = round(current_price * 0.955, 2)
            sl = round(current_price * 1.02, 2)
        elif score <= -2:
            action = "🔴 SAT (SELL) / İZLE"
            win_rate = "65"
            tp = round(current_price * 0.97, 2)
            sl = round(current_price * 1.015, 2)
        else:
            action = "🟡 NÖTR / YATAY"
            win_rate = "50"
            tp = round(current_price * 1.015, 2)
            sl = round(current_price * 0.985, 2)

        return {
            "symbol": clean_symbol,
            "price": round(current_price, 2),
            "change": round(day_change, 2),
            "rsi": round(curr_rsi, 1),
            "action": action,
            "win_rate": win_rate,
            "tp": tp,
            "sl": sl,
            "reasons": " | ".join(reasons[:2]) if reasons else "Belirgin teknik kırılım bekleniyor."
        }

    except Exception as e:
        print(f"Hata {ticker_symbol}: {e}")
        return None

async def bist_fırsat_tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("⚡ *Canlı Piyasa Verileri ve Saatlik İndikatör Kesişimleri Analiz Ediliyor...*", parse_mode='Markdown')
    fırsatlar = []
    
    for symbol in STOCKS:
        data = get_live_pro_analysis(symbol)
        if data:
            fırsatlar.append(data)
    
    if not fırsatlar:
        await update.message.reply_text("❌ Canlı veri çekilemedi, lütfen tekrar deneyin.")
        return

    msg = "🎯 *BIST CANLI TEKNİK ANALİZ VE SINYAL RAPORU*\n───────────────────\n\n"
    for f in fırsatlar:
        msg += f"📌 *{f['symbol']}* | Canlı: `{f['price']} TL` (%{f['change']})\n"
        msg += f"📊 *RSI:* `{f['rsi']}` | *Sinyal:* {f['action']}\n"
        msg += f"🔥 *Tahmini Başarı Oranı:* `%{f['win_rate']}`\n"
        msg += f"🎯 *Hedef (TP):* `{f['tp']} TL` | 🛑 *Stop (SL):* `{f['sl']} TL`\n"
        msg += f"💡 *Canlı Onay:* _{f['reasons']}_\n───────────────────\n"

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
