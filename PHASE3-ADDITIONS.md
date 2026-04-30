# PHASE3-ADDITIONS.md
# Indeterminate Emergence — Phase 3 Testing Additions
# cerberusxops360/indeterminate-emergence

**Version:** 1.0.0
**Date:** 2026-04-15
**Author:** Adam Bishop / XOps360 LLC
**Status:** PLANNED — execute after Phase 2 gate passes

---

## Origin

These additions were derived from analysis of BGP traffic
analysis attack methodology and its structural relationship
to IE's threat model. The key insight: BGP traffic analysis
attacks and IE's timing oracle attacks are isomorphic —
both infer secret state from observable timing patterns at
a network boundary.

Source document:
`shared-library/standards/infrastructure/
 INFRASTRUCTURE-BGP-CAPABILITIES.md` Section 6

---

## Phase 2 Gate Requirement

**None of the work in this document begins until the
Phase 2 gate test passes:**
- 10,000 trials
- Advantage ≤ 2^-20
- Full statistical distinguisher battery passes
- Gate documented in results/

---

## Addition 1 — ML-Based Distinguisher Battery

### Rationale

BGP traffic analysis literature uses k-NN and random
forest classifiers as distinguishers for website
fingerprinting attacks (Wang et al. and follow-on work).
These are the strongest known practical distinguisher
class for timing-pattern attacks. If IE's timing
normalization defeats ML-based classifiers designed
specifically for traffic analysis, the guarantee extends
beyond statistical tests to the strongest real-world
attack methodology.

### Implementation

```python
# poc/eval/ml_distinguisher.py

from sklearn.neighbors import KNeighborsClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
import numpy as np

def run_ml_distinguisher_battery(
    authorized_timings: list[float],
    unauthorized_timings: list[float],
    n_trials: int = 10000
) -> dict:
    """
    Tests IE timing distributions against ML-based
    distinguishers from BGP traffic analysis literature.

    Returns advantage scores per classifier.
    Threshold: advantage > 0.01 (1%) = distinguishable
    """

    X = np.array(authorized_timings + unauthorized_timings).reshape(-1, 1)
    y = np.array([1] * len(authorized_timings) +
                 [0] * len(unauthorized_timings))

    results = {}

    # k-NN (Wang et al. methodology)
    for k in [1, 3, 5, 11]:
        clf = KNeighborsClassifier(n_neighbors=k)
        scores = cross_val_score(clf, X, y, cv=10, scoring='accuracy')
        advantage = abs(scores.mean() - 0.5) * 2
        results[f'knn_k{k}'] = {
            'accuracy': scores.mean(),
            'advantage': advantage,
            'passes': advantage <= 0.01
        }

    # Random forest
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    scores = cross_val_score(rf, X, y, cv=10, scoring='accuracy')
    advantage = abs(scores.mean() - 0.5) * 2
    results['random_forest'] = {
        'accuracy': scores.mean(),
        'advantage': advantage,
        'passes': advantage <= 0.01
    }

    return results
```

### Gate Condition

All ML classifiers must produce advantage ≤ 0.01 (1%).
If any classifier exceeds this threshold, the timing
normalization requires revision before Phase 3 completes.

---

## Addition 2 — Active Timing Injection Tests

### Rationale

Current Phase 2 evaluation tests passive observation —
measuring timing distributions of randomized authorized
vs. unauthorized requests. BGP attack methodology
suggests a stronger test class: active timing injection
where the distinguisher controls input timing patterns
and observes whether IE's response timing distributions
change in response to adversarially structured inputs.

This is the analog of BGP's active traffic injection —
crafted route announcements that probe routing behavior.
The attack is isomorphic: does adversarially structured
input timing leak information about internal state through
the response timing distribution?

### Implementation

```python
# poc/eval/active_injection.py

import time
import asyncio
import numpy as np
from typing import Literal

InputPattern = Literal['burst', 'sparse', 'regular', 'adversarial']

async def run_active_injection_test(
    credential_store_url: str,
    pattern: InputPattern,
    n_requests: int = 1000
) -> dict:
    """
    Tests whether IE's timing normalization holds against
    adversarially structured input timing patterns.

    Patterns:
    - burst: 100 requests in 10ms windows
    - sparse: 1 request per 500ms
    - regular: evenly spaced at 50ms intervals
    - adversarial: alternating burst/sparse designed to
                   maximize timing correlation signal
    """

    timings = []

    if pattern == 'burst':
        # Send requests in tight bursts
        for _ in range(n_requests // 10):
            batch_start = time.perf_counter()
            tasks = [send_request(credential_store_url)
                     for _ in range(10)]
            results = await asyncio.gather(*tasks)
            timings.extend([r['response_time'] for r in results])
            await asyncio.sleep(0.1)

    elif pattern == 'sparse':
        for _ in range(n_requests):
            result = await send_request(credential_store_url)
            timings.append(result['response_time'])
            await asyncio.sleep(0.5)

    elif pattern == 'regular':
        for _ in range(n_requests):
            result = await send_request(credential_store_url)
            timings.append(result['response_time'])
            await asyncio.sleep(0.05)

    elif pattern == 'adversarial':
        # Alternating burst/sparse designed to stress
        # timing normalization under adversarial control
        for i in range(n_requests):
            result = await send_request(credential_store_url)
            timings.append(result['response_time'])
            delay = 0.01 if i % 20 < 10 else 0.2
            await asyncio.sleep(delay)

    return {
        'pattern': pattern,
        'n_requests': n_requests,
        'mean': np.mean(timings),
        'std': np.std(timings),
        'cv': np.std(timings) / np.mean(timings),
        'timings': timings
    }


def test_normalization_independence(
    baseline_timings: list[float],
    injection_results: dict[str, dict]
) -> dict:
    """
    Tests whether response timing distributions are
    independent of input timing pattern.

    Null hypothesis: timing distributions are equal
    across all input patterns (normalization holds).
    """
    from scipy.stats import ks_2samp

    results = {}
    for pattern, data in injection_results.items():
        stat, pvalue = ks_2samp(baseline_timings, data['timings'])
        results[pattern] = {
            'ks_statistic': stat,
            'p_value': pvalue,
            'distinguishable': pvalue < 0.05,
            'passes': pvalue >= 0.05
        }

    return results
```

### Gate Condition

Response timing distributions must be statistically
indistinguishable from baseline across all four input
patterns (p ≥ 0.05 on KS test). If any pattern produces
a distinguishable timing distribution, the timing
normalization has an input-dependency that must be fixed.

---

## Addition 3 — Calibration Mode in divergence_test.py

### Rationale

BGP security uses canary token methodology: deliberately
introduce a detectable anomaly, confirm the detection
system fires, then trust it for real anomaly detection.
Without calibration, a passing gate test could indicate
insufficient statistical power rather than genuine
indistinguishability.

IE's divergence_test.py must demonstrate it can detect
a deliberate timing bias of known magnitude before the
gate test results can be trusted.

### Implementation

Add `--calibration` flag to existing `divergence_test.py`:

```python
# Addition to poc/eval/divergence_test.py

import argparse

def add_calibration_args(parser: argparse.ArgumentParser):
    parser.add_argument(
        '--calibration',
        action='store_true',
        help='Run calibration mode: introduces deliberate '
             'timing bias to validate distinguisher power'
    )
    parser.add_argument(
        '--calibration-bias-ms',
        type=float,
        default=50.0,
        help='Timing bias in milliseconds for calibration '
             'mode (default: 50ms)'
    )


def apply_calibration_bias(
    timings: list[float],
    bias_ms: float,
    authorized: bool
) -> list[float]:
    """
    For calibration only — introduces a deliberate,
    known timing bias between authorized and unauthorized
    paths. If the distinguisher cannot detect this,
    the test lacks statistical power.

    authorized=True: adds bias_ms to all timings
    authorized=False: no modification
    """
    if authorized:
        return [t + (bias_ms / 1000.0) for t in timings]
    return timings


def run_calibration_check(
    authorized_timings: list[float],
    unauthorized_timings: list[float],
    bias_ms: float
) -> dict:
    """
    Validates distinguisher statistical power.
    Should ALWAYS detect bias_ms difference.
    If it doesn't, the gate test is unreliable.
    """
    biased_authorized = apply_calibration_bias(
        authorized_timings, bias_ms, authorized=True
    )

    # Run full distinguisher battery on biased data
    results = run_distinguisher_battery(
        biased_authorized, unauthorized_timings
    )

    all_detected = all(
        r.get('advantage', 0) > 0.1
        for r in results.values()
    )

    return {
        'bias_ms': bias_ms,
        'all_detected': all_detected,
        'calibration_passed': all_detected,
        'results': results,
        'note': (
            'CALIBRATION PASSED — distinguisher has '
            'sufficient power to detect timing differences '
            f'of {bias_ms}ms or greater.'
            if all_detected else
            'CALIBRATION FAILED — distinguisher cannot '
            f'detect a {bias_ms}ms timing bias. Gate test '
            'results are unreliable. Increase n_trials or '
            'improve test methodology before proceeding.'
        )
    }
```

### Required Workflow

```bash
# Step 1: Always run calibration first
python poc/eval/divergence_test.py --calibration --calibration-bias-ms 50

# Verify output shows: CALIBRATION PASSED
# If CALIBRATION FAILED — do NOT proceed to gate test

# Step 2: Run formal gate test only after calibration passes
python poc/eval/divergence_test.py --n-trials 10000
```

Calibration results must be included in all published
empirical reports. A gate test without documented
calibration validation is methodologically incomplete.

---

## Addition 4 — Network Path Jitter Documentation

### Rationale

IE's timing normalization assumes consistent network path
latency between the credential store proxy and the client.
Variable network paths introduce timing jitter that is
not attributable to the credential access pattern —
this is noise that inflates the distinguisher's measurement
error and could mask real timing signals or produce
false positives.

For deployments at scale (enterprise, federal), anycast
infrastructure is the production recommendation to minimize
network-layer timing jitter as a confounding variable.

### Required Documentation

Add `docs/DEPLOYMENT-ASSUMPTIONS.md` to the IE repo:

```markdown
# IE PoC — Network Path Assumptions

## Timing Normalization Prerequisites

IE's timing normalization guarantees are conditioned on
the following network path assumptions:

### Development / Testing (local loopback)
- Client and credential store proxy on same host
- Network jitter: ~0ms (loopback)
- Confounding variables: none
- Suitable for: Phase 2 gate test

### Single-Node Production
- Client and proxy on same LAN segment
- Network jitter: <1ms
- Confounding variables: minimal
- Suitable for: initial production deployments

### Multi-Region Production (recommended)
- Anycast deployment across geographic nodes
- Client always hits nearest node
- Network jitter: <5ms (edge-optimized)
- Confounding variables: minimized
- Architecture: ARIN ASN + owned /24 + Vultr/Hetzner BGP
- Reference: INFRASTRUCTURE-BGP-CAPABILITIES.md Phase 3

## Jitter Impact on Distinguisher Tests

Network jitter σ_network adds in quadrature to the
timing signal σ_timing:

  σ_observed = sqrt(σ_timing² + σ_network²)

For IE's gate threshold (advantage ≤ 2^-20), the
timing signal σ_timing must be small relative to
σ_observed. High σ_network masks real timing signals.

Rule: σ_network must be < 10% of σ_timing for gate
test results to be reliable. Measure σ_network
explicitly before running gate tests in any new
deployment environment.
```

---

## Addition 5 — Literature Grounding in BGP Side Channel Research

### Rationale

IE's threat model (timing oracle attacks on credential
access patterns) is structurally parallel to BGP withdrawal
timing side channels and BGP traffic analysis attacks.
Formally citing this literature positions IE within
established network security research tradition, which
strengthens methodological credibility for IACR resubmission.

### Citations to Add to Paper

Primary references for revised paper submission:

**BGP Traffic Analysis / Website Fingerprinting:**
- Wang, T. et al. "Improved Website Fingerprinting on Tor."
  ACM CCS 2013. (k-NN distinguisher methodology)
- Hayes, J. & Danezis, G. "k-fingerprinting: A Robust
  Scalable Website Fingerprinting Technique." USENIX
  Security 2016. (Random forest methodology)

**BGP Timing Side Channels:**
- Zhang, Z. et al. "On the Feasibility of Traffic Analysis
  Attacks Against Internet Exchange Points." IMC 2018.
- Shi, E. et al. "Oblivious RAM with O((log N)^3) Worst-Case
  Cost." ASIACRYPT 2011. (ORAM as timing oracle defense)

**Framing Paragraph for Paper Revision:**

```
IE's threat model is grounded in the same attack class
as BGP traffic analysis attacks: an adversary infers
secret state from observable timing patterns at a
network boundary without accessing protected content.
BGP traffic analysis attacks [Wang 2013, Hayes 2016]
use timing and size distributions of network flows
to infer which websites a Tor user visits. IE's timing
oracle attacks use response latency distributions to
infer which credentials are accessed. Both attacks
exploit the same fundamental vulnerability: when secret
state influences observable timing, a sufficiently
sensitive distinguisher can recover that state.

IE's defense — fixed-length operations, padding
normalization, and timing independence — addresses the
same class of vulnerability that Tor's defense designers
have studied for over a decade. The BGP traffic analysis
literature provides the correct reference class for
evaluating IE's ML-based distinguisher resistance.
```

---

## Execution Order

```
Phase 2 gate passes (10K trials, advantage ≤ 2^-20)
  ↓
Addition 3: Implement --calibration mode
  ↓
Addition 4: Write DEPLOYMENT-ASSUMPTIONS.md
  ↓
Addition 1: Implement ML distinguisher battery
  Run calibration first, then gate test with ML classifiers
  ↓
Addition 2: Implement active timing injection tests
  Requires Phase 2 infrastructure still running
  ↓
Addition 5: Revise paper with literature citations
  Integrate results from Additions 1-4 into empirical section
  ↓
IACR resubmission
```

---

## Document Control

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-04-15 | Adam Bishop | Initial — derived from BGP infrastructure analysis |

---

*Execute Phase 2 gate test before any work in this document.
All additions here are Phase 3 scope — they strengthen the
empirical case after the core gate passes, not before.*
