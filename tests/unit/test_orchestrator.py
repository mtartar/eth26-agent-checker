"""Step 6 of PLAN.md.

Note what these tests do and don't check: they never call a real LLM. They
verify that VerificationAgent drives the tool-use loop correctly — calls the
right tool, feeds results back, stops on submit_verdict, and has a bounded
exit when the model never converges. Whether a *real* Claude call would
produce a good verdict is a separate, ongoing evaluation concern (see
PLAN.md's "suggested next milestones") — not something a unit test can
meaningfully assert.
"""

from dataclasses import dataclass, field
from typing import Any

from app.agent.orchestrator import MAX_STEPS, VerificationAgent
from app.config import Settings
from app.models import VerdictLabel
from app.tools.base import Tool, ToolResult


@dataclass
class _Block:
    type: str
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeResponse:
    content: list[_Block]


class FakeTool(Tool):
    """A no-op tool that always succeeds, so tests can assert on the loop, not real I/O."""

    name = "fake_lookup"
    description = "A fake tool for testing."

    def to_anthropic_schema(self):
        """Return a minimal, valid tool schema."""
        return {"name": self.name, "description": self.description, "input_schema": {}}

    def run(self, **kwargs):
        """Always succeed, echoing back whatever arguments it was called with."""
        return ToolResult(success=True, data={"found": True, "query": kwargs})


class ScriptedClient:
    """Replays a fixed sequence of responses, one per call.

    The simplest possible fake that still exercises the real loop in
    orchestrator.py.
    """

    def __init__(self, responses: list[_FakeResponse]) -> None:
        """Store the scripted responses to hand out in order."""
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def create_message(self, *, system, messages, tools):
        """Record the call and return the next scripted response."""
        self.calls.append({"messages": list(messages), "tools": tools})
        return self._responses[len(self.calls) - 1]


def _settings() -> Settings:
    return Settings(data_source="fixture")


def test_calls_tool_then_submits_verdict():
    """The agent runs a tool, feeds back its result, then returns the submitted verdict."""
    client = ScriptedClient(
        [
            _FakeResponse(
                content=[_Block(type="tool_use", id="1", name="fake_lookup", input={"q": "x"})]
            ),
            _FakeResponse(
                content=[
                    _Block(
                        type="tool_use",
                        id="2",
                        name="submit_verdict",
                        input={
                            "label": "confirmed",
                            "confidence": 0.9,
                            "explanation": "Found it.",
                        },
                    )
                ]
            ),
        ]
    )
    agent = VerificationAgent(_settings(), tools=[FakeTool()], anthropic_client=client)

    verdict = agent.verify("some claim")

    assert verdict.label == VerdictLabel.confirmed
    assert verdict.confidence == 0.9
    assert len(verdict.evidence) == 1
    assert verdict.evidence[0].tool_name == "fake_lookup"
    assert len(client.calls) == 2


def test_no_tool_call_is_treated_as_unverifiable():
    """A response with no tool_use blocks yields an 'unverifiable' verdict, not a crash."""
    client = ScriptedClient([_FakeResponse(content=[])])
    agent = VerificationAgent(_settings(), tools=[FakeTool()], anthropic_client=client)

    verdict = agent.verify("some claim")

    assert verdict.label == VerdictLabel.unverifiable
    assert verdict.confidence == 0.0


def test_unknown_tool_call_is_recorded_as_failed_evidence_not_a_crash():
    """A tool_use block naming an unregistered tool is recorded as failed evidence."""
    client = ScriptedClient(
        [
            _FakeResponse(
                content=[_Block(type="tool_use", id="1", name="nonexistent_tool", input={})]
            ),
            _FakeResponse(
                content=[
                    _Block(
                        type="tool_use",
                        id="2",
                        name="submit_verdict",
                        input={
                            "label": "unverifiable",
                            "confidence": 0.1,
                            "explanation": "Tool unavailable.",
                        },
                    )
                ]
            ),
        ]
    )
    agent = VerificationAgent(_settings(), tools=[FakeTool()], anthropic_client=client)

    verdict = agent.verify("some claim")

    assert verdict.evidence[0].result.success is False
    assert "unknown tool" in verdict.evidence[0].result.error


def test_gives_up_after_max_steps_without_a_verdict():
    """The loop stops after MAX_STEPS and returns 'unverifiable' if the model never submits."""
    never_submits = _FakeResponse(
        content=[_Block(type="tool_use", id="n", name="fake_lookup", input={})]
    )
    client = ScriptedClient([never_submits] * MAX_STEPS)
    agent = VerificationAgent(_settings(), tools=[FakeTool()], anthropic_client=client)

    verdict = agent.verify("some claim")

    assert verdict.label == VerdictLabel.unverifiable
    assert verdict.steps_used == MAX_STEPS
    assert len(client.calls) == MAX_STEPS
