"""DNS tests: the system resolver vs. public resolvers queried directly over UDP."""

import random
import socket
import struct
import time

from netdiag.config import DNS_DOMAINS, DNS_RESOLVERS


def measure_dns_system(domains=DNS_DOMAINS):
    """Times the OS resolver. Note: the OS/router cache can make repeat lookups look fast."""
    times, failures = [], 0
    for domain in domains:
        t0 = time.perf_counter()  # high-resolution timer (see tcp_worker)
        try:
            socket.getaddrinfo(domain, None, socket.AF_INET)
            times.append((time.perf_counter() - t0) * 1000)
        except OSError:
            failures += 1
    return {
        "avg": round(sum(times) / len(times), 1) if times else None,
        "failures": failures,
        "total": len(domains),
    }


def build_dns_query(domain, qid):
    """Minimal DNS 'A' query packet (recursion desired)."""
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qname = b"".join(bytes([len(label)]) + label.encode("ascii") for label in domain.rstrip(".").split("."))
    return header + qname + b"\x00" + struct.pack(">HH", 1, 1)


def dns_reply_ok(data, qid):
    """True for a response to our query id with RCODE 0 (NOERROR)."""
    if len(data) < 12:
        return False
    rid, flags = struct.unpack(">HH", data[:4])
    return rid == qid and bool(flags & 0x8000) and (flags & 0x000F) == 0


def measure_dns_direct(resolver, domains=DNS_DOMAINS, timeout=2.0):
    """Queries a public resolver directly over UDP, bypassing your OS/router DNS cache."""
    times, failures = [], 0
    for domain in domains:
        qid = random.randrange(0x10000)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                t0 = time.perf_counter()
                sock.sendto(build_dns_query(domain, qid), (resolver, 53))
                data, _ = sock.recvfrom(2048)
                elapsed = (time.perf_counter() - t0) * 1000
            if dns_reply_ok(data, qid):
                times.append(elapsed)
            else:
                failures += 1
        except OSError:
            failures += 1
    return {
        "avg": round(sum(times) / len(times), 1) if times else None,
        "failures": failures,
        "total": len(domains),
    }


def run_dns_tests(domains=DNS_DOMAINS, resolvers=DNS_RESOLVERS):
    result = measure_dns_system(domains)
    result["public"] = {r: measure_dns_direct(r, domains) for r in resolvers}
    return result
