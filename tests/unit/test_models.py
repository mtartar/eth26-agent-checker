"""Step 2 of PLAN.md — pure-Python checks on the model definitions.

No database involved yet.
"""

import pytest

from app.models import Claim, ClaimStatus, Evidence, EvidenceSource, Verdict, VerdictLabel


def test_claim_defaults_to_pending():
    """A newly constructed, unpersisted Claim defaults to 'pending' status."""
    claim = Claim(claim_text="Wallet X received $50,000 in USDC")
    assert claim.status == ClaimStatus.pending
    assert claim.id is None  # not yet persisted


def test_evidence_requires_claim_id():
    """An Evidence row keeps the source it was constructed with."""
    evidence = Evidence(
        claim_id=1, source=EvidenceSource.token_api, data_json='{"amount": 50000}'
    )
    assert evidence.source == EvidenceSource.token_api


def test_verdict_confidence_must_be_between_0_and_1():
    """Constructing a Verdict with a confidence outside [0, 1] raises a ValueError."""
    with pytest.raises(ValueError, match="confidence"):
        Verdict(claim_id=1, label=VerdictLabel.confirmed, confidence=1.5, explanation="x")

    # A valid confidence should not raise.
    Verdict(claim_id=1, label=VerdictLabel.confirmed, confidence=0.9, explanation="x")
