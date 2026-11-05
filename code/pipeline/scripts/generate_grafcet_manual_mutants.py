#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import argparse
import csv
import json
import re
import subprocess
import shutil
import sys

ROOT = Path(".").resolve()
sys.path.insert(0, str(ROOT))

from src.experiment.multi_config_experiment import DATASETS, _dataset_executor_config
from src.executor.transformation_executor import run_transformation


RULES = ["PetriNet", "Place", "Transition", "PlaceToTransition", "TransitionToPlace"]




def replace_in_rule(text: str, rule: str, old: str, new: str) -> str | None:
    pat = re.compile(rf"(?ms)^rule\s+{re.escape(rule)}\s*\{{.*?(?=^rule\s+|\Z)")
    m = pat.search(text)
    if not m:
        return None
    block = m.group(0)
    if old not in block:
        return None
    new_block = block.replace(old, new, 1)
    return text[:m.start()] + new_block + text[m.end():]


def specs() -> list[dict]:
    out = []

    def add(rule, op, old, new):
        out.append({"rule": rule, "operator": op, "old": old, "new": new})

    for rule in RULES:
        add(rule, "location_to_name", "location <- g.location", "location <- g.name")
        add(rule, "name_to_location", "name <- g.name", "name <- g.location")
        add(rule, "empty_name", "name <- g.name", "name <- ''")
        add(rule, "empty_location", "location <- g.location", "location <- ''")

    add("PetriNet", "drop_elements_binding", "elements <- g.elements", "elements <- Sequence{}")
    add("PetriNet", "drop_arcs_binding", "arcs <- g.connections", "arcs <- Sequence{}")

    for rule in ["Place", "Transition"]:
        add(rule, "drop_net_binding", "net <- g.grafcet", "net <- OclUndefined")
        add(rule, "drop_incoming_arc", "incomingArc <- g.incomingConnections", "incomingArc <- Sequence{}")
        add(rule, "drop_outgoing_arc", "outgoingArc <- g.outgoingConnections", "outgoingArc <- Sequence{}")

    add("Place", "target_class_place_to_transition", "p : PetriNet!Place", "p : PetriNet!Transition")
    add("Transition", "target_class_transition_to_place", "p : PetriNet!Transition", "p : PetriNet!Place")

    for rule in ["PlaceToTransition", "TransitionToPlace"]:
        add(rule, "drop_net_binding", "net <- g.grafcet", "net <- OclUndefined")
        add(rule, "drop_from_endpoint", '"from" <- g."from"', '"from" <- OclUndefined')
        add(rule, "drop_to_endpoint", '"to" <- g."to"', '"to" <- OclUndefined')
        add(rule, "swap_endpoints_from", '"from" <- g."from"', '"from" <- g."to"')
        add(rule, "swap_endpoints_to", '"to" <- g."to"', '"to" <- g."from"')

    add(
        "PlaceToTransition",
        "target_class_pt_to_tp",
        "p : PetriNet!PlaceToTransition",
        "p : PetriNet!TransitionToPlace",
    )
    add(
        "TransitionToPlace",
        "target_class_tp_to_pt",
        "p : PetriNet!TransitionToPlace",
        "p : PetriNet!PlaceToTransition",
    )

    return out


def result_ok(result: dict) -> bool:
    return bool(result.get("success") or result.get("ok") or result.get("status") == "OK")


def clean_compiled(trans: Path, name: str) -> None:
    for suffix in [".asm", ".emftvm"]:
        p = trans / f"{name}{suffix}"
        if p.exists():
            p.unlink()


def compile_atl(root: Path, atl_path: Path, asm_path: Path) -> dict:
    cmd = ["java", "-cp", "lib/*:lib", "ATLAsmCompilerRunner", str(atl_path), str(asm_path)]
    p = subprocess.run(cmd, cwd=root, text=True, capture_output=True, timeout=120)
    return {
        "returncode": p.returncode,
        "stdout": p.stdout,
        "stderr": p.stderr,
        "asm_exists": asm_path.exists(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--prefix", default="Grafcet2PetriNet_ManualMutant")
    ap.add_argument("--keep-rejected", action="store_true")
    args = ap.parse_args()

    ds = DATASETS["Grafcet2PetriNet"]
    cfg = _dataset_executor_config(ds)
    trans = Path(cfg["transformations_dir"])
    base_atl = trans / f"{cfg['atl_name']}.atl"
    base_text = base_atl.read_text(encoding="utf-8")

    examples = sorted(
        (ROOT / "results_v3_troya_aligned/grafcet2petrinet_extension/draft_examples").glob("*.xmi")
    )
    if len(examples) != 3:
        raise SystemExit(f"Expected 3 Grafcet examples, found {len(examples)}")

    work = ROOT / "results_v3_troya_aligned/grafcet2petrinet_extension/manual_mutant_gate"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    accepted = []
    rejected = []
    seen_texts = set()
    idx = 1

    for spec in specs():
        if len(accepted) >= args.n:
            break

        mutated = replace_in_rule(base_text, spec["rule"], spec["old"], spec["new"])
        if mutated is None:
            rejected.append({**spec, "status": "PATTERN_NOT_FOUND"})
            continue

        candidate_text = mutated
        if candidate_text in seen_texts:
            rejected.append({**spec, "status": "DUPLICATE_TEXT"})
            continue
        seen_texts.add(candidate_text)

        mutant = f"{args.prefix}{idx:03d}"
        idx += 1
        mutant_path = trans / f"{mutant}.atl"
        mutant_path.write_text(mutated, encoding="utf-8")
        clean_compiled(trans, mutant)

        asm_path = trans / f"{mutant}.asm"
        compile_res = compile_atl(ROOT, mutant_path, asm_path)
        if compile_res["returncode"] != 0 or not compile_res["asm_exists"]:
            rejected.append({
                "mutant": mutant,
                **spec,
                "status": "COMPILE_FAIL",
                "compile": compile_res,
            })
            print("[DROP]", mutant, spec["rule"], spec["operator"], "COMPILE_FAIL", flush=True)
            if not args.keep_rejected:
                mutant_path.unlink(missing_ok=True)
                clean_compiled(trans, mutant)
            continue

        failures = []
        for ex in examples:
            out_model = work / mutant / f"{ex.stem}_out.xmi"
            out_model.parent.mkdir(parents=True, exist_ok=True)
            try:
                res = run_transformation(str(ex), str(out_model), mutant, cfg)
            except Exception as e:
                failures.append(f"{ex.name}: EXCEPTION {type(e).__name__}: {e}")
                continue
            if not result_ok(res):
                failures.append(f"{ex.name}: {res}")

        if failures:
            rejected.append({
                "mutant": mutant,
                **spec,
                "status": "EXEC_OR_COMPILE_FAIL",
                "failures": failures[:3],
            })
            print("[DROP]", mutant, spec["rule"], spec["operator"], failures[0], flush=True)
            if not args.keep_rejected:
                mutant_path.unlink(missing_ok=True)
                clean_compiled(trans, mutant)
            continue

        row = {
            "mutant": mutant,
            "path": str(mutant_path),
            "rule": spec["rule"],
            "target_rule": spec["rule"],
            "operator": spec["operator"],
            "old": spec["old"],
            "new": spec["new"],
            "analysis_scope": "main",
            "lifecycle": "accepted",
            
        }
        accepted.append(row)
        print("[ACCEPT]", mutant, spec["rule"], spec["operator"], flush=True)

    manifest = {
        "dataset": "Grafcet2PetriNet",
        "atl_name": cfg["atl_name"],
        "base_atl": str(base_atl),
        
        "prefix": args.prefix,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "gate": "manual_single_rule_single_edit_exec_gate_on_3_examples",
        "examples": [str(p) for p in examples],
        "accepted": accepted,
        "rejected": rejected,
    }

    manifest_path = trans / f"{args.prefix}_manifest.json"
    csv_path = trans / f"{args.prefix}_manifest.csv"

    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        fields = ["mutant", "path", "rule", "target_rule", "operator", "old", "new", "analysis_scope", "lifecycle"]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in accepted:
            w.writerow({k: row.get(k, "") for k in fields})

    print("accepted:", len(accepted))
    print("rejected:", len(rejected))
    print("manifest:", manifest_path)
    print("csv:", csv_path)

    if not accepted:
        raise SystemExit("No accepted Grafcet mutants")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
