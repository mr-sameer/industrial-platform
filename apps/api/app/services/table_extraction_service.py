"""
Table Intelligence V1 foundation — turns one 2-level regular-grid
table row into exactly one ProductAttributeEvidence row (the approved
Option C "row-as-evidence" architecture), via
app.extraction.table_geometry's deterministic pitch+origin fit and
position-based cell assignment, and the EXISTING, unmodified
app.services.product_attribute_evidence_service.create_ocr_derived_attribute_evidence.

ONE CALL = ONE TARGETED ROW for ONE product, deliberately. A
performance-chart table's rows (JTS-3/11M, JTS-3/05M, ...) are
different real products/SKUs, not different attributes of the same
product — so each row's evidence belongs to a DIFFERENT product_id,
which the existing uq_pae_source_ocr constraint
(UNIQUE(product_id, specification_id, raw_observation_id,
ocr_result_id) — OCR V1 foundation milestone, not modified here)
already accommodates without collision. The OTHER rows given are used
only for multi-row grid-fitting CONSENSUS (a single row's own geometry
is never enough to validate a pitch — see table_geometry's own
docstring) — they never themselves become evidence in this call. A
caller wanting a second row's evidence calls again with that row's own
target_row_identity and (necessarily, since each row is a distinct
product) a different product_id.

Table-region identification and header/data row CLASSIFICATION are
NOT automated here — deliberately. No spike validated a general
technique for separating one table's rows from another, or from
surrounding page prose, without either hardcoding page-specific
anchors or accidentally pooling unrelated tables together (see
table_geometry's own docstring on the discovery process). The caller
supplies already-classified header_rows/data_rows (see
get_table_candidate_rows below for the one piece that IS automated:
turning raw OCR word boxes into row-clustered candidates for the
caller to classify).
"""

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.extraction.table_geometry import (
    CellAssignment,
    CellStatus,
    GridFit,
    GridQualityError,
    WordBox,
    assign_row_to_grid,
    cluster_words_into_rows,
    fit_best_grid,
    is_model_shaped_token,
    resolve_header_semantics,
)
from app.models.product_attribute_evidence import ProductAttributeEvidence
from app.models.provenance_record import ExtractionMethod
from app.services import (
    ocr_pipeline_service,
    ocr_result_service,
    product_attribute_evidence_service,
)
from app.services.tesseract_ocr_service import get_word_boxes

__all__ = [
    "STATUS_AMBIGUOUS_GRID",
    "STATUS_CREATED",
    "STATUS_EXISTING",
    "STATUS_ROW_IDENTITY_NOT_FOUND",
    "STATUS_SEMANTICS_UNRESOLVED",
    "OCRResultNotFoundForTableExtractionError",
    "TableExtractionResult",
    "extract_table_row_evidence",
    "get_table_candidate_rows",
]

STATUS_CREATED = "created"
STATUS_EXISTING = "existing"
STATUS_AMBIGUOUS_GRID = "ambiguous_grid"
STATUS_SEMANTICS_UNRESOLVED = "semantics_unresolved"
STATUS_ROW_IDENTITY_NOT_FOUND = "row_identity_not_found"

_KEY_SANITIZE_RE = re.compile(r"[^a-z0-9]+")


class OCRResultNotFoundForTableExtractionError(Exception):
    pass


@dataclass(frozen=True)
class TableExtractionResult:
    status: str
    evidence_id: uuid.UUID | None = None
    grid_pitch: float | None = None
    grid_score: float | None = None
    message: str | None = None


async def get_table_candidate_rows(
    db: AsyncSession, ocr_result_id: uuid.UUID
) -> list[list[WordBox]]:
    """The one piece of table-region handling that IS automated: real
    word boxes for the page an existing OCRResult was produced from,
    row-clustered (app.extraction.table_geometry.cluster_words_into_rows,
    unmodified from the validated spikes). Callers inspect the
    returned list and choose which indices are header rows and which
    are this table's data rows — see this module's own docstring for
    why that classification step itself is not automated in V1."""
    rendered = await ocr_pipeline_service.get_rendered_page_for_ocr_result(db, ocr_result_id)
    words = get_word_boxes(rendered.image)
    return cluster_words_into_rows(words)


def _find_row_identity(row: list[WordBox]) -> WordBox | None:
    """A row's identity token (e.g. 'JTS-3/11M') by SHAPE only — never
    a lookup against known model names. Exactly zero or exactly one
    candidate is acceptable; zero or MULTIPLE means identity is
    uncertain (instruction: model-number validation stricter than
    ordinary text) and this row must never become evidence."""
    candidates = [w for w in row if is_model_shaped_token(w.text)]
    if len(candidates) != 1:
        return None
    return candidates[0]


def _sanitize_key(label: str) -> str:
    return _KEY_SANITIZE_RE.sub("_", label.strip().lower()).strip("_") or "column"


def _structural_confidence(grid: GridFit, cells: dict[int, CellAssignment]) -> float:
    """Row-level structural confidence, deliberately separate from OCR
    recognition confidence (which ocr_result.confidence already
    carries, and which create_ocr_derived_attribute_evidence combines
    with this value via the EXISTING, unmodified ceiling function — see
    that call site below). Combines: (a) the fitted grid's own overall
    quality score, (b) how COMPLETE this specific row is (present
    cells / expected cells — a row missing most of its data is less
    trustworthy even against a high-quality grid), (c) how TIGHT this
    row's own present-cell positions are against the ideal grid lines.
    Never higher than the grid's own score."""
    present = [c for c in cells.values() if c.status == CellStatus.PRESENT]
    if not cells:
        return 0.0
    completeness = len(present) / len(cells)
    deviations = [c.structural_deviation for c in present if c.structural_deviation is not None]
    if deviations and grid.tolerance > 0:
        avg_dev_fraction = sum(deviations) / len(deviations) / grid.tolerance
        tightness = max(0.0, 1.0 - avg_dev_fraction)
    else:
        tightness = 0.0
    return grid.score * completeness * tightness


async def extract_table_row_evidence(
    db: AsyncSession,
    *,
    product_id: uuid.UUID,
    specification_id: uuid.UUID,
    raw_observation_id: uuid.UUID,
    ocr_result_id: uuid.UUID,
    target_row_identity: str,
    header_rows: list[list[WordBox]],
    data_rows: list[list[WordBox]],
    table_title: str,
) -> TableExtractionResult:
    """
    Fits a grid across ALL of data_rows (multi-row consensus — see
    table_geometry.fit_best_grid), then creates evidence for ONLY the
    row whose identity token exactly matches target_row_identity (see
    this module's own docstring for why one call handles one row).

    Fails closed, creating NO evidence, when:
    - the grid fit doesn't clear its quality gates (GridQualityError)
    - header semantics cannot be independently resolved
      (resolve_header_semantics returns None — the CTSS case)
    - target_row_identity doesn't exactly match exactly one data row's
      own shape-validated identity token

    raw_observation_id/ocr_result_id consistency, VERIFIED status
    exclusion, and the OCR confidence ceiling are all enforced by the
    existing, unmodified
    product_attribute_evidence_service.create_ocr_derived_attribute_evidence
    this function delegates evidence creation to — none of that is
    reimplemented here.
    """
    ocr_result = await ocr_result_service.get_ocr_result(db, ocr_result_id)
    if ocr_result is None:
        raise OCRResultNotFoundForTableExtractionError(str(ocr_result_id))

    try:
        grid = fit_best_grid(data_rows)
    except GridQualityError as exc:
        return TableExtractionResult(status=STATUS_AMBIGUOUS_GRID, message=str(exc))

    column_indices = sorted(grid.occupied_indices)
    header_labels = resolve_header_semantics(header_rows, grid, column_indices)
    if header_labels is None:
        return TableExtractionResult(
            status=STATUS_SEMANTICS_UNRESOLVED,
            grid_pitch=grid.pitch,
            grid_score=grid.score,
            message="Grid geometry recovered but header semantics could not be independently resolved.",
        )

    target_row: list[WordBox] | None = None
    identity_token: WordBox | None = None
    for row in data_rows:
        candidate_identity = _find_row_identity(row)
        if candidate_identity is not None and candidate_identity.text == target_row_identity:
            target_row, identity_token = row, candidate_identity
            break
    if target_row is None or identity_token is None:
        return TableExtractionResult(
            status=STATUS_ROW_IDENTITY_NOT_FOUND,
            grid_pitch=grid.pitch,
            grid_score=grid.score,
            message=f"No data row has an unambiguous identity token matching {target_row_identity!r}.",
        )

    cells = assign_row_to_grid(target_row, grid, column_indices)
    structural_confidence = _structural_confidence(grid, cells)

    row_y_values = [w.y for w in target_row] + [w.y + w.height for w in target_row]
    extraction_context: dict[str, object] = {
        "table_title": table_title,
        "page": ocr_result.page_number,
        "row_y_range": [min(row_y_values), max(row_y_values)],
        "row_identity": identity_token.text,
        "grid": {
            "pitch": grid.pitch,
            "origin": grid.origin_phase,
            "quality_score": grid.score,
            "confidence": structural_confidence,
        },
        "cells": {
            (_sanitize_key(header_labels[idx]) if idx in header_labels else f"column_{idx}"): {
                "value": cell.value,
                "column_path": [header_labels[idx]] if idx in header_labels else None,
                "x_center": cell.x_center,
                "ocr_confidence": cell.ocr_confidence,
                "status": cell.status,
                "ambiguous": cell.status == CellStatus.AMBIGUOUS,
                "missing": cell.status == CellStatus.MISSING,
                "not_applicable": cell.status == CellStatus.NOT_APPLICABLE,
            }
            for idx, cell in cells.items()
        },
    }

    # Pre-check against the EXACT same 4-tuple
    # create_ocr_derived_attribute_evidence itself uses for idempotency
    # (its own docstring: matches uq_pae_source_ocr) — read-only, changes
    # nothing, only lets this function report created vs existing
    # accurately rather than guessing from the returned row's content.
    pre_existing = (
        await db.execute(
            select(ProductAttributeEvidence.id).where(
                ProductAttributeEvidence.product_id == product_id,
                ProductAttributeEvidence.specification_id == specification_id,
                ProductAttributeEvidence.raw_observation_id == raw_observation_id,
                ProductAttributeEvidence.ocr_result_id == ocr_result_id,
            )
        )
    ).scalar_one_or_none()

    (
        evidence,
        _conflict,
    ) = await product_attribute_evidence_service.create_ocr_derived_attribute_evidence(
        db,
        product_id=product_id,
        specification_id=specification_id,
        raw_observation_id=raw_observation_id,
        ocr_result_id=ocr_result_id,
        value_observed=identity_token.text,
        extraction_method=ExtractionMethod.RULE_BASED,
        extraction_confidence=structural_confidence,
        extraction_context=extraction_context,
    )
    status = STATUS_EXISTING if pre_existing is not None else STATUS_CREATED
    return TableExtractionResult(
        status=status,
        evidence_id=evidence.id,
        grid_pitch=grid.pitch,
        grid_score=grid.score,
    )
