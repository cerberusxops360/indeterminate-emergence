# Changelog

## [0.4.1] - 2026-11-22

### Fixed
- eval/results/syscall_trace_*.txt: the local account name in file paths is replaced with
  /home/user. Syscall names, order, timestamps and durations are unchanged; the getcwd
  return length still reflects the original path
- eval/syscall_trace.py: saved traces are normalized the same way

### Added
- tests/test_repo_hygiene.py: fails if a tracked text file carries a local home-directory path

## [0.4.0] - 2026-11-21

### Added
- proxy: optional owner token per session (KI-005). The leakage budget is charged to the caller, only
  the owner can cause real work, anonymous callers are absorbed on their own budget, and
  `absorption_listeners` are called out of band when a budget runs out
- eval/redteam_fuzz.py: differential fuzz over real HTTP (40 probe types, five session states per tool)
- eval/adversary_battery.py: six stronger statistical adversaries with a Bonferroni rule and a 3 ms
  positive control
- results/redteam_fuzz.json, results/adversary_battery.json
- eval/wire_capture_tls.py and eval/sequential_adversary.py, with results

### Results
- Adversary battery, five tools, 400 sessions per class: no leak flagged in 30 comparisons; the positive
  control was detected on every tool
- Differential fuzz: no difference between session states in status, headers or body; no latency
  difference beyond chance
- Wire capture under TLS (loopback): identical byte counts and segment sequences across authorized,
  unauthorized and absorbing connections; KI-001 closed again on valid evidence
- Sequential adversary over 48 probes: guesses at chance (47.9 percent), against 75.8 percent with a
  planted 3 ms difference

## [0.3.0] - 2026-11-21

### Changed
- Paper: Capability-Inference Game added as Definition 3; Section 12 rewritten with a separation
  proposition (ORAM, constant-time execution, deniable encryption) and a reduction proposition
  (Level 1 needs no new cryptographic primitive); "novel primitive" retired in favor of "mechanism"
- Paper: Section 7.6 now reports the certified Level 1 results, the partial Level 2 observations
  (syscall traces and timing autocorrelation, re-run 2026-11-21), and withdraws the five April 2026
  results that came from the faulty harness, including the budget-depletion figure
- docs/EMPIRICAL_FINDINGS.md: correction notice scoped to the experiments actually affected
- Paper: abstract says "statistically indistinguishable", matching the formal definitions
- Paper status line, LaTeX source, PDF, and blog post no longer state an IACR ePrint submission
- README: proof of concept and Level 1 result described; status list brought up to date
- Manifest content hashes updated for the changed files

### Fixed
- proxy: the timing shaper can no longer be switched off by sending the request body slowly (KI-002)
- proxy: malformed bodies, non-string fields, wrong paths and wrong methods all receive the same shaped
  response as any other request (KI-003)
- proxy: OpenAPI schema and interactive docs are no longer served (KI-004)
- Six regression tests added for the above

### Known issues recorded
- KI-001 reopened (its evidence came from the faulty harness); KI-005, KI-006, KI-007 opened

## [0.2.0] - 2026-04-11

### Added
- PoC core system: all five components implemented
  - config.py: session capability tokens, policy check
  - executor.py: sealed executor with normal and absorption paths
  - channel_shaper.py: fixed-size (4096 byte) and fixed-timing (200-400ms) response shaping
  - accountant.py: privacy budget tracker with sticky absorption
  - proxy.py: FastAPI /action endpoint integrating all components
- Test suite: 55 tests across all modules
- Three evaluation experiments:
  - divergence_test.py: TV distance and KL divergence across configs
  - classifier_attack.py: 4 adversarial classifiers targeting <= 52% accuracy
  - budget_depletion.py: adaptive adversary posterior convergence
- Pinned requirements.txt with all dependencies
- ADAM manifest entries for all PoC components and experiments

## [0.1.1] - 2026-03-13

### Added
- BibTeX citation in README
- LaTeX source and bibliography (paper/indeterminate-emergence-v1.tex)
- Submission-ready PDF (paper/indeterminate-emergence-v1.pdf)

## [0.1.0] - 2026-03-13

### Added
- Initial repository structure
- Paper v1 (revised draft with full citations, writing standards applied)
- Blog post (writing standards applied)
- Project plan and PoC specification
- CLAUDE.md execution contract
- ADAM manifest with SHA-256 fingerprints
