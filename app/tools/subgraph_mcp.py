"""Client for querying subgraphs.

What a subgraph is, if you're new to The Graph: a subgraph is a schema plus
a set of mappings that tell an indexer which smart-contract events to watch
and how to turn them into queryable entities. Someone deploys a subgraph
once; after that, anyone can query it with plain GraphQL — you never touch
the raw blockchain logs yourself. There are already 15,000+ public subgraphs
covering most major protocols.

The Graph also ships "Subgraph MCP" — an MCP server that lets an AI agent
search and query subgraphs using natural language instead of hand-written
GraphQL. In production, you have two reasonable choices:

1. Connect to the real Subgraph MCP server as an MCP client (best if you
   want the agent to discover *which* subgraph to use dynamically).
2. Query a specific, known subgraph endpoint directly with GraphQL (best
   once you know exactly which subgraph your use case needs — simpler,
   fewer moving parts, and what this starter implements).

This client does (2): a direct GraphQL client against a configured subgraph
endpoint. If you later want (1), the `Tool` interface in app/tools/base.py
is exactly what makes that swap possible without touching the agent code —
only this file would change.
"""

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.tools.base import Tool, ToolResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"

# A minimal, generic query shape. Real usage should replace this with the
# actual schema of whichever subgraph you're targeting — every subgraph
# defines its own entity types.
_TRANSFER_QUERY = """
query Transfers($wallet: String!, $first: Int!) {
  transfers(
    where: { or: [{ from: $wallet }, { to: $wallet }] }
    first: $first
    orderBy: timestamp
    orderDirection: desc
  ) {
    id
    from
    to
    amount
    token { symbol }
    timestamp
    transactionHash
  }
}
"""


class SubgraphQueryTool(Tool):
    """Queries a specific subgraph endpoint for wallet transfers, against fixtures or live."""

    name = "query_subgraph"
    description = (
        "Run a GraphQL query against an indexed subgraph to check "
        "protocol-level or transfer-level on-chain facts."
    )

    def __init__(self, settings: Settings, subgraph_endpoint: str = "") -> None:
        """Build an HTTP client for live queries against `subgraph_endpoint`."""
        self._settings = settings
        self._endpoint = subgraph_endpoint
        self._client = httpx.Client(timeout=15.0)

    def to_anthropic_schema(self) -> dict[str, Any]:
        """Return this tool's name/description/input_schema for the Anthropic API."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "wallet_address": {
                        "type": "string",
                        "description": "Wallet address to look up transfers for",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max number of results, default 10",
                    },
                },
                "required": ["wallet_address"],
            },
        }

    def run(self, **kwargs: Any) -> ToolResult:
        """Look up transfers for `wallet_address` against fixtures or the live subgraph."""
        wallet_address = kwargs.get("wallet_address", "")
        limit = kwargs.get("limit", 10)
        if not wallet_address:
            return ToolResult(success=False, error="wallet_address is required")

        if self._settings.is_live:
            return self._run_live(wallet_address, limit)
        return self._run_fixture(wallet_address, limit)

    def _run_fixture(self, wallet_address: str, limit: int) -> ToolResult:
        fixture_path = FIXTURES_DIR / "subgraph_response.json"
        try:
            payload = json.loads(fixture_path.read_text())
        except FileNotFoundError:
            return ToolResult(success=False, error=f"fixture not found: {fixture_path}")

        transfers = payload.get("data", {}).get("transfers", [])
        matched = [
            t
            for t in transfers
            if wallet_address.lower() in (t.get("from", "").lower(), t.get("to", "").lower())
        ][:limit]
        return ToolResult(success=True, data={"transfers": matched})

    def _run_live(self, wallet_address: str, limit: int) -> ToolResult:
        if not self._endpoint:
            return ToolResult(success=False, error="no subgraph endpoint configured")
        try:
            response = self._client.post(
                self._endpoint,
                json={
                    "query": _TRANSFER_QUERY,
                    "variables": {"wallet": wallet_address.lower(), "first": limit},
                },
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"subgraph query failed: {exc}")

        if "errors" in payload:
            return ToolResult(success=False, error=str(payload["errors"]))
        return ToolResult(success=True, data=payload.get("data", {}))
