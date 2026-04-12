import json
import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import Response

from src.accountant import PrivacyAccountant
from src.channel_shaper import shape_response
from src.config import SessionConfig, SessionStore, check_policy
from src.executor import execute

logger = logging.getLogger(__name__)

app = FastAPI()

session_store = SessionStore()
accountants: dict[str, PrivacyAccountant] = {}


def _get_or_create_accountant(session: SessionConfig) -> PrivacyAccountant:
    if session.session_id not in accountants:
        accountants[session.session_id] = PrivacyAccountant(
            budget=session.budget,
            per_query_cost=session.per_query_epsilon,
            margin=session.absorption_margin,
        )
    return accountants[session.session_id]


@app.post("/action")
async def handle_action(request: Request) -> Response:
    start = time.monotonic()

    try:
        body = await request.json()
    except Exception:
        body = {}

    session_id = body.get("session_id", "default")
    tool = body.get("tool", "")
    params = body.get("params", {})

    session = session_store.get(session_id)
    policy = check_policy(session, tool)

    is_absorbing = False
    if session is not None:
        accountant = _get_or_create_accountant(session)
        is_absorbing = accountant.record_query()

    raw_result = await execute(
        tool_name=tool,
        params=params,
        authorized=policy["authorized"],
        absorbing=is_absorbing,
    )

    # Per spec: observable payload is always null for the observer.
    # Real content would be delivered through a separate authorized channel.
    observable_result = json.dumps({"result": None})

    shaped = await shape_response(observable_result, start)
    content = json.dumps(shaped)

    logger.debug(
        "action=%s session=%s authorized=%s absorbing=%s",
        tool, session_id, policy["authorized"], is_absorbing,
    )

    return Response(
        content=content.encode("utf-8"),
        status_code=200,
        media_type="application/json",
    )
