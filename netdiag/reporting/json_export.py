"""Machine-readable JSON export of a run."""

import json


def write_json(ctx, path):
    """Machine-readable copy of the results (handy for comparing runs over time)."""
    quality, _, summary = ctx["verdict"]
    data = {
        "generated": ctx["generated"], "platform": ctx["platform"], "target": ctx["target"],
        "secondary": ctx["secondary"], "port": ctx["port"], "gateway": ctx["gateway"],
        "duration_s": ctx["duration"], "verdict": {"grade": quality, "summary": summary},
        "findings": ctx["findings"], "stats": ctx["stats"],
        "speed": {k: v for k, v in ctx["speed"].items() if k != "windows"},
        "dns": ctx["dns"], "bloat": ctx["bloat"], "hops": ctx["hops"], "ip_info": ctx["ip_info"],
        "events": ctx["events"],
        "samples": {k: [[s["time"], s["rtt"]] for s in v] for k, v in ctx["raw"].items()},
    }
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
