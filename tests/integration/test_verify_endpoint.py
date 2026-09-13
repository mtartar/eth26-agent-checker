"""Step 8 of PLAN.md.

This test exercises the real HTTP layer, the real database layer, and the
real orchestration loop — the only thing replaced is the LLM itself
(FixtureAnthropicClient, selected automatically because DATA_SOURCE defaults
to "fixture"). This is the closest thing in this project to "does the whole
system actually work end to end," while still running in under a second
with no network access or API keys.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient wired to a fresh, isolated on-disk database per test."""
    db_path = tmp_path / "test_agent_checker.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DATA_SOURCE", "fixture")

    # These modules cache state at import time (a cached Settings object and
    # a module-level database engine), so we reload them in dependency order
    # to pick up the test environment variables set above.
    import app.config
    import app.database
    import app.main

    app.config.get_settings.cache_clear()
    importlib.reload(app.database)
    importlib.reload(app.main)

    with TestClient(app.main.app) as test_client:
        yield test_client


def test_verify_wallet_transfer_claim(client):
    """A claim about a wallet with a matching fixture transfer resolves to 'confirmed'."""
    submit_response = client.post(
        "/verify",
        json={
            "claim_text": (
                "Wallet 0x1522900b6dafac587d499a862861c0869be6e421 received "
                "a large USDC transfer"
            )
        },
    )
    assert submit_response.status_code == 202
    verification_id = submit_response.json()["verification_id"]

    result_response = client.get(f"/verify/{verification_id}")
    assert result_response.status_code == 200
    body = result_response.json()

    assert body["status"] == "completed"
    assert body["label"] == "confirmed"
    assert len(body["evidence"]) >= 1


def test_verify_unknown_wallet_is_unverifiable(client):
    """A claim about a wallet with no matching fixture transfer resolves to 'unverifiable'."""
    submit_response = client.post(
        "/verify",
        json={"claim_text": "Wallet 0x00000000000000000000000000000000000000ff moved funds"},
    )
    verification_id = submit_response.json()["verification_id"]

    result_response = client.get(f"/verify/{verification_id}")
    body = result_response.json()

    assert body["status"] == "completed"
    assert body["label"] == "unverifiable"


def test_unknown_verification_id_returns_404(client):
    """Polling a verification id that was never submitted returns a 404."""
    response = client.get("/verify/999999")
    assert response.status_code == 404
