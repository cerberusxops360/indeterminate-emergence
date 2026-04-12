# IE Research Notes

Running notes on tangential insights, methodology connections, and questions worth pursuing.
Append-only. Date each entry.

---

## 2026-04-12 — Load Balancers Don't Help (and Can Hurt)

**Observation:** A load balancer operating at the network/TCP layer does not strengthen IE's
indistinguishability guarantee. The adversary's observable is the HTTP response, which the IE
proxy has already normalized before the load balancer touches it.

**Why irrelevant:** IE's guarantee is an application-layer property. The proxy produces fixed
4096-byte responses with 200-400ms timing regardless of authorization state. The load balancer
distributes requests across backends but doesn't change what the distinguisher sees. The
adversary in the IE threat model observes (response content, response size, response timing) —
none of which are affected by routing decisions upstream.

**Why it could actively hurt:** Many load balancers inject observable headers: Via,
X-Forwarded-For, load-balancer instance identifiers, or backend correlation IDs. These introduce
new side channels that the IE proxy doesn't control. Explicit header stripping would be required
to prevent this.

**What would help at the network layer:** Only onion routing or a mix network would strengthen
IE against a network-layer adversary — but those address routing indistinguishability, not access
pattern deniability at the credential store. A different threat model. Out of scope for IE PoC.

**Action:** None required. Documented for completeness. Revisit if threat model expands to
include routing observables.

---

## 2026-04-12 — Red Team / Ethical Hacking Methodology Connections

Several adversarial security testing principles from ethical hacking and penetration testing
apply directly to IE research methodology.

### 1. Timing Oracle Attacks — The Core Threat Model

IE defends against exactly the class of attack that breaks cryptographic implementations via
timing side channels.

- **Padding oracle attacks** (BEAST, POODLE) measure timing differences to infer whether
  decryption succeeded — without seeing the plaintext. IE's threat model is structurally
  identical: the distinguisher observes timing to infer whether a credential access was real
  or noise.
- **Blind SQL injection via timing** (SLEEP(), WAITFOR DELAY) uses deliberate latency to
  confirm or deny a condition. IE's 200-400ms timing normalization eliminates this attack
  surface at the HTTP layer.
- **Constant-time cryptographic implementations** (OpenSSL, BoringSSL) solve the same problem
  at a lower level — ensuring comparison operations don't leak via timing. IE is the analogous
  construction at the HTTP/credential layer.

Application to evaluation: the red team methodology for testing timing oracle defenses is
exactly what divergence_test.py implements — large samples, statistical distinguishing tests,
iterate until no measurable difference remains.

### 2. Traffic Analysis Attacks — What IE Is Defending Against

Traffic analysis infers information from patterns of communication rather than content.

- **VPN traffic analysis:** Packet sizes, timing intervals, and burst patterns reveal which
  websites are visited even with encrypted payloads.
- **Tor deanonymization via traffic correlation:** Entry/exit node observation correlates
  traffic patterns despite onion encryption.
- **Website fingerprinting:** Identifying visited sites via packet timing and size sequences
  over HTTPS.

IE's 4096-byte fixed padding + timing normalization is a traffic analysis countermeasure
applied to credential store access patterns. The design rationale is identical to mix network
padding and onion routing constant-size cells.

Reference for ML-based distinguisher work: Wang et al.'s k-NN and random forest classifiers
for website fingerprinting represent the strongest known distinguishers in this class. If IE
evaluation ever extends beyond TV/KL/KS to ML-based distinguishers, traffic analysis attack
tooling is the right reference point.

### 3. Oracle Attack Methodology — Active Timing Injection

In ethical hacking, an oracle gives a binary answer about secret state. Attacker methodology:
1. Identify the oracle (any observable correlated with secret state)
2. Craft queries to maximize information gain
3. Apply statistical or adaptive analysis to extract the secret

For IE: the oracle is the proxy's observable outputs. Current evaluation tests passive
observation (measure timing distributions of randomized authorized vs unauthorized requests).

**Chosen-ciphertext attacks analog (not yet implemented):** An active distinguisher sends
crafted request timing patterns — bursts vs. sparse — and observes whether response timing
distributions change. This is a stronger attack class worth testing in Experiment 2 or 3.
If IE's timing normalization holds against active injection patterns, the guarantee is stronger.

### 4. Canary Tokens — Calibration Tool for Evaluation

Canary tokens in ethical hacking are deliberately detectable artifacts placed in a system to
confirm an attacker WOULD find them if defenses failed. They validate detection power.

Application to IE: Before the formal gate test (10,000 trials, advantage <= 2^-20), validate
the distinguisher by introducing a deliberately leaky configuration:
- Remove timing normalization: distinguisher should detect with high advantage
- Remove payload padding: distinguisher should detect from size variation

If the test cannot detect a deliberate 50ms timing bias between authorized and unauthorized
requests, the test lacks statistical power. This is the analog of testing a SIEM by injecting
a known attack signature.

**Action:** Consider adding a --calibration mode to divergence_test.py that introduces a
configurable timing bias to confirm the test can detect differences of a known magnitude.

### 5. Differential Analysis — Already Implemented

Differential cryptanalysis analyzes how input differences propagate to output differences to
infer key material. IE's evaluation is structurally the same: run the proxy under two
configurations, observe the output difference distribution (timing, size), confirm differences
are below threshold. divergence_test.py TV/KL/KS is differential analysis applied to IE.

### 6. Statistical Distinguishing Attacks — The ML Extension

Modern applied cryptography uses ML-based distinguishers for testing PRNGs and cipher
primitives. Train a classifier to distinguish outputs of two configurations; measure the
classifier's advantage. If the best classifier can't beat random, the construction is
indistinguishable under that threat model.

Application to IE: After the statistical gate clears, a natural extension is an ML-based
distinguisher (gradient boosted trees or simple neural net) on the timing distributions. Not
required for the current gate — KS/TV/KL tests are sufficient for the PoC — but would
strengthen a journal version of the paper.

### 7. Covert Channels Beyond Timing and Size

Covert channel analysis asks: what channels exist that weren't intended for communication but
can leak information? CPU load, memory pressure, cache state, TCP window size, connection count.

Currently normalized by IE PoC:
- DONE: Response size (4096 bytes fixed)
- DONE: Response timing (200-400ms window)
- DONE: Response content (always {"result": null})

Not currently normalized:
- NOT DONE: TCP connection establishment timing — TLS handshake latency may vary
- NOT DONE: HTTP/2 stream behavior — stream priority or flow control may differ
- NOT DONE: Memory allocation patterns — in-process observer could measure heap allocation
- NOT DONE: CPU utilization — authorized requests may trigger more computation

These are out of scope for the PoC (threat model assumes proxy is the observation boundary).
Document for future versions if threat model expands.

---

## Open Questions

1. Should the evaluation include an active timing injection test (chosen-ciphertext analog)?
2. Should divergence_test.py get a --calibration mode for canary token validation?
3. Is an ML-based distinguisher test worth adding for the full paper?
4. What is the strongest traffic analysis attack against the current proxy configuration?
   (Wang et al. k-NN is the reference; apply to IE timing distributions)
