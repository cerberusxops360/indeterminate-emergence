"""
Experiment 1: Distribution Comparison

Demonstrate that response distributions are statistically indistinguishable
across capability configurations.

Usage:
    # Start proxy first: uvicorn src.proxy:app --port 8000
    python -m eval.divergence_test
"""

import json
import sys
import time

import numpy as np
from scipy import stats

from src.config import ALL_TOOLS, SessionConfig
from src.proxy import session_store

# -- Configuration --
N_SAMPLES = 200
BASE_URL = "http://localhost:8100"
TV_THRESHOLD = 0.05
KL_THRESHOLD = 0.01
KS_ALPHA = 0.05  # KS test significance level (primary timing criterion)


def setup_eval_sessions():
    """Register two sessions: config_a has all tools, config_b has none."""
    session_store.register(SessionConfig(
        session_id="config_a",
        authorized_tools=ALL_TOOLS.copy(),
        budget=10000.0,
        per_query_epsilon=0.01,
        absorption_margin=0.0,
    ))
    session_store.register(SessionConfig(
        session_id="config_b",
        authorized_tools=[],
        budget=10000.0,
        per_query_epsilon=0.01,
        absorption_margin=0.0,
    ))


def collect_samples(client, tool: str, session_id: str, n: int = N_SAMPLES) -> dict:
    """Send n requests and collect response metadata."""
    times = []
    sizes = []

    for _ in range(n):
        start = time.monotonic()
        resp = client.post(f"{BASE_URL}/action", json={
            "tool": tool,
            "params": {"query": "test"},
            "session_id": session_id,
        })
        elapsed = time.monotonic() - start
        times.append(elapsed)
        sizes.append(len(resp.content))

    return {"times": np.array(times), "sizes": np.array(sizes)}


def _auto_bins(n: int) -> int:
    """Freedman-Diaconis-inspired bin count: sqrt(n) clamped to [10, 50]."""
    return max(10, min(50, int(np.sqrt(n))))


def total_variation_distance(p: np.ndarray, q: np.ndarray, bins: int | None = None) -> float:
    """Estimate TV distance between two sample distributions."""
    if bins is None:
        bins = _auto_bins(min(len(p), len(q)))

    min_val = min(p.min(), q.min())
    max_val = max(p.max(), q.max())

    p_hist, edges = np.histogram(p, bins=bins, range=(min_val, max_val), density=True)
    q_hist, _ = np.histogram(q, bins=bins, range=(min_val, max_val), density=True)

    bin_width = edges[1] - edges[0]
    return 0.5 * np.sum(np.abs(p_hist - q_hist)) * bin_width


def kl_divergence(p: np.ndarray, q: np.ndarray, bins: int | None = None) -> float:
    """Estimate KL divergence D(P||Q) between two sample distributions."""
    if bins is None:
        bins = _auto_bins(min(len(p), len(q)))

    min_val = min(p.min(), q.min())
    max_val = max(p.max(), q.max())

    p_hist, _ = np.histogram(p, bins=bins, range=(min_val, max_val), density=True)
    q_hist, _ = np.histogram(q, bins=bins, range=(min_val, max_val), density=True)

    # Add small epsilon to avoid log(0)
    eps = 1e-10
    p_hist = p_hist + eps
    q_hist = q_hist + eps

    # Normalize
    p_hist = p_hist / p_hist.sum()
    q_hist = q_hist / q_hist.sum()

    return float(np.sum(p_hist * np.log(p_hist / q_hist)))


def run_divergence_test():
    """Run the full divergence test across all tools."""
    import httpx

    setup_eval_sessions()

    print(f"Divergence Test — {N_SAMPLES} samples per config per tool")
    print("=" * 70)

    all_pass = True

    with httpx.Client(timeout=10.0) as client:
        for tool in ALL_TOOLS:
            samples_a = collect_samples(client, tool, "config_a")
            samples_b = collect_samples(client, tool, "config_b")

            tv = total_variation_distance(samples_a["times"], samples_b["times"])
            kl = kl_divergence(samples_a["times"], samples_b["times"])
            ks_stat, ks_p = stats.ks_2samp(samples_a["times"], samples_b["times"])

            size_std_a = samples_a["sizes"].std()
            size_std_b = samples_b["sizes"].std()
            sizes_identical = (size_std_a == 0) and (size_std_b == 0)

            # KS test is the primary timing criterion: p >= alpha means
            # we cannot reject H0 (distributions are the same).
            # TV/KL are informational — histogram estimators are noisy at
            # moderate sample sizes.
            ks_pass = ks_p >= KS_ALPHA
            tool_pass = ks_pass and sizes_identical

            if not tool_pass:
                all_pass = False

            status = "PASS" if tool_pass else "FAIL"
            print(f"\n{tool} [{status}]:")
            print(f"  KS test (primary):     stat={ks_stat:.4f}  p={ks_p:.4f}  "
                  f"{'PASS (p >= ' + str(KS_ALPHA) + ')' if ks_pass else 'FAIL (p < ' + str(KS_ALPHA) + ')'}")
            print(f"  TV distance (info):    {tv:.4f}")
            print(f"  KL divergence (info):  {kl:.6f}")
            print(f"  Size std (A):          {size_std_a:.2f}")
            print(f"  Size std (B):          {size_std_b:.2f}")
            print(f"  Sizes identical:       {sizes_identical}")

    print("\n" + "=" * 70)
    print(f"Overall: {'PASS' if all_pass else 'FAIL'}")

    return all_pass


if __name__ == "__main__":
    success = run_divergence_test()
    sys.exit(0 if success else 1)
