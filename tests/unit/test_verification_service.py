"""Step 7 of PLAN.md — composes the database layer with a stand-in agent.

Confirms persistence (Claim -> Evidence -> Verdict) works end to end,
without depending on the real orchestration loop (already covered by
test_orchestrator.py) or a real LLM.
"""

from sqlmodel import select

from app.agent.orchestrator import AgentVerdict, EvidenceRecord
from app.models import Claim, ClaimStatus, Evidence, Verdict, VerdictLabel
from app.services.verification import create_claim, run_verification
from app.tools.base import ToolResult


class FakeAgent:
    """Returns a fixed, pre-built verdict instead of running the real orchestration loop."""

    def __init__(self, verdict: AgentVerdict) -> None:
        """Store the verdict `verify` should return."""
        self._verdict = verdict

    def verify(self, claim_text: str) -> AgentVerdict:
        """Ignore `claim_text` and return the stored verdict."""
        return self._verdict


def test_run_verification_persists_claim_evidence_and_verdict(db_session):
    """run_verification writes a matching Claim, Evidence, and Verdict row."""
    fake_verdict = AgentVerdict(
        label=VerdictLabel.confirmed,
        confidence=0.9,
        explanation="Matched on-chain transfer.",
        evidence=[
            EvidenceRecord(
                tool_name="query_token_transfers",
                result=ToolResult(success=True, data={"count": 1}, source_url="https://etherscan.io/tx/0xabc"),
            )
        ],
        steps_used=2,
    )
    agent = FakeAgent(fake_verdict)

    claim = create_claim(db_session, "Wallet X received $50,000")
    db_session.commit()

    outcome = run_verification(db_session, claim.id, agent)
    db_session.commit()

    assert outcome.claim_id is not None

    verdict_row = db_session.exec(
        select(Verdict).where(Verdict.claim_id == outcome.claim_id)
    ).first()
    assert verdict_row is not None
    assert verdict_row.label == VerdictLabel.confirmed

    evidence_rows = db_session.exec(
        select(Evidence).where(Evidence.claim_id == outcome.claim_id)
    ).all()
    assert len(evidence_rows) == 1

    persisted_claim = db_session.get(Claim, outcome.claim_id)
    assert persisted_claim.status == ClaimStatus.completed


def test_run_verification_raises_for_unknown_claim_id(db_session):
    """Passing a claim id with no matching row raises a ValueError naming that id."""
    agent = FakeAgent(
        AgentVerdict(label=VerdictLabel.unverifiable, confidence=0.0, explanation="n/a")
    )
    try:
        run_verification(db_session, 999999, agent)
        raise AssertionError("expected a ValueError for a nonexistent claim id")
    except ValueError as exc:
        assert "999999" in str(exc)
