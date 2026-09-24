"""Console output: progress bar and the end-of-run summary table."""

import sys
import textwrap


def print_progress(elapsed, duration):
    frac = min(elapsed / duration, 1.0)
    filled = int(40 * frac)
    sys.stdout.write(f"\r[STRESS TESTING] [{'#' * filled}{'-' * (40 - filled)}] "
                     f"{int(frac * 100)}% | {int(elapsed)}/{duration}s ")
    sys.stdout.flush()


def print_console_summary(findings, verdict):
    labels = {0: "GOOD", 1: "MEDIUM", 2: "BAD", None: "n/a"}
    width = max(len(r["test"]) for r in findings)
    print("-" * 78)
    for r in findings:
        print(f"  {r['test']:<{width}}  {labels[r['level']]:<7} {str(r['value'])[:60]}")
    print("-" * 78)
    print(f"Verdict: {verdict[0]}")
    print(textwrap.fill(verdict[2], 78))
