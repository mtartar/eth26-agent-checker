"""Database models.

Three tables, deliberately kept separate rather than one big "Verification"
blob:

- `Claim`   — the thing the user asked us to check, as submitted.
- `Evidence` — one row per fact gathered from an external source while
  checking the claim. A single claim can (and usually should) be checked
  against multiple pieces of evidence from different sources.
- `Verdict` — the final synthesized answer, referencing the claim and
  produced after evidence has been gathered.

Splitting these matters in practice: it lets you later ask questions like
"which source disagrees with our verdicts most often" or "show me every
piece of evidence we've ever pulled from the Token API" without parsing
verdict text — the data is structured from the start. It also means the raw
evidence trail survives even if you later change how verdicts are computed.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClaimStatus(str, Enum):
    """Lifecycle of a submitted claim, from submission to a final verdict."""

    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class VerdictLabel(str, Enum):
    """The agent's final answer for a claim."""

    confirmed = "confirmed"
    partially_true = "partially_true"
    false = "false"
    unverifiable = "unverifiable"


class EvidenceSource(str, Enum):
    """Which external data source a piece of evidence came from."""

    token_api = "token_api"
    subgraph = "subgraph"
    knowledge_graph = "knowledge_graph"


class Claim(SQLModel, table=True):
    """A claim submitted for verification."""

    id: int | None = Field(default=None, primary_key=True)
    claim_text: str
    status: ClaimStatus = Field(default=ClaimStatus.pending)
    created_at: datetime = Field(default_factory=_utcnow)


class Evidence(SQLModel, table=True):
    """One fact gathered from an external source while checking a claim."""

    id: int | None = Field(default=None, primary_key=True)
    claim_id: int = Field(foreign_key="claim.id")
    source: EvidenceSource
    # Free-form but always JSON-serializable — e.g. a tx hash + explorer URL
    # for on-chain evidence, or an entity ID + Space ID for knowledge-graph
    # evidence. Kept as a string (JSON-encoded) so this table doesn't need to
    # change shape every time a new source is added.
    data_json: str
    retrieved_at: datetime = Field(default_factory=_utcnow)


class Verdict(SQLModel, table=True):
    """The final synthesized answer for a claim."""

    id: int | None = Field(default=None, primary_key=True)
    claim_id: int = Field(foreign_key="claim.id")
    label: VerdictLabel
    confidence: float = Field(ge=0.0, le=1.0)
    explanation: str
    created_at: datetime = Field(default_factory=_utcnow)
