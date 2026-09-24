# Network-Diag 🚀

An advanced, automated multi-threaded network diagnostic tool built in Python.

Unlike traditional web-based speed tests that buffer traffic and mask sub-second drops, **Network-Diag** performs concurrent stress testing across local, network, and application layers to detect micro-stutters, CG-NAT restrictions, packet loss, and bufferbloat that ruin real-time competitive gaming.

---

## 🌟 Features

* **Strict Network Quality Rating:** Grades connection stability as **GOOD**, **MEDIUM**, or **BAD** using a strict "worst-case" policy—a single severe metric marks the entire network BAD.
* **Modular Architecture:** Cleanly separated architecture (Probes, Analysis, Reporting) with CLI flag support (`--duration`, `--no-speedtest`).
* **Micro-Stutter & Drop Detection:** High-frequency polling catches sub-second frame skips and lag spikes that standard pings miss.
* **Bufferbloat & Jitter Analysis:** Measures latency inflation under load to expose network congestion caused by saturated bandwidth.
* **Zero-Dependency Speed Testing:** Uses `speedtest-cli` if installed, or automatically falls back to an offline/built-in Cloudflare speed test (`speed.cloudflare.com`).
* **IP Intelligence & CG-NAT Detection:** Detects IPv4, IPv6 support, and automatically scans traceroute hops for RFC 6598 carrier-grade NAT address space (`100.64.x.x`).
* **Offline Self-Contained HTML Report:** Generates an interactive Chart.js dashboard displaying overlaid latency timelines, hop-by-hop route traces, and metric summaries that work completely offline.
* **Cross-Platform:** Works out-of-the-box on Windows, macOS, and Linux (Python 3.8+) for both Ethernet and Wi-Fi connections.

---

## 📊 Diagnostic Test Specifications

| Test Module | Spec / Target | Purpose |
| :--- | :--- | :--- |
| **Bandwidth & Bufferbloat** | `speedtest-cli` / Cloudflare | Measures Download, Upload, Unloaded Ping, and latency inflation under load. |
| **Local Hardware Check** | Default Gateway (1400B ICMP) | Audits local Ethernet cable, Wi-Fi signal, and router LAN ports. |
| **ISP Line Stress** | `8.8.8.8` / `1.1.1.1` (1400B Heavy ICMP) | Simulates heavy packet loads to reveal line noise and MTU fragmentation. |
| **Micro-Stutter Polling** | `8.8.8.8` (32B ICMP @ 100ms) | High-frequency polling (10 pings/sec) to catch micro-stutters and instant drops. |
| **Application Layer** | TCP Port 443 | Measures application-layer TCP connection latency to monitor retransmission delays. |
| **Route Analytics** | 15-Hop Traceroute | Maps every network hop to isolate CG-NAT gateways and external routing bottlenecks. |

---