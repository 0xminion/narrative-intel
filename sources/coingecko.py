"""CoinGecko CLI wrapper. All market/price data comes from here (free)."""

import subprocess
import json
import logging
import re
from typing import Any

log = logging.getLogger(__name__)

CG = "cg"  # Assumes 'cg' is in PATH


def _run(args: list[str], timeout: int = 30) -> str:
    """Run a cg command and return stdout. Raises on failure."""
    cmd = [CG] + args
    log.debug(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            log.error(f"cg command failed: {result.stderr.strip()}")
            raise RuntimeError(f"cg failed: {result.stderr.strip()}")
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log.error(f"cg command timed out: {' '.join(cmd)}")
        raise


def get_trending(limit: int = 15) -> list[dict]:
    """Get CoinGecko trending tokens."""
    try:
        output = _run(["trending", "-o", "json"])
        data = json.loads(output)
        results = []
        coins = data.get("coins", data) if isinstance(data, dict) else data
        for item in coins[:limit]:
            if isinstance(item, dict):
                coin = item.get("item", item)
                results.append({
                    "symbol": coin.get("symbol", "").upper(),
                    "name": coin.get("name", ""),
                    "rank": len(results) + 1,
                })
        return results
    except Exception as e:
        log.warning(f"Failed to get trending: {e}")
        return []


def get_top_gainers_losers(top: int = 300) -> dict:
    """Get top gainers and losers from top N market cap coins.
    Note: This is a paid CoinGecko CLI feature. Falls back to empty if unavailable.
    """
    try:
        # Get gainers
        gainer_output = _run(["top-gainers-losers", "--top-coins", str(top), "-o", "json"])
        gainers = _parse_gainer_loser_json(gainer_output)

        # Get losers
        try:
            loser_output = _run(["top-gainers-losers", "--top-coins", str(top), "--losers", "-o", "json"])
            losers = _parse_gainer_loser_json(loser_output)
        except RuntimeError:
            losers = []

        return {"gainers": gainers[:10], "losers": losers[:10]}
    except RuntimeError as e:
        if "paid" in str(e).lower() or "analyst" in str(e).lower() or "subscription" in str(e).lower():
            log.info("top-gainers-losers requires paid CoinGecko plan, skipping")
        else:
            log.warning(f"Failed to get gainers/losers: {e}")
        return {"gainers": [], "losers": []}
    except Exception as e:
        log.warning(f"Failed to get gainers/losers: {e}")
        return {"gainers": [], "losers": []}


def _parse_gainer_loser_json(output: str) -> list[dict]:
    """Parse JSON output from top-gainers-losers."""
    try:
        data = json.loads(output)
        results = []
        items = data if isinstance(data, list) else data.get("coins", data.get("items", []))
        for item in items:
            if isinstance(item, dict):
                results.append({
                    "symbol": item.get("symbol", "").upper(),
                    "change_24h": _parse_change(item.get("price_change_percentage_24h",
                                       item.get("change", item.get("price_change", 0)))),
                })
        return results
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_change(val) -> float:
    """Parse a percentage value from string or number."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.replace("%", "").replace("+", "").strip())
        except ValueError:
            return 0.0
    return 0.0


def get_price(symbol: str) -> dict | None:
    """Get current price, 24h change, and market cap for a token by symbol."""
    try:
        output = _run(["price", "--symbols", symbol.lower(), "-o", "json"])
        data = json.loads(output)
        # The JSON structure depends on the cg CLI version
        if isinstance(data, dict):
            # Find the token data (key might be symbol in various cases)
            token_data = data.get(symbol.upper(), data.get(symbol.lower(), data))
            if isinstance(token_data, dict):
                return {
                    "symbol": symbol.upper(),
                    "price": _parse_number(token_data.get("usd", token_data.get("price", 0))),
                    "change_24h": _parse_change(token_data.get("usd_24h_change",
                                       token_data.get("price_change_24h", 0))),
                    "market_cap": _parse_number(token_data.get("usd_market_cap",
                                       token_data.get("market_cap", 0))),
                    "volume": _parse_number(token_data.get("usd_24h_vol",
                                     token_data.get("volume", 0))),
                }
        return None
    except Exception as e:
        log.warning(f"Failed to get price for {symbol}: {e}")
        return None


def get_prices_batch(symbols: list[str]) -> dict[str, dict]:
    """Get prices for multiple symbols in a single batch call."""
    results = {}
    if not symbols:
        return results

    # Batch up to 50 symbols per call
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        symbols_str = ",".join(s.lower() for s in batch)
        try:
            output = _run(["price", "--symbols", symbols_str, "-o", "json"])
            data = json.loads(output)
            if isinstance(data, dict):
                for sym in batch:
                    token_data = data.get(sym.upper(), data.get(sym.lower(), {}))
                    if isinstance(token_data, dict) and token_data:
                        results[sym.upper()] = {
                            "symbol": sym.upper(),
                            "price": _parse_number(token_data.get("usd", 0)),
                            "change_24h": _parse_change(token_data.get("usd_24h_change", 0)),
                            "market_cap": _parse_number(token_data.get("usd_market_cap", 0)),
                            "volume": _parse_number(token_data.get("usd_24h_vol", 0)),
                        }
                    else:
                        results[sym.upper()] = {"symbol": sym.upper(), "price": 0,
                                                  "change_24h": 0, "market_cap": 0, "volume": 0}
        except Exception as e:
            log.warning(f"Batch price fetch failed: {e}")
            for sym in batch:
                results[sym.upper()] = {"symbol": sym.upper(), "price": 0,
                                          "change_24h": 0, "market_cap": 0, "volume": 0}

    return results


def _parse_number(val) -> float:
    """Parse a number from various formats."""
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            val = val.strip().replace("$", "").replace(",", "")
            if val.upper().endswith("B"):
                return float(val[:-1]) * 1e9
            if val.upper().endswith("M"):
                return float(val[:-1]) * 1e6
            if val.upper().endswith("K"):
                return float(val[:-1]) * 1e3
            return float(val)
        except ValueError:
            return 0.0
    return 0.0
