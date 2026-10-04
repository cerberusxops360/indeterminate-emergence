import asyncio
import hashlib
import json
import random

# Observable-channel execution. The observable response is nulled and shaped by the
# proxy regardless of path, so capability must not leak through the WORK done to
# produce a response. The real path (simulate_tool) builds genuine tool content for
# out-of-band delivery; the absorption path (dummy_computation) performs the SAME
# latency draw, the SAME sha256 normalization, and the SAME content-build work (then
# discards it) so the two paths are indistinguishable in CPU, allocation, and timing.
# Matching the content-build removed a sub-1pct residual detectable only at very large
# n (calculator, n=120000). Executor latency stays below the channel-shaper floor so
# the shaper fully determines observed timing. Note: a deployment with a real
# side-effecting tool cannot build-and-discard; it requires a sealed or constant-time
# executor, a stated deployment requirement not proven by this PoC.

EXEC_MIN = 0.05
EXEC_MAX = 0.15


def _tool_content(tool_name: str, params: dict) -> str:
    if tool_name == "web_search":
        return json.dumps({"results": ["Result for query"]})
    elif tool_name == "calculator":
        return json.dumps({"result": 42})
    elif tool_name == "file_read":
        return json.dumps({"content": "File contents here..."})
    elif tool_name == "code_exec":
        return json.dumps({"stdout": "Hello World", "exit_code": 0})
    elif tool_name == "database_query":
        return json.dumps({"rows": [{"id": 1, "value": "data"}]})
    else:
        return json.dumps({"result": None})


async def simulate_tool(tool_name: str, params: dict) -> str:
    """Real tool path. Returns genuine content for out-of-band delivery; the
    observable channel is nulled and shaped by the proxy."""
    latency = random.uniform(EXEC_MIN, EXEC_MAX)
    await asyncio.sleep(latency)
    hashlib.sha256(random.randbytes(1024)).hexdigest()
    return _tool_content(tool_name, params)


async def dummy_computation(tool_name: str = "", params: dict = None) -> str:
    """Absorption path. Performs identical observable work to simulate_tool,
    including the content build, then discards it and returns a null observable."""
    latency = random.uniform(EXEC_MIN, EXEC_MAX)
    await asyncio.sleep(latency)
    hashlib.sha256(random.randbytes(1024)).hexdigest()
    _ = _tool_content(tool_name, params or {})
    return json.dumps({"result": None})


async def execute(
    tool_name: str,
    params: dict,
    authorized: bool,
    absorbing: bool,
) -> str:
    """Three cases, one observation. The observable work is identical across
    authorized-normal, unauthorized, and authorized-absorbing."""
    if not authorized or absorbing:
        return await dummy_computation(tool_name, params)
    return await simulate_tool(tool_name, params)
