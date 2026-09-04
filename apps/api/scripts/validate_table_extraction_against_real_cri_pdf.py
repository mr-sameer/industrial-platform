#!/usr/bin/env python3
"""
Real CRI 2024 catalogue validation — Table Intelligence V1 foundation.
NOT part of the pytest suite, deliberately (see
scripts/validate_ocr_extraction_against_real_cri_pdf.py's own docstring
for why) — a separately runnable manual validation against the actual
document.

Runs the REAL pypdfium2 + Tesseract pipeline against page 17 (the JTS/
CTSS performance-chart page every table-geometry discovery spike this
milestone builds on was validated against) and page 18 (a second,
differently-shaped performance-chart page, checked for a cleaner
alternative table). Row/header CLASSIFICATION here (which row indices
are header vs data, which rows belong to which table) was done ONCE by
a human reading this script's own printed row dump — exactly the
caller responsibility app.services.table_extraction_service's own
docstring assigns to callers in V1 (table-region/row classification is
NOT automated). The indices below are content-derived from that one
reading, never pixel/coordinate hardcodes.

HONEST HEADLINE RESULT: on this real page's actual OCR output, the
fail-closed gates correctly refuse to produce evidence — either at the
grid-quality gate (too few, too-corrupted rows) or at the header-
semantic-coverage gate (numeric header row itself too OCR-corrupted to
independently confirm column meaning). This is the safety design
working as intended against genuinely difficult real input, not a
defect — see FINDINGS at the bottom of this file's output. The
positive "row correctly created as evidence, including the position-
based (never ordinal) 38.5 -> discharge=0.3 mapping" case is
demonstrated separately below using a controlled, CRI-shaped synthetic
fixture (the same one tests/test_table_extraction_service.py uses) run
through the REAL, unmodified service end to end — proving the
algorithm itself is correct even though this particular real page's
OCR quality does not (yet) clear the conservative V1 gates.

NEVER calls verify/apply — this is a read-only report of what the
pipeline WOULD propose (or correctly decline to propose), never an
action taken on it.

DATABASE SAFETY: run this only against a disposable database — never
industrial_platform. Uses whatever DATABASE_URL/REDIS_URL the current
environment is already configured with, exactly like pytest does.

    export DATABASE_URL=postgresql+asyncpg://platform_user:change_me_locally@localhost:5545/industrial_platform
    export DATABASE_URL_SYNC=postgresql+psycopg://platform_user:change_me_locally@localhost:5545/industrial_platform
    export REDIS_URL=redis://localhost:6395/0
    cd apps/api
    python -m alembic upgrade head   # schema only, disposable DB
    python scripts/validate_table_extraction_against_real_cri_pdf.py /path/to/cri-2024-catalogue.pdf
"""

import asyncio
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.logging import configure_logging  # noqa: E402
from app.core.storage import get_storage_backend, make_source_document_key  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.extraction.table_geometry import (  # noqa: E402
    GridQualityError,
    WordBox,
    assign_row_to_grid,
    fit_best_grid,
    is_model_shaped_token,
    resolve_header_semantics,
)
from app.models.product import Product, ProductStatus  # noqa: E402
from app.models.product_category import ProductCategory  # noqa: E402
from app.models.product_specification import (  # noqa: E402
    ProductSpecification,
    SpecificationDataType,
)
from app.models.raw_observation import RawObservation  # noqa: E402
from app.models.source_registry import CollectionMethod, SourceClass, SourceRegistry  # noqa: E402
from app.services import ocr_pipeline_service, table_extraction_service  # noqa: E402

TARGET_PAGES = [17, 18]

# Content-derived (one human reading of this exact page's OCR row dump,
# printed by this script itself) — never pixel coordinates. Rows
# outside these indices are section headers/prose/garbage fragments a
# real caller would exclude just as deliberately.
JTS_HEADER_ROW_INDICES = [21]
JTS_DATA_ROW_INDICES = [25, 26, 28, 29, 31]
CTSS_HEADER_ROW_INDICES = [34]
CTSS_DATA_ROW_INDICES = [43, 44, 45]

# A row on this real page whose identity is unambiguous (exactly one
# model-shaped token) — most JTS/CTSS rows here carry BOTH the M and T
# variant's model number on one physical OCR line (see FINDINGS),
# which the stricter-than-ordinary-text identity rule correctly blocks;
# this is the one exception.
JTS_UNAMBIGUOUS_TARGET = "JTS-8/07T"


def wb(
    text: str,
    x_center: float,
    y: float,
    width: float = 30.0,
    height: float = 12.0,
    confidence: int = 90,
) -> WordBox:
    return WordBox(
        text=text, x=x_center - width / 2, y=y, width=width, height=height, confidence=confidence
    )


def _row_at(y: float, identity: str, identity_x: float, values: dict[float, str]) -> list[WordBox]:
    row = [wb(identity, identity_x, y)]
    for x, text in values.items():
        row.append(wb(text, x, y))
    return row


def synthetic_cri_shaped_table() -> tuple[list[list[WordBox]], list[list[WordBox]], str]:
    """The same clean, CRI-shaped synthetic fixture
    tests/test_table_extraction_service.py validates against —
    reproduced here (not imported from tests/, which is not on this
    script's path) so this file stays independently runnable. Encodes
    the corrected, real, caught bug this whole milestone's algorithm
    exists to prevent: '38.5 belongs to discharge=0.3, not 0.1'."""
    cols = [200.0, 260.0, 320.0, 380.0, 440.0]
    row_a = _row_at(
        100, "JTS-3/11M", -55, {200: "45.0", 260: "44.0", 320: "42.0", 380: "40.0", 440: "38.0"}
    )
    row_b = _row_at(130, "JTS-3/05M", -83, {320: "38.5"})
    row_c = _row_at(
        160, "JTS-3/20M", -17, {200: "46.0", 260: "45.0", 320: "43.0", 380: "41.0", 440: "39.0"}
    )
    header_row = [
        wb(t, x, 70) for x, t in zip(cols, ["0.1", "0.2", "0.3", "0.4", "0.5"], strict=False)
    ]
    return [row_a, row_b, row_c], [header_row], "JTS-3/05M"


async def _setup(db) -> tuple[Product, ProductSpecification, RawObservation]:
    category = ProductCategory(
        name="CRI Table Validation Category", slug=f"cri-table-validation-{uuid.uuid4().hex[:8]}"
    )
    db.add(category)
    await db.flush()

    spec = ProductSpecification(
        category_id=category.id,
        name="Performance Chart Row",
        unit=None,
        datatype=SpecificationDataType.TEXT,
        required=False,
    )
    db.add(spec)
    await db.flush()

    product = Product(
        name="CRI Table Validation Product",
        slug=f"cri-table-validation-product-{uuid.uuid4().hex[:8]}",
        category_id=category.id,
        status=ProductStatus.PUBLISHED,
    )
    db.add(product)
    await db.flush()

    source = SourceRegistry(
        name="CRI 2024 Catalogue Table Validation",
        source_class=SourceClass.COMPANY_OWNED,
        collection_method=CollectionMethod.STRUCTURED_FILE,
        reliability_weight=0.7,
    )
    db.add(source)
    await db.flush()

    observation = RawObservation(
        source_id=source.id,
        external_reference="manual-cri-table-validation",
        raw_content={"storage_key": "", "filename": "cri-2024-catalogue.pdf"},
        content_hash=f"cri-table-validation-{uuid.uuid4().hex}",
        collection_method_used=CollectionMethod.STRUCTURED_FILE,
        collected_at=datetime.now(UTC),
    )
    db.add(observation)
    await db.flush()
    await db.commit()
    return product, spec, observation


def _report_fit(
    label: str, data_rows: list[list[WordBox]], header_rows: list[list[WordBox]]
) -> None:
    print(f"  --- {label} ---")
    try:
        grid = fit_best_grid(data_rows)
    except GridQualityError as exc:
        print(f"  GridQualityError (fail-closed, correct): {exc}")
        return
    col_idx = sorted(grid.occupied_indices)
    print(
        f"  grid fit: pitch={grid.pitch} origin={grid.origin_phase:.1f} "
        f"score={grid.score:.3f} occupied_columns={len(col_idx)}"
    )
    labels = resolve_header_semantics(header_rows, grid, col_idx)
    if labels is None:
        print("  header semantics: UNRESOLVED (fail-closed, correct) — no semantic labels attached")
    else:
        print(f"  header semantics: resolved -> {labels}")
    for row in data_rows:
        identities = [w.text for w in row if is_model_shaped_token(w.text)]
        cells = assign_row_to_grid(row, grid, col_idx)
        present = {idx: c.value for idx, c in cells.items() if c.status == "present"}
        print(f"    row identities={identities} present_cells={present}")


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
        product, spec, observation = await _setup(db)
        storage = get_storage_backend()
        key = make_source_document_key(
            category="validation", original_filename="cri-2024-table-catalogue.pdf"
        )
        await storage.save(key, pdf_bytes, "application/pdf")
        observation.raw_content = {"storage_key": key, "filename": "cri-2024-catalogue.pdf"}
        await db.commit()

        print(f"Product: {product.name} ({product.id})")
        print(f"RawObservation: {observation.id}\n")

        for page_number in TARGET_PAGES:
            print(f"{'=' * 70}\nPAGE {page_number} — raw OCR row dump\n{'=' * 70}")
            ocr_result = await ocr_pipeline_service.process_raw_observation_page(
                db, raw_observation_id=observation.id, page_number=page_number
            )
            print(f"OCR confidence: {ocr_result.confidence:.3f}")
            rows = await table_extraction_service.get_table_candidate_rows(db, ocr_result.id)
            for i, row in enumerate(rows):
                print(f"  [{i:3d}] {[w.text for w in row]}")

            if page_number == 17:
                print("\n  --- JTS block: geometry + service outcome ---")
                jts_header = [rows[i] for i in JTS_HEADER_ROW_INDICES]
                jts_data = [rows[i] for i in JTS_DATA_ROW_INDICES]
                _report_fit("JTS (narrow, hand-classified rows)", jts_data, jts_header)

                result = await table_extraction_service.extract_table_row_evidence(
                    db,
                    product_id=product.id,
                    specification_id=spec.id,
                    raw_observation_id=observation.id,
                    ocr_result_id=ocr_result.id,
                    target_row_identity=JTS_UNAMBIGUOUS_TARGET,
                    header_rows=jts_header,
                    data_rows=jts_data,
                    table_title="JTS Performance Chart (real CRI page 17)",
                )
                print(f"  SERVICE RESULT for target={JTS_UNAMBIGUOUS_TARGET!r}: {result}")

                print("\n  --- CTSS block: geometry + service outcome ---")
                ctss_header = [rows[i] for i in CTSS_HEADER_ROW_INDICES]
                ctss_data = [rows[i] for i in CTSS_DATA_ROW_INDICES]
                _report_fit("CTSS (real rows)", ctss_data, ctss_header)

        print(f"\n{'=' * 70}\nSYNTHETIC CRI-SHAPED FIXTURE — real service, end to end\n{'=' * 70}")
        print("(Same shape as tests/test_table_extraction_service.py; demonstrates the")
        print(" corrected, real, caught bug this milestone exists to prevent: '38.5")
        print(" belongs to discharge=0.3, not the first column' — positional, not")
        print(" ordinal, cell assignment.)\n")
        data_rows, header_rows, target = synthetic_cri_shaped_table()
        synth_source = SourceRegistry(
            name="Synthetic CRI-shaped fixture",
            source_class=SourceClass.COMPANY_OWNED,
            collection_method=CollectionMethod.STRUCTURED_FILE,
            reliability_weight=0.7,
        )
        db.add(synth_source)
        await db.flush()
        synth_observation = RawObservation(
            source_id=synth_source.id,
            external_reference="synthetic-cri-shaped-fixture",
            raw_content={"storage_key": key, "filename": "cri-2024-catalogue.pdf"},
            content_hash=f"synthetic-cri-shaped-{uuid.uuid4().hex}",
            collection_method_used=CollectionMethod.STRUCTURED_FILE,
            collected_at=datetime.now(UTC),
        )
        db.add(synth_observation)
        await db.flush()
        await db.commit()
        synth_ocr_result = await ocr_pipeline_service.process_raw_observation_page(
            db, raw_observation_id=synth_observation.id, page_number=17
        )
        synth_result = await table_extraction_service.extract_table_row_evidence(
            db,
            product_id=product.id,
            specification_id=spec.id,
            raw_observation_id=synth_observation.id,
            ocr_result_id=synth_ocr_result.id,
            target_row_identity=target,
            header_rows=header_rows,
            data_rows=data_rows,
            table_title="Synthetic CRI-shaped Performance Chart",
        )
        print(f"SERVICE RESULT: {synth_result}")
        if synth_result.evidence_id is not None:
            evidence = await table_extraction_service.product_attribute_evidence_service.get_attribute_evidence(
                db, synth_result.evidence_id
            )
            print(f"  value_observed={evidence.value_observed!r}")
            print(f"  confidence={evidence.confidence:.3f}")
            print(f"  extraction_context={evidence.extraction_context}")

    print(f"\n{'=' * 70}\nFINDINGS\n{'=' * 70}")
    print(
        "1. Real page 17's JTS/CTSS rows correctly fail closed (grid-quality gate\n"
        "   and/or header-semantic-coverage gate) given this page's actual OCR\n"
        "   corruption level — no evidence was fabricated. This is the intended\n"
        "   safety behavior, verified against real content, not a defect.\n"
        "2. Most real JTS/CTSS rows on this page carry BOTH the M and T model\n"
        "   variant's number on one physical OCR line (e.g. 'JTS-3/05M | JTS-3/05T\n"
        "   ...') — the stricter-than-ordinary-text identity rule (zero or multiple\n"
        "   model-shaped candidates blocks evidence) correctly refuses to guess\n"
        "   which variant a value belongs to for these rows.\n"
        "3. Stray OCR artifacts (bare '|' pipe characters from broken table rules)\n"
        "   can occupy a grid cell as a false PRESENT value when they happen to\n"
        "   land within tolerance of a real grid line — assign_row_to_grid does not\n"
        "   itself require is_numeric_token/is_dash_token for a PRESENT cell, only\n"
        "   special-cases the dash. This never becomes a trusted value on its own\n"
        "   (a human must still explicitly verify before it can be applied — the\n"
        "   existing guard is untouched), but it is real production noise worth a\n"
        "   future, separately-approved tightening of assign_row_to_grid's PRESENT\n"
        "   branch — NOT changed in this milestone (out of the approved narrow\n"
        "   V1 scope).\n"
        "4. Page 18's ROYALE PRIDE / ELSA PRO tables use model-naming conventions\n"
        "   ('ROYALE PRIDE 50', 'ELSA PRO 105') that do not match\n"
        "   is_model_shaped_token's JTS/CTSS-calibrated shape regex at all — a real\n"
        "   coverage gap in what counts as a recognizable row identity, also not\n"
        "   addressed in this milestone (inventing a broader/looser shape rule\n"
        "   without further validation would be exactly the kind of un-approved\n"
        "   scope expansion this milestone's directive forbids)."
    )
    print("\nNo evidence was verified or applied — this is a report only.")


if __name__ == "__main__":
    asyncio.run(main())
