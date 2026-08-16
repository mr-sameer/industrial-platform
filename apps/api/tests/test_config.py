"""
Regression tests for the upload-storage-path configuration bug: bare
`uvicorn app.main:app --reload` (no Docker, no UPLOAD_STORAGE_PATH env
var) used to crash with `OSError: [Errno 30] Read-only file system:
'/app'`, because the default fell back to a Docker-only path. See
docs/adr/0030-upload-storage-path-configuration-bug.md.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from app.core.config import Settings, _default_local_upload_path


def test_default_local_upload_path_is_never_the_docker_path() -> None:
    """The computed default must never silently be /app/uploads — that's exactly this bug."""
    assert _default_local_upload_path() != "/app/uploads"


def test_default_local_upload_path_is_absolute_and_repo_relative() -> None:
    """Deterministic regardless of the process's current working directory — not "./uploads"."""
    path = _default_local_upload_path()
    assert path.endswith("/apps/api/uploads") or path.endswith("apps/api/uploads")


def test_settings_with_no_env_override_resolves_to_local_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates bare `uvicorn` with no .env file and no UPLOAD_STORAGE_PATH env var."""
    monkeypatch.delenv("UPLOAD_STORAGE_PATH", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.upload_storage_path != "/app/uploads"
    assert settings.upload_storage_path == _default_local_upload_path()


def test_explicit_env_var_still_overrides_the_default_docker_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Docker's docker-compose.yml sets this explicitly — must still win over the local default."""
    monkeypatch.setenv("UPLOAD_STORAGE_PATH", "/app/uploads")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.upload_storage_path == "/app/uploads"


@pytest.mark.asyncio
async def test_bare_uvicorn_import_does_not_raise_with_no_env_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """
    The actual reported failure mode: importing app.main (which creates
    the upload directory at startup) must not raise OSError when no
    UPLOAD_STORAGE_PATH is configured. Run in a subprocess with a clean
    environment and cwd, since the current test process already has
    UPLOAD_STORAGE_PATH set (see conftest.py's test env) and we
    specifically need to prove the *unset* case works.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=tmp_path,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(Path(__file__).parent.parent)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}"
    assert "Read-only file system" not in result.stderr
