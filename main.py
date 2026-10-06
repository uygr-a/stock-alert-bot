import os
import threading
import asyncio
import requests
import yfinance as yf
import pandas as pd
import numpy as np

from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Render Keep-Alive Web Sunucusu
flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "Hedge-Fund Grade Decision Engine Active!"

def run_flask():
    port = int(os.environ.get("PORT", 10000))
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")

BIST_TICKERS = [
    "THYAO.IS", "GARAN.IS", "ASELS.IS", "EREGL.IS", "AKBNK.IS", "ISCTR.IS", "KCHOL.IS",
    "SAHOL.IS", "TUPRS.IS", "BIMAS.IS", "SISE.IS", "PGSUS.IS", "TCELL.IS", "TTKOM.IS",
    "YKBNK.IS", "ARCLK.IS", "TOASO.IS", "FROTO.IS", "OYAKC.IS", "MGROS.IS"
]

def analyze_institutional_grade(symbol):
    try:
        session = requests.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0'})

        # 1. Veri Çekme (Günlük ve Haftalık)
        stock_daily = yf.Ticker(symbol, session=session).history(period="6mo", interval="1d")
        stock_weekly = yf.Ticker(symbol, session=session).history(period="1y", interval="1wk")
        bist100_daily = yf.Ticker("XU100.IS", session=session).history(period="6mo", interval="1d")

        if len(stock_daily) < 50 or len(stock_weekly) < 20 or len(bist100_daily) < 50:
            return None

        # Fiyat Bilgileri
        current_price = round(stock_daily['Close'].iloc[-1], 2)
        prev_price = stock_daily['Close'].iloc[-2]
        change_pct = round(((current_price - prev_price) / prev_price) * 100, 2)

        # Düşen trenddeki veya taban yapan hisseleri ele
        if change_pct < -2.0:
            return None

        score = 0
        reasons = []

        # --- KATMAN 1: HAFTALIK MAKTRO TREND ONAYI (25 Puan) ---
        w_ema9 = stock_weekly['Close'].ewm(span=9, adjust=False).mean().iloc[-1]
        w_ema21 = stock_weekly['Close'].ewm(span=21, adjust=False).mean().iloc[-1]
        if w_ema9 > w_ema21:
            score += 25
            reasons.append("Haftalık Makro Trend Pozitif (EMA 9/21)")

        # --- KATMAN 2: GÖRELİ GÜÇ - RS vs BIST100 (25 Puan) ---
        stock_perf_10d = (stock_daily['Close'].iloc[-1] - stock_daily['Close'].iloc[-10]) / stock_daily['Close'].iloc[-10]
        bist_perf_10d = (bist100_daily['Close'].iloc[-1] - bist100_daily['Close'].iloc[-10]) / bist100_daily['Close'].iloc[-10]
        if stock_perf_10d > bist_perf_10d:
            score += 25
            reasons.append("BIST 100 Endeksinden Güçlü (Relative Strength)")

        # --- KATMAN 3: KURUMSAL HACİM VE MUMBASKISI (25 Puan) ---
        vol_20_avg = stock_daily['Volume'].rolling(20).mean().iloc[-1]
        current_vol = stock_daily['Volume'].iloc[-1]
        is_green = stock_daily['Close'].iloc[-1] > stock_daily['Open'].iloc[-1]
        if (current_vol > vol_20_avg * 1.3) and is_green:
            score += 25
            reasons.append("Kurumsal Hacim Girişi (%30+ Hacim Artışı)")

        # --- KATMAN 4: İNDİKATÖR KONFETİSİ (RSI + MACD + EMA Cross) (25 Puan) ---
        # RSI
        delta = stock_daily['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = round((100 - (100 / (1 + rs))).iloc[-1], 1)

        # EMA Cross (Daily 10/30)
        ema10 = stock_daily['Close'].ewm(span=10, adjust=False).mean().iloc[-1]
        ema30 = stock_daily['Close'].ewm(span=30, adjust=False).mean().iloc[-1]

        # MACD
        ema12 = stock_daily['Close'].ewm(span=12, adjust=False).mean()
        ema26 = stock_daily['Close'].ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal_line = macd.ewm(span=9, adjust=False).mean()
        macd_bullish = macd.iloc[-1] > signal_line.iloc[-1]

        if (48 <= rsi <= 68) and (ema10 > ema30) and macd_bullish:
            score += 25
            reasons.append("RSI & MACD & EMA İdeal İvme Bölgesinde")

        # --- EŞİK DEĞERİ KONTROLÜ (En az 75 Puan Şartı) ---
        if score >= 75:
            # ATR İle Risk Hesaplama
            high_low = stock_daily['High'] - stock_daily['Low']
            high_close = np.abs(stock_daily['High'] - stock_daily['Close'].shift())
            low_close = np.abs(stock_daily['Low'] - stock_daily['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            atr = np.max(ranges, axis=1).rolling(14).mean().iloc[-1]

            stop_loss = round(current_price - (atr * 1.5), 2)
            take_profit = round(current_price + (atr * 3.0), 2)
            risk_pct = round(((current_price - stop_loss) / current_price) * 100, 1)
            reward_pct = round(((take_profit - current_price) / current_price) * 100, 1)

            grade = "👑 VIP YÜKSEK OLASILIKLI ALIM" if score == 100 else "⭐ GÜÇLÜ ALIM SİNYALİ"

            return {
                "symbol": symbol.replace('.IS', ''),
                "price": current_price,
                "change": change_pct,
                "score": score,
                "grade": grade,
                "rsi": rsi,
                "reasons": reasons,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "risk_pct": risk_pct,
                "reward_pct": reward_pct
            }
        return None

    except Exception:
        return None

def scan_bist_pro():
    results = []
    for ticker in BIST_TICKERS:
        res = analyze_institutional_grade(ticker)
        if res:
            results.append(res)
    # En yüksek puanlı hisseleri en üste koy
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

# --- INTERAKTİF ARAYÜZ ---
def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("🎯 Yüksek Olasılıklı VIP Tarama", callback_data="run_scan")],
        [InlineKeyboardButton("📊 BIST 100 Piyasa Rejimi", callback_data="bist_status")],
        [InlineKeyboardButton("🔍 Karar Algoritması Detayı", callback_data="about_strategy")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🏛️ *Hedge-Fund Karar Destek Sistemi Aktif!*\n\n"
        "Sistem, **Haftalık Trend Onayı**, **Endeks Göreli Gücü (RS)**, "
        "**Kurumsal Hacim** ve **Üçlü Onay Mekanizması** ile çalışır."
    )
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=get_main_keyboard())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "run_scan":
        await query.message.reply_text("🔬 *Çoklu Zaman Dilimi ve Risk Puanlaması Analizi Yapılıyor...*", parse_mode='Markdown')
        loop = asyncio.get_running_loop()
        signals = await loop.run_in_executor(None, scan_bist_pro)

        if not signals:
            await query.message.reply_text(
                "🛡️ *Piyasada 75+ Güven Puanını Aşan İdeal İşlem Bulunamadı.*\n\n"
                "Sistem hatalı/riskli pozisyon açmamak için **Nakit Pozisyonu** koruyor.",
                reply_markup=get_main_keyboard()
            )
            return

        for s in signals:
            reasons_str = "\n".join([f"• {r}" for r in s['reasons']])
            msg = (
                f"{s['grade']}\n"
                f"───────────────────\n"
                f"📌 *Hisse:* `{s['symbol']}` | *Güven Puanı:* `{s['score']}/100`\n"
                f"💵 *Fiyat:* `{s['price']} TL` (Günlük: %{s['change']})\n"
                f"📊 *RSI:* `{s['rsi']}`\n\n"
                f"📋 *Onay Veren Sinyaller:*\n{reasons_str}\n"
                f"───────────────────\n"
                f"🛑 *Zarar Kes (Stop-Loss):* `{s['stop_loss']} TL` (-%{s['risk_pct']})\n"
                f"🎯 *Hedef Fiyat (Take-Profit):* `{s['take_profit']} TL` (+%{s['reward_pct']})\n"
                f"⚖️ *Risk/Ödül Oranı:* `1 : 2` (Sıkı Risk Yönetimi)\n───────────────────"
            )
            await query.message.reply_text(msg, parse_mode='Markdown', reply_markup=get_main_keyboard())

    elif query.data == "bist_status":
        try:
            bist = yf.Ticker("XU100.IS").history(period="1mo")
            c_price = round(bist['Close'].iloc[-1], 2)
            p_price = round(bist['Close'].iloc[-2], 2)
            chg = round(((c_price - p_price)/p_price)*100, 2)
            
            status = "🟢 *BOĞA PİYASASI (Alım İştahı Yüksek)*" if chg > 0 else "🔴 *AYI / DÜZELTME PİYASASI (Risk Yüksek)*"
            
            msg = f"📈 *BIST 100 Güncel Durum*\n\nEndeks: `{c_price}` (%{chg})\nDurum: {status}"
            await query.message.reply_text(msg, parse_mode='Markdown', reply_markup=get_main_keyboard())
        except Exception:
            await query.message.reply_text("Endeks verisi çekilemedi.", reply_markup=get_main_keyboard())

    elif query.data == "about_strategy":
        info = (
            "🧠 *Karar Motoru Kriterleri (En Az 75/100 Puan Şartı):*\n\n"
            "1. *Haftalık Makro Trend (+25 Puan):* Hisse ana yönü yukarı olmalı.\n"
            "2. *Göreli Güç (+25 Puan):* BIST 100 düşse bile hisse endekse göre güçlü kalmalı.\n"
            "3. *Hacimli Alım (+25 Puan):* 20 günlük ortalama hacmin üzerinde yeşil mum olmalı.\n"
            "4. *İndikatör Uyum (+25 Puan):* RSI (48-68) ve MACD aynı anda 'AL' vermeli."
        )
        await query.message.reply_text(info, parse_mode='Markdown', reply_markup=get_main_keyboard())

if __name__ == '__main__':
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

    if TOKEN:
        app = Application.builder().token(TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CallbackQueryHandler(button_handler))

        print("Hedge-Fund VIP Botu Aktif!")
        app.run_polling(drop_pending_updates=True, close_loop=False)
