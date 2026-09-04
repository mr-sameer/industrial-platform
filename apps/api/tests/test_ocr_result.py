"""
OCRResult tests — V1 OCR data model + result foundation (approved OCR
Architecture Design Proposal). Covers OCRResult persistence, its
RESTRICT relationship to RawObservation, get_or_create_ocr_result's
application-level idempotency, the OCR confidence ceiling function, and
multiple OCR runs coexisting for the same (raw_observation, page).

No real OCR engine is involved anywhere in this file — every OCRResult
here is created with fake/mock text and confidence, exactly matching
this milestone's scope (data model + foundation only).
"""

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.session import AsyncSessionLocal
from app.extraction.ocr_confidence import apply_ocr_confidence_ceiling
from app.models.ocr_result import OCRResult
from app.models.raw_observation import RawObservation
from app.services import ocr_result_service
from tests.test_companies import _register_verified
from tests.test_product_attribute_evidence import _setup_observation


async def _make_observation(client, email: str, content_hash: str = "ocr-hash") -> dict:
    user = await _register_verified(client, email)
    return await _setup_observation(client, user, content_hash=content_hash)


# --------------------------------------------------------------------------
# A. Persistence
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ocr_result_persistence(client):
    observation = await _make_observation(client, "ocr-persist@example.com")
    async with AsyncSessionLocal() as db:
        ocr_result = await ocr_result_service.create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=4,
            text="Power Range : 0.55 kW - 2.2 kW",
            confidence=0.82,
            engine_name="fake-engine",
            engine_version="1.0.0",
            render_dpi=300,
            render_params={"renderer": "fake-renderer", "color_mode": "rgb"},
        )
        assert ocr_result.id is not None
        assert ocr_result.raw_observation_id == uuid.UUID(observation["id"])
        assert ocr_result.page_number == 4
        assert ocr_result.text == "Power Range : 0.55 kW - 2.2 kW"
        assert ocr_result.confidence == 0.82
        assert ocr_result.confidence_detail is None
        assert ocr_result.engine_name == "fake-engine"
        assert ocr_result.engine_version == "1.0.0"
        assert ocr_result.render_dpi == 300
        assert ocr_result.render_params == {"renderer": "fake-renderer", "color_mode": "rgb"}
        assert ocr_result.created_at is not None

        fetched = await ocr_result_service.get_ocr_result(db, ocr_result.id)
        assert fetched is not None
        assert fetched.id == ocr_result.id


@pytest.mark.asyncio
async def test_ocr_result_create_rejects_unknown_raw_observation(client):
    async with AsyncSessionLocal() as db:
        with pytest.raises(ocr_result_service.RawObservationNotFoundForOcrResultError):
            await ocr_result_service.create_ocr_result(
                db,
                raw_observation_id=uuid.uuid4(),
                page_number=1,
                text="anything",
                confidence=0.5,
                engine_name="fake-engine",
                engine_version="1.0.0",
                render_dpi=300,
            )


# --------------------------------------------------------------------------
# B. FK / RESTRICT behavior
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_raw_observation_deletion_blocked_when_referenced_by_ocr_result(client):
    """Mirrors test_product_attribute_evidence.py's own
    test_raw_observation_deletion_blocked_when_referenced_by_evidence —
    identical RESTRICT behavior, now also enforced via OCRResult."""
    observation = await _make_observation(client, "ocr-restrict@example.com", "ocr-restrict-hash")
    async with AsyncSessionLocal() as db:
        await ocr_result_service.create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=1,
            text="text",
            confidence=0.9,
            engine_name="fake-engine",
            engine_version="1.0.0",
            render_dpi=300,
        )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RawObservation).where(RawObservation.id == uuid.UUID(observation["id"]))
        )
        row = result.scalar_one()
        await db.delete(row)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()


# --------------------------------------------------------------------------
# C. get-or-create / idempotency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_or_create_ocr_result_reuses_matching_run(client):
    observation = await _make_observation(client, "ocr-getorcreate@example.com", "ocr-goc-hash")
    async with AsyncSessionLocal() as db:
        first = await ocr_result_service.get_or_create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=2,
            text="first pass text",
            confidence=0.7,
            engine_name="fake-engine",
            engine_version="1.0.0",
            render_dpi=300,
        )
        second = await ocr_result_service.get_or_create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=2,
            text="a different text that should be IGNORED since the run already exists",
            confidence=0.99,
            engine_name="fake-engine",
            engine_version="1.0.0",
            render_dpi=300,
        )
        assert first.id == second.id
        assert second.text == "first pass text"  # not mutated by the second call
        assert second.confidence == 0.7


@pytest.mark.asyncio
async def test_get_or_create_ocr_result_force_reprocess_creates_new_row(client):
    observation = await _make_observation(client, "ocr-force@example.com", "ocr-force-hash")
    async with AsyncSessionLocal() as db:
        first = await ocr_result_service.get_or_create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=2,
            text="first pass",
            confidence=0.7,
            engine_name="fake-engine",
            engine_version="1.0.0",
            render_dpi=300,
        )
        second = await ocr_result_service.get_or_create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=2,
            text="forced re-run",
            confidence=0.95,
            engine_name="fake-engine",
            engine_version="1.0.0",
            render_dpi=300,
            force_reprocess=True,
        )
        assert first.id != second.id
        assert second.text == "forced re-run"


# --------------------------------------------------------------------------
# D. Confidence ceiling, including the 0.45 boundary
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("extraction_confidence", "ocr_confidence", "expected"),
    [
        (0.90, 0.90, 0.90),
        (0.90, 0.20, 0.20),  # low OCR confidence drags a high extraction match down
        (0.20, 0.90, 0.20),  # high OCR confidence never lifts a low extraction match
        (0.45, 0.45, 0.45),  # exact 0.45/0.45 boundary
        (0.70, 0.44, 0.44),  # OCR confidence just below the guard drags evidence below it
        (0.50, 0.50, 0.50),
        (1.0, 1.0, 1.0),
        (0.0, 1.0, 0.0),
    ],
)
def test_ocr_confidence_ceiling(
    extraction_confidence: float, ocr_confidence: float, expected: float
) -> None:
    assert apply_ocr_confidence_ceiling(extraction_confidence, ocr_confidence) == expected


def test_ocr_confidence_ceiling_clamps_out_of_range_raw_confidence() -> None:
    assert apply_ocr_confidence_ceiling(0.90, 1.5) == 0.90
    assert apply_ocr_confidence_ceiling(0.90, -0.5) == 0.0


# --------------------------------------------------------------------------
# E. Multiple OCR runs for the same source/page
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_ocr_runs_for_same_source_and_page_coexist(client):
    """A better engine or higher DPI re-run against the SAME
    (raw_observation, page) is a new, independent row — never an
    overwrite of the old one."""
    observation = await _make_observation(client, "ocr-multi-run@example.com", "ocr-multi-hash")
    async with AsyncSessionLocal() as db:
        run_v1 = await ocr_result_service.create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=4,
            text="low-dpi noisy text",
            confidence=0.4,
            engine_name="fake-engine",
            engine_version="1.0.0",
            render_dpi=150,
        )
        run_v2 = await ocr_result_service.create_ocr_result(
            db,
            raw_observation_id=uuid.UUID(observation["id"]),
            page_number=4,
            text="high-dpi clean text",
            confidence=0.95,
            engine_name="fake-engine",
            engine_version="2.0.0",
            render_dpi=300,
        )
        assert run_v1.id != run_v2.id

        result = await db.execute(
            select(OCRResult).where(
                OCRResult.raw_observation_id == uuid.UUID(observation["id"]),
                OCRResult.page_number == 4,
            )
        )
        rows = list(result.scalars().all())
        assert {r.id for r in rows} == {run_v1.id, run_v2.id}
        # the older run's row is untouched, not mutated by the newer one
        assert run_v1.text == "low-dpi noisy text"
        assert run_v1.confidence == 0.4
