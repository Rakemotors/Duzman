"""Known Pattern Engine metric and operator names."""

KNOWN_METRICS: frozenset[str] = frozenset(
    {
        "RSI_1h",
        "RSI_4h",
        "RSI_1d",
        "RSI_1w",
        "stoch_k_1h",
        "stoch_k_4h",
        "stoch_d_1h",
        "stoch_d_4h",
        "funding_rate_avg",
        "funding_dislocation_pct",
        "oi_change_24h_pct",
        "price_change_24h_pct",
        "price_change_7d_pct",
        "liquidations_longs_24h_usd",
        "liquidations_shorts_24h_usd",
        "fear_greed_index",
        "btc_dominance",
        "btc_dominance_change_7d_pct",
        "etf_net_flow_streak_days",
        "etf_cum_flow_5d_usd",
        "price_vs_btc_change_7d_pct",
        "volatility_24h_annualized",
        "premium_discount_pct",
    }
)

KNOWN_OPERATORS: frozenset[str] = frozenset({">", "<", ">=", "<=", "==", "!="})
