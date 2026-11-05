#!/usr/bin/env python3
"""Generate legacy Ant2Maven rule-disable mutants without implicit writes."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TRANS_DIR = ROOT / "datasets/models_Ant2Maven/transformations"


def find_matching_brace(text: str, open_idx: int) -> int:
    depth = 0
    for index in range(open_idx, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def disable_first_from_pattern(block: str) -> tuple[str, bool]:
    match = re.search(r"(from\s+\w+\s*:\s*\w+!\w+\s*)\(", block)
    if match:
        return (
            block[:match.end()] + "false and " + block[match.end():],
            True,
        )

    match = re.search(r"(from\s+\w+\s*:\s*\w+!\w+)", block)
    if match:
        return block[:match.end()] + "(false)" + block[match.end():], True

    return block, False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_TRANS_DIR,
    )
    parser.add_argument(
        "--prefix",
        default="Ant2Maven_Mutant",
    )
    parser.add_argument(
        "--manifest-name",
        default="Ant2Maven_mutant_manifest.json",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow overwriting existing mutant ATL files and manifest.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    trans_dir = args.output_dir.resolve()
    original = DEFAULT_TRANS_DIR / "Ant2Maven.atl"
    text = original.read_text(encoding="utf-8", errors="replace")

    rule_re = re.compile(
        r"(?m)^[ \t]*(?:abstract[ \t]+)?(?:unique[ \t]+)?"
        r"(?:lazy[ \t]+)?rule[ \t]+([A-Za-z_]\w*)[ \t]*\{"
    )

    rules = []
    for match in rule_re.finditer(text):
        rule_name = match.group(1)
        open_idx = text.find("{", match.start())
        close_idx = find_matching_brace(text, open_idx)
        if close_idx >= 0:
            rules.append((rule_name, match.start(), close_idx + 1))

    planned = []
    mutant_id = 1

    for rule_name, start, end in rules:
        block = text[start:end]
        mutated_block, ok = disable_first_from_pattern(block)
        if not ok:
            print(f"[skip] {rule_name}: no from pattern found")
            continue

        mutant_name = f"{args.prefix}{mutant_id}"
        planned.append({
            "mutant": mutant_name,
            "rule": rule_name,
            "text": text[:start] + mutated_block + text[end:],
            "path": trans_dir / f"{mutant_name}.atl",
        })
        mutant_id += 1

    manifest_path = trans_dir / args.manifest_name
    conflicts = [
        str(row["path"])
        for row in planned
        if row["path"].exists()
    ]
    if manifest_path.exists():
        conflicts.append(str(manifest_path))

    if conflicts and not args.force:
        raise SystemExit(
            "Refusing to overwrite existing files. "
            "Use a unique --output-dir/--prefix or pass --force:\n"
            + "\n".join(conflicts[:20])
        )

    trans_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for row in planned:
        row["path"].write_text(row["text"], encoding="utf-8")
        manifest.append({
            "mutant": row["mutant"],
            "operator": "rule_disabled_by_false_guard",
            "faulty_rules": [row["rule"]],
            "source": str(row["path"]),
        })
        print(f'[write] {row["mutant"]}: disabled rule {row["rule"]}')

    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )

    print(f"[done] generated {len(manifest)} mutants")
    print(f"[manifest] {manifest_path}")


if __name__ == "__main__":
    main()
