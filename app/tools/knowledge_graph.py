"""Client for reading (and, in a limited way, preparing writes to) a GRC-20 knowledge graph.

What GRC-20 is, if you're new to it: it's a data format for representing
structured knowledge — entities, types, attributes, and relations between
them — organized into "Spaces" that can be published and read collectively
(the umbrella project is called Geo). Where a subgraph answers "what happened
on-chain," a GRC-20 knowledge graph answers "what do we know about this
entity" — e.g. "who founded this DAO," "what contract address corresponds to
this token," "what did this audit conclude." Official tooling is currently
JavaScript/TypeScript-first (`@graphprotocol/grc-20`, and the newer
`@geoprotocol/geo-sdk`) — this is genuinely fast-moving infrastructure, so
treat exact package/endpoint names as something to re-verify, not something
to trust from any one snapshot in time (including this file).

Design decision — reads vs. writes:

- **Reads** are implemented as an ordinary GraphQL client against a
  configurable API origin, exactly like `subgraph_mcp.py`. This is safe to
  run against fixtures or real endpoints with no special handling.

- **Writes are intentionally NOT fully implemented here.** Publishing to a
  GRC-20 Space means constructing signed operations and submitting an
  on-chain (or IPFS + on-chain anchor) transaction — that requires wallet key
  management, which is a security-sensitive decision that deserves its own
  explicit design discussion, not a default enabled by an agent calling a
  tool. What's provided instead is `prepare_write()`, which builds the
  well-formed *payload* you would sign and submit, and returns it without
  submitting anything. This lets you build and test the "does the agent
  decide correctly what to write" logic completely safely, and add real
  submission later as a deliberate, reviewed step (see PLAN.md, Step 11
  "Suggested next milestones").
"""

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.tools.base import Tool, ToolResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"

_ENTITY_QUERY = """
query Entity($id: String!, $spaceId: String!) {
  entity(id: $id, spaceId: $spaceId) {
    id
    name
    types
    attributes { name value }
  }
}
"""


class KnowledgeGraphTool(Tool):
    """Looks up entities in a GRC-20 knowledge graph, against fixtures or a live API."""

    name = "query_knowledge_graph"
    description = (
        "Look up a structured entity (person, organization, contract, "
        "claim, etc.) in the GRC-20 knowledge graph by name or ID, to check "
        "non-transactional facts."
    )

    def __init__(self, settings: Settings) -> None:
        """Build an HTTP client for live queries; fixture mode never uses it."""
        self._settings = settings
        self._client = httpx.Client(timeout=15.0)

    def to_anthropic_schema(self) -> dict[str, Any]:
        """Return this tool's name/description/input_schema for the Anthropic API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "entity_name_or_id": {
                        "type": "string",
                        "description": "The entity's name or GRC-20 ID to look up",
                    },
                },
                "required": ["entity_name_or_id"],
            },
        }

    def run(self, **kwargs: Any) -> ToolResult:
        """Look up `entity_name_or_id` against fixtures or the live GRC-20 API."""
        entity_ref = kwargs.get("entity_name_or_id", "")
        if not entity_ref:
            return ToolResult(success=False, error="entity_name_or_id is required")

        if self._settings.is_live:
            return self._run_live(entity_ref)
        return self._run_fixture(entity_ref)

    def _run_fixture(self, entity_ref: str) -> ToolResult:
        fixture_path = FIXTURES_DIR / "grc20_entity.json"
        try:
            entities = json.loads(fixture_path.read_text())
        except FileNotFoundError:
            return ToolResult(success=False, error=f"fixture not found: {fixture_path}")

        match = next(
            (
                e
                for e in entities
                if entity_ref.lower() in (e.get("id", "").lower(), e.get("name", "").lower())
            ),
            None,
        )
        if match is None:
            return ToolResult(success=False, error=f"no entity found matching '{entity_ref}'")
        return ToolResult(
            success=True,
            data=match,
            source_url=f"https://www.geobrowser.io/space/{match.get('space_id')}/{match.get('id')}",
        )

    def _run_live(self, entity_ref: str) -> ToolResult:
        if not self._settings.grc20_api_origin:
            return ToolResult(success=False, error="GRC20_API_ORIGIN is not configured")
        try:
            response = self._client.post(
                f"{self._settings.grc20_api_origin}/graphql",
                json={
                    "query": _ENTITY_QUERY,
                    "variables": {"id": entity_ref, "spaceId": self._settings.grc20_space_id},
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"knowledge graph query failed: {exc}")

        if "errors" in payload:
            return ToolResult(success=False, error=str(payload["errors"]))
        entity = payload.get("data", {}).get("entity")
        if entity is None:
            return ToolResult(success=False, error=f"no entity found matching '{entity_ref}'")
        return ToolResult(success=True, data=entity)

    def prepare_write(
        self, entity_name: str, entity_type: str, attributes: dict[str, str]
    ) -> dict[str, Any]:
        """Build the payload for a new GRC-20 entity/relation *without* submitting anything.

        Returns a plain dict you can log, review, or (deliberately, later)
        pass to real publishing tooling.

        Kept synchronous and side-effect-free on purpose — this is a pure
        function you can unit test without any network access at all.
        """
        return {
            "space_id": self._settings.grc20_space_id,
            "entity": {
                "name": entity_name,
                "types": [entity_type],
                "attributes": [{"name": k, "value": v} for k, v in attributes.items()],
            },
            "status": "prepared_not_submitted",
        }
