# Indeterminate Emergence -- Publication & Launch Project Plan

---

## Overview

This plan covers everything needed to take the paper from its current revised draft to public availability across three channels: IACR ePrint (academic discoverability), GitHub (open research + future PoC code), and a blog (accessible reach). Each channel serves a different audience; together they establish timestamp priority, invite collaboration, and make the work findable.

---

## Phase 0: Pre-Launch Prep (Days 1-3)

### 0.1 Final Paper Review

- [ ] Read the revised paper end-to-end for coherence after all structural changes
- [ ] Verify all 11 numbered references match their inline citations
- [ ] Check all mathematical notation renders correctly in target formats
- [ ] Confirm the worked example (Section 7) is self-contained and readable without prior sections
- [ ] Have one trusted reader (ideally someone in security or DP) do a cold read and flag confusion points
- [ ] Author: Adam Bishop, XOps360 LLC

### 0.2 Choose a License

- [x] **CC BY 4.0** for paper content
- [x] **MIT License** for code
- [x] Add license text to all deliverables

### 0.3 Publication Identity

- [x] Publish under real name: Adam Bishop
- [x] ORCID registered: https://orcid.org/0009-0000-4569-3726
- [x] GitHub organization: cerberusxops360

---

## Phase 1: GitHub Repository (Days 2-4)

### 1.1 Repository Setup

- [x] Create repository: `indeterminate-emergence`
- [x] Set visibility: **Public**
- [x] Add description: "Security through non-existence. Capabilities materialize only inside protected execution boundaries. Theory + proof of concept."
- [x] Add topics/tags: `security`, `differential-privacy`, `ai-safety`, `ai-governance`, `pufferfish-privacy`, `inference-resistance`, `deniable-encryption`

### 1.2 Repository Structure

```
indeterminate-emergence/
├── CLAUDE.md
├── README.md
├── LICENSE-CODE
├── LICENSE-PAPER
├── KNOWN_ISSUES.md
├── CHANGELOG.md
├── .gitignore
├── paper/
│   ├── indeterminate-emergence-v1.md
│   ├── indeterminate-emergence-v1.tex
│   ├── indeterminate-emergence-v1.pdf
│   └── figures/
├── blog/
│   └── what-if-security-meant-non-existence.md
├── poc/
│   ├── README.md
│   ├── requirements.txt
│   ├── src/
│   │   ├── __init__.py
│   │   ├── proxy.py
│   │   ├── executor.py
│   │   ├── channel_shaper.py
│   │   ├── accountant.py
│   │   └── config.py
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── divergence_test.py
│   │   ├── classifier_attack.py
│   │   └── budget_depletion.py
│   ├── results/
│   └── tests/
│       ├── __init__.py
│       ├── test_proxy.py
│       ├── test_executor.py
│       ├── test_channel_shaper.py
│       └── test_accountant.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── THREAT_MODEL.md
│   ├── POC_SPECIFICATION.md
│   ├── PROJECT_PLAN.md
│   └── CONTRIBUTING.md
├── manifest/
│   ├── index.yaml
│   └── objects/
└── .github/
    └── ISSUE_TEMPLATE/
        ├── bug_report.md
        └── research_question.md
```

### 1.3 Initial Commit Plan

- [x] Commit 1: Repository skeleton (README, LICENSE, directory structure, .gitignore, CLAUDE.md)
- [x] Commit 2: Paper (markdown, writing standards applied)
- [x] Commit 3: Blog post (writing standards applied)
- [x] Commit 4: Project plan and PoC specification
- [x] Commit 5: ADAM manifest with SHA-256 fingerprints
- [x] Tag: `v0.1-paper`

---

## Phase 2A: IACR ePrint Submission (Days 3-5)

IACR ePrint is the primary publication target. No endorsement required,
respected in the cryptography and security community, and establishes
a publication portfolio for future arXiv endorsement.

- [ ] Create IACR ePrint account at https://eprint.iacr.org/
- [ ] Prepare submission: PDF only (no LaTeX source required)
- [ ] Categorize under "foundations" or "applications"
- [ ] Author: Adam Bishop, XOps360 LLC
- [ ] ORCID: https://orcid.org/0009-0000-4569-3726
- [ ] Submit
- [ ] Once published: update GitHub README with ePrint link and BibTeX

---

## Phase 2B: arXiv Submission (Deferred)

arXiv submission deferred until IACR ePrint publication establishes a portfolio. The ePrint record will strengthen the endorsement request.

### LaTeX Conversion

- [ ] Convert the revised markdown paper to LaTeX
  - Use a standard template: `article` class, 11pt, single-column for a preprint
- [ ] Verify all math renders correctly in LaTeX
- [ ] Verify the ASCII architecture diagram in Appendix B renders acceptably (or convert to a TikZ figure)
- [ ] Generate a clean PDF and proof it

### arXiv Account & Endorsement

- [ ] Create an arXiv account at https://arxiv.org/user/register if you don't have one
- [ ] Request endorsement for cs.CR (cite IACR ePrint publication as portfolio evidence)
  - Target categories: **cs.CR** (Cryptography and Security) as primary, **cs.AI** (Artificial Intelligence) as secondary
  - Endorsement is a lightweight check that the paper is appropriate for the category, not peer review

### Submission

- [ ] Prepare submission package: `.tex` source + `.bbl` bibliography + figures
- [ ] Write arXiv abstract (can match paper abstract, 1920 character limit)
- [ ] Select categories: primary cs.CR, cross-list cs.AI
- [ ] Submit and wait for processing (typically 1-2 business days)
- [ ] Once live: update GitHub README with arXiv link and BibTeX

---

## Phase 3: Blog Post & Site (Days 4-7)

### 3.1 Platform Selection

**Option A: Substack (Fastest)**
- Pros: Zero setup, built-in audience discovery, email subscription, free tier sufficient
- Cons: Less control, platform dependency
- Setup time: 30 minutes

**Option B: Personal site with static generator (Most control)**
- Pros: Full control, custom domain, professional appearance, can host paper PDF directly
- Options: Hugo, Jekyll, Astro, or plain HTML on GitHub Pages
- Setup time: 2-4 hours with a template
- Recommended if you plan to publish more research

**Option C: Medium (Widest reach)**
- Pros: Large existing audience, good SEO, free
- Cons: Paywall friction for readers, less ownership
- Setup time: 30 minutes

**Recommendation:** Start with **Substack** for speed, or **GitHub Pages + Hugo** if you want a permanent research home. Either way, the blog post content is the same.

### 3.2 Blog Post Publishing Checklist

- [ ] Fill in link placeholders with IACR ePrint / GitHub URLs
- [ ] Add a header image or simple diagram (the architecture diagram from the paper works)
- [ ] Preview on mobile
- [ ] Publish

### 3.3 Distribution

After publishing, share to relevant communities:

- [ ] **Hacker News** with title "What if security meant things don't exist?"
- [ ] **Reddit** in r/netsec, r/crypto, r/MachineLearning, r/aisafety
- [ ] **Twitter/X** thread summarizing the three core ideas
- [ ] **Mastodon** with tags #infosec #aisafety #differentialprivacy
- [ ] **LessWrong / Alignment Forum** for the AI governance audience
- [ ] **LinkedIn** shorter professional summary
- [ ] **Security mailing lists** if applicable

### 3.4 Timing

Publish the blog post **after** the IACR ePrint submission is live. This ensures the timestamped academic version exists before the popular version circulates. The sequence:

1. GitHub repo goes live with paper
2. IACR ePrint submission goes live
3. Update GitHub with ePrint link
4. Publish blog post with all links
5. Distribute to communities

---

## Phase 4: Proof of Concept (Days 7-21)

See the separate **Proof of Concept Specification** document for full details.

Summary:
- Build the AI capability-set inference resistance proxy
- Run three evaluation experiments (divergence, classifier, budget depletion)
- Write up results
- Commit to GitHub under `poc/`
- Optionally: update blog with a follow-up post ("I built the thing")

---

## Phase 5: Follow-Up (Ongoing)

### 5.1 Community Engagement

- [ ] Respond to comments and critiques on all platforms
- [ ] Track citations and forks on GitHub
- [ ] File issues on your own repo for known limitations and future work ideas

### 5.2 Potential Venue Submissions

Once the PoC is complete with empirical results, consider submitting to:

| Venue | Type | Deadline Cycle | Fit |
|---|---|---|---|
| IEEE S&P (Oakland) | Top security conference | ~June annually | Strong if formal results are tight |
| USENIX Security | Top security conference | ~Feb, June, Oct (rolling) | Good for systems + theory |
| CSF (IEEE) | Formal methods in security | ~Feb annually | Best fit for the Pufferfish formalism |
| AAAI / NeurIPS Workshop | AI safety workshops | Varies | Good for AI governance angle |
| SaTML | Security and ML | ~Oct annually | Perfect intersection |
| FAccT | Fairness, Accountability, Transparency | ~Jan annually | If framed around governance |

### 5.3 Versioning

- Tag paper versions in Git: `v0.1-paper`, `v0.2-poc`, `v1.0-camera-ready`
- Keep a CHANGELOG.md tracking revisions
- If substantial revisions happen after community feedback, update ePrint/arXiv

---

## Timeline Summary

| Day | Milestone |
|---|---|
| 1-2 | Final paper review, license decision, ORCID registration |
| 2-4 | GitHub repo live with paper and blog post files |
| 3-5 | IACR ePrint submission |
| 5-7 | Blog post published, initial distribution |
| 7-14 | PoC build (proxy service, channel shaper, accountant) |
| 14-21 | PoC evaluation (divergence, classifier, budget depletion) |
| 21-25 | Results writeup, PoC committed to GitHub, follow-up blog post |
| 25+ | Community engagement, venue submissions, arXiv submission, iterate |

---

## Risk Mitigation

| Risk | Mitigation |
|---|---|
| Negative reception / "this is just DP" critique | The blog post and paper both explicitly position against DP; the novelty is extending deniability to effects, not reinventing DP |
| Someone publishes similar work first | GitHub timestamp + ePrint timestamp establish priority; the framework is distinctive enough that overlap is unlikely to be total |
| PoC takes longer than expected | Paper and blog stand alone without PoC; PoC is a strengthening addition, not a dependency |
| Scope creep on PoC | The spec document defines a minimal PoC; resist adding features before the three core experiments are done |

---
