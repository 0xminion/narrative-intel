"""State persistence for narrative tracking across days."""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)


def save_state(state_dir: Path, narratives: list[dict], extra: dict | None = None) -> None:
    """Save today's narrative state. Overwrites latest.json and creates dated copy."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    state = {
        "date": today,
        "narratives": narratives,
        "token_signals": {},
    }

    # Merge extra data (like token_signals)
    if extra:
        if "token_signals" in extra:
            state["token_signals"] = extra["token_signals"]

    # Save dated copy
    dated_path = state_dir / f"state-{today}.json"
    with open(dated_path, "w") as f:
        json.dump(state, f, indent=2, default=str)
    log.info(f"Saved state to {dated_path}")

    # Save as latest
    latest_path = state_dir / "latest.json"
    with open(latest_path, "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_state(state_dir: Path) -> dict:
    """Load the most recent state (latest.json)."""
    latest_path = state_dir / "latest.json"
    if not latest_path.exists():
        log.info("No previous state found, starting fresh")
        return {"date": None, "narratives": [], "token_signals": {}}

    try:
        with open(latest_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.warning(f"Failed to load state: {e}")
        return {"date": None, "narratives": [], "token_signals": {}}


def load_state_date(state_dir: Path, date_str: str) -> dict | None:
    """Load state for a specific date."""
    path = state_dir / f"state-{date_str}.json"
    if not path.exists():
        return None

    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def load_week(state_dir: Path, days: int = 7) -> list[dict]:
    """Load states for the past N days."""
    states = []
    today = datetime.utcnow()

    for i in range(days):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        state = load_state_date(state_dir, date_str)
        if state:
            states.append(state)

    return states
