"""Step 5a of PLAN.md."""

from app.config import Settings
from app.tools.token_api import TokenApiTool


def _fixture_settings() -> Settings:
    return Settings(data_source="fixture")


def test_finds_transfers_for_known_wallet():
    """A wallet address present in the fixture data returns its transfers."""
    tool = TokenApiTool(_fixture_settings())
    result = tool.run(wallet_address="0x1522900b6dafac587d499a862861c0869be6e421")

    assert result.success is True
    assert result.data["count"] == 2


def test_filters_by_token_symbol():
    """A token_symbol filter that matches nothing returns zero transfers, not an error."""
    tool = TokenApiTool(_fixture_settings())
    result = tool.run(
        wallet_address="0x1522900b6dafac587d499a862861c0869be6e421",
        token_symbol="DOES_NOT_EXIST",
    )

    assert result.success is True
    assert result.data["count"] == 0


def test_no_matches_for_unknown_wallet():
    """A wallet address absent from the fixture data returns an empty, successful result."""
    tool = TokenApiTool(_fixture_settings())
    result = tool.run(wallet_address="0x000000000000000000000000000000000000dead")

    assert result.success is True
    assert result.data["count"] == 0


def test_missing_wallet_address_is_an_error():
    """Calling run() without a wallet_address returns a failed result, not an exception."""
    tool = TokenApiTool(_fixture_settings())
    result = tool.run()

    assert result.success is False
    assert "wallet_address" in result.error
