"""Step 3 of PLAN.md — confirms models and the database layer agree.

Does a real insert + read round-trip against a temporary SQLite database.
"""

from app.models import Claim, ClaimStatus


def test_insert_and_read_claim(db_session):
    """A claim inserted and re-fetched by id round-trips with a default 'pending' status."""
    claim = Claim(claim_text="Wallet X received $50,000 in USDC")
    db_session.add(claim)
    db_session.commit()
    db_session.refresh(claim)

    assert claim.id is not None

    fetched = db_session.get(Claim, claim.id)
    assert fetched is not None
    assert fetched.claim_text == "Wallet X received $50,000 in USDC"
    assert fetched.status == ClaimStatus.pending
