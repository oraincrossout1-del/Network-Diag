"""Public IPv4/IPv6 lookup."""

import concurrent.futures
import ipaddress
import urllib.request


def fetch_ip(url, timeout=3):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            text = resp.read().decode().strip()
        ipaddress.ip_address(text)  # rejects captive-portal HTML etc.
        return text
    except Exception:
        return None


def get_ip_info(cgnat):
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f4 = ex.submit(fetch_ip, "https://api.ipify.org")
        f6 = ex.submit(fetch_ip, "https://api6.ipify.org")
        v4, v6 = f4.result(), f6.result()
    return {
        "ipv4": v4 or "Unknown",
        "ipv6": v6 or "Not detected",
        "type": "Shared (CG-NAT likely)" if cgnat else "Public",
    }
