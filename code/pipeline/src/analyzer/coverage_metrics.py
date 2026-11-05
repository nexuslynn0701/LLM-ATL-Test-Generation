# src/analyzer/coverage_metrics.py
#
# Coverage aggregation metrics for test suites.
# Computes aggregate_coverage, coverage_variance, and coverage_std
# across a set of test models in a (dataset, config) batch.
#
# These metrics are designed to be called from multi_config_experiment.py
# after all per-model traces have been collected, and written into
# multi_config_results.csv as batch-level summary fields.

import csv
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Set, Tuple, Union


# ── Core computation functions ─────────────────────────────────────────────────

def compute_aggregate_coverage(
    test_rule_sets: List[Set[str]],
    all_rules: Union[Set[str], List[str]],
) -> float:
    """
    Compute aggregate (union) coverage of a test suite over a rule set.

    aggregate_coverage = |union(test_rule_sets)| / |all_rules|

    Parameters
    ----------
    test_rule_sets : list of sets
        Each element is the set of rules fired by one test model.
        Empty sets (failed executions) are allowed and contribute nothing.
    all_rules : set or list
        Complete set of transformation rules for this dataset.

    Returns
    -------
    float in [0.0, 1.0].  Returns 0.0 if all_rules is empty.
    """
    if not all_rules:
        return 0.0
    union_covered: Set[str] = set()
    for rule_set in test_rule_sets:
        union_covered.update(rule_set)
    return len(union_covered) / len(all_rules)


def compute_coverage_variance(
    per_test_coverage: List[float],
) -> Tuple[float, float]:
    """
    Compute sample variance and standard deviation of per-model rule coverage.

    Parameters
    ----------
    per_test_coverage : list of float
        Each element is the rule_coverage (0–1) of one test model.

    Returns
    -------
    (variance, std) as floats.
    Returns (0.0, 0.0) if the list has fewer than 2 elements.
    """
    if len(per_test_coverage) < 2:
        return 0.0, 0.0
    variance = statistics.variance(per_test_coverage)
    std      = statistics.stdev(per_test_coverage)
    return variance, std


def summarize_coverage_metrics(
    test_rule_sets: List[Set[str]],
    per_test_coverage: List[float],
    all_rules: Union[Set[str], List[str]],
) -> Dict[str, float]:
    """
    Compute all four coverage summary metrics for a (dataset, config) batch.

    Parameters
    ----------
    test_rule_sets     : per-model fired-rule sets (only successful executions)
    per_test_coverage  : per-model rule_coverage values (0–1, only successful)
    all_rules          : complete rule list for this dataset

    Returns
    -------
    {
        "avg_coverage":       mean of per_test_coverage (0–1),
        "aggregate_coverage": union coverage over all_rules (0–1),
        "coverage_variance":  sample variance of per_test_coverage,
        "coverage_std":       sample std of per_test_coverage,
    }
    All values are 0.0 when inputs are empty.
    """
    avg_cov   = statistics.mean(per_test_coverage) if per_test_coverage else 0.0
    agg_cov   = compute_aggregate_coverage(test_rule_sets, all_rules)
    var, std  = compute_coverage_variance(per_test_coverage)
    return {
        "avg_coverage":       round(avg_cov, 6),
        "aggregate_coverage": round(agg_cov, 6),
        "coverage_variance":  round(var,     6),
        "coverage_std":       round(std,     6),
    }


# ── CSV reader helper ──────────────────────────────────────────────────────────

def load_experiment_metrics(csv_path: Union[str, Path]) -> Dict[Tuple[str, str], dict]:
    """
    Load multi_config_results.csv and return per-(dataset, config) aggregated metrics.

    Reads all per-model rows and computes/reads aggregate statistics.
    If the CSV already contains aggregate_coverage / coverage_variance /
    coverage_std columns (written by the new pipeline), those values are used
    directly from the first row of each group.  Otherwise they are computed
    on the fly from the per-model rule_coverage column.

    Parameters
    ----------
    csv_path : path to multi_config_results.csv

    Returns
    -------
    dict keyed by (dataset, config) with fields:
        avg_coverage, aggregate_coverage, coverage_variance, coverage_std,
        avg_kill_rate, n_models, n_ok
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return {}

    # Group rows by (dataset, config)
    groups: Dict[Tuple[str, str], List[dict]] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row.get("dataset", ""), row.get("config", ""))
            groups.setdefault(key, []).append(row)

    result: Dict[Tuple[str, str], dict] = {}
    for (ds, cfg), rows in groups.items():
        ok_rows = [r for r in rows if r.get("status", "") == "OK"]

        # Per-model coverage and kill rate
        covs  = []
        kills = []
        for r in ok_rows:
            try:   covs.append(float(r["rule_coverage"]))
            except (KeyError, ValueError): pass
            try:   kills.append(float(r["kill_rate"]))
            except (KeyError, ValueError): pass

        # Aggregate coverage: prefer pre-computed column, else compute from covs
        # (note: computing from per-model coverage is an approximation;
        #  the real aggregate requires rule-set union which needs trace files)
        agg_cov_raw = None
        for r in ok_rows:
            v = r.get("aggregate_coverage", "")
            if v:
                try:
                    agg_cov_raw = float(v)
                    break
                except ValueError:
                    pass

        var_raw = None
        std_raw = None
        for r in ok_rows:
            vv = r.get("coverage_variance", "")
            sv = r.get("coverage_std", "")
            if vv and sv:
                try:
                    var_raw = float(vv)
                    std_raw = float(sv)
                    break
                except ValueError:
                    pass

        # Fall back to computing from per-model coverage list
        var_computed, std_computed = compute_coverage_variance(covs)

        result[(ds, cfg)] = {
            "avg_coverage":       round(statistics.mean(covs),  6) if covs  else 0.0,
            "aggregate_coverage": agg_cov_raw if agg_cov_raw is not None
                                  else round(statistics.mean(covs), 6) if covs else 0.0,
            "coverage_variance":  var_raw if var_raw is not None else var_computed,
            "coverage_std":       std_raw if std_raw is not None else std_computed,
            "avg_kill_rate":      round(statistics.mean(kills), 6) if kills else 0.0,
            "n_models":           len(rows),
            "n_ok":               len(ok_rows),
        }
    return result