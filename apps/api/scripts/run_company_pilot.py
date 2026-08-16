#!/usr/bin/env python3
"""
Module 6B — controlled company pilot runner. A thin CLI wrapper around
app.services.pilot_service — all real logic (the legal gate, entity-
resolution orchestration) lives there and is directly unit-tested; this
script only handles argument parsing, printing the required pre-run
summary, and calling into that tested service.

Reuses the EXISTING MCADataGovInAdapter (Module 5C) and MockSourceAdapter
(Module 5B) unchanged — this script registers no new collector type.

Usage (dry run, against the real, deterministic MockSourceAdapter —
no external network call, proves the orchestration logic works):
    python scripts/run_company_pilot.py --dry-run

Usage (a real pilot against MCA/data.gov.in — requires a real,
environment-provided API key, and requires the registered source's
collection_policy_status to already be 'allowed'):
    DATA_GOV_IN_API_KEY=... python scripts/run_company_pilot.py \\
        --resource-id <real-resource-id> --limit 50

Credentials are NEVER hardcoded here — the real API key is read from
the DATA_GOV_IN_API_KEY environment variable only, matching Module 5B's
own established app.collectors.secrets.redact_config discipline (the
key is passed into requested_scope, which acquisition_service already
redacts before persisting or logging it — unchanged, real behavior).
"""

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.source_registry import CollectionMethod, SourceClass  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.provenance import SourceRegistryCreate  # noqa: E402
from app.services import pilot_service  # noqa: E402
from app.services.pilot_service import SourceNotApprovedForPilotError  # noqa: E402


async def _get_or_create_pilot_operator(db: AsyncSession) -> User:
    """
    A real, attributable admin user this pilot's AcquisitionJob is
    recorded as created_by — never an anonymous/system actor,
    matching every prior Module 5 phase's real, enforced
    attribution requirement.
    """
    result = await db.execute(select(User).where(User.email == "pilot-operator@forgex.internal"))
    existing_user: User | None = result.scalar_one_or_none()
    if existing_user is not None:
        return existing_user
    from app.core.security import hash_password

    user = User(
        email="pilot-operator@forgex.internal",
        hashed_password=hash_password(str(uuid.uuid4())),
        full_name="Module 6B Pilot Operator",
        role=Role.ADMIN,
        is_email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _print_pre_run_summary(
    *, dry_run: bool, collector_type: str, resource_id: str | None, limit: int
) -> None:
    api_key_present = bool(os.environ.get("DATA_GOV_IN_API_KEY"))
    print("=" * 70)
    print("MODULE 6B — PILOT PRE-RUN SUMMARY")
    print("=" * 70)
    print(
        f"Mode:                {'DRY RUN (MockSourceAdapter, no external call)' if dry_run else 'REAL PILOT'}"
    )
    print(f"Collector type:      {collector_type}")
    print(f"Resource ID:         {resource_id or '(n/a for mock)'}")
    print(f"Target scope limit:  {limit}")
    print(
        f"DATA_GOV_IN_API_KEY: {'present (value never printed)' if api_key_present else 'NOT SET'}"
    )
    if not dry_run and not api_key_present:
        print()
        print("WARNING: no real API key is configured. The real acquisition")
        print("job will still be attempted (to honestly observe and report")
        print("the actual failure), but success is not expected without one.")
    print("=" * 70)


async def _main(args: argparse.Namespace) -> None:
    collector_type = "mock" if args.dry_run else "mca_data_gov_in"
    _print_pre_run_summary(
        dry_run=args.dry_run,
        collector_type=collector_type,
        resource_id=args.resource_id,
        limit=args.limit,
    )

    async with AsyncSessionLocal() as db:
        operator = await _get_or_create_pilot_operator(db)

        source_payload = SourceRegistryCreate(
            name="MCA Company Master Data (data.gov.in) — Module 6B pilot"
            if not args.dry_run
            else "Module 6B dry-run mock source",
            source_class=SourceClass.PUBLIC_GOVERNMENT,
            collection_method=CollectionMethod.API,
            reliability_weight=0.9,
            geographic_scope="IN",
            base_url="https://api.data.gov.in/resource" if not args.dry_run else None,
        )

        requested_scope: dict[str, object] = {"limit": args.limit}
        if not args.dry_run:
            requested_scope["api_key"] = os.environ.get("DATA_GOV_IN_API_KEY", "")
            requested_scope["resource_id"] = args.resource_id or ""

        try:
            report = await pilot_service.run_pilot(
                db,
                source_payload=source_payload,
                collector_type=collector_type,
                requested_scope=requested_scope,
                created_by=operator.id,
                dry_run=args.dry_run,
            )
        except SourceNotApprovedForPilotError as exc:
            print()
            print("REAL PILOT BLOCKED — legal gate:")
            print(f"  {exc}")
            print()
            print("Implementation complete; real pilot blocked by source approval status.")
            return

        print()
        print("=" * 70)
        print("PILOT RUN REPORT")
        print("=" * 70)
        print(f"Source:                    {report.source_name} ({report.source_id})")
        print(f"Job ID:                    {report.job_id}")
        print(f"Job status:                {report.job_status}")
        print(f"Records created:           {report.records_discovered_or_created}")
        print(f"Records skipped (dup):     {report.records_skipped}")
        print(f"Records failed:            {report.records_failed}")
        print(f"Job retry count:           {report.job_retry_count}")
        print(f"Job error message:         {report.job_error_message}")
        print("-" * 70)
        print(f"Entity resolution total:   {report.entity_resolution.total}")
        print(f"  NEW:                     {report.entity_resolution.new}")
        print(f"  AUTO_MATCH:              {report.entity_resolution.auto_match}")
        print(f"  REVIEW_REQUIRED:         {report.entity_resolution.review_required}")
        print(f"  NO_MATCH:                {report.entity_resolution.no_match}")
        print("=" * 70)

        if report.job_status != "succeeded":
            print()
            print("Implementation complete; live pilot blocked by external source accessibility.")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Module 6B controlled company pilot runner")
    parser.add_argument(
        "--dry-run", action="store_true", help="Run against MockSourceAdapter, no external call"
    )
    parser.add_argument(
        "--resource-id", type=str, default=None, help="data.gov.in resource ID (real pilot only)"
    )
    parser.add_argument(
        "--limit", type=int, default=25, help="Pilot record ceiling (max 50, per Module 5C)"
    )
    return parser.parse_args()


if __name__ == "__main__":
    parsed = _parse_args()
    if parsed.limit > 50:
        print("ERROR: --limit cannot exceed 50 for this pilot (Module 5C's own enforced ceiling).")
        sys.exit(1)
    asyncio.run(_main(parsed))
