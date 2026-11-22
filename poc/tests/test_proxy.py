import json
import time

import pytest
from httpx import ASGITransport, AsyncClient

import src.proxy as proxy_module
from src.proxy import app, session_store, accountants, absorption_listeners
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


class TestRedTeamFixes:
    """Regression tests for the red team findings of 2026-11-21."""

    @staticmethod
    def _is_shaped(resp):
        body = resp.json()
        return (resp.status_code == 200 and len(resp.content) == 4096
                and set(body) == {"status", "receipt", "payload", "padding"})

    @pytest.mark.asyncio
    async def test_malformed_inputs_get_the_shaped_response(self, setup_sessions):
        bodies = [b"[1,2,3]", b"42", b'"with_search"', b"{bad json", b"",
                  b'{"tool":"web_search","params":{},"session_id":{"id":"with_search"}}',
                  b'{"tool":"web_search","params":{},"session_id":["with_search"]}',
                  b'{"tool":["web_search"],"params":"x","session_id":"with_search"}',
                  b'{"tool":null,"params":null,"session_id":null}']
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for raw in bodies:
                resp = await client.post("/action", content=raw, headers={"Content-Type": "application/json"})
                assert self._is_shaped(resp), raw

    @pytest.mark.asyncio
    async def test_wrong_paths_and_methods_get_the_shaped_response(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for method, path in [("GET", "/action"), ("PUT", "/action"), ("DELETE", "/action"), ("POST", "/action/"),
                                 ("POST", "/actions"), ("GET", "/"), ("GET", "/openapi.json"), ("GET", "/docs"), ("GET", "/redoc")]:
                resp = await client.request(method, path)
                assert self._is_shaped(resp), (method, path)

    @pytest.mark.asyncio
    async def test_schema_is_not_served(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/openapi.json")
            assert "openapi" not in resp.json() and "paths" not in resp.json()

    @pytest.mark.asyncio
    async def test_malformed_input_takes_as_long_as_a_normal_request(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for kwargs in ({"content": b"[1,2,3]"}, {"content": b'{"session_id":{"x":1}}'}):
                t0 = time.monotonic()
                await client.post("/action", headers={"Content-Type": "application/json"}, **kwargs)
                assert 0.24 <= time.monotonic() - t0 <= 0.6
            t0 = time.monotonic()
            await client.get("/nope")
            assert 0.24 <= time.monotonic() - t0 <= 0.6

    @pytest.mark.asyncio
    async def test_slow_body_does_not_switch_off_the_timing_shaper(self, setup_sessions):
        """Before the fix the clock started before the body was read: a body sent 0.5 s late came back
        after 0.5 s plus raw executor time (at most about 0.65 s). The shaped floor is 0.25 s after the read."""
        import asyncio
        delay = 0.5

        async def slow():
            await asyncio.sleep(delay)
            yield json.dumps({"tool": "web_search", "params": {}, "session_id": "with_search"}).encode()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(5):
                t0 = time.monotonic()
                resp = await client.post("/action", content=slow(), headers={"Content-Type": "application/json"})
                elapsed = time.monotonic() - t0
                assert self._is_shaped(resp)
                assert elapsed >= delay + 0.24, elapsed

    @pytest.mark.asyncio
    async def test_non_string_session_id_does_not_charge_any_budget(self, setup_sessions):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post("/action", json={"tool": "web_search", "params": {}, "session_id": ["with_search"]})
        assert accountants == {}


class TestOwnerToken:
    """KI-005: the budget is charged to the observer, and only the owner can cause real work."""

    @pytest.fixture
    def owned(self, monkeypatch):
        session_store.register(SessionConfig(session_id="owned", authorized_tools=["web_search"], budget=50.0,
                                             per_query_epsilon=1.0, absorption_margin=5.0, owner_token="s3cret-owner-token"))
        calls = []
        real_execute = proxy_module.execute

        async def spy(tool_name, params, authorized, absorbing):
            calls.append((tool_name, authorized, absorbing))
            return await real_execute(tool_name=tool_name, params=params, authorized=authorized, absorbing=absorbing)

        monkeypatch.setattr(proxy_module, "execute", spy)
        events = []
        absorption_listeners.append(lambda sid, caller: events.append((sid, caller)))
        yield calls, events
        absorption_listeners.clear()

    @staticmethod
    async def _post(client, **body):
        return await client.post("/action", json=body)

    @pytest.mark.asyncio
    async def test_anonymous_drain_cannot_switch_the_owner_off(self, owned):
        calls, events = owned
        import asyncio
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await asyncio.gather(*[self._post(client, tool="not_a_real_tool", params={}, session_id="owned") for _ in range(30)])
            await asyncio.gather(*[self._post(client, tool="web_search", params={}, session_id="owned", caller_token="wrong") for _ in range(30)])
            assert "owned" not in accountants                               # the owner's budget was never touched
            assert accountants["owned\x00anon"].absorbing                    # the prober's budget is spent
            assert all(authorized is False for _, authorized, _ in calls)   # no anonymous call caused real work
            assert events == [("owned", "anon")]                            # the owner was told, once
            calls.clear()
            resp = await self._post(client, tool="web_search", params={}, session_id="owned", caller_token="s3cret-owner-token")
            assert calls == [("web_search", True, False)]                   # the owner still gets real work
            assert accountants["owned"].query_count == 1 and resp.status_code == 200

    @pytest.mark.asyncio
    async def test_owner_anonymous_and_wrong_token_responses_look_the_same(self, owned):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            a = await self._post(client, tool="web_search", params={}, session_id="owned", caller_token="s3cret-owner-token")
            b = await self._post(client, tool="web_search", params={}, session_id="owned")
            c = await self._post(client, tool="web_search", params={}, session_id="owned", caller_token="wrong")
            d = await self._post(client, tool="web_search", params={}, session_id="owned", caller_token=["s3cret-owner-token"])
            assert a.status_code == b.status_code == c.status_code == d.status_code == 200
            assert a.content == b.content == c.content == d.content and len(a.content) == 4096
            assert dict(a.headers) == dict(b.headers) == dict(c.headers) == dict(d.headers)

    @pytest.mark.asyncio
    async def test_owner_is_told_when_own_budget_runs_out(self, owned):
        calls, events = owned
        import asyncio
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await asyncio.gather(*[self._post(client, tool="web_search", params={}, session_id="owned", caller_token="s3cret-owner-token") for _ in range(55)])
        assert events == [("owned", "owner")]
        assert calls[-1] == ("web_search", True, True)

    @pytest.mark.asyncio
    async def test_session_without_owner_token_behaves_as_before(self, monkeypatch):
        session_store.register(SessionConfig(session_id="legacy", authorized_tools=["web_search"]))
        calls = []

        async def spy(tool_name, params, authorized, absorbing):
            calls.append((authorized, absorbing))
            return "{}"

        monkeypatch.setattr(proxy_module, "execute", spy)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await self._post(client, tool="web_search", params={}, session_id="legacy")
            await self._post(client, tool="web_search", params={}, session_id="legacy", caller_token="anything")
        assert calls == [(True, False), (True, False)] and accountants["legacy"].query_count == 2
