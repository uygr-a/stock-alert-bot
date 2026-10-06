import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf
from flask import Flask
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ============================================================
# AYARLAR (GÜNCELLENDİ)
# ============================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

PORTFOLIO_SIZE = float(os.getenv("PORTFOLIO_SIZE", "100000"))
RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", "0.005"))

# Erken sinyal yakalamak için skor limiti 65'e çekildi
MIN_SCORE = int(os.getenv("MIN_SCORE", "65"))

SCAN_MINUTES = int(os.getenv("SCAN_MINUTES", "15"))
COOLDOWN_HOURS = int(os.getenv("COOLDOWN_HOURS", "6"))
MIN_DAILY_VALUE = float(os.getenv("MIN_DAILY_VALUE", "15000000"))

# Maksimum İzin Verilen Günlük Prim (%2.5 üzerini bot almaz)
MAX_DAILY_CHANGE_PCT = 2.5 

DB_FILE = "bist_bot.db"


# ============================================================
# LOG
# ============================================================

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("BIST-BOT")


# ============================================================
# BIST HİSSE LİSTESİ (530+ HİSSE)
# ============================================================

TICK
