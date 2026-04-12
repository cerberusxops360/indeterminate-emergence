"""
Experiment 6: Active Burst Injection

Send bursts of concurrent requests and measure response time distributions.
Tests whether the event loop queuing behavior under concurrent load leaks
path information — the H4 "event loop starvation" attack vector.

Each burst: BURST_SIZE requests fired simultaneously via asyncio.gather.
BURST_COUNT bursts per path.

Run from poc/ directory (proxy must be running on BASE_URL):
    uvicorn src.proxy:app --port 8100
    python -m eval.burst_injection
"""

import asyncio
import sys
import time
from pathlib import Path

import httpx
import numpy as np
from scipy import stats

from src.config import ALL_TOOLS, SessionConfig
from src.proxy import session_store

RESULTS_DIR = Path(__file__).parent / "results"
BASE_URL = "http://localhost:8100"
BURST_SIZE = 10    # concurrent requests per burst
BURST_COUNT = 50   # bursts per path — total 500 requests per path
KS_ALPHA = 0.05
TOOL = "web_search"
PARAMS = {"query": "test"}


def _setup_sessions() -> None:
    session_store.register(SessionConfig(
        session_id="burst_authorized",
        authorized_tools=ALL_TOOLS.copy(),
        budget=100000.0,
        per_query_epsilon=0.001,
        absorption_margin=0.0,
    ))
    session_store.register(SessionConfig(
        session_id="burst_unauthorized",
        authorized_tools=[],
        budget=100000.0,
        per_query_epsilon=0.001,
        absorption_margin=0.0,
    ))


async def _single_request(client: httpx.AsyncClient, session_id: str) -> float:
    """Fire one request, return RTT in milliseconds."""
    start = time.perf_counter_ns()
    await client.post(f"{BASE_URL}/action", json={
        "tool": TOOL,
        "params": PARAMS,
        "session_id": session_id,
    })
    return (time.perf_counter_ns() - start) / 1e6


async def _burst(client: httpx.AsyncClient, session_id: str, size: int) -> list[float]:
    """Fire `size` requests concurrently, return list of RTTs."""
    tasks = [_single_request(client, session_id) for _ in range(size)]
    return list(await asyncio.gather(*tasks))


async def _collect_bursts(session_id: str, label: str) -> np.ndarray:
    """Run BURST_COUNT bursts of BURST_SIZE requests. Returns all RTTs."""
    all_rtts: list[float] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(BURST_COUNT):
            if i % 10 == 0:
                print(f"  {label}: burst {i}/{BURST_COUNT}...", flush=True)
            rtts = await _burst(client, session_id, BURST_SIZE)
            all_rtts.extend(rtts)
    return np.array(all_rtts, dtype=np.float64)


def run_burst_injection() -> bool:
    RESULTS_DIR.mkdir(exist_ok=True)
    _setup_sessions()

    print("Experiment 6: Active Burst Injection")
    print("=" * 70)
    print(f"Burst size: {BURST_SIZE} concurrent requests")
    print(f"Bursts per path: {BURST_COUNT} ({BURST_SIZE * BURST_COUNT} total requests per path)")
    print()

    # Check proxy is reachable
    try:
        import httpx as _httpx
        with _httpx.Client(timeout=5.0) as c:
            c.post(f"{BASE_URL}/action", json={"tool": "calculator", "params": {},
                                                "session_id": "burst_authorized"})
    except Exception as e:
        print(f"ERROR: Proxy not reachable at {BASE_URL}: {e}")
        print("Start the proxy first: uvicorn src.proxy:app --port 8100")
        return False

    loop = asyncio.new_event_loop()
    auth_ms = loop.run_until_complete(
        _collect_bursts("burst_authorized", "authorized")
    )
    unauth_ms = loop.run_until_complete(
        _collect_bursts("burst_unauthorized", "unauthorized")
    )
    loop.close()

    np.save(RESULTS_DIR / "burst_injection_authorized.npy", auth_ms)
    np.save(RESULTS_DIR / "burst_injection_unauthorized.npy", unauth_ms)

    ks_stat, ks_p = stats.ks_2samp(auth_ms, unauth_ms)
    ks_pass = ks_p >= KS_ALPHA

    # Tail analysis — large tail divergence is the H4 signature
    tail_diff_p95 = abs(np.percentile(auth_ms, 95) - np.percentile(unauth_ms, 95))
    tail_diff_p99 = abs(np.percentile(auth_ms, 99) - np.percentile(unauth_ms, 99))

    # Within-burst variance: measures queuing effect
    # Reshape to (BURST_COUNT, BURST_SIZE) and compute per-burst std
    auth_reshaped = auth_ms.reshape(BURST_COUNT, BURST_SIZE)
    unauth_reshaped = unauth_ms.reshape(BURST_COUNT, BURST_SIZE)
    auth_burst_std = auth_reshaped.std(axis=1).mean()
    unauth_burst_std = unauth_reshaped.std(axis=1).mean()

    lines = [
        "Experiment 6: Active Burst Injection",
        "=" * 70,
        f"Burst size: {BURST_SIZE}  |  Bursts: {BURST_COUNT}  |  "
        f"Total per path: {BURST_SIZE * BURST_COUNT}",
        "",
        "RTT distribution (milliseconds):",
        f"  {'':30} {'authorized':>14} {'unauthorized':>14}",
        "  " + "-" * 60,
        f"  {'mean':<30} {auth_ms.mean():>14.3f} {unauth_ms.mean():>14.3f}",
        f"  {'std':<30} {auth_ms.std():>14.3f} {unauth_ms.std():>14.3f}",
        f"  {'p50':<30} {np.percentile(auth_ms, 50):>14.3f} {np.percentile(unauth_ms, 50):>14.3f}",
        f"  {'p95':<30} {np.percentile(auth_ms, 95):>14.3f} {np.percentile(unauth_ms, 95):>14.3f}",
        f"  {'p99':<30} {np.percentile(auth_ms, 99):>14.3f} {np.percentile(unauth_ms, 99):>14.3f}",
        f"  {'max':<30} {auth_ms.max():>14.3f} {unauth_ms.max():>14.3f}",
        "",
        "Burst queuing (within-burst std, mean over all bursts):",
        f"  authorized:   {auth_burst_std:.3f}ms",
        f"  unauthorized: {unauth_burst_std:.3f}ms",
        "  (Large difference here = event loop starvation from CPU-bound path)",
        "",
        "Tail divergence (absolute difference):",
        f"  |p95_auth - p95_unauth| = {tail_diff_p95:.3f}ms",
        f"  |p99_auth - p99_unauth| = {tail_diff_p99:.3f}ms",
        "  (Agora H4 signature: tail divergence > 20ms under burst)",
        "",
        f"  KS statistic:  {ks_stat:.6f}",
        f"  KS p-value:    {ks_p:.6f}",
        f"  KS result:     {'PASS' if ks_pass else 'FAIL'} (alpha={KS_ALPHA})",
        "",
        "=" * 70,
        f"Overall: {'PASS' if ks_pass else 'FAIL'}",
    ]

    summary = "\n".join(lines)
    print()
    print(summary)

    summary_path = RESULTS_DIR / "burst_injection_summary.txt"
    summary_path.write_text(summary + "\n")
    print(f"\nRaw data: {RESULTS_DIR}/burst_injection_*.npy")
    print(f"Summary:  {summary_path}")

    return ks_pass


if __name__ == "__main__":
    success = run_burst_injection()
    sys.exit(0 if success else 1)
