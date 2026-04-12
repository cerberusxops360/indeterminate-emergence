import json
import time

import pytest
from httpx import ASGITransport, AsyncClient

from src.proxy import app, session_store, accountants
from src.config import SessionConfig


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state between tests."""
    session_store._sessions.clear()
    accountants.clear()
    yield
    session_store._sessions.clear()
    accountants.clear()


@pytest.fixture
def setup_sessions():
    """Register test sessions: one with web_search authorized, one without."""
    cfg_a = SessionConfig(
        session_id="with_search",
        authorized_tools=["web_search", "calculator"],
        budget=50.0,
        per_query_epsilon=1.0,
        absorption_margin=5.0,
    )
    cfg_b = SessionConfig(
        session_id="without_search",
        authorized_tools=["calculator"],
        budget=50.0,
        per_query_epsilon=1.0,
        absorption_margin=5.0,
    )
    session_store.register(cfg_a)
    session_store.register(cfg_b)


class TestProxyEndpoint:
    @pytest.mark.asyncio
    async def test_always_returns_200(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action", json={
                "tool": "web_search",
                "params": {"query": "test"},
                "session_id": "with_search",
            })
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthorized_tool_still_200(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action", json={
                "tool": "web_search",
                "params": {},
                "session_id": "without_search",
            })
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_session_still_200(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action", json={
                "tool": "web_search",
                "params": {},
                "session_id": "nonexistent",
            })
            assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_response_body_exactly_4096_bytes(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action", json={
                "tool": "web_search",
                "params": {"query": "test"},
                "session_id": "with_search",
            })
            assert len(resp.content) == 4096

    @pytest.mark.asyncio
    async def test_response_structure(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action", json={
                "tool": "calculator",
                "params": {},
                "session_id": "with_search",
            })
            body = resp.json()
            assert body["status"] == "processed"
            assert body["receipt"] == "ack"
            assert "payload" in body
            assert "padding" in body

    @pytest.mark.asyncio
    async def test_authorized_and_unauthorized_same_size(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp_auth = await client.post("/action", json={
                "tool": "web_search",
                "params": {"query": "test"},
                "session_id": "with_search",
            })
            resp_unauth = await client.post("/action", json={
                "tool": "web_search",
                "params": {"query": "test"},
                "session_id": "without_search",
            })
            assert len(resp_auth.content) == len(resp_unauth.content)

    @pytest.mark.asyncio
    async def test_malformed_request_still_200(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action", json={"garbage": True})
            assert resp.status_code == 200
            assert len(resp.content) == 4096

    @pytest.mark.asyncio
    async def test_accountant_not_exposed_in_response(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/action", json={
                "tool": "web_search",
                "params": {},
                "session_id": "with_search",
            })
            body = resp.json()
            assert "budget" not in body
            assert "spent" not in body
            assert "absorbing" not in body
            assert "threshold" not in body
            assert "query_count" not in body


class TestAbsorption:
    @pytest.mark.asyncio
    async def test_absorption_triggers_after_budget(self):
        """Session with tiny budget should enter absorption quickly."""
        cfg = SessionConfig(
            session_id="tiny_budget",
            authorized_tools=["web_search"],
            budget=3.0,
            per_query_epsilon=1.0,
            absorption_margin=0.0,
        )
        session_store.register(cfg)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Send enough queries to exhaust budget
            for _ in range(5):
                resp = await client.post("/action", json={
                    "tool": "web_search",
                    "params": {},
                    "session_id": "tiny_budget",
                })
                assert resp.status_code == 200
                assert len(resp.content) == 4096

        # Verify accountant is in absorption state
        assert "tiny_budget" in accountants
        assert accountants["tiny_budget"].absorbing is True
