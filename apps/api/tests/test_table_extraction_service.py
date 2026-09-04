"""
Table Intelligence V1 foundation — service/DB-level tests for
app.services.table_extraction_service. Builds WordBox rows directly
(the same synthetic 5-column performance-chart shape validated in
tests/test_table_geometry.py) and drives extract_table_row_evidence
against a real disposable database — no Tesseract execution needed to
test the geometry-to-evidence wiring itself; see
scripts/validate_table_extraction_against_real_cri_pdf.py for the
real-engine, real-CRI-catalogue validation this milestone also
requires.

Letters R-X below match the required-coverage list from the approved
V1 implementation directive; V/W/X are also covered by re-running the
existing OCR/evidence/spec-extraction suites unmodified (see the final
report, not duplicated here).
"""

import uuid

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.extraction.table_geometry import WordBox
from app.models.product_attribute_evidence import ProductAttributeEvidence
from app.models.provenance_record import ProvenanceStatus
from app.services import product_attribute_evidence_service, table_extraction_service
from tests.test_acquisition import _register_admin
from tests.test_product_attribute_evidence import _create_ocr_result_row
from tests.test_provenance import _create_observation, _create_source
from tests.test_spec_extraction import _setup


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


def row_at(y: float, identity: str, identity_x: float, values: dict[float, str]) -> list[WordBox]:
    row = [wb(identity, identity_x, y)]
    for x, text in values.items():
        row.append(wb(text, x, y))
    return row


COLS = [200.0, 260.0, 320.0, 380.0, 440.0]


def _three_row_table() -> tuple[list[list[WordBox]], list[list[WordBox]]]:
    row_a = row_at(
        100, "JTS-3/11M", -55, {200: "45.0", 260: "44.0", 320: "42.0", 380: "40.0", 440: "38.0"}
    )
    row_b = row_at(130, "JTS-3/05M", -83, {320: "38.5"})
    row_c = row_at(
        160, "JTS-3/20M", -17, {200: "46.0", 260: "45.0", 320: "43.0", 380: "41.0", 440: "39.0"}
    )
    data_rows = [row_a, row_b, row_c]
    header_row = [
        wb(t, x, 70) for x, t in zip(COLS, ["0.1", "0.2", "0.3", "0.4", "0.5"], strict=False)
    ]
    return data_rows, [header_row]


async def _plain_observation(client, admin, content_hash: str) -> dict:
    source = await _create_source(client, admin)
    return await _create_observation(
        client, admin, source["id"], "unused", content_hash=content_hash
    )


async def _extract_row(
    client,
    admin,
    *,
    spec_kwargs: dict,
    content_hash: str,
    ocr_confidence: float = 0.95,
    target_row_identity: str = "JTS-3/05M",
    data_rows=None,
    header_rows=None,
):
    _category, _spec, product = await _setup(client, admin, spec_kwargs=spec_kwargs)
    observation = await _plain_observation(client, admin, content_hash)
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=ocr_confidence, text="unused"
    )

    rows, headers = _three_row_table()
    async with AsyncSessionLocal() as db:
        result = await table_extraction_service.extract_table_row_evidence(
            db,
            product_id=uuid.UUID(product["id"]),
            specification_id=uuid.UUID(_spec["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
            target_row_identity=target_row_identity,
            header_rows=headers if header_rows is None else header_rows,
            data_rows=rows if data_rows is None else data_rows,
            table_title="JTS Performance Chart",
        )
    return result, product, _spec, observation, ocr_result


# --------------------------------------------------------------------------
# R. A geometrically valid, targeted row produces evidence with the
#    exact payload shape
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_r_valid_row_creates_evidence_with_expected_payload(client):
    admin = await _register_admin(client, "tblx-r@example.com")
    result, _product, _spec, observation, ocr_result = await _extract_row(
        client,
        admin,
        spec_kwargs={"name": "Discharge Row", "unit": None, "datatype": "text"},
        content_hash="tblx-r-hash",
    )

    assert result.status == table_extraction_service.STATUS_CREATED
    assert result.evidence_id is not None
    assert result.grid_pitch == 60.0

    async with AsyncSessionLocal() as db:
        evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, result.evidence_id
        )

    assert evidence.value_observed == "JTS-3/05M"
    assert evidence.ocr_result_id == ocr_result.id
    assert evidence.raw_observation_id == uuid.UUID(observation["id"])
    assert evidence.status == ProvenanceStatus.EXTRACTED
    ctx = evidence.extraction_context
    assert ctx["table_title"] == "JTS Performance Chart"
    assert ctx["row_identity"] == "JTS-3/05M"
    assert ctx["grid"]["pitch"] == 60.0
    present_cells = [c for c in ctx["cells"].values() if c["status"] == "present"]
    assert len(present_cells) == 1
    assert present_cells[0]["value"] == "38.5"
    assert present_cells[0]["column_path"] == ["0.3"]


# --------------------------------------------------------------------------
# S. Ambiguous/unusable grid produces NO evidence (fail closed)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_s_ambiguous_grid_creates_no_evidence(client):
    admin = await _register_admin(client, "tblx-s@example.com")
    # Only ONE populated data row — below MIN_POPULATED_ROWS, since a
    # single row's own geometry is never enough to validate a pitch
    # (see table_geometry's own docstring). Guaranteed to fail at the
    # very first grid gate regardless of any other token placement.
    single_row = [row_at(100, "JTS-1/A", -60, {100: "10.0", 160: "11.0", 220: "12.0"})]
    result, *_ = await _extract_row(
        client,
        admin,
        spec_kwargs={"name": "Bad Grid", "unit": None, "datatype": "text"},
        content_hash="tblx-s-hash",
        data_rows=single_row,
        target_row_identity="JTS-1/A",
    )
    assert result.status == table_extraction_service.STATUS_AMBIGUOUS_GRID
    assert result.evidence_id is None

    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(ProductAttributeEvidence))).scalars().all()
    assert count == []


# --------------------------------------------------------------------------
# T. Header semantics unresolved (CTSS case) produces NO evidence
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_t_unresolved_header_semantics_creates_no_evidence(client):
    admin = await _register_admin(client, "tblx-t@example.com")
    sparse_header = [[wb("0.1", COLS[0], 70)]]  # only 1 of 5 real columns recovered
    result, *_ = await _extract_row(
        client,
        admin,
        spec_kwargs={"name": "Unresolved Header", "unit": None, "datatype": "text"},
        content_hash="tblx-t-hash",
        header_rows=sparse_header,
    )
    assert result.status == table_extraction_service.STATUS_SEMANTICS_UNRESOLVED
    assert result.evidence_id is None


# --------------------------------------------------------------------------
# U. Row identity ambiguity/absence blocks evidence
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_u_no_matching_row_identity_creates_no_evidence(client):
    admin = await _register_admin(client, "tblx-u@example.com")
    result, *_ = await _extract_row(
        client,
        admin,
        spec_kwargs={"name": "No Match", "unit": None, "datatype": "text"},
        content_hash="tblx-u-hash",
        target_row_identity="JTS-9/99M",  # does not exist in the table
    )
    assert result.status == table_extraction_service.STATUS_ROW_IDENTITY_NOT_FOUND
    assert result.evidence_id is None


@pytest.mark.asyncio
async def test_u_multiple_model_shaped_tokens_in_one_row_blocks_identity():
    """Model-number identity must be unambiguous — a row carrying TWO
    shape-valid candidate tokens is uncertain, never guessed at."""
    row_with_two_candidates = row_at(100, "JTS-3/11M", -55, {320: "38.5"})
    row_with_two_candidates.append(wb("JTS-9/99M", -20, 100))  # a second candidate on the same row
    ambiguous = table_extraction_service._find_row_identity(row_with_two_candidates)
    assert ambiguous is None


# --------------------------------------------------------------------------
# V (partial). Confidence never exceeds the grid's own quality score
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v_structural_confidence_never_exceeds_grid_score(client):
    admin = await _register_admin(client, "tblx-v@example.com")
    result, _product, _spec, _observation, _ocr = await _extract_row(
        client,
        admin,
        spec_kwargs={"name": "Confidence Ceiling", "unit": None, "datatype": "text"},
        content_hash="tblx-v-hash",
    )
    async with AsyncSessionLocal() as db:
        evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, result.evidence_id
        )
    assert evidence.confidence <= result.grid_score


# --------------------------------------------------------------------------
# W. Reprocessing: a second OCRResult run produces a SEPARATE evidence
#    row, never an overwrite
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_w_second_ocr_run_produces_separate_evidence_row(client):
    admin = await _register_admin(client, "tblx-w@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Reprocess Row", "unit": None, "datatype": "text"}
    )
    observation = await _plain_observation(client, admin, "tblx-w-hash")
    run_a = await _create_ocr_result_row(observation["id"], confidence=0.95, text="unused")
    run_b = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="unused", engine_version="2.0.0"
    )

    rows, headers = _three_row_table()
    async with AsyncSessionLocal() as db:
        result_a = await table_extraction_service.extract_table_row_evidence(
            db,
            product_id=uuid.UUID(product["id"]),
            specification_id=uuid.UUID(spec["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=run_a.id,
            target_row_identity="JTS-3/05M",
            header_rows=headers,
            data_rows=rows,
            table_title="JTS Performance Chart",
        )
        result_b = await table_extraction_service.extract_table_row_evidence(
            db,
            product_id=uuid.UUID(product["id"]),
            specification_id=uuid.UUID(spec["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=run_b.id,
            target_row_identity="JTS-3/05M",
            header_rows=headers,
            data_rows=rows,
            table_title="JTS Performance Chart",
        )

    assert result_a.status == table_extraction_service.STATUS_CREATED
    assert result_b.status == table_extraction_service.STATUS_CREATED
    assert result_a.evidence_id != result_b.evidence_id


@pytest.mark.asyncio
async def test_w_repeat_call_same_ocr_result_is_idempotent(client):
    admin = await _register_admin(client, "tblx-w2@example.com")
    first, product, spec, observation, ocr_result = await _extract_row(
        client,
        admin,
        spec_kwargs={"name": "Idempotent Row", "unit": None, "datatype": "text"},
        content_hash="tblx-w2-hash",
    )

    rows, headers = _three_row_table()
    async with AsyncSessionLocal() as db:
        second = await table_extraction_service.extract_table_row_evidence(
            db,
            product_id=uuid.UUID(product["id"]),
            specification_id=uuid.UUID(spec["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
            target_row_identity="JTS-3/05M",
            header_rows=headers,
            data_rows=rows,
            table_title="JTS Performance Chart",
        )

    assert second.status == table_extraction_service.STATUS_EXISTING
    assert second.evidence_id == first.evidence_id


# --------------------------------------------------------------------------
# X. Evidence must still pass through the existing verify/apply
#    workflow untouched (never auto-applied)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_x_evidence_requires_explicit_verification_before_apply(client):
    admin = await _register_admin(client, "tblx-x@example.com")
    result, product, spec, _observation, _ocr = await _extract_row(
        client,
        admin,
        spec_kwargs={"name": "Verify Gate Row", "unit": None, "datatype": "text"},
        content_hash="tblx-x-hash",
    )

    async with AsyncSessionLocal() as db:
        evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, result.evidence_id
        )
        assert evidence.status == ProvenanceStatus.EXTRACTED
        with pytest.raises(product_attribute_evidence_service.EvidenceNotVerifiedError):
            await product_attribute_evidence_service.apply_reviewed_attribute_to_product(
                db, evidence, reviewer_id=uuid.uuid4()
            )
