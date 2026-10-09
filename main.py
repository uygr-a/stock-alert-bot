
import re

POSITIVE_WORDS = [
    "kârını artırdı", "karını artırdı", "kâr artışı", "kar artışı",
    "gelirini artırdı", "rekor kâr", "rekor kar", "temettü",
    "bedelsiz", "geri alım", "yeni sözleşme", "ihale kazandı",
    "kapasite artışı", "olumlu", "güçlü büyüme", "hedef fiyat yükseldi",
    "profit increased", "revenue growth", "beats expectations",
    "upgrade", "buy rating", "dividend", "share buyback",
    "record profit", "contract win", "positive outlook"
]

NEGATIVE_WORDS = [
    "zarar açıkladı", "zararı arttı", "zararı arttırdı",
    "kârı düştü", "karı düştü", "gelir düşüşü",
    "sermaye artırımı", "tedbir", "işlem yasağı",
    "soruşturma", "ceza aldı", "olumsuz", "iflas",
    "hedef fiyat düşürüldü", "temerrüt", "borç yapılandırma",
    "profit warning", "misses expectations", "downgrade",
    "investigation", "default", "bankruptcy", "loss widened",
    "negative outlook", "trading suspension"
]

def analyze_sentiment(text):
    """Ücretsiz, anahtar kelime tabanlı haber sınıflandırması."""
    text = re.sub(r"\s+", " ", (text or "").lower())

    positive_hits = [word for word in POSITIVE_WORDS if word in text]
    negative_hits = [word for word in NEGATIVE_WORDS if word in text]

    positive_score = len(positive_hits)
    negative_score = len(negative_hits)

    if positive_score > negative_score:
        label = "🟢 OLUMLU"
    elif negative_score > positive_score:
        label = "🔴 OLUMSUZ"
    else:
        label = "🟡 NÖTR / BELİRSİZ"

    return {
        "label": label,
        "positive_score": positive_score,
        "negative_score": negative_score,
        "positive_matches": positive_hits,
        "negative_matches": negative_hits,
    }
