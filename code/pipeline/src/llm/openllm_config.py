"""
openllm_config.py — Open-source LLM provider registry, seed schedule, and
provenance contract for the OpenLLM ladder experiment extension.

Phase 1A: Configuration only. No model loading. No generation.
"""

import os
from pathlib import Path

# ── Root paths ──────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parents[2]
RESULTS_OPENLLM_DIR = ROOT / "results_openllm_v1"

# ── Model registry ──────────────────────────────────────────────────────────────

OPENLLM_MODELS = {
    "openllm:devstral": {
        "model_alias":          "devstral-24b",
        "ollama_name":          "devstral",
        "hf_gguf_repo":         "bartowski/mistralai_Devstral-Small-2-24B-Instruct-2512-GGUF",
        "hf_base_repo":         "mistralai/Devstral-Small-2-24B-Instruct-2512",
        "architecture":         "mistral3",
        "param_count":          "24B",
        "quantization":         "Q4_K_M",
        "gguf_filename":        "mistralai_Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf",
        "gguf_local_path":      "<old-machine>/local_llms/models/Devstral-Small-2-24B-Instruct-2512-GGUF/mistralai_Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf",
        
        "gguf_local_size":      14334438272,
        "gguf_hf_lfs_oid":      "TBD_HF_API_UNREACHABLE",
        "integrity_status":     "UNVERIFIED_PENDING_HF_LFS_OID",
        "context_size":         32768,
        "chat_template_source": "GGUF metadata (auto-detected by Ollama)",
        "chat_template_literal": "<s>[SYSTEM_PROMPT]{system_prompt}[/SYSTEM_PROMPT][INST]{prompt}[/INST]",
        "thinking_default":     "UNKNOWN",
        "license":              "Mistral Research License",
    },
    "openllm:gemma": {
        "model_alias":          "gemma-12b",
        "ollama_name":          "gemma",
        "hf_gguf_repo":         "bartowski/google_gemma-3-12b-it-GGUF",
        "hf_base_repo":         "google/gemma-3-12b-it",
        "architecture":         "gemma3",
        "param_count":          "12B",
        "quantization":         "Q4_K_M",
        "gguf_filename":        "google_gemma-3-12b-it-Q4_K_M.gguf",
        "gguf_local_path":      "<old-machine>/local_llms/models/Gemma-3-12B-IT-GGUF/google_gemma-3-12b-it-Q4_K_M.gguf",
        
        "gguf_local_size":      7300575264,
        "gguf_hf_lfs_oid":      "TBD_HF_API_UNREACHABLE",
        "integrity_status":     "INCOMPLETE_PART_FILE",
        "part_file_path":       "<old-machine>/local_llms/models/Gemma-3-12B-IT-GGUF/google_gemma-3-12b-it-Q4_K_M.gguf.part",
        "context_size":         32768,
        "chat_template_source": "GGUF metadata (auto-detected by Ollama)",
        "chat_template_literal": "<bos><start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n",
        "thinking_default":     "UNKNOWN",
        "license":              "gemma-3-license",
    },
    "openllm:glm": {
        "model_alias":          "glm-4.7f",
        "ollama_name":          "glm",
        "hf_gguf_repo":         "bartowski/zai-org_GLM-4.7-Flash-GGUF",
        "hf_base_repo":         "zai-org/GLM-4.7-Flash",
        "architecture":         "glm4",
        "param_count":          "~30B",
        "quantization":         "Q4_K_M",
        "gguf_filename":        "zai-org_GLM-4.7-Flash-Q4_K_M.gguf",
        "gguf_local_path":      "<old-machine>/local_llms/models/GLM-4.7-Flash-GGUF/GLM-4.7-Flash-Q4_K_M.gguf",
        
        "gguf_local_size":      18312339808,
        "gguf_hf_lfs_oid":      "TBD_HF_API_UNREACHABLE",
        "integrity_status":     "UNVERIFIED_PENDING_HF_LFS_OID",
        "context_size":         32768,
        "chat_template_source": "GGUF metadata (auto-detected by Ollama)",
        "chat_template_literal": "[gMASK]<sop><|system|>{system_prompt}<|user|>{prompt}<|assistant|><think>",
        "thinking_default":     "LIKELY_ENABLED",
        "thinking_disabled_via_template": True,
        "thinking_disable_note": "Modelfile TEMPLATE ends with <|assistant|>\\n instead of <|assistant|><think>. Rebuilt 2026-07-22.",
        "max_tokens_override":  16384,
        "max_tokens_note": "Raised from global 8192 to 16384. GLM-4.7-Flash with thinking disabled produces longer outputs on long prompts (CPL ASTMO ~23000 prompt tokens). Budget: 23000+16384=39384 > 32768 context — may still truncate on longest prompts.",
        "license":              "GLM-4 License",
    },
    "openllm:deepseek": {
        "model_alias":          "deepseek-coder-16b",
        "ollama_name":          "deepseek-coder",
        "hf_gguf_repo":         "bartowski/DeepSeek-Coder-V2-Lite-Instruct-GGUF",
        "hf_base_repo":         "deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct",
        "architecture":         "deepseek2",
        "param_count":          "15.7B",
        "quantization":         "Q4_K_M",
        "gguf_filename":        "DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf",
        "gguf_local_path":      "<old-machine>/local_llms/models/DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M/DeepSeek-Coder-V2-Lite-Instruct-Q4_K_M.gguf",
        
        "gguf_local_size":      10364416768,
        "gguf_hf_lfs_oid":      "TBD_HF_API_UNREACHABLE",
        "integrity_status":     "UNVERIFIED",
        "context_size":         49152,
        "chat_template_source": "GGUF metadata (auto-detected by Ollama)",
        "chat_template_literal": "DeepSeek V2 chat format (auto-detected)",
        "thinking_default":     "UNKNOWN",
        "license":              "DeepSeek License",
    },
}

# Explicit per-attempt seeds preserve the established sampling configuration.
def compute_seed(model_alias: str, subject: str, condition: str, attempt_id: int) -> int:
    """Read the configured seed for an experiment attempt (1 through 100)."""
    import json
    schedule = json.loads(Path(__file__).with_name('seed_schedule.json').read_text(encoding='utf-8'))
    if not 1 <= attempt_id <= 100:
        raise ValueError('The configured seed schedule covers attempts 1 through 100')
    return schedule[f'{model_alias}:{subject}:{condition}'][attempt_id - 1]

# ── Provider config entries for llm_client.py PROVIDER_CONFIGS ──────────────────

def get_openllm_provider_configs() -> dict:
    """Return dict suitable for merging into PROVIDER_CONFIGS in llm_client.py."""
    return {
        "openllm:devstral": {
            "url":         "http://localhost:11434/v1/chat/completions",
            "api_key":     "ollama",        # Ollama localhost ignores auth
            "model":       "devstral",
            "temperature": 0.2,
            "provider_type": "ollama_local",
        },
        "openllm:gemma": {
            "url":         "http://localhost:11434/v1/chat/completions",
            "api_key":     "ollama",
            "model":       "gemma",
            "temperature": 0.2,
            "provider_type": "ollama_local",
        },
        "openllm:glm": {
            "url":         "http://localhost:11434/v1/chat/completions",
            "api_key":     "ollama",
            "model":       "glm",
            "temperature": 0.2,
            "provider_type": "ollama_local",
        },
        "openllm:deepseek": {
            "url":         "http://localhost:11434/v1/chat/completions",
            "api_key":     "ollama",
            "model":       "deepseek-coder",
            "temperature": 0.2,
            "provider_type": "ollama_local",
        },
    }

# ── Sampling parameter contract ─────────────────────────────────────────────────
# Values classified as:
#   CODE_EXPLICIT       — exists in the running code (temperature=0.2)
#   NEW_OPENLLM_LOCKED  — set for open-LLM run, not present in original experiment
#   NOT_SET_IN_ORIGINAL — original had no code setting this; left at server default

SAMPLING_CONTRACT = {
    "temperature": {
        "value": 0.2,
        "classification": "CODE_EXPLICIT",
        "original_evidence": "src/llm/llm_client.py PROVIDER_CONFIGS — hardcoded for all providers",
        "ollama_param": "temperature",
        "ollama_api": "both /v1/chat/completions and /api/chat support this",
    },
    "top_p": {
        "value": 0.95,
        "classification": "NEW_OPENLLM_LOCKED_SETTING",
        "original_evidence": "NOT in original llm_client.py payload; original experiment used provider API defaults",
        "ollama_param": "top_p",
        "ollama_api": "both",
    },
    "top_k": {
        "value": 40,
        "classification": "NEW_OPENLLM_LOCKED_SETTING",
        "original_evidence": "NOT in original llm_client.py payload; original experiment used provider API defaults",
        "ollama_param": "top_k",
        "ollama_api": "both",
    },
    "min_p": {
        "value": None,
        "classification": "NOT_SET",
        "original_evidence": "NOT in original; no established default",
        "ollama_param": "min_p",
        "ollama_api": "both",
    },
    "repeat_penalty": {
        "value": 1.0,
        "classification": "NEW_OPENLLM_LOCKED_SETTING",
        "original_evidence": "NOT in original; 1.0 = disabled (safe default for XMI generation)",
        "ollama_param": "repeat_penalty",
        "ollama_api": "both",
    },
    "seed": {
        "value": "per-attempt deterministic (see compute_seed)",
        "classification": "NEW_OPENLLM_LOCKED_SETTING",
        "original_evidence": "NOT in original llm_client.py payload at all; original experiment had NO seed control",
        "ollama_param": "seed",
        "ollama_api": "both /v1/chat/completions (options.seed) and /api/chat (seed)",
    },
    "max_tokens": {
        "value": 8192,
        "classification": "NEW_OPENLLM_LOCKED_SETTING",
        "original_evidence": "NOT in original llm_client.py payload; original relied on provider max_output defaults",
        "calibration_note": "Raised from 4096 to 8192 (2026-07-22) after format probe revealed truncation on ASTMO CPL2SPL (Gemma: completion_tokens=4096, finish_reason=length). Applies uniformly to all open models, all subjects, all conditions.",
        "runtime_policy_version": "v2",
        "applies_to_all_open_models": True,
        "ollama_param": "max_tokens (v1) or num_predict (native)",
        "ollama_api": "both — max_tokens in OpenAI-compat, num_predict in native",
    },
    "context_size": {
        "value": 32768,
        "classification": "NEW_OPENLLM_LOCKED_SETTING",
        "original_evidence": "Original providers have undocumented context windows; 32K is safe floor",
        "ollama_param": "num_ctx (set at model level via Ollama Modelfile or server flag)",
        "ollama_api": "model-level only — cannot override per-request",
    },
    "stream": {
        "value": False,
        "classification": "NEW_OPENLLM_LOCKED_SETTING",
        "original_evidence": "Original used stream=True for connection stability with remote APIs; local Ollama doesn't need streaming",
        "ollama_param": "stream",
        "ollama_api": "both",
    },
}

# ── Provenance fields to record per generation attempt ──────────────────────────

PROVENANCE_FIELDS = [
    # Model identity
    "model_alias",
    "ollama_name",
    
    # Server identity
    "server_version",          # ollama --version
    # Prompt identity
    
    # Sampling parameters (all recorded, not assumed)
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "repeat_penalty",
    "seed",
    "max_tokens",
    "context_size",
    "stream",
    # Response metadata
    "prompt_eval_count",       # tokens in prompt (from Ollama response)
    "eval_count",              # tokens generated (from Ollama response)
    "total_duration_ms",       # wall-clock time for this call
    "load_duration_ms",        # model load time (first call only)
]

# ── CSV fieldnames for results_openllm_v1 ───────────────────────────────────────

OPENLLM_CSV_FIELDNAMES = [
    # Standard ladder fields (matching original experiment)
    "timestamp", "provider", "condition", "dataset", "model_id",
    "status", "valid", "kill_rate", "mutants_killed", "mutants_total",
    "rules_covered", "rules_total", "rule_coverage",
     "prompt_lines",
     "ocl_n_constraints", "components",
    "validity_note",
    # OpenLLM provenance extensions
    "model_alias",
    "ollama_name",
    
    "server_version",
    
    "temperature",
    "top_p",
    "top_k",
    "min_p",
    "repeat_penalty",
    "seed",
    "max_tokens",
    "context_size",
    "stream",
    "prompt_eval_count",
    "eval_count",
    "total_duration_ms",
    "load_duration_ms",
    
    
    # Raw response provenance
    "raw_response_path",
    "extracted_xmi_path",
    # Dual-pathway extraction (multi-metric framework)
    "strict_contract_status",
    "strict_failure_reason",
    "strict_extraction_path",
    
    "recovery_attempted",
    "recovery_rule",
    "recovery_status",
    "recovered_xmi_path",
    
    "recovered_xml_well_formed",
    "recovered_root_tag",
    "recovered_atl_runtime_status",
    "extraction_pathway",
    "primary_analysis_eligible",
    "sensitivity_analysis_eligible",
    
    
    # Gate / budget provenance
    "run_scope",
    "counts_toward_experiment_budget",
    # Context budget (Fix #6)
    "finish_reason",
    "prompt_tokens",
    "completion_tokens",
    "num_ctx",
    "context_overflow",
    "output_truncated",
]

# ── Subject/condition matrix (matches canonical 24-cell layout) ─────────────────

OPENLLM_SUBJECTS = {
    "Ant2Maven": {
        "conditions": ["sm", "stm", "astm", "astmo"],
        "astmo_note": None,
    },
    "BibTeX2DocBook": {
        "conditions": ["sm", "stm", "astm", "astmo"],
        "astmo_note": None,
        "ocl_file": "OCL_Constraints.txt",
    },
    "CPL2SPL": {
        "conditions": ["sm", "stm", "astm", "astmo"],
        "astmo_note": None,
        "ocl_file": "OCL_Constraints.txt",
    },
    "Ecore2Maude": {
        "conditions": ["sm", "stm", "astm", "astmo"],
        "astmo_note": None,
        "ocl_file": "OCL_Constraints.txt",
    },
    "Grafcet2PetriNet": {
        "conditions": ["sm", "stm", "astm", "astmo"],
        "astmo_note": None,
    },
    "UML2ER": {
        "conditions": ["sm", "stm", "astm", "astmo"],
        "astmo_note": None,
        "ocl_file": "OCL_Constraints.txt",
    },
}
