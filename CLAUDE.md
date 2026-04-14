# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Infrastructure Governance
This repo is classified as **T4 — Isolated** under the Infrastructure Governance Standard.
Before modifying shared infrastructure, read: `shared-library/standards/INFRASTRUCTURE-GOVERNANCE.md`
- **Deploy target:** local-only (research)
- **Dependencies:** None
- **Dependents:** None

# CLAUDE.md — Execution Contract
## indeterminate-emergence

## Framework Dependencies
> Canonical specs live in [shared-library](https://github.com/cerberusxops360/shared-library).
> Read these before modifying any framework-level behavior in this repo.

| Dependency | Spec | Why |
|------------|------|-----|
| Voice & Writing Standards | `standards/voice-writing/VOICE-STANDARDS.md` | Paper: MODERATE filter. Blog post: STRICT filter. |
| Epistemic Security | `frameworks/epistemic-security/ES-SPEC.md` | This repo IS the canonical implementation |

---

**Repo:** `cerberusxops360/indeterminate-emergence`  
**Project Type:** Open research — security theory + proof of concept  
**Author:** Adam Bishop, XOps360 LLC  
**ORCID:** https://orcid.org/0009-0000-4569-3726  
**License:** Paper: CC BY 4.0 | Code: MIT  
**ADAM Project ID:** ADAM-PROJ-IE  
**Status:** Phase 3 — PoC Build (next)  

---

## What This Repo Is

A security framework and proof-of-concept implementation for **indeterminate emergence** — a primitive where meaningful information, capabilities, and effects do not exist outside authorized execution contexts. The framework extends deniable encryption concepts to real-time system behavior, using Pufferfish-style privacy definitions and differential privacy composition to provide formal guarantees against capability inference attacks.

This is an open research project. The repo contains:
1. The academic paper (markdown, LaTeX, PDF)
2. A blog post (plain-language explanation)
3. A proof-of-concept proxy service demonstrating AI capability-set inference resistance
4. Evaluation experiments with quantitative results

---

## ADAM Integration

### Object Types

This repo introduces the following ADAM-managed object types:

```
RESEARCH_PAPER
  fingerprint: SHA-256 of paper markdown content
  tier: T1 (warm — actively edited during revision cycles)
  relationships: PRODUCES blog_post, SPECIFIES poc_system
  status: draft | submitted | published | revised

BLOG_POST
  fingerprint: SHA-256 of blog markdown content
  tier: T1 (warm — actively edited during publication cycle)
  relationships: DERIVED_FROM research_paper, PUBLISHED_TO platform_id

POC_COMPONENT
  fingerprint: SHA-256 of source file content
  tier: T1 (warm — actively developed)
  relationships: IMPLEMENTS paper_section, DEPENDS_ON component_id

EVAL_EXPERIMENT
  fingerprint: SHA-256 of experiment script + config
  tier: T1 (warm — actively running)
  relationships: VALIDATES paper_claim, USES poc_component

EVAL_RESULT
  fingerprint: SHA-256 of result data
  tier: T2 (cool — reference data, changes only on re-run)
  relationships: PRODUCED_BY eval_experiment, VALIDATES paper_claim

SUBMISSION_RECORD
  fingerprint: SHA-256 of submission metadata JSON
  tier: T3 (cold — changes only on new submission)
  relationships: SUBMITS research_paper, TARGETS venue_id
```

### Fingerprint Format

Standard ADAM format: `fp-{type}-{YYYYMMDD}-{8hex}-{4hex}`

Type codes for this repo:
```
rpap  — research paper
blog  — blog post
pocc  — proof of concept component
eval  — evaluation experiment
evrs  — evaluation result
subm  — submission record
```

Example: `fp-rpap-20260313-a7b3c9d2-e4f5`

### Manifest Entries

Every versioned artifact gets a manifest entry. Paper versions are tracked by content hash — if the hash changes, a new fingerprint is minted and the old version tiers down (T1 → T2 → T3). ADAM never deletes, only tiers down.

---

## Directory Structure

```
indeterminate-emergence/
├── CLAUDE.md                        # This file — execution contract
├── KNOWN_ISSUES.md                  # Active bugs and known limitations
├── CHANGELOG.md                     # Version history
├── LICENSE-CODE                     # MIT (for code)
├── LICENSE-PAPER                    # CC BY 4.0 (for paper and blog)
├── README.md                        # Public-facing overview
├── .gitignore
├── paper/
│   ├── indeterminate-emergence-v1.md    # Revised paper (source of truth)
│   ├── indeterminate-emergence-v1.tex   # LaTeX for arXiv submission
│   ├── indeterminate-emergence-v1.pdf   # Rendered PDF
│   ├── references.bib                   # BibTeX bibliography
│   ├── abstract.txt                     # Plain-text abstract
│   ├── IACR_SUBMISSION_NOTES.md         # Submission metadata
│   └── figures/                         # Any diagrams or charts
├── blog/
│   └── what-if-security-meant-non-existence.md  # Blog post
├── poc/                                 # ** Not yet built — target structure below **
│   ├── README.md                    # PoC overview, setup, usage
│   ├── requirements.txt             # Python dependencies (pinned)
│   ├── src/
│   │   ├── __init__.py
│   │   ├── proxy.py                 # FastAPI intent interface
│   │   ├── executor.py              # Sealed executor (normal + absorption)
│   │   ├── channel_shaper.py        # Response padding, timing, sizing
│   │   ├── accountant.py            # Privacy budget tracker
│   │   └── config.py                # Capability tokens, session config
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── divergence_test.py       # Experiment 1: distribution comparison
│   │   ├── classifier_attack.py     # Experiment 2: adversarial classifier
│   │   └── budget_depletion.py      # Experiment 3: adaptive probing
│   ├── results/                     # Evaluation output data
│   │   └── .gitkeep
│   └── tests/
│       ├── __init__.py
│       ├── test_proxy.py
│       ├── test_executor.py
│       ├── test_channel_shaper.py
│       └── test_accountant.py
├── docs/
│   ├── ARCHITECTURE.md              # Detailed component spec
│   ├── THREAT_MODEL.md              # Adversary tier definitions
│   ├── POC_SPECIFICATION.md         # Full PoC build spec
│   ├── PROJECT_PLAN.md              # Publication and launch plan
│   ├── CONTRIBUTING.md              # How to contribute
│   └── EMPIRICAL_FINDINGS.md        # Canon: Level 2/3 empirical assessment results
├── agora-seeds/
│   └── ie-level23-empirical.md      # Seed for AGI_9fac33d528a5453dbda3 (closed)
├── manifest/
│   ├── index.yaml                   # ADAM manifest index for this repo
│   └── objects/                     # Individual object manifests
└── .github/
    ├── CODEOWNERS                   # Requires owner approval on all PRs
    └── ISSUE_TEMPLATE/
        ├── bug_report.md
        └── research_question.md
```

**Follow this structure exactly.** Do not create files outside this tree without updating this document first.

---

## How to Work

1. **Read the relevant specification BEFORE writing code.** The PoC specification (`docs/POC_SPECIFICATION.md`) is the TDP for this repo. If code contradicts the spec, the code is wrong.

2. **Write tests FIRST, then implementation.** Tests define the contract. Every `src/` module has a corresponding `tests/test_*.py` file.

3. **Every new file gets an ADAM manifest entry.** Compute SHA-256 of content, assign fingerprint, add to `manifest/index.yaml`.

4. **Commit after each logical unit of work.** Descriptive messages. Format: `[component] description` — e.g., `[channel_shaper] implement fixed-size response padding`.

5. **Push immediately.** Do not accumulate uncommitted work.

6. **`git status` at session start.** Confirm clean working tree before beginning new work.

7. **Set git identity at session start:**
   ```bash
   git config user.name "Adam Bishop"
   git config user.email "adam@xops360.com"
   ```

8. **KNOWN_ISSUES.md-first debugging.** If you encounter a bug, log it in KNOWN_ISSUES.md before attempting a fix. If the fix works, remove the entry and commit both the fix and the KNOWN_ISSUES.md update.

9. **Pin all dependencies.** No floating versions in requirements.txt. Every package gets an exact version.

10. **No silent failures.** Every function either returns a result or raises an exception with a clear message. The proxy endpoint always returns HTTP 200 — but internal logging must capture all errors.

---

## Writing Standards

This repo contains public-facing written content (paper, blog post). All written content MUST comply with XOps360 Voice & Writing Standards:

### Banned Words (Tier 1 — Auto-Replace)
- leverage → use
- utilize → use  
- streamline → simplify / speed up
- comprehensive → [delete or replace with specific scope]
- robust → [replace with actual engineering characteristic]

### Banned Patterns
- Maximum ONE em dash per document
- No "Furthermore" or "Moreover" — ever
- No "However" more than once per 500 words
- No tricolon reflex (groups of three where two or four work better)
- No summary sandwich (introduce → say → summarize)
- No Wikipedia openers ("In the rapidly evolving field of...")

### Claude-Specific Patterns to Avoid
- "That's a great question" / "That's an interesting point"
- "It's worth noting" / "It bears mentioning"
- Reflexive both-sides presentation
- "Let me break this down"
- Parenthetical qualification overuse
- The word "epistemic" in any non-mathematical context (use in formal definitions only, never in prose explanations or the blog post)

### Academic Exception
The paper uses formal mathematical language. Terms like "indistinguishability," "composition," and "adversary" are domain-standard and not AI tells. The blog post is held to STRICT filter level. The paper is held to MODERATE — banned words apply, but technical structure and formalism are expected.

---

## Infrastructure

### Stack
- **Language:** Python 3.11+
- **Web framework:** FastAPI + Uvicorn
- **Evaluation:** NumPy, SciPy, scikit-learn, Matplotlib
- **Testing:** pytest
- **No cloud infrastructure.** The PoC runs locally. No Cloudflare, no D1, no R2 for this repo.

### Local Development
```bash
# Setup
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
pip install -r poc/requirements.txt

# Run proxy (use port 8100 for eval scripts)
cd poc
uvicorn src.proxy:app --host 127.0.0.1 --port 8100

# Run tests
pytest poc/tests/ -v

# Run a single test file
pytest poc/tests/test_executor.py -v

# Run Level 1 evaluations (proxy must be running on 8100)
python -m eval.divergence_test
python -m eval.classifier_attack
python -m eval.budget_depletion

# Run Level 2/3 evaluations (experiments 4-7)
python -m eval.syscall_trace            # no proxy needed
python -m eval.timing_autocorrelation   # no proxy needed
python -m eval.burst_injection          # proxy required
python -m eval.wire_capture             # proxy required; tshark needs cap_net_raw

# Sub-tests 2+3 of wire_capture require:
#   sudo setcap cap_net_raw+eip $(which tcpdump)
#   sudo setcap cap_net_raw+eip $(which tshark)
```

---

## Current Phase

### Phase 1: Repository Setup & Paper Finalization (Complete)

**Author:** Adam Bishop, XOps360 LLC

- [x] Create local repo
- [x] Create GitHub repo: cerberusxops360/indeterminate-emergence (public)
- [x] Commit directory structure, CLAUDE.md, licenses
- [x] Commit paper (markdown)
- [x] Commit blog post
- [x] Commit project plan and PoC specification to docs/
- [x] Convert paper to LaTeX
- [x] Generate PDF
- [ ] Run paper through writing standards audit (banned words, em dashes, patterns)
- [ ] Run blog post through writing standards audit
- [ ] Tag: v0.1-paper

### Phase 2: IACR ePrint Submission (Complete)

- [x] Create IACR ePrint account at https://eprint.iacr.org/
- [x] Convert paper to LaTeX
- [x] Generate PDF from LaTeX
- [x] Submit PDF to IACR ePrint (categorize under "foundations" or "applications")
- [x] Update README with ePrint link and BibTeX
- [x] Published: https://eprint.iacr.org/2026/108326

### Phase 2B: arXiv Submission (Deferred)

arXiv submission deferred until IACR ePrint publication establishes a portfolio for endorsement.

- [ ] Request endorsement for cs.CR (cite ePrint publication)
- [ ] Submit LaTeX + PDF to arXiv
- [ ] Cross-list to cs.AI
- [ ] Update README with arXiv link

### Phase 3: PoC Build (Complete)

- [x] Scaffold: proxy.py returning constant responses
- [x] config.py: session capability tokens
- [x] executor.py: normal + dummy execution paths
- [x] channel_shaper.py: fixed-size + fixed-timing responses
- [x] accountant.py: budget tracking + absorption trigger
- [x] Integration: full request-response flow
- [ ] Tests: all modules passing

### Phase 4: Evaluation (Level 1 complete; Level 2/3 complete)

- [x] Experiment 1: divergence test — PASS
- [x] Experiment 2: classifier attack — PASS (≤52% accuracy)
- [x] Experiment 3: budget depletion — PASS
- [x] Experiment 4: syscall trace comparison — PASS (paths indistinguishable)
- [x] Experiment 5: timing autocorrelation — PASS (KS p=0.226, n=2000)
- [x] Experiment 6: burst injection — PASS (H4 starvation not observed)
- [x] Experiment 7: wire capture — PASS (body size, packet dist, inter-segment timing)
- [x] Overshoot bug fixed in channel_shaper.py (KS p=0.401 post-fix)
- [x] Empirical findings documented: docs/EMPIRICAL_FINDINGS.md
- [x] KI-001 (TCP fragmentation timing) closed
- [ ] Tag: v0.2-poc

### Phase 5: Publication

- [ ] Blog post published (link TBD)
- [ ] Distribution: HN, Reddit, LessWrong, Twitter
- [ ] Tag: v1.0-published

---

## What NOT to Do

- Do not use the word "epistemic" in the blog post, README, or any prose explanation. Reserve it for formal mathematical definitions in the paper only.
- Do not use banned words from the writing standards in any file that leaves this repo (paper, blog, README).
- Do not create cloud infrastructure. This is a local-only project.
- Do not add real API integrations to the PoC tools. All tools are simulated.
- Do not expose the privacy accountant's internal state in HTTP responses. Ever.
- Do not return HTTP status codes other than 200 from the proxy. The whole point is uniform responses.
- Do not use floating dependency versions. Pin everything.
- Do not skip manifest entries for new files. Every file gets a fingerprint.
- Do not commit evaluation results without a corresponding entry in CHANGELOG.md.
- Do not modify the paper without updating the fingerprint in the manifest.

---

## Reference

- **PoC Specification:** `docs/POC_SPECIFICATION.md` (the TDP for the code)
- **Project Plan:** `docs/PROJECT_PLAN.md` (timeline and publishing strategy)
- **Full Paper:** `paper/indeterminate-emergence-v1.md`
- **Empirical Findings:** `docs/EMPIRICAL_FINDINGS.md` (canon: Level 2/3 assessment results)
- **ADAM System Spec:** see `cerberusxops360/adam-system` for fingerprint format and manifest conventions
- **XOps360 Writing Standards:** see Gap Analysis v5 Section 7.1 for filter rules

---

## Document Control

| Version | Date       | Author | Changes              |
|---------|------------|--------|----------------------|
| 1.0.0   | 2026-03-13 | Adam   | Initial CLAUDE.md    |
| 1.1.0   | 2026-04-13 | Adam   | Phase 3/4 complete; Level 2/3 eval; overshoot fix; KI-001 closed |
