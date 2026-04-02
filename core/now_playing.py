from __future__ import annotations

import time

# Utilities to compute and format mm:ss strings for display


def _format_mmss(total_seconds: int) -> str:
    if total_seconds < 0:
        total_seconds = 0
    m, s = divmod(int(total_seconds), 60)
    return f"{m:02d}:{s:02d}"


def compute_remaining(duration_seconds: int | None, start_epoch: float | None) -> int | None:
    """Compute remaining seconds given duration and start epoch seconds.
    Returns None if cannot compute.
    """
    if duration_seconds is None or start_epoch is None:
        return None
    now = time.time()
    elapsed = max(0, int(now - start_epoch))
    remaining = duration_seconds - elapsed
    if remaining < 0:
        return 0
    return remaining


def compute_display_mmss(
    duration_seconds: int | None, start_epoch: float | None
) -> tuple[str, bool]:
    """Return (mm:ss, is_remaining) where is_remaining indicates whether the value
    represents remaining time (True) or total duration (False) when remaining
    is unavailable.
    """
    remaining = compute_remaining(duration_seconds, start_epoch)
    if remaining is not None:
        return _format_mmss(remaining), True
    if duration_seconds is not None:
        return _format_mmss(duration_seconds), False
    return "--:--", False
