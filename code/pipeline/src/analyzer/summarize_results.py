import csv
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path
from scipy.stats import mannwhitneyu

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

RESULTS_DIR = Path(__file__).resolve().parents[2] / "results"

# ── Input files ───────────────────────────────────────────────────────────────

LLM_CSV      = RESULTS_DIR / "multi_config_results.csv"
RANDOM_CSV   = RESULTS_DIR / "random_baseline_metrics.csv"
SUMMARY_OUT  = RESULTS_DIR / "experiment_summary.csv"
COMPARE_OUT  = RESULTS_DIR / "comparison_table.csv"
STATS_OUT    = RESULTS_DIR / "statistical_tests.csv"

# ── Output schema ─────────────────────────────────────────────────────────────

SUMMARY_FIELDS = [
    "dataset", "method", "model_id",
    "rule_coverage", "rules_covered", "rules_total",
    "mutants_killed", "mutants_total", "kill_rate", "status",
]

COMPARE_FIELDS = [
    "dataset", "method", "n_models",
    "avg_rule_coverage", "std_rule_coverage",
    "avg_kill_rate", "std_kill_rate",
    "execution_success_rate",
]

STATS_FIELDS = ["dataset", "metric", "u_statistic", "p_value", "significant"]

SUCCESS_STATUS = {"OK", "success"}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_float(v):
    try:
        return float(v) if v not in ("", None) else None
    except (ValueError, TypeError):
        return None


def _read_csv(path: Path) -> list:
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, fieldnames: list, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# ── Step 1: build unified per-model rows ──────────────────────────────────────

def build_summary_rows() -> list:
    rows = []

    # LLM results
    for r in _read_csv(LLM_CSV):
        rows.append({
            "dataset":        r.get("dataset", "BibTeX2DocBook"),
            "method":         f"LLM_{r.get('config', 'core')}",
            "model_id":       r["model_id"],
            "rule_coverage":  r.get("rule_coverage", ""),
            "rules_covered":  r.get("rules_covered", ""),
            "rules_total":    r.get("rules_total", ""),
            "mutants_killed": r.get("mutants_killed", ""),
            "mutants_total":  r.get("mutants_total", ""),
            "kill_rate":      r.get("kill_rate", ""),
            "status":         r.get("status", ""),
        })

    # Random baseline results
    for r in _read_csv(RANDOM_CSV):
        rows.append({
            "dataset":        r.get("dataset", "BibTeX2DocBook"),
            "method":         "Random",
            "model_id":       r["model_id"],
            "rule_coverage":  r.get("rule_coverage", ""),
            "rules_covered":  "",
            "rules_total":    "",
            "mutants_killed": r.get("mutants_killed", ""),
            "mutants_total":  r.get("mutants_total", ""),
            "kill_rate":      r.get("kill_rate", ""),
            "status":         r.get("status", "OK"),
        })

    return rows


# ── Step 2: aggregate per (dataset, method) ───────────────────────────────────

def build_comparison_rows(summary_rows: list) -> list:

    groups = defaultdict(lambda: {
        "coverages": [], "kill_rates": [],
        "successes": 0,  "total": 0,
    })

    for r in summary_rows:

        key = (r["dataset"], r["method"])
        g = groups[key]

        g["total"] += 1

        if r["status"] in SUCCESS_STATUS:
            g["successes"] += 1

        cov = _safe_float(r["rule_coverage"])
        kil = _safe_float(r["kill_rate"])

        if cov is not None:
            g["coverages"].append(cov)

        if kil is not None:
            g["kill_rates"].append(kil)

    compare_rows = []

    for (dataset, method), g in sorted(groups.items()):

        covs = g["coverages"]
        kils = g["kill_rates"]

        compare_rows.append({
            "dataset": dataset,
            "method": method,
            "n_models": g["total"],
            "avg_rule_coverage": round(st.mean(covs), 4) if covs else "",
            "std_rule_coverage": round(st.stdev(covs), 4) if len(covs) > 1 else 0.0,
            "avg_kill_rate": round(st.mean(kils), 4) if kils else "",
            "std_kill_rate": round(st.stdev(kils), 4) if len(kils) > 1 else 0.0,
            "execution_success_rate": round(g["successes"] / g["total"], 4) if g["total"] > 0 else 0.0,
        })

    return compare_rows


# ── Step 3: Statistical Tests ─────────────────────────────────────────────────

def statistical_tests(summary_rows: list) -> list:
    """
    对每个 dataset 比较 LLM_core vs Random
    Mann-Whitney U test
    H1: LLM_core > Random
    """

    data = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    for r in summary_rows:

        if r["status"] not in SUCCESS_STATUS:
            continue

        ds = r["dataset"]
        method = r["method"]

        cov = _safe_float(r["rule_coverage"])
        kil = _safe_float(r["kill_rate"])

        if cov is not None:
            data[ds][method]["rule_coverage"].append(cov)

        if kil is not None:
            data[ds][method]["kill_rate"].append(kil)

    stats_rows = []

    print(f"\n{'='*72}")
    print(f"{'STATISTICAL SIGNIFICANCE (Mann-Whitney U, LLM_core vs Random)':^72}")
    print(f"{'='*72}")
    print(f"{'Dataset':<18} {'Metric':<15} {'U-Stat':>10} {'P-Value':>10} {'Sig?':>8}")
    print("-" * 72)

    for ds in sorted(data.keys()):

        llm_method = "LLM_core"
        rand_method = "Random"

        if llm_method not in data[ds] or rand_method not in data[ds]:
            continue

        for metric in ["rule_coverage", "kill_rate"]:

            llm_vals = data[ds][llm_method][metric]
            rand_vals = data[ds][rand_method][metric]

            if metric == "kill_rate" and (len(llm_vals) == 0 or len(rand_vals) == 0):
                continue

            if len(llm_vals) == 0 or len(rand_vals) == 0:
                continue

            stat, p = mannwhitneyu(llm_vals, rand_vals, alternative='greater')

            significant = p < 0.05

            row = {
                "dataset": ds,
                "metric": metric,
                "u_statistic": round(stat, 2),
                "p_value": f"{p:.4e}",
                "significant": significant
            }

            stats_rows.append(row)

            sig_str = "*" if significant else "n.s."

            print(f"{ds:<18} {metric:<15} {stat:>10.1f} {p:>10.4f} {sig_str:>8}")

    print("=" * 72)

    _write_csv(STATS_OUT, STATS_FIELDS, stats_rows)

    return stats_rows


# ── Step 4: print comparison table ────────────────────────────────────────────

def print_comparison(compare_rows: list) -> None:

    print(f"\n{'='*72}")
    print("EXPERIMENT COMPARISON TABLE")
    print(f"{'='*72}")
    print(f"{'Dataset':<18} {'Method':<14} {'N':>4} "
          f"{'Avg Cov':>9} {'Std':>7} "
          f"{'Avg Kill':>10} {'Std':>7} {'Exec%':>6}")
    print("-" * 72)

    current_ds = None

    for r in compare_rows:

        if r["dataset"] != current_ds:
            if current_ds is not None:
                print()
            current_ds = r["dataset"]

        avg_cov  = f"{float(r['avg_rule_coverage']):.2%}" if r["avg_rule_coverage"] != "" else "N/A"
        std_cov  = f"{float(r['std_rule_coverage']):.2%}" if r["std_rule_coverage"] != "" else ""
        avg_kill = f"{float(r['avg_kill_rate']):.2%}" if r["avg_kill_rate"] != "" else "N/A"
        std_kill = f"{float(r['std_kill_rate']):.2%}" if r["std_kill_rate"] != "" else ""
        exec_pct = f"{float(r['execution_success_rate']):.0%}"

        print(f"{r['dataset']:<18} {r['method']:<14} {r['n_models']:>4} "
              f"{avg_cov:>9} {std_cov:>7} "
              f"{avg_kill:>10} {std_kill:>7} {exec_pct:>6}")

    print("=" * 72)


# ── Main ──────────────────────────────────────────────────────────────────────

def _models_differ(p1: str, p2: str) -> bool:
    try:
        with open(p1, encoding="utf-8", errors="replace") as f1:
            c1 = f1.read().strip()
        with open(p2, encoding="utf-8", errors="replace") as f2:
            c2 = f2.read().strip()
        return c1 != c2
    except Exception:
        return False


def minimal_test_suite() -> list:
    import re
    OUTPUTS_DIR = RESULTS_DIR / "outputs"
    MINIMAL_OUT = RESULTS_DIR / "minimal_test_suite.csv"
    MINIMAL_FIELDS = ["dataset", "config", "total_models", "min_needed",
                      "efficiency", "first_model_kill_rate", "final_kill_rate"]

    MUTANT_PREFIXES = {
        "BibTeX2DocBook": "BibTeX2DocBook_Mutant",
        "UML2ER":         "SimpleUml2ER_Mutant",
        "CPL2SPL":        "CPL2SPL_Mutant",
        "Ecore2Maude":    "Ecore2Maude_Mutant",
    }

    rows = []
    print(f"\n{'='*68}")
    print("MINIMAL ADEQUATE TEST SUITE")
    print(f"{'='*68}")
    print(f"{'Dataset':<18} {'Config':<12} {'Total':>6} "
          f"{'Min':>5} {'Effic':>7} {'1st Kill':>9} {'Final':>7}")
    print("-" * 68)

    for ds_name, prefix in MUTANT_PREFIXES.items():
        config_base = OUTPUTS_DIR / ds_name
        if not config_base.exists():
            continue
        for config_dir in sorted(config_base.iterdir()):
            if not config_dir.is_dir():
                continue
            config_name = config_dir.name

            model_outputs = sorted([
                p for p in config_dir.glob("output_*.xmi")
                if "Mutant" not in p.name and "trace" not in p.name
            ])
            if not model_outputs:
                continue

            first_idx = re.search(
                r"output_(\d+)\.xmi", model_outputs[0].name)
            if not first_idx:
                continue
            first_idx = first_idx.group(1)

            mutant_names = sorted(set(
                m.group(1)
                for p in config_dir.glob(f"output_{first_idx}_{prefix}*.xmi")
                if "trace" not in p.name
                for m in [re.search(rf"({prefix}\d+)\.xmi", p.name)]
                if m
            ), key=lambda x: int(x.split("Mutant")[1]))

            if not mutant_names:
                continue

            kill_matrix = []
            for op in model_outputs:
                idx = re.search(r"output_(\d+)\.xmi", op.name)
                if not idx:
                    continue
                idx = idx.group(1)
                killed = set()
                for mname in mutant_names:
                    mopath = config_dir / f"output_{idx}_{mname}.xmi"
                    if mopath.is_file() and _models_differ(str(op), str(mopath)):
                        killed.add(mname)
                kill_matrix.append(killed)

            if not kill_matrix:
                continue

            first_kill = len(kill_matrix[0]) / len(mutant_names)
            total      = len(kill_matrix)
            cumulative = set()
            min_needed = total
            for i, killed in enumerate(kill_matrix, 1):
                cumulative |= killed
                if cumulative >= set(mutant_names):
                    min_needed = i
                    break

            final_kill = len(cumulative) / len(mutant_names)
            efficiency = min_needed / total

            print(f"{ds_name:<18} {config_name:<12} {total:>6} "
                  f"{min_needed:>5} {efficiency:>7.0%} "
                  f"{first_kill:>9.1%} {final_kill:>7.1%}")

            rows.append({
                "dataset":               ds_name,
                "config":                config_name,
                "total_models":          total,
                "min_needed":            min_needed,
                "efficiency":            round(efficiency, 4),
                "first_model_kill_rate": round(first_kill, 4),
                "final_kill_rate":       round(final_kill, 4),
            })

    print("=" * 68)
    _write_csv(MINIMAL_OUT, MINIMAL_FIELDS, rows)
    return rows

def main():

    print("Consolidating experiment results…")

    summary_rows = build_summary_rows()

    if not summary_rows:
        print("No result files found. Run an experiment first.")
        return

    _write_csv(SUMMARY_OUT, SUMMARY_FIELDS, summary_rows)
    print(f"  Per-model summary → {SUMMARY_OUT}  ({len(summary_rows)} rows)")

    compare_rows = build_comparison_rows(summary_rows)

    _write_csv(COMPARE_OUT, COMPARE_FIELDS, compare_rows)
    print(f"  Comparison table  → {COMPARE_OUT}  ({len(compare_rows)} rows)")

    print_comparison(compare_rows)

    statistical_tests(summary_rows)
    print(f"  Statistical tests → {STATS_OUT}")
    minimal_test_suite()
    print(f"  Minimal test suite → {RESULTS_DIR}/minimal_test_suite.csv")


if __name__ == "__main__":
    main()

# ── Step 4: Minimal adequate test suite ──────────────────────────────────────

OUTPUTS_DIR = RESULTS_DIR / "outputs"
MINIMAL_OUT = RESULTS_DIR / "minimal_test_suite.csv"
MINIMAL_FIELDS = ["dataset", "config", "total_models", "min_needed",
                  "efficiency", "first_model_kill_rate", "final_kill_rate"]


