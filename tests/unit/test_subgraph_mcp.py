"""Step 5b of PLAN.md."""

from app.config import Settings
from app.tools.subgraph_mcp import SubgraphQueryTool


def _fixture_settings() -> Settings:
    return Settings(data_source="fixture")


def test_finds_transfer_for_known_wallet():
    """A wallet address present in the fixture data returns its matching transfer."""
    tool = SubgraphQueryTool(_fixture_settings())
    result = tool.run(wallet_address="0x1522900b6dafac587d499a862861c0869be6e421")

    assert result.success is True
    assert len(result.data["transfers"]) == 1
    assert result.data["transfers"][0]["token"]["symbol"] == "USDC"


def test_no_matches_for_unknown_wallet():
    """A wallet address absent from the fixture data returns an empty, successful result."""
    tool = SubgraphQueryTool(_fixture_settings())
    result = tool.run(wallet_address="0x000000000000000000000000000000000000dead")

    assert result.success is True
    assert result.data["transfers"] == []


def test_missing_wallet_address_is_an_error():
    """Calling run() without a wallet_address returns a failed result, not an exception."""
    tool = SubgraphQueryTool(_fixture_settings())
    result = tool.run()

    assert result.success is False
