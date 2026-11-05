#!/usr/bin/env python3
"""End-to-end ATL smoke test: no LLM API, no Eclipse, runs in about a minute.

Chain (all real repo assets, deterministic fixed input):
  1. Compile the actual metric tool code/rq1/model_size_audit/EmfSizeCount.java.
  2. Execute the original BibTeX2DocBook transformation (EMFTVM .asm shipped in
     subjects/) on the fixed scenario input
     subjects/BibTeX2DocBook/scenarios/scenario1/AutomaticModel_BibTex1.xmi
     via the experiment's own runner code/pipeline/lib/ATLRunner.java.
  3. Validate the output model (parses, expected element census) and compute
     the RQ1 model-size metric with EmfSizeCount.
  4. Execute a fixed shipped mutant (data/mutants/BibTeX2DocBook/
     BibTeX2DocBook_Mutant1.asm; recorded as killed by all four methods in
     results/experiment_results/RQ2/mutant_kill_matrix.csv) on the same input.
  5. Compare original vs mutant outputs with the experiment's actual XMI
     oracle (code/pipeline/src/analyzer/coverage_analyzer.compare_xmi_models)
     and classify the mutant KILLED/ALIVE.

Expected values below were recorded from verified runs of this exact chain on
the reference environment (JDK 17, shipped EMF/ATL jars); the input model and
the transformation are fixed, so the chain is deterministic.

Note: the scenario directory also ships a reference output
(DocBook_out1.xmi) that was produced by an earlier revision of the
transformation; the current shipped .asm produces a slightly different
4th-section paragraph content on the same input (49 elements in both cases).
This test therefore pins expectations to the current transformation's own
verified behaviour, not to that stale reference file.

Usage:  python code/reproduction/smoke_test.py
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "code/pipeline/lib"
SUBJECT = ROOT / "subjects/BibTeX2DocBook"
WORKDIR = ROOT / "rebuild/smoke"
SRC_MM = SUBJECT / "BibTeX.ecore"
TGT_MM = SUBJECT / "DocBook.ecore"
TRACE_MM = SUBJECT / "Trace.ecore"
ORIG_ASM = SUBJECT / "transformations/BibTeX2DocBook.asm"
MUTANT_ASM = ROOT / "data/mutants/BibTeX2DocBook/BibTeX2DocBook_Mutant1.asm"
INPUT = SUBJECT / "scenarios/scenario1/AutomaticModel_BibTex1.xmi"
SIZETOOL_SRC = ROOT / "code/rq1/model_size_audit/EmfSizeCount.java"

# Recorded from verified runs of this chain (fixed input, deterministic ATL).
EXPECTED = {
    "element_count": 49,
    "composition": {"DocBook": 1, "books": 1, "articles": 1, "sections_1": 4, "paras": 42},
    "emf_size_count": "OK\t49",
    "mutant_id": "BibTeX2DocBook_Mutant1",
}

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        FAILURES.append(f"{label}: {detail}")


def run(cmd: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True,
                          errors="replace", timeout=timeout)


def atl_runner(asm: Path, out: Path) -> subprocess.CompletedProcess:
    cp = f"{LIB / '*'}{';'}{LIB}"
    return run(["java", "-cp", cp, "ATLRunner",
                str(INPUT), str(SRC_MM), str(TGT_MM), str(TRACE_MM),
                "BibTeX", "DocBook", "TMM", str(asm), str(out)])


def census(path: Path) -> tuple[int, dict[str, int]]:
    root = ET.parse(path).getroot()
    tags: dict[str, int] = {}

    def walk(e) -> None:
        name = e.tag.split("}")[-1]
        tags[name] = tags.get(name, 0) + 1
        for c in e:
            walk(c)

    walk(root)
    return sum(tags.values()), tags


def main() -> int:
    print(f"ATL smoke test — subject BibTeX2DocBook, input {INPUT.name}, "
          f"mutant {EXPECTED['mutant_id']}")
    if WORKDIR.exists():
        for p in sorted(WORKDIR.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    WORKDIR.mkdir(parents=True, exist_ok=True)
    classes = WORKDIR / "classes"
    classes.mkdir()

    # 1. metric tool compiles from the shipped source
    p = run(["javac", "-cp", f"{LIB / '*'}", "-d", str(classes), str(SIZETOOL_SRC)])
    check("compile EmfSizeCount.java", p.returncode == 0, p.stderr.strip()[:200])

    # 2. execute the original transformation
    orig = WORKDIR / "out_orig.xmi"
    p = atl_runner(ORIG_ASM, orig)
    check("run original BibTeX2DocBook.asm", p.returncode == 0 and "SUCCESS" in p.stdout,
          (p.stdout + p.stderr).strip()[-300:])
    check("output model written", orig.exists() and orig.stat().st_size > 0)
    check("trace model written", (WORKDIR / "out_orig_trace.xmi").exists())

    # 3. output model structure + RQ1 model-size metric
    count, tags = census(orig)
    check("output element census matches recorded run",
          count == EXPECTED["element_count"] and tags == EXPECTED["composition"],
          f"got {count} {tags}, expected {EXPECTED['element_count']} {EXPECTED['composition']}")
    p = run(["java", "-cp", f"{classes}{';'}{LIB / '*'}", "EmfSizeCount",
             str(TGT_MM), str(orig)])
    line = next((ln for ln in p.stdout.splitlines()
                 if ln.split("\t")[0] == str(orig)), "")
    got = line.split("\t", 1)[1] if "\t" in line else "(no output)"
    check("EmfSizeCount metric on output", got == EXPECTED["emf_size_count"],
          f"got {got!r}, expected {EXPECTED['emf_size_count']!r}")

    # 4. execute the fixed mutant on the same input
    mut = WORKDIR / "out_mut1.xmi"
    p = atl_runner(MUTANT_ASM, mut)
    check(f"run mutant {EXPECTED['mutant_id']}.asm",
          p.returncode == 0 and "SUCCESS" in p.stdout, (p.stdout + p.stderr).strip()[-300:])

    # 5. XMI-difference oracle (the experiment's actual kill oracle)
    sys.path.insert(0, str(ROOT / "code/pipeline/src"))
    try:
        from analyzer.coverage_analyzer import compare_xmi_models
        check("oracle self-check (original vs itself is ALIVE)",
              compare_xmi_models(str(orig), str(orig)) is True)
        killed = compare_xmi_models(str(orig), str(mut)) is False
        check("mutant classified KILLED (outputs differ)", killed,
              "mutant output equals original output (would be ALIVE)")
    finally:
        sys.path.pop(0)

    # 6. full-chain localization demo: original + all 40 mutant executions,
    #    trace-based rule spectra, and the 18-formula SBFL scores, via the
    #    pipeline entry point in replay mode (no LLM API involved)
    loc_dir = ROOT / "rebuild/smoke_loc"
    if loc_dir.exists():
        shutil.rmtree(loc_dir)
    src_root = WORKDIR / "scenario_inputs/BibTeX2DocBook/astmo/gpt"
    src_root.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(INPUT, src_root / "0001.xmi")
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run(
        [sys.executable, "-X", "utf8", str(ROOT / "code/run_pipeline.py"),
         "--mode", "replay", "--run-dir", str(loc_dir),
         "--source-root", str(WORKDIR / "scenario_inputs"),
         "--subjects", "BibTeX2DocBook", "--providers", "gpt",
         "--conditions", "astmo", "--n", "1", "--workers", "4"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=600, env=env)
    check("replay pipeline: 40 mutants executed and localized",
          p.returncode == 0, (p.stdout + p.stderr).strip()[-400:])
    exam_csv = loc_dir / "derived/rq3/mutant_level_exam.csv"
    if exam_csv.exists():
        import csv as _csv
        rows = list(_csv.DictReader(exam_csv.open(encoding="utf-8-sig")))
        check("localization records: 40 mutants x 18 formulas = 720 rows",
              len(rows) == 720, f"got {len(rows)} rows")
        ochiai = next((r for r in rows if r["mutant_id"] == EXPECTED["mutant_id"]
                       and r["formula"] == "ochiai"), None)
        if ochiai is None:
            check("Mutant1 ochiai row present", False)
        else:
            expect_loc = {"n_faulty_rules": "1", "rule_count": "9", "evaluable": "1",
                          "failing_sources": "1", "best_rank": "1", "tie_size": "8.000000",
                          "exam_ac": "0.5"}
            bad = {k: (ochiai[k], v) for k, v in expect_loc.items() if ochiai[k] != v}
            check("Mutant1/ochiai localization anchors "
                  "(rank 1, tie 8/9 rules, EXAM-AC 0.5)", not bad, str(bad))
            cm = list(_csv.DictReader(
                (ROOT / "results/rq2/supplementary/inputs/canonical_mutants.csv").open(encoding="utf-8-sig")))
            fault = next(r["faulty_rule"] for r in cm if r["mutant_id"] == EXPECTED["mutant_id"])
            check("faulty rule mapped to Article_Title_Journal",
                  fault == "Article_Title_Journal", f"got {fault!r}")
    else:
        check("localization records written", False, str(exam_csv))

    print(f"\nSMOKE TEST: {'PASS' if not FAILURES else 'FAIL'}"
          + (f" — {len(FAILURES)} check(s) failed" if FAILURES else " — all checks passed"))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
