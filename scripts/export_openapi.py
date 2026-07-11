#!/usr/bin/env python
"""Export the OpenAPI schema to a file (contract / UI-client source of truth).

Run:  uv run python scripts/export_openapi.py [output_path]
Default output: openapi.json
"""

from __future__ import annotations

import json
import sys

from governance_api.main import create_app


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "openapi.json"
    schema = create_app().openapi()
    with open(out, "w") as fh:
        json.dump(schema, fh, indent=2)
    print(f"wrote {out} ({len(schema.get('paths', {}))} paths)")


if __name__ == "__main__":
    main()
