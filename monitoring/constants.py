"""
Static reference data for the mock trading universe.

Kept as plain constants rather than DB tables — there is no need to query,
filter, or admin-edit these independently of the Order/Trader rows that
reference them, so a table would just be indirection without benefit.
"""

DESKS = [
    "EQUITIES-1",
    "EQUITIES-2",
    "DERIVATIVES-1",
    "DERIVATIVES-2",
    "FX-1",
]

# name -> plausible seed price (used as the anchor for LIMIT order pricing).
# Mix of US equities and a couple of indices; prices are illustrative, not
# real-time-accurate.
SYMBOLS = {
    "AAPL": 189.50,
    "MSFT": 415.20,
    "GOOGL": 175.80,
    "AMZN": 178.30,
    "TSLA": 245.60,
    "NVDA": 118.90,
    "META": 505.40,
    "NFLX": 640.20,
    "AMD": 165.30,
    "JPM": 210.50,
    "V": 275.80,
    "JNJ": 152.40,
    "XOM": 118.60,
    "NIFTY50": 24500.00,
    "BANKNIFTY": 52300.00,
}

TRADER_NAMES = [
    "Alice Chen",
    "Ben Rodriguez",
    "Carla Nguyen",
    "David Okafor",
    "Elena Petrova",
    "Farid Hassan",
    "Grace Kim",
    "Hiro Tanaka",
    "Ines Alvarez",
    "Jack Sullivan",
]

REJECT_REASONS = [
    "RISK_LIMIT_BREACH",
    "INSUFFICIENT_MARGIN",
    "INVALID_SYMBOL",
    "EXCHANGE_TIMEOUT",
]

# Anomaly detection thresholds (section 2.2 of the build plan)
HIGH_LATENCY_MEDIUM_MS = 2000
HIGH_LATENCY_HIGH_MS = 5000
DUPLICATE_FILL_WINDOW_MS = 500
REJECT_SPIKE_WINDOW_MINUTES = 5
REJECT_SPIKE_THRESHOLD = 3
STALE_ORDER_MINUTES = 10
