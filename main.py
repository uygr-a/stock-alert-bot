import os
import threading
import asyncio
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Institutional Hedge-Fund Level BIST Scanner Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
USER_CHAT_ID = None

# Sadece Likit, Kurumsal ve Temeli Sağlam BIST Hisseleri
BIST_TICKERS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "AKBNK.IS", "ISCTR.IS", "KCHOL.IS",
    "SAHOL.IS", "TUPRS.IS", "BIMAS.IS", "SISE.IS", "PGSUS.IS", "TCELL.IS", "TTKOM.IS",
    "YKBNK.IS", "ARCLK.IS", "TOASO.IS", "FROTO.IS", "OYAKC.IS", "MGROS.IS"
]

def analyze_hedge_fund_grade(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})
        
        # Hisse ve Endeks Verisi (XU100 Göreli Güç İncelemesi İçin)
        stock_df = yf.Ticker(symbol, session=session).history(period="3mo", interval="1d")
        bist100_df = yf.Ticker("XU100.IS", session=session).history(period="3mo", interval="1d")

        if len(stock_df) < 30 or len(bist100_df) < 30:
            return None

        current_price = round(stock_df['Close'].iloc[-1], 2)
        prev_price = stock_df['Close'].iloc[-2]
        change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)

        # 1. TEMEL KORUMA: Düşen (%-2 üzeri) veya Taban Yapan Hisseler Doğrudan Elenir
        if change_pct < -2.0:
            return None

        # 2. GÖRELİ GÜÇ (Relative Strength vs BIST100)
        stock_perf = (stock_df['Close'].iloc[-1] - stock_df['Close'].iloc[-5]) / stock_df['Close'].iloc[-5]
        bist_perf = (bist100_df['Close'].iloc[-1] - bist100_df['Close'].iloc[-5]) / bist100_df['Close'].iloc[-5]
        outperforming_index = stock_perf > bist_perf  # Hisse endeksten daha güçlü mü?

        # 3. RSI VE ATR (Atr tabanlı Stop-Loss/Hedef Fiyat için)
        delta = stock_df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rsi = 100 - (100 / (1 + (gain / loss)))
        current_rsi = round(rsi.iloc[-1], 1)

        # True Range & ATR (Volatillik & Stop Mesafesi)
        high_low = stock_df['High'] - stock_df['Low']
        high_close = np.abs(stock_df['High'] - stock_df['Close'].shift())
        low_close = np.abs(stock_df['Low'] - stock_df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr = true_range.rolling(14).mean().iloc[-1]

        # 4. HACİM VE YEŞİL MUM ONAYI
        vol_15_avg = stock_df['Volume'].rolling(15).mean().iloc[-1]
        current_vol = stock_df['Volume'].iloc[-1]
        is_green_candle = stock_df['Close'].iloc[-1] > stock_df['Open'].iloc[-1]
        institutional_volume = (current_vol > vol_15_avg * 1.3) and is_green_candle

        # 5. HAREKETLİ ORTALAMALAR (SMA 5, 20, 50)
        sma5 = stock_df['Close'].rolling(5).mean().iloc[-1]
        sma20 = stock_df['Close'].rolling(20).mean().iloc[-1]
        sma50 = stock_df['Close'].rolling(50).mean().iloc[-1]

        # 6. MACD ONAYI
        ema12 = stock_df['Close'].ewm(span=12, adjust=False).mean()
        ema26 = stock_df['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9, adjust=False).mean()
        macd_bullish = macd.iloc[-1] > signal_line.iloc[-1]

        signal = None
        reason = ""

        # --- KURUMSAL ALIM FİLTRESİ ---
        # Fiyat > SMA20, MACD Pozitif, Hacimli Yeşil Mum, Endeksten Güçlü
        if current_price > sma5 and current_price > sma20 and institutional_volume and macd_bullish and outperforming_index:
            signal = "💎 KURUMSAL VIP AL (TREND + HACİM + ENDEKS ÜSTÜ)"
            reason = f"BIST100'den Güçlü Performans + Kurumsal Hacimli Yeşil Mum + Trend Kesişimi"

        elif current_rsi < 38 and institutional_volume and is_green_candle:
            signal = "🎯 DİPTEN AKILLI TEPKİ ALIMI"
            reason = f"RSI Dip Bölgesinde ({current_rsi}) + Hacimli Para Girişi Mumu Pozitif"

        if signal:
            # Dinamik Stop-Loss ve Hedef Fiyat Hesaplama (1:2 Risk/Ödül Oranı)
            stop_loss = round(current_price - (atr * 1.5), 2)
            take_profit = round(current_price + (atr * 3.0), 2)
            risk_pct = round(((current_price - stop_loss) / current_price) * 100, 1)
            reward_pct = round(((take_profit - current_price) / current_price) * 100, 1)

            return {
                "symbol": symbol.replace('.IS', ''),
                "price": current_price,
                "change": change_pct,
                "rsi": current_rsi,
                "signal": signal,
                "reason": reason,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_pct": risk_pct,
                "reward_pct": reward_pct
            }
        return None

    except Exception as e:
        return None

def scan_bist_pro():
    results = []
    for ticker in BIST_TICKERS:
        res = analyze_hedge_fund_grade(ticker)
        if res:
            results.append(res)
    return results

# --- TELEGRAM KOMUTLARI ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    msg = (
        "🏛️ *Hedge-Fund Seviyesi BIST Analiz Botu Aktif!*\n\n"
        "Sistem Endeks Göreli Gücü, ATR Stop-Loss / Hedef Fiyat ve Kurumsal Hacim Onayı ile çalışır.\n\n"
        "🔍 *Anlık Tarama:* /tarama"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def tarama_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    
    await update.message.reply_text("🔎 *BIST Kurumsal VIP Filtrelerle Taranıyor...*", parse_mode='Markdown')
    
    loop = asyncio.get_running_loop()
    signals = await loop.run_in_executor(None, scan_bist_pro)
    
    if not signals:
        await update.message.reply_text("📌 *Şu anda riski düşük, Kurumsal/VIP kriterleri karşılayan alım fırsatı bulunamadı.* Piyasa izlemede.")
        return

    for s in signals:
        msg = (
            f"🏆 *VIP BİST SİNYALİ*\n───────────────────\n"
            f"📌 *Hisse:* `{s['symbol']}`\n"
            f"💵 *Fiyat:* `{s['price']} TL` (Günlük: %{s['change']})\n"
            f"📊 *RSI:* `{s['rsi']}`\n"
            f"🎯 *Karar:* *{s['signal']}*\n"
            f"💡 *Neden:* _{s['reason']}_\n"
            f"───────────────────\n"
            f"🛑 *Stop-Loss (Zarar Kes):* `{s['stop_loss']} TL` (-%{s['risk_pct']})\n"
            f"🎯 *Hedef Fiyat (Kâr Al):* `{s['take_profit']} TL` (+%{s['reward_pct']})\n"
            f"⚖️ *Risk/Ödül Oranı:* `1 : 2` (Optimum)\n───────────────────"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("tarama", tarama_command))
        
        scheduler = BackgroundScheduler()
        scheduler.add_job(func=lambda: auto_scan_job(app), trigger="interval", minutes=15)
        scheduler.start()
        
        print("Hedge-Fund seviye bot aktif!")
        app.run_polling(drop_pending_updates=True, close_loop=False)
