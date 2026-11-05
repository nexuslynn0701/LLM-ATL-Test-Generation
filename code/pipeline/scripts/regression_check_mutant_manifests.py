from pathlib import Path
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.analyzer.sbfl_analyzer import BUGGY_RULES
from src.experiment.multi_config_experiment import DATASETS, _dataset_executor_config

SUBJECTS = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude", "Ant2Maven"]

def manifest_path_for(subject):
    ds = DATASETS[subject]
    cfg = _dataset_executor_config(ds)
    trans = Path(cfg["transformations_dir"])
    atl = cfg["atl_name"]

    candidates = [
        trans / f"{atl}_FormalMutant_manifest.json",
        trans / f"{atl}_LegacyArtifactMutant_manifest.json",
        trans / f"{atl}_mutant_manifest.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"no manifest for {subject}: {candidates}")

def main():
    for subject in SUBJECTS:
        p = manifest_path_for(subject)
        m = json.loads(p.read_text(encoding="utf-8"))
        records = m["accepted"]

        main_recs = [r for r in records if r.get("analysis_scope") == "main"]
        sens_recs = [r for r in records if r.get("analysis_scope") == "sensitivity"]

        print("\n" + subject)
        print("  manifest:", p)
        print("  total:", len(records))
        print("  main:", len(main_recs))
        print("  sensitivity:", len(sens_recs))

        bad = []
        for r in main_recs:
            if not isinstance(r.get("target_rule"), str):
                bad.append((r["mutant"], "target_rule_not_string", r.get("target_rule")))
            if r.get("target_rules") != [r.get("target_rule")]:
                bad.append((r["mutant"], "target_rules_mismatch", r.get("target_rules"), r.get("target_rule")))

        for r in sens_recs:
            if "target_rule" in r:
                bad.append((r["mutant"], "sensitivity_has_target_rule", r["target_rule"]))
            if not isinstance(r.get("target_rules"), list) or len(r["target_rules"]) < 2:
                bad.append((r["mutant"], "bad_sensitivity_target_rules", r.get("target_rules")))

        if subject != "Ant2Maven":
            mismatch = []
            for r in records:
                old = list(BUGGY_RULES.get(r["mutant"], []))
                new = list(r.get("target_rules", []))
                if old != new:
                    mismatch.append((r["mutant"], old, new))
            print("  BUGGY_RULES mismatches:", len(mismatch))
            for x in mismatch[:10]:
                print("   ", x)

        print("  schema errors:", len(bad))
        for x in bad[:10]:
            print("   ", x)

if __name__ == "__main__":
    main()
