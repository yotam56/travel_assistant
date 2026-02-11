"""Per-request middleware event collector using contextvars.

Usage:
    # In the request handler (main.py):
    reset_events()
    agent.invoke(...)
    events = get_events()

    # In middleware:
    emit_event(middleware="retry_model", status="retried", message="...", details={...})
"""

import contextvars
from typing import Any

_events: contextvars.ContextVar[list[dict[str, Any]]] = contextvars.ContextVar(
    "middleware_events", default=[]
)


def reset_events() -> None:
    """Clear the event list for a new request."""
    _events.set([])


def emit_event(*, middleware: str, status: str, message: str, details: dict[str, Any] | None = None) -> None:
    """Append a middleware event for the current request."""
    event = {"middleware": middleware, "status": status, "message": message}
    if details:
        event["details"] = details
    _events.get().append(event)


def get_events() -> list[dict[str, Any]]:
    """Return all middleware events collected during the current request."""
    return list(_events.get())
