"""Interpretation: statistics, grading, bufferbloat and the event log. Pure computation.
May depend on: config, utils. Must not import probes or reporting.

Public API of the package: other packages import from here, never from the files inside."""

from netdiag.analysis.stats import calc_stats
from netdiag.analysis.bufferbloat import compute_bufferbloat, slice_window
from netdiag.analysis.grading import (
    BLOCKED_HINTS,
    CGNAT_AFFECTS_GRADE,
    INET_NAMES,
    THRESHOLDS,
    collect_findings,
    first_isp_hop,
    rate_high,
    rate_loss,
    rate_low,
    summarize,
)
from netdiag.analysis.events import build_events, find_spikes

__all__ = [
    "calc_stats",
    "slice_window",
    "compute_bufferbloat",
    "THRESHOLDS",
    "CGNAT_AFFECTS_GRADE",
    "INET_NAMES",
    "BLOCKED_HINTS",
    "rate_high",
    "rate_loss",
    "rate_low",
    "first_isp_hop",
    "collect_findings",
    "summarize",
    "find_spikes",
    "build_events",
]
