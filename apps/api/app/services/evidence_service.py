"""
Evidence service — Module 8B. Bridges website/manual-entry evidence
about a company's manufacturing capabilities to the existing Module 5F
knowledge graph. No new persistence, no new architecture: every
capability claim becomes a Capability (get-or-create,
graph_service.create_capability, already idempotent on name) plus a
GraphRelationship (graph_service.create_relationship, already
idempotent on the (company_subject_id, relationship_type, object_type,
object_id) triple), created at status=OBSERVED and linked to the raw
observation it came from — never auto-verified. Only a later, separate,
explicit graph_service.verify_relationship call (unchanged) can ever
move a claim to VERIFIED.

Deliberately NOT Company.capabilities (Module 3B's plain string array
column) — that is a distinct, currently-unsynced concept from this
module's own Capability/GraphRelationship graph entities (see this
module's Module 8B review for the full reasoning). This service only
ever writes to the capabilities/graph_relationships tables, never to
Company.

No capability-name normalization is performed here, by design — see
Module 8B's architectural review: at pilot scale, a reviewer is
expected to check GET /graph/capabilities first and reuse an existing
name; semantic deduplication stays a human review-step concern, not
new code.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.graph_relationship import GraphEntityType, GraphRelationship, RelationshipType
from app.models.provenance_record import ProvenanceStatus
from app.schemas.graph import CapabilityCreate, GraphRelationshipCreate
from app.services import audit_service, graph_service, provenance_service

__all__ = ["RawObservationNotFoundForEvidenceError", "attach_capability_evidence"]


class RawObservationNotFoundForEvidenceError(Exception):
    """Raised when the raw observation backing this evidence claim does
    not exist. Mirrors provenance_service.create_provenance_record's
    own existence check — graph_service.create_relationship does not
    validate raw_observation_id itself (unlike company_subject_id), so
    this function checks explicitly rather than relying on a bare FK
    failure."""


async def attach_capability_evidence(
    db: AsyncSession,
    raw_observation_id: uuid.UUID,
    company_id: uuid.UUID,
    capability_names: list[str],
    reviewer_id: uuid.UUID,
) -> list[GraphRelationship]:
    """
    For each name in capability_names: get-or-create the Capability,
    then create (or return the existing) OBSERVED GraphRelationship
    linking company_id -> that Capability, tagged with
    raw_observation_id. A repeated name, or a repeated call with the
    same (company, capability) pair, is a no-op — preserves
    graph_service.create_relationship's own idempotency, nothing here
    duplicates or re-implements it.

    reviewer_id is not written onto GraphRelationship (that model has
    no "entered_by" column, and creation is not itself a review action
    — only graph_service.verify_relationship, a separate later call,
    records a real reviewer via verified_by) — it is used only to
    attribute the audit log entry below, matching every other write
    path in this codebase.
    """
    observation = await provenance_service.get_raw_observation(db, raw_observation_id)
    if observation is None:
        raise RawObservationNotFoundForEvidenceError(str(raw_observation_id))

    relationships: list[GraphRelationship] = []
    for name in capability_names:
        capability = await graph_service.create_capability(db, CapabilityCreate(name=name))
        relationship = await graph_service.create_relationship(
            db,
            GraphRelationshipCreate(
                company_subject_id=company_id,
                relationship_type=RelationshipType.HAS_CAPABILITY,
                object_type=GraphEntityType.CAPABILITY,
                capability_object_id=capability.id,
                status=ProvenanceStatus.OBSERVED,
                raw_observation_id=raw_observation_id,
            ),
        )
        relationships.append(relationship)

    await audit_service.log_event(
        db,
        "capability_evidence_attached",
        user_id=str(reviewer_id),
        metadata={
            "raw_observation_id": str(raw_observation_id),
            "company_id": str(company_id),
            "capability_names": capability_names,
            "relationship_ids": [str(r.id) for r in relationships],
        },
    )
    return relationships
