"""HTTP endpoints.

Verification is not instant — it can involve several LLM round-trips and
external API calls — so this deliberately does NOT block the request until
it's done. `POST /verify` returns immediately with a 202 Accepted and an id;
`GET /verify/{id}` is polled until the status is "completed" or "failed".

For a real production deployment under real load, replace the
`BackgroundTasks` call below with a proper job queue (Celery, RQ, or a cloud
queue) — see PLAN.md's "suggested next milestones". `BackgroundTasks` is
fine for getting the request/response contract right first, but it runs
in-process and won't survive an API restart or scale independently of the
web server.
"""

import json

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlmodel import select

from app.agent.orchestrator import VerificationAgent
from app.api.schemas import (
    EvidenceResponse,
    VerificationResultResponse,
    VerifyAcceptedResponse,
    VerifyRequest,
)
from app.config import get_settings
from app.database import get_session
from app.models import Claim, ClaimStatus, Evidence, Verdict
from app.services.verification import build_default_tools, create_claim, run_verification

router = APIRouter()


def _build_agent() -> VerificationAgent:
    settings = get_settings()
    tools = build_default_tools(settings)

    if settings.is_live:
        from app.agent.anthropic_client import AnthropicClient

        client = AnthropicClient(settings)
    else:
        # In fixture mode we still exercise the real orchestration loop, but
        # against a scripted client so the whole HTTP path is testable
        # without an API key. See app/agent/fixture_client.py.
        from app.agent.fixture_client import FixtureAnthropicClient

        client = FixtureAnthropicClient()

    return VerificationAgent(settings=settings, tools=tools, anthropic_client=client)


def _process_claim(claim_id: int) -> None:
    """Run verification for a claim in the background.

    Runs in its own fresh database session — the request handler's session
    is already closed by the time this runs.
    `run_verification` fetches the claim by id itself and updates that same
    row, so the id returned to the client in `submit_claim` is guaranteed to
    be the one that eventually holds the verdict.
    """
    with get_session() as session:
        agent = _build_agent()
        try:
            run_verification(session, claim_id, agent)
        except Exception:  # noqa: BLE001 - already logged/marked failed inside
            # run_verification; this catch only stops the background task
            # itself from crashing (FastAPI would otherwise log a bare
            # traceback with no further handling).
            pass


@router.post("/verify", response_model=VerifyAcceptedResponse, status_code=202)
def submit_claim(request: VerifyRequest, background_tasks: BackgroundTasks):
    """Persist the claim and schedule verification, returning immediately."""
    with get_session() as session:
        claim = create_claim(session, request.claim_text)
        claim_id = claim.id
        assert claim_id is not None  # populated by create_claim's session.flush()

    background_tasks.add_task(_process_claim, claim_id)
    return VerifyAcceptedResponse(verification_id=claim_id, status=ClaimStatus.pending)


@router.get("/verify/{verification_id}", response_model=VerificationResultResponse)
def get_verification(verification_id: int):
    """Return the current status, and verdict/evidence once completed, for a claim."""
    with get_session() as session:
        claim = session.get(Claim, verification_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="verification not found")

        verdict = session.exec(
            select(Verdict).where(Verdict.claim_id == verification_id)
        ).first()
        evidence_rows = session.exec(
            select(Evidence).where(Evidence.claim_id == verification_id)
        ).all()

        evidence = [
            EvidenceResponse(
                source=row.source.value,
                data=json.loads(row.data_json).get("data", {}),
                source_url=json.loads(row.data_json).get("source_url"),
            )
            for row in evidence_rows
        ]

        return VerificationResultResponse(
            verification_id=verification_id,
            status=claim.status,
            claim_text=claim.claim_text,
            label=verdict.label if verdict else None,
            confidence=verdict.confidence if verdict else None,
            explanation=verdict.explanation if verdict else None,
            evidence=evidence,
        )
