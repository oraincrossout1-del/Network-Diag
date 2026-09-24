"""Route tracing (tracert / traceroute / tracepath) and CG-NAT detection from the hops."""

import re
import shutil

from netdiag.config import IS_WIN
from netdiag.utils import in_cgnat, run_cmd


def build_trace_cmd(target, max_hops=15):
    """Returns None when no trace tool is installed."""
    if IS_WIN:
        return ["tracert", "-d", "-h", str(max_hops), "-w", "1000", target]
    if shutil.which("traceroute"):
        return ["traceroute", "-n", "-m", str(max_hops), "-w", "1", "-q", "3", target]
    if shutil.which("tracepath"):  # ships with iputils; traceroute often isn't installed
        return ["tracepath", "-n", "-m", str(max_hops), target]
    return None


_HOP_LINE_RE = re.compile(r"^\s*(\d+)\??:?\s+(.*)$")  # '1  ...' (traceroute/tracert) or '1:  ...' (tracepath)
_IPV4_RE = re.compile(r"\d{1,3}(?:\.\d{1,3}){3}")
_MS_RE = re.compile(r"(?<![\d.])(\d+(?:\.\d+)?)\s*ms")


def parse_traceroute(output):
    """Handles all layouts: Windows puts times BEFORE the IP, Linux/macOS put the IP FIRST,
    tracepath prints '1:' and may repeat a hop number (those lines are merged).
    Timed-out hops are kept (ip=None) so the hop numbering stays honest."""
    merged = {}
    for line in output.splitlines():
        m = _HOP_LINE_RE.match(line)
        if not m:
            continue
        entry = merged.setdefault(int(m.group(1)), {"ip": None, "times": []})
        rest = m.group(2)
        ip = _IPV4_RE.search(rest)
        if ip and entry["ip"] is None:
            entry["ip"] = ip.group(0)
        entry["times"].extend(float(t) for t in _MS_RE.findall(rest))
    return [{"hop": n, "ip": e["ip"],
             "avg_ms": round(sum(e["times"]) / len(e["times"]), 1) if e["times"] else None}
            for n, e in sorted(merged.items())]


def run_traceroute(target, max_hops=15):
    """Returns the hop list, or None if this machine has no traceroute/tracert/tracepath."""
    cmd = build_trace_cmd(target, max_hops)
    return None if cmd is None else parse_traceroute(run_cmd(cmd, 150))


def detect_cgnat(hops):
    """Heuristic: a hop inside 100.64.0.0/10 (RFC 6598) means the ISP shares your public IP."""
    return any(h["ip"] and in_cgnat(h["ip"]) for h in hops or [])
