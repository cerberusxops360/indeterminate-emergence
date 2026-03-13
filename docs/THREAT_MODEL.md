# Threat Model

For formal adversary definitions, see the paper Section 6.

## Four Adversary Tiers

**Level 1 -- Passive Transcript Observer**
Sees HTTP responses only (timing, size, content). Network-level access.
This is the adversary the proof of concept targets.

**Level 2 -- Active Adaptive Querier**
Chooses probe actions based on response history. Bounded by the leakage budget.

**Level 3 -- Insider (Partial Context)**
Has access to system calls, memory, or logs outside the sealed executor boundary.

**Level 4 -- Colluding Endpoint**
Receives the actual effects of authorized actions. Fundamental limit acknowledged:
the framework cannot hide effects from whoever receives them.

## PoC Scope

The proof of concept validates guarantees against Level 1 only. Levels 2-4 are
characterized in the paper for completeness but are not targeted by the current
implementation.
