#!/usr/bin/env python3
"""Dynamic smoke for Ant2Maven canonical multi-output kill oracle."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analyzer.coverage_analyzer import (
    compare_xmi_models,
    compute_mutation_kill_rate,
)

LIVE = ROOT / "results_v3_troya_aligned/ant2maven_executor_live_smoke/minimal_project"

ORIGINALS = {
    "OUTMaven": LIVE / "result_OUTMaven.xmi",
    "OUTProject": LIVE / "result_OUTProject.xmi",
}


def rewrite_xml(path: Path, *, attr_order_only=False, change_value=False):
    import xml.etree.ElementTree as ET

    tree = ET.parse(path)
    root = tree.getroot()

    if attr_order_only:
        # Produce valid XML with different formatting and attribute order.
        for elem in root.iter():
            reversed_items = list(elem.attrib.items())[::-1]
            elem.attrib.clear()
            elem.attrib.update(reversed_items)
        ET.indent(tree, space="  ")

    if change_value:
        # Add a valid semantic attribute change to the model root.
        root.set("changed_probe", "yes")

    tree.write(path, encoding="utf-8", xml_declaration=True)


def mutant_result(outputs: dict[str, Path]):
    return {
        "success": True,
        "outputs": {name: str(path) for name, path in outputs.items()},
        "output": str(next(iter(outputs.values()))),
        "trace": None,
        "returncode": 0,
        "stdout": "",
        "stderr": "",
        "error": None,
    }


def main() -> int:
    for path in ORIGINALS.values():
        if not path.is_file():
            raise SystemExit(f"missing live smoke output: {path}")

    with tempfile.TemporaryDirectory(
        dir=ROOT / "results_v3_troya_aligned",
        prefix="ant_multi_output_oracle_",
    ) as tmp_name:
        tmp = Path(tmp_name)

        same = {}
        whitespace = {}
        project_changed = {}
        maven_changed = {}

        for label, source in ORIGINALS.items():
            for bucket, mapping in [
                ("same", same),
                ("whitespace", whitespace),
                ("project_changed", project_changed),
                ("maven_changed", maven_changed),
            ]:
                dest = tmp / bucket / f"result_{label}.xmi"
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                mapping[label] = dest

        for path in whitespace.values():
            rewrite_xml(path, attr_order_only=True)

        rewrite_xml(project_changed["OUTProject"], change_value=True)
        rewrite_xml(maven_changed["OUTMaven"], change_value=True)

        missing_project = {
            "OUTMaven": same["OUTMaven"],
        }

        mutant_results = {
            "same": mutant_result(same),
            "whitespace_only": mutant_result(whitespace),
            "project_only_changed": mutant_result(project_changed),
            "maven_only_changed": mutant_result(maven_changed),
            "missing_project": mutant_result(missing_project),
        }

        direct = compute_mutation_kill_rate(
            {"outputs": {name: str(path) for name, path in ORIGINALS.items()}},
            mutant_results,
        )

        checks = {
            "same_not_killed": "same" not in direct["killed"],
            "whitespace_not_killed": "whitespace_only" not in direct["killed"],
            "project_only_change_killed": "project_only_changed" in direct["killed"],
            "maven_only_change_killed": "maven_only_changed" in direct["killed"],
            "missing_project_reported_error": "missing_project" in direct["errors"],
            "project_diff_detail_true": (
                direct["diff_details"]["project_only_changed"]
                ["outputs"]["OUTProject"]["different"] is True
            ),
            "project_other_output_false": (
                direct["diff_details"]["project_only_changed"]
                ["outputs"]["OUTMaven"]["different"] is False
            ),
        }

        print("================ direct multi-output result ================")
        print(json.dumps(direct, indent=2))
        print("\n================ checks ================")
        print(json.dumps(checks, indent=2))

        passed = all(checks.values())
        print("\npassed:", passed)

        out = ROOT / "results_v3_troya_aligned/ant2maven_multi_output_oracle_audit/dynamic_smoke.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "checks": checks,
            "result": direct,
            "passed": passed,
        }, indent=2), encoding="utf-8")
        print("wrote:", out)

        return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
