"""
OCR pipeline orchestration tests — app.services.ocr_pipeline_service.
Exercises the real, composed RawObservation -> rasterization -> Tesseract
-> OCRResult chain against REAL, uploaded, document-backed
RawObservations (via tests.test_document_extraction's established
upload/extraction-job pattern) — not mocked at any layer, since this
module's whole job is wiring the three real pieces together correctly.
"""

import uuid

import pytest

from app.db.session import AsyncSessionLocal
from app.models.provenance_record import ExtractionMethod
from app.services import (
    ocr_pipeline_service,
    product_attribute_evidence_service,
)
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers
from tests.test_document_extraction import (
    _build_test_pdf,
    _create_extraction_job,
    _create_source,
    _upload,
)
from tests.test_product_attribute_evidence import _setup_product_with_spec


async def _create_document_observation(client, admin, pages_text: list[str]) -> dict:
    data = _build_test_pdf(pages_text)
    upload = (await _upload(client, admin, data)).json()["data"]
    source = await _create_source(client, admin)
    job_res = await _create_extraction_job(client, admin, source["id"], upload)
    assert job_res.status_code == 201, job_res.text
    job = job_res.json()["data"]
    events = await client.get(
        f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
    )
    raw_observation_id = events.json()["data"]["items"][0]["raw_observation_id"]
    return {"id": raw_observation_id, "pages_text": pages_text}


# --------------------------------------------------------------------------
# D. OCRResult creation (real end-to-end pipeline)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_creates_ocr_result_from_real_document(client):
    admin = await _register_admin(client, "ocrpipe-create@example.com")
    observation = await _create_document_observation(client, admin, ["Flow Rate: 500 LPM"])

    async with AsyncSessionLocal() as db:
        result = await ocr_pipeline_service.process_raw_observation_page(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=1,
        )

    assert result.id is not None
    assert result.raw_observation_id == uuid.UUID(observation["id"])
    assert result.page_number == 1
    assert result.engine_name == "tesseract"
    assert result.engine_version
    assert result.render_dpi == ocr_pipeline_service.DEFAULT_DPI
    assert 0.0 <= result.confidence <= 1.0
    assert "Flow" in result.text or "Rate" in result.text  # real OCR round-trip


# --------------------------------------------------------------------------
# H. OCR idempotency (pipeline level)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_reuses_existing_ocr_result_for_same_params(client):
    admin = await _register_admin(client, "ocrpipe-idempotent@example.com")
    observation = await _create_document_observation(client, admin, ["Idempotency check text"])

    async with AsyncSessionLocal() as db:
        first = await ocr_pipeline_service.process_raw_observation_page(
            db, raw_observation_id=uuid.UUID(observation["id"]), page_number=1
        )
        second = await ocr_pipeline_service.process_raw_observation_page(
            db, raw_observation_id=uuid.UUID(observation["id"]), page_number=1
        )

    assert first.id == second.id


# --------------------------------------------------------------------------
# I. Multiple OCR runs
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_different_dpi_creates_separate_ocr_results(client):
    admin = await _register_admin(client, "ocrpipe-multirun@example.com")
    observation = await _create_document_observation(client, admin, ["Multi-run text content"])

    async with AsyncSessionLocal() as db:
        low_dpi = await ocr_pipeline_service.process_raw_observation_page(
            db, raw_observation_id=uuid.UUID(observation["id"]), page_number=1, dpi=150
        )
        high_dpi = await ocr_pipeline_service.process_raw_observation_page(
            db, raw_observation_id=uuid.UUID(observation["id"]), page_number=1, dpi=300
        )

    assert low_dpi.id != high_dpi.id
    assert low_dpi.render_dpi == 150
    assert high_dpi.render_dpi == 300


@pytest.mark.asyncio
async def test_pipeline_force_reprocess_creates_new_ocr_result(client):
    admin = await _register_admin(client, "ocrpipe-force@example.com")
    observation = await _create_document_observation(client, admin, ["Force reprocess text"])

    async with AsyncSessionLocal() as db:
        first = await ocr_pipeline_service.process_raw_observation_page(
            db, raw_observation_id=uuid.UUID(observation["id"]), page_number=1
        )
        second = await ocr_pipeline_service.process_raw_observation_page(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=1,
            force_reprocess=True,
        )

    assert first.id != second.id


# --------------------------------------------------------------------------
# Failure handling (fail closed — no partial/fake OCRResult ever created)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_rejects_unknown_raw_observation(client):
    async with AsyncSessionLocal() as db:
        with pytest.raises(ocr_pipeline_service.RawObservationNotFoundError):
            await ocr_pipeline_service.process_raw_observation_page(
                db, raw_observation_id=uuid.uuid4(), page_number=1
            )


@pytest.mark.asyncio
async def test_pipeline_rejects_raw_observation_without_storage_key(client):
    """A manual/API-collected RawObservation (never a document) has no
    storage_key — the pipeline must reject it explicitly, never guess
    at a document that doesn't exist for it."""
    admin = await _register_admin(client, "ocrpipe-nostoragekey@example.com")
    source = await _create_source(client, admin)
    res = await client.post(
        f"/api/v1/sources/{source['id']}/observations",
        json={
            "source_id": source["id"],
            "raw_content": {"value": "not a document at all"},
            "content_hash": "no-storage-key-hash",
            "collection_method_used": "api",
            "collected_at": "2026-08-08T00:00:00Z",
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    observation_id = res.json()["data"]["id"]

    async with AsyncSessionLocal() as db:
        with pytest.raises(ocr_pipeline_service.InvalidRawObservationForOcrError):
            await ocr_pipeline_service.process_raw_observation_page(
                db, raw_observation_id=uuid.UUID(observation_id), page_number=1
            )


@pytest.mark.asyncio
async def test_pipeline_rejects_out_of_range_page(client):
    admin = await _register_admin(client, "ocrpipe-pagerange@example.com")
    observation = await _create_document_observation(client, admin, ["Only one page here"])

    async with AsyncSessionLocal() as db:
        from app.services.pdf_rasterization_service import PageOutOfRangeError

        with pytest.raises(PageOutOfRangeError):
            await ocr_pipeline_service.process_raw_observation_page(
                db, raw_observation_id=uuid.UUID(observation["id"]), page_number=99
            )


@pytest.mark.asyncio
async def test_pipeline_failure_creates_no_ocr_result_row(client):
    """Fail-closed guarantee: after a rejected call, zero OCRResult rows
    exist for that RawObservation — no partial/fake row was created."""
    admin = await _register_admin(client, "ocrpipe-failclosed@example.com")
    observation = await _create_document_observation(client, admin, ["Fail closed check"])

    async with AsyncSessionLocal() as db:
        from app.services.pdf_rasterization_service import PageOutOfRangeError

        with pytest.raises(PageOutOfRangeError):
            await ocr_pipeline_service.process_raw_observation_page(
                db, raw_observation_id=uuid.UUID(observation["id"]), page_number=99
            )

        from sqlalchemy import select

        from app.models.ocr_result import OCRResult

        result = await db.execute(
            select(OCRResult).where(OCRResult.raw_observation_id == uuid.UUID(observation["id"]))
        )
        assert result.scalar_one_or_none() is None


# --------------------------------------------------------------------------
# K. OCRResult -> ProductAttributeEvidence association (real pipeline output)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_ocr_result_can_back_product_attribute_evidence(client):
    """End-to-end: a REAL OCRResult produced by the actual pipeline (not
    a fake one) correctly backs evidence via the existing (unmodified)
    create_ocr_derived_attribute_evidence from the OCR V1 foundation."""
    user = await _register_admin(client, "ocrpipe-evidence@example.com")
    _category, spec, product = await _setup_product_with_spec(client, user)
    observation = await _create_document_observation(client, user, ["Flow Rate: 500 LPM"])

    async with AsyncSessionLocal() as db:
        ocr_result = await ocr_pipeline_service.process_raw_observation_page(
            db, raw_observation_id=uuid.UUID(observation["id"]), page_number=1
        )
        (
            evidence,
            _conflict,
        ) = await product_attribute_evidence_service.create_ocr_derived_attribute_evidence(
            db,
            product_id=uuid.UUID(product["id"]),
            specification_id=uuid.UUID(spec["id"]),
            raw_observation_id=uuid.UUID(observation["id"]),
            ocr_result_id=ocr_result.id,
            value_observed="500",
            extraction_method=ExtractionMethod.RULE_BASED,
            extraction_confidence=0.90,
        )

    assert evidence.ocr_result_id == ocr_result.id
    assert evidence.raw_observation_id == uuid.UUID(observation["id"])
