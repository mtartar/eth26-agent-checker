"""Client for The Graph's Token API.

What the Token API is: a REST API (not GraphQL, unlike subgraphs) that gives
you simple, ready-made answers to common questions like "what are this
wallet's token balances" or "what transfers has this wallet made" — without
you having to write and deploy your own subgraph first. It's the fastest way
to get on-chain financial data for a claim like "wallet X received $50,000
in USDC" without building indexing infrastructure yourself.

This client has two modes, controlled by `Settings.data_source`:

- "fixture": reads a recorded, real response from tests/fixtures/. This is
  what lets you build and test the whole system before you have an API key,
  and what keeps the test suite fast and deterministic (no network flakiness).
- "live": makes a real HTTPS call using `THE_GRAPH_API_KEY`.

Before wiring up "live" mode for real, check
https://thegraph.com/docs/en/token-api/quick-start/ for the current base URL
and response shape — REST APIs evolve, and this client isolates that change
to one file.
"""

import json
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.tools.base import Tool, ToolResult

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


class TokenApiTool(Tool):
    """Looks up on-chain token transfers for a wallet, against fixtures or the live Token API."""

    name = "query_token_transfers"
    description = (
        "Look up real, on-chain token transfers for a wallet address, "
        "optionally filtered by token symbol and time window. Use this to "
        "check claims about specific wallets sending or receiving funds."
    )

    def __init__(self, settings: Settings) -> None:
        """Build an HTTP client authenticated against The Graph's gateway."""
        self._settings = settings
        self._client = httpx.Client(
            base_url=settings.the_graph_gateway_url,
            headers={"Authorization": f"Bearer {settings.the_graph_api_key}"},
            timeout=15.0,
        )

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
                        "description": "The wallet address to look up, e.g. 0xabc...",
                    },
                    "token_symbol": {
                        "type": "string",
                        "description": "Optional token symbol filter, e.g. USDC",
                    },
                    "min_amount_usd": {
                        "type": "number",
                        "description": "Optional minimum transfer amount in USD",
                    },
                },
                "required": ["wallet_address"],
            },
        }

    def run(self, **kwargs: Any) -> ToolResult:
        """Look up transfers for `wallet_address` against fixtures or the live Token API."""
        wallet_address = kwargs.get("wallet_address", "")
        if not wallet_address:
            return ToolResult(success=False, error="wallet_address is required")

        if self._settings.is_live:
            return self._run_live(wallet_address, kwargs)
        return self._run_fixture(wallet_address, kwargs)

    def _run_fixture(self, wallet_address: str, params: dict[str, Any]) -> ToolResult:
        fixture_path = FIXTURES_DIR / "token_api_transfer.json"
        try:
            payload = json.loads(fixture_path.read_text())
        except FileNotFoundError:
            return ToolResult(success=False, error=f"fixture not found: {fixture_path}")

        transfers = [
            t for t in payload.get("transfers", []) if _matches(t, wallet_address, params)
        ]
        return ToolResult(
            success=True,
            data={"transfers": transfers, "count": len(transfers)},
            source_url=payload.get("explorer_url_template"),
        )

    def _run_live(self, wallet_address: str, params: dict[str, Any]) -> ToolResult:
        try:
            response = self._client.get(
                "/token-api/transfers",
                params={"address": wallet_address, **_clean(params)},
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Token API request failed: {exc}")

        return ToolResult(success=True, data=payload)


def _matches(transfer: dict[str, Any], wallet_address: str, params: dict[str, Any]) -> bool:
    if transfer.get("from", "").lower() != wallet_address.lower() and (
        transfer.get("to", "").lower() != wallet_address.lower()
    ):
        return False
    token_symbol = params.get("token_symbol")
    if token_symbol and transfer.get("token_symbol", "").upper() != token_symbol.upper():
        return False
    min_amount = params.get("min_amount_usd")
    if min_amount and transfer.get("amount_usd", 0) < min_amount:
        return False
    return True


def _clean(params: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if k != "wallet_address" and v is not None}
