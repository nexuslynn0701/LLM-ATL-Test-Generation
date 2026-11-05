#!/usr/bin/env python3
"""Static audit of Ant2Maven multi-output oracle wiring."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results_v3_troya_aligned/ant2maven_multi_output_oracle_audit"
OUT.mkdir(parents=True, exist_ok=True)

FILES = [
    ROOT / "src/executor/transformation_executor.py",
    ROOT / "src/experiment/multi_config_experiment.py",
    ROOT / "src/experiment/run_ladder_experiment.py",
    ROOT / "src/experiment/experiment_runner.py",
    ROOT / "scripts/run_ant2maven_failratio_pilot.py",
    ROOT / "scripts/eval_ant2maven_failratio_existing.py",
]

PATTERNS = {
    "outputs_access": r"\boutputs\b",
    "single_output_access": r'get\(["\']output["\']\)|\[\s*["\']output["\']\s*\]',
    "target_mms": r"\btarget_mms\b",
    "canonical": r"canonical|normalize|c14n",
    "xml_parse": r"ElementTree|ET\.parse|fromstring|lxml",
    "raw_file_compare": r"read_bytes|read_text|filecmp|cmp\(",
    "kill_terms": r"killed|failed|different|diff|equivalent|mutation_score",
}


def matching_lines(text: str, pattern: str) -> list[dict]:
    regex = re.compile(pattern, re.IGNORECASE)
    return [
        {
            "line": index,
            "text": line.rstrip(),
        }
        for index, line in enumerate(text.splitlines(), start=1)
        if regex.search(line)
    ]


def main() -> None:
    rows = []

    for path in FILES:
        if not path.is_file():
            rows.append({
                "path": str(path.relative_to(ROOT)),
                "exists": False,
            })
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        rows.append({
            "path": str(path.relative_to(ROOT)),
            "exists": True,
            "matches": {
                name: matching_lines(text, pattern)
                for name, pattern in PATTERNS.items()
            },
        })

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "scope": "Static audit only; no implementation claim is inferred automatically.",
        "required_ant2maven_oracle": {
            "failed": (
                "canonical_diff(OUTMaven_original, OUTMaven_mutant) "
                "OR canonical_diff(OUTProject_original, OUTProject_mutant)"
            ),
            "record_shape": {
                "failed": True,
                "outputs": {
                    "OUTMaven": {"different": True},
                    "OUTProject": {"different": False},
                },
            },
        },
        "files": rows,
    }

    path = OUT / "static_audit.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("Wrote:", path)

    for row in rows:
        print("\n================", row["path"], "================")
        if not row["exists"]:
            print("missing")
            continue

        for name, matches in row["matches"].items():
            if not matches:
                continue
            print(f"\n-- {name}")
            for match in matches[:30]:
                print(f'{match["line"]:5d}: {match["text"]}')


if __name__ == "__main__":
    main()
