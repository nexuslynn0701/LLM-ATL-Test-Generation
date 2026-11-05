#!/usr/bin/env python3
"""
run_openllm_ladder.py — Open-source LLM ladder experiment driver.

Extends the original run_ladder_experiment.py protocol to three locally-served
Ollama models (devstral-24b, gemma-12b, glm-4.7f).

Key differences from original:
  - Results go to results_openllm_v1/ (NOT results_v3/)
  - Ant2Maven ASTMO is included (with its OCL contract, like the other subjects)
  - Deterministic seed per attempt
  - Full provenance fields recorded per attempt
  - Checkpoint/resume: existing attempts are never overwritten
  - Ollama-specific: api_key="ollama", url="http://localhost:11434/..."
  - No coverage guidance, no repair (matching ladder experiment constraints)

Usage:
  python3 src/experiment/run_openllm_ladder.py --provider openllm:devstral --condition sm --datasets BibTeX2DocBook --n-models 5
  python3 src/experiment/run_openllm_ladder.py --provider openllm:devstral --all-conditions
  python3 src/experiment/run_openllm_ladder.py --provider openllm:devstral --dry-run
"""

import argparse
import csv
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.llm.openllm_config import (
    OPENLLM_MODELS, OPENLLM_SUBJECTS,
    SAMPLING_CONTRACT, OPENLLM_CSV_FIELDNAMES,
    compute_seed, get_openllm_provider_configs,
    RESULTS_OPENLLM_DIR,
)
from src.llm.llm_client import PROVIDER_CONFIGS, call_llm
from src.llm.openllm_extraction import (
    STRICT_CONTRACT_PASS,
    STRICT_CONTRACT_FAIL,
    STRICT_FAIL_API_ERROR,
    STRICT_FAIL_MISSING_WRAPPER,
    STRICT_FAIL_MALFORMED_XML,
    STRICT_FAIL_NO_XML,
    RECOVERY_RECOVERABLE,
    RECOVERY_FAIL_XML_MALFORMED,
    RECOVERY_FAIL_UNEXPECTED_ROOT,
    RECOVERY_FAIL_DOCTYPE_FORBIDDEN,
    RECOVERY_ATTEMPTED_NO_FENCE,
    RECOVERY_ATTEMPTED_MULTIPLE_FENCES,
    PATHWAY_STRICT,
    PATHWAY_RECOVERED,
    PATHWAY_NONE,
    PRIMARY_ELIGIBLE,
    PRIMARY_INELIGIBLE,
    SENSITIVITY_ELIGIBLE,
    SENSITIVITY_INELIGIBLE,
    classify_extraction,
    EXTRACTION_CSV_FIELDS,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Merge OpenLLM providers into the global registry ────────────────────────────

PROVIDER_CONFIGS.update(get_openllm_provider_configs())

# ── Reuse DATASETS, build_ladder_prompt, get_executor_config from original ──────
# pylint: disable=wrong-import-position

from src.experiment.run_ladder_experiment import (
    DATASETS,
    CONDITIONS,
    CONDITION_FLAGS,
    build_ladder_prompt,
    get_executor_config,
    get_safety_note,
    _remove_template_section,
    CSV_FIELDNAMES as _ORIGINAL_CSV_FIELDNAMES,
)

# ── CSV helpers ─────────────────────────────────────────────────────────────────

def init_results_csv(csv_path: Path, fieldnames: list) -> Path:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
    return csv_path


def load_completed_attempts(csv_path: Path) -> set:
    """Return set of (provider, condition, dataset, model_id) already in CSV."""
    completed = set()
    if csv_path.exists() and csv_path.stat().st_size > 0:
        with open(csv_path, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                completed.add((
                    row.get("provider", ""),
                    row.get("condition", ""),
                    row.get("dataset", ""),
                    row.get("model_id", ""),
                ))
    if completed:
        logger.info(f"  Found {len(completed)} existing attempts — will skip.")
    return completed


def append_result(csv_path: Path, row: dict, fieldnames: list):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


# ── Attempt-level provenance ────────────────────────────────────────────────────

def build_provenance_metadata(model_cfg: dict, attempt_id: int,
                               subject: str, condition: str) -> dict:
    """Return a dict of provenance fields for one attempt."""
    seed = compute_seed(
        model_cfg["model_alias"], subject, condition, attempt_id
    )
    sampling = {}
    for param, spec in SAMPLING_CONTRACT.items():
        val = spec["value"]
        if param == "seed":
            val = seed
        elif param == "max_tokens":
            # Allow per-model override (e.g. GLM with thinking disabled needs more)
            if "max_tokens_override" in model_cfg:
                val = model_cfg["max_tokens_override"]
        sampling[param] = val

    return {
        "model_alias":          model_cfg["model_alias"],
        "ollama_name":          model_cfg["ollama_name"],
        
        "server_version":       "TBD_AT_RUNTIME",
        
        "temperature":          sampling["temperature"],
        "top_p":                sampling["top_p"],
        "top_k":                sampling["top_k"],
        "min_p":                sampling.get("min_p", ""),
        "repeat_penalty":       sampling["repeat_penalty"],
        "seed":                 seed,
        "max_tokens":           sampling["max_tokens"],
        "context_size":         sampling["context_size"],
        "stream":               sampling["stream"],
        "prompt_eval_count":    "",
        "eval_count":           "",
        "total_duration_ms":    "",
        "load_duration_ms":     "",
        
        
    }


# ── Ollama API call wrapper ─────────────────────────────────────────────────────

def call_ollama(prompt: str, model_cfg: dict, seed: int,
                max_tokens: int = 4096, temperature: float = 0.2,
                top_p: float = 0.95, top_k: int = 40,
                repeat_penalty: float = 1.0) -> dict:
    """
    Call Ollama via OpenAI-compatible /v1/chat/completions.

    Returns dict with keys:
      content: str           — the model's text response
      prompt_eval_count: int — input token count
      eval_count: int        — output token count
      total_duration_ms: int
      load_duration_ms: int
      model: str             — actual model used
      error: str or None
    """
    import requests as _requests

    url = "http://localhost:11434/v1/chat/completions"
    payload = {
        "model": model_cfg["ollama_name"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "top_p": top_p,
        "seed": seed,
        "max_tokens": max_tokens,
        "stream": False,
        "options": {
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
        },
    }

    t0 = time.monotonic()
    try:
        resp = _requests.post(
            url, json=payload,
            timeout=(30, 300),  # 30s connect, 300s read
        )
        resp.raise_for_status()
        body = resp.json()
        t1 = time.monotonic()

        choice = body.get("choices", [{}])[0]
        usage = body.get("usage", {})

        return {
            "content":            choice.get("message", {}).get("content", ""),
            "prompt_eval_count":  usage.get("prompt_tokens", 0),
            "eval_count":         usage.get("completion_tokens", 0),
            "total_duration_ms":  int((t1 - t0) * 1000),
            "load_duration_ms":   0,
            "model":              body.get("model", ""),
            "finish_reason":      choice.get("finish_reason", ""),
            "error":              None,
        }
    except Exception as e:
        return {
            "content": "",
            "prompt_eval_count": 0,
            "eval_count": 0,
            "total_duration_ms": 0,
            "load_duration_ms": 0,
            "model": "",
            "finish_reason": "",
            "error": str(e),
        }


# ── Single cell runner ──────────────────────────────────────────────────────────

def run_openllm_cell(
    provider: str,
    condition: str,
    dataset_name: str,
    n_models: int = 100,
    dry_run: bool = False,
    csv_path: Path = None,
    run_scope: str = "PRE_GATE_DIAGNOSTIC_DO_NOT_ANALYZE",
) -> dict:
    """
    Run one (provider, condition, dataset) cell with the open-LLM protocol.
    dry_run=True: builds prompt and prints stats, but does NOT call Ollama.
    """
    model_cfg = OPENLLM_MODELS[provider]
    suffix = condition
    provider_short = model_cfg["model_alias"]

    logger.info(f"{'='*60}")
    logger.info(f"CELL: {provider_short} / {condition} / {dataset_name}  n={n_models}  dry_run={dry_run}")

    # ── Build prompt ─────────────────────────────────────────────────────────
    prompt, meta = build_ladder_prompt(dataset_name, condition)
    logger.info(f"  prompt: {meta['prompt_lines']} lines")
    logger.info(f"  components: {meta['components']}")
    if meta.get("astmo_note"):
        logger.info(f"  astmo_note: {meta['astmo_note']}")

    if dry_run:
        logger.info(f"  DRY-RUN: prompt built ({len(prompt)} chars). No API call.")
        return {"status": "dry_run_ok"}

    # ── Output directories ───────────────────────────────────────────────────
    # P0-1: strict isolation — primary vs sensitivity
    primary_gen_dir   = RESULTS_OPENLLM_DIR / provider_short / "primary" / "generated_models" / dataset_name / suffix
    primary_out_dir   = RESULTS_OPENLLM_DIR / provider_short / "primary" / "outputs" / dataset_name / suffix
    sensitivity_gen_dir = RESULTS_OPENLLM_DIR / provider_short / "sensitivity" / "recovered_models" / dataset_name / suffix
    sensitivity_out_dir = RESULTS_OPENLLM_DIR / provider_short / "sensitivity" / "outputs" / dataset_name / suffix
    prompt_dir = RESULTS_OPENLLM_DIR / provider_short / "prompt_samples"
    raw_dir    = RESULTS_OPENLLM_DIR / provider_short / "raw_responses" / dataset_name / suffix

    primary_gen_dir.mkdir(parents=True, exist_ok=True)
    primary_out_dir.mkdir(parents=True, exist_ok=True)
    sensitivity_gen_dir.mkdir(parents=True, exist_ok=True)
    sensitivity_out_dir.mkdir(parents=True, exist_ok=True)
    prompt_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    # ── Save prompt sample (once per cell) ───────────────────────────────────
    sample_path = prompt_dir / f"prompt_{dataset_name}_{condition}.txt"
    if not sample_path.exists():
        sample_path.write_text(
            f"# {dataset_name} / {condition} / {provider_short}\n"
            f"# components={meta['components']}\n"
            f"# ocl_n_constraints={meta.get('ocl_n_constraints', 0)}\n"
            f"# astmo_note={meta.get('astmo_note', 'N/A')}\n"
            f"# generated={datetime.now(timezone.utc).isoformat()}\n\n"
            + prompt,
            encoding="utf-8",
        )

    # ── Load already-completed attempts ──────────────────────────────────────
    completed = load_completed_attempts(csv_path) if csv_path else set()

    # ── ATL executor config ──────────────────────────────────────────────────
    ds = DATASETS[dataset_name]
    exec_cfg = get_executor_config(dataset_name)

    n_ok = 0
    n_total = 0

    for attempt_id in range(1, n_models + 1):
        index_str = f"{attempt_id:04d}"
        row_key = (provider, condition, dataset_name, index_str)

        if row_key in completed:
            logger.info(f"  [{index_str}] already completed — skipping")
            continue

        n_total += 1
        logger.info(f"  [{index_str}] generating...")

        # ── Build provenance ─────────────────────────────────────────────────
        prov = build_provenance_metadata(
            model_cfg, attempt_id, dataset_name, condition
        )

        # ── Call Ollama ──────────────────────────────────────────────────────
        result = call_ollama(
            prompt=prompt,
            model_cfg=model_cfg,
            seed=prov["seed"],
            max_tokens=prov["max_tokens"],
            temperature=prov["temperature"],
            top_p=prov["top_p"],
            top_k=prov["top_k"],
            repeat_penalty=prov["repeat_penalty"],
        )

        # ── Empty extraction_prov for error paths ───────────────────────────
        empty_extraction = {
            "strict_contract_status": STRICT_CONTRACT_FAIL,
            "strict_failure_reason": STRICT_FAIL_API_ERROR,
            "recovery_attempted": str(False),
            "recovery_rule": "",
            "recovery_status": "",
            "strict_extraction_path": "",
            
            "recovery_attempted": str(False),
            "recovery_rule": "",
            "recovery_status": "",
            "recovered_xmi_path": "",
            
            "recovered_xml_well_formed": str(False),
            "recovered_root_tag": "",
            "recovered_atl_runtime_status": "",
            "extraction_pathway": PATHWAY_NONE,
            "primary_analysis_eligible": str(PRIMARY_INELIGIBLE),
            "sensitivity_analysis_eligible": str(SENSITIVITY_INELIGIBLE),
            
            
            "run_scope": run_scope,
            "counts_toward_experiment_budget": str(run_scope == "GATE_PASSED"),
            "finish_reason": "", "prompt_tokens": "", "completion_tokens": "",
            "num_ctx": "32768", "context_overflow": str(False), "output_truncated": str(False),
        }

        if result["error"]:
            logger.warning(f"  [{index_str}] OLLAMA ERROR: {result['error'][:200]}")
            prov["prompt_eval_count"] = ""
            prov["eval_count"] = ""
            prov["total_duration_ms"] = result.get("total_duration_ms", 0)

            if csv_path:
                append_result(csv_path, {
                    "timestamp":  datetime.now(timezone.utc).isoformat(),
                    "provider":   provider,
                    "condition":  condition,
                    "dataset":    dataset_name,
                    "model_id":   index_str,
                    "status":     "OLLAMA_ERROR",
                    "valid":      0,
                    
                    "prompt_lines":  meta["prompt_lines"],
                    
                    "ocl_n_constraints": meta.get("ocl_n_constraints", 0),
                    "components": "|".join(meta["components"]),
                    "raw_response_path": "",
                    "extracted_xmi_path": "",
                    "validity_note": result["error"][:200],
                    **empty_extraction,
                    **prov,
                }, OPENLLM_CSV_FIELDNAMES)
            continue

        raw_response = result["content"]

        # ── Save raw response ────────────────────────────────────────────────
        raw_path = raw_dir / f"raw_response_{index_str}.txt"
        raw_path.write_text(raw_response, encoding="utf-8")

        # ── Save strict extraction (even if empty, for provenance) ───────────
        from src.generator.test_generator import extract_xml_block as _strict_extract
        strict_extraction_dir = RESULTS_OPENLLM_DIR / provider_short / "strict_extractions" / dataset_name / suffix
        strict_extraction_dir.mkdir(parents=True, exist_ok=True)
        strict_raw = _strict_extract(raw_response, "source_model") or ""
        strict_ext_path = strict_extraction_dir / f"strict_extraction_{index_str}.txt"
        strict_ext_path.write_text(strict_raw, encoding="utf-8")

        # ── Dual-pathway XMI extraction (subject-aware) ──────────────────────
        from src.generator.test_generator import save_model

        classification = classify_extraction(raw_response, subject=dataset_name)
        usable_xmi   = classification.get("usable_xml")
        pathway      = classification.get("extraction_pathway", PATHWAY_NONE)

        prov["prompt_eval_count"] = result["prompt_eval_count"]
        prov["eval_count"] = result["eval_count"]
        prov["total_duration_ms"] = result["total_duration_ms"]
        prov["raw_response_path"] = str(raw_path)

        # Build extraction provenance
        extraction_prov = {
            "strict_contract_status":    classification["strict_contract_status"],
            "strict_failure_reason":     classification["strict_failure_reason"],
            "strict_extraction_path":    str(strict_ext_path),
            
            "recovery_attempted":        str(classification["recovery_attempted"]),
            "recovery_rule":             classification["recovery_rule"],
            "recovery_status":           classification["recovery_status"],
            "recovered_xmi_path":        classification["recovered_xmi_path"],
            
            "recovered_xml_well_formed": str(classification["recovered_xml_well_formed"]),
            "recovered_root_tag":        classification["recovered_root_tag"],
            "recovered_atl_runtime_status": classification["recovered_atl_runtime_status"],
            "extraction_pathway":        pathway,
            "primary_analysis_eligible":     str(classification["primary_analysis_eligible"]),
            "sensitivity_analysis_eligible": str(classification["sensitivity_analysis_eligible"]),
            
            
            "run_scope":                 run_scope,
            "counts_toward_experiment_budget": str(run_scope == "GATE_PASSED"),
            # Context budget (Fix #6)
            "finish_reason":             result.get("finish_reason", ""),
            "prompt_tokens":             prov.get("prompt_eval_count", ""),
            "completion_tokens":         prov.get("eval_count", ""),
            "num_ctx":                   prov.get("context_size", 32768),
            "context_overflow":          str(False),
            "output_truncated":          str(False),
        }

        # ── No usable XMI ────────────────────────────────────────────────────
        if usable_xmi is None:
            logger.warning(
                f"  [{index_str}] No usable XMI "
                f"(strict={classification['strict_contract_status']} "
                f"recovery_attempted={classification['recovery_attempted']} "
                f"recovery_status={classification['recovery_status']})"
            )
            prov["extracted_xmi_path"] = ""

            # Unified failure classification (Fix #4)
            recovery_status = classification.get("recovery_status", "")
            strict_reason = classification.get("strict_failure_reason", "")

            if recovery_status == RECOVERY_FAIL_XML_MALFORMED:
                fail_status = "GENERATION_FAIL_MALFORMED_XML"
            elif strict_reason == STRICT_FAIL_MALFORMED_XML:
                fail_status = "GENERATION_FAIL_MALFORMED_XML"
            elif recovery_status == RECOVERY_FAIL_UNEXPECTED_ROOT:
                fail_status = "GENERATION_FAIL_UNEXPECTED_ROOT"
            elif strict_reason in (RECOVERY_FAIL_UNEXPECTED_ROOT,):
                fail_status = "GENERATION_FAIL_UNEXPECTED_ROOT"
            elif recovery_status == RECOVERY_FAIL_DOCTYPE_FORBIDDEN:
                fail_status = "GENERATION_FAIL_MALFORMED_XML"
            elif classification.get("recovery_attempted") and recovery_status in (
                RECOVERY_ATTEMPTED_NO_FENCE, RECOVERY_ATTEMPTED_MULTIPLE_FENCES):
                fail_status = "GENERATION_FAIL_NO_XML"
            elif not classification.get("recovery_attempted") and strict_reason in (
                STRICT_FAIL_NO_XML, ""):
                fail_status = "GENERATION_FAIL_NO_XML"
            else:
                fail_status = "GENERATION_FAIL_NO_XML"

            # Check for truncation / context overflow (Fix #6)
            eval_tokens = int(prov.get("eval_count", 0) or 0)
            prompt_tokens = int(prov.get("prompt_eval_count", 0) or 0)
            max_tok = prov.get("max_tokens", 8192)
            num_ctx = prov.get("context_size", 32768)
            if eval_tokens >= max_tok:
                extraction_prov["output_truncated"] = str(True)
                if prompt_tokens + max_tok > num_ctx:
                    extraction_prov["context_overflow"] = str(True)
                    fail_status = "CONTEXT_OVERFLOW"
                else:
                    fail_status = "OUTPUT_TRUNCATED"

            if csv_path:
                append_result(csv_path, {
                    "timestamp":  datetime.now(timezone.utc).isoformat(),
                    "provider":   provider,
                    "condition":  condition,
                    "dataset":    dataset_name,
                    "model_id":   index_str,
                    "status":     fail_status,
                    "valid":      0,
                    
                    "prompt_lines":  meta["prompt_lines"],
                    
                    "ocl_n_constraints": meta.get("ocl_n_constraints", 0),
                    "components": "|".join(meta["components"]),
                    "raw_response_path": str(raw_path),
                    "extracted_xmi_path": "",
                    **extraction_prov,
                    **prov,
                }, OPENLLM_CSV_FIELDNAMES)
            continue

        # ═══════════════════════════════════════════════════════════════════════
        # Save XMI with strict directory isolation (P0-1)
        # ═══════════════════════════════════════════════════════════════════════
        atl_source_path = None  # path used for ATL call

        if pathway == PATHWAY_STRICT:
            # Strict: write to primary directory
            source_path = primary_gen_dir / f"source_model_{index_str}.xmi"
            save_model(usable_xmi, str(source_path))
            prov["extracted_xmi_path"] = str(source_path)
            # P0 criterion 9: this is the ONLY path that may write to primary
            # Any other path writing to primary would be a bug
            atl_source_path = str(source_path)

        elif pathway == PATHWAY_RECOVERED:
            # Recovered: write ONLY to sensitivity directory
            # DO NOT write to primary/generated_models/
            recovered_path = sensitivity_gen_dir / f"source_model_{index_str}_recovered.xmi"
            save_model(usable_xmi, str(recovered_path))
            prov["extracted_xmi_path"] = ""  # primary path is EMPTY
            extraction_prov["recovered_xmi_path"] = str(recovered_path)

            # Write to temp dir for ATL execution
            atl_tmpdir = tempfile.mkdtemp(prefix="openllm_atl_")
            atl_source_path = os.path.join(atl_tmpdir, "source_model.xmi")
            with open(atl_source_path, "w", encoding="utf-8") as f:
                f.write(usable_xmi)

        else:
            logger.warning(f"  [{index_str}] usable_xmi present but pathway='{pathway}' — treating as no usable XML")
            prov["extracted_xmi_path"] = ""
            if csv_path:
                append_result(csv_path, {
                    "timestamp":  datetime.now(timezone.utc).isoformat(),
                    "provider":   provider, "condition": condition,
                    "dataset":    dataset_name, "model_id": index_str,
                    "status":     "GENERATION_FAIL_NO_XML",
                    "valid":      0,
                    
                    "prompt_lines":  meta["prompt_lines"],
                    
                    "ocl_n_constraints": meta.get("ocl_n_constraints", 0),
                    "components": "|".join(meta["components"]),
                    "raw_response_path": str(raw_path),
                    "extracted_xmi_path": "",
                    **extraction_prov, **prov,
                }, OPENLLM_CSV_FIELDNAMES)
            continue

        # ═══════════════════════════════════════════════════════════════════════
        # ATL execution
        # ═══════════════════════════════════════════════════════════════════════
        from src.executor.transformation_executor import run_transformation
        from src.analyzer.coverage_analyzer import compute_rule_coverage

        atl_path_str = str(ds["dataset_dir"] / ds["atl_file"])

        if pathway == PATHWAY_STRICT:
            out_path = str(primary_out_dir / f"output_{index_str}.xmi")
        else:
            out_path = str(sensitivity_out_dir / f"output_{index_str}_recovered.xmi")

        exec_res = run_transformation(atl_source_path, out_path, ds["atl_name"], exec_cfg)

        atl_success = exec_res["success"]
        extraction_prov["recovered_atl_runtime_status"] = (
            "SUCCESS" if atl_success else "FAILED"
        )

        if atl_success:
            trace_path = exec_res.get("trace") or out_path.replace(".xmi", "_trace.xmi")
            if os.path.isfile(trace_path):
                cov = compute_rule_coverage(trace_path, atl_path_str)
                rules_covered = cov["covered_rules"]
                rules_total = cov["total_rules"]
                rule_coverage = cov["rule_coverage"]
            else:
                rules_covered = ""
                rules_total = ""
                rule_coverage = ""

            if pathway == PATHWAY_STRICT:
                status = "OK"
            else:
                status = "OK_RECOVERED"
            valid = 1
            n_ok += 1
        else:
            status = "ORIGINAL_ATL_EXEC_FAIL"
            valid = 0
            rules_covered = ""
            rules_total = ""
            rule_coverage = ""

        # ── Final eligibility: ATL must also pass ────────────────────────────
        # P0-3: primary_eligible = strict + well-formed + expected_root + ATL
        #       sensitivity_eligible = primary OR (recovered + well-formed + expected_root + ATL)
        primary_final = (
            classification["primary_analysis_eligible"] == PRIMARY_ELIGIBLE
            and atl_success
        )
        sensitivity_final = (
            primary_final
            or (
                classification["sensitivity_analysis_eligible"] == SENSITIVITY_ELIGIBLE
                and atl_success
            )
        )
        extraction_prov["primary_analysis_eligible"] = str(primary_final)
        extraction_prov["sensitivity_analysis_eligible"] = str(sensitivity_final)

        if csv_path:
            append_result(csv_path, {
                "timestamp":       datetime.now(timezone.utc).isoformat(),
                "provider":        provider,
                "condition":       condition,
                "dataset":         dataset_name,
                "model_id":        index_str,
                "status":          status,
                "valid":           valid,
                "kill_rate":       "",
                "mutants_killed":  "",
                "mutants_total":   "",
                "rules_covered":   rules_covered,
                "rules_total":     rules_total,
                "rule_coverage":   rule_coverage,
                
                "prompt_lines":    meta["prompt_lines"],
                
                "ocl_n_constraints": meta.get("ocl_n_constraints", 0),
                "components":      "|".join(meta["components"]),
                "validity_note":   meta.get("astmo_note", ""),
                **extraction_prov,
                **prov,
            }, OPENLLM_CSV_FIELDNAMES)

        # ── Clean up temp ATL dir ────────────────────────────────────────────
        if pathway == PATHWAY_RECOVERED:
            try:
                import shutil
                shutil.rmtree(atl_tmpdir, ignore_errors=True)
            except Exception:
                pass

        logger.info(
            f"  [{index_str}] {status} (pathway={pathway}) "
            f"(tokens: {result['prompt_eval_count']}+{result['eval_count']}, "
            f"seed={prov['seed']})"
        )

    val_rate = n_ok / n_total if n_total > 0 else 0.0
    logger.info(f"  Cell complete: {n_ok}/{n_total} valid ({val_rate:.1%})")
    return {"status": "done", "n_ok": n_ok, "n_total": n_total,
            "val_rate": val_rate}


# ── Primary analysis loader assertion (criterion 9) ─────────────────────────────

def assert_primary_analysis_eligible(row: dict) -> None:
    """
    Hard assertion: any row loaded for primary analysis MUST be strict-valid.

    This function MUST be called by every RQ1–RQ5 analysis script before using
    a row from the OpenLLM CSV. It prevents silent contamination of primary
    analysis with recovered data.

    Raises AssertionError if the row fails any primary eligibility check.
    """
    status = row.get("status", "")
    pathway = row.get("extraction_pathway", "")
    primary = row.get("primary_analysis_eligible", "")
    strict_status = row.get("strict_contract_status", "")

    assert primary == str(True), (
        f"PRIMARY ANALYSIS ASSERTION FAILED: "
        f"primary_analysis_eligible={primary} for model_id={row.get('model_id', '?')}"
    )
    assert pathway == PATHWAY_STRICT, (
        f"PRIMARY ANALYSIS ASSERTION FAILED: "
        f"extraction_pathway='{pathway}' (expected 'strict') "
        f"for model_id={row.get('model_id', '?')}"
    )
    assert strict_status == STRICT_CONTRACT_PASS, (
        f"PRIMARY ANALYSIS ASSERTION FAILED: "
        f"strict_contract_status='{strict_status}' (expected 'PASS_FORMAT_COMPLIANT') "
        f"for model_id={row.get('model_id', '?')}"
    )
    assert "RECOVERED" not in status, (
        f"PRIMARY ANALYSIS ASSERTION FAILED: "
        f"status='{status}' contains 'RECOVERED' "
        f"for model_id={row.get('model_id', '?')}"
    )
    run_scope = row.get("run_scope", "")
    assert run_scope == "GATE_PASSED", (
        f"PRIMARY ANALYSIS ASSERTION FAILED: "
        f"run_scope='{run_scope}' — only GATE_PASSED records may enter primary analysis "
        f"for model_id={row.get('model_id', '?')}"
    )
    counts = row.get("counts_toward_experiment_budget", "")
    assert counts != "False", (
        f"PRIMARY ANALYSIS ASSERTION FAILED: "
        f"counts_toward_experiment_budget='{counts}' "
        f"for model_id={row.get('model_id', '?')}"
    )


def load_primary_analysis_data(csv_path: str) -> list[dict]:
    """
    Load only primary-analysis-eligible rows from the OpenLLM CSV.

    Hard-asserts every loaded row (criterion 9).
    Returns rows where primary_analysis_eligible == 'True'.
    """
    import csv as _csv
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in _csv.DictReader(f):
            if row.get("primary_analysis_eligible") == str(True):
                assert_primary_analysis_eligible(row)
                rows.append(row)
    return rows


# ── Entry point ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Open-source LLM ladder experiment (Ollama backend)"
    )
    parser.add_argument("--provider", required=True,
                        choices=list(OPENLLM_MODELS.keys()),
                        help="Which open-source model to use")
    parser.add_argument("--condition", choices=CONDITIONS,
                        help="Single ladder condition")
    parser.add_argument("--datasets", nargs="+",
                        default=list(OPENLLM_SUBJECTS.keys()),
                        choices=list(OPENLLM_SUBJECTS.keys()))
    parser.add_argument("--n-models", type=int, default=100,
                        help="Number of models per cell")
    parser.add_argument("--all-conditions", action="store_true",
                        help="Run ALL conditions for this subject")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build prompts and print stats; no API calls")
    parser.add_argument("--output-dir", default=None,
                        help="Override results root directory")
    parser.add_argument("--run-scope", default="PRE_GATE_DIAGNOSTIC_DO_NOT_ANALYZE",
                        choices=["PRE_GATE_DIAGNOSTIC_DO_NOT_ANALYZE",
                                 "FORMAT_COMPLIANCE_PROBE",
                                 "GATE_PASSED"],
                        help="Run scope tag (controls CSV fields and analysis eligibility)")
    args = parser.parse_args()

    global RESULTS_OPENLLM_DIR
    if args.output_dir:
        RESULTS_OPENLLM_DIR = Path(args.output_dir)

    provider = args.provider
    model_cfg = OPENLLM_MODELS[provider]
    provider_short = model_cfg["model_alias"]

    conditions = CONDITIONS if args.all_conditions else [args.condition]
    if not args.condition and not args.all_conditions:
        parser.error("--condition required (or use --all-conditions)")

    logger.info("=" * 60)
    logger.info(f"OpenLLM Ladder Experiment: {provider_short}")
    logger.info(f"  Model:  {model_cfg['ollama_name']} ({model_cfg['quantization']})")
    logger.info(f"  Conditions: {conditions}")
    logger.info(f"  Datasets:   {args.datasets}")
    logger.info(f"  n_models:   {args.n_models}")
    logger.info(f"  dry_run:    {args.dry_run}")
    logger.info(f"  Results:    {RESULTS_OPENLLM_DIR}")

    total_cells = sum(
        1 for ds in args.datasets
        for cond in conditions
        if cond in OPENLLM_SUBJECTS[ds]["conditions"]
    )
    logger.info(f"  Total cells: {total_cells}")
    logger.info("=" * 60)

    csv_path = RESULTS_OPENLLM_DIR / provider_short / "multi_config_results.csv"
    init_results_csv(csv_path, OPENLLM_CSV_FIELDNAMES)

    summary = []
    for condition in conditions:
        for dataset in args.datasets:
            subj_conditions = OPENLLM_SUBJECTS[dataset]["conditions"]
            if condition not in subj_conditions:
                logger.info(f"  Skip: {dataset}/{condition} not in subject config")
                continue

            result = run_openllm_cell(
                provider=provider,
                condition=condition,
                dataset_name=dataset,
                n_models=args.n_models,
                dry_run=args.dry_run,
                csv_path=csv_path,
                run_scope=args.run_scope,
            )
            summary.append({
                "provider": provider_short, "condition": condition,
                "dataset": dataset, **result,
            })

    logger.info("\n" + "=" * 60)
    logger.info("Summary:")
    for s in summary:
        if s.get("status") == "dry_run_ok":
            logger.info(
                f"  {s['provider']:15s} {s['condition']:6s} {s['dataset']:20s} "
                "DRY-RUN complete"
            )
        elif s.get("status") == "done":
            logger.info(
                f"  {s['provider']:15s} {s['condition']:6s} {s['dataset']:20s} "
                f"valid={s.get('n_ok',0)}/{s.get('n_total',0)} "
                f"({s.get('val_rate',0):.1%})"
            )


if __name__ == "__main__":
    main()
