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

# Interactive docs and the OpenAPI schema are off: they describe the interface to anyone who asks.
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
# No automatic redirect for a trailing slash: a redirect is an unshaped response.
app.router.redirect_slashes = False

session_store = SessionStore()
accountants: dict[str, PrivacyAccountant] = {}

_ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


def _get_or_create_accountant(session: SessionConfig) -> PrivacyAccountant:
    if session.session_id not in accountants:
        accountants[session.session_id] = PrivacyAccountant(
            budget=session.budget,
            per_query_cost=session.per_query_epsilon,
            margin=session.absorption_margin,
        )
    return accountants[session.session_id]


async def _read_body(request: Request) -> dict:
    """Read and parse the request body. Anything that is not a JSON object is treated as an empty request."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    return body if isinstance(body, dict) else {}


async def _respond(body: dict) -> Response:
    """The one response path. Every request, well formed or not, leaves through here.

    The shaping clock starts when this function is entered, which is AFTER the request body has been
    read. Starting it before the read let a caller send the body slowly, push the elapsed time past
    the shaping target, and receive the response at raw executor time (red team finding, 2026-11-21).
    """
    start = time.monotonic()

    session_id = body.get("session_id", "default")
    tool = body.get("tool", "")
    params = body.get("params", {})
    # Type confusion: a non-string session id or tool, or non-object params, is handled as an
    # unknown session, an unknown tool, or empty params. No input may raise.
    if not isinstance(tool, str):
        tool = ""
    if not isinstance(params, dict):
        params = {}

    session = session_store.get(session_id) if isinstance(session_id, str) else None
    policy = check_policy(session, tool)

    is_absorbing = False
    if session is not None:
        accountant = _get_or_create_accountant(session)
        is_absorbing = accountant.record_query()

    await execute(
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


@app.post("/action")
async def handle_action(request: Request) -> Response:
    return await _respond(await _read_body(request))


@app.api_route("/{full_path:path}", methods=_ALL_METHODS, include_in_schema=False)
async def handle_anything_else(request: Request, full_path: str) -> Response:
    """Wrong path or wrong method. Answered exactly like a request for an unknown session: same status,
    same size, same timing, same work. The body is read and discarded so the clock starts at the same point."""
    await _read_body(request)
    return await _respond({})


@app.exception_handler(Exception)
async def handle_exception(request: Request, exc: Exception) -> Response:
    """Last resort. An unexpected error still leaves through the shaped path."""
    logger.exception("unhandled error, answered through the shaped path")
    return await _respond({})
