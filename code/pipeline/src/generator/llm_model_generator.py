# src/generator/llm_model_generator.py
#
# LLM-based test model generator supporting zero-shot and few-shot strategies.
# The LLM backend is injected at call time, making it fully replaceable.

import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prompt templates ───────────────────────────────────────────────────────────

_ZERO_SHOT_TEMPLATE = """\
You are an expert in model-driven engineering and EMF/Ecore metamodels.

Your task is to generate a valid XMI source model that conforms to the \
following Ecore metamodel.

METAMODEL:
{metamodel_text}

Instructions:
- Generate a realistic and varied model instance.
- The model must be well-formed and conform strictly to the metamodel.
- Include multiple instances of the main entity types.
- Output ONLY the raw XMI content. Do not include any explanation, \
markdown, or code fences.
- The output must start with: <?xml version="1.0"
"""

_FEW_SHOT_TEMPLATE = """\
You are an expert in model-driven engineering and EMF/Ecore metamodels.

Your task is to generate a valid XMI source model that conforms to the \
following Ecore metamodel.

METAMODEL:
{metamodel_text}

Below are example models that conform to this metamodel. Use them as \
a reference for structure and style, but generate a NEW and DIFFERENT model.

{examples_block}

Instructions:
- Generate a realistic and varied model instance, different from the examples.
- The model must be well-formed and conform strictly to the metamodel.
- Include multiple instances of the main entity types.
- Output ONLY the raw XMI content. Do not include any explanation, \
markdown, or code fences.
- The output must start with: <?xml version="1.0"
"""


# ── 1. Prompt construction ─────────────────────────────────────────────────────

def build_zero_shot_prompt(metamodel_text: str) -> str:
    """
    Build a zero-shot prompt instructing the LLM to generate a model
    conforming to the given metamodel.

    Parameters
    ----------
    metamodel_text : contents of the .ecore file (as a string)

    Returns
    -------
    Complete prompt string ready to send to an LLM.
    """
    return _ZERO_SHOT_TEMPLATE.format(metamodel_text=metamodel_text.strip())


def build_few_shot_prompt(metamodel_text: str, examples: list[str]) -> str:
    """
    Build a few-shot prompt that includes example XMI models.

    Parameters
    ----------
    metamodel_text : contents of the .ecore file (as a string)
    examples       : list of XMI model strings to use as demonstrations

    Returns
    -------
    Complete prompt string ready to send to an LLM.
    """
    examples_block_parts = []
    for i, xmi in enumerate(examples, start=1):
        examples_block_parts.append(
            f"--- Example {i} ---\n{xmi.strip()}\n--- End of Example {i} ---"
        )
    examples_block = "\n\n".join(examples_block_parts)

    return _FEW_SHOT_TEMPLATE.format(
        metamodel_text=metamodel_text.strip(),
        examples_block=examples_block,
    )


# ── 2. LLM call interface ──────────────────────────────────────────────────────

def generate_model_with_llm(prompt: str, llm_client) -> Optional[str]:
    """
    Send a prompt to the LLM and return the raw text response.

    This function is API-agnostic. Pass any client object that exposes
    a `generate(prompt: str) -> str` method, or a callable that accepts
    a prompt string and returns a string.

    Compatible with the existing deepseek_client.call_deepseek() by
    wrapping it in a lambda:

        llm_client = lambda p: call_deepseek(p, api_key)

    Parameters
    ----------
    prompt     : the complete prompt string
    llm_client : callable(prompt: str) -> str  OR  object with .generate()

    Returns
    -------
    Raw LLM response text, or None if the call failed.
    """
    try:
        if callable(llm_client):
            response = llm_client(prompt)
        elif hasattr(llm_client, "generate"):
            response = llm_client.generate(prompt)
        else:
            raise TypeError(
                "llm_client must be callable or expose a .generate() method."
            )
        return response
    except Exception as e:
        logger.error(f"LLM call failed: {e}")
        return None


# ── 3. Model extraction ────────────────────────────────────────────────────────

_XMI_START_RE = re.compile(
    r'(<\?xml\s[^>]*\?>.*)', re.DOTALL | re.IGNORECASE)
_CODE_FENCE_RE = re.compile(
    r'```(?:xml)?\s*(.*?)\s*```', re.DOTALL | re.IGNORECASE)


def extract_xmi_model(response_text: str) -> Optional[str]:
    """
    Extract XMI model content from a raw LLM response.

    Handles three common LLM output formats:
    1. Pure XMI starting with <?xml ...>
    2. XMI wrapped in a ```xml ... ``` code fence
    3. XMI embedded somewhere in the response text

    Parameters
    ----------
    response_text : raw string returned by the LLM

    Returns
    -------
    Extracted XMI string, or None if extraction failed.
    """
    if not response_text:
        return None

    # Strategy A: code fence
    fence_match = _CODE_FENCE_RE.search(response_text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate.lower().startswith("<?xml") or candidate.startswith("<"):
            return candidate

    # Strategy B: starts with <?xml
    xml_match = _XMI_START_RE.search(response_text)
    if xml_match:
        return xml_match.group(1).strip()

    # Strategy C: starts with a root element (no XML declaration)
    stripped = response_text.strip()
    if stripped.startswith("<") and not stripped.startswith("</"):
        return stripped

    return None


# ── 4. Save model ──────────────────────────────────────────────────────────────

def save_model(model_text: str, output_path: str) -> bool:
    """
    Write XMI model text to a file.

    Parameters
    ----------
    model_text  : XMI content string
    output_path : destination .xmi file path

    Returns
    -------
    True if saved successfully, False otherwise.
    """
    try:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(model_text)
            f.flush()
            os.fsync(f.fileno())
        return True
    except Exception as e:
        logger.error(f"Failed to save model to '{output_path}': {e}")
        return False


# ── 5. High-level generator ────────────────────────────────────────────────────

def generate_test_model(
    strategy: str,
    metamodel_text: str,
    output_path: str,
    llm_client,
    examples: Optional[list[str]] = None,
) -> dict:
    """
    Generate a test model using the specified prompting strategy.

    Parameters
    ----------
    strategy       : "zero_shot" or "few_shot"
    metamodel_text : contents of the .ecore metamodel file
    output_path    : path where the generated .xmi file will be saved
    llm_client     : callable(prompt) -> str  or  object with .generate()
    examples       : list of example XMI strings (required for "few_shot")

    Returns
    -------
    {
        "success":    bool,
        "model_path": str | None,
        "strategy":   str,
    }
    """
    if strategy not in ("zero_shot", "few_shot"):
        raise ValueError(
            f"Unknown strategy '{strategy}'. "
            f"Must be 'zero_shot' or 'few_shot'."
        )

    # ── Build prompt ───────────────────────────────────────────────────────
    if strategy == "zero_shot":
        prompt = build_zero_shot_prompt(metamodel_text)
    else:
        if not examples:
            logger.warning(
                "few_shot strategy requested but no examples provided. "
                "Falling back to zero_shot."
            )
            prompt = build_zero_shot_prompt(metamodel_text)
        else:
            prompt = build_few_shot_prompt(metamodel_text, examples)

    logger.info(f"[llm_model_generator] strategy={strategy} | "
                f"prompt_length={len(prompt)} chars")

    # ── Call LLM ───────────────────────────────────────────────────────────
    response = generate_model_with_llm(prompt, llm_client)
    if response is None:
        logger.warning(f"[llm_model_generator] strategy={strategy} | "
                       f"LLM returned no response.")
        return {"success": False, "model_path": None, "strategy": strategy}

    # ── Extract XMI ────────────────────────────────────────────────────────
    model_text = extract_xmi_model(response)
    if model_text is None:
        logger.warning(f"[llm_model_generator] strategy={strategy} | "
                       f"XMI extraction failed.")
        return {"success": False, "model_path": None, "strategy": strategy}

    # ── Save model ─────────────────────────────────────────────────────────
    saved = save_model(model_text, output_path)
    if not saved:
        return {"success": False, "model_path": None, "strategy": strategy}

    logger.info(f"[llm_model_generator] strategy={strategy} | "
                f"generation SUCCESS → {output_path}")

    return {
        "success":    True,
        "model_path": output_path,
        "strategy":   strategy,
    }


# ── Batch helper ───────────────────────────────────────────────────────────────

def generate_test_models_batch(
    strategy: str,
    metamodel_text: str,
    output_dir: str,
    llm_client,
    n: int = 5,
    examples: Optional[list[str]] = None,
    prefix: str = "llm_model",
) -> list[dict]:
    """
    Generate n test models using the specified strategy.

    Returns a list of generate_test_model() result dicts.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    results = []
    for i in range(1, n + 1):
        output_path = str(Path(output_dir) / f"{prefix}_{strategy}_{i:04d}.xmi")
        result = generate_test_model(
            strategy       = strategy,
            metamodel_text = metamodel_text,
            output_path    = output_path,
            llm_client     = llm_client,
            examples       = examples,
        )
        results.append(result)
        status = "OK" if result["success"] else "FAILED"
        print(f"[{i:04d}] {strategy}: {status} → {output_path}")
    return results


# ── main: demonstration ────────────────────────────────────────────────────────

def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    root       = Path(__file__).resolve().parents[2]
    dataset    = root / "datasets" / "models_BibTexML2DocBook"
    output_dir = root / "results" / "generated_models" / "llm_generator_test"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load metamodel text
    mm_path = dataset / "BibTeX.ecore"
    if not mm_path.is_file():
        print(f"Metamodel not found: {mm_path}")
        return
    metamodel_text = mm_path.read_text(encoding="utf-8")

    # Load a couple of example models for few-shot
    examples = []
    for i in range(1, 4):
        xmi_path = dataset / "scenarios" / f"scenario{i}" / \
                   f"AutomaticModel_BibTex{i}.xmi"
        if xmi_path.is_file():
            examples.append(xmi_path.read_text(encoding="utf-8"))

    # Set up LLM client using existing deepseek_client
    from src.llm.llm_client import call_deepseek, read_api_key
    api_key    = read_api_key(str(root / "config" / "deepseek_api_key.txt"))
    llm_client = lambda prompt: call_deepseek(prompt, api_key)

    print("\n" + "="*60)
    print("TEST 1: Zero-shot generation")
    print("="*60)
    result_zs = generate_test_model(
        strategy       = "zero_shot",
        metamodel_text = metamodel_text,
        output_path    = str(output_dir / "zero_shot_0001.xmi"),
        llm_client     = llm_client,
    )
    print(f"  success    : {result_zs['success']}")
    print(f"  model_path : {result_zs['model_path']}")

    print("\n" + "="*60)
    print("TEST 2: Few-shot generation")
    print("="*60)
    result_fs = generate_test_model(
        strategy       = "few_shot",
        metamodel_text = metamodel_text,
        output_path    = str(output_dir / "few_shot_0001.xmi"),
        llm_client     = llm_client,
        examples       = examples,
    )
    print(f"  success    : {result_fs['success']}")
    print(f"  model_path : {result_fs['model_path']}")


if __name__ == "__main__":
    main()