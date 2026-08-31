#!/usr/bin/env python3
"""
Seeds realistic Industrial Product Graph data — Phase 4B. Creates real
categories, dynamic specifications (different per category, never
hardcoded — Phase 4A Section 5), products with real attribute values,
several companies, and multiple Offerings per product from different
companies, demonstrating the module's ABSOLUTE RULE directly: one
Product, many Companies, zero duplication.

Idempotent: safe to run more than once — every create step checks for
an existing row by slug/email first and skips if already present,
rather than erroring or duplicating.

Run:
    cd apps/api && python scripts/seed_product_graph.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models.company import Company, CompanyStatus  # noqa: E402
from app.models.company_member import CompanyMember, CompanyMemberStatus, CompanyRole  # noqa: E402
from app.models.offering import Offering, OfferingRole  # noqa: E402
from app.models.product import Product, ProductStatus  # noqa: E402
from app.models.product_attribute import ProductAttribute  # noqa: E402
from app.models.product_category import ProductCategory  # noqa: E402
from app.models.product_specification import (  # noqa: E402
    ProductSpecification,
    SpecificationDataType,
)
from app.models.user import Role, User  # noqa: E402
from app.services.offering_service import DuplicateOfferingError  # noqa: E402
from app.services.product_service import (  # noqa: E402
    _generate_unique_category_slug,
    _generate_unique_product_slug,
)

logger = get_logger(__name__)

SEED_COMPANIES = [
    ("seed-alpha-industrial@example.com", "Alpha Industrial Works", "India", "Pune"),
    ("seed-bravo-manufacturing@example.com", "Bravo Manufacturing Co", "China", "Shenzhen"),
    ("seed-crestline-exports@example.com", "Crestline Exports Ltd", "India", "Chennai"),
    ("seed-deltamech-supply@example.com", "DeltaMech Supply Co", "Germany", "Stuttgart"),
]

# Each entry: category name, [(spec name, unit, datatype), ...], [(product name, industry, {spec_name: value}), ...]
SEED_CATALOG: list[
    tuple[str, list[tuple[str, str | None, str]], list[tuple[str, str, dict[str, str]]]]
] = [
    (
        "Electric Motors",
        [("Power", "kW", "number"), ("Voltage", "V", "number"), ("RPM", None, "number")],
        [
            (
                "XJ-450 Electric Motor",
                "Manufacturing",
                {"Power": "5.5", "Voltage": "415", "RPM": "1440"},
            )
        ],
    ),
    (
        "Hydraulic Cylinders",
        [
            ("Bore Diameter", "mm", "number"),
            ("Stroke Length", "mm", "number"),
            ("Working Pressure", "bar", "number"),
        ],
        [
            (
                "HC-200 Hydraulic Cylinder",
                "Heavy Machinery",
                {"Bore Diameter": "200", "Stroke Length": "600", "Working Pressure": "250"},
            )
        ],
    ),
    (
        "Centrifugal Pumps",
        [("Flow Rate", "LPM", "number"), ("Head", "m", "number"), ("Material", None, "text")],
        [
            (
                "CP-100 Centrifugal Pump",
                "Water Treatment",
                {"Flow Rate": "1200", "Head": "45", "Material": "Stainless Steel 316"},
            )
        ],
    ),
    (
        "Packaging Machines",
        [
            ("Cycle Time", "sec", "number"),
            ("Pack Size Range", "mm", "text"),
            ("Power Consumption", "kW", "number"),
        ],
        [
            (
                "VP-30 Vacuum Packaging Machine",
                "Food Packaging",
                {"Cycle Time": "18", "Pack Size Range": "100-400", "Power Consumption": "2.2"},
            )
        ],
    ),
    (
        # Named to match the University's own Lesson 7 example phrasing
        # ("Need CNC machining in India") — lib/requirement.ts's
        # resolveCategoryId does deterministic whole-word matching after
        # singularizing plurals, which normalizes "machines" but not the
        # gerund "machining", so a category literally named "CNC Machines"
        # can never match that buyer sentence (see ForgeX Product Audit
        # §08's P0 "CNC machining in India" finding).
        "CNC Machining",
        [
            ("Axes", None, "number"),
            ("Spindle Speed", "RPM", "number"),
            ("Table Size", "mm", "text"),
        ],
        [
            (
                "CNC-5X Machining Center",
                "Precision Machining",
                {"Axes": "5", "Spindle Speed": "12000", "Table Size": "800x500"},
            )
        ],
    ),
    (
        "Valves",
        [
            ("Size", "inch", "number"),
            ("Pressure Rating", "bar", "number"),
            ("Body Material", None, "text"),
        ],
        [
            (
                "BV-50 Ball Valve",
                "Oil & Gas",
                {"Size": "2", "Pressure Rating": "150", "Body Material": "Carbon Steel"},
            )
        ],
    ),
    (
        "Bearings",
        [
            ("Bore Diameter", "mm", "number"),
            ("Load Rating", "kN", "number"),
            ("Type", None, "text"),
        ],
        [
            (
                "DB-6205 Deep Groove Ball Bearing",
                "Industrial Components",
                {"Bore Diameter": "25", "Load Rating": "14.8", "Type": "Deep Groove Ball Bearing"},
            )
        ],
    ),
]

# Which companies offer which products, and in what role — deliberately
# spread so at least one product has 3 offerings (demonstrating the
# ABSOLUTE RULE concretely, not just possible in principle).
SEED_OFFERINGS = [
    (
        "XJ-450 Electric Motor",
        "seed-alpha-industrial@example.com",
        OfferingRole.MANUFACTURER,
        "50 units",
        "3 weeks",
    ),
    (
        "XJ-450 Electric Motor",
        "seed-bravo-manufacturing@example.com",
        OfferingRole.MANUFACTURER,
        "100 units",
        "4 weeks",
    ),
    (
        "XJ-450 Electric Motor",
        "seed-deltamech-supply@example.com",
        OfferingRole.DISTRIBUTOR,
        "10 units",
        "1 week",
    ),
    (
        "HC-200 Hydraulic Cylinder",
        "seed-alpha-industrial@example.com",
        OfferingRole.MANUFACTURER,
        "20 units",
        "5 weeks",
    ),
    (
        "HC-200 Hydraulic Cylinder",
        "seed-crestline-exports@example.com",
        OfferingRole.EXPORTER,
        "20 units",
        "6 weeks",
    ),
    (
        "CP-100 Centrifugal Pump",
        "seed-bravo-manufacturing@example.com",
        OfferingRole.MANUFACTURER,
        "30 units",
        "4 weeks",
    ),
    (
        "VP-30 Vacuum Packaging Machine",
        "seed-alpha-industrial@example.com",
        OfferingRole.MANUFACTURER,
        "5 units",
        "8 weeks",
    ),
    (
        "CNC-5X Machining Center",
        "seed-bravo-manufacturing@example.com",
        OfferingRole.MANUFACTURER,
        "2 units",
        "12 weeks",
    ),
    (
        "BV-50 Ball Valve",
        "seed-crestline-exports@example.com",
        OfferingRole.SUPPLIER,
        "500 units",
        "2 weeks",
    ),
    (
        "DB-6205 Deep Groove Ball Bearing",
        "seed-deltamech-supply@example.com",
        OfferingRole.SUPPLIER,
        "1000 units",
        "1 week",
    ),
]


async def _get_or_create_company_with_owner(
    db: AsyncSession, email: str, name: str, country: str, city: str
) -> Company:
    result = await db.execute(select(User).where(User.email == email))
    user: User | None = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            hashed_password=hash_password("SeedData-Not-Real-9"),
            full_name=name.split()[0] + " Owner",
            role=Role.VIEWER,
            is_active=True,
            is_email_verified=True,
        )
        db.add(user)
        await db.flush()

    company_result = await db.execute(select(Company).where(Company.name == name))
    existing_company: Company | None = company_result.scalar_one_or_none()
    if existing_company is not None:
        return existing_company

    from app.core.slug import candidate_slugs, slugify

    base = slugify(name)
    slug = base
    for candidate in candidate_slugs(base):
        check = await db.execute(select(Company.id).where(Company.slug == candidate))
        if check.scalar_one_or_none() is None:
            slug = candidate
            break

    company = Company(
        name=name,
        legal_name=f"{name} Pvt Ltd",
        slug=slug,
        country=country,
        city=city,
        status=CompanyStatus.ACTIVE,
    )
    db.add(company)
    await db.flush()
    db.add(
        CompanyMember(
            company_id=company.id,
            user_id=user.id,
            role=CompanyRole.OWNER,
            status=CompanyMemberStatus.ACTIVE,
        )
    )
    await db.flush()
    return company


async def _get_or_create_category(db: AsyncSession, name: str) -> ProductCategory:
    result = await db.execute(select(ProductCategory).where(ProductCategory.name == name))
    existing_category: ProductCategory | None = result.scalar_one_or_none()
    if existing_category is not None:
        return existing_category
    slug = await _generate_unique_category_slug(db, name)
    category = ProductCategory(name=name, slug=slug)
    db.add(category)
    await db.flush()
    return category


async def _get_or_create_specification(
    db: AsyncSession, category_id: uuid.UUID, name: str, unit: str | None, datatype: str
) -> ProductSpecification:
    result = await db.execute(
        select(ProductSpecification).where(
            ProductSpecification.category_id == category_id, ProductSpecification.name == name
        )
    )
    existing_spec: ProductSpecification | None = result.scalar_one_or_none()
    if existing_spec is not None:
        return existing_spec
    spec = ProductSpecification(
        category_id=category_id,
        name=name,
        unit=unit,
        datatype=SpecificationDataType(datatype),
        required=False,
    )
    db.add(spec)
    await db.flush()
    return spec


async def _get_or_create_product(
    db: AsyncSession,
    name: str,
    category_id: uuid.UUID,
    industry: str,
    attribute_values: dict[str, str],
    specs_by_name: dict[str, ProductSpecification],
) -> Product:
    result = await db.execute(select(Product).where(Product.name == name))
    existing_product: Product | None = result.scalar_one_or_none()
    if existing_product is not None:
        return existing_product

    slug = await _generate_unique_product_slug(db, name)
    product = Product(
        name=name,
        slug=slug,
        description=f"{name} — seeded reference data for Phase 4B.",
        category_id=category_id,
        industry=industry,
        status=ProductStatus.PUBLISHED,  # seeded data is trusted, unlike user submissions (Phase 4A Section 6)
    )
    db.add(product)
    await db.flush()

    for spec_name, value in attribute_values.items():
        spec = specs_by_name[spec_name]
        db.add(ProductAttribute(product_id=product.id, specification_id=spec.id, value=value))
    await db.flush()
    return product


async def main() -> None:
    configure_logging()
    async with AsyncSessionLocal() as db:
        companies_by_email: dict[str, Company] = {}
        for email, name, country, city in SEED_COMPANIES:
            companies_by_email[email] = await _get_or_create_company_with_owner(
                db, email, name, country, city
            )
        await db.commit()
        logger.info("seeded_companies", count=len(companies_by_email))

        products_by_name: dict[str, Product] = {}
        for category_name, spec_defs, product_defs in SEED_CATALOG:
            category = await _get_or_create_category(db, category_name)
            specs_by_name = {}
            for spec_name, unit, datatype in spec_defs:
                specs_by_name[spec_name] = await _get_or_create_specification(
                    db, category.id, spec_name, unit, datatype
                )
            for product_name, industry, attribute_values in product_defs:
                products_by_name[product_name] = await _get_or_create_product(
                    db, product_name, category.id, industry, attribute_values, specs_by_name
                )
        await db.commit()
        logger.info("seeded_products", count=len(products_by_name))

        offering_count = 0
        for product_name, company_email, role, moq, lead_time in SEED_OFFERINGS:
            product = products_by_name[product_name]
            company = companies_by_email[company_email]
            existing = await db.execute(
                select(Offering).where(
                    Offering.product_id == product.id,
                    Offering.company_id == company.id,
                    Offering.role == role,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
            db.add(
                Offering(
                    company_id=company.id,
                    product_id=product.id,
                    role=role,
                    moq=moq,
                    lead_time=lead_time,
                    country=company.country,
                )
            )
            offering_count += 1
        try:
            await db.commit()
        except (
            DuplicateOfferingError
        ):  # pragma: no cover — idempotency guard, not expected in normal runs
            await db.rollback()
        logger.info("seeded_offerings", count=offering_count)

    print(
        f"Seeded {len(companies_by_email)} companies, {len(products_by_name)} products, {offering_count} new offerings."
    )


if __name__ == "__main__":
    asyncio.run(main())
