"""Thin adapter around the real Anthropic SDK.

This exists purely to satisfy `AnthropicClientProtocol` in orchestrator.py
with a single, narrow method — keeping the SDK's actual client (with all its
other methods, auth handling, retries, etc.) out of the orchestration logic.
Only this file imports `anthropic` directly.
"""

from typing import Any, cast

import anthropic
from anthropic.types import MessageParam, ToolParam

from app.config import Settings


class AnthropicClient:
    """Wraps `anthropic.Anthropic` behind the single method the orchestrator needs."""

    def __init__(self, settings: Settings) -> None:
        """Build the underlying SDK client from `settings`."""
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def create_message(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> Any:
        """Send one turn to the model and return the raw SDK response."""
        # `messages`/`tools` are plain dicts by design (see AnthropicClientProtocol) so
        # a fixture client can satisfy the same shape without depending on `anthropic`.
        # The real SDK wants its own TypedDicts; the shape is identical at runtime.
        return self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=system,
            messages=cast("list[MessageParam]", messages),
            tools=cast("list[ToolParam]", tools),
        )
