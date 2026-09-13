"""The verification pipeline.

This is the one place that composes everything else: it creates a `Claim`
row, builds the tools and agent, runs verification, and persists the result
as `Evidence` and `Verdict` rows. Keeping this composition in one function
(rather than scattering it across the API layer) means it can be reused
identically from an HTTP endpoint, a CLI script, or a background worker —
none of which should have to know how the agent is constructed.
"""

import json
from dataclasses import dataclass

from sqlmodel import Session

from app.agent.orchestrator import AgentVerdict, VerificationAgent
from app.config import Settings
from app.models import Claim, ClaimStatus, Evidence, Verdict
from app.tools.base import Tool


@dataclass
class VerificationOutcome:
    """The claim a verification run applied to and the verdict it produced."""

    claim_id: int
    verdict: AgentVerdict


def build_default_tools(settings: Settings) -> list[Tool]:
    """Construct the standard tool set.

    Factored out so tests can pass a different (e.g. empty, or extra) tool
    list without touching this module.
    """
    from app.tools.knowledge_graph import KnowledgeGraphTool
    from app.tools.subgraph_mcp import SubgraphQueryTool
    from app.tools.token_api import TokenApiTool

    return [
        TokenApiTool(settings),
        SubgraphQueryTool(settings),
        KnowledgeGraphTool(settings),
    ]


def create_claim(session: Session, claim_text: str) -> Claim:
    """Create and flush a pending Claim row, returning it with its id populated.

    Split out from `run_verification` so the API layer can create the row
    and hand its id back to the client *immediately*, before the
    (potentially slow) verification work runs in the background — see
    app/api/routes.py.
    """
    claim = Claim(claim_text=claim_text, status=ClaimStatus.pending)
    session.add(claim)
    session.flush()  # populates claim.id without committing yet
    return claim


def run_verification(
    session: Session,
    claim_id: int,
    agent: VerificationAgent,
) -> VerificationOutcome:
    """Run verification for an *existing* claim and persist evidence + a verdict.

    The claim (created via `create_claim`) is identified by `claim_id`.

    Deliberately takes an id, not a Claim object: this function is typically
    called from a background task holding a fresh database session, and a
    Claim object loaded in a different session should not be reused across
    sessions. Takes an already-constructed `agent` so this function doesn't
    need to know about API keys, settings, or which Anthropic client to use —
    that's the caller's job (see app/api/routes.py and tests).
    """
    claim = session.get(Claim, claim_id)
    if claim is None:
        raise ValueError(f"no claim found with id {claim_id}")

    claim.status = ClaimStatus.in_progress
    session.add(claim)
    session.flush()

    try:
        agent_verdict = agent.verify(claim.claim_text)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any agent
        # failure should mark the claim as failed rather than crash the caller
        claim.status = ClaimStatus.failed
        session.add(claim)
        raise RuntimeError(f"verification failed for claim {claim_id}: {exc}") from exc

    for record in agent_verdict.evidence:
        session.add(
            Evidence(
                claim_id=claim_id,
                source=_infer_source(record.tool_name),
                data_json=json.dumps(
                    {
                        "success": record.result.success,
                        "data": record.result.data,
                        "error": record.result.error,
                        "source_url": record.result.source_url,
                    }
                ),
            )
        )

    verdict = Verdict(
        claim_id=claim_id,
        label=agent_verdict.label,
        confidence=agent_verdict.confidence,
        explanation=agent_verdict.explanation,
    )
    session.add(verdict)

    claim.status = ClaimStatus.completed
    session.add(claim)

    return VerificationOutcome(claim_id=claim_id, verdict=agent_verdict)


def _infer_source(tool_name: str):
    from app.models import EvidenceSource

    mapping = {
        "query_token_transfers": EvidenceSource.token_api,
        "query_subgraph": EvidenceSource.subgraph,
        "query_knowledge_graph": EvidenceSource.knowledge_graph,
    }
    return mapping.get(tool_name, EvidenceSource.subgraph)
