"""30-day retention cleanup for reports and state files."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)


def cleanup(daily_dir: Path, weekly_dir: Path, state_dir: Path,
            retention_days: int = 30, tz=None) -> int:
    """Delete files older than retention_days. Returns count of deleted files."""
    if tz is None:
        tz = timezone.utc
    cutoff = datetime.now(tz) - timedelta(days=retention_days)
    deleted = 0

    for directory in [daily_dir, weekly_dir, state_dir]:
        if not directory.exists():
            continue

        for f in directory.iterdir():
            if not f.is_file():
                continue
            # Never delete latest.json
            if f.name == "latest.json":
                continue

            # Try to parse date from filename
            file_date = _parse_date_from_filename(f.name)
            if file_date and file_date < cutoff:
                try:
                    f.unlink()
                    deleted += 1
                    log.info(f"Deleted old file: {f.name}")
                except OSError as e:
                    log.warning(f"Failed to delete {f.name}: {e}")

    if deleted:
        log.info(f"Cleanup: deleted {deleted} files older than {retention_days} days")
    return deleted


def _parse_date_from_filename(filename: str) -> datetime | None:
    """Extract date from filenames like 2026-04-10.txt, weekly-2026-W15.txt, state-2026-04-10.json."""
    # Try YYYY-MM-DD
    parts = filename.replace(".txt", "").replace(".json", "").replace("state-", "").replace("weekly-", "")
    if "W" in parts:
        # Weekly: YYYY-WXX — approximate to Monday of that week
        try:
            year_str, week_str = parts.split("-W")
            year = int(year_str)
            week = int(week_str)
            return datetime.strptime(f"{year} {week} 1", "%Y %W %w")
        except (ValueError, IndexError):
            return None

    # Daily: YYYY-MM-DD
    for fmt in ["%Y-%m-%d", "%Y%m%d"]:
        try:
            return datetime.strptime(parts, fmt)
        except ValueError:
            continue

    return None
