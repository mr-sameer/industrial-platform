"""
Document upload + DocumentExtractionAdapter tests — Checkpoint 1 of the
approved Document -> Structured Product Data design review. Covers the
generic PDF upload endpoint (RBAC, magic-byte validation, size limit,
sha256 computation, storage round-trip) and the acquisition-adapter
foundation (sha256 re-verification, deterministic page-level text
extraction, idempotency via the existing, unmodified acquisition_service
pipeline, and safe failure on a malformed PDF). Deliberately stops
before any product-attribute extraction — not built in this checkpoint.
Reuses test_companies.py/test_acquisition.py's established fixtures.
"""

import hashlib
import io

import pytest
from PIL import Image

from app.collectors.base import NonRetryableCollectorError
from app.collectors.document_extraction_adapter import DocumentExtractionAdapter
from app.core.storage import get_storage_backend
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _register_verified


def _build_test_pdf(pages_text: list[str]) -> bytes:
    """
    Hand-assembled, minimal, VALID multi-page PDF with a real text
    object per page — entirely synthetic structural content ("Test
    Page N", "Alpha content", ...), never real supplier/product data.
    Used only to exercise the extraction pipeline deterministically
    without a binary fixture file or a new PDF-authoring dependency.
    """
    n = len(pages_text)
    font_obj_num = 3 + n * 2
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(n))

    objs: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
    }
    for i, text in enumerate(pages_text):
        page_num = 3 + i * 2
        content_num = 4 + i * 2
        escaped = text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        stream = f"BT /F1 12 Tf 20 700 Td ({escaped}) Tj ET".encode()
        objs[page_num] = (
            f"<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 {font_obj_num} 0 R >> >> "
            f"/MediaBox [0 0 612 792] /Contents {content_num} 0 R >>"
        ).encode()
        objs[content_num] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )
    objs[font_obj_num] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    header = b"%PDF-1.4\n"
    body = bytearray(header)
    offsets: dict[int, int] = {}
    pos = len(header)
    for num in sorted(objs):
        offsets[num] = pos
        obj_bytes = f"{num} 0 obj\n".encode() + objs[num] + b"\nendobj\n"
        body += obj_bytes
        pos += len(obj_bytes)

    xref_start = pos
    total_objs = max(objs) + 1
    xref_lines = [f"xref\n0 {total_objs}\n", "0000000000 65535 f \n"]
    for num in range(1, total_objs):
        offset = offsets.get(num)
        xref_lines.append(
            f"{offset:010d} 00000 n \n" if offset is not None else "0000000000 65535 f \n"
        )
    xref = "".join(xref_lines).encode()
    trailer = (
        f"trailer\n<< /Size {total_objs} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF".encode()
    )
    return bytes(body) + xref + trailer


def _valid_test_pdf_bytes() -> bytes:
    return _build_test_pdf(["Test Page One Content", "Test Page Two Content"])


async def _upload(client, user, data: bytes, filename: str = "catalogue.pdf"):
    return await client.post(
        "/api/v1/documents",
        files={"file": (filename, data, "application/pdf")},
        headers=_auth_headers(user),
    )


def _source_payload(name: str = "Test Document Source") -> dict:
    return {
        "name": name,
        "source_class": "company_owned",
        "collection_method": "structured_file",
        "reliability_weight": 0.7,
    }


async def _create_source(client, admin, **overrides) -> dict:
    payload = {**_source_payload(), **overrides}
    res = await client.post("/api/v1/sources", json=payload, headers=_auth_headers(admin))
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _create_extraction_job(client, actor, source_id: str, upload: dict):
    return await client.post(
        "/api/v1/acquisition/jobs",
        json={
            "source_id": source_id,
            "collector_type": "document_extraction",
            "requested_scope": {
                "storage_key": upload["storage_key"],
                "sha256": upload["sha256"],
                "filename": upload["filename"],
            },
        },
        headers=_auth_headers(actor),
    )


# --------------------------------------------------------------------------
# Upload endpoint
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_requires_auth(client):
    res = await client.post(
        "/api/v1/documents",
        files={"file": ("catalogue.pdf", _valid_test_pdf_bytes(), "application/pdf")},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_non_admin_cannot_upload_document(client):
    user = await _register_verified(client, "doc-nonadmin@example.com")
    res = await _upload(client, user, _valid_test_pdf_bytes())
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_upload_valid_pdf(client):
    admin = await _register_admin(client, "doc-admin@example.com")
    data = _valid_test_pdf_bytes()
    res = await _upload(client, admin, data, filename="Real Catalogue!!.pdf")
    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["content_type"] == "application/pdf"
    assert body["size_bytes"] == len(data)
    assert body["filename"] == "Real Catalogue!!.pdf"
    assert len(body["sha256"]) == 64
    assert body["storage_key"]
    assert not body["storage_key"].startswith("/")  # never a raw filesystem path


@pytest.mark.asyncio
async def test_sha256_is_computed_from_actual_bytes(client):
    admin = await _register_admin(client, "doc-sha256@example.com")
    data = _valid_test_pdf_bytes()
    res = await _upload(client, admin, data)
    assert res.json()["data"]["sha256"] == hashlib.sha256(data).hexdigest()


@pytest.mark.asyncio
async def test_invalid_magic_bytes_rejected(client):
    admin = await _register_admin(client, "doc-badmagic@example.com")
    res = await _upload(client, admin, b"this is not a pdf or an image at all")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_oversized_document_rejected(client):
    admin = await _register_admin(client, "doc-oversized@example.com")
    oversized = b"%PDF-1.4\n" + b"0" * (16 * 1024 * 1024)
    res = await _upload(client, admin, oversized)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "FILE_TOO_LARGE"


@pytest.mark.asyncio
async def test_non_pdf_content_type_rejected_even_if_it_were_an_image(client):
    """A genuinely-valid image (a real, well-formed PNG) must still be
    rejected in this checkpoint — PDF only, per the approved design's
    explicit scope."""
    admin = await _register_admin(client, "doc-notpdf@example.com")
    buffer = io.BytesIO()
    Image.new("RGB", (1, 1)).save(buffer, format="PNG")
    res = await _upload(client, admin, buffer.getvalue(), filename="not-a-pdf.png")
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "UNSUPPORTED_DOCUMENT_TYPE"


@pytest.mark.asyncio
async def test_stored_file_can_be_retrieved_through_storage_backend(client):
    admin = await _register_admin(client, "doc-retrieve@example.com")
    data = _valid_test_pdf_bytes()
    res = await _upload(client, admin, data)
    key = res.json()["data"]["storage_key"]
    storage = get_storage_backend()
    assert storage.read_bytes(key) == data


# --------------------------------------------------------------------------
# Adapter unit tests
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_extracts_page_level_text_and_preserves_page_numbers(client):
    admin = await _register_admin(client, "doc-adapter-pages@example.com")
    data = _build_test_pdf(["Alpha content", "Beta content", "Gamma content"])
    upload = (await _upload(client, admin, data)).json()["data"]

    adapter = DocumentExtractionAdapter()
    items = adapter.collect(
        {
            "storage_key": upload["storage_key"],
            "sha256": upload["sha256"],
            "filename": upload["filename"],
        }
    )
    assert len(items) == 1
    raw = items[0].raw_content
    assert raw["page_count"] == 3
    assert [p["page"] for p in raw["pages"]] == [1, 2, 3]
    assert raw["pages"][0]["text"].strip() == "Alpha content"
    assert raw["pages"][1]["text"].strip() == "Beta content"
    assert raw["pages"][2]["text"].strip() == "Gamma content"
    assert items[0].external_identifier == upload["sha256"]


@pytest.mark.asyncio
async def test_adapter_rejects_sha256_mismatch(client):
    admin = await _register_admin(client, "doc-adapter-mismatch@example.com")
    upload = (await _upload(client, admin, _valid_test_pdf_bytes())).json()["data"]

    adapter = DocumentExtractionAdapter()
    with pytest.raises(NonRetryableCollectorError):
        adapter.collect(
            {
                "storage_key": upload["storage_key"],
                "sha256": "0" * 64,
                "filename": upload["filename"],
            }
        )


def test_adapter_rejects_missing_storage_key():
    adapter = DocumentExtractionAdapter()
    with pytest.raises(NonRetryableCollectorError):
        adapter.collect(
            {
                "storage_key": "source-documents/uploads/does-not-exist.pdf",
                "sha256": "a" * 64,
                "filename": "x.pdf",
            }
        )


def test_adapter_validate_config_requires_all_fields():
    adapter = DocumentExtractionAdapter()
    with pytest.raises(NonRetryableCollectorError):
        adapter.validate_config({"storage_key": "x"})


@pytest.mark.asyncio
async def test_adapter_fails_safely_on_malformed_pdf(client):
    admin = await _register_admin(client, "doc-malformed@example.com")
    # Passes the upload endpoint's magic-byte check (starts with %PDF-)
    # but is not a structurally valid PDF — exactly the boundary this
    # checkpoint's design expects: upload accepts "looks like a PDF,"
    # extraction is where genuine structural invalidity is discovered.
    malformed = b"%PDF-1.4\nthis is garbage, not a real pdf body\n%%EOF"
    upload = (await _upload(client, admin, malformed)).json()["data"]

    adapter = DocumentExtractionAdapter()
    with pytest.raises(NonRetryableCollectorError):
        adapter.collect(
            {
                "storage_key": upload["storage_key"],
                "sha256": upload["sha256"],
                "filename": upload["filename"],
            }
        )


# --------------------------------------------------------------------------
# Full acquisition pipeline integration
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquisition_creates_expected_raw_observation(client):
    admin = await _register_admin(client, "doc-job-admin@example.com")
    data = _build_test_pdf(["Flow Rate section content"])
    upload = (await _upload(client, admin, data, filename="catalogue.pdf")).json()["data"]
    source = await _create_source(client, admin)

    res = await _create_extraction_job(client, admin, source["id"], upload)
    assert res.status_code == 201, res.text
    job = res.json()["data"]
    assert job["status"] == "succeeded"
    assert job["result_count"] == 1

    events = await client.get(
        f"/api/v1/acquisition/jobs/{job['id']}/events", headers=_auth_headers(admin)
    )
    raw_observation_id = events.json()["data"]["items"][0]["raw_observation_id"]

    observation = await client.get(
        f"/api/v1/acquisition/observations/{raw_observation_id}", headers=_auth_headers(admin)
    )
    assert observation.status_code == 200
    data_body = observation.json()["data"]
    content = data_body["raw_content"]
    assert content["filename"] == "catalogue.pdf"
    assert content["sha256"] == upload["sha256"]
    assert content["page_count"] == 1
    assert content["pages"][0]["text"].strip() == "Flow Rate section content"
    assert data_body["collection_method_used"] == "structured_file"
    assert data_body["external_reference"] == upload["sha256"]


@pytest.mark.asyncio
async def test_same_document_is_idempotent(client):
    admin = await _register_admin(client, "doc-idempotent@example.com")
    data = _valid_test_pdf_bytes()
    upload = (await _upload(client, admin, data)).json()["data"]
    source = await _create_source(client, admin)

    first = await _create_extraction_job(client, admin, source["id"], upload)
    assert first.json()["data"]["result_count"] == 1

    second = await _create_extraction_job(client, admin, source["id"], upload)
    assert second.status_code == 201
    second_job = second.json()["data"]
    assert second_job["result_count"] == 0
    assert second_job["skipped_count"] == 1
    assert second_job["status"] == "succeeded"


@pytest.mark.asyncio
async def test_malformed_pdf_job_fails_safely_without_crashing(client):
    admin = await _register_admin(client, "doc-job-malformed@example.com")
    malformed = b"%PDF-1.4\nnot really a pdf\n%%EOF"
    upload = (await _upload(client, admin, malformed)).json()["data"]
    source = await _create_source(client, admin)

    res = await _create_extraction_job(client, admin, source["id"], upload)
    assert res.status_code == 201, res.text
    job = res.json()["data"]
    assert job["status"] == "failed"
    assert job["retry_count"] == 0  # non-retryable — zero retries, no fabricated success


@pytest.mark.asyncio
async def test_extraction_job_requires_admin(client):
    user = await _register_verified(client, "doc-job-nonadmin@example.com")
    admin = await _register_admin(client, "doc-job-nonadmin-admin@example.com")
    upload = (await _upload(client, admin, _valid_test_pdf_bytes())).json()["data"]
    source = await _create_source(client, admin)
    res = await _create_extraction_job(client, user, source["id"], upload)
    assert res.status_code == 403
