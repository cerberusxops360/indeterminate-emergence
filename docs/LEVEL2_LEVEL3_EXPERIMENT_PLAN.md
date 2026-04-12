# Level 2/3 Adversary Experiment Plan

**Status:** Draft — pending AGORA review
**Author:** Adam Bishop, XOps360 LLC
**Date:** 2026-04-12
**Depends on:** PoC core system (complete), Level 1 evaluation results (complete)
**Paper reference:** Sections 5.2 (Resource Trace Model), 6.1-6.3 (Adversary Models), 13 (Buildability)

---

## 1. Objective

Extend the IE evaluation from Level 1 (network-only) adversary resistance to Level 2
(system-level) and Level 3 (co-located) adversary resistance. The Level 1 PoC validates
that HTTP responses are indistinguishable. Levels 2 and 3 ask whether an adversary with
deeper system access can distinguish authorized from unauthorized execution through
side channels the HTTP proxy does not control.

---

## 2. Adversary Definitions (from paper Section 5.2)

**Level 2 — System-Level Adversary:**
Observes system call traces, memory allocation patterns, and fine-grained timing
(microsecond or nanosecond granularity). Has access to OS-level instrumentation
(strace, perf, /proc) but not to the sealed executor's internal state.

**Level 3 — Co-Located Adversary:**
Shares hardware with the executor. Observes cache timing (Flush+Reload, Prime+Probe),
CPU power consumption, memory bus contention, and branch prediction state. This is the
adversary model for shared-tenancy cloud deployments.

---

## 3. What Level 1 Does Not Cover

The current PoC normalizes three channels:
- Response size (4096 bytes fixed) — verified: zero variance
- Response timing (200-400ms window) — verified: KS test p > 0.05
- Response content (always `{"result": null}`) — verified: identical

The following channels are NOT normalized and are observable by Level 2/3 adversaries:

| Channel | Level | Current Exposure |
|---------|-------|------------------|
| System call trace (strace) | 2 | `simulate_tool()` and `dummy_computation()` likely differ in syscall patterns |
| Memory allocation | 2 | Real tool execution may allocate differently than SHA-256 dummy |
| Fine-grained timing (< 1ms) | 2 | asyncio.sleep resolution is ~1ms; sub-ms differences may leak |
| CPU utilization pattern | 2 | Real vs dummy workloads have different CPU profiles |
| Cache line access pattern | 3 | Code path divergence between normal and absorption creates cache signatures |
| Branch prediction state | 3 | Conditional branches on `authorized` flag leave predictor state |
| TLS handshake timing | 2 | Connection establishment may vary (out of proxy scope) |
| TCP window / flow control | 2 | OS-level TCP behavior may correlate with payload generation timing |

---

## 4. Experiment Design

### 4.1 Experiment 4: System Call Trace Indistinguishability (Level 2)

**Goal:** Determine whether `strace` output differs between authorized and unauthorized
request handling.

**Method:**
1. Run the IE proxy under `strace -f -e trace=all -T -o trace_auth.log` with an
   authorized session, send 100 requests.
2. Repeat with an unauthorized session (`trace_unauth.log`).
3. Parse traces into per-request syscall sequences.
4. Compare:
   - Syscall count distributions (KS test)
   - Syscall type histograms (chi-squared test)
   - Syscall timing sequences (DTW distance or sequence alignment)
5. Train a classifier on (syscall_count, unique_syscalls, total_syscall_time) features.

**Success criteria:** KS p-value >= 0.05 on syscall count distributions; classifier
accuracy not significantly above chance (binomial test p >= 0.05).

**Expected failure mode:** `simulate_tool()` makes different syscalls than
`dummy_computation()` (e.g., different async I/O patterns). Fix: unify the code paths
so both execute the same syscall sequence regardless of authorization.

**Implementation notes:**
- `strace -f` captures all threads/processes spawned by uvicorn.
- Parse with a script that segments traces by request (correlate via timing or PID).
- The proxy must run as a regular process, not in Docker, for strace access.

### 4.2 Experiment 5: Memory Allocation Profiling (Level 2)

**Goal:** Determine whether heap allocation patterns differ between authorized and
unauthorized execution.

**Method:**
1. Instrument the proxy with `tracemalloc` (Python stdlib) or `memray`.
2. Record per-request allocation snapshots for 100 authorized and 100 unauthorized
   requests.
3. Compare:
   - Total bytes allocated per request
   - Number of allocation calls per request
   - Peak memory per request
   - Allocation site distributions

**Success criteria:** No statistically significant difference (KS test p >= 0.05) in
total bytes allocated or allocation count between authorized and unauthorized requests.

**Expected failure mode:** `simulate_tool()` allocates strings for tool output;
`dummy_computation()` allocates differently (hashlib buffer). Fix: ensure dummy
computation allocates the same size and count of objects.

### 4.3 Experiment 6: Microsecond Timing Resolution (Level 2)

**Goal:** Determine whether timing differences below the 200-400ms shaping window
leak information at microsecond resolution.

**Method:**
1. Modify the proxy to log `time.perf_counter_ns()` at request start and response
   send (internal timing, not visible to HTTP client).
2. Record 500 authorized and 500 unauthorized requests.
3. Compare internal execution time distributions at microsecond resolution.
4. Also measure from the client side using `time.perf_counter_ns()` instead of
   `time.monotonic()` to capture sub-millisecond HTTP timing.

**Success criteria:** KS test p >= 0.05 at microsecond resolution. If the shaping
window is working, internal timing differences should be absorbed by the padding.

**Expected failure mode:** The asyncio event loop introduces quantization artifacts —
real tool calls may cause different event loop scheduling than dummy computation,
visible as timing clusters at microsecond scale. Fix: ensure both paths yield to the
event loop the same number of times.

### 4.4 Experiment 7: Cache Timing Side Channel (Level 3)

**Goal:** Determine whether Flush+Reload or Prime+Probe cache attacks can distinguish
authorized from unauthorized execution.

**Method:**
1. Run the proxy on a dedicated core (taskset / cpuset).
2. Run a co-located spy process on a sibling core (shared L2/L3 cache).
3. The spy performs Flush+Reload on the proxy's code pages:
   - Flush a cache line covering `simulate_tool` function entry
   - Wait for a request to be processed
   - Reload and measure access time — fast reload means the function was executed
4. Repeat for `dummy_computation` code pages.
5. Compare cache hit patterns between authorized and unauthorized requests.

**Success criteria:** The spy cannot determine which code path executed with advantage
above chance (binomial test p >= 0.05).

**Expected failure mode:** `simulate_tool` and `dummy_computation` are at different
code addresses. Cache monitoring trivially distinguishes them. Fix: either:
- (a) Execute both functions on every request and discard the unused result, or
- (b) Run the executor inside a TEE/enclave that prevents cache observation, or
- (c) Implement constant-address execution: a single function that takes both code
  paths through the same instruction sequence (branchless where possible).

**Implementation notes:**
- Flush+Reload requires shared memory pages (same binary or shared library).
- For Python: the CPython interpreter's opcode dispatch is the observable, not the
  Python source. Cache attacks on interpreted languages are noisier but documented.
- Reference: Bernstein 2005 (cache-timing attacks on AES) [paper ref 10].
- This experiment requires C/Rust tooling for the spy process. Python cannot measure
  cache timing at the required resolution.

### 4.5 Experiment 8: CPU Branch Prediction Leakage (Level 3)

**Goal:** Determine whether the conditional branch on `authorized`/`absorbing` flags
leaves observable branch predictor state.

**Method:**
1. Use hardware performance counters (`perf stat -e branch-misses,branches`) to
   measure branch prediction behavior during authorized vs unauthorized requests.
2. Compare branch miss rates between the two conditions.
3. Alternatively, use a Spectre-style gadget from a co-located process to probe
   branch predictor state (research context only — controlled environment).

**Success criteria:** No statistically significant difference in branch miss rates.

**Expected failure mode:** The `if not authorized or absorbing` branch in
`executor.py:execute()` trains the predictor differently depending on the path taken.
Over many requests, the predictor state leaks which path is more common. Fix:
branchless conditional assignment (in a compiled language; Python's interpreter
makes this moot for the PoC).

**Practical note:** This experiment is primarily relevant if the executor is
reimplemented in C/Rust for production. The CPython interpreter's branch prediction
behavior is dominated by interpreter overhead, not application-level branches.
Include for completeness but flag as lower priority for the Python PoC.

---

## 5. Implementation Roadmap

### Phase A: Instrumentation (Level 2 experiments)

| Step | Experiment | Effort | Dependency |
|------|-----------|--------|------------|
| A1 | Syscall tracing harness | 1 day | strace, trace parser script |
| A2 | Memory profiling harness | 1 day | tracemalloc or memray |
| A3 | Microsecond timing instrumentation | 0.5 day | time.perf_counter_ns |
| A4 | Run Experiments 4-6 | 1 day | A1-A3 complete |
| A5 | Analyze results, iterate on executor | 1-2 days | Depends on findings |

### Phase B: Side Channel Tooling (Level 3 experiments)

| Step | Experiment | Effort | Dependency |
|------|-----------|--------|------------|
| B1 | Cache spy process (C/Rust) | 2-3 days | Flush+Reload implementation |
| B2 | CPU pinning + isolation harness | 0.5 day | taskset, cpuset |
| B3 | Run Experiment 7 | 1 day | B1-B2 complete |
| B4 | Branch prediction profiling | 1 day | perf counters |
| B5 | Run Experiment 8 | 0.5 day | B4 complete |
| B6 | Analyze results, assess TEE requirement | 1-2 days | Depends on findings |

### Phase C: Mitigations (if experiments reveal leakage)

| Mitigation | Level | Approach |
|------------|-------|----------|
| Unified syscall paths | 2 | Refactor executor so both paths make identical syscalls |
| Matched allocation profiles | 2 | Dummy computation mirrors real allocation sizes/counts |
| Event loop normalization | 2 | Both paths yield to event loop same number of times |
| Dual-path execution | 3 | Execute both real and dummy on every request, discard one |
| TEE encapsulation | 3 | Run executor in SGX/SEV enclave (eliminates cache/branch leakage) |
| Compiled executor | 3 | Reimplement executor in Rust with constant-time patterns |

---

## 6. Relationship to Existing Evaluation

The Level 2/3 experiments extend, not replace, the Level 1 evaluation:

| Experiment | Level | Status |
|-----------|-------|--------|
| 1: Divergence test (TV/KL/KS) | 1 | PASS |
| 2: Classifier attack (4 classifiers) | 1 | PASS |
| 3: Budget depletion (posterior convergence) | 1 | PASS |
| 4: Syscall trace indistinguishability | 2 | Planned |
| 5: Memory allocation profiling | 2 | Planned |
| 6: Microsecond timing resolution | 2 | Planned |
| 7: Cache timing side channel | 3 | Planned |
| 8: Branch prediction leakage | 3 | Planned |

---

## 7. Open Questions (from Research Notes 2026-04-12)

The following questions arose during PoC evaluation and red team methodology analysis.
They are related to the Level 2/3 work but may warrant separate investigation tracks.

### Q1: Active Timing Injection Test (Chosen-Ciphertext Analog)

Should the evaluation include an active distinguisher that sends crafted request
timing patterns (bursts, specific intervals) and observes whether response timing
distributions change? This is a stronger attack than passive observation — it tests
whether the timing shaper is robust to adversary-controlled input timing.

**Recommendation:** Spec as a separate experiment (Experiment 9) under Level 2. The
current shaper draws timing independently of request arrival; an active injection test
validates this independence. Suitable for its own AGORA seed — the methodology connects
to chosen-ciphertext attack literature more than to system-level side channels.

### Q2: Calibration Mode for Divergence Test (Canary Token Validation)

Should `divergence_test.py` get a `--calibration` flag that introduces a deliberate
timing bias (e.g., 50ms) between authorized and unauthorized requests? This validates
that the test has sufficient statistical power to detect differences of a known
magnitude before trusting its "no difference found" result.

**Recommendation:** Implement directly — this is a test infrastructure improvement, not
a research question. Add `--bias-ms N` flag to `divergence_test.py`. If the test cannot
detect a 50ms bias with 200 samples, increase sample count or bin resolution. Does not
need an AGORA seed.

### Q3: ML-Based Distinguisher for Full Paper

Is a dedicated ML-based distinguisher test (beyond the 4 classifiers in Experiment 2)
worth adding for a journal submission? Reference: Wang et al. k-NN and random forest
classifiers for website fingerprinting.

**Recommendation:** Yes, but as a paper-strengthening addition, not a gate requirement.
The current classifier attack uses session-level features (mean, std, min, max, median
of timing). A stronger distinguisher would use raw timing sequences as input to an LSTM
or 1D-CNN, which can detect temporal correlations the summary statistics miss. Suitable
for its own AGORA seed — connects to traffic analysis attack literature.

### Q4: Strongest Traffic Analysis Attack Against Current Proxy

What is the strongest known traffic analysis attack applicable to the IE proxy's fixed-
size, fixed-timing response pattern? Does the current padding scheme have known
weaknesses from the traffic analysis literature?

**Recommendation:** This is a literature review question. Dyer et al. 2012 (paper ref
[9], "Peek-a-Boo, I Still See You") specifically analyzes why traffic analysis
countermeasures fail — directly relevant to IE's channel shaper. Suitable for its own
AGORA seed — the answer informs whether the current shaper design needs revision before
Level 2/3 work begins.

---

## 8. Suggested AGORA Seed Decomposition

| Seed | Scope | Priority |
|------|-------|----------|
| **This document** | Level 2/3 experiment plan — methodology, tooling, mitigations | Primary |
| Q1 + Q3 | Active timing injection + ML distinguisher — adversarial methodology | Secondary |
| Q4 | Traffic analysis literature review — shaper design validation | Secondary |

Q2 (calibration mode) does not need a seed — implement directly.
