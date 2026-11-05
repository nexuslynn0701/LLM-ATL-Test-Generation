from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def find_mutant_manifest(transformations_dir: str | Path, atl_name: str) -> Path:
    trans = Path(transformations_dir)
    candidates = [
        trans / f"{atl_name}_FormalMutant_manifest.json",
        trans / f"{atl_name}_LegacyArtifactMutant_manifest.json",
        trans / f"{atl_name}_mutant_manifest.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"No mutant manifest found for {atl_name} in {trans}")

def load_mutant_manifest(transformations_dir: str | Path, atl_name: str) -> dict[str, Any]:
    p = find_mutant_manifest(transformations_dir, atl_name)
    data = json.loads(p.read_text(encoding="utf-8"))
    data["_manifest_path"] = str(p)
    return data

def load_buggy_rule_metadata(
    transformations_dir: str | Path,
    atl_name: str,
    *,
    analysis_scope: str | None = "main",
) -> dict[str, list[str]]:
    manifest = load_mutant_manifest(transformations_dir, atl_name)
    out: dict[str, list[str]] = {}

    for rec in manifest.get("accepted", []):
        if analysis_scope is not None and rec.get("analysis_scope") != analysis_scope:
            continue

        mutant = rec["mutant"]
        if rec.get("analysis_scope") == "main":
            target_rule = rec.get("target_rule")
            if not isinstance(target_rule, str):
                raise ValueError(f"{mutant}: main record has invalid target_rule={target_rule!r}")
            out[mutant] = [target_rule]
        else:
            target_rules = rec.get("target_rules")
            if not isinstance(target_rules, list) or not target_rules:
                raise ValueError(f"{mutant}: sensitivity record has invalid target_rules={target_rules!r}")
            out[mutant] = list(target_rules)

    return out
