import pytest
from src.config import (
    ALL_TOOLS,
    DEFAULT_BUDGET,
    DEFAULT_PER_QUERY_EPSILON,
    DEFAULT_ABSORPTION_MARGIN,
    SessionConfig,
    SessionStore,
    check_policy,
)


class TestSessionConfig:
    def test_default_session_has_no_tools(self):
        cfg = SessionConfig(session_id="s1", authorized_tools=[])
        assert cfg.authorized_tools == []

    def test_session_stores_budget_params(self):
        cfg = SessionConfig(
            session_id="s1",
            authorized_tools=["web_search"],
            budget=100.0,
            per_query_epsilon=2.0,
            absorption_margin=10.0,
        )
        assert cfg.budget == 100.0
        assert cfg.per_query_epsilon == 2.0
        assert cfg.absorption_margin == 10.0

    def test_session_uses_defaults(self):
        cfg = SessionConfig(session_id="s1", authorized_tools=["calculator"])
        assert cfg.budget == DEFAULT_BUDGET
        assert cfg.per_query_epsilon == DEFAULT_PER_QUERY_EPSILON
        assert cfg.absorption_margin == DEFAULT_ABSORPTION_MARGIN


class TestSessionStore:
    def test_get_returns_none_for_unknown(self):
        store = SessionStore()
        assert store.get("nonexistent") is None

    def test_register_and_get(self):
        store = SessionStore()
        cfg = SessionConfig(session_id="s1", authorized_tools=["web_search"])
        store.register(cfg)
        assert store.get("s1") is cfg

    def test_register_overwrites(self):
        store = SessionStore()
        cfg1 = SessionConfig(session_id="s1", authorized_tools=["web_search"])
        cfg2 = SessionConfig(session_id="s1", authorized_tools=["calculator"])
        store.register(cfg1)
        store.register(cfg2)
        assert store.get("s1").authorized_tools == ["calculator"]


class TestCheckPolicy:
    def test_authorized_tool(self):
        cfg = SessionConfig(session_id="s1", authorized_tools=["web_search", "calculator"])
        result = check_policy(cfg, "web_search")
        assert result["authorized"] is True
        assert result["reason"] == "ok"

    def test_unauthorized_tool(self):
        cfg = SessionConfig(session_id="s1", authorized_tools=["web_search"])
        result = check_policy(cfg, "calculator")
        assert result["authorized"] is False
        assert result["reason"] == "not_authorized"

    def test_unknown_tool(self):
        cfg = SessionConfig(session_id="s1", authorized_tools=["web_search"])
        result = check_policy(cfg, "totally_fake_tool")
        assert result["authorized"] is False
        assert result["reason"] == "unknown_tool"

    def test_no_session_returns_not_authorized(self):
        result = check_policy(None, "web_search")
        assert result["authorized"] is False
        assert result["reason"] == "no_session"

    def test_all_tools_are_known(self):
        cfg = SessionConfig(session_id="s1", authorized_tools=ALL_TOOLS.copy())
        for tool in ALL_TOOLS:
            result = check_policy(cfg, tool)
            assert result["authorized"] is True

    def test_return_structure_is_consistent(self):
        """Policy result always has the same keys regardless of outcome."""
        cfg = SessionConfig(session_id="s1", authorized_tools=["web_search"])
        for tool in ["web_search", "calculator", "unknown_xyz"]:
            result = check_policy(cfg, tool)
            assert set(result.keys()) == {"authorized", "reason"}


class TestAllTools:
    def test_five_tools_defined(self):
        assert len(ALL_TOOLS) == 5

    def test_expected_tools(self):
        expected = {"web_search", "calculator", "file_read", "code_exec", "database_query"}
        assert set(ALL_TOOLS) == expected
