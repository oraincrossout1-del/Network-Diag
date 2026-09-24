"""Turns raw probe samples into statistics (loss, avg/P99, jitter, outages)."""

from netdiag.utils import percentile


def calc_stats(samples):
    total = len(samples)
    stats = {"n": total, "received": 0, "lost": 0, "loss": None, "avg": None, "min": None,
             "max": None, "p99": None, "jitter": None, "max_burst": 0,
             "max_outage_s": 0.0, "outages": []}
    if total == 0:
        return stats
    rtts = [s["rtt"] for s in samples if s["rtt"] is not None]
    stats["received"] = len(rtts)
    stats["lost"] = total - len(rtts)
    stats["loss"] = round((total - len(rtts)) / total * 100, 1)

    streak = longest = 0
    for s in samples:
        if s["rtt"] is None:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    stats["max_burst"] = longest

    # Outage = >=3 consecutive lost probes (isolated drops aren't an outage). Each is logged.
    gaps = sorted(b["time"] - a["time"] for a, b in zip(samples, samples[1:]))
    interval = gaps[len(gaps) // 2] if gaps else 0.0
    i = 0
    while i < total:
        if samples[i]["rtt"] is None:
            j = i
            while j + 1 < total and samples[j + 1]["rtt"] is None:
                j += 1
            if j - i + 1 >= 3:
                stats["outages"].append({
                    "start": samples[i]["time"], "probes": j - i + 1,
                    "duration": round(samples[j]["time"] - samples[i]["time"] + interval, 1)})
            i = j + 1
        else:
            i += 1
    stats["max_outage_s"] = max((o["duration"] for o in stats["outages"]), default=0.0)

    if rtts:
        ordered = sorted(rtts)
        stats.update(avg=round(sum(rtts) / len(rtts), 1), min=round(ordered[0], 1),
                     max=round(ordered[-1], 1), p99=round(percentile(ordered, 0.99), 1))
        if len(rtts) > 1:  # jitter = mean absolute difference between consecutive replies
            diffs = [abs(b - a) for a, b in zip(rtts, rtts[1:])]
            stats["jitter"] = round(sum(diffs) / len(diffs), 1)
    return stats
