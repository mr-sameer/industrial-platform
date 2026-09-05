#!/usr/bin/env python3
"""
Pump supplier/product coverage expansion — Module 7A/7B follow-on pilot.
Same spirit and same real, unmodified service-layer calls as
scripts/curate_cri_msp_2e_22_pilot.py (provenance_service,
product_service, product_attribute_evidence_service, company_service,
offering_service): no schema change, no migration, no new model, no
shortcut around VERIFY/APPLY, no change to requirement_matching_service.

Goal (Requirement Intelligence coverage milestone): the "Centrifugal
Pumps" category had exactly one product (CRI MSP-2E/22) before this
script. This adds real, evidence-backed products from three more real
manufacturers, each sourced from that manufacturer's own official
catalogue/datasheet — never a directory listing, never a family range
turned into a fabricated single value.

Every product below was screened against a source that gives a
genuine, model-specific, single-value rating for at least one
supported specification. Two real candidates researched for this same
milestone (Ruhrpumpen India, Flowmore Limited) are DELIBERATELY NOT
curated here — their public literature is family-level "coverage
chart" range data only (explicitly marked "approximate... for
tentative selection" in Flowmore's own brochures), with no
individual-model table anywhere found. Turning either into a "product"
would mean fabricating a single value from a curve/range, which this
script's own precedent (CRI's Flow Rate/Head, deliberately left
unsourced) exists specifically to refuse to do. See the curation
session's own report for the full discovery/review-candidate list.

Companies and real sources curated in this run:

  1. Kirloskar Brothers Limited (KBL) — "MONOBLOC PUMPS THREE PHASE"
     catalogue (doc code SP-10-2017-01). Real letterhead confirmed:
     registered office Udyog Bhavan, Tilak Road, Pune-411002; CIN
     L29113PN1920PLC000670; www.kirloskarpumps.com. Fetched via a
     distributor mirror (kirloskarpumps.com itself blocks automated
     fetches with a bot-protection challenge) — the DOCUMENT's own
     letterhead/CIN, not the hosting domain, is what establishes this
     as KBL's genuine official catalogue.
       - KDS-515+: Motor Power 3.7 kW (page 2, "PERFORMANCE CHART FOR
         'KDS+ / KDS++ / GMC' SERIES" table, row 19).
       - KS-1022+: Motor Power 7.5 kW (page 1, "PERFORMANCE CHART FOR
         'KS+' SERIES" table, row 8).
     Pump Type for both = "Monobloc Pump" — the catalogue's own cover
     title ("KIRLOSKAR BROTHERS LIMITED / MONOBLOC PUMPS / THREE
     PHASE"), not an inferred category.
     Flow Rate / Head NOT sourced: every performance chart in this
     catalogue gives a multi-point discharge-vs-head CURVE per model,
     never one rated duty point — same "curve, not one rated figure"
     situation as CRI's own Head/Flow Rate, and left absent for the
     same reason.

  2. KSB Limited — "200+150 mm - Submersible Motor Pumpsets" brochure
     (doc code 3402.025, ksbindia.in/pdf/Submersible-Pumps.pdf, page
     4). Real letterhead confirmed: KSB Limited, Standard Pumps
     Division, Plot No. E3 & E4, MIDC Sinnar, Nashik 422 113;
     www.ksbindia.co.in.
       - KSB 373/1A: Motor Power 7.50 kW ("BPHA / UMA I 150" bracket,
         row "373/1A").
       - KSB 383/2A: Motor Power 15.00 kW ("BPH / UMA H 150" bracket,
         row "383/2A").
     Pump Type for both = "Submersible Motor Pumpset" — this document's
     own page title, and the identical canonical string
     PUMP_TYPE_PHRASE_TO_CANONICAL in apps/web/src/lib/requirement.ts
     already maps "submersible"-family buyer phrases onto.
     Flow Rate / Head NOT sourced: the Selection Table's "Discharge
     (m3/hr.)" columns give head at 10 different flow points per pump
     — a curve, not one rated figure. Same discipline as above.

  3. Grundfos Pumps India Private Limited — "CR, CRI, CRN 50 Hz IEC /
     Vertical multistage centrifugal pumps / Data booklet"
     (api.grundfos.com/literature/Grundfosliterature-6014742.pdf).
     Company identity (India entity, CIN U29309TN1998PTC040102,
     registered office Chennai) corroborated via public company-registry
     aggregators (Zauba/ClearTax/Tofler mirroring the same MCA filing) —
     used only for identity corroboration, never as product-attribute
     evidence, per this pilot's own source-quality ranking.
       - CR 15-2: Motor Power 2.2 kW (page 49, "Dimensions and weights"
         table, row "CR 15-2", column "Motor P2 [kW]").
       - CR 15-6: Motor Power 5.5 kW (same table, row "CR 15-6").
     Pump Type for both = "Vertical Multistage Centrifugal Pump" — page
     3's own Introduction text ("CR pumps are vertical, multistage
     centrifugal pumps"), which is also the exact, real, already-VERIFIED
     canonical value CRI's MSP-2E/22 uses — independent corroboration
     from a second real manufacturer that this is the correct industry
     term for this design, not a coincidence of this pilot's own naming.
     Flow Rate / Head NOT sourced: page 48/50's performance curves plot
     H against Q continuously per stage-count variant (CR 15-1 through
     CR 15-17) — a curve, never one rated duty point.

Usage:
    cd apps/api && python scripts/curate_pump_supplier_coverage_pilot.py
"""

import asyncio
import hashlib
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.company import Company  # noqa: E402
from app.models.offering import Offering, OfferingRole  # noqa: E402
from app.models.product import Product, ProductStatus  # noqa: E402
from app.models.product_attribute import ProductAttribute  # noqa: E402
from app.models.product_category import ProductCategory  # noqa: E402
from app.models.product_specification import ProductSpecification  # noqa: E402
from app.models.provenance_record import ExtractionMethod, ProvenanceStatus  # noqa: E402
from app.models.source_registry import CollectionMethod, SourceClass  # noqa: E402
from app.models.user import Role, User  # noqa: E402
from app.schemas.company import CompanyCreate  # noqa: E402
from app.schemas.product import OfferingCreate, ProductCreate, ProductUpdate  # noqa: E402
from app.schemas.product_attribute_evidence import ProductAttributeEvidenceCreate  # noqa: E402
from app.schemas.provenance import RawObservationCreate, SourceRegistryCreate  # noqa: E402
from app.services import (  # noqa: E402
    company_service,
    offering_service,
    product_attribute_evidence_service,
    product_service,
    provenance_service,
)

logger = get_logger(__name__)

CENTRIFUGAL_PUMPS_CATEGORY_NAME = "Centrifugal Pumps"


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _get_or_create_reviewer(db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.email == "curation-admin@forgex.internal")
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    user = User(
        email="curation-admin@forgex.internal",
        hashed_password=hash_password(str(uuid.uuid4())),
        full_name="ForgeX Curation Pilot Admin",
        role=Role.ADMIN,
        is_active=True,
        is_email_verified=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _get_or_create_company(
    db: AsyncSession, name: str, website: str, country: str
) -> Company:
    result = await db.execute(select(Company).where(Company.name == name))
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing
    return await company_service.create_company(
        db,
        # created_by is the reviewer/admin performing this curation run —
        # mirrors curate_cri_msp_2e_22_pilot.py's own admin-authored
        # Company row exactly (no anonymous-submission path exists for
        # curated companies, same as that script).
        (await _get_or_create_reviewer(db)).id,
        CompanyCreate(name=name, legal_name=name, website=website, country=country),
    )


async def _curate_product(
    db: AsyncSession,
    admin: User,
    *,
    company: Company,
    category: ProductCategory,
    specs_by_name: dict[str, ProductSpecification],
    product_name: str,
    product_family: str | None,
    source: object,
    pump_type_value: str,
    pump_type_page_ref: str,
    pump_type_note: str,
    motor_power_kw: str,
    motor_power_page_ref: str,
    motor_power_note: str,
) -> Product:
    """
    One product, curated end to end through the real evidence workflow
    (create -> evidence -> verify -> apply -> publish -> offering) —
    factored out because this run repeats the identical sequence 6
    times (2 products x 3 companies), and the sequence itself must stay
    byte-for-byte the same real service calls
    curate_cri_msp_2e_22_pilot.py already used, not a shortcut version.
    Idempotent: skips creation steps for anything that already exists
    by name/(product, specification) pair.
    """
    pump_type_spec = specs_by_name["Pump Type"]
    motor_power_spec = specs_by_name["Motor Power"]

    product_result = await db.execute(select(Product).where(Product.name == product_name))
    product = product_result.scalar_one_or_none()
    if product is None:
        product = await product_service.create_product(
            db,
            ProductCreate(
                name=product_name,
                description=None,
                product_family=product_family,
                category_id=category.id,
                industry=None,
                attributes=[],
            ),
        )
    print(f"  Product: {product.id} ({product.name}), status={product.status.value}")

    # RawObservations — one per real source location, verbatim transcription.
    pump_type_text = (
        f"{source.name}. {pump_type_page_ref}. {pump_type_note}"
    )
    raw_obs_pump_type = await provenance_service.create_raw_observation(
        db,
        RawObservationCreate(
            source_id=source.id,
            external_reference=f"{source.base_url}#{pump_type_page_ref}",
            raw_content={
                "document": source.name,
                "location": pump_type_page_ref,
                "transcribed_text": pump_type_text,
            },
            content_hash=_hash(pump_type_text + product_name + "pump_type"),
            collection_method_used=CollectionMethod.MANUAL,
            collected_at=datetime.now(UTC),
        ),
    )

    motor_power_text = f"{source.name}. {motor_power_page_ref}. {motor_power_note}"
    raw_obs_motor_power = await provenance_service.create_raw_observation(
        db,
        RawObservationCreate(
            source_id=source.id,
            external_reference=f"{source.base_url}#{motor_power_page_ref}",
            raw_content={
                "document": source.name,
                "location": motor_power_page_ref,
                "model_row": product_name,
                "transcribed_text": motor_power_text,
            },
            content_hash=_hash(motor_power_text + product_name + "motor_power"),
            collection_method_used=CollectionMethod.MANUAL,
            collected_at=datetime.now(UTC),
        ),
    )

    # Evidence -> VERIFY -> APPLY (skip whole block if already applied —
    # idempotent re-run). Queried directly against ProductAttribute
    # rather than via Product.attributes' lazy relationship, which would
    # require an explicit async load.
    existing_attrs = set(
        (
            await db.execute(
                select(ProductAttribute.specification_id).where(ProductAttribute.product_id == product.id)
            )
        ).scalars().all()
    )

    if pump_type_spec.id not in existing_attrs:
        pump_type_evidence, _c = await product_attribute_evidence_service.create_attribute_evidence(
            db,
            ProductAttributeEvidenceCreate(
                product_id=product.id,
                specification_id=pump_type_spec.id,
                raw_observation_id=raw_obs_pump_type.id,
                value_observed=pump_type_value,
                extraction_method=ExtractionMethod.MANUAL,
                confidence=0.9,
                status=ProvenanceStatus.OBSERVED,
                extraction_context={"document": source.name, "location": pump_type_page_ref},
            ),
        )
        pump_type_evidence = await product_attribute_evidence_service.verify_product_attribute_evidence(
            db, pump_type_evidence, verified_by=admin.id
        )
        pump_type_attr = await product_attribute_evidence_service.apply_reviewed_attribute_to_product(
            db, pump_type_evidence, reviewer_id=admin.id
        )
        print(f"    Pump Type evidence: {pump_type_evidence.id} -> attribute {pump_type_attr.id} = {pump_type_attr.value!r}")

    if motor_power_spec.id not in existing_attrs:
        motor_power_evidence, _c2 = await product_attribute_evidence_service.create_attribute_evidence(
            db,
            ProductAttributeEvidenceCreate(
                product_id=product.id,
                specification_id=motor_power_spec.id,
                raw_observation_id=raw_obs_motor_power.id,
                value_observed=motor_power_kw,
                extraction_method=ExtractionMethod.MANUAL,
                confidence=0.95,
                status=ProvenanceStatus.OBSERVED,
                extraction_context={
                    "document": source.name,
                    "location": motor_power_page_ref,
                    "model_row": product_name,
                },
            ),
        )
        motor_power_evidence = await product_attribute_evidence_service.verify_product_attribute_evidence(
            db, motor_power_evidence, verified_by=admin.id
        )
        motor_power_attr = await product_attribute_evidence_service.apply_reviewed_attribute_to_product(
            db, motor_power_evidence, reviewer_id=admin.id
        )
        print(f"    Motor Power evidence: {motor_power_evidence.id} -> attribute {motor_power_attr.id} = {motor_power_attr.value} kW")

    if product.status != ProductStatus.PUBLISHED:
        product = await product_service.update_product(
            db, product, ProductUpdate(status=ProductStatus.PUBLISHED)
        )
    print(f"    Product published: status={product.status.value}")

    existing_offering_result = await db.execute(
        select(Offering).where(
            Offering.company_id == company.id,
            Offering.product_id == product.id,
            Offering.role == OfferingRole.MANUFACTURER,
        )
    )
    offering = existing_offering_result.scalar_one_or_none()
    if offering is None:
        offering = await offering_service.create_offering(
            db,
            company.id,
            OfferingCreate(product_id=product.id, role=OfferingRole.MANUFACTURER, country=company.country),
        )
    print(f"    Offering: {offering.id} status={offering.status.value} role={offering.role.value}")

    return product


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        admin = await _get_or_create_reviewer(db)
        print(f"Reviewer/admin user: {admin.id} ({admin.email})")

        cat_result = await db.execute(
            select(ProductCategory).where(ProductCategory.name == CENTRIFUGAL_PUMPS_CATEGORY_NAME)
        )
        category = cat_result.scalar_one_or_none()
        if category is None:
            print(f"FATAL: '{CENTRIFUGAL_PUMPS_CATEGORY_NAME}' category not found.")
            return
        specs = await product_service.list_specifications_for_category(db, category.id)
        specs_by_name = {s.name: s for s in specs}
        for required in ("Pump Type", "Motor Power"):
            if required not in specs_by_name:
                print(f"FATAL: required specification {required!r} not found on this category.")
                return
        print(f"Category: {category.id} ({category.name})")

        # ---- 1. Kirloskar Brothers Limited ----
        kbl = await _get_or_create_company(
            db, "Kirloskar Brothers Limited", "https://www.kirloskarpumps.com", "India"
        )
        print(f"\nCompany: {kbl.id} ({kbl.name})")
        kbl_source = await provenance_service.create_source(
            db,
            SourceRegistryCreate(
                name="Kirloskar Brothers Limited — MONOBLOC PUMPS THREE PHASE catalogue (SP-10-2017-01)",
                source_class=SourceClass.COMPANY_OWNED,
                description=(
                    "KBL three-phase monobloc pump range catalogue — KDS/KDI/KDT/KS/SRF "
                    "series. Real letterhead confirmed: registered office Udyog Bhavan, "
                    "Tilak Road, Pune-411002; CIN L29113PN1920PLC000670; "
                    "www.kirloskarpumps.com. Fetched via a distributor mirror "
                    "(kirloskarpumps.com's own domain blocks automated fetches with a bot "
                    "challenge); authenticity is established by the document's own "
                    "letterhead/CIN, not the hosting domain."
                ),
                base_url="https://www.kirloskarpumps.com",
                reliability_weight=0.85,
                collection_method=CollectionMethod.MANUAL,
                geographic_scope="IN",
            ),
        )
        print(f"SourceRegistry (KBL): {kbl_source.id}")

        await _curate_product(
            db, admin,
            company=kbl, category=category, specs_by_name=specs_by_name,
            product_name="KDS-515+", product_family="KDS Series",
            source=kbl_source,
            pump_type_value="Monobloc Pump",
            pump_type_page_ref="page=1 (cover)",
            pump_type_note=(
                "Cover banner: 'KIRLOSKAR BROTHERS LIMITED / MONOBLOC PUMPS / THREE PHASE' — "
                "this heading covers every model listed in the KDS/KDI/KDT/KS/SRF performance "
                "charts on the following pages, KDS-515+ included."
            ),
            motor_power_kw="3.7",
            motor_power_page_ref="page=2, PERFORMANCE CHART FOR 'KDS+ / KDS++ / GMC' SERIES, row 19",
            motor_power_note=(
                "Table row 'KDS-515+': Rated Voltage 400V, Power Rating kW=3.7 HP=5, "
                "Pipe Size SUC=100mm DEL=100mm. Head/discharge columns give a multi-point "
                "curve (32.8m at 6 m3/hr down to 12.5m at 16 m3/hr), not one rated duty "
                "point — Flow Rate/Head deliberately NOT sourced from this row."
            ),
        )
        await _curate_product(
            db, admin,
            company=kbl, category=category, specs_by_name=specs_by_name,
            product_name="KS-1022+", product_family="KS Series",
            source=kbl_source,
            pump_type_value="Monobloc Pump",
            pump_type_page_ref="page=1 (cover)",
            pump_type_note=(
                "Cover banner: 'KIRLOSKAR BROTHERS LIMITED / MONOBLOC PUMPS / THREE PHASE' — "
                "this heading covers every model listed in the KDS/KDI/KDT/KS/SRF performance "
                "charts, KS-1022+ included."
            ),
            motor_power_kw="7.5",
            motor_power_page_ref="page=1, PERFORMANCE CHART FOR 'KS+' SERIES, row 8",
            motor_power_note=(
                "Table row 'KS-1022+': Rated Voltage 400V, Rated Speed 1430 RPM, Power "
                "Rating kW=7.5 HP=10, Pipe Size SUC=100mm DEL=100mm. Head/discharge "
                "columns give a multi-point curve (36.0m at 14 l/s down to 17.5m at 22 l/s), "
                "not one rated duty point — Flow Rate/Head deliberately NOT sourced."
            ),
        )

        # ---- 2. KSB Limited ----
        ksb = await _get_or_create_company(db, "KSB Limited", "https://www.ksbindia.co.in", "India")
        print(f"\nCompany: {ksb.id} ({ksb.name})")
        ksb_source = await provenance_service.create_source(
            db,
            SourceRegistryCreate(
                name="KSB Limited — 200+150 mm Submersible Motor Pumpsets brochure (3402.025)",
                source_class=SourceClass.COMPANY_OWNED,
                description=(
                    "KSB India submersible motor pumpset selection brochure, 150-200mm "
                    "range. Real letterhead confirmed: KSB Limited, Standard Pumps "
                    "Division, Plot No. E3 & E4, MIDC Sinnar, Nashik 422 113; "
                    "www.ksbindia.co.in."
                ),
                base_url="https://ksbindia.in/pdf/Submersible-Pumps.pdf",
                reliability_weight=0.9,
                collection_method=CollectionMethod.MANUAL,
                geographic_scope="IN",
            ),
        )
        print(f"SourceRegistry (KSB): {ksb_source.id}")

        await _curate_product(
            db, admin,
            company=ksb, category=category, specs_by_name=specs_by_name,
            product_name="KSB 373/1A", product_family="373 Series",
            source=ksb_source,
            pump_type_value="Submersible Motor Pumpset",
            pump_type_page_ref="page=3 (cover), '200+150 mm Submersible Motor Pumpsets'",
            pump_type_note="Section title covers every model row in this brochure's Selection Table, 373/1A included.",
            motor_power_kw="7.50",
            motor_power_page_ref="page=4, Selection Table, 'BPHA / UMA I 150' bracket, row 373/1A",
            motor_power_note=(
                "Table row '373/1A': Motor type UMA I 150, Motor rating kW=7.50 HP=10.00, "
                "Cable size 2.5mm2, Starting method S/D, Rated current 15.6A. Discharge "
                "(m3/hr.) columns 80-170 give head 17.5m down to 10.0m — a curve across "
                "10 flow points, not one rated duty point. Flow Rate/Head deliberately NOT sourced."
            ),
        )
        await _curate_product(
            db, admin,
            company=ksb, category=category, specs_by_name=specs_by_name,
            product_name="KSB 383/2A", product_family="383 Series",
            source=ksb_source,
            pump_type_value="Submersible Motor Pumpset",
            pump_type_page_ref="page=3 (cover), '200+150 mm Submersible Motor Pumpsets'",
            pump_type_note="Section title covers every model row in this brochure's Selection Table, 383/2A included.",
            motor_power_kw="15.00",
            motor_power_page_ref="page=4, Selection Table, 'BPH / UMA H 150' bracket, row 383/2A",
            motor_power_note=(
                "Table row '383/2A': Motor type UMA H 150, Motor rating kW=15.00 HP=20.00, "
                "Cable size 4.0mm2, Starting method S/D, Rated current 33.0A. Discharge "
                "(m3/hr.) columns 80-200 give head 36m down to 20m — a curve, not one rated "
                "duty point. Flow Rate/Head deliberately NOT sourced."
            ),
        )

        # ---- 3. Grundfos Pumps India Private Limited ----
        grundfos = await _get_or_create_company(
            db, "Grundfos Pumps India Private Limited", "https://www.grundfos.com/in", "India"
        )
        print(f"\nCompany: {grundfos.id} ({grundfos.name})")
        grundfos_source = await provenance_service.create_source(
            db,
            SourceRegistryCreate(
                name="Grundfos — CR, CRI, CRN 50 Hz IEC Data Booklet",
                source_class=SourceClass.COMPANY_OWNED,
                description=(
                    "Grundfos CR/CRI/CRN vertical multistage centrifugal pump data "
                    "booklet — global technical literature, served from Grundfos' own "
                    "literature CDN (api.grundfos.com)."
                ),
                base_url="https://api.grundfos.com/literature/Grundfosliterature-6014742.pdf",
                reliability_weight=0.9,
                collection_method=CollectionMethod.MANUAL,
                geographic_scope="GLOBAL",
            ),
        )
        print(f"SourceRegistry (Grundfos): {grundfos_source.id}")

        await _curate_product(
            db, admin,
            company=grundfos, category=category, specs_by_name=specs_by_name,
            product_name="Grundfos CR 15-2", product_family="CR 15",
            source=grundfos_source,
            pump_type_value="Vertical Multistage Centrifugal Pump",
            pump_type_page_ref="page=3, Introduction",
            pump_type_note="'CR pumps are vertical, multistage centrifugal pumps.' — the exact, real, already-VERIFIED canonical value CRI's MSP-2E/22 uses.",
            motor_power_kw="2.2",
            motor_power_page_ref="page=49, Dimensions and weights table, row CR 15-2",
            motor_power_note=(
                "Table row 'CR 15-2': Motor P2 [kW]=2.2 (Oval flange D1=415mm D2=736mm, "
                "DIN flange D1=415mm D2=736mm). Pages 48/50's performance curves plot H "
                "against Q continuously per stage-count variant (CR 15-1 through CR 15-17) "
                "— a curve, not one rated duty point. Flow Rate/Head deliberately NOT sourced."
            ),
        )
        await _curate_product(
            db, admin,
            company=grundfos, category=category, specs_by_name=specs_by_name,
            product_name="Grundfos CR 15-6", product_family="CR 15",
            source=grundfos_source,
            pump_type_value="Vertical Multistage Centrifugal Pump",
            pump_type_page_ref="page=3, Introduction",
            pump_type_note="'CR pumps are vertical, multistage centrifugal pumps.'",
            motor_power_kw="5.5",
            motor_power_page_ref="page=49, Dimensions and weights table, row CR 15-6",
            motor_power_note=(
                "Table row 'CR 15-6': Motor P2 [kW]=5.5 (Oval flange D1=632mm D2=1011mm, "
                "DIN flange D1=632mm D2=1011mm D3=300mm). Same curve-not-duty-point "
                "situation as CR 15-2 — Flow Rate/Head deliberately NOT sourced."
            ),
        )

        print("\n" + "=" * 70)
        print("DONE")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
