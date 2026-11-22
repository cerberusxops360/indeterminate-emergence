import hmac
import json
import logging
import time
from typing import Callable

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


# Called out of band when a budget runs out: listener(session_id, caller) with caller "owner" or "anon".
# This is how the session's owner learns that real work has stopped, or that someone is probing the
# session, without anything changing on the observable channel.
absorption_listeners: list[Callable[[str, str], None]] = []

_ANON_SUFFIX = "\x00anon"


def _get_or_create_accountant(session: SessionConfig, caller: str = "owner") -> PrivacyAccountant:
    key = session.session_id if caller == "owner" else session.session_id + _ANON_SUFFIX
    if key not in accountants:
        accountants[key] = PrivacyAccountant(
            budget=session.budget,
            per_query_cost=session.per_query_epsilon,
            margin=session.absorption_margin,
        )
    return accountants[key]


def _classify_caller(session: SessionConfig, caller_token: str) -> str:
    """"owner" or "anon". A session with no owner token keeps the original behaviour: every caller is the owner."""
    if session.owner_token is None:
        return "owner"
    same = hmac.compare_digest(caller_token.encode("utf-8"), session.owner_token.encode("utf-8"))
    return "owner" if same else "anon"


def _notify_absorption(session_id: str, caller: str) -> None:
    logger.warning("absorption started: session=%s caller=%s", session_id, caller)
    for listener in list(absorption_listeners):
        try:
            listener(session_id, caller)
        except Exception:
            logger.exception("absorption listener failed")


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
    caller_token = body.get("caller_token", "")
    if not isinstance(caller_token, str):
        caller_token = ""

    session = session_store.get(session_id) if isinstance(session_id, str) else None
    policy = check_policy(session, tool)

    # KI-005: the budget measures what one observer has learned, so it is charged to the observer.
    # A caller who does not hold the owner token spends the anonymous budget, can never cause real
    # work, and cannot touch the owner's budget. The observable response is the same either way.
    caller = "owner"
    is_absorbing = False
    if session is not None:
        caller = _classify_caller(session, caller_token)
        accountant = _get_or_create_accountant(session, caller)
        was_absorbing = accountant.absorbing
        is_absorbing = accountant.record_query()
        if is_absorbing and not was_absorbing:
            _notify_absorption(session.session_id, caller)

    await execute(
        tool_name=tool,
        params=params,
        authorized=policy["authorized"] and caller == "owner",
        absorbing=is_absorbing,
    )

    # Per spec: observable payload is always null for the observer.
    # Real content would be delivered through a separate authorized channel.
    observable_result = json.dumps({"result": None})

    shaped = await shape_response(observable_result, start)
    content = json.dumps(shaped)

    logger.debug(
        "action=%s session=%s authorized=%s caller=%s absorbing=%s",
        tool, session_id, policy["authorized"], caller, is_absorbing,
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
