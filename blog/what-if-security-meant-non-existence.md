# What If Security Meant Things Don't Exist?

## A new security primitive for the age of AI agents

---

Every lock tells you there's something worth locking.

That sentence is the starting point for a paper I've been working on about **indeterminate emergence**, and it captures something that's been bothering me about how we build secure systems, especially now that AI agents are acting autonomously in the real world.

Traditional security works by scrambling. You take a secret, encrypt it, and hope nobody cracks the code. That's fine for protecting files. But it has a fundamental problem: the *existence* of the ciphertext announces that a secret exists. A locked door tells you there's a room worth entering.

Modern AI systems have an even worse version of this problem. They don't just store secrets. They *do things*. And every time a system does something (or refuses to do something), it leaks information about what it's capable of.

---

### The refusal problem

Ask an AI agent to access a database and it says "access denied." What did you just learn? That the database exists, that the agent *could* access it in principle, and that some policy prevented it this time. The denial itself is an oracle, a machine that answers questions you didn't even need to ask directly.

This is the core insight: **in systems that act, silence is informative, refusal is informative, and even the absence of a response is informative.** The adversary doesn't need to break encryption. They just need to watch behavior and make inferences.

---

### So what's the alternative?

The paper proposes a different starting point. Instead of asking "how do we hide this secret?", it asks:

> If we threw away every existing definition of encryption but kept the *intent*, what should a secure system actually look like?

The answer is what I'm calling **indeterminate emergence**: a system where meaningful information, capabilities, and effects *don't exist* outside the exact moment and context where they're authorized.

Not hidden. Not encrypted. Genuinely non-existent.

An unauthorized observer can't distinguish between three possibilities:
1. Nothing is there.
2. Something is there but undefined.
3. It's just noise.

That's stronger than encryption. Encryption says "you can't read this." Indeterminate emergence says "there's nothing to read, and you can't even tell whether that's true."

---

### Three core ideas

**1. Don't hide meaning. Make it not exist.**

Design systems where capabilities only materialize inside a protected execution boundary. Outside that boundary, there's nothing to find. Not encrypted nothing. Actual nothing.

**2. When threatened, absorb. Don't refuse.**

If the system detects probing, it doesn't shut down or throw errors. It keeps responding exactly the same way, but quietly stops doing anything real. From the outside, the system looks identical whether it's working normally or has gone completely inert.

I call this *absorptive execution*. It's the security equivalent of a poker player whose cards don't have numbers on them until they're played.

**3. Put a budget on what attackers can learn.**

Every interaction leaks a tiny amount of information. The system tracks this like a spending account, a leakage budget. When the budget runs out, absorption kicks in automatically. The math (borrowing from differential privacy) guarantees that no matter how clever the attacker is, they can't learn more than the budget allows.

---

### Why now?

This matters because AI agents are proliferating, and they act in the world. An AI agent with access to your company's tools, APIs, and databases is a walking capability profile. If an adversary can figure out what the agent can do, they can craft attacks that exploit those specific capabilities.

Current security approaches protect the data. This framework protects the *capability set itself*. An observer watching the agent can't determine which tools it has access to, even by actively experimenting.

---

### How realistic is this?

More realistic than it sounds. The paper formalizes everything, but the engineering boils down to:

- **Fixed-format responses** where every reply from the system looks identical regardless of what happened internally
- **Timing padding** so response latency is drawn from a fixed distribution, hiding whether real computation occurred
- **A counter** that tracks the leakage budget and triggers absorption when it reaches a threshold

A minimal proof of concept, an AI agent proxy that resists capability inference, is buildable in roughly two weeks by a single developer. The hard part isn't any individual component; it's making them work together without springing leaks at the seams.

---

### What are the limits?

The paper is honest about what this can't do:

- **You can't hide effects from whoever receives them.** If the system writes to a database, and the adversary *is* the database, they know something happened. The framework protects every other observer, but not the endpoint.
- **The agent's downstream behavior can still leak information.** The framework protects the system's observation channel, but if the agent changes strategy based on which tools are available, that's visible. Protecting agent behavior is a separate (hard) problem.
- **The guarantees depend on correctly specifying what's sensitive.** If you define the wrong secrets, you get the wrong protection.

These aren't bugs in the theory. They're fundamental limits that should be acknowledged, not hidden.

---

### The formal version

The full paper, with Pufferfish-style privacy definitions, composition theorems, four adversary models, a worked example, and a complete reference list, is available on [GitHub](https://github.com/cerberusxops360/indeterminate-emergence).

I welcome critique, extension, and collaboration.

If you want the one-sentence version:

> **The strongest security signal is not silence, but the inability to determine whether silence is meaningful, accidental, or impossible.**

---

*Adam Bishop is the founder of XOps360 LLC, a service-disabled veteran-owned small business specializing in federal IT modernization. The full paper is available on [IACR ePrint](link TBD) and the code at [github.com/cerberusxops360/indeterminate-emergence](https://github.com/cerberusxops360/indeterminate-emergence).*
