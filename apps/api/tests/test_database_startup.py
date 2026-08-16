"""
Regression tests for the database-startup auto-fix mechanism —
app.main._verify_database_connection / _try_auto_create_role_and_database.

Context: a reported `role "platform_user" does not exist` error
persisted even after a manual bootstrap step was documented, because
the failure only ever surfaced deep inside a request handler with no
indication of which DATABASE_URL was actually in play, and because a
separate manual script is easy to skip or accidentally run against a
different Postgres instance than the one the app itself connects to.
These tests cover the fix: the app now verifies (and can self-heal)
its own database connection at startup, using the exact connection the
running process would use — eliminating the "which instance" ambiguity
by construction.
"""

import os
import uuid

import pytest

from app.main import _parse_database_url, _try_auto_create_role_and_database


def test_parse_database_url_extracts_all_fields() -> None:
    parsed = _parse_database_url(
        "postgresql+asyncpg://platform_user:change_me_locally@localhost:5432/industrial_platform"
    )
    assert parsed == {
        "user": "platform_user",
        "password": "change_me_locally",
        "host": "localhost",
        "port": "5432",
        "dbname": "industrial_platform",
    }


def test_parse_database_url_rejects_unparseable_input() -> None:
    with pytest.raises(ValueError, match="Could not parse DATABASE_URL"):
        _parse_database_url("not-a-valid-url")


@pytest.mark.asyncio
async def test_auto_create_refuses_non_local_host() -> None:
    """Never attempts privilege escalation against a remote server —
    only ever a local target, matching scripts/bootstrap_local_postgres.sh's
    own same restriction."""
    parsed = {
        "user": "some_user",
        "password": "some_password",
        "host": "db.example.com",
        "port": "5432",
        "dbname": "some_db",
    }
    result = await _try_auto_create_role_and_database(parsed)
    assert result is False


async def _ensure_os_user_has_peer_auth_role() -> None:
    """
    The auto-fix connects via the Unix socket as the current OS user
    (peer auth) — these tests need that role to genuinely exist to
    exercise the real code path, the same real precondition a
    developer's own machine would or wouldn't have. Created via the
    test suite's own already-known-good admin connection
    (DATABASE_URL's platform_user, a superuser per
    scripts/bootstrap_local_postgres.sh) rather than assumed to already
    be present — self-contained, not dependent on whatever a previous,
    unrelated debugging session happened to leave behind.
    """
    import asyncpg

    os_user = os.environ.get("USER") or os.environ.get("LOGNAME") or "root"
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="platform_user",
        password="change_me_locally",
        database="postgres",
        timeout=5,
    )
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", os_user)
        if not exists:
            await conn.execute(f'CREATE ROLE "{os_user}" WITH LOGIN SUPERUSER')
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_auto_create_role_and_database_end_to_end() -> None:
    """
    Real end-to-end proof, against the real local Postgres this test
    suite already runs against: given a role/database that doesn't
    exist yet, the auto-fix creates both, using only a local Unix-socket
    connection this process can already establish — no manual step.
    """
    unique = uuid.uuid4().hex[:8]
    test_role = f"autofix_test_role_{unique}"
    test_db = f"autofix_test_db_{unique}"
    parsed = {
        "user": test_role,
        "password": "test-password-not-real",
        "host": "localhost",
        "port": "5432",
        "dbname": test_db,
    }

    import asyncpg

    await _ensure_os_user_has_peer_auth_role()

    try:
        result = await _try_auto_create_role_and_database(parsed)
        assert result is True

        # Prove it actually exists now, via a fresh connection using the
        # exact credentials the auto-fix just created.
        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user=test_role,
            password="test-password-not-real",
            database=test_db,
            timeout=5,
        )
        try:
            current_db = await conn.fetchval("SELECT current_database()")
            assert current_db == test_db
        finally:
            await conn.close()
    finally:
        admin_conn = await asyncpg.connect(database="postgres", timeout=5)
        try:
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{test_db}"')
            await admin_conn.execute(f'DROP ROLE IF EXISTS "{test_role}"')
        finally:
            await admin_conn.close()


@pytest.mark.asyncio
async def test_auto_create_when_only_database_is_missing() -> None:
    """
    Regression test for a real gap found after the initial fix shipped:
    a role can exist while its database doesn't (e.g. the role survives
    a DROP DATABASE, or was created for something else entirely) — this
    is InvalidCatalogNameError, a genuinely different asyncpg exception
    than the role-missing case, and the first version of
    _verify_database_connection's except clause didn't catch it at
    all, so this scenario fell through to an uncaught crash — exactly
    the failure mode this whole mechanism exists to prevent. Found via
    direct reproduction (drop only the database, leave the role), not
    assumed to be covered by the existing role-missing tests.
    """
    await _ensure_os_user_has_peer_auth_role()
    unique = uuid.uuid4().hex[:8]
    test_role = f"autofix_dbonly_role_{unique}"
    test_db = f"autofix_dbonly_db_{unique}"
    parsed = {
        "user": test_role,
        "password": "test-password-not-real",
        "host": "localhost",
        "port": "5432",
        "dbname": test_db,
    }

    import asyncpg

    # Pre-create only the role, matching the exact scenario: role
    # exists, database doesn't.
    admin_conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="platform_user",
        password="change_me_locally",
        database="postgres",
        timeout=5,
    )
    try:
        await admin_conn.execute(
            f'CREATE ROLE "{test_role}" WITH LOGIN SUPERUSER ' f"PASSWORD '{parsed['password']}'"
        )
    finally:
        await admin_conn.close()

    try:
        result = await _try_auto_create_role_and_database(parsed)
        assert result is True

        conn = await asyncpg.connect(
            host="localhost",
            port=5432,
            user=test_role,
            password="test-password-not-real",
            database=test_db,
            timeout=5,
        )
        try:
            current_db = await conn.fetchval("SELECT current_database()")
            assert current_db == test_db
        finally:
            await conn.close()
    finally:
        admin_conn = await asyncpg.connect(database="postgres", timeout=5)
        try:
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{test_db}"')
            await admin_conn.execute(f'DROP ROLE IF EXISTS "{test_role}"')
        finally:
            await admin_conn.close()


@pytest.mark.asyncio
async def test_auto_create_is_idempotent_when_already_exists() -> None:
    """Running the auto-fix against a role/database that already exists
    (e.g. this test suite's own) is a safe no-op, not an error."""
    await _ensure_os_user_has_peer_auth_role()
    parsed = _parse_database_url(
        "postgresql+asyncpg://platform_user:change_me_locally@localhost:5432/industrial_platform_test"
    )
    result = await _try_auto_create_role_and_database(parsed)
    assert result is True
