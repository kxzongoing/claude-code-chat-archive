from __future__ import annotations

import json
import os
from typing import Any

MANIFEST_FILENAME = "manifest.json"


def load_manifest(output_root: str) -> dict[str, Any]:
    path = os.path.join(output_root, MANIFEST_FILENAME)
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_manifest(output_root: str, manifest: dict[str, Any]) -> None:
    path = os.path.join(output_root, MANIFEST_FILENAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def manifest_key(project_dir: str, session_id: str) -> str:
    return f"{project_dir}/{session_id}"
