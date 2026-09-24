"""Grading: every test is rated GOOD / MEDIUM / BAD; the overall grade is the worst rating.
All tunable thresholds live in THRESHOLDS."""

from netdiag.config import COLOR_BAD, COLOR_GOOD, COLOR_MEDIUM, MIN_DEAD_PROBES, MIN_LOSS_EVENTS
from netdiag.utils import fmt, format_dns


# Every test is rated on its own: 0 = GOOD, 1 = MEDIUM, 2 = BAD (None = not measured).
# The overall grade is the WORST individual rating, so a single severe result = BAD.
#   GOOD   = flawless for competitive gaming, 4K streaming and video meetings, even when the line is busy
#   MEDIUM = fine for general browsing, but gaming / 4K / calls will show flaws
#   BAD    = a real network problem
THRESHOLDS = {
    # key: (medium_at, bad_at) -- higher is worse ("_below" keys: LOWER is worse)
    "download_mbps_below": (25.0, 5.0),    # 4K streaming needs ~25 Mbps
    "upload_mbps_below": (10.0, 2.0),      # HD video calls need ~3 Mbps up, 1080p/streaming more
    "bloat_ms": (30.0, 100.0),             # extra latency while the line is saturated
    "loss_pct": (1.0, 3.0),                # internet packet loss (also used under load)
    "local_loss_pct": (0.5, 1.0),          # your own router should basically never drop packets
    "local_latency_ms": (15.0, 50.0),      # router average
    "local_p99_ms": (50.0, 100.0),         # router spikes
    "latency_avg_ms": (80.0, 200.0),       # to the ping target (anycast 8.8.8.8 is normally close)
    "latency_p99_ms": (100.0, 250.0),      # spikes
    "jitter_ms": (15.0, 40.0),
    "outage_s": (1.0, 3.0),                # longest silent period (3+ consecutive lost probes)
    "first_hop_ms": (40.0, 100.0),         # first ISP router after yours (last-mile health)
    "dns_ms": (100.0, 300.0),
}
CGNAT_AFFECTS_GRADE = True  # CG-NAT = strict NAT in multiplayer games, so it isn't "flawless gaming"
INET_NAMES = {"heavy": "1400B ping", "rapid": "32B ping", "secondary": "secondary ping", "tcp": "TCP connect"}

# A probe type that gets ZERO replies while the others work is being filtered, not "lossy".
BLOCKED_HINTS = {
    "heavy": ("Large packets (1400 B)",
              "1400-byte pings get no reply while other probes do. Large packets are probably being "
              "dropped (an MTU/fragmentation problem, common with PPPoE, VPNs and tunnels) or the "
              "target filters large ICMP. Try lowering your router's MTU (e.g. 1492)."),
    "rapid": ("Small packets (32 B)",
              "32-byte pings get no reply while other probes do. ICMP to this target is probably "
              "filtered; latency figures rely on the other probes."),
    "secondary": ("Secondary target",
                  "The secondary target never answers ping while the primary does (blocked or "
                  "unreachable), so it can't be used to cross-check the primary."),
    "tcp": ("TCP connect",
            "Pings work but TCP connections to the target port all fail. A firewall or your ISP may "
            "be blocking HTTPS to this target."),
}


def rate_high(value, key):
    """Rating for metrics where a higher value is worse."""
    if value is None:
        return None
    medium, bad = THRESHOLDS[key]
    return 2 if value >= bad else 1 if value >= medium else 0


def rate_loss(loss_pct, lost, key):
    """Loss rating that ignores a lone dropped probe (indistinguishable from noise, and 1 lost
    probe out of 30 would otherwise read as 3.3% = BAD)."""
    if loss_pct is None:
        return None
    return 0 if lost < MIN_LOSS_EVENTS else rate_high(loss_pct, key)


def rate_low(value, key):
    """Rating for metrics where a lower value is worse (speeds)."""
    if value is None:
        return None
    medium, bad = THRESHOLDS[key]
    return 2 if value < bad else 1 if value < medium else 0


def _max_level(*levels):
    known = [lv for lv in levels if lv is not None]
    return max(known) if known else None


def _worst(series, field):
    """(value, series name) with the highest `field` across the internet series."""
    best = (None, None)
    for key, s in series.items():
        v = s.get(field)
        if v is not None and (best[0] is None or v > best[0]):
            best = (v, INET_NAMES[key])
    return best


def first_isp_hop(hops, gateway=None):
    """First responding router beyond your own gateway."""
    for h in hops or []:
        if h["hop"] >= 2 and h["ip"] and h["ip"] != gateway and h["avg_ms"] is not None:
            return h
    return None


def collect_findings(stats, speed, cgnat, dns=None, bloat=None, hops=None, gateway=None):
    """One row per test: {"test", "value", "level", "message"}. level None = test didn't run."""
    rows = []

    def row(test, value, level, medium_msg="", bad_msg=None):
        if level == 2:
            msg = medium_msg if bad_msg is None else bad_msg
        else:
            msg = medium_msg if level == 1 else ""
        rows.append({"test": test, "value": value, "level": level, "message": msg})

    # ---- Bandwidth -------------------------------------------------------
    measured = speed.get("status") == "Success"
    down = speed.get("down") if measured else None
    up = speed.get("up") if measured else None
    row("Download speed", fmt(down, " Mbps"), rate_low(down, "download_mbps_below"),
        f"Download speed is low ({down} Mbps). Fine for browsing, but 4K streaming and large downloads will buffer.",
        f"Download speed is very low ({down} Mbps). Even HD video and video calls will struggle.")
    row("Upload speed", fmt(up, " Mbps"), rate_low(up, "upload_mbps_below"),
        f"Upload speed is low ({up} Mbps). Video calls, game streaming and cloud backups will suffer.",
        f"Upload speed is very low ({up} Mbps). Video calls will freeze or drop out.")

    if bloat:
        for b in bloat:
            d, inc = b["direction"], b["increase"]
            a = "an" if d == "upload" else "a"
            row(f"Latency during {d}", f"+{inc} ms ({b['idle']} -> {b['loaded']} ms)",
                rate_high(inc, "bloat_ms"),
                f"Moderate bufferbloat: latency rises by {inc} ms during {a} {d}. "
                f"Games and video calls may lag while someone {d}s.",
                f"Severe bufferbloat: latency rises by {inc} ms during {a} {d} "
                f"({b['idle']} ms idle -> {b['loaded']} ms loaded). Any {d} on your network will cause "
                "lag in games and video calls; enable SQM/QoS (Smart Queue Management) on your router.")
        worst = max(bloat, key=lambda b: b["loaded_loss"])
        lloss = worst["loaded_loss"]
        row("Packet loss under load",
            f"{lloss}% ({worst['loaded_lost']}/{worst['n']} probes, during {worst['direction']})",
            rate_loss(lloss, worst["loaded_lost"], "loss_pct"),
            f"Some packets are lost when the line is busy ({lloss}%). Your connection struggles under load.",
            f"Heavy packet loss when the line is busy ({lloss}%). Your connection collapses under load.")
    else:
        row("Latency under load", "not measured", None)
        row("Packet loss under load", "not measured", None)

    # ---- Local network ---------------------------------------------------
    inet = {k: stats[k] for k in INET_NAMES if stats.get(k) and stats[k]["n"]}
    live = {k: s for k, s in inet.items() if s["received"]}
    blocked = {k: s for k, s in inet.items() if not s["received"] and s["n"] >= MIN_DEAD_PROBES}
    loc = stats.get("local")
    if loc and loc["n"]:
        if loc["received"] == 0 and live:  # router just ignores ping -> can't judge it
            row("Local router loss", "router ignores ping", None)
            row("Local router latency", "router ignores ping", None)
        else:
            row("Local router loss", f"{loc['loss']}% ({loc['lost']}/{loc['n']})",
                rate_loss(loc["loss"], loc["lost"], "local_loss_pct"),
                f"Your local router/Wi-Fi is dropping some packets ({loc['loss']}%). "
                "Check Wi-Fi signal/interference or the Ethernet cable.",
                f"Your local router/Wi-Fi is dropping {loc['loss']}% of packets. "
                "Move closer to the router or replace the Ethernet cable.")
            lvl = _max_level(rate_high(loc["avg"], "local_latency_ms"), rate_high(loc["p99"], "local_p99_ms"))
            detail = f"router avg {fmt(loc['avg'], ' ms')}, P99 {fmt(loc['p99'], ' ms')}"
            row("Local router latency", f"avg {fmt(loc['avg'], ' ms')}, P99 {fmt(loc['p99'], ' ms')}", lvl,
                f"Slow/erratic local network ({detail}). Likely Wi-Fi interference or congestion.",
                f"Very slow local network ({detail}). Wi-Fi is badly congested or the router is overloaded; "
                "try Ethernet.")
    else:
        row("Local router loss", "not tested", None)
        row("Local router latency", "not tested", None)

    # ---- Internet --------------------------------------------------------
    if not inet:
        row("Internet connectivity", "not tested", None)
    elif not live:
        if loc and loc["received"]:
            msg = ("Your router answers but nothing from the internet does. Check the modem/ISP "
                   "(or a firewall blocking ping and TCP 443).")
        else:
            msg = "No replies from the internet at all. Check your connection (or a firewall blocking ping and TCP 443)."
        row("Internet connectivity", "no replies", 2, msg)
    else:
        row("Internet connectivity", "reachable", 0)

        for key in blocked:  # judged separately so they don't masquerade as "100% packet loss"
            name, hint = BLOCKED_HINTS[key]
            row(name, "no replies", 1, hint)

        wk = max(live, key=lambda k: live[k]["loss"])
        v, n, lost = live[wk]["loss"], INET_NAMES[wk], live[wk]["lost"]
        row("Internet packet loss", f"{v}% ({lost} lost, {n})", rate_loss(v, lost, "loss_pct"),
            f"Minor internet packet loss ({v}% on {n}). You may notice occasional stutter.",
            f"High internet packet loss ({v}% on {n}). This causes rubberbanding in games and drops in video calls.")

        v, n = _worst(live, "avg")
        row("Internet latency (avg)", f"{v} ms ({n})", rate_high(v, "latency_avg_ms"),
            f"Latency is higher than ideal ({v} ms on {n}); competitive gaming will feel sluggish.",
            f"Very high latency ({v} ms on {n}); games and video calls will feel badly delayed.")

        v, n = _worst(live, "p99")
        row("Latency spikes (P99)", f"{v} ms ({n})", rate_high(v, "latency_p99_ms"),
            f"Ping spikes detected (P99 {v} ms on {n}). Fine for browsing, but real-time gaming may feel delayed.",
            f"Severe latency spikes (P99 {v} ms on {n}); games will stutter and calls will glitch.")

        v, n = _worst(live, "jitter")
        row("Jitter", f"{v} ms ({n})", rate_high(v, "jitter_ms"),
            f"High jitter ({v} ms on {n}). Voice/video calls and games will feel uneven.",
            f"Severe jitter ({v} ms on {n}); voice/video calls and games will be unreliable.")

        v, n = _worst(live, "max_outage_s")
        row("Connection dropouts", f"longest {v} s ({n})", rate_high(v, "outage_s"),
            f"Connection dropout: the internet went silent for {v} s ({n}). Games may freeze or disconnect.",
            f"Severe dropout: the internet went silent for {v} s ({n}). Games will disconnect and calls will drop.")

    hop = first_isp_hop(hops, gateway)
    if hop:
        row("First ISP hop latency", f"{hop['avg_ms']} ms ({hop['ip']})", rate_high(hop["avg_ms"], "first_hop_ms"),
            f"Slow first ISP hop ({hop['ip']}: {hop['avg_ms']} ms). The delay is between your router and your ISP.",
            f"Very slow first ISP hop ({hop['ip']}: {hop['avg_ms']} ms). The problem is on your ISP line "
            "(cable/fiber/DSL) or ISP congestion, not your Wi-Fi.")
    else:
        row("First ISP hop latency", "not measured", None)

    # ---- DNS / IP --------------------------------------------------------
    if dns:
        fails, total = dns["failures"], dns["total"]
        fail_lvl = 0 if not fails else (2 if fails * 2 >= total else 1)
        level = _max_level(fail_lvl, rate_high(dns["avg"], "dns_ms"))
        public = {r: d["avg"] for r, d in (dns.get("public") or {}).items() if d and d["avg"] is not None}
        if fail_lvl:
            msg = f"{fails} of {total} DNS lookups failed. Try a different DNS server (e.g. 1.1.1.1 or 8.8.8.8)."
        elif public and min(public.values()) < dns["avg"] / 2:
            best = min(public, key=public.get)
            msg = (f"Slow DNS ({dns['avg']} ms average) while {best} answers in {public[best]} ms. "
                   f"Switching your DNS server to {best} should make page loads snappier.")
        else:
            msg = f"Slow DNS ({dns['avg']} ms average). Try a faster DNS server."
        row("DNS", format_dns(dns), level, msg)
    else:
        row("DNS", "not tested", None)

    row("IP type", "CG-NAT likely (shared IP)" if cgnat else "Public IP", 1 if (cgnat and CGNAT_AFFECTS_GRADE) else 0,
        "A hop in the shared 100.64.0.0/10 range was found on your route, which usually means your ISP shares "
        "one public IP between customers (CG-NAT). This is a heuristic: to confirm, compare the WAN/Internet IP "
        "on your router's status page with the IPv4 shown above. If they differ (or it starts with 100.64-100.127) "
        "it is CG-NAT: expect strict NAT types and trouble hosting or joining multiplayer games; ask your ISP "
        "for a public IP.")
    return rows


def summarize(rows, stats, speed):
    """Overall grade = worst individual rating. Returns (quality, color, text)."""
    issues = sorted((r for r in rows if r["level"]), key=lambda r: -r["level"])
    if not issues:
        inet = [stats[k] for k in INET_NAMES if stats.get(k) and stats[k]["received"]]
        bits = []
        if inet:
            bits.append(f"{max(s['loss'] for s in inet)}% packet loss")
            avgs = [s["avg"] for s in inet if s["avg"] is not None]
            if avgs:
                bits.append(f"{max(avgs)} ms worst average latency")
            jit = [s["jitter"] for s in inet if s["jitter"] is not None]
            if jit:
                bits.append(f"{max(jit)} ms jitter")
        if speed.get("status") == "Success":
            bits.append(f"{speed['down']} Mbps down / {speed['up']} Mbps up")
        text = "All tests passed: this network is excellent for competitive gaming, 4K streaming and video meetings"
        text += f" ({', '.join(bits)})." if bits else "."
        if speed.get("status") != "Success":
            text += " Bandwidth was not tested, so download/upload capacity is unverified."
        return "GOOD", COLOR_GOOD, text
    level = issues[0]["level"]
    text = " ".join(r["message"] for r in issues)
    if level == 2:
        text = "At least one test shows a severe problem. " + text
    return ("BAD" if level == 2 else "MEDIUM"), (COLOR_BAD if level == 2 else COLOR_MEDIUM), text
