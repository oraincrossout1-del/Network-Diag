import os
import sys
import re
import time
import socket
import urllib.request
import subprocess
import webbrowser
import concurrent.futures
import json
from datetime import datetime

# ==========================================
# CONFIGURATION
# ==========================================
TARGET_HOST = "8.8.8.8"
TCP_PORT = 443
TEST_DURATION_SEC = 300  # 5 Minutes
RAPID_INTERVAL_SEC = 0.1


def get_default_gateway():
    """Detects gateway on Windows, Mac, or Linux (Ethernet or Wi-Fi)."""
    try:
        if os.name == 'nt':
            output = subprocess.check_output("ipconfig", text=True, errors="ignore")
            for line in output.splitlines():
                if "Default Gateway" in line and ":" in line:
                    ip = line.split(":")[-1].strip()
                    if ip and not ip.startswith("fe80") and ip != "0.0.0.0":
                        return ip
        else:
            output = subprocess.check_output("ip route", shell=True, text=True)
            for line in output.splitlines():
                if "default via" in line:
                    return line.split()[2]
    except Exception:
        pass
    return "192.168.0.1"


def get_ip_info(hops):
    """Detects IPv4, IPv6, and identifies CG-NAT based on RFC 6598 IPs."""
    info = {"ipv4": "Unknown", "ipv6": "Unsupported", "type": "Dynamic / Public"}
    try:
        info["ipv4"] = urllib.request.urlopen("https://api.ipify.org", timeout=3).read().decode()
    except:
        pass
    try:
        info["ipv6"] = urllib.request.urlopen("https://api6.ipify.org", timeout=3).read().decode()
    except:
        pass

    # Check traceroute for CG-NAT gateways (100.64.0.0 - 100.127.255.255)
    cgnat_detected = False
    for h in hops:
        if h['ip'].startswith("100."):
            parts = h['ip'].split('.')
            if len(parts) == 4 and 64 <= int(parts[1]) <= 127:
                cgnat_detected = True
                break

    if cgnat_detected:
        info["type"] = "Shared (CG-NAT Detected)"

    return info, cgnat_detected


def run_speedtest():
    """Runs a bandwidth test prior to the stress test."""
    print("[*] Phase 1: Running Bandwidth Speedtest (This takes ~20 seconds)...")
    try:
        import speedtest
        st = speedtest.Speedtest()
        st.get_best_server()
        down = round(st.download() / 1_000_000, 2)
        up = round(st.upload() / 1_000_000, 2)
        ping = round(st.results.ping, 1)
        return {"down": down, "up": up, "ping": ping, "status": "Success"}
    except Exception as e:
        return {"down": 0, "up": 0, "ping": 0, "status": f"Failed (Ensure speedtest-cli is installed)"}


def threaded_ping_test(target, size, interval, duration_sec):
    results = []
    start_time = time.time()
    end_time = start_time + duration_sec
    while time.time() < end_time:
        cmd = f"ping -n 1 -w 500 -l {size} {target}" if os.name == 'nt' else f"ping -c 1 -W 1 -s {size} {target}"
        proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        rel_time = round(time.time() - start_time, 1)
        match = re.search(r"time[=<]([0-9.]+)\s*ms", proc.stdout)
        if match:
            results.append({"time": rel_time, "rtt": float(match.group(1))})
        else:
            results.append({"time": rel_time, "rtt": None})
        time.sleep(interval)
    return results


def threaded_tcp_ping(target, port, interval, duration_sec):
    results = []
    start_time = time.time()
    end_time = start_time + duration_sec
    while time.time() < end_time:
        call_start = time.time()
        rel_time = round(call_start - start_time, 1)
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)
            sock.connect((target, port))
            rtt = (time.time() - call_start) * 1000
            results.append({"time": rel_time, "rtt": int(rtt)})
            sock.close()
        except Exception:
            results.append({"time": rel_time, "rtt": None})
        time.sleep(interval)
    return results


def test_dns_resolution():
    domains = ["google.com", "cloudflare.com", "steampowered.com", "github.com"]
    dns_times = []
    for domain in domains:
        start = time.time()
        try:
            socket.gethostbyname(domain)
            dns_times.append(int((time.time() - start) * 1000))
        except Exception:
            pass
    return round(sum(dns_times) / len(dns_times), 1) if dns_times else 0


def run_tracert(target):
    hops = []
    cmd = f"tracert -d -h 15 {target}" if os.name == 'nt' else f"traceroute -n -m 15 {target}"
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, shell=True)
        for line in proc.stdout.splitlines():
            match = re.search(r"^\s*(\d+)\s+([\d\*\s<ms.]+)\s+([\d\.]+)", line)
            if match:
                times = re.findall(r"([0-9.]+)\s*ms", match.group(2))
                avg_time = sum(map(float, times)) / len(times) if times else 0
                hops.append({"hop": match.group(1), "ip": match.group(3), "avg_ms": round(avg_time, 1)})
    except Exception:
        pass
    return hops


def evaluate_network(st_loc, st_hvy, st_rap, st_tcp, speed_data, cgnat_detected):
    """Evaluates network health and generates a summary."""

    if st_loc['loss'] >= 1.0:
        return "BAD", "#fca5a5", f"Your local router/Wi-Fi is dropping {st_loc['loss']}% of packets. Move closer to the router or replace the Ethernet cable."

    isp_loss = max(st_hvy['loss'], st_rap['loss'])
    if isp_loss >= 3.0:
        reason = f"High internet packet loss detected ({isp_loss}%). This causes rubberbanding in games and drops in meetings."
        if cgnat_detected:
            reason += " You are on a congested Shared CG-NAT IP. Contact your ISP for a Public IP."
        return "BAD", "#fca5a5", reason

    p99_max = max(st_hvy['p99'], st_rap['p99'])
    if p99_max >= 100:
        return "MEDIUM", "#fcd34d", f"Ping spikes detected (P99: {p99_max}ms). Good enough for browsing, but real-time gaming may feel sluggish or delayed."

    if speed_data['status'] == "Success" and speed_data['down'] < 25.0:
        return "MEDIUM", "#fcd34d", f"Download speed is low ({speed_data['down']} Mbps). Sufficient for browsing, but 4K streaming or large downloads will buffer."

    if cgnat_detected and isp_loss > 0:
        return "MEDIUM", "#fcd34d", "CG-NAT detected with minor packet loss. You may experience strict NAT type issues in multiplayer games."

    return "GOOD", "#86efac", "Network is highly stable with low latency and 0 packet loss. Excellent for competitive gaming, 4K streaming, and online meetings."


def generate_html_report(gateway, local_res, heavy_res, rapid_res, tcp_res, hops, dns_time, speed_data):
    def calc_stats(pings):
        valid = [p["rtt"] for p in pings if p["rtt"] is not None]
        total = len(pings)
        dropped = total - len(valid)
        loss = round((dropped / total) * 100, 1) if total > 0 else 0
        valid.sort()
        p99 = valid[int(len(valid) * 0.99)] if len(valid) > 10 else (max(valid) if valid else 0)
        return {
            "avg": round(sum(valid) / len(valid), 1) if valid else 0,
            "p99": round(p99, 1),
            "loss": loss
        }

    st_loc = calc_stats(local_res)
    st_hvy = calc_stats(heavy_res)
    st_rap = calc_stats(rapid_res)
    st_tcp = calc_stats(tcp_res)

    ip_info, cgnat_detected = get_ip_info(hops)
    quality, q_color, summary_text = evaluate_network(st_loc, st_hvy, st_rap, st_tcp, speed_data, cgnat_detected)

    def prep_chart(data):
        return [p["rtt"] if p["rtt"] is not None else "null" for p in data], [p["time"] for p in data]

    loc_y, loc_x = prep_chart(local_res)
    rap_y, rap_x = prep_chart(rapid_res)
    tcp_y, tcp_x = prep_chart(tcp_res)
    hop_labels = [f"Hop {h['hop']} ({h['ip']})" for h in hops]
    hop_data = [h['avg_ms'] for h in hops]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Global Network Diagnostic</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #f8fafc; padding: 20px; }}
        .summary-box {{ background: #1e293b; padding: 20px; border-radius: 8px; border-left: 5px solid {q_color}; margin-bottom: 20px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: #1e293b; padding: 15px; border-radius: 8px; border: 1px solid #334155; }}
        .chart-box {{ background: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; margin-bottom: 20px; }}
        .bad {{ color: #fca5a5; font-weight: bold; }}
        .good {{ color: #86efac; font-weight: bold; }}
        h2, h3, h4 {{ color: #38bdf8; margin-top: 0; }}
        .value {{ font-size: 1.6em; font-weight: bold; margin: 5px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 10px; border-bottom: 1px solid #334155; text-align: left; }}
        th {{ background: #020617; }}
    </style>
</head>
<body>
    <div style="text-align: center; margin-bottom: 20px;">
        <h2>Network Analysis ({TEST_DURATION_SEC}s Run)</h2>
    </div>

    <div class="summary-box">
        <h3 style="color: {q_color};">Network Quality: {quality}</h3>
        <p>{summary_text}</p>
        <hr style="border: 1px solid #334155; margin: 15px 0;">
        <div style="display: flex; justify-content: space-between; font-size: 0.9em;">
            <span><b>IPv4:</b> {ip_info['ipv4']}</span>
            <span><b>IPv6:</b> {ip_info['ipv6']}</span>
            <span><b>IP Type:</b> {ip_info['type']}</span>
            <span><b>DNS Speed:</b> {dns_time} ms</span>
        </div>
    </div>

    <div class="grid">
        <div class="card">
            <h4>Speedtest</h4>
            <div class="value">{speed_data['down']} Mbps ↓</div>
            <div style="color: #94a3b8;">{speed_data['up']} Mbps ↑ | {speed_data['ping']} ms</div>
        </div>
        <div class="card">
            <h4>Local Router (1400B)</h4>
            <div class="value">{st_loc['avg']} ms</div>
            Loss: <span class="{'bad' if st_loc['loss'] > 0 else 'good'}">{st_loc['loss']}%</span> | P99: {st_loc['p99']} ms
        </div>
        <div class="card">
            <h4>ISP Payload (1400B)</h4>
            <div class="value">{st_hvy['avg']} ms</div>
            Loss: <span class="{'bad' if st_hvy['loss'] > 0 else 'good'}">{st_hvy['loss']}%</span> | P99: {st_hvy['p99']} ms
        </div>
        <div class="card">
            <h4>Micro-Stutter (32B)</h4>
            <div class="value">{st_rap['avg']} ms</div>
            Loss: <span class="{'bad' if st_rap['loss'] > 0 else 'good'}">{st_rap['loss']}%</span> | P99: {st_rap['p99']} ms
        </div>
        <div class="card">
            <h4>Game Sync (TCP)</h4>
            <div class="value">{st_tcp['avg']} ms</div>
            Loss: <span class="{'bad' if st_tcp['loss'] > 0 else 'good'}">{st_tcp['loss']}%</span> | P99: {st_tcp['p99']} ms
        </div>
    </div>

    <div class="chart-box">
        <h3>Latency Timeline (5-Minute Concurrent Overlay)</h3>
        <canvas id="timelineChart" height="80"></canvas>
    </div>

    <div class="chart-box">
        <h3>Hop-by-Hop Route Trace</h3>
        <canvas id="hopChart" height="60"></canvas>
    </div>

    <script>
        new Chart(document.getElementById('timelineChart').getContext('2d'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(rap_x)},
                datasets: [
                    {{ label: 'Micro-Stutter (ISP)', data: {json.dumps(rap_y)}, borderColor: '#38bdf8', borderWidth: 1, pointRadius: 0 }},
                    {{ label: 'Game Layer (TCP)', data: {json.dumps(tcp_y)}, borderColor: '#f43f5e', borderWidth: 1, pointRadius: 0 }},
                    {{ label: 'Local Router', data: {json.dumps(loc_y)}, borderColor: '#22c55e', borderWidth: 1, pointRadius: 0 }}
                ]
            }},
            options: {{ responsive: true, interaction: {{ mode: 'index', intersect: false }}, scales: {{ y: {{ beginAtZero: true }}, x: {{ display: false }} }} }}
        }});

        new Chart(document.getElementById('hopChart').getContext('2d'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(hop_labels)},
                datasets: [{{ label: 'Avg Latency (ms)', data: {json.dumps(hop_data)}, backgroundColor: '#f59e0b', borderRadius: 4 }}]
            }},
            options: {{ responsive: true, scales: {{ y: {{ beginAtZero: true }} }} }}
        }});
    </script>
</body>
</html>"""

    report_path = os.path.abspath("network_diagnostic_results.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)
    webbrowser.open(f"file://{report_path}")


def main():
    os.system('cls' if os.name == 'nt' else 'clear')
    print("=" * 60)
    print("    GLOBAL NETWORK DIAGNOSTIC SUITE".center(60))
    print("=" * 60)
    gateway = get_default_gateway()
    print(f"\n[*] Target: {TARGET_HOST}")
    print(f"[*] Local Gateway: {gateway}")

    # Run sequential bandwidth test first so it doesn't skew ping stats
    speed_data = run_speedtest()
    dns_time = test_dns_resolution()

    print(f"\n[*] Phase 2: Starting {TEST_DURATION_SEC}-second stability stress test...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        f_local = executor.submit(threaded_ping_test, gateway, 1400, 1.0, TEST_DURATION_SEC)
        f_heavy = executor.submit(threaded_ping_test, TARGET_HOST, 1400, 1.0, TEST_DURATION_SEC)
        f_rapid = executor.submit(threaded_ping_test, TARGET_HOST, 32, RAPID_INTERVAL_SEC, TEST_DURATION_SEC)
        f_tcp = executor.submit(threaded_tcp_ping, TARGET_HOST, TCP_PORT, 1.0, TEST_DURATION_SEC)
        f_trace = executor.submit(run_tracert, TARGET_HOST)

        poll_interval = 0.5
        total_steps = int(TEST_DURATION_SEC / poll_interval)

        for step in range(total_steps):
            if all([f_local.done(), f_heavy.done(), f_rapid.done(), f_tcp.done()]):
                break
            progress = (step + 1) / total_steps
            bar_len = 40
            filled = int(bar_len * progress)
            bar = '█' * filled + '-' * (bar_len - filled)
            percent = int(progress * 100)
            elapsed = int((step + 1) * poll_interval)

            sys.stdout.write(f"\r[STRESS TESTING] [{bar}] {percent}% | {elapsed}/{TEST_DURATION_SEC}s ")
            sys.stdout.flush()
            time.sleep(poll_interval)

    print("\n\n[*] Analyzing data and generating final report...")
    generate_html_report(gateway, f_local.result(), f_heavy.result(), f_rapid.result(), f_tcp.result(),
                         f_trace.result(), dns_time, speed_data)
    print("[*] Complete! Report opened in your browser.")


if __name__ == "__main__":
    main()
