# src/experiment/config_registry.py

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class ExperimentConfig:
    """Complete specification for one experiment run."""

    # ── Identity ──────────────────────────────────────────────────────────────
    config_id:    str
    name:         str
    rq:           str
    group:        str

    # ── Prompt ────────────────────────────────────────────────────────────────
    prompt_config: str
    llm_provider:  str = "deepseek"

    # ── Generation loop ───────────────────────────────────────────────────────
    use_coverage_guidance: bool = True
    verify_coverage:       bool = True
    enable_repair:         bool = True
    fl_aware_feedback:     bool = False
    mixed_mode_feedback:   bool = False
    sat_aware_feedback:    bool = False   # NEW: saturation-aware distribution control
    source_only_context:   bool = False   # NEW: source metamodel + source examples only
    no_ocl:                bool = False   # NEW: omit OCL constraints from prompt
    no_atl:                bool = False   # NEW: omit ATL code from prompt
    no_atl:                bool = False   # NEW: omit ATL code from prompt

    # ── Experiment scale ──────────────────────────────────────────────────────
    n_models:     int  = 10
    run_mutation: bool = True

    # ── Datasets ──────────────────────────────────────────────────────────────
    datasets: List[str] = field(default_factory=lambda: ["BibTeX2DocBook"])

    # ── Notes ─────────────────────────────────────────────────────────────────
    description: str = ""
    hypothesis:  str = ""


# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict = {}


def register(cfg: ExperimentConfig) -> None:
    _REGISTRY[cfg.config_id] = cfg


# ── Proposed method ───────────────────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "PROPOSED_core",
    name                  = "Proposed: Coverage-Guided LLM (core)",
    rq                    = "RQ1,RQ2,RQ3,RQ5",
    group                 = "PROPOSED",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 10,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    description           = "Full proposed method: feedback loop + ATL verification + repair",
    hypothesis            = "LLM with coverage guidance significantly outperforms random",
))

register(ExperimentConfig(
    config_id             = "PROPOSED_cot",
    name                  = "Proposed: Coverage-Guided LLM (CoT)",
    rq                    = "RQ6",
    group                 = "PROPOSED",
    prompt_config         = "cot",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "CoT variant of proposed method",
    hypothesis            = "CoT improves coverage and kill rate over core",
))

register(ExperimentConfig(
    config_id             = "PROPOSED_100",
    name                  = "Proposed: 100 Models for SBFL Comparison",
    rq                    = "SBFL",
    group                 = "PROPOSED",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "100-model run for fair SBFL comparison",
    hypothesis            = "LLM 100 models achieves comparable EXAM score to SBFL 100 scenarios",
))

register(ExperimentConfig(
    config_id             = "PROPOSED_100_all",
    name                  = "Proposed: 100 Models for All Datasets SBFL",
    rq                    = "SBFL",
    group                 = "PROPOSED",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER", "CPL2SPL", "Ecore2Maude"],
    description           = "100-model run for fair SBFL comparison on all datasets",
    hypothesis            = "LLM 100 models achieves comparable EXAM score to SBFL 100 scenarios",
))

# ── B1: Random / Naive Baselines ─────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "ABL_random",
    name                  = "B1: Random Model Generator",
    rq                    = "RQ2",
    group                 = "B1",
    prompt_config         = "core",
    use_coverage_guidance = False,
    verify_coverage       = False,
    enable_repair         = False,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 10,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    description           = "Random XMI generation — lower bound baseline",
    hypothesis            = "Random significantly underperforms LLM",
))

# ── B3: LLM Baselines ────────────────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "ABL_no_feedback",
    name                  = "B3.1: Direct LLM Generation (No Loop)",
    rq                    = "RQ2,RQ6",
    group                 = "B3",
    prompt_config         = "core",
    use_coverage_guidance = False,
    verify_coverage       = False,
    enable_repair         = False,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    description           = "LLM generates once, no feedback loop, no coverage guidance.",
    hypothesis            = "Without feedback loop, coverage and kill rate are significantly lower",
))

register(ExperimentConfig(
    config_id             = "ABL_cot_no_feedback",
    name                  = "B3.3: CoT without Coverage Guidance",
    rq                    = "RQ6",
    group                 = "B3",
    prompt_config         = "cot",
    use_coverage_guidance = False,
    verify_coverage       = False,
    enable_repair         = False,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "CoT prompt but no coverage feedback.",
    hypothesis            = "CoT alone does not explain performance gain — feedback loop is key",
))

# ── B4: Ablation Baselines ───────────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "ABL_no_coverage_guidance",
    name                  = "B4.1: No Coverage Guidance",
    rq                    = "RQ6",
    group                 = "B4",
    prompt_config         = "core",
    use_coverage_guidance = False,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "Coverage guidance disabled but ATL verification kept.",
    hypothesis            = "Without coverage guidance, coverage converges slower",
))

register(ExperimentConfig(
    config_id             = "ABL_no_repair",
    name                  = "B4.3: No Adaptive Repair",
    rq                    = "RQ4",
    group                 = "B4",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = False,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "Ecore2Maude"],
    description           = "Adaptive repair disabled.",
    hypothesis            = "Without repair, execution rate drops for CPL2SPL and Ecore2Maude",
))

register(ExperimentConfig(
    config_id             = "ABL_no_atl",
    name                  = "B4.5: No ATL Code in Prompt (zero_shot)",
    rq                    = "RQ6",
    group                 = "B4",
    prompt_config         = "zero_shot",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    description           = "ATL code removed from prompt (equivalent to zero_shot).",
    hypothesis            = "Without ATL code, oracle accuracy drops to 0%",
))

# ── Qwen对比实验 ──────────────────────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "QWEN_core",
    name                  = "Qwen: Coverage-Guided (core)",
    rq                    = "RQ1,RQ2,RQ5",
    group                 = "QWEN",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    llm_provider          = "qwen",
    description           = "Qwen-Max版本，用于与DeepSeek对比验证方法通用性",
    hypothesis            = "Qwen生成的测试模型质量与DeepSeek相当",
))

# ── FL-aware strict ───────────────────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "FL_AWARE_cpl",
    name                  = "FL-Aware Strict: CPL2SPL",
    rq                    = "RQ_SBFL",
    group                 = "FL_AWARE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "Strict FL-aware: single mode, minimal models, no kill-rate push.",
    hypothesis            = "Strict FL-aware reduces fail_ratio but kill_rate drops to ~30%",
))

register(ExperimentConfig(
    config_id             = "FL_AWARE_bibtex",
    name                  = "FL-Aware Strict: BibTeX2DocBook",
    rq                    = "RQ_SBFL",
    group                 = "FL_AWARE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "Strict FL-aware: BibTeX2DocBook variant.",
    hypothesis            = "Strict FL-aware reduces fail_ratio and improves EXAM at cost of kill_rate",
))

register(ExperimentConfig(
    config_id             = "FL_AWARE_uml",
    name                  = "FL-Aware Strict: UML2ER",
    rq                    = "RQ_SBFL",
    group                 = "FL_AWARE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER"],
    description           = "100-model strict FL-aware for UML2ER.",
    hypothesis            = "Strict FL-aware lower bound on UML2ER",
))

# ── Mixed-mode feedback ───────────────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "MIXED_MODE_cpl",
    name                  = "Mixed-Mode Feedback: CPL2SPL",
    rq                    = "RQ_SBFL",
    group                 = "MIXED_MODE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "Three-mode mixed strategy on CPL2SPL: B=36, M=33, S=31.",
    hypothesis            = "Mixed-mode achieves kill_rate >50% while improving Ochiai EXAM AC",
))

register(ExperimentConfig(
    config_id             = "MIXED_MODE_bibtex",
    name                  = "Mixed-Mode Feedback: BibTeX2DocBook",
    rq                    = "RQ_SBFL",
    group                 = "MIXED_MODE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "Three-mode mixed strategy on BibTeX2DocBook.",
    hypothesis            = "Mixed-mode improves EXAM toward 0.188 while keeping kill_rate >70%",
))

register(ExperimentConfig(
    config_id             = "MIXED_MODE_uml",
    name                  = "Mixed-Mode Feedback: UML2ER",
    rq                    = "RQ_SBFL",
    group                 = "MIXED_MODE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER"],
    description           = "100-model mixed-mode for UML2ER.",
    hypothesis            = "Mixed-mode generalises to UML2ER: EXAM improves, kill_rate acceptable",
))

register(ExperimentConfig(
    config_id             = "FL_AWARE_ecore",
    name                  = "FL-Aware Strict: Ecore2Maude",
    rq                    = "RQ_SBFL",
    group                 = "FL_AWARE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["Ecore2Maude"],
    description           = "100-model strict FL-aware for Ecore2Maude.",
    hypothesis            = "Strict FL-aware on Ecore2Maude: saturation expected",
))
register(ExperimentConfig(
    config_id             = "MIXED_MODE_ecore",
    name                  = "Mixed-Mode Feedback: Ecore2Maude",
    rq                    = "RQ_SBFL",
    group                 = "MIXED_MODE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["Ecore2Maude"],
    description           = "100-model mixed-mode for Ecore2Maude.",
    hypothesis            = "Mixed-mode on Ecore2Maude: saturation expected",
))

# ── Sanity test configs ───────────────────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "SANITY_baseline",
    name                  = "Sanity Test: Detection-Oriented Baseline (CPL2SPL, n=30)",
    rq                    = "RQ_SANITY",
    group                 = "SANITY",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 30,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "30-model detection-oriented baseline for sanity comparison.",
    hypothesis            = "Baseline sets the reference kill_rate and EXAM level",
))

register(ExperimentConfig(
    config_id             = "SANITY_fl_strict",
    name                  = "Sanity Test: Strict FL-Aware (CPL2SPL, n=30)",
    rq                    = "RQ_SANITY",
    group                 = "SANITY",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 30,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "30-model strict FL-aware for sanity comparison.",
    hypothesis            = "Strict FL-aware reduces kill_rate and fail_ratio; EXAM may improve",
))

register(ExperimentConfig(
    config_id             = "SANITY_mixed",
    name                  = "Sanity Test: Mixed-Mode (CPL2SPL, n=30)",
    rq                    = "RQ_SANITY",
    group                 = "SANITY",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 30,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "30-model mixed-mode for sanity comparison.",
    hypothesis            = "Mixed-mode balances kill_rate and EXAM between baseline and strict FL-aware",
))

# ── Full 100-model comparison configs ─────────────────────────────────────────

register(ExperimentConfig(
    config_id             = "FULL_baseline_cpl",
    name                  = "Full 100: Detection-Oriented Baseline (CPL2SPL)",
    rq                    = "RQ_SBFL",
    group                 = "FULL",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "100-model detection-oriented baseline for CPL2SPL.",
    hypothesis            = "Baseline reference for EXAM and kill_rate on CPL2SPL",
))

register(ExperimentConfig(
    config_id             = "FULL_fl_strict_cpl",
    name                  = "Full 100: Strict FL-Aware (CPL2SPL)",
    rq                    = "RQ_SBFL",
    group                 = "FULL",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "100-model strict FL-aware for CPL2SPL.",
    hypothesis            = "Strict FL-aware lower bound: best EXAM, lowest kill_rate",
))

register(ExperimentConfig(
    config_id             = "FULL_mixed_cpl",
    name                  = "Full 100: Mixed-Mode (CPL2SPL)",
    rq                    = "RQ_SBFL",
    group                 = "FULL",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = "100-model mixed-mode for CPL2SPL.",
    hypothesis            = "Mixed-mode: EXAM close to strict, kill_rate close to baseline",
))

register(ExperimentConfig(
    config_id             = "FULL_baseline_uml",
    name                  = "Full 100: Detection-Oriented Baseline (UML2ER)",
    rq                    = "RQ_SBFL",
    group                 = "FULL",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER"],
    description           = "100-model detection-oriented baseline for UML2ER.",
    hypothesis            = "Baseline reference for EXAM and kill_rate on UML2ER",
))

register(ExperimentConfig(
    config_id             = "FULL_fl_strict_uml",
    name                  = "Full 100: Strict FL-Aware (UML2ER)",
    rq                    = "RQ_SBFL",
    group                 = "FULL",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER"],
    description           = "100-model strict FL-aware for UML2ER.",
    hypothesis            = "Strict FL-aware lower bound on UML2ER",
))

register(ExperimentConfig(
    config_id             = "FULL_mixed_uml",
    name                  = "Full 100: Mixed-Mode (UML2ER)",
    rq                    = "RQ_SBFL",
    group                 = "FULL",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER"],
    description           = "100-model mixed-mode for UML2ER.",
    hypothesis            = "Mixed-mode generalises to UML2ER",
))

# ── SAT_AWARE: Saturation-Aware Distribution Control ─────────────────────────
#
# New strategy that tracks execution profiles across generated models and
# injects saturation-aware hints to:
#   1. Avoid repeating frequent rule combinations
#   2. Avoid failure saturation (fail_ratio → 1)
#   3. Preserve aggregate coverage while increasing coverage variance
#   4. Improve SBFL WC stability without sacrificing kill_rate excessively
#
# Pilot datasets: CPL2SPL (primary) and BibTeX2DocBook (secondary)
# Pilot size: 30 models (fast validation before committing to 100)
#
# Output directories follow standard convention:
#   results/generated_models/{dataset}/SAT_AWARE_{suffix}/
#   results/outputs/{dataset}/SAT_AWARE_{suffix}/
# Current fresh-run spectra are exported by code/run_pipeline.py.

register(ExperimentConfig(
    config_id             = "SAT_AWARE_cpl",
    name                  = "SAT_AWARE: CPL2SPL (pilot, n=30)",
    rq                    = "RQ_SBFL",
    group                 = "SAT_AWARE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = True,
    n_models              = 30,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = (
        "Saturation-aware pilot on CPL2SPL (30 models).  "
        "Tracks execution profiles, avoids failure saturation, "
        "increases coverage variance."
    ),
    hypothesis            = (
        "SAT_AWARE achieves lower fail_ratio than core (target <0.5), "
        "higher CovStd than FL_AWARE, and Ochiai_WC < core WC (0.466)"
    ),
))

register(ExperimentConfig(
    config_id             = "SAT_AWARE_bibtex",
    name                  = "SAT_AWARE: BibTeX2DocBook (pilot, n=30)",
    rq                    = "RQ_SBFL",
    group                 = "SAT_AWARE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = True,
    n_models              = 30,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = (
        "Saturation-aware pilot on BibTeX2DocBook (30 models).  "
        "Tests whether profile-tracking can break the fail saturation "
        "seen with core (fail_ratio=0.882)."
    ),
    hypothesis            = (
        "SAT_AWARE reduces fail_ratio below 0.7 and improves Ochiai_WC "
        "compared to core (WC=0.531)"
    ),
))

register(ExperimentConfig(
    config_id             = "SAT_AWARE_cpl_100",
    name                  = "SAT_AWARE: CPL2SPL (full, n=100)",
    rq                    = "RQ_SBFL",
    group                 = "SAT_AWARE",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = True,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL"],
    description           = (
        "Full 100-model SAT_AWARE run on CPL2SPL.  "
        "Run only after pilot (SAT_AWARE_cpl) confirms positive trend."
    ),
    hypothesis            = (
        "SAT_AWARE 100-model: lower fail_ratio than MIXED_MODE, "
        "comparable or better Ochiai_AC, higher CovStd"
    ),
))


# ── API ───────────────────────────────────────────────────────────────────────

def get_config(config_id: str) -> ExperimentConfig:
    if config_id not in _REGISTRY:
        raise ValueError(f"Unknown config_id: '{config_id}'. "
                         f"Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[config_id]


def list_configs(group: str = None) -> list:
    configs = list(_REGISTRY.values())
    if group:
        configs = [c for c in configs if c.group == group]
    return configs


def print_registry() -> None:
    print(f"\n{'='*75}")
    print(f"{'ID':<28} {'Group':<12} {'RQ':<12} {'Name'}")
    print("-" * 75)
    for cfg in _REGISTRY.values():
        print(f"{cfg.config_id:<28} {cfg.group:<12} {cfg.rq:<12} {cfg.name}")
    print("=" * 75)


if __name__ == "__main__":
    print_registry()
    print("\n--- SAT_AWARE configs ---")
    for cfg in list_configs("SAT_AWARE"):
        print(f"\n  {cfg.config_id}")
        print(f"    sat_aware_feedback: {cfg.sat_aware_feedback}")
        print(f"    n_models:           {cfg.n_models}")
        print(f"    hypothesis: {cfg.hypothesis}")
# ── Source-only context pilot ─────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "PILOT_source_only_bibtex",
    name                  = "Pilot: Source-only context (BibTeX2DocBook, n=30)",
    rq                    = "RQ_PILOT",
    group                 = "PILOT",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    source_only_context   = True,
    n_models              = 30,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "Pilot: no target metamodel, no example target models.",
    hypothesis            = "Source-only context reduces fail_ratio vs full context core",
))

# ── No OCL pilot ──────────────────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "PILOT_no_ocl_bibtex",
    name                  = "Pilot: No OCL in prompt (BibTeX2DocBook, n=30)",
    rq                    = "RQ_PILOT",
    group                 = "PILOT",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    source_only_context   = False,
    no_ocl                = True,
    n_models              = 30,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook"],
    description           = "Pilot: OCL removed from prompt, all other components kept.",
    hypothesis            = "OCL removal does not significantly affect kill rate or SBFL",
))

# ── ABL_no_target_context ─────────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "ABL_no_target_context",
    name                  = "Ablation: No target context (source MM + ATL + source examples only)",
    rq                    = "RQ_ABL",
    group                 = "ABLATION",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    source_only_context   = True,
    no_ocl                = True,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    description           = "Removes all target semantic context: no target MM, no OCL, no example target models.",
    hypothesis            = "Removing all target context degrades SBFL due to homogeneous model generation",
))
# ── 临时续跑 config ────────────────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "ABL_no_target_context_RESUME",
    name                  = "ABL_no_target_context: resume UML2ER + Ecore2Maude",
    rq                    = "RQ_ABL",
    group                 = "ABLATION",
    prompt_config         = "core",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    source_only_context   = True,
    no_ocl                = True,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER", "Ecore2Maude"],
    description           = "Resume only",
    hypothesis            = "",
))

register(ExperimentConfig(
    config_id             = "ABL_no_feedback_RESUME",
    name                  = "ABL_no_feedback: resume UML2ER + Ecore2Maude",
    rq                    = "RQ_ABL",
    group                 = "ABLATION",
    prompt_config         = "core",
    use_coverage_guidance = False,
    verify_coverage       = False,
    enable_repair         = False,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["UML2ER", "Ecore2Maude"],
    description           = "Resume only",
    hypothesis            = "",
))

register(ExperimentConfig(
    config_id             = "ABL_no_atl_RESUME",
    name                  = "ABL_no_atl: resume CPL2SPL + UML2ER + Ecore2Maude",
    rq                    = "RQ_ABL",
    group                 = "ABLATION",
    prompt_config         = "zero_shot",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL", "UML2ER", "Ecore2Maude"],
    description           = "Resume only",
    hypothesis            = "",
))

# ── QWEN 并行跑 ──────────────────────────────────────────────────────────────
for _ds in ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"]:
    register(ExperimentConfig(
        config_id             = f"QWEN_core_{_ds}",
        name                  = f"Qwen core: {_ds}",
        rq                    = "RQ1,RQ2,RQ5",
        group                 = "QWEN",
        prompt_config         = "core",
        use_coverage_guidance = True,
        verify_coverage       = True,
        enable_repair         = True,
        fl_aware_feedback     = False,
        mixed_mode_feedback   = False,
        sat_aware_feedback    = False,
        n_models              = 100,
        run_mutation          = True,
        datasets              = [_ds],
        llm_provider          = "qwen",
        description           = f"Qwen core on {_ds} only",
        hypothesis            = "",
    ))

# ── QWEN FL_AWARE + MIXED_MODE（跨模型验证，对标 DeepSeek FL_AWARE / MIXED_MODE）──
_QWEN_VARIANT_SUFFIX = {
    "CPL2SPL":        "cpl",
    "UML2ER":         "uml",
    "BibTeX2DocBook": "bibtex",
    "Ecore2Maude":    "ecore",
}
 
for _ds, _sfx in _QWEN_VARIANT_SUFFIX.items():
    register(ExperimentConfig(
        config_id             = f"QWEN_fl_aware_{_ds}",
        name                  = f"Qwen FL-Aware Strict: {_ds}",
        rq                    = "RQ_SBFL",
        group                 = "QWEN",
        prompt_config         = "core",
        use_coverage_guidance = True,
        verify_coverage       = True,
        enable_repair         = True,
        fl_aware_feedback     = True,
        mixed_mode_feedback   = False,
        sat_aware_feedback    = False,
        n_models              = 100,
        run_mutation          = True,
        datasets              = [_ds],
        llm_provider          = "qwen",
        description           = f"Qwen FL-Aware strict on {_ds}, mirrors FL_AWARE_{_sfx}",
        hypothesis            = "Qwen FL-Aware achieves similar EXAM improvement as DeepSeek FL-Aware",
    ))
 
for _ds, _sfx in _QWEN_VARIANT_SUFFIX.items():
    register(ExperimentConfig(
        config_id             = f"QWEN_mixed_{_ds}",
        name                  = f"Qwen Mixed-Mode: {_ds}",
        rq                    = "RQ_SBFL",
        group                 = "QWEN",
        prompt_config         = "core",
        use_coverage_guidance = True,
        verify_coverage       = True,
        enable_repair         = True,
        fl_aware_feedback     = False,
        mixed_mode_feedback   = True,
        sat_aware_feedback    = False,
        n_models              = 100,
        run_mutation          = True,
        datasets              = [_ds],
        llm_provider          = "qwen",
        description           = f"Qwen Mixed-Mode on {_ds}, mirrors MIXED_MODE_{_sfx}",
        hypothesis            = "Qwen Mixed-Mode balances kill_rate and EXAM comparable to DeepSeek",
    ))
# ── GPT (OpenAI via agicto) ───────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "GPT_core",
    name                  = "GPT-5.1: Coverage-Guided (core)",
    rq                    = "RQ1,RQ2,RQ5",
    group                 = "GPT",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    llm_provider          = "openai",
    description           = "GPT-5.1 via agicto，用于跨模型验证",
    hypothesis            = "GPT-5.1 core achieves comparable SBFL performance to DeepSeek core",
))

register(ExperimentConfig(
    config_id             = "GPT_fl_aware",
    name                  = "GPT-5.1: FL-Aware",
    rq                    = "RQ_SBFL",
    group                 = "GPT",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    llm_provider          = "openai",
    description           = "GPT-5.1 FL-Aware，跨模型验证 FL 效果",
    hypothesis            = "GPT-5.1 FL-Aware improves SBFL over GPT core",
))

register(ExperimentConfig(
    config_id             = "GPT_mixed",
    name                  = "GPT-5.1: Mixed-Mode",
    rq                    = "RQ_SBFL",
    group                 = "GPT",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    llm_provider          = "openai",
    description           = "GPT-5.1 Mixed-Mode，跨模型验证",
    hypothesis            = "GPT-5.1 Mixed-Mode balances kill_rate and EXAM",
))

# ── DeepSeek v2 (source-only prompt, 新版主实验) ──────────────────────────────
register(ExperimentConfig(
    config_id             = "DeepSeek_core_v2",
    name                  = "DeepSeek: core v2 (source-only prompt)",
    rq                    = "RQ1,RQ2,RQ5",
    group                 = "DEEPSEEK_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    llm_provider          = "deepseek-flash",
    description           = "DeepSeek core 重跑版，使用 source-only prompt v2",
    hypothesis            = "Source-only prompt achieves comparable SBFL to original core",
))

register(ExperimentConfig(
    config_id             = "DeepSeek_fl_aware_v2",
    name                  = "DeepSeek: FL-Aware v2 (source-only prompt)",
    rq                    = "RQ_SBFL",
    group                 = "DEEPSEEK_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    llm_provider          = "deepseek-flash",
    description           = "DeepSeek FL-Aware 重跑版，source-only prompt v2",
    hypothesis            = "FL-Aware improves SBFL over core v2",
))

register(ExperimentConfig(
    config_id             = "DeepSeek_mixed_v2",
    name                  = "DeepSeek: Mixed-Mode v2 (source-only prompt)",
    rq                    = "RQ_SBFL",
    group                 = "DEEPSEEK_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    llm_provider          = "deepseek-flash",
    description           = "DeepSeek Mixed-Mode 重跑版，source-only prompt v2",
    hypothesis            = "Mixed-Mode v2 balances kill_rate and EXAM",
))

# ── QWEN v2 (source-only prompt) ─────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "QWEN_core_v2",
    name                  = "QWEN: core v2 (source-only prompt)",
    rq                    = "RQ1,RQ2,RQ5",
    group                 = "QWEN_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"],
    llm_provider          = "qwen",
    description           = "QWEN core 重跑版，使用 source-only prompt v2",
    hypothesis            = "QWEN core_v2 achieves comparable SBFL to DeepSeek core_v2",
))

# ── Mechanism Verification: Condition C ──────────────────────────────────────
# 条件C：source-only prompt v2 + safety note + 要求输出 target（但框架只用 source）
# 用于验证 planning scaffold 机制：target prediction 是否是新旧版差异的来源
register(ExperimentConfig(
    config_id             = "QWEN_cpl_condC",
    name                  = "QWEN: CPL2SPL Condition C (with-target prompt, source-only use)",
    rq                    = "RQ_mech",
    group                 = "MECHANISM_VERIFY",
    datasets              = ["CPL2SPL"],
    prompt_config         = "core_v2_with_target",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    llm_provider          = "qwen",
    description           = "机制验证条件C：prompt要求生成target但框架忽略，隔离planning scaffold效应",
))

# ── 消融实验 v2 ───────────────────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "ABL_v2_no_atl",
    name                  = "Ablation v2: No ATL code",
    rq                    = "RQ_ABL",
    group                 = "ABL_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    no_ocl                = False,
    no_atl                = True,
    source_only_context   = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    llm_provider          = "deepseek",
    description           = "去掉ATL代码，其他与core_v2完全一致",
    hypothesis            = "Removing ATL code degrades source model quality and SBFL",
))

register(ExperimentConfig(
    config_id             = "ABL_v2_no_target",
    name                  = "Ablation v2: No target context",
    rq                    = "RQ_ABL",
    group                 = "ABL_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    no_ocl                = False,
    no_atl                = False,
    source_only_context   = True,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    llm_provider          = "deepseek",
    description           = "去掉target metamodel context，其他与core_v2完全一致",
    hypothesis            = "Target context has non-uniform effect on source model generation",
))

register(ExperimentConfig(
    config_id             = "ABL_v2_no_coverage",
    name                  = "Ablation v2: No coverage guidance",
    rq                    = "RQ_ABL",
    group                 = "ABL_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = False,
    verify_coverage       = False,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    no_ocl                = False,
    no_atl                = False,
    source_only_context   = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    llm_provider          = "deepseek",
    description           = "去掉coverage guidance，其他与core_v2完全一致",
    hypothesis            = "Coverage guidance improves rule coverage and mutation adequacy",
))

register(ExperimentConfig(
    config_id             = "ABL_v2_no_ocl",
    name                  = "Ablation v2: No OCL constraints",
    rq                    = "RQ_ABL",
    group                 = "ABL_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    no_ocl                = True,
    no_atl                = False,
    source_only_context   = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["BibTeX2DocBook", "UML2ER", "CPL2SPL", "Ecore2Maude"],
    llm_provider          = "deepseek",
    description           = "去掉OCL约束，其他与core_v2完全一致",
    hypothesis            = "OCL constraints improve source model validity rate",
))

# ── GPT 三主条件 ──────────────────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "GPT_fl_aware_v2",
    name                  = "GPT-5.1: FL-Aware v2",
    rq                    = "RQ_SBFL",
    group                 = "GPT_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL", "UML2ER"],
    llm_provider          = "openai",
    description           = "GPT-5.1 FL-Aware v2",
    hypothesis            = "GPT FL-Aware improves SBFL over GPT core",
))

register(ExperimentConfig(
    config_id             = "GPT_mixed_v2",
    name                  = "GPT-5.1: Mixed-Mode v2",
    rq                    = "RQ_SBFL",
    group                 = "GPT_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL", "UML2ER"],
    llm_provider          = "openai",
    description           = "GPT-5.1 Mixed-Mode v2",
    hypothesis            = "GPT Mixed-Mode balances kill_rate and EXAM",
))

# ── QWEN 三主条件 ─────────────────────────────────────────────────────────────
register(ExperimentConfig(
    config_id             = "QWEN_fl_aware_v2",
    name                  = "QWEN: FL-Aware v2",
    rq                    = "RQ_SBFL",
    group                 = "QWEN_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = True,
    mixed_mode_feedback   = False,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL", "UML2ER"],
    llm_provider          = "qwen",
    description           = "QWEN FL-Aware v2",
    hypothesis            = "QWEN FL-Aware improves SBFL over QWEN core",
))

register(ExperimentConfig(
    config_id             = "QWEN_mixed_v2",
    name                  = "QWEN: Mixed-Mode v2",
    rq                    = "RQ_SBFL",
    group                 = "QWEN_V2",
    prompt_config         = "core_v2",
    use_coverage_guidance = True,
    verify_coverage       = True,
    enable_repair         = True,
    fl_aware_feedback     = False,
    mixed_mode_feedback   = True,
    sat_aware_feedback    = False,
    n_models              = 100,
    run_mutation          = True,
    datasets              = ["CPL2SPL", "UML2ER"],
    llm_provider          = "qwen",
    description           = "QWEN Mixed-Mode v2",
    hypothesis            = "QWEN Mixed-Mode balances kill_rate and EXAM",
))
