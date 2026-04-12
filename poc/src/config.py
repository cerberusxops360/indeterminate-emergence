from dataclasses import dataclass, field
from typing import Optional

ALL_TOOLS = [
    "web_search",
    "calculator",
    "file_read",
    "code_exec",
    "database_query",
]

DEFAULT_BUDGET = 50.0
DEFAULT_PER_QUERY_EPSILON = 1.0
DEFAULT_ABSORPTION_MARGIN = 5.0


@dataclass
class SessionConfig:
    session_id: str
    authorized_tools: list[str]
    budget: float = DEFAULT_BUDGET
    per_query_epsilon: float = DEFAULT_PER_QUERY_EPSILON
    absorption_margin: float = DEFAULT_ABSORPTION_MARGIN


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionConfig] = {}

    def register(self, config: SessionConfig) -> None:
        self._sessions[config.session_id] = config

    def get(self, session_id: str) -> Optional[SessionConfig]:
        return self._sessions.get(session_id)


def check_policy(session: Optional[SessionConfig], tool: str) -> dict:
    """Return policy decision. Structure is identical regardless of outcome."""
    if session is None:
        return {"authorized": False, "reason": "no_session"}
    if tool not in ALL_TOOLS:
        return {"authorized": False, "reason": "unknown_tool"}
    if tool not in session.authorized_tools:
        return {"authorized": False, "reason": "not_authorized"}
    return {"authorized": True, "reason": "ok"}
