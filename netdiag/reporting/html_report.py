"""The self-contained HTML report (inline SVG + a small inline script, no CDN)."""

import html
import json
import webbrowser

from netdiag.analysis import rate_loss
from netdiag.config import SERIES_DEFS
from netdiag.utils import fmt, format_dns, in_cgnat


HTML_CSS = """
body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f172a; color: #f8fafc;
       padding: 20px; margin: 0 auto; max-width: 1200px; }
.summary-box { background: #1e293b; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 15px; margin-bottom: 20px; }
.card { background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #334155; }
.panel { background: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 20px; }
.bad { color: #fca5a5; font-weight: bold; }
.warn { color: #fcd34d; font-weight: bold; }
.good { color: #86efac; font-weight: bold; }
.muted { color: #94a3b8; font-size: 0.85em; }
h2, h3, h4 { color: #38bdf8; margin-top: 0; }
.value { font-size: 1.6em; font-weight: bold; margin: 5px 0; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 10px; border-bottom: 1px solid #334155; text-align: left; vertical-align: top; }
th { background: #020617; }
.meta { display: flex; flex-wrap: wrap; gap: 8px 24px; font-size: 0.9em; }
.legend { display: flex; flex-wrap: wrap; gap: 4px 8px; margin: 0 0 10px; font-size: 0.85em; color: #cbd5e1; }
.chip { background: none; border: 1px solid transparent; border-radius: 6px; color: inherit; font: inherit; cursor: pointer; padding: 3px 8px; }
.chip:hover { background: #334155; }
.chip:focus-visible { outline: 2px solid #38bdf8; outline-offset: 1px; }
.chip.off { opacity: 0.45; text-decoration: line-through; }
.chip i { display: inline-block; width: 14px; height: 3px; margin-right: 6px; vertical-align: middle; border-radius: 2px; }
.chip i.band { height: 10px; opacity: 0.4; }
.chartwrap { position: relative; }
svg.chart { width: 100%; height: auto; display: block; touch-action: pan-y; }
.tip { position: absolute; pointer-events: none; z-index: 2; background: #020617; border: 1px solid #334155; border-radius: 6px; padding: 6px 9px; font-size: 12px; line-height: 1.5; white-space: nowrap; }
.hopbar { background: #0f172a; border-radius: 4px; height: 10px; min-width: 120px; }
.hopbar > div { background: #f59e0b; height: 100%; border-radius: 4px; }
@media (max-width: 640px) {  /* phones: stack each table row instead of squeezing the columns */
  .stack table, .stack tbody, .stack tr, .stack td { display: block; }
  .stack tr:first-child { display: none; }
  .stack tr { padding: 8px 0; border-bottom: 1px solid #334155; }
  .stack td { border: 0; padding: 2px 6px; }
}
"""


def _clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 60}:{seconds % 60:02d}"


def timeline_data(raw, duration, stats):
    """Data for the interactive timeline (embedded in the page as JSON), or None if no samples."""
    series = [{"key": k, "label": label, "color": color, "short": short,
               "pts": [[s["time"], s["rtt"]] for s in raw[k]]}
              for k, label, color, short in SERIES_DEFS if raw.get(k)]
    if not series:
        return None
    return {"duration": duration, "series": series,
            "outages": {s["key"]: [[o["start"], o["duration"]] for o in (stats.get(s["key"]) or {}).get("outages", [])]
                        for s in series}}


def timeline_html(data):
    """Legend (click a name to hide/show it) + the SVG canvas the inline script draws into."""
    if data is None:
        return '<p class="muted">No samples were collected.</p>'
    e = html.escape
    chips = "".join(
        f'<button type="button" class="chip" data-key="{e(s["key"])}" aria-pressed="true">'
        f'<i style="background:{s["color"]}"></i>{e(s["label"])}</button>' for s in data["series"])
    chips += ('<button type="button" class="chip" data-kind="lost" aria-pressed="true">'
              '<i style="background:#ef4444"></i>Lost probe</button>'
              '<button type="button" class="chip" data-kind="outage" aria-pressed="true">'
              '<i class="band" style="background:#ef4444"></i>Outage (3+ lost in a row)</button>')
    return ('<div class="muted" style="margin-bottom: 8px;">Click a name to hide or show it (the scale adjusts). '
            'Hover the chart to read the value of every visible line at that moment.</div>'
            f'<div class="legend" id="tl-legend">{chips}</div>'
            '<div class="chartwrap"><svg id="tl" class="chart" viewBox="0 0 1000 320" role="img" '
            'aria-label="Latency timeline of all concurrent probes; gaps and red ticks are lost packets" '
            'font-family="Segoe UI, system-ui, sans-serif" font-size="11"></svg>'
            '<div id="tl-tip" class="tip" hidden></div></div>'
            '<noscript><p class="muted">The interactive chart needs JavaScript; the numbers above are unaffected.</p></noscript>'
            '<div class="muted" id="tl-note"></div>')


# Inline chart script: no library, no network. Redraws on every legend click so the Y scale
# always fits the lines that are visible; hover shows the nearest sample of each visible line.
HTML_JS = """
(function () {
  var D = __DATA__;
  var svg = document.getElementById('tl'), tip = document.getElementById('tl-tip');
  var note = document.getElementById('tl-note'), wrap = svg.parentNode;
  var NS = 'http://www.w3.org/2000/svg';
  var W = 1000, H = 320, L = 56, R = 14, T = 12, B = 40, PW = W - L - R, PH = H - T - B;
  var hidden = {}, hideLost = false, hideOutage = false, view = null;

  function mk(tag, attrs, text) {
    var el = document.createElementNS(NS, tag);
    for (var k in attrs) el.setAttribute(k, attrs[k]);
    if (text !== undefined) el.textContent = text;
    return el;
  }
  function niceStep(span, ticks) {
    var raw = Math.max(span, 1e-9) / Math.max(1, ticks);
    var mag = Math.pow(10, Math.floor(Math.log10(raw))), m = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < m.length; i++) if (raw <= m[i] * mag) return m[i] * mag;
    return 10 * mag;
  }
  function num(v) { return String(+v.toFixed(2)); }
  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) {
    return {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]; }); }
  function nearest(pts, t) {
    var lo = 0, hi = pts.length - 1;
    if (hi < 0) return -1;
    while (hi - lo > 1) { var mid = (lo + hi) >> 1; if (pts[mid][0] < t) lo = mid; else hi = mid; }
    return Math.abs(pts[lo][0] - t) <= Math.abs(pts[hi][0] - t) ? lo : hi;
  }

  function draw() {
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    tip.hidden = true;
    var vis = D.series.filter(function (s) { return !hidden[s.key]; });
    var xmax = Math.max(1, D.duration);
    D.series.forEach(function (s) { if (s.pts.length) xmax = Math.max(xmax, s.pts[s.pts.length - 1][0]); });
    var rtts = [];
    vis.forEach(function (s) { s.pts.forEach(function (p) { if (p[1] !== null) rtts.push(p[1]); }); });
    rtts.sort(function (a, b) { return a - b; });
    var top = 1;  // Y axis is capped so one huge spike can't flatten everything else
    if (rtts.length) {
      var p995 = rtts[Math.min(rtts.length - 1, Math.max(0, Math.ceil(0.995 * rtts.length) - 1))];
      top = Math.max(1, Math.min(rtts[rtts.length - 1], Math.max(25, p995 * 1.5)));
    }
    var ystep = niceStep(top, 5), ymax = Math.ceil(top / ystep - 1e-9) * ystep;
    function X(t) { return L + Math.min(t, xmax) / xmax * PW; }
    function Y(v) { return T + (1 - Math.min(v, ymax) / ymax) * PH; }
    view = {xmax: xmax, X: X, Y: Y, vis: vis};

    var i, v;
    for (i = 0; i <= Math.round(ymax / ystep); i++) {
      v = i * ystep;
      svg.appendChild(mk('line', {x1: L, x2: W - R, y1: Y(v), y2: Y(v), stroke: '#334155'}));
      svg.appendChild(mk('text', {x: L - 8, y: Y(v) + 4, 'text-anchor': 'end', fill: '#94a3b8'}, num(v)));
    }
    var xstep = niceStep(xmax, 8);
    for (i = 0; i <= Math.floor(xmax / xstep + 1e-9); i++) {
      v = i * xstep;
      svg.appendChild(mk('line', {x1: X(v), x2: X(v), y1: T + PH, y2: T + PH + 5, stroke: '#64748b'}));
      svg.appendChild(mk('text', {x: X(v), y: T + PH + 18, 'text-anchor': 'middle', fill: '#94a3b8'}, num(v)));
    }
    svg.appendChild(mk('text', {x: L + PW / 2, y: H - 6, 'text-anchor': 'middle', fill: '#cbd5e1'}, 'Seconds into test'));
    svg.appendChild(mk('text', {transform: 'rotate(-90 13 ' + (T + PH / 2) + ')', x: 13, y: T + PH / 2,
                                'text-anchor': 'middle', fill: '#cbd5e1'}, 'Round-trip (ms)'));

    if (!hideOutage) vis.forEach(function (s) {
      (D.outages[s.key] || []).forEach(function (o) {
        var x0 = X(o[0]), x1 = X(o[0] + o[1]);
        svg.appendChild(mk('rect', {x: x0, y: T, width: Math.max(2, x1 - x0), height: PH, fill: '#ef4444', opacity: 0.16}));
      });
    });

    var off = [], clipped = 0;
    vis.forEach(function (s) {
      var d = '', seg = [];
      function flush() { if (seg.length) { if (seg.length === 1) seg.push(seg[0]); d += 'M' + seg.join('L'); seg = []; } }
      s.pts.forEach(function (p) {
        if (p[1] === null) { flush(); return; }
        seg.push(X(p[0]).toFixed(1) + ' ' + Y(p[1]).toFixed(1));
        if (p[1] > ymax) { clipped++; off.push({v: p[1], t: p[0], c: s.color}); }
      });
      flush();
      if (d) svg.appendChild(mk('path', {d: d, fill: 'none', stroke: s.color, 'stroke-width': 1.2,
                                         'stroke-linejoin': 'round', 'stroke-linecap': 'round'}));
    });
    off.sort(function (a, b) { return b.v - a.v; }).slice(0, 60).forEach(function (o) {  // off-scale samples
      var x = X(o.t);
      svg.appendChild(mk('path', {d: 'M' + (x - 4) + ' ' + (T + 9) + 'L' + (x + 4) + ' ' + (T + 9) + 'L' + x + ' ' + T + 'Z', fill: o.c}));
    });

    if (!hideLost) {
      var seen = {}, d2 = '';
      vis.forEach(function (s) { s.pts.forEach(function (p) {
        if (p[1] === null) { var x = X(p[0]).toFixed(1); if (!seen[x]) { seen[x] = 1; d2 += 'M' + x + ' ' + (T + PH) + 'v-9'; } }
      }); });
      if (d2) svg.appendChild(mk('path', {d: d2, stroke: '#ef4444', 'stroke-width': 1.3, fill: 'none'}));
    }
    svg.appendChild(mk('path', {d: 'M' + L + ' ' + T + 'V' + (T + PH) + 'H' + (W - R), stroke: '#64748b', fill: 'none'}));

    if (!vis.length) {
      svg.appendChild(mk('text', {x: L + PW / 2, y: T + PH / 2, 'text-anchor': 'middle', fill: '#94a3b8', 'font-size': 14},
                         'All lines are hidden - click a name above to show it again.'));
    }
    view.cross = mk('line', {y1: T, y2: T + PH, stroke: '#94a3b8', 'stroke-dasharray': '3 3', visibility: 'hidden'});
    view.dots = mk('g', {});
    svg.appendChild(view.cross); svg.appendChild(view.dots);
    note.textContent = clipped ? clipped + ' sample(s) above ' + num(ymax) + ' ms are drawn as triangles on the top edge (worst: ' +
                       num(rtts[rtts.length - 1]) + ' ms). Hover to read their values.' : '';
  }

  function pick(pts, t, sy) {
    // Dense lines (10 probes/s) have several samples under one pixel: choose the one closest to the
    // cursor's height, so a single-sample spike can be hovered instead of its neighbour.
    var i = nearest(pts, t);
    if (i < 0) return null;
    var best = pts[i], bestD = Infinity, x0 = view.X(t);
    function dist(p) { return Math.abs((p[1] === null ? T + PH - 5 : view.Y(p[1])) - sy); }
    [-1, 1].forEach(function (dir) {
      for (var j = i; j >= 0 && j < pts.length; j += dir) {
        if (Math.abs(view.X(pts[j][0]) - x0) > 2) break;
        var d = dist(pts[j]);
        if (d < bestD) { bestD = d; best = pts[j]; }
      }
    });
    return best;
  }
  function hideTip() {
    tip.hidden = true;
    if (view && view.cross) { view.cross.setAttribute('visibility', 'hidden'); while (view.dots.firstChild) view.dots.removeChild(view.dots.firstChild); }
  }
  function onMove(ev) {
    if (!view || !view.vis.length) return;
    var r = svg.getBoundingClientRect(), sx = (ev.clientX - r.left) * W / r.width;
    var sy = (ev.clientY - r.top) * H / r.height;
    if (sx < L || sx > W - R) { hideTip(); return; }
    var t = (sx - L) / PW * view.xmax, html = '', head = null;
    while (view.dots.firstChild) view.dots.removeChild(view.dots.firstChild);
    view.vis.forEach(function (s) {
      var p = pick(s.pts, t, sy), val;
      if (!p) return;
      if (head === null || Math.abs(p[0] - t) < Math.abs(head - t)) head = p[0];
      if (p[1] === null) val = '<b style="color:#fca5a5">lost</b>';
      else {
        val = '<b>' + num(p[1]) + ' ms</b>';
        view.dots.appendChild(mk('circle', {cx: view.X(p[0]), cy: view.Y(p[1]), r: 3.5, fill: s.color, stroke: '#0f172a'}));
      }
      html += '<div><span style="color:' + s.color + '">&#9679;</span> ' + esc(s.short) + ': ' + val +
              ' <span style="color:#94a3b8">@ ' + num(p[0]) + ' s</span></div>';
    });
    view.cross.setAttribute('x1', view.X(t)); view.cross.setAttribute('x2', view.X(t));
    view.cross.setAttribute('visibility', 'visible');
    tip.innerHTML = '<div style="color:#94a3b8;margin-bottom:2px">t = ' + num(t) + ' s</div>' + html;
    tip.hidden = false;
    var wr = wrap.getBoundingClientRect(), x = ev.clientX - wr.left + 14, y = ev.clientY - wr.top + 10;
    if (x + tip.offsetWidth > wr.width) x = ev.clientX - wr.left - tip.offsetWidth - 14;
    tip.style.left = Math.max(0, x) + 'px';
    tip.style.top = Math.max(0, Math.min(y, wr.height - tip.offsetHeight)) + 'px';
  }

  document.querySelectorAll('#tl-legend .chip').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var off = btn.getAttribute('aria-pressed') === 'true';   // currently on -> turn off
      btn.setAttribute('aria-pressed', off ? 'false' : 'true');
      btn.classList.toggle('off', off);
      var key = btn.getAttribute('data-key'), kind = btn.getAttribute('data-kind');
      if (key) hidden[key] = off; else if (kind === 'lost') hideLost = off; else hideOutage = off;
      draw();
    });
  });
  svg.addEventListener('pointermove', onMove);
  svg.addEventListener('pointerdown', onMove);
  svg.addEventListener('pointerleave', hideTip);
  draw();
})();
"""


def hop_table_html(hops, gateway):
    if not hops:
        return ('<p class="muted">No route data (traceroute/tracert/tracepath is missing or was '
                'blocked).</p>')
    e = html.escape
    top = max([h["avg_ms"] for h in hops if h["avg_ms"] is not None] or [1.0]) or 1.0
    rows = []
    for h in hops:
        tag = ""
        if h["ip"] and h["ip"] == gateway:
            tag = ' <span class="muted">(your router)</span>'
        elif h["ip"] and in_cgnat(h["ip"]):
            tag = ' <span class="warn">CG-NAT range</span>'
        if h["avg_ms"] is None:
            bar, ms = '<span class="muted">no reply</span>', ""
        else:
            width = max(1.5, h["avg_ms"] / top * 100)
            bar = f'<div class="hopbar"><div style="width:{width:.1f}%"></div></div>'
            ms = f'{h["avg_ms"]} ms'
        rows.append(f'<tr><td>{h["hop"]}</td><td>{e(h["ip"] or "*")}{tag}</td><td>{bar}</td><td>{ms}</td></tr>')
    return ('<div class="table-wrap"><table><tr><th>Hop</th><th>Address</th><th>Latency</th><th></th></tr>'
            + "".join(rows) + "</table></div>")


def build_report_html(ctx):
    e = html.escape
    st, speed, dns, ip = ctx["stats"], ctx["speed"], ctx["dns"], ctx["ip_info"]
    bloat = ctx["bloat"]
    quality, q_color, summary = ctx["verdict"]

    def stat_card(title, s, loss_key="loss_pct"):
        if not s or not s["n"]:
            return (f'<div class="card"><h4>{e(title)}</h4><div class="value">N/A</div>'
                    f'<div class="muted">Not run</div></div>')
        cls = ("good", "warn", "bad")[rate_loss(s["loss"], s["lost"], loss_key)]  # same rule as the scorecard
        return (f'<div class="card"><h4>{e(title)}</h4>'
                f'<div class="value">{fmt(s["avg"], " ms")}</div>'
                f'Loss: <span class="{cls}">{s["loss"]}%</span> | P99: {fmt(s["p99"], " ms")}<br>'
                f'<span class="muted">Jitter: {fmt(s["jitter"], " ms")} | Max: {fmt(s["max"], " ms")} | '
                f'Longest loss streak: {s["max_burst"]} | n={s["n"]}</span></div>')

    if bloat:
        worst = max(bloat, key=lambda b: b["increase"])
        lines = "<br>".join(
            f'{e(b["direction"].title())}: +{b["increase"]} ms ({b["idle"]} &rarr; {b["loaded"]} ms, '
            f'{e(b["grade"])})' for b in bloat)
        loss = max(b["loaded_loss"] for b in bloat)
        bloat_card = (f'<div class="card"><h4>Latency Under Load</h4>'
                      f'<div class="value">+{worst["increase"]} ms</div>{lines}<br>'
                      f'<span class="muted">Worst case shown | Loss under load: {loss}%</span></div>')
    else:
        bloat_card = ('<div class="card"><h4>Latency Under Load</h4><div class="value">N/A</div>'
                      '<div class="muted">Needs a successful speedtest</div></div>')

    source = f' | {e(speed["source"])}' if speed.get("source") else ""
    speed_card = (f'<div class="card"><h4>Speedtest</h4>'
                  f'<div class="value">{fmt(speed["down"], " Mbps")} &darr;</div>'
                  f'<div class="muted">{fmt(speed["up"], " Mbps")} &uarr; | {fmt(speed["ping"], " ms")}{source} | '
                  f'{e(speed["status"])}</div></div>')

    cards = [
        speed_card, bloat_card,
        stat_card("Local Router (1400B)", st.get("local"), "local_loss_pct"),
        stat_card(f"ISP Payload (1400B) \u2192 {ctx['target']}", st.get("heavy")),
        stat_card(f"Micro-Stutter (32B) \u2192 {ctx['target']}", st.get("rapid")),
        stat_card(f"Secondary Target \u2192 {ctx['secondary']}", st.get("secondary")),
        stat_card(f"Game Sync (TCP {ctx['port']})", st.get("tcp")),
    ]

    badges = {0: '<span class="good">GOOD</span>', 1: '<span class="warn">MEDIUM</span>',
              2: '<span class="bad">BAD</span>', None: '<span class="muted">N/A</span>'}
    score_rows = "".join(
        f'<tr><td>{e(r["test"])}</td><td>{e(str(r["value"]))}</td><td>{badges[r["level"]]}</td>'
        f'<td class="muted">{e(r["message"])}</td></tr>' for r in ctx.get("findings", []))

    events = ctx.get("events", [])
    if events:
        event_rows = "".join(
            f'<tr><td>{_clock(ev["t"])}</td><td>{e(ev["source"])}</td><td>{e(ev["kind"])}</td>'
            f'<td class="muted">{e(ev["detail"])}</td></tr>' for ev in events)
        events_html = ('<div class="table-wrap stack"><table><tr><th>At</th><th>Source</th><th>Event</th>'
                       f'<th>Detail</th></tr>{event_rows}</table></div>'
                       '<div class="muted" style="margin-top: 8px;">Events that hit the local router and the '
                       'internet at the same moment point at your Wi-Fi or router; events on the internet '
                       'probes only point at your ISP or the path beyond.</div>')
    else:
        events_html = '<p class="muted">No outages or notable latency spikes were detected.</p>'

    tl_data = timeline_data(ctx["raw"], ctx["duration"], st)
    timeline = timeline_html(tl_data)
    script = ""
    if tl_data is not None:
        script = "<script>" + HTML_JS.replace("__DATA__", json.dumps(tl_data, separators=(",", ":")).replace("<", "\\u003c")) + "</script>"
    hop_html = hop_table_html(ctx["hops"], ctx["gateway"])
    gateway = ctx["gateway"] or "not detected (local test skipped)"
    dns_line = format_dns(dns)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Global Network Diagnostic</title>
    <style>{HTML_CSS}</style>
</head>
<body>
    <div style="text-align: center; margin-bottom: 20px;">
        <h2>Network Analysis ({ctx['duration']}s run)</h2>
        <div class="muted">Generated {e(ctx['generated'])} | Gateway: {e(gateway)} | {e(ctx['platform'])}</div>
    </div>

    <div class="summary-box" style="border-left: 5px solid {q_color};">
        <h3 style="color: {q_color};">Network Quality: {quality}</h3>
        <p>{e(summary)}</p>
        <hr style="border: 1px solid #334155; margin: 15px 0;">
        <div class="meta">
            <span><b>IPv4:</b> {e(ip['ipv4'])}</span>
            <span><b>IPv6:</b> {e(ip['ipv6'])}</span>
            <span><b>IP Type:</b> {e(ip['type'])}</span>
            <span><b>DNS:</b> {e(dns_line)}</span>
        </div>
    </div>

    <div class="panel">
        <h3>Scorecard</h3>
        <div class="muted" style="margin-bottom: 8px;">Every test is graded separately. The overall grade is the
        worst individual result, so one BAD result makes the whole network BAD.</div>
        <div class="table-wrap stack"><table>
            <tr><th>Test</th><th>Result</th><th>Grade</th><th>Detail</th></tr>
            {score_rows}
        </table></div>
    </div>

    <div class="grid">{''.join(cards)}</div>

    <div class="panel">
        <h3>Latency Timeline (concurrent overlay)</h3>
        {timeline}
    </div>

    <div class="panel">
        <h3>Notable events</h3>
        {events_html}
    </div>

    <div class="panel">
        <h3>Hop-by-Hop Route Trace</h3>
        {hop_html}
    </div>

    <div class="muted" style="text-align: center;">Self-contained report: works offline, nothing is loaded from the internet.</div>
    {script}
</body>
</html>"""


def write_report(ctx, out_dir, stamp, open_browser=True):
    path = out_dir / f"network_diagnostic_{stamp}.html"
    path.write_text(build_report_html(ctx), encoding="utf-8")
    if open_browser:
        webbrowser.open(path.as_uri())
    return path
