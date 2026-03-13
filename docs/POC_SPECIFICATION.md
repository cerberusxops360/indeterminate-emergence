# Proof of Concept Specification
## Indeterminate Emergence -- AI Capability-Set Inference Resistance

---

## 1. Objective

Build a working proxy service that sits between an external observer and an AI agent's tool registry. Demonstrate that the observer cannot determine which tools the agent has access to, even through active probing. Validate the three core claims of the paper empirically:

1. **Observation indistinguishability** — response distributions are statistically indistinguishable across different capability sets.
2. **Classifier resistance** — a trained adversarial classifier cannot determine tool presence above chance.
3. **Budget enforcement** — an adaptive probing strategy's posterior converges to the theoretical bound, not to certainty.

---

## 2. Scope

### In Scope

- Single-agent, single-session proxy with configurable tool registry
- Five simulated tools with realistic latency and response size variation
- Channel shaping (fixed-size responses, timing padding, constant-format receipts)
- Privacy budget accountant with absorption trigger
- Three evaluation experiments with quantitative results
- Level 1 adversary (network-only: sees HTTP responses and timing)

### Out of Scope

- Real AI agent integration (use simulated tool calls)
- Multi-session correlation attacks
- Level 2/3 adversaries (system call, cache timing)
- Agent behavioral leakage
- Production hardening, TLS, authentication
- UI or dashboard

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   Attacker / Evaluator                                       │
│       │                                                      │
│       │  HTTP POST /action                                   │
│       ▼                                                      │
│   ┌────────────────────┐                                     │
│   │   Intent Interface  │  FastAPI endpoint                  │
│   │   (proxy.py)        │  Validates request schema          │
│   └────────┬───────────┘                                     │
│            │                                                 │
│            ▼                                                 │
│   ┌────────────────────┐     ┌──────────────────────┐       │
│   │   Policy Check      │────▶│  Privacy Accountant   │      │
│   │   (config.py)       │     │  (accountant.py)      │      │
│   │                     │     │                       │      │
│   │   - Token lookup    │     │  - Budget tracking    │      │
│   │   - Action allowed? │     │  - Absorption trigger │      │
│   └────────┬───────────┘     └──────────┬───────────┘       │
│            │                             │                   │
│            ▼                             │ mode signal       │
│   ┌────────────────────┐                 │                   │
│   │   Sealed Executor   │◀───────────────┘                   │
│   │   (executor.py)     │                                    │
│   │                     │                                    │
│   │   Normal: call tool │                                    │
│   │   Absorb: dummy wait│                                    │
│   └────────┬───────────┘                                     │
│            │                                                 │
│            ▼                                                 │
│   ┌────────────────────┐                                     │
│   │   Channel Shaper    │                                    │
│   │   (channel_shaper)  │                                    │
│   │                     │                                    │
│   │   - Pad to 4KB      │                                    │
│   │   - Pad timing      │                                    │
│   │   - Fixed receipt    │                                    │
│   └────────┬───────────┘                                     │
│            │                                                 │
│            ▼                                                 │
│       HTTP Response                                          │
│       (fixed size, padded timing, uniform structure)         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Component Specifications

### 4.1 Intent Interface (`proxy.py`)

**Purpose:** Single HTTP endpoint that accepts action requests and returns shaped responses.

**Endpoint:**
```
POST /action
Content-Type: application/json

{
    "tool": "web_search",          # Requested tool name
    "params": { "query": "test" }, # Tool-specific parameters
    "session_id": "abc123"         # Session identifier
}
```

**Response (always identical structure):**
```
HTTP 200 OK
Content-Type: application/json
Content-Length: 4096

{
    "status": "processed",
    "receipt": "ack",
    "payload": "<padded to exactly 3800 bytes>",
    "padding": "<fills remaining space to 4096 total>"
}
```

**Key behaviors:**
- Always returns HTTP 200. Never 403, 404, or 500.
- Response body is always exactly 4096 bytes.
- The `status` field is always `"processed"`.
- The `receipt` field is always `"ack"`.
- Response timing is controlled by the channel shaper, not by actual execution time.
- Invalid requests (malformed JSON, unknown fields) receive the same response.

**Implementation:**
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import json

app = FastAPI()

@app.post("/action")
async def handle_action(request: Request):
    body = await request.json()

    # Policy check + execution (details in executor)
    result = await execute_action(body)

    # Channel shaping (details in channel_shaper)
    shaped_response = await shape_response(result)

    return JSONResponse(
        content=shaped_response,
        status_code=200
    )
```

**Estimated lines:** ~80

---

### 4.2 Configuration & Policy (`config.py`)

**Purpose:** Define capability tokens (which tools are authorized per session) and system parameters.

**Session configuration (loaded at startup or per-session):**
```python
SESSION_CONFIG = {
    "abc123": {
        "authorized_tools": ["web_search", "calculator", "file_read"],
        "budget": 50.0,          # Total epsilon budget
        "per_query_epsilon": 1.0, # Epsilon cost per interaction
        "absorption_margin": 5.0  # Enter absorption when budget < margin
    }
}

# All possible tools in the system
ALL_TOOLS = [
    "web_search",
    "calculator",
    "file_read",
    "code_exec",
    "database_query"
]
```

**Policy check function:**
```python
def check_policy(session_id: str, tool: str) -> dict:
    """
    Returns policy decision. Crucially, the return value
    has the same structure regardless of outcome.
    """
    session = SESSION_CONFIG.get(session_id)

    if session is None:
        return {"authorized": False, "reason": "no_session"}
    if tool not in ALL_TOOLS:
        return {"authorized": False, "reason": "unknown_tool"}
    if tool not in session["authorized_tools"]:
        return {"authorized": False, "reason": "not_authorized"}

    return {"authorized": True, "reason": "ok"}
```

**Key behavior:** The policy decision is internal only. It never appears in the response. The external response is identical regardless of `authorized` value.

**Estimated lines:** ~50

---

### 4.3 Sealed Executor (`executor.py`)

**Purpose:** Execute the real tool call (normal mode) or perform a dummy computation (absorption mode).

**Simulated tools:** Each tool is a function that takes parameters and returns a result after a realistic delay. For the PoC, tools are simulated — they don't call real APIs.

```python
import asyncio
import random
import hashlib

async def simulate_tool(tool_name: str, params: dict) -> str:
    """Simulate a real tool call with realistic latency and output."""

    # Simulate variable computation time (50-300ms)
    latency = random.uniform(0.05, 0.3)
    await asyncio.sleep(latency)

    # Generate plausible output (varies by tool)
    if tool_name == "web_search":
        return json.dumps({"results": [f"Result for {params.get('query', '')}"]})
    elif tool_name == "calculator":
        return json.dumps({"result": 42})
    elif tool_name == "file_read":
        return json.dumps({"content": "File contents here..."})
    elif tool_name == "code_exec":
        return json.dumps({"stdout": "Hello World", "exit_code": 0})
    elif tool_name == "database_query":
        return json.dumps({"rows": [{"id": 1, "value": "data"}]})
    else:
        return json.dumps({"result": None})


async def dummy_computation() -> str:
    """
    Absorption mode: perform work that matches real tool resource profile.
    NOT a no-op. Consumes similar CPU time and memory.
    """
    # Simulate comparable latency
    latency = random.uniform(0.05, 0.3)
    await asyncio.sleep(latency)

    # Do some actual computation to match resource signature
    data = hashlib.sha256(random.randbytes(1024)).hexdigest()

    return json.dumps({"result": None})


async def execute(
    tool_name: str,
    params: dict,
    authorized: bool,
    absorbing: bool
) -> str:
    """
    Core execution logic.

    Three cases, all producing the same external observation:
    1. Not authorized -> dummy computation
    2. Authorized but absorbing -> dummy computation
    3. Authorized and normal -> real tool call
    """
    if not authorized or absorbing:
        return await dummy_computation()
    else:
        return await simulate_tool(tool_name, params)
```

**Key behavior:** The executor returns a string in all cases. The *content* differs, but the channel shaper will normalize this before it reaches the observer.

**Estimated lines:** ~100

---

### 4.4 Channel Shaper (`channel_shaper.py`)

**Purpose:** Transform variable-size, variable-timing execution results into fixed-size, fixed-timing responses. This is the most critical component for indistinguishability.

**Size shaping:**
```python
import json
import time
import asyncio
import random

RESPONSE_SIZE = 4096  # bytes, fixed

def pad_payload(raw_result: str) -> dict:
    """
    Create a fixed-size response body regardless of raw_result content.
    """
    response = {
        "status": "processed",
        "receipt": "ack",
        "payload": "",
        "padding": ""
    }

    # Serialize the real payload (truncate if too long)
    max_payload = RESPONSE_SIZE - 200  # reserve space for structure + padding
    payload = raw_result[:max_payload] if raw_result else ""

    response["payload"] = payload

    # Calculate padding needed
    current_size = len(json.dumps(response).encode('utf-8'))
    padding_needed = RESPONSE_SIZE - current_size

    if padding_needed > 0:
        response["padding"] = "x" * padding_needed
    elif padding_needed < 0:
        # Payload too large even after truncation — truncate more
        overage = abs(padding_needed)
        response["payload"] = payload[:len(payload) - overage]
        response["padding"] = ""

    return response
```

**Timing shaping:**
```python
# Timing distribution parameters
MIN_LATENCY = 0.2    # 200ms minimum
MAX_LATENCY = 0.4    # 400ms maximum

async def shape_timing(execution_start: float):
    """
    Ensure total response time falls within [MIN_LATENCY, MAX_LATENCY]
    regardless of actual execution time.
    """
    # Draw target latency from uniform distribution
    target = random.uniform(MIN_LATENCY, MAX_LATENCY)

    elapsed = time.monotonic() - execution_start
    remaining = target - elapsed

    if remaining > 0:
        await asyncio.sleep(remaining)
    # If execution took longer than target, we still return
    # (this is a bounded leak — log it for analysis)
```

**Combined shaping function:**
```python
async def shape_response(raw_result: str, execution_start: float) -> dict:
    """Full channel shaping: pad size + pad timing."""
    # Size shaping
    response = pad_payload(raw_result)

    # Timing shaping
    await shape_timing(execution_start)

    return response
```

**Key behaviors:**
- Every response is exactly 4096 bytes
- Every response takes between 200ms and 400ms
- The `payload` field contains real tool output in normal mode or `null`/empty in absorption mode — but the observer sees only the fixed-size padded version
- In the PoC, the `payload` for unauthorized/absorbed requests is always `json.dumps({"result": null})` — matching what an authorized-but-empty-result tool call would return

**Important:** For the indistinguishability argument to hold, null payloads must be indistinguishable from empty-result payloads. The simplest way: always set `payload` to `json.dumps({"result": null})` for the observer, and deliver real content only through a separate authorized channel (out of scope for this PoC — the point is proving the observation channel is indistinguishable).

**Estimated lines:** ~80

---

### 4.5 Privacy Accountant (`accountant.py`)

**Purpose:** Track cumulative leakage per session and trigger absorption when budget is exhausted.

```python
import random

class PrivacyAccountant:
    def __init__(self, budget: float, per_query_cost: float, margin: float):
        self.budget = budget
        self.per_query_cost = per_query_cost
        self.margin = margin
        self.spent = 0.0
        self.absorbing = False
        self.query_count = 0

        # Randomized threshold (optional — reduces meta-leakage)
        self.threshold = budget - random.uniform(0, margin)

    def record_query(self) -> bool:
        """
        Record a query and return current absorption state.
        Returns True if absorbing.
        """
        self.query_count += 1
        self.spent += self.per_query_cost

        if not self.absorbing and self.spent >= self.threshold:
            self.absorbing = True  # Sticky — stays absorbed

        return self.absorbing

    def get_state(self) -> dict:
        """For internal logging/evaluation only. Never exposed externally."""
        return {
            "query_count": self.query_count,
            "spent": self.spent,
            "budget": self.budget,
            "threshold": self.threshold,
            "absorbing": self.absorbing
        }
```

**Key behaviors:**
- Absorption is **sticky** — once triggered, it doesn't revert within a session
- Threshold is randomized within the margin range to prevent threshold-oracle attacks
- The accountant's state is never exposed in the HTTP response
- Each query costs the same epsilon regardless of tool or result (simplification for PoC; a production system would assign per-action costs)

**Estimated lines:** ~40

---

## 5. Integration Flow

The full request-response cycle:

```
1. Request arrives at /action
2. Parse request body (tool name, params, session_id)
3. Record start time
4. Look up session config
5. Check policy (is tool authorized for this session?)
6. Query accountant (is session absorbing?)
7. Execute:
   - If authorized AND not absorbing: call simulate_tool()
   - Otherwise: call dummy_computation()
8. Shape response:
   - Pad payload to fixed size
   - Pad timing to target latency
9. Return shaped response (always 200, always 4096 bytes)
```

Pseudocode for the main handler:

```python
@app.post("/action")
async def handle_action(request: Request):
    start = time.monotonic()
    body = await request.json()

    session_id = body.get("session_id", "default")
    tool = body.get("tool", "")
    params = body.get("params", {})

    # Policy check
    policy = check_policy(session_id, tool)

    # Budget check
    accountant = get_accountant(session_id)
    is_absorbing = accountant.record_query()

    # Execute
    raw_result = await execute(
        tool_name=tool,
        params=params,
        authorized=policy["authorized"],
        absorbing=is_absorbing
    )

    # Shape
    response = await shape_response(raw_result, start)

    return JSONResponse(content=response, status_code=200)
```

---

## 6. Evaluation Experiments

### 6.1 Experiment 1: Distribution Comparison

**Goal:** Demonstrate that response distributions are statistically indistinguishable across capability configurations.

**Method:**

```python
# For each tool X:
#   Config A: tool X is in the authorized set
#   Config B: tool X is NOT in the authorized set
#
# For each config:
#   Send 1000 identical requests for tool X
#   Record: response body, response time, response size
#
# Compare distributions of (body, time, size) between A and B
```

**Metrics:**
- Total variation distance between response time distributions
- KL divergence between response time distributions
- Byte-level comparison of response bodies (should be identical in structure)
- Chi-squared test on any categorical response features

**Success criteria:**
- TV distance < 0.05
- KL divergence < 0.01
- Response bodies have identical structure (differ only in padded content, which is opaque)

**Implementation:**

```python
# eval/divergence_test.py

import numpy as np
from scipy import stats
import requests
import time

def collect_samples(tool: str, config: dict, n: int = 1000) -> dict:
    """Send n requests and collect response metadata."""
    times = []
    sizes = []

    for _ in range(n):
        start = time.monotonic()
        resp = requests.post("http://localhost:8000/action", json={
            "tool": tool,
            "params": {"query": "test"},
            "session_id": config["session_id"]
        })
        elapsed = time.monotonic() - start

        times.append(elapsed)
        sizes.append(len(resp.content))

    return {"times": np.array(times), "sizes": np.array(sizes)}


def total_variation_distance(p: np.ndarray, q: np.ndarray, bins: int = 50) -> float:
    """Estimate TV distance between two sample distributions."""
    min_val = min(p.min(), q.min())
    max_val = max(p.max(), q.max())

    p_hist, edges = np.histogram(p, bins=bins, range=(min_val, max_val), density=True)
    q_hist, _ = np.histogram(q, bins=bins, range=(min_val, max_val), density=True)

    bin_width = edges[1] - edges[0]
    return 0.5 * np.sum(np.abs(p_hist - q_hist)) * bin_width


def run_divergence_test():
    tools = ["web_search", "calculator", "file_read", "code_exec", "database_query"]

    for tool in tools:
        # Config A: tool authorized
        samples_a = collect_samples(tool, {"session_id": "config_a"})

        # Config B: tool NOT authorized
        samples_b = collect_samples(tool, {"session_id": "config_b"})

        tv = total_variation_distance(samples_a["times"], samples_b["times"])
        ks_stat, ks_p = stats.ks_2samp(samples_a["times"], samples_b["times"])

        print(f"{tool}:")
        print(f"  TV distance (timing): {tv:.4f}")
        print(f"  KS statistic: {ks_stat:.4f}, p-value: {ks_p:.4f}")
        print(f"  Size variance A: {samples_a['sizes'].std():.2f}")
        print(f"  Size variance B: {samples_b['sizes'].std():.2f}")
```

**Estimated lines:** ~120

---

### 6.2 Experiment 2: Classifier Attack

**Goal:** Train the best possible adversarial classifier and show it can't distinguish tool presence from absence.

**Method:**

```python
# Generate labeled dataset:
#   For each tool X, for N sessions:
#     - Half the sessions have X authorized (label = 1)
#     - Half don't (label = 0)
#     - Each session: send K probe requests, record responses
#     - Feature vector: [response_times, response_sizes, any extractable content features]
#
# Train binary classifier on (features, labels)
# Evaluate on held-out test set
# Measure: accuracy, AUC-ROC, advantage over chance
```

**Classifiers to try:**
- Logistic regression (baseline)
- Random forest (nonlinear)
- Gradient boosted trees (XGBoost)
- Small MLP (neural network)

**Features per session (K probes):**
- Mean, std, min, max, median of response times
- Mean, std of response sizes
- Entropy of response body bytes
- Any detectable patterns in payload content

**Success criteria:**
- All classifiers achieve accuracy ≤ 52% (within noise of 50% chance)
- AUC-ROC ≤ 0.55
- Adversary advantage (|accuracy - 0.5|) bounded by the theoretical epsilon bound

**Implementation:**

```python
# eval/classifier_attack.py

import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
import requests

def collect_session_features(
    tool: str,
    session_id: str,
    n_probes: int = 20
) -> np.ndarray:
    """Send n_probes requests and extract feature vector."""
    times = []
    sizes = []

    for _ in range(n_probes):
        start = time.monotonic()
        resp = requests.post("http://localhost:8000/action", json={
            "tool": tool,
            "params": {"query": f"probe_{_}"},
            "session_id": session_id
        })
        elapsed = time.monotonic() - start
        times.append(elapsed)
        sizes.append(len(resp.content))

    t = np.array(times)
    s = np.array(sizes)

    features = [
        t.mean(), t.std(), t.min(), t.max(), np.median(t),
        s.mean(), s.std(),
    ]
    return np.array(features)


def run_classifier_attack(
    tool: str = "web_search",
    n_sessions: int = 500,
    n_probes: int = 20
):
    X = []
    y = []

    for i in range(n_sessions):
        # Alternate: tool authorized vs not
        authorized = i % 2 == 0
        session_id = f"eval_session_{i}"

        # Configure session (via API or direct config manipulation)
        configure_session(session_id, tool, authorized)

        features = collect_session_features(tool, session_id, n_probes)
        X.append(features)
        y.append(1 if authorized else 0)

    X = np.array(X)
    y = np.array(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.3, random_state=42
    )

    classifiers = {
        "Logistic Regression": LogisticRegression(),
        "Random Forest": RandomForestClassifier(n_estimators=100),
        "Gradient Boosted": GradientBoostingClassifier(n_estimators=100),
        "MLP": MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=500)
    }

    print(f"\nClassifier Attack Results for tool: {tool}")
    print(f"{'Classifier':<25} {'Accuracy':<12} {'AUC-ROC':<12} {'Advantage':<12}")
    print("-" * 61)

    for name, clf in classifiers.items():
        clf.fit(X_train, y_train)
        y_pred = clf.predict(X_test)
        y_prob = clf.predict_proba(X_test)[:, 1]

        acc = accuracy_score(y_test, y_pred)
        auc = roc_auc_score(y_test, y_prob)
        advantage = abs(acc - 0.5)

        print(f"{name:<25} {acc:<12.4f} {auc:<12.4f} {advantage:<12.4f}")
```

**Estimated lines:** ~130

---

### 6.3 Experiment 3: Budget Depletion

**Goal:** Show that an adaptive adversary's posterior probability converges to the theoretical bound (Theorem 1), not to certainty, and that absorption halts further learning.

**Method:**

```python
# Simulate an optimal adaptive probing strategy:
#   - Adversary has prior P(tool_exists) = 0.5
#   - Each probe: adversary chooses action to maximize expected information gain
#   - After each probe: adversary updates posterior based on any detectable signal
#   - Track posterior over time
#
# Expected result:
#   - Posterior drifts slightly from 0.5 but stays within theoretical bound
#   - After absorption triggers, posterior stops moving
#
# Compare to:
#   - Theoretical maximum: P(tool) ≤ e^ε_total / (1 + e^ε_total)
#   - Unprotected system (no channel shaping): posterior → 1.0 quickly
```

**Implementation:**

```python
# eval/budget_depletion.py

import numpy as np
import requests
import time

def bayesian_update(prior: float, observation_score: float, epsilon: float) -> float:
    """
    Update prior based on observation.
    The observation_score represents the adversary's best estimate
    of the likelihood ratio from this observation.
    Bounded by e^epsilon due to the channel shaping.
    """
    # Likelihood ratio bounded by e^epsilon
    lr = min(observation_score, np.exp(epsilon))
    lr = max(lr, np.exp(-epsilon))

    posterior = (lr * prior) / (lr * prior + (1 - prior))
    return posterior


def adaptive_probing_strategy(
    tool: str,
    session_id: str,
    n_queries: int = 100,
    per_query_epsilon: float = 1.0,
    total_budget: float = 50.0
):
    """
    Simulate an adaptive adversary probing for tool presence.
    """
    prior = 0.5
    posteriors = [prior]

    # Theoretical bound after full budget
    theoretical_max = np.exp(total_budget) / (1 + np.exp(total_budget))
    # More realistic: with small per-query epsilon
    practical_max = np.exp(min(total_budget, n_queries * per_query_epsilon))
    practical_max = practical_max / (1 + practical_max)

    for i in range(n_queries):
        # Adversary probes
        start = time.monotonic()
        resp = requests.post("http://localhost:8000/action", json={
            "tool": tool,
            "params": {"query": f"adaptive_probe_{i}"},
            "session_id": session_id
        })
        elapsed = time.monotonic() - start

        # Adversary tries to extract signal from response
        # (timing, size, content — whatever they can measure)
        observation_score = extract_signal(resp, elapsed)

        # Update posterior
        prior = bayesian_update(prior, observation_score, per_query_epsilon)
        posteriors.append(prior)

    return {
        "posteriors": posteriors,
        "theoretical_max": theoretical_max,
        "practical_max": practical_max,
        "queries": n_queries
    }


def extract_signal(response, elapsed_time: float) -> float:
    """
    Adversary's best attempt to extract distinguishing signal.
    Returns estimated likelihood ratio.

    In a well-shaped system, this should return ~1.0 (no signal).
    """
    # Try timing signal
    timing_signal = elapsed_time  # raw timing

    # Try size signal
    size_signal = len(response.content)

    # Try content signal
    try:
        body = response.json()
        content_signal = len(str(body.get("payload", "")))
    except:
        content_signal = 0

    # Combine signals into a likelihood ratio estimate
    # (In a well-shaped system, all signals are constant → ratio ≈ 1.0)
    # For evaluation, use a simple heuristic or trained model

    # Placeholder: return 1.0 (no signal detected)
    # In a real evaluation, replace with the trained classifier's confidence
    return 1.0


def run_budget_depletion_test():
    """Run the full budget depletion experiment and plot results."""

    # Test with tool present
    result_present = adaptive_probing_strategy(
        tool="web_search",
        session_id="budget_test_present",
        n_queries=100
    )

    # Test with tool absent
    result_absent = adaptive_probing_strategy(
        tool="web_search",
        session_id="budget_test_absent",
        n_queries=100
    )

    # Also run against unprotected system for comparison
    # (bypass channel shaper — direct responses)
    # result_unprotected = ...

    print("Budget Depletion Results")
    print(f"Theoretical max posterior: {result_present['theoretical_max']:.4f}")
    print(f"Final posterior (present): {result_present['posteriors'][-1]:.4f}")
    print(f"Final posterior (absent):  {result_absent['posteriors'][-1]:.4f}")

    # Save for plotting
    np.save("results/posteriors_present.npy", result_present["posteriors"])
    np.save("results/posteriors_absent.npy", result_absent["posteriors"])
```

**Expected output chart:**

```
Posterior P(tool exists)
1.0 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ← unprotected (converges to truth)
    │                        ___________
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─           ← theoretical bound
    │          ~~~~~~~~~~~~
0.5 ├─────────────────────────────────── ← protected (stays near 0.5)
    │          ~~~~~~~~~~~~
    │  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─           ← theoretical lower bound
    │                        ___________
0.0 ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  ← unprotected (converges to truth)
    0       25       50       75     100
                  Queries →
                              ↑
                         absorption kicks in
```

**Estimated lines:** ~150

---

## 7. Technology Stack

| Component | Technology | Reason |
|---|---|---|
| Proxy service | Python 3.11+ with FastAPI | Async-native, clean, fast enough for PoC |
| HTTP server | Uvicorn | Standard ASGI server for FastAPI |
| Timing control | `asyncio.sleep` + `time.monotonic` | Sufficient precision for Level 1 adversary |
| Evaluation stats | NumPy, SciPy | Standard scientific computing |
| Classifier attack | scikit-learn | All four classifiers available |
| Plotting | Matplotlib | For results visualization |
| HTTP client (eval) | `requests` or `httpx` | For sending probe requests |

### Dependencies (`requirements.txt`)

```
fastapi>=0.104.0
uvicorn>=0.24.0
numpy>=1.24.0
scipy>=1.11.0
scikit-learn>=1.3.0
matplotlib>=3.7.0
requests>=2.31.0
xgboost>=2.0.0
```

---

## 8. Build Sequence

### Week 1: Core System (Days 1–7)

| Day | Task | Deliverable |
|---|---|---|
| 1 | Project scaffold, dependencies, config | Runnable empty FastAPI server |
| 2 | Intent interface + fixed-response handler | `/action` endpoint returning constant 4096-byte responses |
| 3 | Policy check + capability tokens | Session-configurable tool authorization |
| 4 | Sealed executor (normal + dummy paths) | Tool simulation with absorption path |
| 5 | Channel shaper (size padding + timing) | All responses are 4096 bytes, 200–400ms |
| 6 | Privacy accountant + integration | Full request flow with budget tracking and absorption |
| 7 | Integration testing, bug fixes | End-to-end working system |

**Day 7 milestone:** System is running. You can send requests and get fixed-format responses. You can toggle tool authorization per session and the responses look identical.

### Week 2: Evaluation (Days 8–14)

| Day | Task | Deliverable |
|---|---|---|
| 8 | Divergence test scaffolding | `eval/divergence_test.py` running |
| 9 | Run divergence test, iterate on channel shaper if needed | TV distance and KL divergence numbers |
| 10 | Classifier attack scaffolding | `eval/classifier_attack.py` running |
| 11 | Run classifier attack with all four classifiers | Accuracy, AUC-ROC, advantage table |
| 12 | Budget depletion test scaffolding | `eval/budget_depletion.py` running |
| 13 | Run budget depletion, generate plots | Posterior convergence charts |
| 14 | Results compilation, README update | Complete evaluation results |

**Day 14 milestone:** Three experiments complete with quantitative results. You know whether the system works.

### Week 3: Writeup & Polish (Days 15–21)

| Day | Task | Deliverable |
|---|---|---|
| 15–16 | Write `poc/README.md` with results, methodology, interpretation | PoC documentation |
| 17 | Generate publication-quality plots | Charts for blog post / paper update |
| 18 | Code cleanup, comments, docstrings | Clean codebase |
| 19 | Write follow-up blog post: "I built the thing" | Blog draft |
| 20 | Commit everything to GitHub | `poc/` directory complete |
| 21 | Buffer / iterate on any weak results | Final polish |

---

## 9. What "Success" Looks Like

### Strong success (everything works)
- TV distance < 0.05 across all tools
- All classifiers at ≤ 52% accuracy
- Posterior stays within theoretical bounds
- Absorption visibly stops posterior drift in the chart

**Interpretation:** The framework's core claims are empirically validated for a Level 1 adversary.

### Partial success (channel shaper has a leak)
- TV distance low for most metrics but timing shows signal (e.g., TV > 0.1 on timing)
- One classifier beats chance at ~55–60%
- Posterior drifts further than theoretical bound but doesn't reach certainty

**Interpretation:** The framework is sound but the implementation needs tighter channel shaping. This is still a useful result — it shows *where* leakage occurs and how to fix it. Document it honestly.

### Failure (system is distinguishable)
- Classifiers easily beat chance (>65%)
- Posterior converges to truth

**Interpretation:** The channel shaper is broken or the execution paths have a fundamental observable difference. Debug by isolating which feature (timing, size, content) the classifier uses. Fix and re-run. This is unlikely if the padding is implemented correctly, but worth planning for.

---

## 10. What to Do with Results

**If strong success:** Add results to paper (new Section 7.6 becomes real data instead of an evaluation plan). Update blog with a follow-up. Push to GitHub. This dramatically strengthens any venue submission.

**If partial success:** Document honestly. The partial leak itself is interesting — it shows the engineering difficulty of channel shaping and motivates future work on tighter implementations. Still publishable and still valuable.

**If failure:** Debug. The most likely cause is timing leakage (real tool calls have different latency distributions than dummy computation). Fix the timing model, re-run. If the failure is fundamental (not fixable with engineering), that's also a publishable result — it constrains the feasibility of the framework.

---
