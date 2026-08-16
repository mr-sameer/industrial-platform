import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import app.models  # noqa: F401 — registers every model on Base.metadata for create_all below
from app.core.config import get_settings
from app.db.redis_client import get_redis_client, reset_pool_for_new_event_loop
from app.db.session import Base, get_engine
from app.main import app

settings = get_settings()


@pytest.fixture(autouse=True)
async def _reset_connections_for_this_test_loop():
    """
    pytest-asyncio gives each test function its own event loop by
    default. The SQLAlchemy async engine and the Redis connection pool
    are both module-level singletons (by design — see docs/adr/0005 and
    docs/adr/0006 — since a real running server only ever has one loop
    for its whole lifetime). In tests, a connection can only be closed
    cleanly on the same loop that opened it — asyncio ties sockets/
    futures to their creating loop, and closing (or reusing) one from a
    different loop raises "Event loop is closed" / "attached to a
    different loop" deep inside asyncpg/redis-py.

    So disposal has to happen at TEARDOWN, at the end of the test that
    used these connections, while its loop is still alive — not at the
    next test's setup, when that loop is already gone. This fixture runs
    first (autouse, no dependencies) so its teardown runs *last*,
    after every other fixture in this test has finished using the
    connections.
    """
    yield
    await get_engine().dispose()
    await reset_pool_for_new_event_loop()


@pytest.fixture(autouse=True)
async def _setup_schema(_reset_connections_for_this_test_loop):
    """
    Creates all ORM-declared tables before each test and drops them after.
    This intentionally bypasses Alembic for test speed — the migrations in
    alembic/versions/ are still the source of truth for real deployments
    and are exercised separately (see the "run alembic upgrade head" step
    in README.md), not duplicated here.

    The one exception: `company_members`' partial unique index enforcing
    "exactly one Owner per company" (docs/domain/08-business-rules.md) is
    deliberately NOT part of the declarative model (see the comment in
    app/models/company_member.py) and is created here explicitly via a
    plain **sync** (psycopg) connection — exactly matching how Alembic
    creates it in migration 0003, which is proven reliable. Creating it
    over the *async* engine (asyncpg) reproduces
    "invalid input value for enum company_role: 'owner'" even though the
    enum type's labels are directly verified correct (checked against
    pg_enum) and the identical statement succeeds via raw asyncpg *and*
    via SQLAlchemy's async engine in isolation — the failure only
    reproduces within this fixture's full sequence, and its root cause
    inside asyncpg's statement machinery wasn't worth chasing further
    once the sync-connection workaround (proven correct by the real
    migration) was available.
    """
    import sqlalchemy as sync_sa

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sync_engine = sync_sa.create_engine(settings.database_url_sync)
    with sync_engine.connect() as sync_conn:
        sync_conn.execute(
            text(
                "CREATE UNIQUE INDEX uq_company_members_one_owner "
                "ON company_members (company_id) WHERE role = 'owner'"
            )
        )
        sync_conn.commit()
    sync_engine.dispose()

    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def _clean_tables(_setup_schema):
    """Truncates all tables between tests so auth tests (e.g. unique email) don't collide."""
    engine = get_engine()
    async with engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(text(f'TRUNCATE TABLE "{table.name}" CASCADE'))
    yield


@pytest.fixture(autouse=True)
async def _flush_redis(_reset_connections_for_this_test_loop):
    """
    Clears rate-limit counters and account lockouts between tests —
    without this, login-failure tests would accumulate strikes across the
    whole test run and spuriously trigger ACCOUNT_LOCKED / RATE_LIMITED in
    unrelated tests.
    """
    client = get_redis_client()
    await client.flushdb()
    yield
    await client.aclose()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
