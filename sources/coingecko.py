"""CoinGecko CLI wrapper. All market/price data comes from here (free)."""

import subprocess
import json
import logging
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
        output = _run(["trending"])
        lines = output.strip().split("\n")
        results = []
        for line in lines:
            # Skip empty lines, header rows, and separator lines
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            # Skip common header patterns
            lower = stripped.lower()
            if lower.startswith("rank") or lower.startswith("symbol") or lower.startswith("name"):
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                # First column is symbol, last column might be rank/price, rest is name
                symbol = parts[0].strip().upper().lstrip("$")
                # Skip if first "word" doesn't look like a token symbol
                if not symbol or not any(c.isalpha() for c in symbol):
                    continue
                results.append({
                    "symbol": symbol,
                    "name": " ".join(parts[1:-1]) if len(parts) > 2 else parts[1],
                    "rank": len(results) + 1,
                })
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        log.warning(f"Failed to get trending: {e}")
        return []


def get_top_gainers_losers(top: int = 300) -> dict:
    """Get top gainers and losers from top N market cap tokens."""
    try:
        output = _run(["top-gainers-losers"])
        lines = output.strip().split("\n")

        gainers = []
        losers = []
        section = None

        for line in lines:
            lower = line.lower()
            if "gainer" in lower:
                section = "gainers"
                continue
            elif "loser" in lower:
                section = "losers"
                continue

            if section and line.strip() and not line.startswith("-"):
                # Parse: SYMBOL price change%
                parts = line.split()
                if len(parts) >= 3:
                    entry = {
                        "symbol": parts[0].strip().upper().lstrip("$"),
                        "change_24h": _parse_change(parts[-1]) if "%" in parts[-1] else 0,
                    }
                    if section == "gainers":
                        gainers.append(entry)
                    else:
                        losers.append(entry)

        return {"gainers": gainers[:10], "losers": losers[:10]}
    except Exception as e:
        log.warning(f"Failed to get gainers/losers: {e}")
        return {"gainers": [], "losers": []}


def _parse_change(s: str) -> float:
    """Parse a percentage string like '+12.34%' or '-5.6%'."""
    try:
        return float(s.replace("%", "").replace("+", "").strip())
    except ValueError:
        return 0.0


def get_price(token: str) -> dict | None:
    """Get current price, 24h change, and market cap for a token."""
    try:
        output = _run(["price", token])
        # Parse the output - cg price format varies
        lines = output.strip().split("\n")
        result = {"symbol": token.upper()}
        for line in lines:
            lower = line.lower()
            parts = line.split(":")
            if len(parts) >= 2:
                val = parts[1].strip()
                if "price" in lower:
                    result["price"] = _parse_number(val)
                elif "24h" in lower or "change" in lower:
                    result["change_24h"] = _parse_change(val)
                elif "market cap" in lower or "mcap" in lower:
                    result["market_cap"] = _parse_number(val)
                elif "volume" in lower:
                    result["volume"] = _parse_number(val)
        return result if "price" in result else None
    except Exception as e:
        log.warning(f"Failed to get price for {token}: {e}")
        return None


def get_prices_batch(tokens: list[str]) -> dict[str, dict]:
    """Get prices for multiple tokens. Tries batch first, falls back to individual."""
    results = {}
    if not tokens:
        return results

    # Try batch (cg may support comma-separated)
    try:
        batch_str = ",".join(tokens[:10])  # Limit batch size
        output = _run(["price", batch_str])
        # Parse batch output
        for token in tokens[:10]:
            results[token.upper()] = {"symbol": token.upper(), "price": 0,
                                       "change_24h": 0, "market_cap": 0, "volume": 0}
        # Try to parse from output
        lines = output.split("\n")
        current_token = None
        for line in lines:
            for token in tokens:
                if token.upper() in line.upper():
                    current_token = token.upper()
            if current_token:
                lower = line.lower()
                parts = line.split(":")
                if len(parts) >= 2:
                    val = parts[1].strip()
                    if "price" in lower:
                        results[current_token]["price"] = _parse_number(val)
                    elif "24h" in lower or "change" in lower:
                        results[current_token]["change_24h"] = _parse_change(val)
    except Exception:
        pass

    # Fetch remaining individually
    remaining = [t for t in tokens if t.upper() not in results]
    for token in remaining:
        data = get_price(token)
        if data:
            results[token.upper()] = data
        else:
            results[token.upper()] = {"symbol": token.upper(), "price": 0,
                                       "change_24h": 0, "market_cap": 0, "volume": 0}

    return results


def _parse_number(s: str) -> float:
    """Parse a number string like '$1,234.56' or '1.2M' or '500K'."""
    try:
        s = s.strip().replace("$", "").replace(",", "")
        if s.upper().endswith("B"):
            return float(s[:-1]) * 1e9
        if s.upper().endswith("M"):
            return float(s[:-1]) * 1e6
        if s.upper().endswith("K"):
            return float(s[:-1]) * 1e3
        return float(s)
    except ValueError:
        return 0.0
