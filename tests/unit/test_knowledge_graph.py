"""Step 5c of PLAN.md."""

from app.config import Settings
from app.tools.knowledge_graph import KnowledgeGraphTool


def _fixture_settings() -> Settings:
    return Settings(data_source="fixture", grc20_space_id="space-example-daos")


def test_finds_entity_by_name():
    """Looking up an entity by its name returns the matching fixture record and a source URL."""
    tool = KnowledgeGraphTool(_fixture_settings())
    result = tool.run(entity_name_or_id="Example DAO")

    assert result.success is True
    assert result.data["id"] == "grc20-entity-0001"
    assert result.source_url is not None


def test_finds_entity_by_id():
    """Looking up an entity by its GRC-20 id returns the matching fixture record."""
    tool = KnowledgeGraphTool(_fixture_settings())
    result = tool.run(entity_name_or_id="grc20-entity-0002")

    assert result.success is True
    assert result.data["name"] == "Example USD Coin"


def test_unknown_entity_returns_error():
    """Looking up a name/id with no fixture match returns a failed result, not an exception."""
    tool = KnowledgeGraphTool(_fixture_settings())
    result = tool.run(entity_name_or_id="Nonexistent Entity")

    assert result.success is False
    assert "no entity found" in result.error


def test_prepare_write_does_not_hit_the_network():
    """prepare_write is a pure function — it must never make an HTTP call.

    Real GRC-20 writes require deliberate wallet-key handling that this
    project does not implement (see the module docstring).
    """
    tool = KnowledgeGraphTool(_fixture_settings())
    payload = tool.prepare_write(
        entity_name="New Entity",
        entity_type="Organization",
        attributes={"Founded": "2026"},
    )

    assert payload["status"] == "prepared_not_submitted"
    assert payload["entity"]["name"] == "New Entity"
    assert payload["space_id"] == "space-example-daos"
