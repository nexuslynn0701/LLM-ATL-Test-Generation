#!/usr/bin/env python3
"""
run_all.py
==========
Master runner for the TOSEM equivalent-mutant supplementary analysis.

Pipeline
~~~~~~~~
  Step 1  01_mutant_coverage.py          – rule-coverage classification
  Step 2  02_mutant_type_breakdown.py    – per-operator kill/survive rates
  Step 3  03_suspected_equivalents.py    – union-pool labeling + sensitivity

Each step is run as a subprocess so its own argparse + error handling applies.

Usage
~~~~~
  # Run everything with defaults
  python run_all.py

  # Override base directory
  python run_all.py --base /path/to/llm_mt_experiment

  # Run only specific steps
  python run_all.py --steps 1 3

  # Only specific datasets
  python run_all.py --datasets BibTeX2DocBook CPL2SPL
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent

STEPS = {
    1: ("01_mutant_coverage.py",       "Mutant Reachability / Rule Coverage"),
    2: ("02_mutant_type_breakdown.py", "Mutation Operator Breakdown"),
    3: ("03_suspected_equivalents.py", "Suspected-Equivalent Labeling"),
}


def run_step(step_num: int, script: str, extra_args: list[str]) -> bool:
    path = SCRIPT_DIR / script
    cmd  = [sys.executable, str(path)] + extra_args

    print(f"\n{'='*72}")
    print(f"  STEP {step_num}: {STEPS[step_num][1]}")
    print(f"  Command: {' '.join(cmd)}")
    print(f"{'='*72}")

    t0  = time.time()
    ret = subprocess.run(cmd)
    elapsed = time.time() - t0

    if ret.returncode != 0:
        print(f"\n  [ERROR] Step {step_num} failed (exit {ret.returncode}) after {elapsed:.1f}s")
        return False

    print(f"\n  [OK] Step {step_num} completed in {elapsed:.1f}s")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run full TOSEM equivalent-mutant analysis pipeline"
    )
    parser.add_argument(
        "--base",
        default=str(Path.home() / "research" / "llm_mt_experiment"),
        help="Project root directory",
    )
    parser.add_argument(
        "--datasets", nargs="+",
        default=["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
        help="Datasets to analyse",
    )
    parser.add_argument(
        "--steps", nargs="+", type=int,
        default=[1, 2, 3],
        choices=[1, 2, 3],
        help="Which steps to run (default: all)",
    )
    parser.add_argument(
        "--stop-on-error", action="store_true",
        help="Abort pipeline on first step failure",
    )
    args = parser.parse_args()

    extra = ["--base", args.base, "--datasets"] + args.datasets

    print("\n" + "="*72)
    print("  TOSEM Equivalent Mutant Analysis Pipeline")
    print("="*72)
    print(f"  Base:     {args.base}")
    print(f"  Datasets: {', '.join(args.datasets)}")
    print(f"  Steps:    {args.steps}")

    results = {}
    for step in sorted(args.steps):
        script, _ = STEPS[step]
        step_args = extra
        ok = run_step(step, script, step_args)
        results[step] = ok
        if not ok and args.stop_on_error:
            print(f"\n  Aborting pipeline (--stop-on-error set).")
            break

    print("\n" + "="*72)
    print("  PIPELINE SUMMARY")
    print("="*72)
    for step, ok in results.items():
        mark = "✓" if ok else "✗"
        print(f"  [{mark}] Step {step}: {STEPS[step][1]}")

    failed = [s for s, ok in results.items() if not ok]
    if failed:
        print(f"\n  {len(failed)} step(s) failed: {failed}")
        print("  Check output above for details.")
        sys.exit(1)
    else:
        out = Path(args.base) / "results_v2" / "analysis"
        print(f"\n  All steps completed successfully.")
        print(f"  Outputs in: {out}")
        print(f"\n  Key files:")
        print(f"    coverage/coverage_overall.csv")
        print(f"    mutation_types/operator_breakdown_overall.csv")
        print(f"    suspected_equiv/suspected_equiv_summary.csv")
        print(f"    suspected_equiv/sensitivity_analysis.json")


if __name__ == "__main__":
    main()