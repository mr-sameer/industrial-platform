"""
OCR -> deterministic specification extraction -> ProductAttributeEvidence
integration tests — the approved milestone connecting
app.services.spec_extraction_service.run_ocr_extraction (new) to the
existing, unmodified OCR V1 foundation
(product_attribute_evidence_service.create_ocr_derived_attribute_evidence)
and OCR processing foundation (ocr_result_service). OCRResult rows here
are hand-crafted with fake/controlled text and confidence (mirroring
tests.test_product_attribute_evidence's own _create_ocr_result_row) —
no real Tesseract execution needed to test the extraction/evidence
wiring itself; see
scripts/validate_ocr_extraction_against_real_cri_pdf.py for the real-
engine, real-CRI-catalogue validation this milestone also requires.
"""

import uuid

import pytest

from app.db.session import AsyncSessionLocal
from app.models.provenance_record import ProvenanceStatus
from app.services import product_attribute_evidence_service, spec_extraction_service
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers
from tests.test_product_attribute_evidence import _create_ocr_result_row
from tests.test_provenance import _create_observation, _create_source
from tests.test_spec_extraction import _create_document_observation, _extract, _get_evidence, _setup


async def _create_plain_observation(client, admin, content_hash: str) -> dict:
    """A RawObservation with no document-shaped raw_content at all —
    run_ocr_extraction never calls _extract_pages/reads raw_content, so
    (unlike native extraction) it has no need for the document-adapter
    contract shape. Using the simplest possible observation here is
    itself part of proving that."""
    source = await _create_source(client, admin)
    return await _create_observation(
        client, admin, source["id"], "unused", content_hash=content_hash
    )


# --------------------------------------------------------------------------
# A. OCRResult text usable as extraction input
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_text_produces_extraction_candidate(client):
    admin = await _register_admin(client, "ocrspx-a@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-a-hash")
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )

    assert len(result.created) == 1


@pytest.mark.asyncio
async def test_ocr_text_that_does_not_safely_parse_produces_no_candidate(client):
    """Mirrors the real CRI finding: a line an OCR engine mangled beyond
    what app.extraction.validation accepts produces NO candidate — never
    a guessed one. No 'OCR correction' heuristic exists anywhere in this
    pipeline."""
    admin = await _register_admin(client, "ocrspx-a2@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-a2-hash")
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="F1ow R4te garbled nonsense with no shape at all"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )

    assert result.created == []


# --------------------------------------------------------------------------
# B. OCR-derived evidence receives ocr_result_id
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_derived_evidence_has_ocr_result_id_and_raw_observation_id(client):
    admin = await _register_admin(client, "ocrspx-b@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-b-hash")
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
        evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, result.created[0]
        )

    assert evidence.ocr_result_id == ocr_result.id
    assert evidence.raw_observation_id == uuid.UUID(observation["id"])
    assert evidence.extraction_method.value == "rule_based"


# --------------------------------------------------------------------------
# C. raw_observation_id / ocr_result_id consistency is enforced
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mismatched_raw_observation_and_ocr_result_rejected(client):
    admin = await _register_admin(client, "ocrspx-c@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation_a = await _create_plain_observation(client, admin, "ocrspx-c-a-hash")
    observation_b = await _create_plain_observation(client, admin, "ocrspx-c-b-hash")
    ocr_result_on_a = await _create_ocr_result_row(
        observation_a["id"], confidence=0.95, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        with pytest.raises(product_attribute_evidence_service.RawObservationOcrResultMismatchError):
            await spec_extraction_service.run_ocr_extraction(
                db,
                product_id=uuid.UUID(product["id"]),
                raw_observation_id=uuid.UUID(observation_b["id"]),  # wrong document
                ocr_result_id=ocr_result_on_a.id,
            )


@pytest.mark.asyncio
async def test_mismatch_rejected_even_when_ocr_text_has_no_matches(client):
    """The consistency check must fire UNCONDITIONALLY — even on a page
    with zero valid readings, which would otherwise never reach
    create_ocr_derived_attribute_evidence's own equivalent check at
    all."""
    admin = await _register_admin(client, "ocrspx-c2@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation_a = await _create_plain_observation(client, admin, "ocrspx-c2-a-hash")
    observation_b = await _create_plain_observation(client, admin, "ocrspx-c2-b-hash")
    ocr_result_on_a = await _create_ocr_result_row(
        observation_a["id"], confidence=0.95, text="nothing matches anything here"
    )

    async with AsyncSessionLocal() as db:
        with pytest.raises(product_attribute_evidence_service.RawObservationOcrResultMismatchError):
            await spec_extraction_service.run_ocr_extraction(
                db,
                product_id=uuid.UUID(product["id"]),
                raw_observation_id=uuid.UUID(observation_b["id"]),
                ocr_result_id=ocr_result_on_a.id,
            )


# --------------------------------------------------------------------------
# D. OCR confidence ceiling is applied correctly
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_low_ocr_confidence_drags_down_high_extraction_confidence(client):
    admin = await _register_admin(client, "ocrspx-d@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-d-hash")
    # exact-name, colon-style, unit-resolved match -> extraction tier 0.90
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.30, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
        evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, result.created[0]
        )

    assert evidence.confidence == pytest.approx(0.30)  # min(0.90, 0.30)


@pytest.mark.asyncio
async def test_high_ocr_confidence_never_lifts_low_extraction_confidence(client):
    admin = await _register_admin(client, "ocrspx-d2@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-d2-hash")
    # gap-style (no colon) -> extraction tier 0.45, regardless of OCR confidence
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.99, text="Flow Rate      500 L/min"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
        evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, result.created[0]
        )

    assert evidence.confidence == pytest.approx(0.45)  # min(0.45, 0.99)


# --------------------------------------------------------------------------
# F. OCR-derived evidence cannot be directly VERIFIED
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_derived_evidence_created_as_extracted_never_verified(client):
    admin = await _register_admin(client, "ocrspx-f@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-f-hash")
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
        evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, result.created[0]
        )

    assert evidence.status == ProvenanceStatus.EXTRACTED
    assert evidence.verified_by is None
    assert evidence.verified_at is None


# --------------------------------------------------------------------------
# G. OCR-derived evidence below 0.45 is rejected by the EXISTING guard
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_derived_evidence_below_threshold_blocked_at_verify(client):
    user = await _register_admin(client, "ocrspx-g-user@example.com")
    admin = await _register_admin(client, "ocrspx-g-admin@example.com")
    _category, _spec, product = await _setup(
        client, user, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, user, "ocrspx-g-hash")
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.10, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
        evidence_id = result.created[0]

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence_id}/verify",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "EVIDENCE_CONFIDENCE_TOO_LOW"


# --------------------------------------------------------------------------
# H. OCR-derived evidence at exactly the permitted threshold (0.45)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_derived_evidence_at_exact_threshold_verifies(client):
    user = await _register_admin(client, "ocrspx-h-user@example.com")
    admin = await _register_admin(client, "ocrspx-h-admin@example.com")
    _category, _spec, product = await _setup(
        client, user, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, user, "ocrspx-h-hash")
    # extraction tier 0.90 (exact/colon/unit-resolved) x ocr confidence 0.45 -> final 0.45
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.45, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        result = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
        evidence_id = result.created[0]
        evidence = await product_attribute_evidence_service.get_attribute_evidence(db, evidence_id)
        assert evidence.confidence == pytest.approx(0.45)

    res = await client.post(
        f"/api/v1/products/attribute-evidence/{evidence_id}/verify",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    assert res.json()["data"]["status"] == "verified"


# --------------------------------------------------------------------------
# I. Repeat extraction from the same OCRResult is idempotent
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_repeat_extraction_from_same_ocr_result_is_idempotent(client):
    admin = await _register_admin(client, "ocrspx-i@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-i-hash")
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="Flow Rate: 500 L/min"
    )

    async with AsyncSessionLocal() as db:
        first = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
        second = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )

    assert len(first.created) == 1
    assert second.created == []
    assert second.existing == first.created


# --------------------------------------------------------------------------
# J. Two different OCRResult runs produce separate evidence rows
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_ocr_runs_produce_separate_evidence_rows(client):
    admin = await _register_admin(client, "ocrspx-j@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    observation = await _create_plain_observation(client, admin, "ocrspx-j-hash")
    run_a = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="Flow Rate: 500 L/min"
    )
    run_b = await _create_ocr_result_row(
        observation["id"],
        confidence=0.95,
        text="Flow Rate: 500 L/min",
        engine_version="2.0.0",
    )

    async with AsyncSessionLocal() as db:
        result_a = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=run_a.id,
        )
        result_b = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=run_b.id,
        )

    assert result_a.created[0] != result_b.created[0]


# --------------------------------------------------------------------------
# K. Native evidence and OCR evidence coexist correctly
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_native_and_ocr_evidence_coexist_for_same_document_and_spec(client):
    """The critical regression this milestone must prevent: a native
    extraction's idempotency lookup must never accidentally match an
    OCR-derived row (or vice versa) for the same (product, spec,
    raw_observation) — they share the same raw_observation_id (both
    trace to the same original document) and are distinguished ONLY by
    ocr_result_id."""
    admin = await _register_admin(client, "ocrspx-k@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "L/min", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    # Document-shaped observation: native extraction needs raw_content.pages.
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow Rate: 500 L/min"], content_hash="ocrspx-k-hash"
    )
    ocr_result = await _create_ocr_result_row(
        observation["id"], confidence=0.95, text="Flow Rate: 500 L/min"
    )

    native_res = await _extract(client, admin, product["id"], observation["id"])
    assert native_res.status_code == 200, native_res.text
    native_evidence_id = native_res.json()["data"]["created"][0]

    async with AsyncSessionLocal() as db:
        ocr_result_run = await spec_extraction_service.run_ocr_extraction(
            db,
            product_id=uuid.UUID(product["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
        )
    ocr_evidence_id = str(ocr_result_run.created[0])

    assert native_evidence_id != ocr_evidence_id

    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    evidence_by_id = {e["id"]: e for e in evidence_list}
    assert len(evidence_list) == 2
    assert evidence_by_id[native_evidence_id]["raw_observation_id"] == observation["id"]
    assert evidence_by_id[ocr_evidence_id]["raw_observation_id"] == observation["id"]

    # ocr_result_id is not part of the public API schema (untouched by
    # this milestone) — checked directly via the service layer instead.
    async with AsyncSessionLocal() as db:
        native_evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, uuid.UUID(native_evidence_id)
        )
        ocr_evidence = await product_attribute_evidence_service.get_attribute_evidence(
            db, uuid.UUID(ocr_evidence_id)
        )
    assert native_evidence.ocr_result_id is None
    assert ocr_evidence.ocr_result_id == ocr_result.id

    # Re-running native extraction is still idempotent and does not
    # collide with (or duplicate) the OCR-derived row.
    native_res_again = await _extract(client, admin, product["id"], observation["id"])
    assert native_res_again.json()["data"]["existing"] == [native_evidence_id]
