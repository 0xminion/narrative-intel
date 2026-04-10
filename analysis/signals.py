"""Token signal classification and progression tracking."""

import logging
from collections import defaultdict

log = logging.getLogger(__name__)


def classify_tokens(all_tokens: dict, narrative_tokens: dict,
                    cg_trending: list[dict], cg_gainers: list[dict],
                    emerging_tokens: list[dict]) -> dict:
    """Classify each token as double-confirmed, social-first, or price-first.

    Returns: { "TOKEN": { "symbol": ..., "signal": ..., "narrative": ..., ... } }
    """
    cg_trending_symbols = {t["symbol"].upper() for t in cg_trending}
    cg_gainer_symbols = {t["symbol"].upper() for t in cg_gainers}
    cg_price_symbols = cg_trending_symbols | cg_gainer_symbols

    # Build emerging tokens lookup
    emerging_map = {t["token"].upper().lstrip("$"): t for t in emerging_tokens}

    classified = {}

    # Process tokens from narrative keyword mentions
    for narrative_name, tokens in narrative_tokens.items():
        for token_info in tokens:
            symbol = (token_info.get("token", "") or token_info.get("symbol", "")).upper().lstrip("$")
            if not symbol:
                continue

            in_social = True
            in_price = symbol in cg_price_symbols
            in_emerging = symbol in emerging_map

            if in_social and in_price:
                signal = "double-confirmed"
            elif in_social and not in_price:
                signal = "social-first"
            elif in_price and not in_social:
                signal = "price-first"
            else:
                signal = "social-first"

            key = symbol.upper()
            if key not in classified:
                classified[key] = {
                    "symbol": symbol,
                    "signal": signal,
                    "narrative": narrative_name,
                    "mentions": token_info.get("engagement", 0),
                    "in_emerging": in_emerging,
                    "price_data": {},
                }
            else:
                # Keep the stronger signal
                if signal == "double-confirmed":
                    classified[key]["signal"] = "double-confirmed"

    # Add CoinGecko-only tokens (price first)
    for cg_token in cg_trending + cg_gainers:
        symbol = cg_token["symbol"].upper()
        if symbol not in classified:
            classified[symbol] = {
                "symbol": symbol,
                "signal": "price-first",
                "narrative": None,
                "mentions": 0,
                "in_emerging": False,
                "price_data": cg_token,
            }

    return classified


def enrich_with_prices(classified: dict, prices: dict) -> dict:
    """Add price data to classified tokens."""
    for symbol, info in classified.items():
        price_info = prices.get(symbol.upper(), {})
        info["price_data"] = {
            "price": price_info.get("price", 0),
            "change_24h": price_info.get("change_24h", 0),
            "market_cap": price_info.get("market_cap", 0),
            "volume": price_info.get("volume", 0),
        }
    return classified


def update_signal_history(classified: dict, state_dir, storage_module) -> dict:
    """Track signal progression over multiple days. Updates classified dict in place."""
    prev_state = storage_module.load_state(state_dir)
    prev_signals = prev_state.get("token_signals", {})

    for symbol, info in classified.items():
        prev = prev_signals.get(symbol.upper(), {})
        history = prev.get("signal_history", [])
        history.append(info["signal"])
        # Keep last 7 days
        info["signal_history"] = history[-7:]
        info["days_appearing"] = prev.get("days_appearing", 0) + 1

    return classified


def save_token_signals(classified: dict, state_dir, storage_module) -> None:
    """Save current token signals to state for tomorrow's comparison."""
    signals = {}
    for symbol, info in classified.items():
        signals[symbol.upper()] = {
            "signal_history": info.get("signal_history", [info["signal"]]),
            "days_appearing": info.get("days_appearing", 1),
            "narrative": info.get("narrative"),
        }
    # Merge with existing state
    state = storage_module.load_state(state_dir)
    state["token_signals"] = signals
    storage_module.save_state(state_dir, state.get("narratives", []), state)


def get_signal_display(signal: str) -> str:
    """Get emoji display for signal type."""
    return {
        "double-confirmed": "🔥 Double confirmed",
        "social-first": "📢 Social first",
        "price-first": "💰 Price first",
    }.get(signal, signal)
