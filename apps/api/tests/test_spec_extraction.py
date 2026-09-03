"""
Deterministic specification extraction tests — the approved milestone
turning an already-extracted RawObservation's page text into
ProductAttributeEvidence(EXTRACTED, RULE_BASED) rows against an
already-existing Product's already-existing ProductSpecifications.
Reuses test_product_graph.py/test_provenance.py/test_acquisition.py/
test_document_extraction.py/test_companies.py's established fixtures
rather than duplicating them.

Pure-function tests against app.extraction's modules run with no
database and no client at all (fast, isolate parsing/validation/
confidence logic). Integration tests exercise the real
POST /products/{id}/extract-specifications route end to end, including
one true PDF-upload-to-evidence run through the unmodified
DocumentExtractionAdapter pipeline.
"""

import uuid

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.extraction import label_matching, patterns, unit_conversion, validation
from app.extraction.confidence import compute_confidence
from app.models.product_attribute import ProductAttribute
from app.models.product_specification import ProductSpecification, SpecificationDataType
from app.models.specification_alias import SpecificationAlias
from tests.test_acquisition import _register_admin
from tests.test_companies import _auth_headers, _register_verified
from tests.test_document_extraction import _build_test_pdf, _create_extraction_job, _upload
from tests.test_product_graph import _create_category, _create_product, _create_specification
from tests.test_provenance import _create_observation, _create_source

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


async def _create_document_observation(
    client, admin, source_id: str, pages: list[str], content_hash: str
) -> dict:
    res = await client.post(
        f"/api/v1/sources/{source_id}/observations",
        json={
            "source_id": source_id,
            "raw_content": {
                "filename": "catalogue.pdf",
                "sha256": "0" * 64,
                "storage_key": "source-documents/uploads/catalogue.pdf",
                "page_count": len(pages),
                "pages": [{"page": i + 1, "text": text} for i, text in enumerate(pages)],
            },
            "content_hash": content_hash,
            "collection_method_used": "structured_file",
            "collected_at": "2026-09-03T00:00:00Z",
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _add_alias(specification_id: str, alias: str) -> None:
    async with AsyncSessionLocal() as db:
        db.add(SpecificationAlias(specification_id=uuid.UUID(specification_id), alias=alias))
        await db.commit()


async def _create_enum_specification(
    client, admin, category_id: str, name: str, enum_options: list[str]
) -> dict:
    res = await client.post(
        f"/api/v1/product-categories/{category_id}/specifications",
        json={
            "name": name,
            "unit": None,
            "datatype": "enum",
            "enum_options": enum_options,
            "required": False,
        },
        headers=_auth_headers(admin),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _setup(client, admin, *, spec_kwargs: dict, category_name: str = "Test Pumps"):
    category = await _create_category(client, admin, category_name)
    spec = await _create_specification(client, admin, category["id"], **spec_kwargs)
    product = await _create_product(client, admin, category["id"], name="Test Pump 5000")
    return category, spec, product


async def _extract(client, admin, product_id: str, raw_observation_id: str):
    return await client.post(
        f"/api/v1/products/{product_id}/extract-specifications",
        json={"raw_observation_id": raw_observation_id},
        headers=_auth_headers(admin),
    )


async def _get_evidence(client, admin, product_id: str, specification_id: str) -> list[dict]:
    res = await client.get(
        f"/api/v1/products/{product_id}/attributes/{specification_id}/evidence",
        headers=_auth_headers(admin),
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]["items"]


def _spec(datatype, unit=None, enum_options=None) -> ProductSpecification:
    return ProductSpecification(
        id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        name="Test Spec",
        datatype=datatype,
        unit=unit,
        enum_options=enum_options,
    )


# --------------------------------------------------------------------------
# Pure unit tests — app.extraction modules, no database
# --------------------------------------------------------------------------


def test_label_normalization_case_whitespace_colon():
    assert label_matching.normalize_label("  Flow Rate:  ") == "flow rate"
    assert label_matching.normalize_label("FLOW   RATE") == "flow rate"


def test_split_label_value_colon_and_gap_styles():
    colon = patterns.split_label_value("Flow: 50 m³/h")
    assert colon is not None
    assert colon.style == "colon"
    assert colon.value_text == "50 m³/h"

    gap = patterns.split_label_value("Flow      50 m³/h")
    assert gap is not None
    assert gap.style == "gap"

    assert patterns.split_label_value("just a sentence with no shape at all") is None


def test_parse_numeric_with_unit():
    assert patterns.parse_numeric_with_unit("50 m³/h", unit_conversion.KNOWN_UNITS) == (
        "50",
        "m³/h",
    )
    assert patterns.parse_numeric_with_unit("2900 rpm", unit_conversion.KNOWN_UNITS) == (
        "2900",
        "rpm",
    )
    assert patterns.parse_numeric_with_unit("fifty", unit_conversion.KNOWN_UNITS) is None
    assert patterns.parse_numeric_with_unit("50 kg extra", unit_conversion.KNOWN_UNITS) is None


def test_parse_range_dash_and_to_word():
    assert patterns.parse_range("10-50 m³/h", unit_conversion.KNOWN_UNITS) == ("10", "50", "m³/h")
    assert patterns.parse_range("20-80 m", unit_conversion.KNOWN_UNITS) == ("20", "80", "m")
    assert patterns.parse_range("-10 to 120 °C", unit_conversion.KNOWN_UNITS) == (
        "-10",
        "120",
        "°C",
    )
    assert patterns.parse_range("50 m³/h", unit_conversion.KNOWN_UNITS) is None


def test_hp_to_kw_conversion_is_never_offered():
    resolution = unit_conversion.resolve_unit("HP", "kW")
    assert resolution.unit_resolved is False
    assert resolution.reject_reason is None
    assert resolution.convert is None


def test_safe_conversion_examples():
    assert unit_conversion.resolve_unit("L/min", "m³/h").unit_resolved is True
    assert unit_conversion.resolve_unit("bar", "psi").unit_resolved is True
    assert unit_conversion.resolve_unit("mm", "m").unit_resolved is True
    assert unit_conversion.resolve_unit("°C", "°F").unit_resolved is True


def test_incompatible_physical_family_unit_rejected():
    resolution = unit_conversion.resolve_unit("bar", "kW")
    assert resolution.reject_reason == "incompatible_unit"


def test_unrecognized_unit_rejected():
    resolution = unit_conversion.resolve_unit("furlongs", "m")
    assert resolution.reject_reason == "unrecognized_unit"


def test_confidence_tiers_are_deterministic_and_explainable():
    assert (
        compute_confidence(
            match_type="name", match_style="colon", unit_resolved=True, ambiguous=False
        )
        == 0.90
    )
    assert (
        compute_confidence(
            match_type="alias", match_style="colon", unit_resolved=True, ambiguous=False
        )
        == 0.70
    )
    assert (
        compute_confidence(
            match_type="name", match_style="gap", unit_resolved=True, ambiguous=False
        )
        == 0.45
    )
    assert (
        compute_confidence(
            match_type="name", match_style="colon", unit_resolved=False, ambiguous=False
        )
        == 0.45
    )
    assert (
        compute_confidence(
            match_type="name", match_style="colon", unit_resolved=True, ambiguous=True
        )
        == 0.20
    )


def test_label_index_detects_ambiguous_configuration():
    category_id = uuid.uuid4()
    flow = ProductSpecification(
        id=uuid.uuid4(), category_id=category_id, name="Flow", datatype=SpecificationDataType.NUMBER
    )
    discharge = ProductSpecification(
        id=uuid.uuid4(),
        category_id=category_id,
        name="Discharge",
        datatype=SpecificationDataType.NUMBER,
    )
    alias_row = SpecificationAlias(specification_id=discharge.id, alias="Flow")
    index = label_matching.build_label_index([flow, discharge], {discharge.id: [alias_row]})
    result = label_matching.resolve_label(index, "Flow")
    assert isinstance(result, list)
    assert {s.id for s in result} == {flow.id, discharge.id}


def test_malformed_number_rejected():
    outcome = validation.validate_reading(
        _spec(SpecificationDataType.NUMBER, unit="kW"), "roughly twenty"
    )
    assert isinstance(outcome, validation.ValidationFailure)
    assert outcome.reason == "malformed_number"


def test_range_rejected_against_number_datatype():
    outcome = validation.validate_reading(
        _spec(SpecificationDataType.NUMBER, unit="m³/h"), "10-50 m³/h"
    )
    assert isinstance(outcome, validation.ValidationFailure)
    assert outcome.reason == "range_not_allowed_for_number"


def test_scalar_rejected_against_range_datatype():
    outcome = validation.validate_reading(_spec(SpecificationDataType.RANGE, unit="m"), "50 m")
    assert isinstance(outcome, validation.ValidationFailure)
    assert outcome.reason == "scalar_not_allowed_for_range"


def test_range_extraction_valid():
    outcome = validation.validate_reading(
        _spec(SpecificationDataType.RANGE, unit="°C"), "-10 to 120 °C"
    )
    assert isinstance(outcome, validation.ParsedReading)
    assert outcome.observed_value == "-10 to 120 °C"


def test_enum_exact_match():
    spec = _spec(SpecificationDataType.ENUM, enum_options=["Centrifugal", "Submersible"])
    outcome = validation.validate_reading(spec, "Centrifugal")
    assert isinstance(outcome, validation.ParsedReading)
    assert outcome.observed_value == "Centrifugal"


def test_enum_invalid_value_rejected():
    spec = _spec(SpecificationDataType.ENUM, enum_options=["Centrifugal", "Submersible"])
    outcome = validation.validate_reading(spec, "Centrifugall")
    assert isinstance(outcome, validation.ValidationFailure)
    assert outcome.reason == "enum_value_not_allowed"


def test_safe_unit_conversion_populates_normalized_value():
    spec = _spec(SpecificationDataType.NUMBER, unit="m³/h")
    outcome = validation.validate_reading(spec, "833.3 L/min")
    assert isinstance(outcome, validation.ParsedReading)
    assert outcome.unit_resolved is True
    assert outcome.normalized_unit == "m³/h"
    assert abs(float(outcome.normalized_value) - 50.0) < 0.1


def test_hp_reading_against_kw_spec_not_rejected_but_unresolved():
    spec = _spec(SpecificationDataType.NUMBER, unit="kW")
    outcome = validation.validate_reading(spec, "22 HP")
    assert isinstance(outcome, validation.ParsedReading)
    assert outcome.unit_resolved is False
    assert outcome.normalized_value is None
    assert outcome.observed_value == "22 HP"


def test_value_with_unknown_unit_token_rejected():
    spec = _spec(SpecificationDataType.NUMBER, unit="kW")
    outcome = validation.validate_reading(spec, "22 xyz")
    assert isinstance(outcome, validation.ValidationFailure)


# --------------------------------------------------------------------------
# Integration — real API, real database
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_name_match_extracts_high_confidence(client):
    admin = await _register_admin(client, "spx-name@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-name"
    )

    res = await _extract(client, admin, product["id"], observation["id"])
    assert res.status_code == 200, res.text
    body = res.json()["data"]
    assert len(body["created"]) == 1
    assert body["rejected"] == []
    assert body["ambiguous_configuration"] == []

    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert len(evidence_list) == 1
    evidence = evidence_list[0]
    assert evidence["value_observed"] == "50 m³/h"
    assert evidence["extraction_method"] == "rule_based"
    assert evidence["status"] == "extracted"
    assert evidence["confidence"] == 0.90
    context = evidence["extraction_context"]
    assert context["matched_label"] == "Flow"
    assert context["match_type"] == "name"
    assert context["page"] == 1


@pytest.mark.asyncio
async def test_alias_match_extracts_at_alias_confidence(client):
    admin = await _register_admin(client, "spx-alias@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    await _add_alias(spec["id"], "Discharge")
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Discharge: 50 m³/h"], content_hash="h-alias"
    )

    res = await _extract(client, admin, product["id"], observation["id"])
    assert res.status_code == 200, res.text
    assert len(res.json()["data"]["created"]) == 1

    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert evidence_list[0]["confidence"] == 0.70
    assert evidence_list[0]["extraction_context"]["match_type"] == "alias"


@pytest.mark.asyncio
async def test_label_normalization_through_full_pipeline(client):
    admin = await _register_admin(client, "spx-normalize@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow Rate", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["  flow   rate  :   50 m³/h"], content_hash="h-norm"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert len(evidence_list) == 1


@pytest.mark.asyncio
async def test_unknown_label_produces_no_candidate(client):
    admin = await _register_admin(client, "spx-nomatch@example.com")
    await _setup(client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"})
    _category2, _spec2, product = await _setup(
        client,
        admin,
        spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"},
        category_name="Test Pumps Two",
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Warranty: 12 months"], content_hash="h-nomatch"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    body = res.json()["data"]
    assert body["created"] == []
    assert body["rejected"] == []
    assert body["ambiguous_configuration"] == []


@pytest.mark.asyncio
async def test_ambiguous_configuration_reported_not_guessed(client):
    admin = await _register_admin(client, "spx-ambig@example.com")
    category = await _create_category(client, admin, "Ambiguous Pumps")
    flow = await _create_specification(
        client, admin, category["id"], name="Flow", unit="m³/h", datatype="number"
    )
    discharge = await _create_specification(
        client, admin, category["id"], name="Discharge", unit="mm", datatype="number"
    )
    await _add_alias(discharge["id"], "Flow")
    product = await _create_product(client, admin, category["id"], name="Ambiguous Pump")
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-ambig"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    body = res.json()["data"]
    assert body["created"] == []
    assert len(body["ambiguous_configuration"]) == 1
    entry = body["ambiguous_configuration"][0]
    assert entry["label"] == "Flow"
    assert set(entry["specification_ids"]) == {flow["id"], discharge["id"]}


@pytest.mark.asyncio
async def test_exact_unit_match_high_confidence(client):
    admin = await _register_admin(client, "spx-unit-exact@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Power", "unit": "kW", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Power: 22 kW"], content_hash="h-unit-exact"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert evidence_list[0]["confidence"] == 0.90
    assert evidence_list[0]["value_observed"] == "22 kW"


@pytest.mark.asyncio
async def test_range_extraction_for_range_datatype(client):
    admin = await _register_admin(client, "spx-range@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Temperature", "unit": "°C", "datatype": "range"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Temperature: -10 to 120 °C"], content_hash="h-range"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert evidence_list[0]["value_observed"] == "-10 to 120 °C"


@pytest.mark.asyncio
async def test_range_rejected_against_number_datatype_integration(client):
    admin = await _register_admin(client, "spx-range-reject@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 10-50 m³/h"], content_hash="h-range-reject"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    body = res.json()["data"]
    assert body["created"] == []
    assert len(body["rejected"]) == 1
    assert body["rejected"][0]["reason"] == "range_not_allowed_for_number"
    assert body["rejected"][0]["label"] == "Flow"


@pytest.mark.asyncio
async def test_enum_exact_match_extracts(client):
    admin = await _register_admin(client, "spx-enum@example.com")
    category = await _create_category(client, admin, "Enum Pumps")
    spec = await _create_enum_specification(
        client, admin, category["id"], "Type", ["Centrifugal", "Submersible"]
    )
    product = await _create_product(client, admin, category["id"], name="Enum Pump")
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Type: Centrifugal"], content_hash="h-enum"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert evidence_list[0]["value_observed"] == "Centrifugal"


@pytest.mark.asyncio
async def test_invalid_enum_value_rejected(client):
    admin = await _register_admin(client, "spx-enum-invalid@example.com")
    category = await _create_category(client, admin, "Enum Pumps Invalid")
    await _create_enum_specification(
        client, admin, category["id"], "Type", ["Centrifugal", "Submersible"]
    )
    product = await _create_product(client, admin, category["id"], name="Enum Pump Invalid")
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Type: Centrifugall"], content_hash="h-enum-invalid"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    body = res.json()["data"]
    assert body["created"] == []
    assert body["rejected"][0]["reason"] == "enum_value_not_allowed"


@pytest.mark.asyncio
async def test_malformed_number_rejected_integration(client):
    admin = await _register_admin(client, "spx-malformed@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: approximately fifty"], content_hash="h-malformed"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    body = res.json()["data"]
    assert body["created"] == []
    assert body["rejected"][0]["reason"] == "malformed_number"


@pytest.mark.asyncio
async def test_safe_unit_conversion_normalizes_and_keeps_high_confidence(client):
    admin = await _register_admin(client, "spx-safe-convert@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 833.33 L/min"], content_hash="h-safe-convert"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert evidence_list[0]["value_observed"] == "833.33 L/min"
    assert evidence_list[0]["confidence"] == 0.90


@pytest.mark.asyncio
async def test_hp_to_kw_conversion_refused_confidence_capped(client):
    admin = await _register_admin(client, "spx-hp@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Power", "unit": "kW", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Power: 22 HP"], content_hash="h-hp"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    evidence = evidence_list[0]
    assert evidence["value_observed"] == "22 HP"
    assert evidence["confidence"] == 0.45


@pytest.mark.asyncio
async def test_value_with_unknown_unit_rejected_integration(client):
    admin = await _register_admin(client, "spx-unknown-unit@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Power", "unit": "kW", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Power: 22 zzz"], content_hash="h-unknown-unit"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    body = res.json()["data"]
    assert body["created"] == []
    assert len(body["rejected"]) == 1


@pytest.mark.asyncio
async def test_repeated_identical_value_single_row_high_confidence(client):
    admin = await _register_admin(client, "spx-repeat-identical@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client,
        admin,
        source["id"],
        ["Flow: 50 m³/h", "Some unrelated text", "Flow: 50 m³/h"],
        content_hash="h-repeat-identical",
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert len(evidence_list) == 1
    context = evidence_list[0]["extraction_context"]
    assert context["ambiguous"] is False
    assert len(context["occurrences"]) == 2
    assert evidence_list[0]["confidence"] == 0.90


@pytest.mark.asyncio
async def test_conflicting_occurrences_same_document_low_confidence_no_data_conflict(client):
    admin = await _register_admin(client, "spx-conflict-same-doc@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client,
        admin,
        source["id"],
        ["Flow: 50 m³/h", "Flow: 60 m³/h"],
        content_hash="h-conflict-same-doc",
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert len(evidence_list) == 1
    evidence = evidence_list[0]
    assert evidence["confidence"] == 0.20
    assert evidence["conflict_id"] is None
    context = evidence["extraction_context"]
    assert context["ambiguous"] is True
    assert len(context["occurrences"]) == 2
    assert {o["value"] for o in context["occurrences"]} == {"50 m³/h", "60 m³/h"}


@pytest.mark.asyncio
async def test_same_value_different_safe_units_treated_as_agreement(client):
    admin = await _register_admin(client, "spx-safe-agree@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client,
        admin,
        source["id"],
        ["Flow: 50 m³/h", "Flow: 833.33 L/min"],
        content_hash="h-safe-agree",
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    evidence = evidence_list[0]
    assert evidence["extraction_context"]["ambiguous"] is False
    assert evidence["confidence"] == 0.90


@pytest.mark.asyncio
async def test_conflicting_values_different_safe_units_ambiguous(client):
    admin = await _register_admin(client, "spx-safe-conflict@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client,
        admin,
        source["id"],
        ["Flow: 50 m³/h", "Flow: 1000 L/min"],
        content_hash="h-safe-conflict",
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    evidence = evidence_list[0]
    assert evidence["extraction_context"]["ambiguous"] is True
    assert evidence["confidence"] == 0.20


@pytest.mark.asyncio
async def test_extraction_context_contains_required_fields(client):
    admin = await _register_admin(client, "spx-context@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-context"
    )
    await _extract(client, admin, product["id"], observation["id"])
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    context = evidence_list[0]["extraction_context"]
    for key in (
        "page",
        "snippet",
        "matched_label",
        "match_type",
        "match_style",
        "extraction_rule",
        "occurrences",
        "ambiguous",
    ):
        assert key in context
    assert context["page"] == 1
    assert context["extraction_rule"] == "numeric_with_unit"


@pytest.mark.asyncio
async def test_extraction_never_creates_verified_evidence_or_touches_product_attribute(client):
    admin = await _register_admin(client, "spx-no-auto-verify@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-no-auto-verify"
    )
    await _extract(client, admin, product["id"], observation["id"])

    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert evidence_list[0]["status"] == "extracted"
    assert evidence_list[0]["verified_by"] is None
    assert evidence_list[0]["verified_at"] is None

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ProductAttribute).where(
                ProductAttribute.product_id == uuid.UUID(product["id"]),
                ProductAttribute.specification_id == uuid.UUID(spec["id"]),
            )
        )
        assert result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_rerunning_extraction_is_idempotent_no_duplicates(client):
    admin = await _register_admin(client, "spx-idempotent@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-idempotent"
    )
    first = await _extract(client, admin, product["id"], observation["id"])
    assert len(first.json()["data"]["created"]) == 1

    second = await _extract(client, admin, product["id"], observation["id"])
    body = second.json()["data"]
    assert body["created"] == []
    assert body["existing"] == first.json()["data"]["created"]

    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert len(evidence_list) == 1


@pytest.mark.asyncio
async def test_preexisting_manual_evidence_reported_as_existing_not_duplicated(client):
    admin = await _register_admin(client, "spx-preexisting@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-preexisting"
    )
    manual = await client.post(
        f"/api/v1/products/{product['id']}/attributes/{spec['id']}/evidence",
        json={
            "product_id": product["id"],
            "specification_id": spec["id"],
            "raw_observation_id": observation["id"],
            "value_observed": "50 m³/h",
            "extraction_method": "manual",
            "confidence": 0.6,
        },
        headers=_auth_headers(admin),
    )
    assert manual.status_code == 201, manual.text
    manual_id = manual.json()["data"]["id"]

    res = await _extract(client, admin, product["id"], observation["id"])
    body = res.json()["data"]
    assert body["created"] == []
    assert body["existing"] == [manual_id]

    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert len(evidence_list) == 1
    assert evidence_list[0]["extraction_method"] == "manual"


@pytest.mark.asyncio
async def test_two_documents_disagreeing_creates_data_conflict(client):
    admin = await _register_admin(client, "spx-cross-doc-conflict@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation_a = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-cross-a"
    )
    observation_b = await _create_document_observation(
        client, admin, source["id"], ["Flow: 60 m³/h"], content_hash="h-cross-b"
    )

    await _extract(client, admin, product["id"], observation_a["id"])
    await _extract(client, admin, product["id"], observation_b["id"])

    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert len(evidence_list) == 2
    conflict_ids = {e["conflict_id"] for e in evidence_list}
    assert None not in conflict_ids
    assert len(conflict_ids) == 1


@pytest.mark.asyncio
async def test_extraction_requires_admin(client):
    admin = await _register_admin(client, "spx-admin-ok@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-admin-ok"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert res.status_code == 200, res.text


@pytest.mark.asyncio
async def test_extraction_rejected_for_non_admin(client):
    admin = await _register_admin(client, "spx-non-admin-setup@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-non-admin"
    )
    non_admin = await _register_verified(client, "spx-non-admin@example.com")
    res = await client.post(
        f"/api/v1/products/{product['id']}/extract-specifications",
        json={"raw_observation_id": observation["id"]},
        headers=_auth_headers(non_admin),
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_extraction_against_nonexistent_product_404(client):
    admin = await _register_admin(client, "spx-no-product@example.com")
    _category, _spec, _product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_document_observation(
        client, admin, source["id"], ["Flow: 50 m³/h"], content_hash="h-no-product"
    )
    res = await client.post(
        f"/api/v1/products/{uuid.uuid4()}/extract-specifications",
        json={"raw_observation_id": observation["id"]},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "PRODUCT_NOT_FOUND"


@pytest.mark.asyncio
async def test_extraction_against_nonexistent_raw_observation_404(client):
    admin = await _register_admin(client, "spx-no-observation@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    res = await client.post(
        f"/api/v1/products/{product['id']}/extract-specifications",
        json={"raw_observation_id": str(uuid.uuid4())},
        headers=_auth_headers(admin),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "RAW_OBSERVATION_NOT_FOUND"


@pytest.mark.asyncio
async def test_extraction_rejects_non_document_raw_observation(client):
    admin = await _register_admin(client, "spx-non-document@example.com")
    _category, _spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Flow", "unit": "m³/h", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    observation = await _create_observation(
        client, admin, source["id"], "50", content_hash="h-non-document"
    )
    res = await _extract(client, admin, product["id"], observation["id"])
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_DOCUMENT_STRUCTURE"


@pytest.mark.asyncio
async def test_end_to_end_from_real_pdf_upload_through_extraction(client):
    """The one true end-to-end path: a real (synthetic, structurally
    valid) PDF -> POST /documents -> the unmodified
    DocumentExtractionAdapter/acquisition_service pipeline ->
    RawObservation -> this milestone's extractor -> evidence. Proves
    the extractor works against pypdf's actual output, not just
    hand-built raw_content."""
    # ASCII-only content deliberately: this shared synthetic-PDF builder
    # (from test_document_extraction.py, reused unmodified) writes text
    # via a bare Helvetica/WinAnsi Tj string with no encoding handling,
    # so a non-ASCII glyph like "³" round-trips through real pypdf
    # extraction as mangled bytes — a synthetic-fixture limitation, not
    # an extractor defect (verified directly against
    # app.collectors.pdf_text_extraction.extract_pdf_pages). "rpm" is
    # exercised instead to keep this test genuinely end-to-end.
    admin = await _register_admin(client, "spx-e2e-pdf@example.com")
    _category, spec, product = await _setup(
        client, admin, spec_kwargs={"name": "Speed", "unit": "rpm", "datatype": "number"}
    )
    source = await _create_source(client, admin)
    pdf_bytes = _build_test_pdf(["Speed: 2900 rpm"])
    upload = (await _upload(client, admin, pdf_bytes, filename="catalogue.pdf")).json()["data"]
    job_res = await _create_extraction_job(client, admin, source["id"], upload)
    assert job_res.status_code == 201, job_res.text
    events = await client.get(
        f"/api/v1/acquisition/jobs/{job_res.json()['data']['id']}/events",
        headers=_auth_headers(admin),
    )
    raw_observation_id = events.json()["data"]["items"][0]["raw_observation_id"]

    res = await _extract(client, admin, product["id"], raw_observation_id)
    assert res.status_code == 200, res.text
    assert len(res.json()["data"]["created"]) == 1
    evidence_list = await _get_evidence(client, admin, product["id"], spec["id"])
    assert evidence_list[0]["value_observed"] == "2900 rpm"
    assert evidence_list[0]["extraction_method"] == "rule_based"
    assert evidence_list[0]["status"] == "extracted"
