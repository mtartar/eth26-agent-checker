"""The shared interface every data-source client implements.

Why this exists: the agent (app/agent/orchestrator.py) needs to call
whichever tool is relevant to a claim without knowing the details of each
API. If every tool exposes the same shape — a name, a JSON-schema-like
description of its inputs, and a `run(**kwargs) -> ToolResult` method — the
agent's code that dispatches tool calls never needs to change when you add a
new tool. This is the same idea as Anthropic's tool-use API itself: you
describe tools declaratively, the model decides which to call, your code
just executes whichever one it picked.

If you're new to "tool use" / "function calling" with LLMs: the core idea is
that you give the model a list of available tools (name + description +
parameters), the model responds with which tool to call and what arguments
to pass, you actually run that code yourself, and you feed the result back
to the model. The model never executes anything directly — it only ever
requests that *you* do so. That's what makes tool use safe to reason about:
every side effect is still your code, in your control.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """The outcome of running a tool.

    Shaped so the agent can reason about it and so we can persist it as
    Evidence (see app/models.py).
    """

    success: bool
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    # A human-checkable pointer to where this data came from — a block
    # explorer URL, a Space/entity ID, etc. This is what makes a verdict
    # more than "trust the AI": every piece of evidence has a citation.
    source_url: str | None = None


class Tool(ABC):
    """Base class for every external data source the agent can query."""

    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: Any) -> ToolResult:
        """Execute the tool and return a ToolResult.

        Must never raise for "expected" failures (not found, rate limited,
        etc.) — those should come back as `ToolResult(success=False,
        error=...)` so the agent can reason about them. Only raise for
        genuine bugs (bad configuration, programming errors).
        """

    def to_anthropic_schema(self) -> dict[str, Any]:
        """Return the tool description in the shape Anthropic's tool-use API expects.

        Override in subclasses (name/description/input_schema).
        """
        raise NotImplementedError
