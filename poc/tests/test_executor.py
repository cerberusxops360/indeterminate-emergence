import asyncio
import json
import time

import pytest

from src.executor import simulate_tool, dummy_computation, execute
from src.config import ALL_TOOLS


class TestSimulateTool:
    @pytest.mark.asyncio
    async def test_returns_valid_json_for_all_tools(self):
        for tool in ALL_TOOLS:
            result = await simulate_tool(tool, {"query": "test"})
            parsed = json.loads(result)
            assert isinstance(parsed, dict)

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_null_result(self):
        result = await simulate_tool("nonexistent", {})
        parsed = json.loads(result)
        assert parsed["result"] is None

    @pytest.mark.asyncio
    async def test_web_search_includes_results(self):
        result = await simulate_tool("web_search", {"query": "hello"})
        parsed = json.loads(result)
        assert "results" in parsed

    @pytest.mark.asyncio
    async def test_latency_within_bounds(self):
        start = time.monotonic()
        await simulate_tool("calculator", {"expr": "1+1"})
        elapsed = time.monotonic() - start
        assert 0.04 <= elapsed <= 0.5  # generous bounds for CI


class TestDummyComputation:
    @pytest.mark.asyncio
    async def test_returns_valid_json(self):
        result = await dummy_computation()
        parsed = json.loads(result)
        assert parsed["result"] is None

    @pytest.mark.asyncio
    async def test_latency_within_bounds(self):
        start = time.monotonic()
        await dummy_computation()
        elapsed = time.monotonic() - start
        assert 0.04 <= elapsed <= 0.5


class TestExecute:
    @pytest.mark.asyncio
    async def test_authorized_normal_returns_tool_output(self):
        result = await execute("web_search", {"query": "test"}, authorized=True, absorbing=False)
        parsed = json.loads(result)
        assert "results" in parsed

    @pytest.mark.asyncio
    async def test_unauthorized_returns_null(self):
        result = await execute("web_search", {"query": "test"}, authorized=False, absorbing=False)
        parsed = json.loads(result)
        assert parsed["result"] is None

    @pytest.mark.asyncio
    async def test_absorbing_returns_null(self):
        result = await execute("web_search", {"query": "test"}, authorized=True, absorbing=True)
        parsed = json.loads(result)
        assert parsed["result"] is None

    @pytest.mark.asyncio
    async def test_unauthorized_and_absorbing_returns_null(self):
        result = await execute("web_search", {}, authorized=False, absorbing=True)
        parsed = json.loads(result)
        assert parsed["result"] is None

    @pytest.mark.asyncio
    async def test_all_paths_return_string(self):
        for auth, absorb in [(True, False), (False, False), (True, True), (False, True)]:
            result = await execute("calculator", {}, authorized=auth, absorbing=absorb)
            assert isinstance(result, str)
