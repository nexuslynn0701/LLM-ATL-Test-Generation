"""
blackbox_prompt_builder.py
--------------------------
Constructs prompts for black-box test generation experiments.

STRICT ISOLATION GUARANTEE
===========================
This module reads ONLY:
  - source metamodel (.ecore / .xmi)
  - source example models (AutomaticModel_*.xmi)

This module NEVER reads:
  - OCL_Constraints.txt
  - ATL transformation files
  - target metamodel
  - target output examples
  - coverage feedback
  - mutation feedback
  - repair feedback

Do NOT import or call build_prompt() from prompt_builder.py here.
"""

from __future__ import annotations

import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_blackbox_prompt(
    template_path: str,
    source_metamodel_path: str,
    source_example_paths: list[str] | None = None,
    target_metamodel_path: str | None = None,
) -> str:
    """
    Build a black-box prompt by filling a template with ONLY:
      - source metamodel content
      - (optionally) source example model contents

    Parameters
    ----------
    template_path : str
        Path to a prompt template file (e.g. prompts/blackbox_zs_source_only.txt).
        Must contain {SOURCE_METAMODEL_CONTENT}.
        May contain {SOURCE_EXAMPLE_MODELS} (required for BB_FS template).
    source_metamodel_path : str
        Path to the source metamodel file (.ecore).
    source_example_paths : list[str] | None
        Paths to source example XMI files.  Pass None or [] for BB_ZS.
    target_metamodel_path : str | None
        Path to the target metamodel (.ecore).  Pass None for BB_ZS/BB_FS.
        When provided, the template must contain {TARGET_METAMODEL_CONTENT}.

    Returns
    -------
    str
        The fully-rendered prompt string.

    Raises
    ------
    FileNotFoundError
        If template or source metamodel is missing.
    ValueError
        If the template requires {SOURCE_EXAMPLE_MODELS} but none were supplied.
    """
    template_path = Path(template_path)
    source_metamodel_path = Path(source_metamodel_path)

    # --- safety checks ---------------------------------------------------
    _assert_not_forbidden(template_path)
    _assert_not_forbidden(source_metamodel_path)

    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    if not source_metamodel_path.exists():
        raise FileNotFoundError(f"Source metamodel not found: {source_metamodel_path}")

    # --- load template ---------------------------------------------------
    template = template_path.read_text(encoding="utf-8")

    # --- load source metamodel -------------------------------------------
    source_mm_content = source_metamodel_path.read_text(encoding="utf-8")

    # --- load source examples (optional) ---------------------------------
    examples_block = ""
    if source_example_paths:
        parts: list[str] = []
        for idx, ep in enumerate(source_example_paths, start=1):
            ep = Path(ep)
            _assert_not_forbidden(ep)
            _assert_is_source_example(ep)
            if not ep.exists():
                continue
            content = ep.read_text(encoding="utf-8")
            parts.append(f"--- Example {idx}: {ep.name} ---\n{content}")
        examples_block = "\n\n".join(parts)

# --- load target metamodel (BB_FS_target only) ----------------------
    target_mm_content = ""
    if target_metamodel_path is not None:
        target_mm_path = Path(target_metamodel_path)
        _assert_is_target_metamodel(target_mm_path)
        if not target_mm_path.exists():
            raise FileNotFoundError(
                f"Target metamodel not found: {target_mm_path}"
            )
        target_mm_content = target_mm_path.read_text(encoding="utf-8")

    # --- fill template ---------------------------------------------------
    prompt = template.replace("{SOURCE_METAMODEL_CONTENT}", source_mm_content)

    if "{SOURCE_EXAMPLE_MODELS}" in template:
        if not examples_block:
            raise ValueError(
                "Template requires {SOURCE_EXAMPLE_MODELS} but no valid example paths "
                "were supplied or all paths were missing."
            )
        prompt = prompt.replace("{SOURCE_EXAMPLE_MODELS}", examples_block)

    if "{TARGET_METAMODEL_CONTENT}" in template:
        if not target_mm_content:
            raise ValueError(
                "Template requires {TARGET_METAMODEL_CONTENT} but "
                "target_metamodel_path was not supplied."
            )
        prompt = prompt.replace("{TARGET_METAMODEL_CONTENT}", target_mm_content)

    return prompt


def get_source_example_paths(
    dataset_dir: Path,
    max_scenarios: int = 3,
) -> list[str]:
    """
    Discover source-model XMI files from a dataset's scenarios directory.

    Reads ONLY AutomaticModel_*.xmi files.
    Explicitly EXCLUDES:
      - *_out*.xmi   (target output models)
      - *Trace*.xmi  (trace models)
      - *Joint*.xmi  (joint models)

    Parameters
    ----------
    dataset_dir : Path
        Root directory of the dataset (e.g. datasets/models_BibTexML2DocBook).
    max_scenarios : int
        Maximum number of scenarios to pull examples from (default 3).

    Returns
    -------
    list[str]
        Sorted list of absolute path strings for qualifying source XMI files.
    """
    dataset_dir = Path(dataset_dir)
    scenarios_dir = dataset_dir / "scenarios"

    if not scenarios_dir.exists():
        return []

    collected: list[Path] = []

    # Walk scenario{i} sub-directories in sorted order
    scenario_dirs = sorted(
        d for d in scenarios_dir.iterdir()
        if d.is_dir() and re.match(r"scenario\d+", d.name)
    )

    for scenario_dir in scenario_dirs[:max_scenarios]:
        for xmi_file in sorted(scenario_dir.glob("AutomaticModel_*.xmi")):
            # Extra guard: reject anything that looks like output / trace / joint
            name_lower = xmi_file.name.lower()
            if "_out" in name_lower:
                continue
            if "trace" in name_lower:
                continue
            if "joint" in name_lower:
                continue
            collected.append(xmi_file)

    return [str(p) for p in collected]


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def extract_source_model(llm_response: str) -> str | None:
    """
    Extract the content inside <source_model>...</source_model> tags.

    Returns None if the tags are not found or the content is empty / whitespace.
    """
    match = re.search(
        r"<source_model>\s*(.*?)\s*</source_model>",
        llm_response,
        flags=re.DOTALL,
    )
    if not match:
        return None
    content = match.group(1).strip()
    return content if content else None


def extract_coverage_notes(llm_response: str) -> str:
    """
    Extract the content inside <coverage_notes>...</coverage_notes> tags.

    Returns an empty string if not found.
    """
    match = re.search(
        r"<coverage_notes>\s*(.*?)\s*</coverage_notes>",
        llm_response,
        flags=re.DOTALL,
    )
    if not match:
        return ""
    return match.group(1).strip()


# ---------------------------------------------------------------------------
# Internal safety helpers
# ---------------------------------------------------------------------------

# Filenames / path fragments that must NEVER be read in black-box mode
_FORBIDDEN_PATTERNS: list[str] = [
    "ocl",
    "OCL",
    "constraint",
    ".atl",
    # "target_mm" and "target_metamodel" removed:
    # BB_FS_target intentionally reads target metamodel via target_metamodel_path.
    # Safety is enforced by _assert_is_target_metamodel() instead.
    "_out",
    "output_example",
    "mutation",
    "coverage_feedback",
    "repair",
]


def _assert_not_forbidden(path: Path) -> None:
    """Raise ValueError if path looks like a forbidden (non-source) file."""
    path_str = str(path)
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in path_str:
            raise ValueError(
                f"[BLACKBOX SAFETY] Refusing to read forbidden file: {path}\n"
                f"  Matched forbidden pattern: '{pattern}'"
            )


def _assert_is_source_example(path: Path) -> None:
    """Raise ValueError if the file does not look like a source example model."""
    name = path.name
    if not name.startswith("AutomaticModel_"):
        raise ValueError(
            f"[BLACKBOX SAFETY] Source example file must start with 'AutomaticModel_': {path}"
        )
    if name.endswith("_out.xmi") or "_out" in name.lower():
        raise ValueError(
            f"[BLACKBOX SAFETY] Source example must not be a target output file: {path}"
        )
    
def _assert_is_target_metamodel(path: Path) -> None:
    """
    Safety check for target metamodel files (BB_FS_target only).
    Allows only .ecore files; rejects OCL, ATL, output, trace files.
    """
    if not path.suffix.lower() == ".ecore":
        raise ValueError(
            f"[BLACKBOX SAFETY] Target metamodel must be a .ecore file: {path}"
        )
    name = path.name.lower()
    for bad in ("_out", "trace", "ocl", ".atl", "mutation", "repair"):
        if bad in name:
            raise ValueError(
                f"[BLACKBOX SAFETY] Refusing suspicious target metamodel path: {path}\n"
                f"  Matched pattern: '{bad}'"
            )