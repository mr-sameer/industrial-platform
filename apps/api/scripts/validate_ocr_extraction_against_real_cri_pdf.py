#!/usr/bin/env python3
"""
Real CRI 2024 catalogue validation — OCR -> deterministic extraction ->
ProductAttributeEvidence, end to end, against the actual validated
document (Test 3 / the approved rasterization+OCR technology-selection
experiment). NOT part of the pytest suite, deliberately — that would
make the normal suite depend on downloading/holding an external file —
this is a separately runnable manual validation instead.

Creates its own throwaway category/specifications/product/source/
RawObservation directly via the ORM (no HTTP, no auth) — mirrors
scripts/seed_product_graph.py's own pattern. Runs the REAL pypdfium2 +
Tesseract pipeline (app.services.ocr_pipeline_service) against 3
representative pages already established in Test 3: a simple text/
label page (2), the MSP specification page (4, real, measured OCR
errors include "Power Range >" colon-corruption and "0°C to 90°C" ->
"OPC to 9D°C" degree/digit corruption), and the difficult FEEDER PUMPS
page (17, real measured decimal-point loss in its performance table and
complete label/value line separation). Then runs
app.services.spec_extraction_service.run_ocr_extraction against each
resulting OCRResult and reports every proposed evidence row: its value,
its confidence, and whether the EXISTING (unmodified) 0.45 verification
guard would block it.

NEVER calls verify/reject/apply — this is a read-only report of what
the pipeline WOULD propose, never an action taken on it.

DATABASE SAFETY: run this only against a disposable database — never
industrial_platform. Uses whatever DATABASE_URL/REDIS_URL the current
environment is already configured with, exactly like pytest does; point
those at a disposable Postgres before running, e.g.:

    export DATABASE_URL=postgresql+asyncpg://forgex_test_user:forgex_test_pass@localhost:5545/forgex_test
    export DATABASE_URL_SYNC=postgresql+psycopg://forgex_test_user:forgex_test_pass@localhost:5545/forgex_test
    cd apps/api
    python scripts/validate_ocr_extraction_against_real_cri_pdf.py /path/to/cri-2024-catalogue.pdf
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.core.logging import configure_logging  # noqa: E402
from app.core.storage import get_storage_backend, make_source_document_key  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.product import Product, ProductStatus  # noqa: E402
from app.models.product_category import ProductCategory  # noqa: E402
from app.models.product_specification import (  # noqa: E402
    ProductSpecification,
    SpecificationDataType,
)
from app.models.raw_observation import RawObservation  # noqa: E402
from app.models.source_registry import CollectionMethod, SourceClass, SourceRegistry  # noqa: E402
from app.services import ocr_pipeline_service, spec_extraction_service  # noqa: E402
from app.services.product_attribute_evidence_service import (  # noqa: E402
    MIN_VERIFIABLE_CONFIDENCE,
    get_attribute_evidence,
)

# Simple label/value page, MSP specification page, difficult FEEDER
# PUMPS table page — the exact three pages Test 3 established as
# representative.
TARGET_PAGES = [2, 4, 17]

# name, unit, datatype — chosen to match real CRI 2024 catalogue label
# vocabulary established in Test 3's own ground-truth transcription.
TARGET_SPECS: list[tuple[str, str | None, str]] = [
    ("Ambient Temperature", "°C", "number"),
    ("Liquid Temperature", "°C", "range"),
    ("Degree of Protection", None, "text"),
    ("Power Range", "kW", "range"),
]


async def _setup(db, pdf_bytes: bytes) -> tuple[Product, RawObservation]:
    category = ProductCategory(
        name="CRI Validation Category", slug=f"cri-validation-{uuid.uuid4().hex[:8]}"
    )
    db.add(category)
    await db.flush()

    for name, unit, datatype in TARGET_SPECS:
        db.add(
            ProductSpecification(
                category_id=category.id,
                name=name,
                unit=unit,
                datatype=SpecificationDataType(datatype),
                required=False,
            )
        )
    await db.flush()

    product = Product(
        name="CRI Validation Product",
        slug=f"cri-validation-product-{uuid.uuid4().hex[:8]}",
        category_id=category.id,
        status=ProductStatus.PUBLISHED,
    )
    db.add(product)
    await db.flush()

    source = SourceRegistry(
        name="CRI 2024 Catalogue Validation",
        source_class=SourceClass.COMPANY_OWNED,
        collection_method=CollectionMethod.STRUCTURED_FILE,
        reliability_weight=0.7,
    )
    db.add(source)
    await db.flush()

    storage = get_storage_backend()
    key = make_source_document_key(
        category="validation", original_filename="cri-2024-catalogue.pdf"
    )
    await storage.save(key, pdf_bytes, "application/pdf")

    observation = RawObservation(
        source_id=source.id,
        external_reference="manual-cri-validation",
        raw_content={"storage_key": key, "filename": "cri-2024-catalogue.pdf"},
        content_hash=f"cri-validation-{uuid.uuid4().hex}",
        collection_method_used=CollectionMethod.STRUCTURED_FILE,
        collected_at=datetime.now(UTC),
    )
    db.add(observation)
    await db.flush()
    await db.commit()
    return product, observation


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    pdf_path = Path(sys.argv[1])
    if not pdf_path.is_file():
        print(f"No such file: {pdf_path}")
        sys.exit(1)
    pdf_bytes = pdf_path.read_bytes()

    configure_logging()
    async with AsyncSessionLocal() as db:
        product, observation = await _setup(db, pdf_bytes)
        spec_rows = (
            (
                await db.execute(
                    select(ProductSpecification).where(
                        ProductSpecification.category_id == product.category_id
                    )
                )
            )
            .scalars()
            .all()
        )
        spec_name_by_id = {s.id: s.name for s in spec_rows}

        print(f"Product: {product.name} ({product.id})")
        print(f"RawObservation: {observation.id}\n")

        for page_number in TARGET_PAGES:
            print(f"{'=' * 70}\nPAGE {page_number}\n{'=' * 70}")
            ocr_result = await ocr_pipeline_service.process_raw_observation_page(
                db,
                raw_observation_id=observation.id,
                page_number=page_number,
            )
            print(f"OCR confidence: {ocr_result.confidence:.3f}")
            print(f"OCR text (first 200 chars): {ocr_result.text[:200]!r}\n")

            result = await spec_extraction_service.run_ocr_extraction(
                db,
                product_id=product.id,
                raw_observation_id=observation.id,
                ocr_result_id=ocr_result.id,
            )

            if not result.created and not result.rejected:
                print("  No extraction candidates produced on this page.")
            for evidence_id in result.created:
                evidence = await get_attribute_evidence(db, evidence_id)
                spec_name = spec_name_by_id.get(evidence.specification_id, "?")
                blocked = evidence.confidence < MIN_VERIFIABLE_CONFIDENCE
                guard = "BLOCKED by 0.45 guard" if blocked else "would pass 0.45 guard"
                print(
                    f"  PROPOSED (never verified/applied): {spec_name} = "
                    f"{evidence.value_observed!r} (confidence={evidence.confidence:.3f}, {guard})"
                )
            for rejected in result.rejected:
                print(
                    f"  REJECTED (validation failure): label={rejected.label!r} reason={rejected.reason}"
                )
            print()

    print("Validation complete. No evidence was verified or applied — this is a report only.")


if __name__ == "__main__":
    asyncio.run(main())
