"""The verification agent's tool-use loop.

If you're new to building agents: this is the entire pattern. It is not more
complex than what's below. The loop is:

1. Send the conversation so far (starting with just the claim) to the model,
   along with a list of tools it's allowed to call.
2. The model replies with either plain text, or one or more "tool_use"
   blocks — structured requests like {"name": "query_token_transfers",
   "input": {"wallet_address": "0xabc..."}}.
3. Your code — not the model — actually executes the matching tool, and
   sends the result back as a "tool_result" message.
4. Repeat until the model calls a special `submit_verdict` tool (defined in
   prompts.py), which is how we get a structured final answer instead of
   parsing free text.

A hard step limit prevents an infinite loop if the model never calls
`submit_verdict` — always assume external systems (including LLMs) can
misbehave, and design a bounded exit path for when they do.

Testability note: `AnthropicClientProtocol` describes the one method this
module actually calls. Tests pass in a small fake object satisfying that
protocol instead of a real Anthropic client — see tests/unit/test_orchestrator.py.
This is what "mock the LLM, test your orchestration logic" looks like in
practice: nothing here asserts anything about whether Claude's *reasoning*
is good, only that your loop drives it correctly.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.agent.prompts import SUBMIT_VERDICT_TOOL, SYSTEM_PROMPT
from app.config import Settings
from app.models import VerdictLabel
from app.tools.base import Tool, ToolResult

MAX_STEPS = 6


class AnthropicClientProtocol(Protocol):
    """The one method this module needs from the Anthropic SDK's client.

    Defining this narrow protocol (rather than importing the real client
    type everywhere) is what makes a fake test double trivially valid.
    """

    def create_message(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> Any:
        """Send one turn to the model and return its raw response."""
        ...


@dataclass
class EvidenceRecord:
    """One tool call the agent made and the result it got back."""

    tool_name: str
    result: ToolResult


@dataclass
class AgentVerdict:
    """The agent's final answer for a claim, plus the evidence behind it."""

    label: VerdictLabel
    confidence: float
    explanation: str
    evidence: list[EvidenceRecord] = field(default_factory=list)
    steps_used: int = 0


class VerificationAgent:
    """Runs the tool-use loop described in this module's docstring."""

    def __init__(
        self,
        settings: Settings,
        tools: list[Tool],
        anthropic_client: AnthropicClientProtocol,
    ) -> None:
        """Wire up the tools the agent may call and the client it calls the model with."""
        self._settings = settings
        self._tools_by_name: dict[str, Tool] = {t.name: t for t in tools}
        self._client = anthropic_client

    def verify(self, claim_text: str) -> AgentVerdict:
        """Run the tool-use loop for one claim and return the resulting verdict."""
        messages: list[dict[str, Any]] = [{"role": "user", "content": claim_text}]
        tool_schemas = [t.to_anthropic_schema() for t in self._tools_by_name.values()]
        tool_schemas.append(SUBMIT_VERDICT_TOOL)
        evidence: list[EvidenceRecord] = []

        for step in range(1, MAX_STEPS + 1):
            response = self._client.create_message(
                system=SYSTEM_PROMPT, messages=messages, tools=tool_schemas
            )
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

            if not tool_use_blocks:
                # The model produced plain text with no tool call. Treat this
                # as inconclusive rather than guessing at a verdict from prose.
                return AgentVerdict(
                    label=VerdictLabel.unverifiable,
                    confidence=0.0,
                    explanation="Agent did not call any tools or submit a verdict.",
                    evidence=evidence,
                    steps_used=step,
                )

            for block in tool_use_blocks:
                if block.name == "submit_verdict":
                    return AgentVerdict(
                        label=VerdictLabel(block.input["label"]),
                        confidence=float(block.input["confidence"]),
                        explanation=block.input["explanation"],
                        evidence=evidence,
                        steps_used=step,
                    )

            # Not a verdict yet — run every requested tool and feed results back.
            messages.append({"role": "assistant", "content": response.content})
            tool_results_content = []
            for block in tool_use_blocks:
                tool = self._tools_by_name.get(block.name)
                if tool is None:
                    result = ToolResult(success=False, error=f"unknown tool: {block.name}")
                else:
                    result = tool.run(**block.input)
                evidence.append(EvidenceRecord(tool_name=block.name, result=result))
                tool_results_content.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(
                            {"success": result.success, "data": result.data, "error": result.error}
                        ),
                    }
                )
            messages.append({"role": "user", "content": tool_results_content})

        return AgentVerdict(
            label=VerdictLabel.unverifiable,
            confidence=0.0,
            explanation=f"Agent did not reach a verdict within {MAX_STEPS} steps.",
            evidence=evidence,
            steps_used=MAX_STEPS,
        )
