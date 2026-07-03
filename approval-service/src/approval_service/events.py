"""Simple in-process event bus for future integration.

Publishes events after state changes so other services can react.
Currently just logs — replace with Kafka/RabbitMQ/Redis PubSub in production.
"""

import logging
from collections.abc import Callable, Coroutine
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

_listeners: list[Handler] = []


def subscribe(handler: Handler) -> None:
    """Register an async event handler.  Handler signature: (event_type, payload) -> None."""
    _listeners.append(handler)


async def publish(event_type: str, payload: dict[str, Any]) -> None:
    """Publish an event to all registered handlers."""
    # Strip secrets/sensitive data before publishing
    safe_payload = _sanitize(payload)
    logger.info("Event published: type=%s payload=%s", event_type, safe_payload)
    for handler in _listeners:
        try:
            await handler(event_type, safe_payload)
        except Exception:
            logger.exception("Event handler failed for %s", event_type)


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive keys from payload before logging/publishing."""
    sensitive = {"token", "secret", "password", "email", "key", "url", "credential"}
    return {
        k: v
        for k, v in payload.items()
        if not any(s in k.lower() for s in sensitive)
    }
