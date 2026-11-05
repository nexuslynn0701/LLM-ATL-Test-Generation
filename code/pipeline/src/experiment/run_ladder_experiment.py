#!/usr/bin/env python3
"""
run_ladder_experiment.py
=========================
四档 prompt 信息量阶梯实验主脚本（RQ1 / RQ2 / RQ3）。

实验矩阵：
  4 conditions (sm / stm / astm / astmo)
  × 3 LLMs    (gpt / qwen / deepseek-flash)
  × N datasets (默认 4 个，可扩展)
  = 48 cells，每 cell 生成 100 个候选 source model

设计约束：
  - 四档严格累加：sm ⊂ stm ⊂ astm ⊂ astmo
  - 所有档无 feedback 机制（use_coverage_guidance=False）
  - safety note 全局基础组件，字节级一致，不属于四档变量
  - 不补齐到 100 个有效——生成失败计入 generation robustness (RQ1)
  - sm 档 pilot 是独立步骤（10个/cell），跑完后需手动决定是否启动全量

用法：
  python3 run_ladder_experiment.py --provider gpt --condition astmo
  python3 run_ladder_experiment.py --pilot-only          # sm档小样本，所有provider
  python3 run_ladder_experiment.py --all-conditions --provider gpt
  python3 run_ladder_experiment.py --provider gpt --condition sm --datasets BibTeX2DocBook --n-models 5

结果写入：
  results_v3/{provider}/outputs/{dataset}/{condition}/
  results_v3/{provider}/generated_models/{dataset}/{condition}/
  results_v3/{provider}/multi_config_results.csv
  results_v3/{provider}/prompt_samples/{dataset}_{condition}.txt
"""

import argparse
import csv
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.generator.test_generator import generate_tests
from src.llm.llm_client import PROVIDER_CONFIGS, get_api_key

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── 数据集配置（可扩展）────────────────────────────────────────────────────────
DATASETS = {
    "BibTeX2DocBook": {
        "dataset_dir":    ROOT / "datasets/models_BibTexML2DocBook",
        "source_mm":      "BibTeX.ecore",
        "target_mms":     ["DocBook.ecore"],
        "atl_name":       "BibTeX2DocBook",
        "atl_file":       "transformations/BibTeX2DocBook.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "BibTeX",
        "target_mm_name": "DocBook",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "CPL2SPL": {
        "dataset_dir":    ROOT / "datasets/models_CPL2SPL",
        "source_mm":      "CPL.ecore",
        "target_mms":     ["SPL.ecore"],
        "atl_name":       "CPL2SPL",
        "atl_file":       "transformations/CPL2SPL.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "CPL",
        "target_mm_name": "SPL",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "UML2ER": {
        "dataset_dir":    ROOT / "datasets/models_UML2ER",
        "source_mm":      "SimpleUml.ecore",
        "target_mms":     ["ER.ecore"],
        "atl_name":       "SimpleUml2ER",
        "atl_file":       "transformations/SimpleUml2ER.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "SimpleUML",
        "target_mm_name": "ER",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "Ecore2Maude": {
        "dataset_dir":    ROOT / "datasets/models_Ecore2Maude",
        "source_mm":      "ecore.ecore",
        "target_mms":     ["Maude.ecore"],
        "atl_name":       "Ecore2Maude",
        "atl_file":       "transformations/Ecore2Maude.atl",
        "ocl_file":       "OCL_Constraints.txt",
        "source_mm_name": "Ecore",
        "target_mm_name": "Maude",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
    },
    "Ant2Maven": {
        "dataset_dir":          ROOT / "datasets/models_Ant2Maven",
        "source_mm":            "Ant.ecore",
        "target_mms":           ["MavenMaven.ecore", "MavenProject.ecore"],
        "executor_target_mms":  {
            "OUTMaven":   "MavenMaven.ecore",
            "OUTProject": "MavenProject.ecore",
        },
        "atl_name":             "Ant2Maven",
        "atl_exec_name":        "Ant2Maven_trace",
        "atl_file":             "transformations/Ant2Maven.atl",
        "ocl_file":             "OCL_CONTRACT.txt",
        "source_mm_name":       "Ant",
        "target_mm_name":       "MavenMaven",
        "target_mm_names":      {
            "OUTMaven":   "MavenMaven",
            "OUTProject": "MavenProject",
        },
        "trace_mm_name":        "TMM",
        "trace_mm":             "Trace.ecore",
        "java_cp":              str(ROOT / "lib"),
        "normalize_source_xmi_ids": True,
        "reject_containment_warning": True,
        "reject_source_xsi_types": ["Echo", "Exec"],
        "conditions":           ["sm", "stm", "astm", "astmo"],
        "pilot_min_validity":   0.70,
    },
    "Grafcet2PetriNet": {
        "dataset_dir":    ROOT / "datasets/models_Grafcet2PetriNet",
        "source_mm":      "Grafcet.ecore",
        "target_mms":     ["PetriNet.ecore"],
        "atl_name":       "Grafcet2PetriNet_trace",
        "atl_file":       "transformations/Grafcet2PetriNet_trace.atl",
        "ocl_file":       "OCL_CONTRACT.txt",
        "source_mm_name": "Grafcet",
        "target_mm_name": "PetriNet",
        "trace_mm_name":  "TMM",
        "trace_mm":       "Trace.ecore",
        "java_cp":        str(ROOT / "lib"),
        "conditions":     ["sm", "stm", "astm", "astmo"],
        "pilot_min_validity": 0.10,
    },
}

# ── LLM provider 配置 ─────────────────────────────────────────────────────────
PROVIDERS = {
    "gpt":            "openai",
    "qwen":           "qwen",
    "deepseek-flash": "deepseek-flash",
}

EXPECTED_MODELS = {
    "gpt":            "gpt-5.1",
    "qwen":           "qwen3-max",
    "deepseek-flash": "deepseek-v4-flash",
}


def resolve_provider_model(provider: str) -> tuple[str, str]:
    llm_provider = PROVIDERS.get(provider, provider)
    resolved = PROVIDER_CONFIGS[llm_provider]["model"]
    expected = EXPECTED_MODELS[provider]
    if resolved != expected:
        raise RuntimeError(
            f"Model mismatch for {provider}: expected {expected}, got {resolved}"
        )
    return llm_provider, resolved

# ── 结果目录 ──────────────────────────────────────────────────────────────────
RESULTS_DIR = ROOT / "results_v3"

# ── 四档定义 ──────────────────────────────────────────────────────────────────
CONDITIONS = ["sm", "stm", "astm", "astmo"]


def _remove_template_section(prompt: str, heading: str) -> str:
    """Remove a named prompt section for lower-information ladder conditions."""
    lines = prompt.splitlines()
    out = []
    i = 0
    target = heading.strip().lower()

    while i < len(lines):
        line = lines[i]
        normalized = line.strip().strip("#").strip().lower()

        if normalized == target:
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_norm = nxt.strip().strip("#").strip()
                is_next_section = (
                    nxt_norm
                    and not nxt.startswith((" ", "\t"))
                    and nxt_norm.upper() == nxt_norm
                    and len(nxt_norm.split()) <= 8
                )
                if is_next_section:
                    break
                i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).strip() + "\n"


CONDITION_FLAGS = {
    "sm":    {"include_target_mm": False, "include_atl": False, "include_ocl": False},
    "stm":   {"include_target_mm": True,  "include_atl": False, "include_ocl": False},
    "astm":  {"include_target_mm": True,  "include_atl": True,  "include_ocl": False},
    "astmo": {"include_target_mm": True,  "include_atl": True,  "include_ocl": True},
}

# ── Safety note（Fix #4：显式dict，未配置数据集raise ValueError）────────────────

# frozen Grafcet note locations: canonical path first, frozen copy fallback
_GRAFCET_NOTE_PATHS = [
    ROOT / "results_v3_troya_aligned/grafcet2petrinet_extension/SAFETY_NOTE_DRAFT.txt",
    ROOT / "reproducibility/frozen_prompts/grafcet_safety_note_202606.txt",
]

# June-9 2026 rq4 Grafcet OCL contract (superseded by the Aug-6 rerun's
# OCL_CONTRACT.txt; preserved verbatim from the historical prompt dump)
_GRAFCET_RQ4_OCL = (
    ROOT / "reproducibility/frozen_prompts/grafcet_rq4_202606_ocl_contract.txt")


def _ant2maven_safety_note_run3() -> str:
    """Historical Ant2Maven note as used in the formal runs.

    The formal-run prompts (2026-06-01/02 and the 2026-08-06 astmo rerun)
    use the Ant:Jar task attribute ``destfile``; the current constant in
    multi_config_experiment was later edited to ``jarfile``.  The historical
    variant is reconstructed by reverting that edit on the current text.
    """
    from src.generator.test_generator import _ANT2MAVEN_SAFETY_NOTE
    return _ANT2MAVEN_SAFETY_NOTE.replace(
        'jarfile="dist/app.jar"', 'destfile="dist/app.jar"')


def get_safety_note(dataset_name: str, prompt_version: str = "latest") -> str:
    """Return the dataset-specific safety note for a prompt version.

    Historical versions return the note exactly as used in the formal runs
    (Ant2Maven ``destfile``); ``latest`` returns the current constants
    (Ant2Maven ``jarfile``).
    """
    if dataset_name == "Grafcet2PetriNet":
        for p in _GRAFCET_NOTE_PATHS:
            if p.is_file():
                return p.read_text(encoding="utf-8")
        raise FileNotFoundError("Grafcet safety note not found (tried: "
                                + ", ".join(str(p) for p in _GRAFCET_NOTE_PATHS)
                                + ")")

    try:
        if dataset_name == "Ant2Maven" and prompt_version == "run3_202606":
            return _ant2maven_safety_note_run3()
        from src.experiment.multi_config_experiment import _get_base_safety_note
        return _get_base_safety_note(dataset_name)
    except Exception as exc:
        raise ValueError(
            f"dataset {dataset_name!r} has no configured safety note"
        ) from exc


def _remove_template_section_title_only(prompt: str, heading: str) -> str:
    """June-2026 Grafcet-run behaviour: only the heading line is removed
    (the closing dashes line matches the next-section heuristic), leaving
    separator / intro residual.  Kept verbatim for historical fidelity."""
    lines = prompt.splitlines()
    out = []
    i = 0
    target = heading.strip().lower()

    while i < len(lines):
        line = lines[i]
        normalized = line.strip().strip("#").strip().lower()

        if normalized == target:
            i += 1
            while i < len(lines):
                nxt = lines[i]
                nxt_norm = nxt.strip().strip("#").strip()
                is_next_section = (
                    nxt_norm
                    and not nxt.startswith((" ", "\t"))
                    and nxt_norm.upper() == nxt_norm
                    and len(nxt_norm.split()) <= 8
                )
                if is_next_section:
                    break
                i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).strip() + "\n"


def _remove_template_section_clean(prompt: str, heading: str) -> str:
    """run3-era (2026-06-01/02) behaviour: remove the whole section block —
    opening dashes, title, closing dashes, intro, and the placeholder line —
    while keeping the blank separator lines between sections.  Byte-level
    behaviour is pinned by tests/test_frozen_prompt_repro.py."""
    def is_dashes(s):
        t = s.strip()
        return len(t) >= 20 and set(t) == {"-"}

    lines = prompt.splitlines()
    out = []
    i, n = 0, len(lines)
    target = heading.strip().lower()
    while i < n:
        if (i + 2 < n and is_dashes(lines[i])
                and lines[i + 1].strip().lower() == target
                and is_dashes(lines[i + 2])):
            j = i + 3
            # consume section content up to (excluding) the blank line that
            # precedes the next section's opening dashes
            while j < n:
                if (not lines[j].strip() and j + 1 < n
                        and is_dashes(lines[j + 1])):
                    break
                j += 1
            i = j
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out) + "\n"


# prompt versions ────────────────────────────────────────────────────────────
#   run3_202606      formal ladder run of 2026-06-01/02 (core four datasets
#                    + Ant2Maven): clean section removal, Ant note with
#                    ``destfile``.  Byte-reproduces the run3 / ant dumps.
#   grafcet_202606  Grafcet2PetriNet formal run (sm/stm/astm 2026-06-08,
#                    astmo rerun 2026-08-06): title-only section removal
#                    (historical residual preserved by design), current
#                    OCL_CONTRACT.txt.
#   grafcet_rq4_202606  Grafcet astmo as used by the 2026-06-09 RQ4 run
#                    (older context/inv-style OCL contract, preserved in
#                    reproducibility/frozen_prompts/).
#   latest           fixed clean removal + current constants (Ant2Maven
#                    ``jarfile``); for future execution only — does NOT
#                    reproduce the formal-run prompts.
PROMPT_VERSIONS = ("run3_202606", "grafcet_202606", "grafcet_rq4_202606",
                   "latest")
_VERSION_DATASETS = {
    "run3_202606": {"BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude",
                    "Ant2Maven"},
    "grafcet_202606": {"Grafcet2PetriNet"},
    "grafcet_rq4_202606": {"Grafcet2PetriNet"},
    "latest": None,          # all datasets
}
_VERSION_REMOVAL = {
    "run3_202606": _remove_template_section_clean,
    "grafcet_202606": _remove_template_section_title_only,
    "grafcet_rq4_202606": _remove_template_section_title_only,
    "latest": _remove_template_section_clean,
}


def _remove_template_section(prompt: str, heading: str,
                             prompt_version: str = "latest") -> str:
    """Remove a named prompt section using the version's behaviour."""
    return _VERSION_REMOVAL[prompt_version](prompt, heading)


def build_ladder_prompt(dataset_name: str, condition: str,
                        prompt_version: str = "latest") -> tuple[str, str, dict]:
    """
    Build the strict cumulative core-style ladder.

    sm    = source MM
    stm   = source MM + target MM
    astm  = stm + ATL
    astmo = astm + OCL

    prompt_version selects byte-level prompt behaviour (see PROMPT_VERSIONS):
    historical versions reproduce the formal-run prompts exactly; "latest"
    uses the current corrected logic and is intended for future runs only.

    The static wording, requirements, safety note, empty examples scaffold,
    and output format are shared across all tiers. astmo must be byte-identical
    to build_prompt(generate_test_model_v2.txt, example_paths=[]).
    """
    if prompt_version not in PROMPT_VERSIONS:
        raise ValueError(f"unknown prompt_version {prompt_version!r}; "
                         f"expected one of {PROMPT_VERSIONS}")
    allowed_ds = _VERSION_DATASETS[prompt_version]
    if allowed_ds is not None and dataset_name not in allowed_ds:
        raise ValueError(f"prompt_version {prompt_version!r} does not cover "
                         f"dataset {dataset_name!r}")
    ds = DATASETS[dataset_name]
    allowed = ds.get("conditions", CONDITIONS)
    if condition not in allowed:
        raise ValueError(f"{dataset_name} supports only: {allowed}")

    flags = CONDITION_FLAGS[condition]
    meta = {
        "condition": condition,
        "dataset": dataset_name,
        "components": ["header", "source_mm"],
    }

    template_path = ROOT / "prompts/generate_test_model_v2.txt"
    prompt = template_path.read_text(encoding="utf-8")

    full_mm_intro = (
        "Two metamodels are provided below in order: SOURCE first, TARGET second.\n\n"
        "The SOURCE metamodel defines the structure your output must conform to.\n"
        "The TARGET metamodel is provided only to help you understand the target-side\n"
        "types and bindings referenced in the ATL transformation.\n\n"
        "Do NOT instantiate target metamodel classes.\n"
        "Do NOT generate a target model.\n"
        "Do NOT use target-only classes, attributes, references, or namespace prefixes\n"
        "in the source model.\n"
    )
    source_only_intro = (
        "Only the SOURCE metamodel is provided below.\n\n"
        "The SOURCE metamodel defines the structure your output must conform to.\n\n"
        "Do NOT instantiate target metamodel classes.\n"
        "Do NOT generate a target model.\n"
        "Do NOT use classes, attributes, references, or namespace prefixes that are\n"
        "not defined in the source metamodel.\n"
    )

    src_path = ds["dataset_dir"] / ds["source_mm"]
    mm_paths = [src_path]

    if flags["include_target_mm"]:
        mm_paths.extend(ds["dataset_dir"] / name for name in ds["target_mms"])
        meta["components"].append("target_mm")
        meta["target_mm_paths"] = [
            str(ds["dataset_dir"] / name) for name in ds["target_mms"]
        ]
    else:
        if full_mm_intro not in prompt:
            raise RuntimeError("Expected v2 metamodel introduction was not found")
        prompt = prompt.replace(full_mm_intro, source_only_intro, 1)

    metamodel_content = ""
    for path in mm_paths:
        if not path.is_file():
            raise FileNotFoundError(f"Metamodel file not found: {path}")
        content = path.read_text(encoding="utf-8", errors="replace")
        metamodel_content += f"--- {path.name} ---\n{content}\n\n"
    metamodel_content = metamodel_content.rstrip()

    meta["source_mm_path"] = str(src_path)
    meta["source_mm_lines"] = len(
        src_path.read_text(encoding="utf-8", errors="replace").splitlines()
    )

    if flags["include_ocl"]:
        if prompt_version == "grafcet_rq4_202606":
            ocl_text = _GRAFCET_RQ4_OCL.read_text(
                encoding="utf-8", errors="replace").strip()
            meta["ocl_path"] = str(_GRAFCET_RQ4_OCL)
        else:
            ocl_path = ds["dataset_dir"] / ds["ocl_file"]
            if not ocl_path.is_file():
                raise FileNotFoundError(f"OCL file not found: {ocl_path}")
            ocl_text = ocl_path.read_text(encoding="utf-8", errors="replace").strip()
            meta["ocl_path"] = str(ocl_path)
        meta["components"].append("ocl")
        meta["ocl_n_constraints"] = sum(
            1 for line in ocl_text.splitlines()
            if line.strip() and not line.strip().startswith("-")
        )
        meta["ocl_source"] = "Troya et al. 2015 TSE"
    else:
        prompt = _remove_template_section(prompt, "OCL CONSTRAINTS",
                                          prompt_version)
        ocl_text = ""
        meta["ocl_n_constraints"] = 0

    if flags["include_atl"]:
        atl_path = ds["dataset_dir"] / ds["atl_file"]
        if not atl_path.is_file():
            raise FileNotFoundError(f"ATL file not found: {atl_path}")
        atl_text = atl_path.read_text(encoding="utf-8", errors="replace").strip()
        meta["components"].append("atl")
        meta["atl_path"] = str(atl_path)
        meta["atl_lines"] = len(atl_text.splitlines())
    else:
        prompt = _remove_template_section(prompt, "MODEL TRANSFORMATION (ATL)",
                                          prompt_version)
        atl_text = ""

    safety = get_safety_note(dataset_name, prompt_version)
    meta["components"].append("safety_note")
    meta["safety_note_chars"] = len(safety)
    meta["prompt_version"] = prompt_version

    prompt = prompt.replace("{METAMODEL_CONTENT}", metamodel_content)
    prompt = prompt.replace("{OCL_CONSTRAINTS}", ocl_text)
    prompt = prompt.replace("{ATL_CODE}", atl_text)
    prompt = prompt.replace("{EXAMPLE_MODELS}", "")
    prompt = prompt.replace("{SOURCE_FORMAT_NOTES}", safety)
    prompt = prompt.replace("{SAFETY_NOTE}", safety)

    meta["prompt_chars"] = len(prompt)
    meta["prompt_lines"] = len(prompt.splitlines())

    return prompt, meta


# ── CSV ───────────────────────────────────────────────────────────────────────
# Record prompt components and constraint counts.
CSV_FIELDNAMES = [
    "timestamp", "provider", "condition", "dataset", "model_id",
    "status", "valid", "kill_rate", "mutants_killed", "mutants_total",
    "rules_covered", "rules_total", "rule_coverage",
     "prompt_lines",
     "ocl_n_constraints", "components",
    "validity_note",
]

def append_result(csv_path: Path, row: dict):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES, extrasaction="ignore")
        if write_header:
            w.writeheader()
        w.writerow(row)


# ── 执行器配置 ────────────────────────────────────────────────────────────────

def get_executor_config(dataset_name: str) -> dict:
    ds = DATASETS[dataset_name]
    dd = ds["dataset_dir"]
    cfg = {
        "source_mm":           str(dd / ds["source_mm"]),
        "target_mm":           str(dd / ds["target_mms"][0]),
        "trace_mm":            str(dd / ds["trace_mm"]),
        "source_mm_name":      ds["source_mm_name"],
        "target_mm_name":      ds["target_mm_name"],
        "trace_mm_name":       ds["trace_mm_name"],
        "transformations_dir": str(dd / "transformations"),
        "atl_name":            ds["atl_name"],
        "atl_exec_name":       ds.get("atl_exec_name", ds["atl_name"]),
        "java_cp":             ds["java_cp"],
        "max_workers":         8,
    }
    if "executor_target_mms" in ds:
        cfg["target_mms"] = {
            name: str(dd / filename)
            for name, filename in ds["executor_target_mms"].items()
        }
        cfg["target_mm_names"] = ds["target_mm_names"]
    for key in (
        "normalize_source_xmi_ids",
        "reject_containment_warning",
        "reject_source_xsi_types",
    ):
        if key in ds:
            cfg[key] = ds[key]
    return cfg


# ── 单个 cell ─────────────────────────────────────────────────────────────────

def build_execution_prompt(dataset_name, condition, prompt_version):
    """Select the canonical published prompt explicitly for fresh reproduction."""
    if prompt_version != 'formal':
        return build_ladder_prompt(dataset_name, condition, prompt_version=prompt_version)
    manifest = json.loads((ROOT / 'reproducibility/frozen_prompts/manifest.json').read_text(encoding='utf-8'))
    rows = [r for r in manifest['rows'] if r['dataset'] == dataset_name
            and r['condition'] == condition and str(r.get('canonical')).lower() == 'true']
    versions = {r['prompt_version'] for r in rows}
    if len(versions) != 1:
        raise ValueError(f'No unique canonical frozen prompt: {dataset_name}/{condition}')
    version = versions.pop()
    return build_ladder_prompt(dataset_name,condition,prompt_version=version)


def run_cell(
    provider:     str,
    condition:    str,
    dataset_name: str,
    n_models:     int  = 100,
    pilot:        bool = False,
    csv_path:     Path = None,
    prompt_version: str = 'latest',
) -> dict:
    """
    运行一个 (provider, condition, dataset) cell。

    pilot=True：只生成 10 个 model，用于 sm 档 validity 估计。
    pilot 是独立步骤，不自动触发全量；全量需单独用 pilot=False 调用。
    """
    n = 10 if pilot else n_models
    logger.info(f"{'='*60}")
    logger.info(f"CELL: {provider} / {condition} / {dataset_name}  n={n}  pilot={pilot}")

    # Fix #1：先构建 prompt，后面直接传给 generate_tests
    prompt, meta = build_execution_prompt(dataset_name, condition, prompt_version)
    logger.info(f"  prompt: {meta['prompt_lines']} lines")
    logger.info(f"  components: {meta['components']}")
    if "ocl_n_constraints" in meta:
        logger.info(f"  ocl_n_constraints: {meta['ocl_n_constraints']}")

    # 保存 prompt 样本
    provider_short = provider.replace("-flash", "")
    prompt_dir = RESULTS_DIR / provider_short / "prompt_samples"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    sample_path = prompt_dir / f"prompt_{dataset_name}_{condition}.txt"
    if not sample_path.exists():
        sample_path.write_text(
            f"# {dataset_name} / {condition} / {provider}\n"
            f"# components={meta['components']}\n"
            f"# ocl_n_constraints={meta.get('ocl_n_constraints', 0)}\n"
            f"# generated={datetime.now().isoformat()}\n\n"
            + prompt,
            encoding="utf-8",
        )
        logger.info(f"  prompt sample → {sample_path}")

    # API key and explicit model lock
    llm_provider, resolved_model_id = resolve_provider_model(provider)
    meta["resolved_model_id"] = resolved_model_id
    logger.info(f"  resolved_model_id: {resolved_model_id}")

    # cell 级上下文 → 写进该 cell 所有 API 调用的审计记录
    from src.llm import call_logger
    call_logger.set_context(
        experiment        = "ladder",
        provider          = provider,
        condition         = condition,
        subject           = dataset_name,
        cell_n            = n,
        pilot             = pilot,
        model_requested   = resolved_model_id,
        
    )
    try:
        api_key = get_api_key(llm_provider)
    except Exception as e:
        logger.error(f"  无法读取 API key ({llm_provider}): {e}")
        return {"status": "api_key_error"}

    # 输出目录
    suffix    = f"{condition}_pilot" if pilot else condition
    gen_dir   = RESULTS_DIR / provider_short / "generated_models" / dataset_name / suffix
    trans_dir = RESULTS_DIR / provider_short / "outputs"          / dataset_name / suffix
    gen_dir.mkdir(parents=True, exist_ok=True)
    trans_dir.mkdir(parents=True, exist_ok=True)

    ds       = DATASETS[dataset_name]
    exec_cfg = get_executor_config(dataset_name)

    # Fix #1：generate_tests 需要接受 pre_built_prompt 参数
    # 如果 generate_tests 还没有这个参数，用 monkey-patch 临时覆盖模板逻辑
    # （正式修法：在 src/generator/test_generator.py 加 pre_built_prompt 参数）
    try:
        generation_results = generate_tests(
            template_path         = str(ROOT / "src/prompt/templates/generate_test_model.txt"),
            metamodel_paths       = [],        # pre_built_prompt 下不需要
            ocl_path              = "",        # pre_built_prompt 下不需要
            example_paths         = [],
            atl_path              = "",        # pre_built_prompt 下不需要
            api_key               = api_key,
            safety_note           = "",        # 已包含在 pre_built_prompt 中
            output_dir            = str(gen_dir),
            n                     = n,
            start_index           = 1,
            use_coverage_guidance = False,
            verify_coverage       = False,
            enable_repair         = False,
            fl_aware_feedback     = False,
            mixed_mode_feedback   = False,
            sat_aware_feedback    = False,
            transform_dir         = str(trans_dir),
            transformation_name   = ds["atl_name"],
            executor_config       = exec_cfg,
            pre_built_prompt      = prompt,    # Fix #1 核心：直接传入构建好的 prompt
            llm_provider          = llm_provider,  # 显式传入provider
              abort_on_api_error     = True,          # API异常不计入RQ1
        )
    except TypeError as e:
        if "pre_built_prompt" in str(e):
            logger.error(
                "  generate_tests 尚未支持 pre_built_prompt 参数。\n"
                "  请在 src/generator/test_generator.py 的 generate_tests() 函数签名里\n"
                "  加入 pre_built_prompt: str = None，\n"
                "  并在函数体内：若 pre_built_prompt 不为 None，直接用它替代模板渲染结果。"
            )
        raise

    # ── ATL执行 + status判定 ───────────────────────────────────────────────
    from src.executor.transformation_executor import run_transformation
    from src.analyzer.coverage_analyzer import compute_rule_coverage
    atl_path_str = str(ds["dataset_dir"] / ds["atl_file"])
    for pair in generation_results:
        if pair.get("generation_failure"):
            pair.update({
                "exec_success": False,
                "rule_coverage": "",
                "rules_covered": "",
                "rules_total": "",
            })
            continue

        idx        = pair["index"]
        out_path   = str(trans_dir / f"output_{idx}.xmi")
        exec_res   = run_transformation(pair["source"], out_path, ds["atl_name"], exec_cfg)
        trace_path = exec_res.get("trace") or out_path.replace(".xmi", "_trace.xmi")
        if exec_res["success"] and os.path.isfile(trace_path):
            cov = compute_rule_coverage(trace_path, atl_path_str)
            pair.update({"status":"OK","exec_success":True,
                         "rule_coverage":cov["rule_coverage"],
                         "rules_covered":cov["covered_rules"],
                         "rules_total":cov["total_rules"]})
        else:
            pair.update({"status":"ATL_EXEC_FAIL","exec_success":False,
                         "rule_coverage":"","rules_covered":"","rules_total":""})

    # 统计 validity
    n_ok     = sum(1 for r in generation_results if r.get("status") == "OK")
    n_total  = len(generation_results)
    val_rate = n_ok / n_total if n_total > 0 else 0.0
    val_note = ""

    # Fix #5：pilot 是独立步骤，不自动触发全量
    if pilot:
        pilot_min_validity = ds.get("pilot_min_validity", 0.10)
        if val_rate < pilot_min_validity:
            val_note = "low_validity_sample_limited"
            logger.warning(
                f"  pilot validity={val_rate:.1%} < {pilot_min_validity:.0%} → "
                f"标注 'low_validity_sample_limited'。\n"
                f"  全量 100 个仍需手动触发（去掉 --pilot 标志重新跑）。"
            )
        else:
            val_note = "pilot_ok"
            logger.info(
                f"  pilot validity={val_rate:.1%} ≥ {pilot_min_validity:.0%}。\n"
                f"  可启动全量：去掉 --pilot 标志重新跑。"
            )

    # Write the per-attempt CSV.
    if csv_path:
        for r in generation_results:
            append_result(csv_path, {
                "timestamp":         datetime.now().isoformat(),
                "provider":          provider,
                "condition":         condition,
                "dataset":           dataset_name,
                "model_id":          r.get("index", ""),
                "status":            r.get("status", ""),
                "valid":             1 if r.get("status") == "OK" else 0,
                "kill_rate":         r.get("kill_rate", ""),
                "mutants_killed":    r.get("mutants_killed", ""),
                "mutants_total":     r.get("mutants_total", ""),
                "rules_covered":     r.get("rules_covered", ""),
                "rules_total":       r.get("rules_total", ""),
                "rule_coverage":     r.get("rule_coverage", ""),
                
                "prompt_lines":      meta["prompt_lines"],
                
                "ocl_n_constraints": meta.get("ocl_n_constraints", 0),
                "components":        "|".join(meta["components"]),
                "validity_note":     val_note,
            })

    logger.info(f"  完成: {n_ok}/{n_total} valid ({val_rate:.1%})")
    return {
        "status":      "done",
        "n_ok":        n_ok,
        "n_total":     n_total,
        "val_rate":    val_rate,
        "val_note":    val_note,
        
        "meta":        meta,
    }


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="四档 prompt 阶梯实验")
    parser.add_argument("--provider", choices=list(PROVIDERS.keys()))
    parser.add_argument("--condition", choices=CONDITIONS)
    parser.add_argument("--datasets", nargs="+",
                        default=list(DATASETS.keys()),
                        choices=list(DATASETS.keys()))
    parser.add_argument("--n-models", type=int, default=100)
    parser.add_argument('--prompt-version', choices=('formal', *PROMPT_VERSIONS), default='latest',
                        help='formal selects and verifies the canonical frozen prompt per subject/condition')
    parser.add_argument("--all-conditions", action="store_true",
                        help="跑每个 subject 支持的全部档位（需指定 --provider）")
    parser.add_argument("--all-providers", action="store_true",
                        help="跑全部三个 provider（需指定 --condition）")
    parser.add_argument("--pilot", action="store_true",
                        help="pilot 模式：只生成 10 个/cell，独立步骤，不自动触发全量")
    parser.add_argument("--pilot-only", action="store_true",
                        help="sm 档 pilot，所有 provider 和 dataset")
    parser.add_argument("--output-dir", default=None,
                        help="结果根目录（默认 results_v3/）")
    global RESULTS_DIR
    args = parser.parse_args()
    RESULTS_DIR = Path(args.output_dir) if args.output_dir else RESULTS_DIR

    # run 级审计：调用日志落点 + 价格快照（费用核算与复现性留痕）
    from src.llm import call_logger
    call_logger.configure(run_meta={
        "script":      "run_ladder_experiment.py",
        "results_dir": str(RESULTS_DIR),
        "n_models":    args.n_models,
        "pilot":       args.pilot,
    })
    call_logger.write_pricing_snapshot()

    providers  = list(PROVIDERS.keys()) if args.all_providers  else ([args.provider] if args.provider else None)
    conditions = CONDITIONS             if args.all_conditions  else ([args.condition] if args.condition else None)

    if args.pilot_only:
        providers  = list(PROVIDERS.keys())
        conditions = ["sm"]
        args.pilot = True

    if not providers:
        parser.error("请指定 --provider 或使用 --all-providers / --pilot-only")
    if not conditions:
        parser.error("请指定 --condition 或使用 --all-conditions / --pilot-only")

    logger.info("实验矩阵:")
    logger.info(f"  providers:  {providers}")
    logger.info(f"  conditions: {conditions}")
    logger.info(f"  datasets:   {args.datasets}")
    logger.info(f"  n_models:   {args.n_models}")
    logger.info(f"  pilot:      {args.pilot}")
    total_cells = sum(
        condition in DATASETS[dataset].get("conditions", CONDITIONS)
        for provider in providers
        for condition in conditions
        for dataset in args.datasets
    )
    logger.info(f"  total cells: {total_cells}")

    summary = []
    for provider in providers:
        provider_short = provider.replace("-flash", "")
        csv_path = RESULTS_DIR / provider_short / "multi_config_results.csv"
        for condition in conditions:
            for dataset in args.datasets:
                if condition not in DATASETS[dataset].get("conditions", CONDITIONS):
                    logger.info(f"  skip unsupported cell: {dataset} / {condition}")
                    continue
                result = run_cell(
                    provider     = provider,
                    condition    = condition,
                    dataset_name = dataset,
                    n_models     = args.n_models,
                    pilot        = args.pilot,
                    csv_path     = csv_path,
                    prompt_version = args.prompt_version,
                )
                summary.append({"provider": provider, "condition": condition,
                                 "dataset": dataset, **result})

    logger.info("\n" + "="*60)
    logger.info("汇总:")
    for s in summary:
        if s.get("status") == "done":
            logger.info(
                f"  {s['provider']:15s} {s['condition']:6s} {s['dataset']:20s} "
                f"valid={s.get('n_ok',0)}/{s.get('n_total',0)} "
                f"({s.get('val_rate',0):.1%})"
            )
        else:
            logger.info(
                f"  {s['provider']:15s} {s['condition']:6s} {s['dataset']:20s} "
                f"status={s.get('status','?')}"
            )


if __name__ == "__main__":
    main()
