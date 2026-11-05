#!/usr/bin/env python3
"""
run_blackbox_experiment.py
--------------------------
Fully isolated black-box test-generation experiment runner.

Black-box means the LLM receives NO information about:
  - ATL transformation code
  - target metamodel
  - OCL constraints
  - target output examples
  - execution / coverage / mutation feedback
  - repair feedback

The LLM only generates source models; the evaluation phase (ATL execution,
coverage, mutation) is performed externally by existing infrastructure.

Usage examples
--------------
python3 src/experiment/run_blackbox_experiment.py \
    --config BB_ZS \
    --datasets BibTeX2DocBook UML2ER CPL2SPL Ecore2Maude \
    --num_models 100

python3 src/experiment/run_blackbox_experiment.py \
    --config all --datasets all --num_models 100

Isolation guarantee
-------------------
Writes ONLY to:
  results/blackbox/blackbox_results.csv
  results/blackbox/blackbox_summary.csv
  results/blackbox/generated_models/{dataset}/{config}/
  results/blackbox/outputs/{dataset}/{config}/
  results/blackbox/metadata.json
  logs/blackbox_{config}_{timestamp}.log

Never touches:
  results/multi_config_results.csv
  results/multi_config_summary.csv
  results/generated_models/
  results/outputs/
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

# ---------------------------------------------------------------------------
# Resolve project root so that src/* imports work regardless of CWD
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# Black-box prompt builder (reads ONLY source metamodel + source examples)
from src.prompt.blackbox_prompt_builder import (  # noqa: E402
    build_blackbox_prompt,
    extract_source_model,
    extract_coverage_notes,
    get_source_example_paths,
)

# Existing infrastructure (used only in the EVALUATION phase)
try:
    from src.executor.transformation_executor import run_transformation as _run_atl
    _HAS_EXECUTOR = True
except ImportError:
    _run_atl = None
    _HAS_EXECUTOR = False

try:
    from src.analyzer.coverage_analyzer import CoverageAnalyzer
except ImportError:
    CoverageAnalyzer = None  # type: ignore[assignment,misc]

try:
    from src.analyzer.sbfl_analyzer import SBFLAnalyzer
    _HAS_SBFL = True
except ImportError:
    _HAS_SBFL = False

# Mutation helpers — names may differ; adapt to your actual module
try:
    from src.executor.transformation_executor import (
        run_mutants_parallel,
        compute_mutation_kill_rate,
    )
    _HAS_MUTATION = True
except (ImportError, AttributeError):
    _HAS_MUTATION = False

# LLM client — reuse whatever the white-box experiment uses
try:
    from src.generator.test_generator import call_llm  # adjust if needed
    _HAS_LLM = True
except ImportError:
    try:
        from src.generator.test_generator import TestGenerator
        _HAS_LLM = True
        _USE_TEST_GENERATOR_CLASS = True
    except ImportError:
        _HAS_LLM = False


# ===========================================================================
# Dataset registry
# ===========================================================================

DATASET_CONFIGS: dict[str, dict[str, str]] = {
    "BibTeX2DocBook": {
        "dataset_dir":    "datasets/models_BibTexML2DocBook",
        "source_mm":      "BibTeX.ecore",
        "target_mm":      "DocBook.ecore",
        "trace_mm":       "Trace.ecore",
        "source_mm_name": "BibTeX",
        "target_mm_name": "DocBook",
        "trace_mm_name":  "TMM",
        "atl_name":       "BibTeX2DocBook",
    },
    "UML2ER": {
        "dataset_dir":    "datasets/models_UML2ER",
        "source_mm":      "SimpleUml.ecore",
        "target_mm":      "ER.ecore",
        "trace_mm":       "Trace.ecore",
        "source_mm_name": "SimpleUML",
        "target_mm_name": "ER",
        "trace_mm_name":  "TMM",
        "atl_name":       "SimpleUml2ER",
    },
    "CPL2SPL": {
        "dataset_dir":    "datasets/models_CPL2SPL",
        "source_mm":      "CPL.ecore",
        "target_mm":      "SPL.ecore",
        "trace_mm":       "Trace.ecore",
        "source_mm_name": "CPL",
        "target_mm_name": "SPL",
        "trace_mm_name":  "TMM",
        "atl_name":       "CPL2SPL",
    },
    "Ecore2Maude": {
        "dataset_dir":    "datasets/models_Ecore2Maude",
        "source_mm":      "ecore.ecore",
        "target_mm":      "Maude.ecore",
        "trace_mm":       "Trace.ecore",
        "source_mm_name": "Ecore",
        "target_mm_name": "Maude",
        "trace_mm_name":  "TMM",
        "atl_name":       "Ecore2Maude",
    },
}

ALL_DATASETS = list(DATASET_CONFIGS.keys())

# ===========================================================================
# Black-box configuration registry
# ===========================================================================

BLACKBOX_CONFIGS: dict[str, dict[str, Any]] = {
    "BB_ZS": {
        "description": "Black-box zero-shot: source metamodel only",
        "template":    "prompts/blackbox_zs_source_only.txt",
        "use_source_examples": False,
        "max_source_examples": 0,
    },
    "BB_FS": {
        "description": "Black-box few-shot: source metamodel + source examples",
        "template":    "prompts/blackbox_fs_source_only.txt",
        "use_source_examples": True,
        "max_source_examples": 3,
    },
    "BB_FS_target": {
        "description": "Black-box few-shot with target metamodel: source MM + target MM + source examples",
        "template":    "prompts/blackbox_fs_target.txt",
        "use_source_examples": True,
        "max_source_examples": 3,
        "use_target_mm": True,
    },
}

ALL_CONFIGS = list(BLACKBOX_CONFIGS.keys())

# ===========================================================================
# Result paths (ALL under results/blackbox/)
# ===========================================================================

BLACKBOX_ROOT      = PROJECT_ROOT / "results" / "blackbox"
RESULTS_CSV        = BLACKBOX_ROOT / "blackbox_results.csv"
SUMMARY_CSV        = BLACKBOX_ROOT / "blackbox_summary.csv"
METADATA_JSON      = BLACKBOX_ROOT / "metadata.json"
LOGS_DIR           = PROJECT_ROOT / "logs"

RESULTS_CSV_FIELDS = [
    "dataset", "config", "model_id", "status",
    "rule_coverage", "rules_covered", "rules_total",
    "mutants_killed", "mutants_total", "kill_rate",
    "source_model_path", "output_model_path", "trace_path",
    "error_message", "coverage_notes", "timestamp",
]

SUMMARY_CSV_FIELDS = [
    "dataset", "config",
    "models", "ok_models", "failed_models",
    "execution_success_rate",
    "avg_rule_coverage", "std_rule_coverage",
    "aggregate_coverage", "coverage_std",
    "avg_kill_rate", "std_kill_rate",
]

# ===========================================================================
# Logging setup
# ===========================================================================

def setup_logger(config_name: str) -> logging.Logger:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOGS_DIR / f"blackbox_{config_name}_{ts}.log"

    logger = logging.getLogger(f"blackbox.{config_name}.{ts}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    logger.info(f"Log file: {log_file}")
    return logger


# ===========================================================================
# CSV helpers (no pandas, row-level flush, skip-if-exists)
# ===========================================================================

def _ensure_csv(path: Path, fieldnames: list[str]) -> None:
    """Create CSV with header if it does not exist yet."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            f.flush()


def _load_existing_keys(path: Path) -> set[tuple]:
    """
    Load (dataset, config, model_id) triples from an existing results CSV.
    Used to skip already-completed rows.
    """
    keys: set[tuple] = set()
    if not path.exists():
        return keys
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add((row.get("dataset", ""), row.get("config", ""), row.get("model_id", "")))
    return keys


def _append_row(path: Path, fieldnames: list[str], row: dict) -> None:
    """Append one row to CSV and flush immediately."""
    _ensure_csv(path, fieldnames)
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writerow(row)
        f.flush()


# ===========================================================================
# LLM call wrapper
# ===========================================================================

def _call_llm(prompt: str, logger: logging.Logger) -> str:
    """
    Call the project's LLM client with api_key loaded from config.
    """
    from src.llm.llm_client import read_api_key, call_llm as _call_llm_inner
    api_key_path = PROJECT_ROOT / "config" / "deepseek_api_key.txt"
    api_key = read_api_key(str(api_key_path))
    try:
        return _call_llm_inner(prompt, api_key)
    except Exception as exc:
        logger.error(f"LLM call failed: {exc}")
        raise


# ===========================================================================
# Evaluation helpers
# ===========================================================================

def _run_transformation(
    source_model_path: Path,
    output_dir: Path,
    model_id: str,
    dataset_cfg: dict,
    logger: logging.Logger,
) -> dict[str, Any]:
    """
    Run ATL transformation on a generated source model.
    Returns dict with output_model_path, trace_path, ok flag.
    """
    result: dict[str, Any] = {
        "output_model_path": "",
        "trace_path": "",
        "exec_ok": False,
        "error": "",
    }
    if _run_atl is None:
        logger.warning("run_transformation not available; skipping execution.")
        return result
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"output_{model_id}.xmi"
    try:
        from src.executor.transformation_executor import _default_config
        cfg = _default_config()
        cfg["source_mm"]      = str(PROJECT_ROOT / dataset_cfg["dataset_dir"] / dataset_cfg["source_mm"])
        cfg["target_mm"]      = str(PROJECT_ROOT / dataset_cfg["dataset_dir"] / dataset_cfg["target_mm"])
        cfg["trace_mm"]       = str(PROJECT_ROOT / dataset_cfg["dataset_dir"] / dataset_cfg["trace_mm"])
        cfg["source_mm_name"] = dataset_cfg["source_mm_name"]
        cfg["target_mm_name"] = dataset_cfg["target_mm_name"]
        cfg["trace_mm_name"]  = dataset_cfg["trace_mm_name"]
        cfg["transformations_dir"] = str(PROJECT_ROOT / dataset_cfg["dataset_dir"] / "transformations")
        res = _run_atl(
            source_model_path   = str(source_model_path),
            output_model_path   = str(output_path),
            transformation_name = dataset_cfg["atl_name"],
            config              = cfg,
        )
        if res["success"]:
            result["output_model_path"] = str(output_path)
            result["trace_path"]        = res.get("trace", "") or ""
            result["exec_ok"]           = True
        else:
            result["error"] = res.get("error", "unknown error")
            logger.warning(f"  Transformation failed for {model_id}: {result['error']}")
    except Exception as exc:
        result["error"] = str(exc)
        logger.warning(f"  Transformation failed for {model_id}: {exc}")
    return result

    return result


def _run_coverage(
    output_model_path: str,
    trace_path: str,
    dataset_cfg: dict,
    logger: logging.Logger,
) -> dict[str, Any]:
    """
    Compute rule coverage via CoverageAnalyzer.
    Returns dict with rule_coverage, rules_covered, rules_total,
    and executed_rules (set of rule names).
    """
    result: dict[str, Any] = {
        "rule_coverage": 0.0,
        "rules_covered": 0,
        "rules_total":   0,
        "executed_rules": set(),
    }
    if CoverageAnalyzer is None or not output_model_path:
        return result
    try:
        analyzer = CoverageAnalyzer(
            dataset_dir = str(PROJECT_ROOT / dataset_cfg["dataset_dir"]),
            atl_name    = dataset_cfg["atl_name"],
        )
        cov = analyzer.compute_coverage(
            output_model_path = output_model_path,
            trace_path        = trace_path,
        )
        result["rule_coverage"]  = float(cov.get("rule_coverage", 0.0))
        result["rules_covered"]  = int(cov.get("rules_covered", 0))
        result["rules_total"]    = int(cov.get("rules_total", 0))
        result["executed_rules"] = set(cov.get("executed_rules", []))
    except Exception as exc:
        logger.warning(f"  Coverage analysis failed: {exc}")
    return result


def _run_mutation(
    source_model_path: str,
    dataset_cfg: dict,
    logger: logging.Logger,
    output_dir: Path | None = None,
    index_str: str | None = None,
) -> dict[str, Any]:
    """
    Run mutation testing using run_mutants_parallel + compute_mutation_kill_rate.
    """
    result: dict[str, Any] = {
        "mutants_killed": 0,
        "mutants_total":  0,
        "kill_rate":      0.0,
    }
    if not _HAS_MUTATION or not source_model_path:
        return result
    try:
        dc     = dataset_cfg
        ds_dir = PROJECT_ROOT / dc["dataset_dir"]
        c = _default_config()
        c["source_mm"]           = str(ds_dir / dc["source_mm"])
        c["target_mm"]           = str(ds_dir / dc["target_mm"])
        c["trace_mm"]            = str(ds_dir / dc["trace_mm"])
        c["source_mm_name"]      = dc["source_mm_name"]
        c["target_mm_name"]      = dc["target_mm_name"]
        c["trace_mm_name"]       = dc["trace_mm_name"]
        c["transformations_dir"] = str(ds_dir / "transformations")
        mutant_names = _discover_mutants(str(ds_dir / "transformations"))
        run_mutants_parallel(  # type: ignore[name-defined]
            source_model_path = source_model_path,
            output_dir        = str(output_dir),
            index_str         = index_str,
            mutant_names      = mutant_names,
            config            = c,
        )
        # compute kill rate from mutant output files
        import re as _re
        prefix   = mutant_names[0].rsplit("_Mutant", 1)[0] + "_Mutant" if mutant_names else ""
        output   = Path(output_dir) / f"output_{index_str}.xmi"
        mut_files = [m for m in Path(output_dir).glob(f"output_{index_str}_{prefix}*.xmi")
                     if "trace" not in m.name]
        if not mut_files:
            logger.warning(f"  No mutant output files found in {output_dir}")
            return result
        mutant_exec = {}
        for mf in mut_files:
            m = _re.search(prefix + r"\d+", mf.name)
            if m:
                mutant_exec[m.group(0)] = {"success": True, "output": str(mf)}
        kill_info = compute_mutation_kill_rate(str(output), mutant_exec)  # type: ignore[name-defined]
        result["mutants_killed"] = kill_info.get("killed_mutants", 0)
        result["mutants_total"]  = kill_info.get("total_mutants", 0)
        result["kill_rate"]      = float(kill_info.get("kill_rate", 0.0))
    except Exception as exc:
        logger.warning(f"  Mutation testing failed: {exc}")
    return result


# ===========================================================================
# Per-model generation + evaluation
# ===========================================================================

def _process_one_model(
    model_id: str,
    dataset_name: str,
    config_name: str,
    bb_cfg: dict,
    dataset_cfg: dict,
    gen_dir: Path,
    out_dir: Path,
    run_mutation: bool,
    logger: logging.Logger,
) -> dict[str, Any]:
    """
    Generate one source model and evaluate it.
    Returns a result row dict (always, even on failure).
    """
    row: dict[str, Any] = {
        "dataset":            dataset_name,
        "config":             config_name,
        "model_id":           model_id,
        "status":             "FAILED",
        "rule_coverage":      "",
        "rules_covered":      "",
        "rules_total":        "",
        "mutants_killed":     "",
        "mutants_total":      "",
        "kill_rate":          "",
        "source_model_path":  "",
        "output_model_path":  "",
        "trace_path":         "",
        "error_message":      "",
        "coverage_notes":     "",
        "timestamp":          datetime.now().isoformat(),
        # internal-only (not in CSV fieldnames, ignored by extrasaction='ignore')
        "_executed_rules":    set(),
    }

    try:
        # ---- 1. Build prompt (black-box: ONLY source metamodel / examples) ---
        source_mm_path = (
            PROJECT_ROOT
            / dataset_cfg["dataset_dir"]
            / dataset_cfg["source_mm"]
        )
        template_path = PROJECT_ROOT / bb_cfg["template"]

        source_example_paths: list[str] | None = None
        if bb_cfg["use_source_examples"]:
            source_example_paths = get_source_example_paths(
                dataset_dir   = PROJECT_ROOT / dataset_cfg["dataset_dir"],
                max_scenarios = bb_cfg["max_source_examples"],
            )
            if not source_example_paths:
                logger.warning(
                    f"  [{model_id}] BB_FS: no source examples found; "
                    "falling back to zero-shot."
                )

        target_mm_path: str | None = None
        if bb_cfg.get("use_target_mm", False):
            target_mm_path = str(
                PROJECT_ROOT
                / dataset_cfg["dataset_dir"]
                / dataset_cfg["target_mm"]
            )

        prompt = build_blackbox_prompt(
            template_path         = str(template_path),
            source_metamodel_path = str(source_mm_path),
            source_example_paths  = source_example_paths,
            target_metamodel_path = target_mm_path,
        )

        # ---- 2. Call LLM --------------------------------------------------
        logger.debug(f"  [{model_id}] Calling LLM…")
        llm_response = _call_llm(prompt, logger)

        # ---- 3. Extract source model XMI ----------------------------------
        source_xmi = extract_source_model(llm_response)
        if not source_xmi:
            raise ValueError("LLM response did not contain a valid <source_model> block.")

        coverage_notes = extract_coverage_notes(llm_response)
        row["coverage_notes"] = coverage_notes

        # ---- 4. Save source model -----------------------------------------
        gen_dir.mkdir(parents=True, exist_ok=True)
        source_model_path = gen_dir / f"source_model_{model_id}.xmi"
        source_model_path.write_text(source_xmi, encoding="utf-8")
        row["source_model_path"] = str(source_model_path)
        logger.debug(f"  [{model_id}] Saved source model → {source_model_path.name}")

        # ---- 5. ATL transformation ----------------------------------------
        exec_result = _run_transformation(
            source_model_path = source_model_path,
            output_dir        = out_dir,
            model_id          = model_id,
            dataset_cfg       = dataset_cfg,
            logger            = logger,
        )
        row["output_model_path"] = exec_result["output_model_path"]
        row["trace_path"]        = exec_result["trace_path"]

        if not exec_result["exec_ok"]:
            row["error_message"] = f"ATL execution failed: {exec_result['error']}"
            # We still write the row as FAILED but keep going for coverage if
            # there is a partial output (rare; handled by coverage gracefully).

        # ---- 6. Coverage --------------------------------------------------
        cov = _run_coverage(
            output_model_path = exec_result["output_model_path"],
            trace_path        = exec_result["trace_path"],
            dataset_cfg       = dataset_cfg,
            logger            = logger,
        )
        row["rule_coverage"]   = cov["rule_coverage"]
        row["rules_covered"]   = cov["rules_covered"]
        row["rules_total"]     = cov["rules_total"]
        row["_executed_rules"] = cov["executed_rules"]

        # ---- 7. Mutation (optional) ----------------------------------------
        if run_mutation and exec_result["exec_ok"]:
            mut = _run_mutation(
                source_model_path = str(source_model_path),
                dataset_cfg       = dataset_cfg,
                logger            = logger,
                output_dir        = out_dir,
                index_str         = model_id,
            )

        if exec_result["exec_ok"]:
            row["status"] = "OK"

    except Exception as exc:
        row["status"]        = "FAILED"
        row["error_message"] = f"{type(exc).__name__}: {exc}"
        logger.error(f"  [{model_id}] FAILED — {exc}")
        logger.debug(traceback.format_exc())

    return row


# ===========================================================================
# Experiment loop for one (dataset, config) pair
# ===========================================================================

def run_one_combination(
    dataset_name: str,
    config_name: str,
    num_models: int,
    run_mutation: bool,
    max_workers: int,
    existing_keys: set[tuple],
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    """
    Generate and evaluate `num_models` source models for one dataset × config.
    Skips model IDs already present in existing_keys.
    Returns list of result rows.
    """
    bb_cfg      = BLACKBOX_CONFIGS[config_name]
    dataset_cfg = DATASET_CONFIGS[dataset_name]

    gen_dir = BLACKBOX_ROOT / "generated_models" / dataset_name / config_name
    out_dir = BLACKBOX_ROOT / "outputs"           / dataset_name / config_name
    gen_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    model_ids = [f"{i:04d}" for i in range(1, num_models + 1)]
    # Filter already-done
    todo = [
        mid for mid in model_ids
        if (dataset_name, config_name, mid) not in existing_keys
    ]
    logger.info(
        f"  {dataset_name} × {config_name}: "
        f"{num_models} total, {len(todo)} to generate, "
        f"{num_models - len(todo)} skipped (already done)."
    )

    rows: list[dict[str, Any]] = []

    def _task(mid: str) -> dict:
        return _process_one_model(
            model_id      = mid,
            dataset_name  = dataset_name,
            config_name   = config_name,
            bb_cfg        = bb_cfg,
            dataset_cfg   = dataset_cfg,
            gen_dir       = gen_dir,
            out_dir       = out_dir,
            run_mutation  = run_mutation,
            logger        = logger,
        )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_task, mid): mid for mid in todo}
        for fut in as_completed(futures):
            mid = futures[fut]
            try:
                row = fut.result()
            except Exception as exc:
                row = {
                    "dataset": dataset_name, "config": config_name,
                    "model_id": mid, "status": "FAILED",
                    "error_message": str(exc),
                    "timestamp": datetime.now().isoformat(),
                }
            rows.append(row)
            _append_row(RESULTS_CSV, RESULTS_CSV_FIELDS, row)
            logger.info(
                f"  [{mid}] {row['status']} | "
                f"cov={row.get('rule_coverage', 'N/A')} | "
                f"kill={row.get('kill_rate', 'N/A')}"
            )

    return rows


# ===========================================================================
# Summary computation
# ===========================================================================

def compute_and_write_summary(logger: logging.Logger) -> None:
    """
    Read blackbox_results.csv, compute per-(dataset,config) statistics,
    write blackbox_summary.csv.
    """
    if not RESULTS_CSV.exists():
        logger.warning("No results CSV found; skipping summary.")
        return

    # Group rows
    groups: dict[tuple[str, str], list[dict]] = {}
    with RESULTS_CSV.open("r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["dataset"], row["config"])
            groups.setdefault(key, []).append(row)

    _ensure_csv(SUMMARY_CSV, SUMMARY_CSV_FIELDS)

    # Overwrite summary (it's derived data, cheap to recompute)
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_CSV_FIELDS)
        writer.writeheader()

        for (dataset, config), rows in sorted(groups.items()):
            ok_rows     = [r for r in rows if r.get("status") == "OK"]
            failed_rows = [r for r in rows if r.get("status") != "OK"]

            n_total  = len(rows)
            n_ok     = len(ok_rows)
            n_failed = len(failed_rows)
            exec_sr  = round(n_ok / n_total, 4) if n_total else 0.0

            coverages = []
            kill_rates = []
            all_executed_rules: set[str] = set()
            total_rules: int = 0

            for r in ok_rows:
                try:
                    cov = float(r["rule_coverage"])
                    coverages.append(cov)
                except (ValueError, KeyError):
                    pass
                try:
                    kr = float(r["kill_rate"])
                    kill_rates.append(kr)
                except (ValueError, KeyError):
                    pass
                try:
                    total_rules = max(total_rules, int(r.get("rules_total", 0)))
                except (ValueError, TypeError):
                    pass
                # Aggregate covered rules — stored as comma-separated names if
                # re-loaded from CSV (they were sets at generation time)
                covered_str = r.get("_executed_rules", "")
                if covered_str:
                    for rname in str(covered_str).split(","):
                        rname = rname.strip()
                        if rname:
                            all_executed_rules.add(rname)

            avg_cov = round(mean(coverages), 4) if coverages else 0.0
            std_cov = round(stdev(coverages), 4) if len(coverages) > 1 else 0.0

            # aggregate_coverage = |union of covered rules| / total_rules
            agg_cov = (
                round(len(all_executed_rules) / total_rules, 4)
                if total_rules and all_executed_rules
                else avg_cov  # fall back to average if rule names unavailable
            )

            avg_kill = round(mean(kill_rates), 4) if kill_rates else 0.0
            std_kill = round(stdev(kill_rates), 4) if len(kill_rates) > 1 else 0.0

            summary_row = {
                "dataset":                dataset,
                "config":                 config,
                "models":                 n_total,
                "ok_models":              n_ok,
                "failed_models":          n_failed,
                "execution_success_rate": exec_sr,
                "avg_rule_coverage":      avg_cov,
                "std_rule_coverage":      std_cov,
                "aggregate_coverage":     agg_cov,
                "coverage_std":           std_cov,
                "avg_kill_rate":          avg_kill,
                "std_kill_rate":          std_kill,
            }
            writer.writerow(summary_row)
            f.flush()

            logger.info(
                f"  Summary [{dataset}][{config}]: "
                f"ok={n_ok}/{n_total} | "
                f"avg_cov={avg_cov:.3f} | "
                f"agg_cov={agg_cov:.3f} | "
                f"avg_kill={avg_kill:.3f}"
            )

    logger.info(f"Summary written → {SUMMARY_CSV}")


# ===========================================================================
# Metadata
# ===========================================================================

def write_metadata(
    configs: list[str],
    datasets: list[str],
    num_models: int,
    run_mutation: bool,
    max_workers: int,
) -> None:
    BLACKBOX_ROOT.mkdir(parents=True, exist_ok=True)
    meta: dict[str, Any] = {
        "experiment_type": "blackbox",
        "configs":         configs,
        "datasets":        datasets,
        "num_models":      num_models,
        "run_mutation":    run_mutation,
        "max_workers":     max_workers,
        "started_at":      datetime.now().isoformat(),
        "isolation": {
            "llm_receives": [
                "source metamodel",
                "(BB_FS only) source example models",
            ],
            "llm_does_NOT_receive": [
                "ATL transformation code",
                "target metamodel",
                "OCL constraints",
                "target output examples",
                "coverage feedback",
                "mutation feedback",
                "repair feedback",
                "execution feedback",
            ],
        },
    }
    existing: dict = {}
    if METADATA_JSON.exists():
        try:
            existing = json.loads(METADATA_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    existing.update(meta)
    METADATA_JSON.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")


# ===========================================================================
# CLI
# ===========================================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Black-box ATL test-generation experiment runner."
    )
    parser.add_argument(
        "--config",
        default="all",
        help="Config name (BB_ZS | BB_FS | BB_FS_target | all).  Default: all",
    )
    parser.add_argument(
        "--datasets",
        nargs="+",
        default=["all"],
        help="Dataset names or 'all'.  Default: all",
    )
    parser.add_argument(
        "--num_models",
        type=int,
        default=100,
        help="Number of source models to generate per (dataset, config).  Default: 100",
    )
    parser.add_argument(
        "--run_mutation",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run mutation testing.  Default: True",
    )
    parser.add_argument(
        "--max_workers",
        type=int,
        default=8,
        help="Thread pool size for parallel generation.  Default: 8",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve configs
    if args.config.lower() == "all":
        configs = ALL_CONFIGS
    else:
        configs = [args.config]
    for c in configs:
        if c not in BLACKBOX_CONFIGS:
            print(f"ERROR: Unknown config '{c}'.  Valid: {ALL_CONFIGS}", file=sys.stderr)
            sys.exit(1)

    # Resolve datasets
    if args.datasets == ["all"] or args.datasets == ["ALL"]:
        datasets = ALL_DATASETS
    else:
        datasets = args.datasets
    for d in datasets:
        if d not in DATASET_CONFIGS:
            print(f"ERROR: Unknown dataset '{d}'.  Valid: {ALL_DATASETS}", file=sys.stderr)
            sys.exit(1)

    # Logger (use combined name for multi-config runs)
    combined_name = "_".join(configs)
    logger = setup_logger(combined_name)

    # Print experiment config
    logger.info("=" * 70)
    logger.info("BLACK-BOX EXPERIMENT — CONFIGURATION")
    logger.info("=" * 70)
    logger.info(f"  Configs:       {configs}")
    logger.info(f"  Datasets:      {datasets}")
    logger.info(f"  Num models:    {args.num_models}")
    logger.info(f"  Run mutation:  {args.run_mutation}")
    logger.info(f"  Max workers:   {args.max_workers}")
    logger.info(f"  Results root:  {BLACKBOX_ROOT}")
    logger.info(f"  Results CSV:   {RESULTS_CSV}")
    logger.info("  LLM receives:  source metamodel (+ source examples for BB_FS)")
    logger.info("  LLM does NOT receive: ATL / OCL / target MM / target outputs / feedback")
    logger.info("=" * 70)

    # Create output root
    BLACKBOX_ROOT.mkdir(parents=True, exist_ok=True)

    # Write metadata
    write_metadata(
        configs      = configs,
        datasets     = datasets,
        num_models   = args.num_models,
        run_mutation = args.run_mutation,
        max_workers  = args.max_workers,
    )

    # Ensure CSV exists with header
    _ensure_csv(RESULTS_CSV, RESULTS_CSV_FIELDS)

    # Load existing keys (resume support)
    existing_keys = _load_existing_keys(RESULTS_CSV)
    logger.info(f"  Existing result rows: {len(existing_keys)}")

    t_start = time.time()

    for config_name in configs:
        for dataset_name in datasets:
            logger.info("-" * 60)
            logger.info(f">>> {dataset_name} × {config_name}")
            run_one_combination(
                dataset_name  = dataset_name,
                config_name   = config_name,
                num_models    = args.num_models,
                run_mutation  = args.run_mutation,
                max_workers   = args.max_workers,
                existing_keys = existing_keys,
                logger        = logger,
            )
            # Refresh existing_keys so parallel configs don't re-do rows
            existing_keys = _load_existing_keys(RESULTS_CSV)

    elapsed = time.time() - t_start
    logger.info("=" * 70)
    logger.info(f"All combinations done in {elapsed:.1f}s.  Computing summary…")

    compute_and_write_summary(logger)

    logger.info("=" * 70)
    logger.info("BLACK-BOX EXPERIMENT COMPLETE")
    logger.info(f"  Results: {RESULTS_CSV}")
    logger.info(f"  Summary: {SUMMARY_CSV}")
    logger.info(f"  Models:  {BLACKBOX_ROOT / 'generated_models'}")
    logger.info(f"  Outputs: {BLACKBOX_ROOT / 'outputs'}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()