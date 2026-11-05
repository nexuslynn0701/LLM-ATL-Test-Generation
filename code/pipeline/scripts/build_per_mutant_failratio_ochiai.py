#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import csv
from pathlib import Path
from collections import Counter

inp_dir = Path("results/sbfl_export")

out_all = Path("results/final_summary/per_mutant_failratio_ochiai.csv")
out_main = Path("results/final_summary/per_mutant_failratio_ochiai_main.csv")

out_all.parent.mkdir(parents=True, exist_ok=True)

fields = [
    "dataset",
    "method",
    "mutant",
    "buggy_rules",
    "total_tests",
    "total_fail",
    "total_pass",
    "fail_ratio",
    "ochiai_AC",
    "ochiai_BC",
    "ochiai_WC",
    "tarantula_AC",
    "dstar_AC",
    "zoltar_AC",
]

MAIN_METHODS = {
    "random",
    "core",
    "FL_AWARE",
    "MIXED_MODE",
}

EXCLUDE_FILES_CONTAINING = {
    "MASTER",
    "summary",
    "config",
}


def should_skip_file(p: Path) -> bool:
    name = p.name
    for token in EXCLUDE_FILES_CONTAINING:
        if token in name:
            return True
    return False


def normalize_method(method: str) -> str:
    method = (method or "").strip()

    if method in {"random", "core", "FL_AWARE", "MIXED_MODE", "SAT_AWARE"}:
        return method

    low = method.lower()

    if "sat" in low:
        return "SAT_AWARE"
    if "mixed" in low:
        return "MIXED_MODE"
    if "fl_aware" in low or "fl-aware" in low:
        return "FL_AWARE"
    if "random" in low:
        return "random"
    if "core" in low:
        return "core"

    return method


rows_all = []

for p in sorted(inp_dir.glob("sbfl_exam_*.csv")):
    if should_skip_file(p):
        continue

    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    for r in rows:
        if "dataset" not in r or "method" not in r:
            continue
        if "fail_ratio" not in r or "ochiai_AC" not in r:
            continue

        row = {k: r.get(k, "") for k in fields}
        row["method"] = normalize_method(row["method"])

        rows_all.append(row)


rows_main = [
    r for r in rows_all
    if r["method"] in MAIN_METHODS
]


for out, rows in [
    (out_all, rows_all),
    (out_main, rows_main),
]:
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    pairs = Counter((r["dataset"], r["method"]) for r in rows)

    print("Wrote:", out)
    print("rows:", len(rows))
    print()

    for (dataset, method), n in sorted(pairs.items()):
        print(f"{dataset:20s} {method:15s} mutants={n}")

    print()
