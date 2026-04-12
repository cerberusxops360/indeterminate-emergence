import pytest

from src.accountant import PrivacyAccountant


class TestPrivacyAccountant:
    def test_initial_state_not_absorbing(self):
        acct = PrivacyAccountant(budget=50.0, per_query_cost=1.0, margin=5.0)
        assert acct.absorbing is False
        assert acct.query_count == 0
        assert acct.spent == 0.0

    def test_single_query_not_absorbing(self):
        acct = PrivacyAccountant(budget=50.0, per_query_cost=1.0, margin=5.0)
        result = acct.record_query()
        assert result is False
        assert acct.query_count == 1
        assert acct.spent == 1.0

    def test_absorption_triggers_near_budget(self):
        acct = PrivacyAccountant(budget=10.0, per_query_cost=1.0, margin=0.0)
        # With margin=0, threshold = budget exactly (no randomization range)
        for _ in range(9):
            assert acct.record_query() is False
        # 10th query should trigger (spent=10 >= threshold=10)
        assert acct.record_query() is True

    def test_absorption_is_sticky(self):
        acct = PrivacyAccountant(budget=5.0, per_query_cost=5.0, margin=0.0)
        acct.record_query()  # spent=5, triggers absorption
        assert acct.absorbing is True
        # Subsequent queries stay absorbed
        assert acct.record_query() is True
        assert acct.record_query() is True

    def test_threshold_randomized_within_margin(self):
        """Threshold should be between budget-margin and budget."""
        seen_thresholds = set()
        for _ in range(100):
            acct = PrivacyAccountant(budget=50.0, per_query_cost=1.0, margin=5.0)
            seen_thresholds.add(acct.threshold)
            assert 45.0 <= acct.threshold <= 50.0
        # With 100 samples, should see variation
        assert len(seen_thresholds) > 1

    def test_get_state_returns_all_fields(self):
        acct = PrivacyAccountant(budget=50.0, per_query_cost=1.0, margin=5.0)
        acct.record_query()
        state = acct.get_state()
        assert state["query_count"] == 1
        assert state["spent"] == 1.0
        assert state["budget"] == 50.0
        assert "threshold" in state
        assert state["absorbing"] is False

    def test_zero_budget_absorbs_immediately(self):
        acct = PrivacyAccountant(budget=0.0, per_query_cost=1.0, margin=0.0)
        assert acct.record_query() is True

    def test_query_count_increments(self):
        acct = PrivacyAccountant(budget=100.0, per_query_cost=1.0, margin=0.0)
        for i in range(10):
            acct.record_query()
        assert acct.query_count == 10
        assert acct.spent == 10.0
