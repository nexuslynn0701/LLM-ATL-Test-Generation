from pathlib import Path
import csv
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analyzer.sbfl_analyzer import BUGGY_RULES
from src.experiment.multi_config_experiment import DATASETS, _dataset_executor_config

SUBJECTS = {
    "BibTeX2DocBook": "BibTeX2DocBook",
    "CPL2SPL": "CPL2SPL",
    "UML2ER": "SimpleUml2ER",
    "Ecore2Maude": "Ecore2Maude",
}

AUDIT = Path("results/mutant_audit/mutant_operator_comment_audit.csv")

def load_operator_audit():
    by_mutant = {}
    if not AUDIT.exists():
        return by_mutant

    with AUDIT.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mutant = row.get("mutant")
            if not mutant:
                continue
            ops = (
                row.get("operators")
                or row.get("operator")
                or row.get("primary_operator")
                or row.get("comment_operator")
                or "unknown_operator"
            )
            if isinstance(ops, str):
                sub_ops = [x.strip() for x in re.split(r"[;+]", ops) if x.strip()]
            else:
                sub_ops = ["unknown_operator"]
            by_mutant[mutant] = {
                "operator_type": row.get("primary_operator") or row.get("operator") or sub_ops[0],
                "sub_operators": sub_ops or ["unknown_operator"],
                "operator_source": "comment_audit",
            }
    return by_mutant

def read_atl_rules(atl_path):
    if not atl_path.exists():
        return set()
    text = atl_path.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"\brule\s+([A-Za-z_]\w*)\s*\{", text))

def main():
    op_audit = load_operator_audit()

    schema = {
        "main": {
            "analysis_scope": "main",
            "fault_models": ["legacy_single_location", "single_rule_single_operator", "same_rule_coupled"],
            "target_rule": "single ATL rule name string",
            "target_rules": "single-element provenance list",
        },
        "sensitivity": {
            "analysis_scope": "sensitivity",
            "fault_models": ["legacy_cross_rule_multi_fault", "cross_rule_multi_fault"],
            "target_rules": "two-or-more ATL rule name strings",
            "target_rule": "absent",
        },
        "note": "Legacy manifests are reconstructed from src.analyzer.sbfl_analyzer.BUGGY_RULES; original generation metadata is not available in this repo.",
    }

    for subject, prefix in SUBJECTS.items():
        ds = DATASETS[subject]
        cfg = _dataset_executor_config(ds)
        trans = Path(cfg["transformations_dir"])
        atl_name = cfg["atl_name"]
        original_atl = trans / f"{atl_name}.atl"
        atl_rules = read_atl_rules(original_atl)

        records = []
        bad_rules = []

        keys = sorted(
            [k for k in BUGGY_RULES if k.startswith(prefix + "_Mutant")],
            key=lambda x: int(re.search(r"Mutant(\d+)", x).group(1)),
        )

        for mutant in keys:
            rules = list(BUGGY_RULES[mutant])
            audit = op_audit.get(mutant, {
                "operator_type": "unknown_operator",
                "sub_operators": ["unknown_operator"],
                "operator_source": "not_available",
            })

            rec = {
                "mutant": mutant,
                "dataset": subject,
                "lifecycle": "legacy_artifact",
                "has_atl": (trans / f"{mutant}.atl").exists(),
                "has_asm": (trans / f"{mutant}.asm").exists(),
                "operator_type": audit["operator_type"],
                "sub_operators": audit["sub_operators"],
                "operator_source": audit["operator_source"],
                "target_rules": rules,
            }

            if len(rules) == 1:
                rec["analysis_scope"] = "main"
                rec["fault_model"] = "legacy_single_location"
                rec["target_rule"] = rules[0]
            else:
                rec["analysis_scope"] = "sensitivity"
                rec["fault_model"] = "legacy_cross_rule_multi_fault"

            for rule in rules:
                if atl_rules and rule not in atl_rules:
                    bad_rules.append((mutant, rule))

            records.append(rec)

        manifest = {
            "dataset": subject,
            "atl_name": atl_name,
            "source": "legacy_troya_sbfl_mt_artifact_reconstructed_from_BUGGY_RULES",
            "manifest_schema": schema,
            "accepted_count": len(records),
            "main_count": sum(r["analysis_scope"] == "main" for r in records),
            "sensitivity_count": sum(r["analysis_scope"] == "sensitivity" for r in records),
            "accepted": records,
            "bad_target_rules": bad_rules,
        }

        out = trans / f"{atl_name}_LegacyArtifactMutant_manifest.json"
        out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        print(subject)
        print("  manifest:", out)
        print("  total:", len(records))
        print("  main:", manifest["main_count"])
        print("  sensitivity:", manifest["sensitivity_count"])
        print("  bad_target_rules:", len(bad_rules))

if __name__ == "__main__":
    main()
