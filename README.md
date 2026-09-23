# Network Diag 🚀

An advanced, automated multi-threaded network diagnostic tool built in Python.

Unlike traditional web-based speed tests that buffer traffic and mask sub-second drops, **Network Diag** performs concurrent stress testing across local, network, and application layers to detect micro-stutters, CG-NAT restrictions, and packet loss that ruin real-time competitive gaming.

---

## 🌟 Features

* **Network Quality Rating System:** Automatically grades connection quality into **GOOD**, **MEDIUM**, or **BAD** based on gaming, 4K streaming, and online meeting thresholds.
* **Concurrent Multi-Layer Stress Testing:** Runs 5-minute parallel diagnostic threads to detect transient latency spikes without choking local bandwidth.
* **Micro-Stutter Detection:** High-frequency (100ms) polling catches sub-second frame skips and lag spikes that standard 1-second pings miss.
* **IP Intelligence & CG-NAT Detection:** Identifies IPv4, IPv6 support, and automatically scans traceroute hops for RFC 6598 carrier-grade NAT address space (`100.64.x.x`).
* **Visual HTML Report:** Generates an interactive Chart.js dashboard displaying overlaid latency timelines, hop-by-hop route traces, and metric summaries.
* **Cross-Platform:** Works out-of-the-box on Windows, macOS, and Linux for both Ethernet and Wi-Fi connections.
* **Retro Terminal UI:** Features an animated console loading bar and real-time execution feedback.

---

## 📊 Diagnostic Test Specifications

| Test Module | Spec / Target | Purpose |
| :--- | :--- | :--- |
| **Bandwidth Test** | `speedtest-cli` | Measures raw Download (Mbps), Upload (Mbps), and Unloaded Ping before stress testing begins. |
| **Local Hardware Check** | Default Gateway (1400B ICMP) | Audits local Ethernet cable, Wi-Fi signal, and router LAN ports. |
| **ISP Line Stress** | `8.8.8.8` (1400B Heavy ICMP) | Simulates heavy packet loads to reveal line noise and MTU fragmentation. |
| **Micro-Stutter Polling** | `8.8.8.8` (32B ICMP @ 100ms) | Rapid polling rate (10 pings/sec) to catch micro-stutters and instant drops. |
| **Application Layer** | TCP Port 443 | Measures application-layer TCP connection latency to monitor retransmission delays. |
| **Route Analytics** | 15-Hop Traceroute | Maps every network hop to isolate CG-NAT gateways and external routing bottlenecks. |

---
