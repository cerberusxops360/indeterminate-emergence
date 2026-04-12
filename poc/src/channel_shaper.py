import asyncio
import json
import random
import time

RESPONSE_SIZE = 4096  # bytes, fixed
MIN_LATENCY = 0.2     # 200ms minimum
MAX_LATENCY = 0.4     # 400ms maximum


def pad_payload(raw_result: str) -> dict:
    """Create a fixed-size response body regardless of raw_result content."""
    response = {
        "status": "processed",
        "receipt": "ack",
        "payload": "",
        "padding": "",
    }

    # Measure the skeleton size (empty payload and padding)
    skeleton_size = len(json.dumps(response).encode("utf-8"))
    available = RESPONSE_SIZE - skeleton_size

    # Encode payload to measure its byte length in JSON serialization.
    # json.dumps adds surrounding quotes and escapes special chars,
    # so we measure the serialized form minus the 2 quote chars.
    def json_str_bytes(s: str) -> int:
        return len(json.dumps(s).encode("utf-8")) - 2  # subtract quotes

    # Truncate payload to fit, leaving room for padding
    payload = raw_result
    payload_bytes = json_str_bytes(payload)

    # Binary search for max payload length that fits
    if payload_bytes > available:
        lo, hi = 0, len(payload)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if json_str_bytes(payload[:mid]) <= available - 1:  # leave at least 1 byte for padding
                lo = mid
            else:
                hi = mid - 1
        payload = payload[:lo]
        payload_bytes = json_str_bytes(payload)

    response["payload"] = payload
    padding_bytes_needed = available - payload_bytes

    # Padding char 'x' is 1 byte in both UTF-8 and JSON string encoding
    if padding_bytes_needed > 0:
        response["padding"] = "x" * padding_bytes_needed

    # Verify and adjust — handle off-by-one from JSON escaping
    actual = len(json.dumps(response).encode("utf-8"))
    diff = RESPONSE_SIZE - actual

    if diff > 0:
        response["padding"] = response["padding"] + "x" * diff
    elif diff < 0:
        response["padding"] = response["padding"][:len(response["padding"]) + diff]

    return response


async def shape_timing(execution_start: float) -> None:
    """Ensure total response time falls within [MIN_LATENCY, MAX_LATENCY]."""
    target = random.uniform(MIN_LATENCY, MAX_LATENCY)
    elapsed = time.monotonic() - execution_start
    remaining = target - elapsed

    if remaining > 0:
        await asyncio.sleep(remaining)


async def shape_response(raw_result: str, execution_start: float) -> dict:
    """Full channel shaping: pad size + pad timing."""
    response = pad_payload(raw_result)
    await shape_timing(execution_start)
    return response
