# Level 3 and Deferred High-Capability Adversaries (decision note, 2026-10-04)

Status: captures a decision that had been verbal. No prior written rented-compute
plan was found in the repo, the paper, the project docs, or the ADAM notes vault; this note
replaces that missing record.

## Where Levels 1 and 2 stand
- Level 1 (network observer): certified. Single pre-registered RandomForest, probe n up to
  120k per condition, real-vs-negative-control noise-floor rule, positive control detects a
  3ms bias. Per-tool capability-inference advantage certified at or below 1 pct at 95 pct
  confidence (web_search 0.36, code_exec 0.30, database_query 0.63; calculator and file_read
  rerun at higher n to pull under 1 pct). See results/gate-rebuild-2026-10-04.md.
- Level 2 (system): syscall-type indistinguishability holds incidentally; process-per-session
  isolation and the memory/CPU experiments are not yet done. Tractable systems work.

## Level 3 (co-located) experiment design (Experiments 7 and 8)
Cache side channel: proxy pinned to one core (taskset/cpuset), a co-located spy on a sibling
core sharing L2/L3, Flush+Reload or Prime+Probe on the simulate_tool vs dummy_computation
code pages. Branch predictor: perf counters on branch-misses, or a Spectre-style gadget from a
co-located process.

The binding blocker is NOT the machine. It is that the executor is CPython: cache and branch
attacks on interpreted code are dominated by interpreter overhead, and Python cannot measure
cache timing at the needed resolution. A faithful Level 3 result requires reimplementing the
executor in C or Rust with constant-address, branchless execution (or running both paths every
request and discarding the unused result, or a TEE). Only then does the choice of machine matter.

## The deferred high-capability adversary (the thing that needed a system we do not have)
Vectors in the Level 3 model that exceed the current setup, and what rented compute can and
cannot supply:
- Cache side channels (Exp 7): need bare-metal with perf access, CPU pinning, known cache
  topology. Ordinary cloud VMs disable the primitives or float vCPUs and break the attack.
  Satisfiable by a dedicated, perf-enabled bare-metal cloud instance. An internal host can
  also host the controlled self-attack test; bare-metal cloud only adds a clean, reproducible,
  named-microarchitecture environment a reviewer can replicate.
- Branch predictor / Spectre gadget (Exp 8): same, plus a chosen microarchitecture. Cloud
  bare-metal satisfies it.
- Heavyweight ML / traffic-analysis adversary at large scale: if a maximal distinguisher
  (deep nets, very large n) is wanted beyond the RandomForest used, that wants a GPU instance.
  A cloud GPU instance satisfies it.
- Power consumption and EM emanations (named in the paper Level 3 definition): require physical
  lab instrumentation (oscilloscope, EM probe, hardware access). NO cloud can provide this. This
  is a hardware-lab item and should be scoped out permanently, not deferred to rented compute.

## Recommendation
For the paper: scope Level 3 out honestly. State it as a deployment requirement (compiled
constant-address executor, or TEE) and name the known fixes and attacks; do not claim coverage.
If Level 3 is later pursued empirically: build the C/Rust constant-address executor first, run
the controlled cache test on an internal host, and reach for a bare-metal cloud node only for
a reproducible, named-hardware demonstration. Pursue power/EM only with a real hardware lab, or
not at all. A maximal ML adversary on a GPU box is optional and lower priority given the
RandomForest result already certifies sub-1 pct at Level 1.

## Decision (Adam): TBD
