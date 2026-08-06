#!/usr/bin/env python3
"""
Regenerates docs/architecture/openapi.json from the live FastAPI app
definition — run this after any route/schema change so the checked-in
spec doesn't drift from reality:

    cd apps/api && python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent / "docs" / "architecture" / "openapi.json"
)


def main() -> None:
    spec = app.openapi()
    OUTPUT_PATH.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"Wrote {len(spec['paths'])} paths to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
