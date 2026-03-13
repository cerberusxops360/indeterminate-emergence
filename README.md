# Indeterminate Emergence: Security Through Non-Existence

**Author:** Adam Bishop, XOps360 LLC
[![ORCID](https://img.shields.io/badge/ORCID-0009--0000--4569--3726-green)](https://orcid.org/0009-0000-4569-3726)

A security framework where meaning, capability, and effect do not exist outside
authorized contexts. Unauthorized observers cannot distinguish between three
possibilities: nothing is there, something is undefined, or it is noise.

## What Is This

Traditional security hides information behind encryption. This framework takes a
different approach: meaningful information and system effects only materialize
inside protected execution boundaries. Outside those boundaries, there is
nothing to find, intercept, or decrypt.

The framework uses Pufferfish-style privacy definitions and differential privacy
composition to provide formal guarantees against capability inference attacks.

## Paper

The full paper is available in `paper/indeterminate-emergence-v1.md`. It defines
the formal security model, proves non-collapse guarantees, specifies four
adversary tiers, and works through a concrete application to AI capability-set
inference resistance.

## Proof of Concept

A planned demonstration of capability-set inference resistance for AI agent
systems. The proxy service will sit between an external observer and an AI
agent's tool registry, making it impossible to determine which tools the agent
has access to. See `docs/POC_SPECIFICATION.md` for the full build spec.

## Core Ideas

1. **Indeterminate emergence** -- capabilities only materialize inside a
   protected execution boundary. Outside that boundary, there is nothing to
   find.

2. **Absorptive execution** -- when the system detects probing, it keeps
   responding identically but silently stops producing real effects. From the
   outside, normal operation and absorption are indistinguishable.

3. **Leakage budget** -- every interaction leaks a bounded amount of
   information. A privacy accountant tracks cumulative leakage and triggers
   absorption automatically when the budget is spent. Composition theorems
   guarantee the bound holds against adaptive adversaries.

## Status

- [x] Theory paper (revised draft with full citations)
- [x] Blog post
- [ ] IACR ePrint submission
- [ ] Proof of concept
- [ ] Empirical evaluation

## Citation

BibTeX entry will be added after IACR ePrint publication.

## License

Paper: [CC BY 4.0](LICENSE-PAPER) | Code: [MIT](LICENSE-CODE)

## Contributing

This project is published as independent research for open discussion and
development. Critique, extension, and collaboration are welcome. See
[CONTRIBUTING.md](docs/CONTRIBUTING.md) for details.
