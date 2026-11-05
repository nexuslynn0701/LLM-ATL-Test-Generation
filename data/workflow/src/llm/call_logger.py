"""Minimal JSONL call logger without file-integrity metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path

_context: dict[str, object] = {}


def set_context(**fields: object) -> None:
    _context.update(fields)


def log_call(record: dict[str, object]) -> None:
    destination = os.environ.get("LLM_CALL_LOG", "")
    if not destination:
        return
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {**_context, **record}
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
