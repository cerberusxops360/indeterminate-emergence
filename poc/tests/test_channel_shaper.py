import asyncio
import json
import time

import pytest

from src.channel_shaper import (
    RESPONSE_SIZE,
    MIN_LATENCY,
    MAX_LATENCY,
    pad_payload,
    shape_timing,
    shape_response,
)


class TestPadPayload:
    def test_output_is_exactly_response_size(self):
        result = pad_payload('{"result": 42}')
        serialized = json.dumps(result).encode("utf-8")
        assert len(serialized) == RESPONSE_SIZE

    def test_empty_input_is_exactly_response_size(self):
        result = pad_payload("")
        serialized = json.dumps(result).encode("utf-8")
        assert len(serialized) == RESPONSE_SIZE

    def test_null_result_is_exactly_response_size(self):
        result = pad_payload(json.dumps({"result": None}))
        serialized = json.dumps(result).encode("utf-8")
        assert len(serialized) == RESPONSE_SIZE

    def test_large_input_is_truncated_to_response_size(self):
        large = "x" * (RESPONSE_SIZE * 2)
        result = pad_payload(large)
        serialized = json.dumps(result).encode("utf-8")
        assert len(serialized) == RESPONSE_SIZE

    def test_response_has_required_fields(self):
        result = pad_payload("test")
        assert result["status"] == "processed"
        assert result["receipt"] == "ack"
        assert "payload" in result
        assert "padding" in result

    def test_various_payload_sizes_all_hit_target(self):
        for size in [0, 1, 10, 100, 500, 1000, 2000, 3000, 3500, 3900]:
            raw = "a" * size
            result = pad_payload(raw)
            serialized = json.dumps(result).encode("utf-8")
            assert len(serialized) == RESPONSE_SIZE, f"Failed for input size {size}"

    def test_unicode_payload_hits_target(self):
        raw = json.dumps({"emoji": "\U0001f600" * 50})
        result = pad_payload(raw)
        serialized = json.dumps(result).encode("utf-8")
        assert len(serialized) == RESPONSE_SIZE

    def test_authorized_and_unauthorized_same_structure(self):
        real = pad_payload(json.dumps({"results": ["Real data here"]}))
        dummy = pad_payload(json.dumps({"result": None}))
        assert set(real.keys()) == set(dummy.keys())
        assert real["status"] == dummy["status"]
        assert real["receipt"] == dummy["receipt"]


class TestShapeTiming:
    @pytest.mark.asyncio
    async def test_pads_short_execution(self):
        start = time.monotonic()
        await shape_timing(start)
        elapsed = time.monotonic() - start
        assert elapsed >= MIN_LATENCY - 0.01  # small tolerance

    @pytest.mark.asyncio
    async def test_does_not_exceed_max_significantly(self):
        start = time.monotonic()
        await shape_timing(start)
        elapsed = time.monotonic() - start
        assert elapsed <= MAX_LATENCY + 0.05  # tolerance for scheduling

    @pytest.mark.asyncio
    async def test_already_slow_execution_returns_immediately(self):
        """If execution already took longer than MAX_LATENCY, don't add more delay."""
        start = time.monotonic() - 1.0  # pretend 1s already elapsed
        before = time.monotonic()
        await shape_timing(start)
        additional_delay = time.monotonic() - before
        assert additional_delay < 0.05  # should return almost immediately


class TestShapeResponse:
    @pytest.mark.asyncio
    async def test_full_pipeline_size(self):
        start = time.monotonic()
        result = await shape_response('{"result": 42}', start)
        serialized = json.dumps(result).encode("utf-8")
        assert len(serialized) == RESPONSE_SIZE

    @pytest.mark.asyncio
    async def test_full_pipeline_timing(self):
        start = time.monotonic()
        await shape_response('{"result": 42}', start)
        elapsed = time.monotonic() - start
        assert elapsed >= MIN_LATENCY - 0.01
