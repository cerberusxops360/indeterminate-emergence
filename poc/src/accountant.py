import random


class PrivacyAccountant:
    """Track cumulative leakage per session and trigger absorption when budget is exhausted."""

    def __init__(self, budget: float, per_query_cost: float, margin: float) -> None:
        self.budget = budget
        self.per_query_cost = per_query_cost
        self.margin = margin
        self.spent = 0.0
        self.absorbing = False
        self.query_count = 0
        # Randomized threshold reduces meta-leakage from threshold-oracle attacks
        self.threshold = budget - random.uniform(0, margin)

    def record_query(self) -> bool:
        """Record a query and return current absorption state. Returns True if absorbing."""
        self.query_count += 1
        self.spent += self.per_query_cost

        if not self.absorbing and self.spent >= self.threshold:
            self.absorbing = True  # Sticky — stays absorbed for session lifetime

        return self.absorbing

    def get_state(self) -> dict:
        """For internal logging/evaluation only. Never exposed externally."""
        return {
            "query_count": self.query_count,
            "spent": self.spent,
            "budget": self.budget,
            "threshold": self.threshold,
            "absorbing": self.absorbing,
        }
