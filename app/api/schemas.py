"""Request/response models for the HTTP API.

Kept separate from app/models.py (the database models) on purpose: the
shape you want to expose over HTTP is not always the same as the shape you
want to store. Right now they're similar, but this separation means you can
change your database schema without silently changing your public API
contract, and vice versa.
"""


from pydantic import BaseModel, Field

from app.models import ClaimStatus, VerdictLabel


class VerifyRequest(BaseModel):
    """Body of `POST /verify`."""

    claim_text: str = Field(..., min_length=1, max_length=2000)


class VerifyAcceptedResponse(BaseModel):
    """Response to `POST /verify`: an id to poll for the result."""

    verification_id: int
    status: ClaimStatus


class EvidenceResponse(BaseModel):
    """One piece of evidence backing a verdict."""

    source: str
    data: dict
    source_url: str | None = None


class VerificationResultResponse(BaseModel):
    """Response to `GET /verify/{id}`."""

    verification_id: int
    status: ClaimStatus
    claim_text: str
    label: VerdictLabel | None = None
    confidence: float | None = None
    explanation: str | None = None
    evidence: list[EvidenceResponse] = Field(default_factory=list)
