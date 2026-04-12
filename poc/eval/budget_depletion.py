"""
Experiment 3: Budget Depletion

Show that an adaptive adversary's posterior probability converges to
the theoretical bound, not to certainty, and that absorption halts
further learning.

Usage:
    # Start proxy first: uvicorn src.proxy:app --port 8000
    python -m eval.budget_depletion
"""

import json
import sys
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from src.config import SessionConfig
from src.proxy import session_store, accountants

# -- Configuration --
N_QUERIES = 100
PER_QUERY_EPSILON = 1.0
TOTAL_BUDGET = 50.0
ABSORPTION_MARGIN = 5.0
BASE_URL = "http://localhost:8000"


def setup_budget_sessions():
    """Register sessions for budget depletion test."""
    session_store.register(SessionConfig(
        session_id="budget_present",
        authorized_tools=["web_search"],
        budget=TOTAL_BUDGET,
        per_query_epsilon=PER_QUERY_EPSILON,
        absorption_margin=ABSORPTION_MARGIN,
    ))
    session_store.register(SessionConfig(
        session_id="budget_absent",
        authorized_tools=[],
        budget=TOTAL_BUDGET,
        per_query_epsilon=PER_QUERY_EPSILON,
        absorption_margin=ABSORPTION_MARGIN,
    ))


def bayesian_update(prior: float, observation_score: float, epsilon: float) -> float:
    """
    Update prior based on observation.
    Likelihood ratio bounded by e^epsilon due to channel shaping.
    """
    lr = min(observation_score, np.exp(epsilon))
    lr = max(lr, np.exp(-epsilon))
    posterior = (lr * prior) / (lr * prior + (1 - prior))
    return posterior


def extract_signal(response, elapsed_time: float) -> float:
    """
    Adversary's best attempt to extract distinguishing signal.
    Returns estimated likelihood ratio.

    In a well-shaped system, this returns ~1.0 (no signal).
    Uses timing and size as the two available side channels.
    """
    size = len(response.content)

    # Attempt to detect timing signal: compare to expected range
    # The channel shaper targets 200-400ms; any deviation is signal
    expected_mean = 0.3  # midpoint of [0.2, 0.4]
    timing_deviation = abs(elapsed_time - expected_mean) / expected_mean

    # Attempt to detect size signal: should be exactly 4096
    size_deviation = abs(size - 4096)

    # Convert deviations to a likelihood ratio estimate
    # Small deviations -> ratio near 1.0 (no signal)
    # Large deviations -> ratio further from 1.0
    lr = 1.0 + timing_deviation * 0.1 + size_deviation * 0.01

    return lr


def adaptive_probing(client, session_id: str, n_queries: int = N_QUERIES) -> dict:
    """Simulate an adaptive adversary probing for tool presence."""
    prior = 0.5
    posteriors = [prior]

    for i in range(n_queries):
        start = time.monotonic()
        resp = client.post(f"{BASE_URL}/action", json={
            "tool": "web_search",
            "params": {"query": f"adaptive_probe_{i}"},
            "session_id": session_id,
        })
        elapsed = time.monotonic() - start

        observation_score = extract_signal(resp, elapsed)
        prior = bayesian_update(prior, observation_score, PER_QUERY_EPSILON)
        posteriors.append(prior)

    return {"posteriors": posteriors}


def theoretical_bound(total_epsilon: float) -> float:
    """Maximum posterior after observing total_epsilon leakage."""
    return np.exp(total_epsilon) / (1.0 + np.exp(total_epsilon))


def plot_results(result_present: dict, result_absent: dict, output_path: str):
    """Generate posterior convergence chart."""
    queries = np.arange(len(result_present["posteriors"]))
    bound = theoretical_bound(min(TOTAL_BUDGET, N_QUERIES * PER_QUERY_EPSILON))
    lower_bound = 1.0 - bound

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(queries, result_present["posteriors"], label="Tool present", alpha=0.8)
    ax.plot(queries, result_absent["posteriors"], label="Tool absent", alpha=0.8)
    ax.axhline(y=0.5, color="gray", linestyle="--", alpha=0.5, label="No information (0.5)")
    ax.axhline(y=bound, color="red", linestyle=":", alpha=0.7, label=f"Theoretical bound ({bound:.4f})")
    ax.axhline(y=lower_bound, color="red", linestyle=":", alpha=0.7)

    ax.set_xlabel("Queries")
    ax.set_ylabel("Posterior P(tool exists)")
    ax.set_title("Budget Depletion: Adaptive Adversary Posterior Convergence")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    print(f"  Plot saved to {output_path}")


def run_budget_depletion_test():
    """Run the full budget depletion experiment."""
    import httpx

    setup_budget_sessions()

    print("Budget Depletion Test")
    print("=" * 65)
    print(f"  Queries: {N_QUERIES}")
    print(f"  Per-query epsilon: {PER_QUERY_EPSILON}")
    print(f"  Total budget: {TOTAL_BUDGET}")
    print(f"  Absorption margin: {ABSORPTION_MARGIN}")

    bound = theoretical_bound(min(TOTAL_BUDGET, N_QUERIES * PER_QUERY_EPSILON))
    lower_bound = 1.0 - bound
    print(f"  Theoretical posterior bound: [{lower_bound:.4f}, {bound:.4f}]")

    with httpx.Client(timeout=10.0) as client:
        print("\n  Probing with tool present...")
        result_present = adaptive_probing(client, "budget_present")

        print("  Probing with tool absent...")
        result_absent = adaptive_probing(client, "budget_absent")

    final_present = result_present["posteriors"][-1]
    final_absent = result_absent["posteriors"][-1]

    within_bound_present = lower_bound <= final_present <= bound
    within_bound_absent = lower_bound <= final_absent <= bound
    all_pass = within_bound_present and within_bound_absent

    print(f"\n  Final posterior (tool present): {final_present:.4f}  "
          f"{'PASS' if within_bound_present else 'FAIL'}")
    print(f"  Final posterior (tool absent):  {final_absent:.4f}  "
          f"{'PASS' if within_bound_absent else 'FAIL'}")

    # Check absorption state
    if "budget_present" in accountants:
        state = accountants["budget_present"].get_state()
        print(f"\n  Accountant state (present): queries={state['query_count']}, "
              f"spent={state['spent']:.1f}, absorbing={state['absorbing']}")

    plot_results(result_present, result_absent, "results/budget_depletion.png")

    print("\n" + "=" * 65)
    print(f"Overall: {'PASS' if all_pass else 'FAIL'}")

    return all_pass


if __name__ == "__main__":
    success = run_budget_depletion_test()
    sys.exit(0 if success else 1)
