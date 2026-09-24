"""Latency-under-load (bufferbloat) calculation from idle vs. loaded samples."""

from netdiag.analysis.grading import rate_high
from netdiag.config import LOAD_TRIM_SEC, MIN_LOAD_SAMPLES


def slice_window(samples, w0, w1, trim=LOAD_TRIM_SEC):
    """Samples taken while the link was saturated, minus the ramp-up at the start."""
    lo = w0 + min(trim, (w1 - w0) / 4)
    return [s for s in samples if lo <= s["abs"] <= w1]


def compute_bufferbloat(idle, loaded, direction):
    """Latency increase while the link is saturated. Big jumps = lag during downloads/calls."""
    if (not idle or not loaded or idle["avg"] is None or loaded["avg"] is None
            or idle["received"] < 3 or loaded["n"] < MIN_LOAD_SAMPLES):
        return None
    increase = round(max(0.0, loaded["avg"] - idle["avg"]), 1)
    grade = ("Excellent", "Fair", "Poor")[rate_high(increase, "bloat_ms")]
    return {"direction": direction, "idle": idle["avg"], "loaded": loaded["avg"],
            "increase": increase, "grade": grade, "loaded_loss": loaded["loss"], "loaded_lost": loaded["lost"],
            "n": loaded["n"]}
