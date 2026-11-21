# Changelog

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
