# src/experiment/multi_config_experiment.py

import csv
import json
import logging
import os
import shutil
import statistics
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.prompt.prompt_builder            import get_metamodel_paths, get_example_paths
from src.llm.llm_client import read_api_key
from src.generator.test_generator         import generate_tests
from src.executor.transformation_executor import (
    run_transformation, run_mutants_parallel,
    _discover_mutants, _default_config,
)
from src.analyzer.coverage_analyzer       import (
    compute_rule_coverage, compute_mutation_kill_rate,
)
from src.analyzer.metrics_collector       import print_summary, collect_metrics
# NEW: aggregate coverage metrics
from src.analyzer.coverage_metrics        import summarize_coverage_metrics

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).resolve().parents[2]
_results_override = os.environ.get("LLM_RESULTS_DIR")
RESULTS_DIR = Path(_results_override) if _results_override else ROOT / "results"

API_KEY_PATH  = ROOT / "config" / "deepseek_api_key.txt"
LLM_PROVIDER  = "deepseek"
TEMPLATE_BASE = ROOT / "prompts"

CSV_PATH         = RESULTS_DIR / "multi_config_results.csv"
SUMMARY_CSV_PATH = RESULTS_DIR / "multi_config_summary.csv"
METADATA_PATH    = RESULTS_DIR / "experiment_config.json"

# ── [dataset registry] ────────────────────────────────────────────────────────

DATASETS = {
    "BibTeX2DocBook": {
        "name":            "BibTeX2DocBook",
        "dataset_dir":     ROOT / "datasets" / "models_BibTexML2DocBook",
        "source_mm":       "BibTeX.ecore",
        "target_mm":       "DocBook.ecore",
        "trace_mm":        "Trace.ecore",
        "source_mm_name":  "BibTeX",
        "target_mm_name":  "DocBook",
        "trace_mm_name":   "TMM",
        "atl_name":        "BibTeX2DocBook",
        "mm_config":       "core",
    },
    "UML2ER": {
        "name":            "UML2ER",
        "dataset_dir":     ROOT / "datasets" / "models_UML2ER",
        "source_mm":       "SimpleUml.ecore",
        "target_mm":       "ER.ecore",
        "trace_mm":        "Trace.ecore",
        "source_mm_name":  "SimpleUML",
        "target_mm_name":  "ER",
        "trace_mm_name":   "TMM",
        "atl_name":        "SimpleUml2ER",
        "mm_config":       "core",
    },
    "CPL2SPL": {
        "name":            "CPL2SPL",
        "dataset_dir":     ROOT / "datasets" / "models_CPL2SPL",
        "source_mm":       "CPL.ecore",
        "target_mm":       "SPL.ecore",
        "trace_mm":        "Trace.ecore",
        "source_mm_name":  "CPL",
        "target_mm_name":  "SPL",
        "trace_mm_name":   "TMM",
        "atl_name":        "CPL2SPL",
        "mm_config":       "core",
    },
    "Ecore2Maude": {
        "name":            "Ecore2Maude",
        "dataset_dir":     ROOT / "datasets" / "models_Ecore2Maude",
        "source_mm":       "ecore.ecore",
        "target_mm":       "Maude.ecore",
        "trace_mm":        "Trace.ecore",
        "source_mm_name":  "Ecore",
        "target_mm_name":  "Maude",
        "trace_mm_name":   "TMM",
        "atl_name":        "Ecore2Maude",
        "mm_config":       "core",
    },
        "Grafcet2PetriNet": {
        "name":            "Grafcet2PetriNet",
        "dataset_dir":     ROOT / "datasets" / "models_Grafcet2PetriNet",
        "source_mm":       "Grafcet.ecore",
        "target_mm":       "PetriNet.ecore",
        "trace_mm":        "Trace.ecore",
        "source_mm_name":  "Grafcet",
        "target_mm_name":  "PetriNet",
        "trace_mm_name":   "TMM",
        "atl_name":        "Grafcet2PetriNet_trace",
        "mm_config":       "core",
    },
    "Ant2Maven": {
        "name":            "Ant2Maven",
        "dataset_dir":     ROOT / "datasets" / "models_Ant2Maven",
        "source_mm":       "Ant.ecore",
        "target_mm":       "MavenMaven.ecore",
        "target_mms": {
            "OUTMaven":    "MavenMaven.ecore",
            "OUTProject":  "MavenProject.ecore",
        },
        "trace_mm":        "Trace.ecore",
        "source_mm_name":  "Ant",
        "target_mm_name":  "MavenMaven",
        "target_mm_names": {
            "OUTMaven":    "MavenMaven",
            "OUTProject":  "MavenProject",
        },
        "trace_mm_name":   "TMM",
        "atl_name":        "Ant2Maven",
        "atl_exec_name":   "Ant2Maven_trace",
        "normalize_source_xmi_ids": True,
        "reject_containment_warning": True,
        "reject_source_xsi_types": ["Echo", "Exec"],
        "mm_config":       "core",
        "smoke_input":     "scenarios/scenario_smoke/buildAnt.xmi",
        "smoke_expected_outputs": {
            "OUTMaven":    "scenarios/scenario_smoke/mavenFile.xmi",
            "OUTProject":  "scenarios/scenario_smoke/projectFile.xmi",
        },
        "example_sources": [
            "scenarios/scenario_minimal/minimal_project.xmi",
            "scenarios/scenario_smoke/buildAnt.xmi",
            "scenarios/scenario_rich/library_build.xmi",
        ],
    },
}

# ── Prompt configuration registry ─────────────────────────────────────────────

PROMPT_CONFIGS = {
    "core": {
        "template":  "generate_test_model.txt",
        "mm_config": "core",
    },
    "full": {
        "template":  "generate_test_model.txt",
        "mm_config": "full",
    },
    "zero_shot": {
        "template":  "generate_test_model_zs.txt",
        "mm_config": "core",
    },
    "few_shot": {
        "template":  "generate_test_model_fs.txt",
        "mm_config": "core",
    },
    "cot": {
        "template":  "generate_test_model_cot.txt",
        "mm_config": "core",
    },
    "core_v2": {
        "template":  "generate_test_model_v2.txt",
        "mm_config": "core",
    },
    "core_v2_with_target": {
        "template":  "generate_test_model_v2_with_target.txt",
        "mm_config": "core",
    },
}

# ── Experiment parameters ──────────────────────────────────────────────────────

N_MODELS      = 5
MAX_SCENARIOS = 3
RUN_MUTATION  = True
BASE_SEED     = 42
MAX_WORKERS   = 8

USE_COVERAGE_GUIDANCE = True
VERIFY_COVERAGE       = True
SKIP_GENERATION       = False  # mutation-only模式：跳过LLM生成，直接用已有模型跑mutation
FL_AWARE_FEEDBACK     = False  # overridden by run_experiment.py per-config
MIXED_MODE_FEEDBACK   = False  # overridden by run_experiment.py per-config
SAT_AWARE_FEEDBACK    = False  # NEW: overridden by run_experiment.py per-config
SOURCE_ONLY_CONTEXT   = False  # overridden by run_experiment.py per-config
NO_OCL                = False  # overridden by run_experiment.py per-config
NO_ATL                = False  # overridden by run_experiment.py per-config
NO_ATL                = False  # overridden by run_experiment.py per-config
BLACKBOX_MODE         = False  # overridden by run_experiment.py per-config

# ── Dataset-aware executor config ─────────────────────────────────────────────

def _dataset_executor_config(ds: dict) -> dict:
    cfg = {
        "java_cp":             str(ROOT / "lib"),
        "source_mm":           str(ds["dataset_dir"] / ds["source_mm"]),
        "target_mm":           str(ds["dataset_dir"] / ds["target_mm"]),
        "trace_mm":            str(ds["dataset_dir"] / ds["trace_mm"]),
        "source_mm_name":      ds["source_mm_name"],
        "target_mm_name":      ds["target_mm_name"],
        "trace_mm_name":       ds["trace_mm_name"],
        "atl_name":            ds["atl_name"],
        "atl_exec_name":       ds.get("atl_exec_name", ds["atl_name"]),
        "normalize_source_xmi_ids": ds.get("normalize_source_xmi_ids", False),
        "reject_containment_warning": True,
        "reject_source_xsi_types": ds.get("reject_source_xsi_types", []),
        "transformations_dir": str(ds["dataset_dir"] / "transformations"),
        "timeout":             300,
        "max_workers":         MAX_WORKERS,
    }

    if "target_mms" in ds:
        cfg["target_mms"] = {
            out_name: str(ds["dataset_dir"] / mm_path)
            for out_name, mm_path in ds["target_mms"].items()
        }
        cfg["target_mm_names"] = ds.get("target_mm_names", {})
        cfg["smoke_input"] = str(ds["dataset_dir"] / ds["smoke_input"])
        cfg["smoke_expected_outputs"] = {
            out_name: str(ds["dataset_dir"] / rel_path)
            for out_name, rel_path in ds.get("smoke_expected_outputs", {}).items()
        }

    return cfg


def _discover_mutants_for_dataset(ds: dict) -> list:
    trans_dir = ds["dataset_dir"] / "transformations"
    atl_stem  = ds["atl_name"]
    names = []
    for f in sorted(trans_dir.iterdir()):
        if (f.suffix == ".asm"
                and "Mutant" in f.name
                and "no_trace" not in f.name
                and f.name.startswith(atl_stem)):
            names.append(f.stem)
    return names


def _get_base_safety_note(dataset_name: str) -> str:
    """
    Subject-specific source XMI serialization format notes.
    Only added when the subject has known serialization conventions
    that LLMs frequently violate. Describes source-side structure only;
    no target output, mutant behavior, or expected faults.
    """
    from src.generator.test_generator import (
        _ANT2MAVEN_SAFETY_NOTE,
        _CPL_SAFETY_NOTE,
        _UML2ER_SAFETY_NOTE,
        _ECORE_SAFETY_NOTE,
        _BIBTEX_SAFETY_NOTE,
    )
    if "Ant2Maven" in dataset_name:
        return _ANT2MAVEN_SAFETY_NOTE
    if "CPL" in dataset_name:
        return _CPL_SAFETY_NOTE
    if "UML" in dataset_name:
        return _UML2ER_SAFETY_NOTE
    if "Ecore" in dataset_name:
        return _ECORE_SAFETY_NOTE
    if "BibTeX" in dataset_name:
        return _BIBTEX_SAFETY_NOTE
    return ""  # 其他 subject 无特殊 source format note


def _get_metamodel_paths_for_dataset(ds: dict) -> list:
    if "target_mms" in ds:
        return [
            str(ds["dataset_dir"] / ds["source_mm"]),
            *[
                str(ds["dataset_dir"] / mm_path)
                for mm_path in ds["target_mms"].values()
            ],
        ]

    return [
        str(ds["dataset_dir"] / ds["source_mm"]),
        str(ds["dataset_dir"] / ds["target_mm"]),
    ]


def _get_metamodel_paths_source_only(ds: dict) -> list:
    """Source metamodel only — no target metamodel."""
    return [
        str(ds["dataset_dir"] / ds["source_mm"])]

def _get_example_paths_source_only(ds: dict) -> list:
    """Example source models only — no target model pairing."""
    if "example_sources" in ds:
        return [str(ds["dataset_dir"] / p) for p in ds["example_sources"]]

    scenarios_dir = ds["dataset_dir"] / "scenarios"
    paths = []
    for i in range(1, MAX_SCENARIOS + 1):
        sdir = scenarios_dir / f"scenario{i}"
        if not sdir.is_dir():
            break
        sources = list(sdir.glob("AutomaticModel_*.xmi"))
        if sources:
            paths.append(str(sources[0]))
    return paths


def _get_example_paths_for_dataset(ds: dict) -> list:
    if "example_sources" in ds:
        return [str(ds["dataset_dir"] / p) for p in ds["example_sources"]]

    scenarios_dir = ds["dataset_dir"] / "scenarios"
    pairs = []
    for i in range(1, MAX_SCENARIOS + 1):
        sdir = scenarios_dir / f"scenario{i}"
        if not sdir.is_dir():
            break
        sources  = list(sdir.glob("AutomaticModel_*.xmi"))
        atl_stem = ds["atl_name"].split("2")[1] if "2" in ds["atl_name"] else ""
        targets  = [f for f in sdir.glob("*_out*.xmi")
                    if "Trace" not in f.name and "Joint" not in f.name]
        if sources:
            src = str(sources[0])
            tgt = str(targets[0]) if targets else None
            pairs.append((src, tgt) if tgt else src)
    return pairs


# ── CSV helpers ────────────────────────────────────────────────────────────────

CSV_FIELDNAMES = [
    "dataset", "config", "model_id",
    "rule_coverage",
    "aggregate_coverage",
    "coverage_variance",
    "coverage_std",
    "rules_covered", "rules_total",
    "mutants_killed", "mutants_total", "kill_rate",
    "oracle_correct", "oracle_similarity",
    "exam_tarantula", "exam_ochiai", "exam_ochiai2", "exam_dstar",
    "status"]

SUMMARY_FIELDNAMES = [
    "dataset", "config", "models",
    "avg_rule_coverage", "std_rule_coverage",
    "aggregate_coverage",
    "coverage_variance",
    "coverage_std",
    "avg_kill_rate", "std_kill_rate", "execution_success_rate"]


def _init_csv(path: Path, fieldnames: list, overwrite: bool = False) -> tuple:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode   = "w" if overwrite else "a"
    is_new = overwrite or not path.exists() or path.stat().st_size == 0
    fh     = open(path, mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
    if is_new:
        writer.writeheader()
        fh.flush()
    return fh, writer


def _write_row(writer, fh, row: dict) -> None:
    writer.writerow(row)
    fh.flush()
    os.fsync(fh.fileno())


def _load_existing_keys(path: Path) -> set:
    keys = set()
    if path.exists() and path.stat().st_size > 0:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    keys.add((
                        row.get("dataset", ""),
                        row.get("config",  ""),
                        row.get("model_id",""),
                    ))
        except Exception as e:
            logger.warning(f"Could not read existing CSV keys: {e}")
    return keys


def _backup_csv(path: Path) -> None:
    if path.exists() and path.stat().st_size > 0:
        ts     = datetime.now().strftime("%Y%m%d_%H%M")
        backup = path.parent / f"{path.stem}_backup_{ts}{path.suffix}"
        shutil.copy2(path, backup)
        logger.info(f"Backed up existing results → {backup}")


# ── Experiment metadata ────────────────────────────────────────────────────────

def _save_experiment_metadata(
    dataset_names: list,
    configs: list,
    mutant_counts: dict,
) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    metadata = {
        "datasets":               dataset_names,
        "configs":                configs,
        "mutant_counts":          mutant_counts,
        "models_per_config":      N_MODELS,
        "base_seed":              BASE_SEED,
        "max_workers":            MAX_WORKERS,
        "use_coverage_guidance":  USE_COVERAGE_GUIDANCE,
        "verify_coverage":        VERIFY_COVERAGE,
        "timestamp":              datetime.now().isoformat(),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Experiment metadata saved → {METADATA_PATH}")


# ── Summary CSV ────────────────────────────────────────────────────────────────

def _save_summary_csv(all_stats: dict) -> None:
    fh, writer = _init_csv(SUMMARY_CSV_PATH, SUMMARY_FIELDNAMES, overwrite=True)
    try:
        for (ds_name, cfg_name), stats in all_stats.items():
            coverages  = stats["coverages"]
            kill_rates = stats["kill_rates"]
            total      = stats["total"]
            successes  = stats["successes"]

            avg_cov   = statistics.mean(coverages)   if coverages           else 0.0
            std_cov   = statistics.stdev(coverages)  if len(coverages)  > 1 else 0.0
            avg_kil   = statistics.mean(kill_rates)  if kill_rates          else 0.0
            std_kil   = statistics.stdev(kill_rates) if len(kill_rates) > 1 else 0.0
            exec_rate = successes / total             if total > 0           else 0.0

            agg_cov  = stats.get("aggregate_coverage", "")
            cov_var  = stats.get("coverage_variance",  "")
            cov_std  = stats.get("coverage_std",       "")

            _write_row(writer, fh, {
                "dataset":                ds_name,
                "config":                 cfg_name,
                "models":                 total,
                "avg_rule_coverage":      round(avg_cov,   4),
                "std_rule_coverage":      round(std_cov,   4),
                "aggregate_coverage":     round(agg_cov,   4) if isinstance(agg_cov, float) else agg_cov,
                "coverage_variance":      round(cov_var,   6) if isinstance(cov_var, float) else cov_var,
                "coverage_std":           round(cov_std,   6) if isinstance(cov_std, float) else cov_std,
                "avg_kill_rate":          round(avg_kil,   4),
                "std_kill_rate":          round(std_kil,   4),
                "execution_success_rate": round(exec_rate, 4),
            })
    finally:
        fh.close()
    logger.info(f"Summary CSV saved → {SUMMARY_CSV_PATH}")


# ── Single dataset × config experiment ────────────────────────────────────────

def run_one(
    dataset_name: str,
    config_name: str,
    config_index: int,
    api_key: str,
    writer,
    fh,
    existing_keys: set = None,
    output_dir_name: str = None,
) -> tuple:
    ds   = DATASETS[dataset_name]
    spec = PROMPT_CONFIGS[config_name]

    if existing_keys is None:
        existing_keys = set()

    seed         = BASE_SEED + config_index
    exec_cfg     = _dataset_executor_config(ds)
    mutant_names = _discover_mutants_for_dataset(ds)
    atl_path     = str(ds["dataset_dir"] / "transformations" / f"{ds['atl_name']}.atl")

    logger.info(f"{'='*60}")
    logger.info(
        f"Dataset: {dataset_name}  Config: {config_name.upper()}  "
        f"seed={seed}  mutants={len(mutant_names)}"
    )
    logger.info(f"{'='*60}")

    _out_name = output_dir_name if output_dir_name else config_name
    gen_dir   = RESULTS_DIR / "generated_models" / dataset_name / _out_name
    trans_dir = RESULTS_DIR / "outputs"           / dataset_name / _out_name
    gen_dir.mkdir(parents=True, exist_ok=True)
    trans_dir.mkdir(parents=True, exist_ok=True)

    template_path = TEMPLATE_BASE / spec["template"]
    if not template_path.is_file():
        logger.warning(f"Template '{spec['template']}' not found, falling back.")
        template_path = TEMPLATE_BASE / "generate_test_model.txt"

    source_only = SOURCE_ONLY_CONTEXT
    metamodel_paths = _get_metamodel_paths_source_only(ds) if source_only else _get_metamodel_paths_for_dataset(ds)
    example_paths   = _get_example_paths_source_only(ds)   if source_only else _get_example_paths_for_dataset(ds)
    no_ocl    = NO_OCL
    ocl_path        = "" if no_ocl else str(ds["dataset_dir"] / "OCL_Constraints.txt")
    no_atl    = NO_ATL
    if no_atl:
        atl_path  = ""
    no_atl    = NO_ATL
    if no_atl:
        atl_path = ""

    # ── mutation-only模式：跳过生成，从已有文件重建generation_results ──────
    if SKIP_GENERATION:
        logger.info(f"[{dataset_name}/{config_name}] SKIP_GENERATION=True, loading existing models...")
        generation_results = []
        for idx in range(1, N_MODELS + 1):
            index_str   = str(idx).zfill(4)
            source_path = str(gen_dir / f"source_model_{index_str}.xmi")
            target_path = str(gen_dir / f"target_model_{index_str}.xmi")
            if os.path.isfile(source_path):
                generation_results.append({
                    "index":        index_str,
                    "source":       source_path,
                    "target":       target_path if os.path.isfile(target_path) else "",
                    "exec_success": None,  # 让后续流程自己跑ATL
                })
        logger.info(f"[{dataset_name}/{config_name}] Found {len(generation_results)} existing models.")
    else:
        # ── Pre-skip：跳过CSV里已有的model，只生成缺失的 ─────────────────
        _csv_config_key = output_dir_name if output_dir_name else config_name
        already_done = set()
        for idx in range(1, N_MODELS + 1):
            index_str = str(idx).zfill(4)
            # existing_keys用不带前导零的字符串存model_id（如'1'不是'0001'）
            row_key_zfill = (dataset_name, _csv_config_key, index_str)
            row_key_plain = (dataset_name, _csv_config_key, str(idx))
            row_key_int   = (dataset_name, _csv_config_key, idx)
            if row_key_zfill in existing_keys or row_key_plain in existing_keys or row_key_int in existing_keys:
                already_done.add(idx)
        n_remaining = N_MODELS - len(already_done)
        if n_remaining == 0:
            logger.info(
                f"[{dataset_name}/{config_name}] All {N_MODELS} models already in CSV, skipping generation.")
            generation_results = []
        else:
            logger.info(
                f"[{dataset_name}/{config_name}] "
                f"{len(already_done)} done, generating {n_remaining} remaining...")

    if not SKIP_GENERATION and 'generation_results' not in dir():
        generation_results = generate_tests(
        template_path         = str(template_path),
        metamodel_paths       = metamodel_paths,
        ocl_path              = ocl_path,
        example_paths         = example_paths,
        atl_path              = atl_path,
        api_key               = api_key,
        safety_note           = _get_base_safety_note(dataset_name),
        output_dir            = str(gen_dir),
        n                     = N_MODELS,
        start_index           = 1,
        use_coverage_guidance = USE_COVERAGE_GUIDANCE,
        verify_coverage       = VERIFY_COVERAGE,
        transform_dir         = str(trans_dir),
        transformation_name   = ds["atl_name"],
        executor_config       = exec_cfg,
        fl_aware_feedback     = FL_AWARE_FEEDBACK,
        mixed_mode_feedback   = MIXED_MODE_FEEDBACK,
        sat_aware_feedback    = SAT_AWARE_FEEDBACK,   # NEW
    )
    if not SKIP_GENERATION:
        logger.info(
            f"[{dataset_name}/{config_name}] Generated {len(generation_results)} pair(s).")

    coverage_results = []
    mutation_results = []
    stats = {"coverages": [], "kill_rates": [], "successes": 0, "total": 0}

    per_model_rule_sets: list = []

    for pair in generation_results:
        index_str   = pair["index"]
        source_path = pair["source"]
        output_path = str(trans_dir / f"output_{index_str}.xmi")
        stats["total"] += 1

        _csv_config = output_dir_name if output_dir_name else config_name
        row_key = (dataset_name, _csv_config, index_str)
        skip_write = row_key in existing_keys

        if VERIFY_COVERAGE and pair.get("exec_success") is not None:
            if not pair["exec_success"]:
                logger.warning(
                    f"[{dataset_name}/{config_name}][{index_str}] FAILED.")
                coverage_results.append(None)
                mutation_results.append(None)
                if not skip_write:
                    _write_row(writer, fh, {
                        "dataset": dataset_name, "config": _csv_config,
                        "model_id": index_str, "rule_coverage": "",
                        "aggregate_coverage": "", "coverage_variance": "",
                        "coverage_std": "",
                        "rules_covered": "", "rules_total": "",
                        "mutants_killed": "", "mutants_total": "",
                        "kill_rate": "", "oracle_correct": "",
                        "oracle_similarity": "", "status": "FAILED",
                        "exam_tarantula": "", "exam_ochiai": "",
                        "exam_ochiai2": "", "exam_dstar": "",
                    })
                continue
            stats["successes"] += 1
        else:
            exec_res = run_transformation(
                source_path, output_path,
                ds["atl_name"], exec_cfg)
            if not exec_res["success"]:
                logger.warning(
                    f"[{dataset_name}/{config_name}][{index_str}] FAILED.")
                coverage_results.append(None)
                mutation_results.append(None)
                if not skip_write:
                    _write_row(writer, fh, {
                        "dataset": dataset_name, "config": _csv_config,
                        "model_id": index_str, "rule_coverage": "",
                        "aggregate_coverage": "", "coverage_variance": "",
                        "coverage_std": "",
                        "rules_covered": "", "rules_total": "",
                        "mutants_killed": "", "mutants_total": "",
                        "kill_rate": "", "oracle_correct": "",
                        "oracle_similarity": "", "status": "FAILED",
                        "exam_tarantula": "", "exam_ochiai": "",
                        "exam_ochiai2": "", "exam_dstar": "",
                    })
                continue
            stats["successes"] += 1

        trace_path = output_path.replace(".xmi", "_trace.xmi")
        cov = None
        if os.path.isfile(trace_path):
            from src.analyzer.coverage_analyzer import compute_rule_coverage
            cov = compute_rule_coverage(trace_path, atl_path)
            stats["coverages"].append(cov["rule_coverage"])
            fired_set = set(cov.get("executed_rules", []))
            per_model_rule_sets.append(fired_set)
            logger.info(
                f"[{dataset_name}/{config_name}][{index_str}] "
                f"Coverage: {cov['rule_coverage']:.2%} "
                f"({cov['covered_rules']}/{cov['total_rules']})"
            )
        coverage_results.append(cov)

        mut = None
        if RUN_MUTATION and mutant_names:
            logger.info(
                f"[{dataset_name}/{config_name}][{index_str}] "
                f"Running {len(mutant_names)} mutants…"
            )
            mutant_exec = run_mutants_parallel(
                source_model_path = source_path,
                output_dir        = str(trans_dir),
                index_str         = index_str,
                mutant_names      = mutant_names,
                config            = exec_cfg,
                max_workers       = MAX_WORKERS,
            )
            from src.analyzer.coverage_analyzer import compute_mutation_kill_rate
            mut = compute_mutation_kill_rate(
                _mutation_oracle_original_outputs(output_path, exec_cfg),
                mutant_exec,
            )
            stats["kill_rates"].append(mut["kill_rate"])
            logger.info(
                f"[{dataset_name}/{config_name}][{index_str}] "
                f"Kill rate: {mut['kill_rate']:.2%} "
                f"({mut['killed_mutants']}/{mut['total_mutants']})"
            )
        mutation_results.append(mut)

        sbfl_result = None
        if RUN_MUTATION and mutant_names and os.path.isfile(trace_path):
            try:
                from src.analyzer.sbfl_analyzer import compute_sbfl_for_mutant, BUGGY_RULES
                from src.analyzer.mutant_manifest_loader import load_buggy_rule_metadata
                from src.analyzer.coverage_analyzer import extract_rules_and_helpers
                all_rules_list = extract_rules_and_helpers(atl_path)["rules"]
                try:
                    buggy_rules_map = load_buggy_rule_metadata(
                        Path(atl_path).parent,
                        Path(atl_path).stem,
                        analysis_scope="main",
                    )
                except Exception as _manifest_exc:
                    logger.warning(f"Mutant manifest unavailable, falling back to BUGGY_RULES: {_manifest_exc}")
                    buggy_rules_map = BUGGY_RULES

                exam_values = {"tarantula": [], "ochiai": [], "ochiai2": [], "dstar": []}
                for mname in mutant_names:
                    buggy = buggy_rules_map.get(mname)
                    if not buggy:
                        continue
                    sbfl_original_output = _sbfl_original_output_for_index(trans_dir, index_str, exec_cfg)
                    sbfl_mutant_output = _sbfl_mutant_output_for_index(trans_dir, index_str, mname, exec_cfg)
                    if sbfl_original_output is None or sbfl_mutant_output is None:
                        continue
                    r = compute_sbfl_for_mutant(
                        trace_paths         = [trace_path],
                        output_paths        = [sbfl_original_output],
                        mutant_output_paths = [sbfl_mutant_output],
                        all_rules           = all_rules_list,
                        mutant_name         = mname,
                        buggy_rules         = buggy,
                    )
                    for f in exam_values:
                        exam_values[f].append(r["exam_scores"][f])
                import statistics as _st
                sbfl_result = {
                    f: round(_st.mean(v), 4) if v else ""
                    for f, v in exam_values.items()
                }
                logger.info(
                    f"[{dataset_name}/{config_name}][{index_str}] "
                    f"EXAM ochiai={sbfl_result.get('ochiai', '?')}"
                )
            except Exception as e:
                logger.warning(f"SBFL computation failed: {e}")

        oracle_result = None
        target_path   = pair.get("target", "")
        if target_path and os.path.isfile(target_path) and os.path.isfile(output_path):
            from src.analyzer.oracle_evaluator import evaluate_oracle
            oracle_result = evaluate_oracle(target_path, output_path)
            if oracle_result["error"] is None:
                logger.info(
                    f"[{dataset_name}/{config_name}][{index_str}] "
                    f"Oracle: correct={oracle_result['oracle_correct']} | "
                    f"similarity={oracle_result['similarity']:.2%}"
                )

        if not skip_write:
            _write_row(writer, fh, {
                "dataset":           dataset_name,
                "config":            _csv_config,
                "model_id":          index_str,
                "rule_coverage":     round(cov["rule_coverage"], 4) if cov else "",
                "aggregate_coverage": "",
                "coverage_variance":  "",
                "coverage_std":       "",
                "rules_covered":     cov["covered_rules"]           if cov else "",
                "rules_total":       cov["total_rules"]             if cov else "",
                "mutants_killed":    mut["killed_mutants"]          if mut else "",
                "mutants_total":     mut["total_mutants"]           if mut else "",
                "kill_rate":         round(mut["kill_rate"], 4)     if mut else "",
                "oracle_correct":    oracle_result["oracle_correct"]
                                     if oracle_result and oracle_result["error"] is None
                                     else "",
                "oracle_similarity": round(oracle_result["similarity"], 4)
                                     if oracle_result and oracle_result["error"] is None
                                     else "",
                "exam_tarantula":    sbfl_result.get("tarantula", "") if sbfl_result else "",
                "exam_ochiai":       sbfl_result.get("ochiai",    "") if sbfl_result else "",
                "exam_ochiai2":      sbfl_result.get("ochiai2",   "") if sbfl_result else "",
                "exam_dstar":        sbfl_result.get("dstar",     "") if sbfl_result else "",
                "status":            "OK",
            })
        else:
            logger.info(
                f"[{dataset_name}/{config_name}][{index_str}] "
                f"Skipped write (already exists in CSV)"
            )

    # ── Batch-level aggregate coverage metrics ────────────────────────────────
    try:
        from src.analyzer.coverage_analyzer import extract_rules_and_helpers
        all_rules_list = extract_rules_and_helpers(atl_path)["rules"]
        cov_summary = summarize_coverage_metrics(
            test_rule_sets    = per_model_rule_sets,
            per_test_coverage = stats["coverages"],
            all_rules         = all_rules_list,
        )
        stats["aggregate_coverage"] = cov_summary["aggregate_coverage"]
        stats["coverage_variance"]  = cov_summary["coverage_variance"]
        stats["coverage_std"]       = cov_summary["coverage_std"]
        logger.info(
            f"[{dataset_name}/{config_name}] "
            f"Aggregate coverage: {cov_summary['aggregate_coverage']:.2%} | "
            f"std: {cov_summary['coverage_std']:.4f}"
        )
    except Exception as e:
        logger.warning(f"Aggregate coverage computation failed: {e}")
        stats["aggregate_coverage"] = ""
        stats["coverage_variance"]  = ""
        stats["coverage_std"]       = ""


def _mutation_oracle_original_outputs(output_path: str, exec_config: dict):
    """Return explicit declared output paths for the mutation diff oracle."""
    if not exec_config.get("target_mms"):
        return output_path

    base, ext = os.path.splitext(output_path)
    ext = ext or ".xmi"
    return {
        "outputs": {
            out_name: f"{base}_{out_name}{ext}"
            for out_name in exec_config["target_mms"]
        }
    }


def _sbfl_original_output_for_index(trans_dir: Path, idx_s: str, exec_config: dict):
    if exec_config.get("target_mms"):
        out = {}
        for out_name in exec_config["target_mms"]:
            candidates = [
                trans_dir / f"output_{idx_s}_{out_name}.xmi",
                trans_dir / f"output_{idx_s.zfill(4)}_{out_name}.xmi",
                trans_dir / f"output_{idx_s}_original_{out_name}.xmi",
                trans_dir / f"output_{idx_s.zfill(4)}_original_{out_name}.xmi",
            ]
            p = next((x for x in candidates if x.exists()), None)
            if p is None:
                return None
            out[out_name] = str(p)
        return out

    p = trans_dir / f"output_{idx_s}.xmi"
    if not p.exists():
        p = trans_dir / f"output_{idx_s.zfill(4)}.xmi"
    return str(p) if p.exists() else None


def _sbfl_mutant_output_for_index(trans_dir: Path, idx_s: str, mutant_name: str, exec_config: dict):
    if exec_config.get("target_mms"):
        out = {}
        for out_name in exec_config["target_mms"]:
            p = trans_dir / f"output_{idx_s}_{mutant_name}_{out_name}.xmi"
            if not p.exists():
                p = trans_dir / f"output_{idx_s.zfill(4)}_{mutant_name}_{out_name}.xmi"
            if not p.exists():
                return None
            out[out_name] = str(p)
        return out

    p = trans_dir / f"output_{idx_s}_{mutant_name}.xmi"
    if not p.exists():
        p = trans_dir / f"output_{idx_s.zfill(4)}_{mutant_name}.xmi"
    return str(p) if p.exists() else None


    # ── Global SBFL ───────────────────────────────────────────────────────────
    if RUN_MUTATION and mutant_names:
        try:
            from src.analyzer.sbfl_analyzer import compute_sbfl_for_mutant, BUGGY_RULES, summarize_exam_scores
            from src.analyzer.mutant_manifest_loader import load_buggy_rule_metadata
            from src.analyzer.coverage_analyzer import extract_rules_and_helpers
            all_rules_list = extract_rules_and_helpers(atl_path)["rules"]
            try:
                buggy_rules_map = load_buggy_rule_metadata(
                    Path(atl_path).parent,
                    Path(atl_path).stem,
                    analysis_scope="main",
                )
            except Exception as _manifest_exc:
                logger.warning(f"Mutant manifest unavailable, falling back to BUGGY_RULES: {_manifest_exc}")
                buggy_rules_map = BUGGY_RULES

            all_trace_paths  = []
            all_output_paths = []
            for pair in generation_results:
                idx_s = pair["index"]
                tp    = str(trans_dir / f"output_{idx_s}_trace.xmi")
                op    = _sbfl_original_output_for_index(trans_dir, idx_s, exec_cfg)
                if os.path.isfile(tp) and op is not None:
                    all_trace_paths.append(tp)
                    all_output_paths.append(op)

            if all_trace_paths:
                sbfl_batch_results = []
                for mname in mutant_names:
                    buggy = buggy_rules_map.get(mname)
                    if not buggy:
                        continue
                    aligned_traces  = []
                    aligned_outputs = []
                    aligned_mutants = []
                    for pair in generation_results:
                        idx_s  = pair["index"]
                        tp     = str(trans_dir / f"output_{idx_s}_trace.xmi")
                        op     = _sbfl_original_output_for_index(trans_dir, idx_s, exec_cfg)
                        mopath = _sbfl_mutant_output_for_index(trans_dir, idx_s, mname, exec_cfg)
                        if not os.path.isfile(tp):
                            tp = str(trans_dir / f"output_{idx_s.zfill(4)}_trace.xmi")
                        if os.path.isfile(tp) and op is not None and mopath is not None:
                            aligned_traces.append(tp)
                            aligned_outputs.append(op)
                            aligned_mutants.append(mopath)
                    if not aligned_traces:
                        continue
                    r = compute_sbfl_for_mutant(
                        trace_paths         = aligned_traces,
                        output_paths        = aligned_outputs,
                        mutant_output_paths = aligned_mutants,
                        all_rules           = all_rules_list,
                        mutant_name         = mname,
                        buggy_rules         = buggy,
                    )
                    sbfl_batch_results.append(r)

                if sbfl_batch_results:
                    summary = summarize_exam_scores(sbfl_batch_results)
                    logger.info(
                        f"[{dataset_name}/{config_name}] Global SBFL "
                        f"({len(all_trace_paths)} models, "
                        f"{len(sbfl_batch_results)} mutants):"
                    )
                    for formula, s in summary.items():
                        logger.info(
                            f"  {formula:<12}: avg EXAM = {s['mean']:.4f} "
                            f"(std={s['std']:.4f})"
                        )
                    stats["sbfl_exam"] = {
                        f: s["mean"] for f, s in summary.items()
                    }
        except Exception as e:
            logger.warning(f"Global SBFL failed: {e}")

    metrics = collect_metrics(
        generation_results = generation_results,
        coverage_results   = coverage_results,
        mutation_results   = mutation_results,
        config             = {
            "dataset":       dataset_name,
            "config_name":   config_name,
            "n_models":      N_MODELS,
            "seed":          seed,
        },
    )
    print_summary(metrics)
    return metrics, stats


# ── Multi-dataset × multi-config driver ───────────────────────────────────────

def run_multi_config_experiment(
    configs: list = None,
    datasets: list = None,
    config_id: str = None,
) -> dict:
    """
    Run the experiment for every (dataset, config) combination.

    Append-mode with dedup: backs up existing CSV, appends new rows,
    skips (dataset, config, model_id) triples already present.
    """
    if configs  is None: configs  = ["core"]
    if datasets is None: datasets = ["BibTeX2DocBook"]

    unknown_cfg = [c for c in configs  if c not in PROMPT_CONFIGS]
    unknown_ds  = [d for d in datasets if d not in DATASETS]
    if unknown_cfg:
        raise ValueError(f"Unknown config(s): {unknown_cfg}")
    if unknown_ds:
        raise ValueError(f"Unknown dataset(s): {unknown_ds}. "
                         f"Available: {list(DATASETS.keys())}")

    _key_files = {
        "deepseek":       "deepseek_api_key.txt",
        "deepseek-flash": "deepseek_api_key.txt",
        "qwen":           "qwen_api_key.txt",
        "glm":            "glm_api_key.txt",
        "openai":         "openai_api_key.txt",
    }
    _key_file = _key_files.get(LLM_PROVIDER, "deepseek_api_key.txt")
    _key_path = ROOT / "config" / _key_file
    api_key = read_api_key(str(_key_path))
    logger.info(f"LLM Provider: {LLM_PROVIDER} | Key: {_key_file}")

    mutant_counts = {
        ds: len(_discover_mutants_for_dataset(DATASETS[ds]))
        for ds in datasets
    }
    _save_experiment_metadata(datasets, configs, mutant_counts)

    _backup_csv(CSV_PATH)
    existing_keys = _load_existing_keys(CSV_PATH)
    if existing_keys:
        logger.info(
            f"Found {len(existing_keys)} existing rows in CSV — "
            f"will append new results and skip duplicates."
        )

    fh, writer  = _init_csv(CSV_PATH, CSV_FIELDNAMES, overwrite=False)
    all_results = {}
    all_stats   = {}

    try:
        idx = 0
        for dataset_name in datasets:
            for config_name in configs:
                print(f"\n{'#'*60}")
                print(f"# Dataset: {dataset_name}  Config: {config_name.upper()}")
                print(f"{'#'*60}")
                metrics, stats = run_one(
                    dataset_name    = dataset_name,
                    config_name     = config_name,
                    config_index    = idx,
                    api_key         = api_key,
                    writer          = writer,
                    fh              = fh,
                    existing_keys   = existing_keys,
                    output_dir_name = config_id if config_id else config_name,
                )
                all_results[(dataset_name, config_name)] = metrics
                all_stats[(dataset_name, config_name)]   = stats
                idx += 1
    finally:
        fh.close()

    _save_summary_csv(all_stats)
    _print_comparison(all_results)

    logger.info(f"Per-model CSV  → {CSV_PATH}")
    logger.info(f"Summary CSV    → {SUMMARY_CSV_PATH}")
    logger.info(f"Metadata       → {METADATA_PATH}")
    return all_results


def _print_comparison(results: dict) -> None:
    if not results:
        return
    print(f"\n{'='*70}")
    print("MULTI-DATASET × MULTI-CONFIG COMPARISON")
    print(f"{'='*70}")
    print(f"{'Dataset':<18} {'Config':<10} {'Exec%':>6} "
          f"{'Coverage':>10} {'Kill Rate':>10}")
    print("-" * 58)
    for (ds, cfg), metrics in results.items():
        s = metrics["summary"]
        print(
            f"{ds:<18} {cfg:<10} "
            f"{s['transformation_execution_rate']:>6.1%} "
            f"{s['aggregate_rule_coverage']:>10.2%} "
            f"{s['aggregate_kill_rate']:>10.2%}"
        )
    print("=" * 70)


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", nargs="+",
                        default=["BibTeX2DocBook"],
                        choices=list(DATASETS.keys()))
    parser.add_argument("--configs",  nargs="+",
                        default=["core"],
                        choices=list(PROMPT_CONFIGS.keys()))
    args = parser.parse_args()
    run_multi_config_experiment(configs=args.configs, datasets=args.datasets)