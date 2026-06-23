RISK_WEIGHTS = {
    "conservative": {"fundamental": 0.6, "technical": 0.1, "sentiment": 0.3},
    "moderate": {"fundamental": 0.4, "technical": 0.3, "sentiment": 0.3},
    "aggressive": {"fundamental": 0.2, "technical": 0.5, "sentiment": 0.3},
}

# Per-signal weights for the multi-signal technical verdict (pattern + RSI +
# MACD + trend + volume). Keyed to the same risk-profile names:
#  - conservative leans on trend & volume confirmation (avoid chasing)
#  - aggressive leans on pattern & momentum (act early)
#  - moderate is balanced
# Each profile's weights sum to 1.0.
SIGNAL_WEIGHTS = {
    "conservative": {"pattern": 0.15, "rsi": 0.15, "macd": 0.15, "trend": 0.35, "volume": 0.20},
    "moderate":     {"pattern": 0.25, "rsi": 0.20, "macd": 0.20, "trend": 0.20, "volume": 0.15},
    "aggressive":   {"pattern": 0.35, "rsi": 0.25, "macd": 0.25, "trend": 0.10, "volume": 0.05},
}