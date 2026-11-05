#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from src.generator.test_generator import generate_tests
from src.llm.llm_client import PROVIDER_CONFIGS

PROVIDERS = {
    "gpt": ("openai", "OPENAI_API_KEY"),
    "qwen": ("qwen", "QWEN_API_KEY"),
    "deepseek": ("deepseek-flash", "DEEPSEEK_API_KEY"),
}

SUBJECTS = {
    "Ant2Maven": {
        "source_mm": "Ant.ecore",
        "target_mm": "MavenMaven.ecore",
        "target_mms": {"OUTMaven": "MavenMaven.ecore", "OUTProject": "MavenProject.ecore"},
        "source_name": "Ant",
        "target_name": "MavenMaven",
        "target_names": {"OUTMaven": "MavenMaven", "OUTProject": "MavenProject"},
        "trace_name": "TMM",
        "transformation": "Ant2Maven",
        "exec_name": "Ant2Maven_trace",
        "metamodels": ["Ant.ecore", "MavenMaven.ecore", "MavenProject.ecore"],
        "ocl": "OCL_CONTRACT.txt",
    },
    "BibTeX2DocBook": {
        "source_mm": "BibTeX.ecore", "target_mm": "DocBook.ecore",
        "source_name": "BibTeX", "target_name": "DocBook", "trace_name": "TMM",
        "transformation": "BibTeX2DocBook", "metamodels": ["BibTeX.ecore", "DocBook.ecore"],
        "ocl": "OCL_Constraints.txt",
    },
    "CPL2SPL": {
        "source_mm": "CPL.ecore", "target_mm": "SPL.ecore",
        "source_name": "CPL", "target_name": "SPL", "trace_name": "TMM",
        "transformation": "CPL2SPL", "metamodels": ["CPL.ecore", "SPL.ecore"],
        "ocl": "OCL_Constraints.txt",
    },
    "Ecore2Maude": {
        "source_mm": "ecore.ecore", "target_mm": "Maude.ecore",
        "source_name": "Ecore", "target_name": "Maude", "trace_name": "TMM",
        "transformation": "Ecore2Maude", "metamodels": ["ecore.ecore", "Maude.ecore"],
        "ocl": "OCL_Constraints.txt",
    },
    "Grafcet2PetriNet": {
        "source_mm": "Grafcet.ecore", "target_mm": "PetriNet.ecore",
        "source_name": "Grafcet", "target_name": "PetriNet", "trace_name": "TMM",
        "transformation": "Grafcet2PetriNet_trace", "metamodels": ["Grafcet.ecore", "PetriNet.ecore"],
        "ocl": "OCL_CONTRACT.txt",
    },
    "UML2ER": {
        "source_mm": "SimpleUml.ecore", "target_mm": "ER.ecore",
        "source_name": "SimpleUML", "target_name": "ER", "trace_name": "TMM",
        "transformation": "SimpleUml2ER", "metamodels": ["SimpleUml.ecore", "ER.ecore"],
        "ocl": "OCL_Constraints.txt",
    },
}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one paper workflow generation cell.")
    parser.add_argument("--subject", required=True, choices=sorted(SUBJECTS))
    parser.add_argument("--provider", required=True, choices=sorted(PROVIDERS))
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--output-root", type=Path, default=ROOT / "results/rq5/new_workflow_runs")
    parser.add_argument("--atl-lib", type=Path, default=None)
    parser.add_argument("--endpoint", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    return parser.parse_args()


def main() -> int:
    args = arguments()
    if args.n < 1 or args.start_index < 1:
        raise SystemExit("--n and --start-index must be positive")
    if args.atl_lib is None or not args.atl_lib.is_dir():
        raise SystemExit("Pass --atl-lib with the ATL/EMF jars and compiled runner classes")

    provider_key, key_variable = PROVIDERS[args.provider]
    api_key = os.environ.get(key_variable, "")
    if not api_key:
        raise SystemExit(f"Set {key_variable} before running generation")

    provider = PROVIDER_CONFIGS[provider_key]
    if args.endpoint:
        provider["url"] = args.endpoint
    if args.model:
        provider["model"] = args.model
    provider["temperature"] = args.temperature

    spec = SUBJECTS[args.subject]
    assets = HERE / "assets" / args.subject
    transformations = assets / "transformations"
    example_files = sorted((assets / "examples").glob("*.xmi"))
    source_examples = [p for p in example_files if p.name.startswith("AutomaticModel_")]
    if source_examples:
        examples = []
        for source in source_examples:
            suffix = "".join(ch for ch in source.stem if ch.isdigit())
            targets = [p for p in example_files if "_out" in p.name and suffix and suffix in p.stem]
            examples.append((str(source), str(targets[0])) if targets else str(source))
    else:
        examples = [str(p) for p in example_files]
    output = args.output_root / args.subject / args.provider
    generated = output / "generated_models"
    transformed = output / "outputs"
    generated.mkdir(parents=True, exist_ok=True)
    transformed.mkdir(parents=True, exist_ok=True)

    executor = {
        "java_cp": str(args.atl_lib),
        "source_mm": str(assets / spec["source_mm"]),
        "target_mm": str(assets / spec["target_mm"]),
        "trace_mm": str(assets / "Trace.ecore"),
        "source_mm_name": spec["source_name"],
        "target_mm_name": spec["target_name"],
        "trace_mm_name": spec["trace_name"],
        "atl_name": spec["transformation"],
        "atl_exec_name": spec.get("exec_name", spec["transformation"]),
        "transformations_dir": str(transformations),
        "timeout": 300,
        "max_workers": 8,
        "reject_containment_warning": True,
    }
    if "target_mms" in spec:
        executor["target_mms"] = {name: str(assets / path) for name, path in spec["target_mms"].items()}
        executor["target_mm_names"] = spec["target_names"]

    os.environ["LLM_PROVIDER"] = provider_key
    os.environ["LLM_CALL_LOG"] = str(output / "llm_calls.jsonl")
    rows = generate_tests(
        template_path=str(HERE / "prompts/template.txt"),
        metamodel_paths=[str(assets / name) for name in spec["metamodels"]],
        ocl_path=str(assets / spec["ocl"]),
        example_paths=examples,
        atl_path=str(transformations / f"{spec['transformation']}.atl"),
        api_key=api_key,
        output_dir=str(generated),
        n=args.n,
        start_index=args.start_index,
        use_coverage_guidance=True,
        verify_coverage=True,
        transform_dir=str(transformed),
        transformation_name=spec["transformation"],
        executor_config=executor,
        safety_note=(assets / "safety_note.txt").read_text(encoding="utf-8"),
        enable_repair=True,
        llm_provider=provider_key,
        abort_on_api_error=True,
    )
    (output / "generation_summary.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {len(rows)} records in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
