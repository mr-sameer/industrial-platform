"""
Deterministic PDF -> ProductAttributeEvidence extraction — the smallest
trustworthy layer between an already-extracted RawObservation's page
text (app.collectors.pdf_text_extraction, unchanged by this package)
and a ProductAttributeEvidence candidate (app.services.
product_attribute_evidence_service, also unchanged).

No module in this package touches the database, calls an LLM, performs
OCR, or uses embeddings/vector search — every function here is a pure,
reproducible transformation of already-extracted text plus already-
configured ProductSpecification/SpecificationAlias rows. Orchestration
(loading those rows, calling create_attribute_evidence) lives one
layer up, in app.services.spec_extraction_service — deliberately kept
out of this package so every function here stays independently unit-
testable with no database at all.
"""
