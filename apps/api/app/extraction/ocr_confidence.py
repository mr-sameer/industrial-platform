"""
OCR confidence — deliberately a separate, explicit module from
app.extraction.confidence. That module's four tiers (0.90/0.70/0.45/
0.20) describe how certain deterministic extraction is that it matched
the right label to the right value, GIVEN clean input text. OCR
introduces an independent, upstream uncertainty — is this even the
right character sequence at all — that has to be combined with, never
confused for, extraction certainty (approved OCR Architecture Design
Proposal, finding #4/#8.5).

Combined as a CEILING, not a blend: `apply_ocr_confidence_ceiling`
computes min(extraction_confidence, ocr_confidence_mapped). A high OCR
confidence can never let a naturally-ambiguous extraction climb higher
than extraction alone would allow; a low OCR confidence CAN drag down
an otherwise-high extraction match. The result is what gets stored as
ProductAttributeEvidence.confidence — by the time it reaches
app.services.product_attribute_evidence_service.MIN_VERIFIABLE_CONFIDENCE,
OCR uncertainty has already been folded in, so that guard needs no
knowledge of OCR at all.

map_ocr_confidence is an explicit, small, versioned mapping — not a
raw pass-through of an OCR engine's native 0-1 (or 0-100) score, since
different engines/versions calibrate their own confidence numbers
differently and a raw pass-through would let that calibration silently
become the de facto verification threshold. V1 uses a simple identity-
clamped mapping (engines are already expected to report 0.0-1.0); this
is the seam a future engine-specific calibration would replace.
"""


def map_ocr_confidence(raw_ocr_confidence: float) -> float:
    """Maps an OCR engine's native confidence onto the same 0.0-1.0
    scale app.extraction.confidence's tiers live on. V1: clamp only —
    see this module's own docstring for why this is a deliberate seam,
    not an assumption that every future engine needs no calibration."""
    if raw_ocr_confidence < 0.0:
        return 0.0
    if raw_ocr_confidence > 1.0:
        return 1.0
    return raw_ocr_confidence


def apply_ocr_confidence_ceiling(extraction_confidence: float, raw_ocr_confidence: float) -> float:
    """The single combination point between extraction confidence and
    OCR confidence — see this module's own docstring. Always a min(),
    never an average or weighted blend."""
    return min(extraction_confidence, map_ocr_confidence(raw_ocr_confidence))


__all__ = ["apply_ocr_confidence_ceiling", "map_ocr_confidence"]
