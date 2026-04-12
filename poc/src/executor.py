import asyncio
import hashlib
import json
import random


async def simulate_tool(tool_name: str, params: dict) -> str:
    """Simulate a real tool call with realistic latency and output."""
    latency = random.uniform(0.05, 0.3)
    await asyncio.sleep(latency)

    if tool_name == "web_search":
        return json.dumps({"results": [f"Result for {params.get('query', '')}"]})
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


async def dummy_computation() -> str:
    """
    Absorption mode: perform work that matches real tool resource profile.
    Consumes similar CPU time and memory as a real tool call.
    """
    latency = random.uniform(0.05, 0.3)
    await asyncio.sleep(latency)
    hashlib.sha256(random.randbytes(1024)).hexdigest()
    return json.dumps({"result": None})


async def execute(
    tool_name: str,
    params: dict,
    authorized: bool,
    absorbing: bool,
) -> str:
    """
    Core execution logic. Three cases, all producing the same external observation:
    1. Not authorized -> dummy computation
    2. Authorized but absorbing -> dummy computation
    3. Authorized and normal -> real tool call
    """
    if not authorized or absorbing:
        return await dummy_computation()
    return await simulate_tool(tool_name, params)
