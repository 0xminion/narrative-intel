"""Narrative shift detection, velocity tracking, and boundary watch."""

import logging
from datetime import datetime, timedelta, timezone
from storage.state import load_state, load_state_date

log = logging.getLogger(__name__)


def analyze_shifts(current_narratives: list[dict], state_dir, tz=None) -> dict:
    """Compare current narratives to previous day. Returns shift classifications."""
    prev = load_state(state_dir)
    prev_map = {n["name"].lower(): n for n in prev.get("narratives", [])}

    shifts = {
        "positive": [],  # moved up 2+ or new entry
        "negative": [],  # moved down 2+ or exited
        "neutral": [],   # moved 0-1 positions
    }

    current_names = {n["name"].lower() for n in current_narratives}
    prev_names = set(prev_map.keys())

    for n in current_narratives:
        name_lower = n["name"].lower()
        current_rank = n["rank"]

        if name_lower in prev_map:
            prev_rank = prev_map[name_lower]["rank"]
            delta = prev_rank - current_rank  # positive = moved up
        else:
            prev_rank = None
            delta = None  # new entry

        entry = {
            "name": n["name"],
            "current_rank": current_rank,
            "prev_rank": prev_rank,
            "delta": delta,
            "keywords": n.get("keywords", []),
        }

        if delta is None:
            entry["delta_label"] = "NEW ENTRY"
            entry["delta_display"] = "—"
            shifts["positive"].append(entry)
        elif delta >= 2:
            entry["delta_label"] = f"+{delta}"
            entry["delta_display"] = f"#{prev_rank} → #{current_rank} (+{delta})"
            shifts["positive"].append(entry)
        elif delta <= -2:
            entry["delta_label"] = str(delta)
            entry["delta_display"] = f"#{prev_rank} → #{current_rank} ({delta})"
            shifts["negative"].append(entry)
        else:
            entry["delta_label"] = "0" if delta == 0 else f"+{delta}"
            entry["delta_display"] = f"#{prev_rank} → #{current_rank} ({'+' if delta >= 0 else ''}{delta})"
            shifts["neutral"].append(entry)

    # Check for narratives that exited top 10
    for name_lower, prev_n in prev_map.items():
        if name_lower not in current_names:
            shifts["negative"].append({
                "name": prev_n["name"],
                "current_rank": None,
                "prev_rank": prev_n["rank"],
                "delta": None,
                "delta_label": "EXITED",
                "delta_display": f"#{prev_n['rank']} → — (EXITED TOP 10)",
                "keywords": prev_n.get("keywords", []),
            })

    # Sort: positive by delta desc, negative by delta asc
    shifts["positive"].sort(key=lambda x: x.get("delta") or 999, reverse=True)
    shifts["negative"].sort(key=lambda x: x.get("delta") or -999)

    return shifts


def calculate_velocity(state_dir, current_narratives: list[dict], days: int = 3,
                       tz=None) -> dict:
    """Calculate 3-day trajectory for each narrative."""
    velocity = {}

    # Load states from past N days
    past_states = []
    if tz is None:
        tz = timezone.utc
    today = datetime.now(tz)
    for i in range(1, days + 1):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        state = load_state_date(state_dir, date_str)
        if state:
            past_states.append(state)

    if len(past_states) < 2:
        return velocity

    for n in current_narratives:
        name = n["name"]
        name_lower = name.lower()
        current_rank = n["rank"]

        ranks = []
        for state in past_states:
            for sn in state.get("narratives", []):
                if sn["name"].lower() == name_lower:
                    ranks.append(sn["rank"])
                    break

        if len(ranks) >= 2:
            # Compare first and last in window
            net_change = ranks[-1] - ranks[0]  # positive = moved down (bad)
            recent_change = ranks[-1] - current_rank

            if abs(recent_change) > abs(net_change) / max(len(ranks), 1):
                velocity[name] = "accelerating" if recent_change > 0 else "decelerating"
            else:
                velocity[name] = "steady"

    return velocity


def boundary_watch(current_narratives: list[dict], state_dir) -> list[dict]:
    """Find narratives approaching top 10 (ranked 11-15) that are moving up."""
    prev = load_state(state_dir)
    prev_map = {n["name"].lower(): n for n in prev.get("narratives", [])}

    # We need narratives beyond top 10 — check if trending-narratives returned more
    # If not, we can only check from previous state
    boundary = []

    # Check if any narrative jumped from 11+ into or near top 10
    for n in current_narratives:
        if n["rank"] > 10:
            name_lower = n["name"].lower()
            if name_lower in prev_map:
                prev_rank = prev_map[name_lower]["rank"]
                if prev_rank > n["rank"]:
                    boundary.append({
                        "name": n["name"],
                        "current_rank": n["rank"],
                        "prev_rank": prev_rank,
                        "movement": prev_rank - n["rank"],
                        "note": f"#{prev_rank} → #{n['rank']} (+{prev_rank - n['rank']})"
                    })

    boundary.sort(key=lambda x: x["movement"], reverse=True)
    return boundary
