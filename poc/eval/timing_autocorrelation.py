"""
Experiment 5: Timing Autocorrelation

Collect 500 server-side execution times (perf_counter_ns) per path by calling
execute() + shape_response() directly, bypassing HTTP. This is the cleanest
measure of what a Level 1 adversary would observe after subtracting network
jitter from RTT.

Two analyses:
  1. Distribution test — are the shaped timing distributions distinguishable
     between the authorized and unauthorized paths?
  2. Autocorrelation — does a sequential series of requests carry temporal
     correlation that leaks which path is running?

Run from poc/ directory:
    python -m eval.timing_autocorrelation
"""

import asyncio
import sys
import time
from pathlib import Path

import numpy as np
from scipy import stats

from src.executor import execute
from src.channel_shaper import shape_response
from src.config import ALL_TOOLS

RESULTS_DIR = Path(__file__).parent / "results"
N_SAMPLES = 500
KS_ALPHA = 0.05
TOOL = "web_search"
PARAMS = {"query": "test"}


async def _timed_request(authorized: bool) -> float:
    """
    Run one full execute + shape cycle. Returns elapsed nanoseconds.
    Equivalent to the server-side work for a single /action request,
    minus FastAPI routing overhead.
    """
    start_ns = time.perf_counter_ns()
    start_mono = time.monotonic()

    await execute(
        tool_name=TOOL,
        params=PARAMS,
        authorized=authorized,
        absorbing=False,
    )
    await shape_response('{"result": null}', start_mono)

    return float(time.perf_counter_ns() - start_ns)


async def _collect(authorized: bool, n: int, label: str) -> np.ndarray:
    samples = np.zeros(n, dtype=np.float64)
    for i in range(n):
        if i % 100 == 0:
            print(f"  {label}: {i}/{n}...", flush=True)
        samples[i] = await _timed_request(authorized)
    return samples


def _autocorrelation(x: np.ndarray, max_lag: int = 20) -> np.ndarray:
    """Normalized autocorrelation at lags 1..max_lag."""
    x = x - x.mean()
    var = np.dot(x, x)
    if var == 0:
        return np.zeros(max_lag)
    acf = np.array([np.dot(x[:-lag], x[lag:]) / var for lag in range(1, max_lag + 1)])
    return acf


def run_timing_autocorrelation() -> bool:
    RESULTS_DIR.mkdir(exist_ok=True)

    print("Experiment 5: Timing Autocorrelation")
    print("=" * 70)
    print(f"Samples per path: {N_SAMPLES}")
    print(f"Measuring: execute() + shape_response() via perf_counter_ns")
    print()

    loop = asyncio.new_event_loop()
    auth_ns = loop.run_until_complete(_collect(authorized=True,  n=N_SAMPLES, label="authorized"))
    unauth_ns = loop.run_until_complete(_collect(authorized=False, n=N_SAMPLES, label="unauthorized"))
    loop.close()

    # Convert to milliseconds for readability
    auth_ms = auth_ns / 1e6
    unauth_ms = unauth_ns / 1e6

    # Save raw data
    np.save(RESULTS_DIR / "timing_autocorrelation_authorized.npy", auth_ns)
    np.save(RESULTS_DIR / "timing_autocorrelation_unauthorized.npy", unauth_ns)

    # Distribution statistics
    ks_stat, ks_p = stats.ks_2samp(auth_ms, unauth_ms)
    ks_pass = ks_p >= KS_ALPHA

    # Autocorrelation at lags 1-10
    auth_acf = _autocorrelation(auth_ms)
    unauth_acf = _autocorrelation(unauth_ms)

    # Max absolute ACF in first 10 lags — a high value indicates temporal leakage
    auth_max_acf = float(np.max(np.abs(auth_acf[:10])))
    unauth_max_acf = float(np.max(np.abs(unauth_acf[:10])))

    lines = [
        "Experiment 5: Timing Autocorrelation",
        "=" * 70,
        f"Samples: {N_SAMPLES} per path",
        "",
        "Distribution statistics (shaped, server-side):",
        f"  {'':30} {'authorized':>14} {'unauthorized':>14}",
        "  " + "-" * 60,
        f"  {'mean (ms)':<30} {auth_ms.mean():>14.3f} {unauth_ms.mean():>14.3f}",
        f"  {'std (ms)':<30} {auth_ms.std():>14.3f} {unauth_ms.std():>14.3f}",
        f"  {'p5 (ms)':<30} {np.percentile(auth_ms, 5):>14.3f} {np.percentile(unauth_ms, 5):>14.3f}",
        f"  {'p50 (ms)':<30} {np.percentile(auth_ms, 50):>14.3f} {np.percentile(unauth_ms, 50):>14.3f}",
        f"  {'p95 (ms)':<30} {np.percentile(auth_ms, 95):>14.3f} {np.percentile(unauth_ms, 95):>14.3f}",
        f"  {'p99 (ms)':<30} {np.percentile(auth_ms, 99):>14.3f} {np.percentile(unauth_ms, 99):>14.3f}",
        "",
        f"  KS statistic:                  {ks_stat:.6f}",
        f"  KS p-value:                    {ks_p:.6f}",
        f"  KS result (alpha={KS_ALPHA}):         "
        f"{'PASS — distributions indistinguishable' if ks_pass else 'FAIL — distributions distinguishable'}",
        "",
        "Autocorrelation (lags 1-10):",
        f"  {'lag':<8} {'authorized':>12} {'unauthorized':>14}",
        "  " + "-" * 36,
    ]

    for lag in range(10):
        lines.append(
            f"  {lag+1:<8} {auth_acf[lag]:>12.4f} {unauth_acf[lag]:>14.4f}"
        )

    lines += [
        "",
        f"  Max |ACF| lags 1-10 — authorized:   {auth_max_acf:.4f}",
        f"  Max |ACF| lags 1-10 — unauthorized: {unauth_max_acf:.4f}",
        "  (Values >0.10 suggest temporal leakage in the timing series)",
        "",
        "=" * 70,
    ]

    dist_pass = ks_pass
    acf_pass = auth_max_acf < 0.10 and unauth_max_acf < 0.10

    lines += [
        f"Distribution indistinguishable: {dist_pass}",
        f"Autocorrelation below threshold: {acf_pass}",
        f"Overall: {'PASS' if dist_pass and acf_pass else 'FAIL'}",
    ]

    summary = "\n".join(lines)
    print()
    print(summary)

    summary_path = RESULTS_DIR / "timing_autocorrelation_summary.txt"
    summary_path.write_text(summary + "\n")
    print(f"\nRaw data: {RESULTS_DIR}/timing_autocorrelation_*.npy")
    print(f"Summary:  {summary_path}")

    return dist_pass and acf_pass


if __name__ == "__main__":
    success = run_timing_autocorrelation()
    sys.exit(0 if success else 1)
