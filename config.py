"""Configuration loader. Reads config.yaml + .env for secrets."""

import os
import sys
import logging
import yaml
from datetime import datetime, timezone
from dotenv import load_dotenv
from pathlib import Path

log = logging.getLogger(__name__)

# Load .env from same directory as this script
load_dotenv(Path(__file__).parent / ".env")

PROJECT_DIR = Path(__file__).parent
REPORTS_DIR = PROJECT_DIR / "reports"
DAILY_DIR = REPORTS_DIR / "daily"
WEEKLY_DIR = REPORTS_DIR / "weekly"
STATE_DIR = REPORTS_DIR / "state"

# Ensure directories exist
for d in [DAILY_DIR, WEEKLY_DIR, STATE_DIR]:
    d.mkdir(parents=True, exist_ok=True)


def _resolve(value: str | None, env_key: str) -> str:
    """Resolve a config value: use directly if set, else fall back to env var."""
    if value and value.strip():
        return value.strip()
    env_val = os.getenv(env_key, "").strip()
    if not env_val:
        print(f"ERROR: {env_key} not set in config.yaml or .env", file=sys.stderr)
        sys.exit(1)
    return env_val


def load():
    """Load and validate configuration. Returns a dict."""
    config_path = PROJECT_DIR / "config.yaml"
    if not config_path.exists():
        print("ERROR: config.yaml not found. Copy config.yaml.example to config.yaml and fill in values.", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        cfg = yaml.safe_load(f)

    # Resolve secrets
    elfa_key = _resolve(cfg.get("elfa", {}).get("api_key"), "ELFA_API_KEY")
    llm_key = _resolve(cfg.get("llm", {}).get("api_key"), "LLM_API_KEY")
    bot_token = _resolve(cfg.get("bot_token"), "TELEGRAM_BOT_TOKEN")

    llm = cfg.get("llm", {})
    settings = cfg.get("settings", {})
    destinations = cfg.get("destinations", [])

    if not destinations:
        print("ERROR: No destinations configured in config.yaml", file=sys.stderr)
        sys.exit(1)

    # Resolve timezone
    import zoneinfo
    tz_name = settings.get("timezone", "UTC")
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except KeyError:
        log.warning(f"Unknown timezone '{tz_name}', falling back to UTC")
        tz = timezone.utc
        tz_name = "UTC"

    # Calculate UTC offset string for display
    now = datetime.now(tz)
    offset = now.strftime("%z")  # e.g., +0800
    offset_display = f"GMT{offset[:3]}:{offset[3:]}" if offset else "UTC"
    if offset_display == "GMT+00:00":
        offset_display = "UTC"

    return {
        "elfa_key": elfa_key,
        "llm_key": llm_key,
        "llm_provider": llm.get("provider", "openai"),
        "llm_model": llm.get("model", "gpt-4o-mini"),
        "bot_token": bot_token,
        "timezone": tz,
        "timezone_name": tz_name,
        "timezone_display": offset_display,
        "settings": {
            "top_narratives": settings.get("top_narratives", 10),
            "min_mentions": settings.get("min_mentions", 15),
            "tokens_shift": settings.get("tokens_per_narrative_shift", 5),
            "tokens_neutral": settings.get("tokens_per_narrative_neutral", 3),
            "retention_days": settings.get("retention_days", 30),
            "sentiment_mentions": settings.get("sentiment_mentions", 30),
        },
        "destinations": destinations,
    }
