"""Event log: outages and latency spikes with timestamps."""

import statistics

from netdiag.config import SERIES_DEFS


def find_spikes(samples, limit=3, floor_ms=100.0, min_gap_s=2.0):
    """Worst latency spikes: at least floor_ms and 3x the median, at least min_gap_s apart."""
    vals = [s["rtt"] for s in samples if s["rtt"] is not None]
    if not vals:
        return []
    threshold = max(floor_ms, 3 * statistics.median(vals))
    picks = []
    for s in sorted((s for s in samples if s["rtt"] is not None and s["rtt"] >= threshold),
                    key=lambda s: -s["rtt"]):
        if all(abs(s["time"] - p["time"]) >= min_gap_s for p in picks):
            picks.append(s)
        if len(picks) >= limit:
            break
    return sorted(picks, key=lambda s: s["time"])


def build_events(raw, stats, max_events=30):
    """Outages and latency spikes with timestamps. Events that hit the router AND the
    internet at the same moment point at your local network/Wi-Fi."""
    events = []
    for key, _, _, short in SERIES_DEFS:
        for o in (stats.get(key) or {}).get("outages", []):
            events.append({"t": o["start"], "source": short, "kind": "Outage",
                           "detail": f"{o['probes']} probes lost in a row (~{o['duration']} s silent)"})
        for s in find_spikes(raw.get(key, []), floor_ms=50.0 if key == "local" else 100.0):
            events.append({"t": s["time"], "source": short, "kind": "Spike", "detail": f"{s['rtt']} ms"})
    return sorted(events, key=lambda ev: ev["t"])[:max_events]
