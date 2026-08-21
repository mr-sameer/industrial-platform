#!/usr/bin/env python3
"""
Module 8A — controlled MCA pilot promotion script. A thin CLI wrapper
around app.services.company_promotion_service.promote_raw_observation_to_company
— the same, unmodified function app/api/v1/acquisition_review.py's
POST /acquisition/observations/{id}/promote route calls. All real
logic (CIN duplicate check, field-profile-driven provenance creation,
the OBSERVED/EXTRACTED-never-VERIFIED rule) lives there, unchanged;
this script only handles argument parsing, per-observation
verification output, and halting on the first failure.

Used to promote the 5 real RawObservation rows collected by the
Module 8A live MCA pilot (job 83870cac-4987-47f9-8776-4f615dd6144f)
one at a time, each independently verified before moving to the next
— preserved here as the record of exactly how that promotion was
performed, and as a reusable tool for any future controlled promotion
of specific observation IDs.

Never calls data.gov.in, never creates an AcquisitionJob, never
touches entity-resolution logic — promotion is a separate, later,
explicit human action over already-collected RawObservation rows.

Usage:
    python scripts/promote_mca_pilot_observations.py --observation-id <uuid> --reviewer-email <email>
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.provenance_record import ProvenanceRecord  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import company_promotion_service  # noqa: E402


async def _resolve_reviewer(
    db: AsyncSession, *, reviewer_id: str | None, reviewer_email: str | None
) -> uuid.UUID:
    if reviewer_id:
        return uuid.UUID(reviewer_id)
    assert reviewer_email, "either --reviewer-id or --reviewer-email is required"
    result = await db.execute(select(User).where(User.email == reviewer_email))
    user = result.scalar_one_or_none()
    if user is None:
        raise SystemExit(f"No user found with email {reviewer_email!r} — create one first.")
    return user.id


async def _promote_one(
    db: AsyncSession, observation_id: uuid.UUID, *, reviewer_id: uuid.UUID
) -> bool:
    """Returns True if this promotion and its verification both succeeded."""
    print(f"=== Promoting observation {observation_id} ===")

    companies_before = (await db.execute(select(func.count()).select_from(Company))).scalar_one()
    try:
        company = await company_promotion_service.promote_raw_observation_to_company(
            db, observation_id, reviewer_id=reviewer_id
        )
    except Exception as exc:  # noqa: BLE001 — must report, never swallow
        print(f"  PROMOTION FAILED: {type(exc).__name__}: {exc}")
        return False
    companies_after = (await db.execute(select(func.count()).select_from(Company))).scalar_one()

    prov_result = await db.execute(
        select(ProvenanceRecord).where(ProvenanceRecord.company_id == company.id)
    )
    prov_records = prov_result.scalars().all()
    statuses = {r.status.value for r in prov_records}
    obs_ids_referenced = {r.raw_observation_id for r in prov_records}

    checks = [
        ("exactly one Company created", companies_after - companies_before == 1),
        ("no 'verified' provenance status", "verified" not in statuses),
        ("all provenance linked only to this observation", obs_ids_referenced == {observation_id}),
        ("at least one provenance record created", len(prov_records) > 0),
    ]
    ok = all(passed for _, passed in checks)

    print(f"  Company ID: {company.id}")
    print(f"  Name:       {company.name}")
    print(f"  CIN:        {company.cin}")
    print(f"  Provenance record count: {len(prov_records)}")
    for label, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {label}")
    print()
    return ok


async def _main(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as db:
        reviewer_id = await _resolve_reviewer(
            db, reviewer_id=args.reviewer_id, reviewer_email=args.reviewer_email
        )
        for raw_id in args.observation_id:
            ok = await _promote_one(db, uuid.UUID(raw_id), reviewer_id=reviewer_id)
            if not ok:
                print(
                    "STOPPING — this observation's promotion/verification failed; "
                    "remaining --observation-id values were not attempted."
                )
                sys.exit(1)
        print(f"All {len(args.observation_id)} observation(s) promoted and verified successfully.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Promote specific RawObservation rows to Company, one at a time, "
        "verifying promotion and provenance invariants after each, halting on the first failure."
    )
    parser.add_argument(
        "--observation-id",
        action="append",
        required=True,
        help="A RawObservation UUID to promote. Repeat for multiple; promoted in the order given.",
    )
    parser.add_argument("--reviewer-id", type=str, default=None, help="Reviewer's user UUID.")
    parser.add_argument(
        "--reviewer-email",
        type=str,
        default=None,
        help="Reviewer's email, looked up to a user ID (alternative to --reviewer-id).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    parsed = _parse_args()
    if not parsed.reviewer_id and not parsed.reviewer_email:
        print("ERROR: one of --reviewer-id or --reviewer-email is required.")
        sys.exit(1)
    asyncio.run(_main(parsed))
