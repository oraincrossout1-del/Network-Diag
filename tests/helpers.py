"""Shared test data builders."""
from netdiag.analysis import calc_stats, collect_findings, summarize


def samples(rtts, step=1.0):
    """Probe samples like the workers produce: None = lost probe."""
    return [{"time": round(i * step, 2), "abs": 1000 + i * step, "rtt": r} for i, r in enumerate(rtts)]


SPEED_OK = {"down": 200.0, "up": 20.0, "ping": 10.0, "status": "Success", "windows": {}, "source": "speedtest-cli"}
SPEED_SKIPPED = {"down": None, "up": None, "ping": None, "status": "Skipped", "windows": {}, "source": None}
DNS_OK = {"avg": 20.0, "failures": 0, "total": 4,
          "public": {"1.1.1.1": {"avg": 15.0, "failures": 0, "total": 4}}}


def make_stats(local=None, heavy=None, rapid=None, secondary=None, tcp=None):
    """Stats for every probe. Defaults are a perfectly healthy line (100 samples each)."""
    good = [20.0] * 100
    pick = lambda value, default: calc_stats(samples(default if value is None else value))
    return {"local": pick(local, [1.0] * 100), "heavy": pick(heavy, good), "rapid": pick(rapid, good),
            "secondary": pick(secondary, good), "tcp": pick(tcp, good)}


def make_bloat(direction="download", idle=10.0, increase=0.0, lost=0, n=40):
    return {"direction": direction, "idle": idle, "loaded": idle + increase, "increase": increase,
            "grade": "Excellent" if increase < 30 else "Fair" if increase < 100 else "Poor",
            "loaded_loss": round(lost / n * 100, 1), "loaded_lost": lost, "n": n}


def verdict(stats=None, speed=SPEED_OK, cgnat=False, dns=DNS_OK, bloat=None, hops=None, gateway=None):
    """(grade, colour, text) exactly as main() computes it."""
    stats = stats or make_stats()
    return summarize(collect_findings(stats, speed, cgnat, dns, bloat, hops, gateway), stats, speed)
