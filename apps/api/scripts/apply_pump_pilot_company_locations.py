#!/usr/bin/env python3
"""
Location-intelligence activation — applies real, sourced company `city`
facts through the newly-extended, sanctioned
data_quality_service.apply_reviewed_field_to_company workflow (see that
function's own docstring for why `state`/`city` are now two more
explicit branches in its closed allowlist, added specifically to close
this gap). Uses ONLY the real, existing, unmodified service-layer
functions the real API routes call (provenance_service,
data_quality_service) — no schema change, no raw SQL, no shortcut
around OBSERVED -> VERIFIED -> APPLY.

Scope, deliberately narrow — exactly the two facts the location-
intelligence pilot's own source review found explicitly stated in a
source already associated with that company:

  Kirloskar Brothers Limited: city = "Pune"
    Source: the same KBL "MONOBLOC PUMPS THREE PHASE" catalogue
    (SourceRegistry already created by
    curate_pump_supplier_coverage_pilot.py) — page 1 letterhead:
    "Registered Pffice: Udyog Bhavan, Tilak Road, Pune-411002... Global
    Headquarters: 'Yamuna', Survey No. 98/(3.7), Baner, Pune-411045."
    Both the registered office and the global headquarters address
    are in Pune — city is unambiguous and explicit.

  KSB Limited: city = "Nashik"
    Source: the same KSB "200+150 mm - Submersible Motor Pumpsets"
    brochure (SourceRegistry already created by the same script) —
    page 4 footer letterhead: "KSB Limited / Standard Pumps Division /
    Plot No. E3 & E4, MIDC Sinnar, Nashik 422 113."

Deliberately NOT applied here (per the location-intelligence pilot's
own findings, restated so a future run of this script doesn't
casually widen scope without a real decision):
  - No `state` fact for either company — "Maharashtra" is not
    literally stated on either letterhead; it would be a geographic
    inference from the city, not a transcription, and the pilot's own
    review chose not to create that fact merely because it's obvious.
  - No location fact for C.R.I. Pumps — its own already-associated
    source (the CRI 2024 catalogue's company_text observation) states
    no address at all, only a toll-free number and website.
  - No location fact for Grundfos Pumps India Private Limited — its
    only already-associated source (the global CR/CRI/CRN data
    booklet) contains no India address; the Chennai address found
    during discovery came from a company-registry directory
    (Zauba/ClearTax), which this pilot's own source-quality ranking
    restricts to identity corroboration, never evidence.

Idempotent: safe to run more than once — each step checks for an
existing VERIFIED-and-applied fact first (Company.city/.state already
matching the target value) and skips if already present, rather than
creating a duplicate ProvenanceRecord or erroring.

Usage:
    cd apps/api && python scripts/apply_pump_pilot_company_locations.py
"""

import asyncio
import hashlib
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.logging import configure_logging  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.provenance_record import EntityType, ExtractionMethod, ProvenanceStatus  # noqa: E402
from app.models.source_registry import CollectionMethod, SourceRegistry  # noqa: E402
from app.models.user import User  # noqa: E402
from app.schemas.provenance import ProvenanceRecordCreate, RawObservationCreate  # noqa: E402
from app.services import data_quality_service, provenance_service  # noqa: E402


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _apply_city_fact(
    db,
    *,
    admin: User,
    company_name: str,
    source_name: str,
    city_value: str,
    page_ref: str,
    transcribed_text: str,
) -> None:
    company_result = await db.execute(select(Company).where(Company.name == company_name))
    company = company_result.scalar_one_or_none()
    if company is None:
        print(f"FATAL: company {company_name!r} not found.")
        return

    if company.city == city_value:
        print(f"  {company_name}: city already = {city_value!r} — skipping (idempotent).")
        return
    if company.city:
        print(
            f"  SKIPPING {company_name}: city already has a different value "
            f"({company.city!r}) — this script never overwrites (no overwrite=True passed)."
        )
        return

    source_result = await db.execute(select(SourceRegistry).where(SourceRegistry.name == source_name))
    source = source_result.scalar_one_or_none()
    if source is None:
        print(f"FATAL: source {source_name!r} not found — expected it to already exist from the pump curation pilot.")
        return

    raw_obs = await provenance_service.create_raw_observation(
        db,
        RawObservationCreate(
            source_id=source.id,
            external_reference=f"{source.base_url}#{page_ref}",
            raw_content={
                "document": source_name,
                "location": page_ref,
                "field": "company.city",
                "transcribed_text": transcribed_text,
            },
            content_hash=_hash(transcribed_text + company_name + "city"),
            collection_method_used=CollectionMethod.MANUAL,
            collected_at=datetime.now(UTC),
        ),
    )
    print(f"  RawObservation (city): {raw_obs.id}")

    record, _conflict = await provenance_service.create_provenance_record(
        db,
        ProvenanceRecordCreate(
            entity_type=EntityType.COMPANY,
            company_id=company.id,
            field_name="city",
            raw_observation_id=raw_obs.id,
            value_observed=city_value,
            extraction_method=ExtractionMethod.MANUAL,
            confidence=0.9,
            status=ProvenanceStatus.OBSERVED,
        ),
    )
    print(f"  ProvenanceRecord (city={city_value!r}): {record.id}, status={record.status.value}")

    record = await provenance_service.verify_provenance_record(db, record, verified_by=admin.id)
    print(f"  Verified: {record.status.value} by {record.verified_by}")

    company = await data_quality_service.apply_reviewed_field_to_company(
        db, record, company, reviewer_id=admin.id, overwrite=False
    )
    print(f"  Applied -> {company_name}.city = {company.city!r}")


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        admin_result = await db.execute(
            select(User).where(User.email == "curation-admin@forgex.internal")
        )
        admin = admin_result.scalar_one_or_none()
        if admin is None:
            print("FATAL: curation-admin@forgex.internal not found — run the pump curation pilot first.")
            return
        print(f"Reviewer/admin user: {admin.id} ({admin.email})\n")

        print("Kirloskar Brothers Limited:")
        await _apply_city_fact(
            db,
            admin=admin,
            company_name="Kirloskar Brothers Limited",
            source_name="Kirloskar Brothers Limited — MONOBLOC PUMPS THREE PHASE catalogue (SP-10-2017-01)",
            city_value="Pune",
            page_ref="page=1 (letterhead)",
            transcribed_text=(
                "Page 1 letterhead: 'Registered Pffice: Udyog Bhavan, Tilak Road, "
                "Pune-411002. Tel: +91(20)24440770, Global Headquarters: \"Yamuna\", "
                "Survey No. 98/(3.7), Baner, Pune-411045. Tel: +91(20)27214444, "
                "Email: marketing@kbl.co.in, Website: www.kirloskarpumps.com, "
                "CIN No.: L29113PN1920PLC000670.' Both the registered office and the "
                "global headquarters address are in Pune."
            ),
        )

        print("\nKSB Limited:")
        await _apply_city_fact(
            db,
            admin=admin,
            company_name="KSB Limited",
            source_name="KSB Limited — 200+150 mm Submersible Motor Pumpsets brochure (3402.025)",
            city_value="Nashik",
            page_ref="page=4 (letterhead)",
            transcribed_text=(
                "Page 4 footer letterhead: 'KSB Limited / Standard Pumps Division / "
                "Plot No. E3 & E4, MIDC Sinnar, Nashik 422 113. / Tel.: +91-2551-230252 "
                "/ 53, 229700 www.ksbindia.co.in.' Same page as the Selection Table this "
                "pilot's Motor Power evidence for 373/1A and 383/2A was sourced from."
            ),
        )

        print("\n" + "=" * 70)
        print("DONE")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
