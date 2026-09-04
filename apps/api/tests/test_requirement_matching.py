"""
Requirement Matching & Ranking Engine tests — Module 7A-2. Covers
candidate retrieval (category scoping, published/active filters, the
500-candidate bounded-retrieval ceiling), the mandatory hard
specification-criteria filter (all-or-nothing, missing evidence always
fails), the three soft signals (trust/location/certifications) and
their exact scoring formula, the Fact->Evidence->Signal->Score
Contribution->Explanation contract, deterministic ranking, the
no-category short-circuit, and ownership-scoped authorization —
identical policy to GET /requirements/{id}.

Reuses test_companies.py's and test_product_graph.py's established
fixtures, same as test_requirements.py.
"""

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.models.verification_document import DocumentStatus, VerificationDocument
from app.services import requirement_matching_service
from tests.test_companies import _auth_headers, _company_payload, _register_verified
from tests.test_product_graph import (
    _create_category,
    _create_product,
    _create_specification,
    _create_verified_company,
    _publish,
)


async def _create_requirement(client, user, **overrides) -> dict:
    payload = {"raw_query": "Need an industrial supplier"}
    payload.update(overrides)
    res = await client.post("/api/v1/requirements", json=payload, headers=_auth_headers(user))
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _get_matches(client, user, requirement_id: str) -> dict:
    res = await client.get(
        f"/api/v1/requirements/{requirement_id}/matches", headers=_auth_headers(user)
    )
    assert res.status_code == 200, res.text
    return res.json()["data"]


async def _create_company_at(
    client, email: str, name: str, *, country: str, state: str, city: str
) -> tuple[dict, dict]:
    owner = await _register_verified(client, email)
    payload = _company_payload(name)
    payload.update(country=country, state=state, city=city)
    res = await client.post("/api/v1/companies", json=payload, headers=_auth_headers(owner))
    assert res.status_code == 201, res.text
    return owner, res.json()["data"]


async def _offer(client, owner_data, company: dict, product: dict, **overrides) -> dict:
    payload = {"product_id": product["id"], "role": "manufacturer"}
    payload.update(overrides)
    res = await client.post(
        f"/api/v1/companies/{company['id']}/offerings",
        json=payload,
        headers=_auth_headers(owner_data),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]


async def _upload_document(client, owner_data, company_id: str, document_type: str) -> str:
    files = {"file": ("cert.pdf", b"%PDF-1.4\n%fake\n%%EOF", "application/pdf")}
    res = await client.post(
        f"/api/v1/companies/{company_id}/documents",
        data={"document_type": document_type},
        files=files,
        headers=_auth_headers(owner_data),
    )
    assert res.status_code == 201, res.text
    return res.json()["data"]["id"]


async def _mark_document_verified(document_id: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(VerificationDocument).where(VerificationDocument.id == document_id)
        )
        doc = result.scalar_one()
        doc.status = DocumentStatus.VERIFIED
        await db.commit()


# --------------------------------------------------------------------------
# No-category short-circuit (Section 11 — no unbounded global scan)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_category_returns_category_required(client):
    user = await _register_verified(client, "match-nocat@example.com")
    requirement = await _create_requirement(client, user)
    assert requirement["product_category_id"] is None

    data = await _get_matches(client, user, requirement["id"])
    assert data["status"] == "category_required"
    assert data["matches"] == []
    assert data["total_candidates_considered"] == 0
    assert data["excluded_for_hard_criteria"] == 0
    assert data["returned_count"] == 0
    assert data["more_candidates_may_exist"] is False


# --------------------------------------------------------------------------
# Empty / category-isolated candidate universe
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_category_with_no_offerings_returns_computed_zero_matches(client):
    user = await _register_verified(client, "match-empty@example.com")
    category = await _create_category(client, user, "Empty Category")
    requirement = await _create_requirement(client, user, product_category_id=category["id"])

    data = await _get_matches(client, user, requirement["id"])
    assert data["status"] == "computed"
    assert data["matches"] == []
    assert data["total_candidates_considered"] == 0
    assert data["returned_count"] == 0


@pytest.mark.asyncio
async def test_offering_in_a_different_category_is_never_a_candidate(client):
    user = await _register_verified(client, "match-catisolate@example.com")
    other_category = await _create_category(client, user, "Other Category")
    product = await _create_product(
        client, user, other_category["id"], name="Other Category Product"
    )
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "match-catisolate-co@example.com", "Iso Co"
    )
    await _offer(client, owner, company, product)

    target_category = await _create_category(client, user, "Target Category")
    requirement = await _create_requirement(client, user, product_category_id=target_category["id"])

    data = await _get_matches(client, user, requirement["id"])
    assert data["total_candidates_considered"] == 0
    assert data["matches"] == []


@pytest.mark.asyncio
async def test_unpublished_product_is_never_a_candidate(client):
    user = await _register_verified(client, "match-unpublished@example.com")
    category = await _create_category(client, user, "Unpublished Category")
    product = await _create_product(client, user, category["id"], name="Draft Product")
    # deliberately never published
    owner, company = await _create_verified_company(
        client, "match-unpublished-co@example.com", "Draft Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["total_candidates_considered"] == 0


@pytest.mark.asyncio
async def test_inactive_offering_is_never_a_candidate(client):
    user = await _register_verified(client, "match-inactive@example.com")
    category = await _create_category(client, user, "Inactive Category")
    product = await _create_product(client, user, category["id"], name="Inactive Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "match-inactive-co@example.com", "Inactive Co"
    )
    offering = await _offer(client, owner, company, product)
    patch_res = await client.patch(
        f"/api/v1/companies/{company['id']}/offerings/{offering['id']}",
        json={"status": "inactive"},
        headers=_auth_headers(owner),
    )
    assert patch_res.status_code == 200

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])
    assert data["total_candidates_considered"] == 0


# --------------------------------------------------------------------------
# Trust-only scoring (no location/certifications requested)
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trust_only_scoring_when_no_location_or_certifications_requested(client):
    user = await _register_verified(client, "match-trustonly@example.com")
    category = await _create_category(client, user, "Trust Only Category")
    product = await _create_product(client, user, category["id"], name="Trust Only Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "match-trustonly-co@example.com", "Trust Only Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])

    assert data["returned_count"] == 1
    match = data["matches"][0]
    assert match["rank"] == 1
    signals = match["signals"]
    # A brand-new company is only email_verified (12.5/50) — see
    # test_company_verification.test_new_company_starts_unverified.
    assert signals["trust_tier"]["level"] == "email_verified"
    assert signals["trust_tier"]["points_earned"] == 12.5
    assert signals["trust_tier"]["points_possible"] == 50.0
    assert signals["location"]["points_possible"] == 0.0
    assert signals["certifications"]["points_possible"] == 0.0
    assert signals["category"]["matched"] is True
    expected_score = round((12.5 / 50.0) * 100, 2)
    assert match["score"] == expected_score


# --------------------------------------------------------------------------
# Hard specification-criteria filter — all-or-nothing, missing = fail
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hard_criteria_exclude_non_matching_and_missing_evidence_candidates(client):
    user = await _register_verified(client, "match-hardfilter@example.com")
    category = await _create_category(client, user, "Hard Filter Category")
    power = await _create_specification(
        client, user, category["id"], name="Power", datatype="number"
    )

    matching_product = await _create_product(
        client,
        user,
        category["id"],
        name="Matching Product",
        attributes=[{"specification_id": power["id"], "value": "10"}],
    )
    below_threshold_product = await _create_product(
        client,
        user,
        category["id"],
        name="Below Threshold Product",
        attributes=[{"specification_id": power["id"], "value": "2"}],
    )
    missing_attribute_product = await _create_product(
        client, user, category["id"], name="Missing Attribute Product"
    )
    for p in (matching_product, below_threshold_product, missing_attribute_product):
        await _publish(client, user, p["id"])

    owner, company = await _create_verified_company(
        client, "match-hardfilter-co@example.com", "Hard Filter Co"
    )
    await _offer(client, owner, company, matching_product, role="manufacturer")
    await _offer(client, owner, company, below_threshold_product, role="supplier")
    await _offer(client, owner, company, missing_attribute_product, role="distributor")

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[{"specification_id": power["id"], "operator": "gte", "value": 5.0}],
    )
    data = await _get_matches(client, user, requirement["id"])

    assert data["total_candidates_considered"] == 3
    assert data["excluded_for_hard_criteria"] == 2
    assert data["returned_count"] == 1
    assert data["matches"][0]["product"]["id"] == matching_product["id"]

    criterion_signal = data["matches"][0]["signals"]["criteria"][0]
    assert criterion_signal["specification_name"] == "Power"
    assert criterion_signal["operator"] == "gte"
    assert criterion_signal["candidate_value"] == "10"
    assert criterion_signal["status"] == "matched"


@pytest.mark.asyncio
async def test_all_criteria_must_match_partial_credit_never_survives(client):
    user = await _register_verified(client, "match-allcriteria@example.com")
    category = await _create_category(client, user, "All Criteria Category")
    power = await _create_specification(
        client, user, category["id"], name="Power", datatype="number"
    )
    material = await _create_specification(
        client, user, category["id"], name="Material", datatype="text", unit=None
    )
    product = await _create_product(
        client,
        user,
        category["id"],
        name="Partial Match Product",
        attributes=[
            {"specification_id": power["id"], "value": "10"},
            {"specification_id": material["id"], "value": "Steel"},
        ],
    )
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "match-allcriteria-co@example.com", "All Criteria Co"
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        criteria=[
            {"specification_id": power["id"], "operator": "gte", "value": 5.0},
            {"specification_id": material["id"], "operator": "eq", "value": "Aluminum"},
        ],
    )
    data = await _get_matches(client, user, requirement["id"])
    assert data["excluded_for_hard_criteria"] == 1
    assert data["matches"] == []


# --------------------------------------------------------------------------
# Location signal — hierarchical scoring
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_location_full_hierarchy_match_earns_all_points(client):
    user = await _register_verified(client, "match-locfull@example.com")
    category = await _create_category(client, user, "Location Full Category")
    product = await _create_product(client, user, category["id"], name="Location Full Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client,
        "match-locfull-co@example.com",
        "Location Full Co",
        country="Germany",
        state="Bavaria",
        city="Munich",
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        country="Germany",
        state="Bavaria",
        city="Munich",
    )
    data = await _get_matches(client, user, requirement["id"])
    location = data["matches"][0]["signals"]["location"]
    assert location["points_earned"] == 30.0
    assert location["points_possible"] == 30.0


@pytest.mark.asyncio
async def test_location_omitted_state_blocks_city_credit_even_if_city_matches(client):
    """
    Documented, deliberate consequence of the approved formula's literal
    hierarchy (architecture doc Section 6/8): city credit requires
    state_matched, which requires requirement.state to have actually
    been given. A requirement that specifies country+city but omits
    state can never earn city credit, even against a candidate whose
    city genuinely matches.
    """
    user = await _register_verified(client, "match-locpartial@example.com")
    category = await _create_category(client, user, "Location Partial Category")
    product = await _create_product(client, user, category["id"], name="Location Partial Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client,
        "match-locpartial-co@example.com",
        "Location Partial Co",
        country="Germany",
        state="Bavaria",
        city="Munich",
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        country="Germany",
        city="Munich",  # state deliberately omitted
    )
    data = await _get_matches(client, user, requirement["id"])
    location = data["matches"][0]["signals"]["location"]
    assert location["points_earned"] == 15.0  # country only, city credit withheld


# --------------------------------------------------------------------------
# Country-identity normalization (_normalize_country) — unit-level, no DB.
# Covers the CRI pilot's real gap: Company.country="IN" vs a buyer
# Requirement.country="India" scored 0 location points before this table
# existed, despite denoting the same real country.
# --------------------------------------------------------------------------


def test_normalize_country_matches_india_and_iso_code_both_directions():
    assert requirement_matching_service._normalize_country(
        "India"
    ) == requirement_matching_service._normalize_country("IN")
    assert requirement_matching_service._normalize_country(
        "IN"
    ) == requirement_matching_service._normalize_country("India")


def test_normalize_country_is_case_insensitive():
    assert requirement_matching_service._normalize_country(
        "india"
    ) == requirement_matching_service._normalize_country("in")


def test_normalize_country_preserves_exact_match_for_unlisted_countries():
    # Not in _COUNTRY_ALIASES at all — must fall back to the same
    # lowercased/stripped behavior _score_location always had.
    assert requirement_matching_service._normalize_country(
        "Germany"
    ) == requirement_matching_service._normalize_country("germany")


def test_normalize_country_does_not_conflate_india_and_indonesia():
    assert requirement_matching_service._normalize_country(
        "India"
    ) != requirement_matching_service._normalize_country("Indonesia")


def test_normalize_country_does_not_conflate_in_and_id():
    assert requirement_matching_service._normalize_country(
        "IN"
    ) != requirement_matching_service._normalize_country("ID")


@pytest.mark.asyncio
async def test_location_india_requirement_matches_iso_in_candidate(client):
    """The real CRI-pilot shape: Company.country stores the ISO code
    'IN'; the buyer's Requirement.country is the free-text 'India'. Must
    earn country-level location points via normalization, not a raw
    string comparison."""
    user = await _register_verified(client, "match-loc-india-in@example.com")
    category = await _create_category(client, user, "India ISO Alias Category")
    product = await _create_product(client, user, category["id"], name="India ISO Alias Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client,
        "match-loc-india-in-co@example.com",
        "India ISO Alias Co",
        country="IN",  # exactly how the real CRI pilot company stores it
        state="Tamil Nadu",
        city="Coimbatore",
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        country="India",  # exactly how the real buyer query phrases it
    )
    data = await _get_matches(client, user, requirement["id"])
    location = data["matches"][0]["signals"]["location"]
    assert location["points_earned"] == 15.0  # country only — state/city not requested


@pytest.mark.asyncio
async def test_location_alias_matched_country_still_unlocks_state_and_city_hierarchy(client):
    """Proves the hierarchy composition (Section 6/8) is unaffected by
    normalization: an alias-matched country ('India' vs 'IN') must
    unlock state/city credit exactly as an exact-string country match
    already did — full 30/30 when the requirement also specifies a
    genuinely matching state and city."""
    user = await _register_verified(client, "match-loc-india-full@example.com")
    category = await _create_category(client, user, "India ISO Alias Full Category")
    product = await _create_product(
        client, user, category["id"], name="India ISO Alias Full Product"
    )
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client,
        "match-loc-india-full-co@example.com",
        "India ISO Alias Full Co",
        country="IN",
        state="Tamil Nadu",
        city="Coimbatore",
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        country="India",
        state="Tamil Nadu",
        city="Coimbatore",
    )
    data = await _get_matches(client, user, requirement["id"])
    location = data["matches"][0]["signals"]["location"]
    assert location["points_earned"] == 30.0
    assert location["points_possible"] == 30.0


@pytest.mark.asyncio
async def test_location_country_mismatch_still_blocks_all_credit(client):
    """India vs Indonesia must remain a genuine non-match — the alias
    table must never cause two different real countries to score."""
    user = await _register_verified(client, "match-loc-india-indonesia@example.com")
    category = await _create_category(client, user, "India Indonesia Category")
    product = await _create_product(
        client, user, category["id"], name="India Indonesia Product"
    )
    await _publish(client, user, product["id"])
    owner, company = await _create_company_at(
        client,
        "match-loc-india-indonesia-co@example.com",
        "India Indonesia Co",
        country="Indonesia",
        state="Java",
        city="Jakarta",
    )
    await _offer(client, owner, company, product)

    requirement = await _create_requirement(
        client,
        user,
        product_category_id=category["id"],
        country="India",
    )
    data = await _get_matches(client, user, requirement["id"])
    location = data["matches"][0]["signals"]["location"]
    assert location["points_earned"] == 0.0


# --------------------------------------------------------------------------
# Certification signal — VERIFIED-only, conservative word-boundary match
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pending_certification_document_never_scores_a_match(client):
    user = await _register_verified(client, "match-certpending@example.com")
    category = await _create_category(client, user, "Cert Pending Category")
    product = await _create_product(client, user, category["id"], name="Cert Pending Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "match-certpending-co@example.com", "Cert Pending Co"
    )
    await _offer(client, owner, company, product)
    await _upload_document(client, owner, company["id"], "iso")  # stays PENDING

    requirement = await _create_requirement(
        client, user, product_category_id=category["id"], certifications=["ISO 9001"]
    )
    data = await _get_matches(client, user, requirement["id"])
    cert = data["matches"][0]["signals"]["certifications"]
    assert cert["points_earned"] == 0.0
    assert cert["evidence_found"] == []
    assert cert["note"] is not None


@pytest.mark.asyncio
async def test_verified_certification_document_scores_a_match(client):
    user = await _register_verified(client, "match-certverified@example.com")
    category = await _create_category(client, user, "Cert Verified Category")
    product = await _create_product(client, user, category["id"], name="Cert Verified Product")
    await _publish(client, user, product["id"])
    owner, company = await _create_verified_company(
        client, "match-certverified-co@example.com", "Cert Verified Co"
    )
    await _offer(client, owner, company, product)
    document_id = await _upload_document(client, owner, company["id"], "iso")
    await _mark_document_verified(document_id)

    requirement = await _create_requirement(
        client, user, product_category_id=category["id"], certifications=["ISO 9001"]
    )
    data = await _get_matches(client, user, requirement["id"])
    cert = data["matches"][0]["signals"]["certifications"]
    assert cert["points_earned"] == 20.0
    assert cert["evidence_found"] == ["ISO 9001"]
    assert cert["points_possible"] == 20.0


# --------------------------------------------------------------------------
# Ranking — score-descending order, and determinism across repeated calls
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matches_are_ranked_by_score_descending(client):
    user = await _register_verified(client, "match-ranking@example.com")
    category = await _create_category(client, user, "Ranking Category")
    product = await _create_product(client, user, category["id"], name="Ranking Product")
    await _publish(client, user, product["id"])

    plain_owner, plain_company = await _create_verified_company(
        client, "match-ranking-plain@example.com", "Ranking Plain Co"
    )
    await _offer(client, plain_owner, plain_company, product)

    certified_owner, certified_company = await _create_verified_company(
        client, "match-ranking-certified@example.com", "Ranking Certified Co"
    )
    await _offer(client, certified_owner, certified_company, product)
    document_id = await _upload_document(client, certified_owner, certified_company["id"], "iso")
    await _mark_document_verified(document_id)

    requirement = await _create_requirement(
        client, user, product_category_id=category["id"], certifications=["ISO 9001"]
    )
    data = await _get_matches(client, user, requirement["id"])
    assert data["returned_count"] == 2
    assert data["matches"][0]["company"]["id"] == certified_company["id"]
    assert data["matches"][0]["score"] > data["matches"][1]["score"]
    assert data["matches"][0]["rank"] == 1
    assert data["matches"][1]["rank"] == 2


@pytest.mark.asyncio
async def test_matches_are_deterministic_across_repeated_calls(client):
    user = await _register_verified(client, "match-deterministic@example.com")
    category = await _create_category(client, user, "Deterministic Category")
    product = await _create_product(client, user, category["id"], name="Deterministic Product")
    await _publish(client, user, product["id"])

    owner_a, company_a = await _create_verified_company(
        client, "match-deterministic-a@example.com", "Deterministic Co A"
    )
    owner_b, company_b = await _create_verified_company(
        client, "match-deterministic-b@example.com", "Deterministic Co B"
    )
    await _offer(client, owner_a, company_a, product)
    await _offer(client, owner_b, company_b, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    first = await _get_matches(client, user, requirement["id"])
    second = await _get_matches(client, user, requirement["id"])
    assert [m["offering_id"] for m in first["matches"]] == [
        m["offering_id"] for m in second["matches"]
    ]
    assert len(first["matches"]) == 2


# --------------------------------------------------------------------------
# Bounded candidate retrieval — Option B truncation transparency
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_more_candidates_may_exist_when_ceiling_is_reached(client, monkeypatch):
    monkeypatch.setattr(requirement_matching_service, "_CANDIDATE_CEILING", 2)

    user = await _register_verified(client, "match-ceiling@example.com")
    category = await _create_category(client, user, "Ceiling Category")
    product = await _create_product(client, user, category["id"], name="Ceiling Product")
    await _publish(client, user, product["id"])

    for i in range(3):
        owner, company = await _create_verified_company(
            client, f"match-ceiling-{i}@example.com", f"Ceiling Co {i}"
        )
        await _offer(client, owner, company, product)

    requirement = await _create_requirement(client, user, product_category_id=category["id"])
    data = await _get_matches(client, user, requirement["id"])

    assert data["total_candidates_considered"] == 2
    assert data["more_candidates_may_exist"] is True


# --------------------------------------------------------------------------
# Ownership-scoped authorization — identical policy to GET /{id}
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matches_requires_auth(client):
    user = await _register_verified(client, "match-noauth@example.com")
    requirement = await _create_requirement(client, user)
    res = await client.get(f"/api/v1/requirements/{requirement['id']}/matches")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_matches_for_nonexistent_requirement_404s(client):
    user = await _register_verified(client, "match-missing@example.com")
    res = await client.get(
        "/api/v1/requirements/00000000-0000-0000-0000-000000000000/matches",
        headers=_auth_headers(user),
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "REQUIREMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_matches_for_requirement_owned_by_someone_else_404s_not_403(client):
    owner = await _register_verified(client, "match-owner@example.com")
    other = await _register_verified(client, "match-other@example.com")
    requirement = await _create_requirement(client, owner)
    res = await client.get(
        f"/api/v1/requirements/{requirement['id']}/matches", headers=_auth_headers(other)
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "REQUIREMENT_NOT_FOUND"
