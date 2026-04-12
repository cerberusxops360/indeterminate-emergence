# IE Level 2/3 Empirical Assessment

**Mode:** Oracle Dialogue
**Max rounds:** 3
**Vector radius:** 1
**Objective:** Assessment — evaluate what empirical data means for published security claims. Do not re-derive theory from first principles. Ground every claim in the source code and experiment results below.

---

## Mandatory Pre-Read

The previous six-round investigation (AGI_c81730101d944e7cad17) never read the source code. Every quantitative prediction in that investigation was conditional on unverified implementation assumptions. Those assumptions are now resolved. **Agents must read the source below before doing anything else.** Treat it as ground truth for all analysis in this session.

---

## Source Code: `poc/src/executor.py`

```python
import asyncio
import hashlib
import json
import random


async def simulate_tool(tool_name: str, params: dict) -> str:
    """Simulate a real tool call with realistic latency and output."""
    latency = random.uniform(0.05, 0.3)
    await asyncio.sleep(latency)

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
    Consumes similar CPU time and memory as a real tool call.
    """
    latency = random.uniform(0.05, 0.3)
    await asyncio.sleep(latency)
    hashlib.sha256(random.randbytes(1024)).hexdigest()
    return json.dumps({"result": None})


async def execute(
    tool_name: str,
    params: dict,
    authorized: bool,
    absorbing: bool,
) -> str:
    """
    Core execution logic. Three cases, all producing the same external observation:
    1. Not authorized -> dummy computation
    2. Authorized but absorbing -> dummy computation
    3. Authorized and normal -> real tool call
    """
    if not authorized or absorbing:
        return await dummy_computation()
    return await simulate_tool(tool_name, params)
```

**Key facts from the source:**
- Both paths: `await asyncio.sleep(random.uniform(0.05, 0.3))` — identical yield mechanism
- `dummy_computation` adds: `hashlib.sha256(random.randbytes(1024)).hexdigest()` — ~1KB SHA-256, CPU-bound, ~0.05ms
- No real I/O, no network calls, no file access on either path
- Single conditional branch on `authorized` — the only semantic divergence
- Server: single uvicorn worker, single-threaded asyncio, Python 3.12.3

---

## Source Code: `poc/src/channel_shaper.py`

```python
import asyncio
import json
import random
import time

RESPONSE_SIZE = 4096  # bytes, fixed
MIN_LATENCY = 0.2     # 200ms minimum
MAX_LATENCY = 0.4     # 400ms maximum


def pad_payload(raw_result: str) -> dict:
    """Create a fixed-size response body regardless of raw_result content."""
    response = {
        "status": "processed",
        "receipt": "ack",
        "payload": "",
        "padding": "",
    }

    skeleton_size = len(json.dumps(response).encode("utf-8"))
    available = RESPONSE_SIZE - skeleton_size

    def json_str_bytes(s: str) -> int:
        return len(json.dumps(s).encode("utf-8")) - 2

    payload = raw_result
    payload_bytes = json_str_bytes(payload)

    if payload_bytes > available:
        lo, hi = 0, len(payload)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if json_str_bytes(payload[:mid]) <= available - 1:
                lo = mid
            else:
                hi = mid - 1
        payload = payload[:lo]
        payload_bytes = json_str_bytes(payload)

    response["payload"] = payload
    padding_bytes_needed = available - payload_bytes
    if padding_bytes_needed > 0:
        response["padding"] = "x" * padding_bytes_needed

    actual = len(json.dumps(response).encode("utf-8"))
    diff = RESPONSE_SIZE - actual
    if diff > 0:
        response["padding"] = response["padding"] + "x" * diff
    elif diff < 0:
        response["padding"] = response["padding"][:len(response["padding"]) + diff]

    return response


async def shape_timing(execution_start: float) -> None:
    """Ensure total response time falls within [MIN_LATENCY, MAX_LATENCY]."""
    target = random.uniform(MIN_LATENCY, MAX_LATENCY)
    elapsed = time.monotonic() - execution_start
    remaining = target - elapsed

    if remaining > 0:
        await asyncio.sleep(remaining)


async def shape_response(raw_result: str, execution_start: float) -> dict:
    """Full channel shaping: pad size + pad timing."""
    response = pad_payload(raw_result)
    await shape_timing(execution_start)
    return response
```

**Key facts from the source:**
- Response size: exactly 4096 bytes, enforced by binary-search padding
- Timing: `random.uniform(0.2, 0.4)` seconds — uniform distribution over a 200ms window
- Timing is target-from-start, not padding-after-completion: `remaining = target - elapsed`
- If executor finishes early, shaper sleeps the remainder. If executor overshoots 400ms, no additional sleep (no hard cap on overshoot)
- No request-side padding — only response is shaped
- Timing seed: `time.monotonic()` at request entry in proxy; shaping draws a fresh `random.uniform` per request

---

## Empirical Results: Experiments 4–7

All experiments run on oracle-prime (single uvicorn worker, Python 3.12.3, loopback interface).

### Experiment 4 — Syscall Trace Comparison (strace -tt -T, 5 runs per path)

| Metric | Authorized | Unauthorized |
|---|---|---|
| Total syscall events | 7,415 | 7,415 |
| Total syscall time | 802.56ms | 754.11ms |
| Path-exclusive syscall types | 0 | 0 |
| Top syscall by time | epoll_wait (766ms) | epoll_wait (718ms) |

**Timing delta:** 802.56ms − 754.11ms = **48.45ms** across 5 runs (~9.7ms per run average difference).

**Top syscalls by count (both paths identical):** newfstatat (1960), fstat (1115), read (1010), lseek (920), close (660), openat (640).

**Assessment:** No path-exclusive syscall types. Both paths dominated by `epoll_wait` (asyncio sleep). The 48ms aggregate timing difference is not per-request — it is aggregate over 5 strace runs, each covering the full Python interpreter startup + module import + one function call. Per-request delta is within the variance of `random.uniform(0.05, 0.3)`.

---

### Experiment 5 — Timing Autocorrelation (server-side perf_counter_ns)

Execute() + shape_response() called directly, bypassing HTTP.

**n=500 run (initial):**

| Metric | Authorized | Unauthorized |
|---|---|---|
| Mean (ms) | 302.355 | 306.138 |
| Std (ms) | 55.786 | 56.764 |
| p5 (ms) | 213.360 | 216.556 |
| p50 (ms) | 300.319 | 306.363 |
| p95 (ms) | 392.240 | 391.780 |
| p99 (ms) | 399.284 | 399.670 |
| KS statistic | 0.074 | |
| KS p-value | 0.129 | |
| KS result | PASS | |
| Max \|ACF\| lags 1-10 (auth) | 0.1125 (lag-3) | |
| Max \|ACF\| lags 1-10 (unauth) | 0.0703 | |

**n=2000 rerun (ACF confirmation):**

| Lag | Authorized | Unauthorized |
|---|---|---|
| 1 | 0.0159 | 0.0111 |
| 2 | −0.0018 | 0.0317 |
| 3 | −0.0062 | 0.0240 |
| 4 | 0.0041 | −0.0114 |
| 5 | 0.0230 | 0.0217 |
| Max \|ACF\| lags 1-5 | 0.0230 | 0.0317 |
| KS statistic | 0.033 | |
| KS p-value | 0.226 | |

**Verdict:** Lag-3 ACF of −0.1125 at n=500 collapsed to −0.0062 at n=2000 (18× reduction). Sampling noise. No temporal leakage detected in the timing series.

---

### Experiment 6 — Active Burst Injection (10 concurrent, 50 bursts, 500 total per path)

| Metric | Authorized | Unauthorized |
|---|---|---|
| Mean RTT (ms) | 311.511 | 317.667 |
| Std (ms) | 55.006 | 55.700 |
| p95 (ms) | 398.947 | 403.393 |
| p99 (ms) | 411.708 | 410.807 |
| Within-burst std, mean (ms) | 52.151 | 52.903 |
| \|p95_auth − p95_unauth\| | 4.445ms | |
| \|p99_auth − p99_unauth\| | 0.902ms | |
| KS statistic | 0.054 | |
| KS p-value | 0.460 | |
| KS result | PASS | |

**H4 event loop starvation check:** Prior theoretical prediction (Agora round 5) was tail divergence >20ms under 10-concurrent burst if dummy was CPU-bound. Actual tail divergence: 4.4ms at p95, 0.9ms at p99. **H4 does not apply** — both paths yield via asyncio.sleep and neither starves the event loop.

---

### Experiment 7 — Wire-Level Capture

**Sub-test 1 (HTTP body size, 200 requests total):**

| Path | All exactly 4096 bytes | Min | Max |
|---|---|---|---|
| Authorized | True | 4096 | 4096 |
| Unauthorized | True | 4096 | 4096 |

Result: PASS — response size padding holds at the HTTP layer across all requests.

**Sub-test 2 (TCP packet distribution):** Skipped — tcpdump requires elevated capabilities on oracle-prime. Packet-level distinguishability is unmeasured. This is the one empirically open item.

---

## Assessment Questions

Agents must answer all four. Ground every answer in the source code and experiment results above. Do not introduce implementation assumptions — the source is complete.

**Q1 — Syscall timing delta:**
The aggregate strace timing across 5 runs shows 802ms (authorized) vs 754ms (unauthorized) — a 48ms difference over 5 runs (~9.7ms per run). Is this a meaningful Level 2 leakage risk? At what sample size would a strace-capable adversary be able to distinguish paths based on aggregate syscall time? The shaping window is uniform(200, 400ms). The executor latency is uniform(50, 300ms). Work through the statistics.

**Q2 — Timing model safety:**
`shape_timing` targets `random.uniform(0.2, 0.4)` from request start. The executor draws `random.uniform(0.05, 0.3)`. Executor max (300ms) + framework overhead can approach or exceed the shaping target max (400ms). When the executor overshoots 400ms, there is no sleep — the response goes out immediately with no additional padding. How often does this happen under the current distributions? Does the overshoot case constitute a timing oracle? Quantify the exposure.

**Q3 — Request-side padding:**
Only responses are padded to 4096 bytes. Request bodies vary by tool name and params. A Level 1 adversary observing request sizes can potentially distinguish `simulate_tool` calls (which include tool-name and params) from `dummy_computation` (which still sends a request body). Is this a meaningful attack surface given the current threat model? The proxy endpoint is `/action` and always receives a JSON body — evaluate whether request-size variation leaks path information.

**Q4 — Level 2/3 future work section:**
The paper (IACR ePrint 2026/108326) states that Level 2/3 protection "requires increasingly constrained execution environments (dedicated processes, TEEs) and is analogous to the challenges faced by constant-time cryptographic implementations." Given the empirical results above, what concrete mitigations — if any — are actually needed before this claim is accurate? Separate: (a) what is already handled by the current implementation, (b) what is a real gap the paper should acknowledge, (c) what is genuinely out of scope for a Python PoC and should be stated as such.

---

## Context

- **Paper:** IACR ePrint 2026/108326 — indeterminate emergence
- **Author:** Adam Bishop, XOps360 LLC
- **PoC:** Single uvicorn worker, loopback, Python 3.12.3
- **Level 1 experiments (Experiments 1–3):** All pass. Distributions indistinguishable at KS α=0.05.
- **Prior agora investigation:** AGI_c81730101d944e7cad17, 6 rounds, stagnated on source-verification gap. All critical findings from that session are superseded by the empirical data above.
- **Threat model summary:** Level 1 = network-only adversary (coarse RTT, response size, content). Level 2 = system-level adversary (strace, /proc, microsecond timing). Level 3 = co-located adversary (cache timing, branch prediction, power). The PoC claims Level 1 protection. The paper acknowledges Level 2/3 as open problems requiring hardware mitigations.

---

## What This Investigation Should Produce

Three deliverables, one per round:

**Round 1:** Direct answers to Q1–Q4 grounded in the source and data. No open questions — commit to positions with confidence levels.

**Round 2:** Identify any internal contradictions or overlooked implications in Round 1 answers. Surface the hardest objection to the most confident claim.

**Round 3:** Synthesize into a concrete recommendation: what, if anything, needs to change in the implementation or the paper's Level 2/3 claims before the paper is accurate as written. Specific and actionable — not "further research is needed."
