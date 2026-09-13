"""A scripted stand-in for the real Anthropic client, used when `DATA_SOURCE=fixture`.

This lets you run the *entire* HTTP API — submit a claim, get a verdict — with
zero API keys, by following a fixed two-step script instead of real model
reasoning:

  step 1: call `query_token_transfers` for a wallet address found in the
          claim text (or a default demo address if none is found)
  step 2: submit a verdict based on whether that lookup found matching
          transfers

This is deliberately simple and not meant to demonstrate real agent
reasoning — it exists so the full request/response contract (API, database,
background task, evidence persistence) is exercisable and testable before
you've written a single line of prompt engineering or spent a token on a
real model call. Compare this to a UI team building against a mocked
backend before the real backend exists — same idea.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

_ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
_DEFAULT_ADDRESS = "0x1522900b6dafac587d499a862861c0869be6e421"


@dataclass
class _Block:
    type: str
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    text: str = ""


@dataclass
class _FakeResponse:
    content: list[_Block]
    stop_reason: str = "tool_use"


class FixtureAnthropicClient:
    """Runs the two-step script described in the module docstring above.

    Deliberately stateless across calls to `create_message`: which step of
    the script to run is inferred from the *shape of the conversation so
    far* (how many messages have been exchanged), not from an internal
    counter. A counter would break the moment this client is reused across
    more than one `agent.verify()` call — exactly the situation
    `scripts/seed_demo_data.py` exercises when it checks several claims with
    one agent instance.
    """

    def create_message(
        self, *, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> _FakeResponse:
        """Return the next scripted tool call given the conversation so far."""
        if len(messages) == 1:
            claim_text = messages[0]["content"]
            match = _ADDRESS_RE.search(claim_text)
            wallet_address = match.group(0) if match else _DEFAULT_ADDRESS
            return _FakeResponse(
                content=[
                    _Block(
                        type="tool_use",
                        id="call_1",
                        name="query_token_transfers",
                        input={"wallet_address": wallet_address},
                    )
                ]
            )

        # Step 2: look at the most recent tool_result to decide the verdict.
        last_message = messages[-1]
        tool_result_content = last_message["content"][0]["content"]
        result = json.loads(tool_result_content)
        found_transfers = result.get("success") and result.get("data", {}).get("count", 0) > 0

        if found_transfers:
            label, confidence, explanation = (
                "confirmed",
                0.85,
                "Found a matching on-chain transfer for the claimed wallet address.",
            )
        else:
            label, confidence, explanation = (
                "unverifiable",
                0.3,
                "No matching on-chain transfer was found for the claimed wallet address "
                "in the available data.",
            )

        return _FakeResponse(
            content=[
                _Block(
                    type="tool_use",
                    id="call_2",
                    name="submit_verdict",
                    input={"label": label, "confidence": confidence, "explanation": explanation},
                )
            ]
        )
