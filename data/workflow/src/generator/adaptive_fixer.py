# src/generator/adaptive_fixer.py
#
# Adaptive repair module for LLM-generated XMI models.
#
# When ATL transformation fails, this module:
#   1. Extracts the error message from the ATL execution
#   2. Reads the failing XMI model
#   3. Constructs a repair prompt with the error + original model
#   4. Calls the LLM to fix the model
#   5. Returns the repaired XMI
#
# Usage:
#   from src.generator.adaptive_fixer import AdaptiveFixer
#   fixer = AdaptiveFixer(api_key, max_attempts=3)
#   fixed_xmi, success, attempts = fixer.fix(source_path, error_msg, safety_note)

import logging
import os
import re

from src.llm import call_logger

logger = logging.getLogger(__name__)

# ── Repair prompt template ────────────────────────────────────────────────────

_REPAIR_TEMPLATE = """You are an expert in Model-Driven Engineering (MDE) and XMI model repair.

The following XMI model failed to execute in an ATL model transformation with this error:

ERROR:
{error_message}

FAILING MODEL:
{failing_model}

{safety_note}

TASK:
Fix the XMI model so that the ATL transformation can execute successfully.
Common fixes:
- Remove invalid cross-references (use XMI path format like //@elements.N instead of id-based refs)
- Move misplaced elements to their correct containment location
- Add missing mandatory attributes (lowerBound=1 features)
- Remove elements that are only valid as children of specific parent types

Return ONLY the fixed XMI model, starting with <?xml version="1.0"
Do not include any explanation or markdown formatting.
"""

_REPAIR_TEMPLATE_WITH_CONTEXT = """You are an expert in Model-Driven Engineering (MDE) and XMI model repair.

The following XMI model failed to execute in an ATL model transformation with this error:

ERROR:
{error_message}

FAILING MODEL:
{failing_model}

METAMODEL CONTEXT:
{metamodel_context}

{safety_note}

TASK:
Fix the XMI model so that the ATL transformation can execute successfully.
Study the error carefully and correct the specific issue.

Return ONLY the fixed XMI model, starting with <?xml version="1.0"
Do not include any explanation or markdown formatting.
"""


# ── Error extraction ──────────────────────────────────────────────────────────

def extract_error_type(error_msg: str) -> str:
    """Classify the error type for targeted repair hints."""
    if "DanglingHREFException" in error_msg:
        return "dangling_href"
    elif "IllegalValueException" in error_msg:
        return "illegal_value"
    elif "UnresolvedReferenceException" in error_msg:
        return "unresolved_reference"
    elif "ClassCastException" in error_msg:
        return "class_cast"
    elif "NullPointerException" in error_msg:
        return "null_pointer"
    else:
        return "unknown"


def get_repair_hint(error_type: str, error_msg: str) -> str:
    """Return targeted repair hint based on error type."""
    hints = {
        "dangling_href": (
            "HINT: DanglingHREFException means an element references an object "
            "that is not in the model. Check all 'ref' attributes — they should "
            "be plain string values, not object references. "
            "Example: ref=\"anyStringValue\" not ref=\"someId\""
        ),
        "illegal_value": (
            "HINT: IllegalValueException means an element is in the wrong location. "
            "Check that all elements appear in their correct containment position. "
            "Some element types can only appear as children of specific parent types, "
            "not as top-level elements."
        ),
        "unresolved_reference": (
            "HINT: UnresolvedReferenceException means a reference cannot be resolved. "
            "Use XMI path format for cross-references: //@eClassifiers.N (0-based index). "
            "Do NOT use name-based references like #//ClassName."
        ),
        "unknown": (
            "HINT: Fix the model structure to comply with the metamodel constraints."
        ),
    }
    return hints.get(error_type, hints["unknown"])


# ── Main fixer class ──────────────────────────────────────────────────────────

class AdaptiveFixer:
    """
    Attempts to repair a failing XMI model using LLM feedback.

    Parameters
    ----------
    api_key      : API key for the selected provider
    max_attempts : maximum repair attempts per model (default 3)
    provider     : LLM provider key（应与生成该模型的 provider 一致；
                   None 时回退到环境变量 LLM_PROVIDER，再回退 deepseek）
    """

    def __init__(self, api_key: str, max_attempts: int = 3, provider: str = None):
        self.api_key      = api_key
        self.max_attempts = max_attempts
        self.provider     = provider

    def fix(
        self,
        source_path:      str,
        error_msg:        str,
        safety_note:      str = "",
        metamodel_paths:  list = None,
    ) -> tuple:
        """
        Attempt to repair a failing XMI model.

        Parameters
        ----------
        source_path     : path to the failing XMI file
        error_msg       : ATL error message
        safety_note     : dataset-specific constraints to include in prompt
        metamodel_paths : optional list of ecore paths for context

        Returns
        -------
        (fixed_xmi: str, success: bool, attempts: int)
        """
        from src.llm.llm_client import call_llm

        # Read the failing model
        try:
            with open(source_path, "r", encoding="utf-8", errors="replace") as f:
                failing_model = f.read().strip()
        except Exception as e:
            logger.error(f"Cannot read failing model: {e}")
            return None, False, 0

        # Classify error and get targeted hint
        error_type  = extract_error_type(error_msg)
        repair_hint = get_repair_hint(error_type, error_msg)
        full_note   = f"{repair_hint}\n\n{safety_note}".strip()

        # Optionally include metamodel context
        metamodel_context = ""
        if metamodel_paths:
            for mm_path in metamodel_paths[:2]:  # max 2 metamodels
                if os.path.isfile(mm_path):
                    try:
                        with open(mm_path, "r", encoding="utf-8",
                                  errors="replace") as f:
                            metamodel_context += f"\n--- {os.path.basename(mm_path)} ---\n"
                            metamodel_context += f.read().strip()[:3000]  # truncate
                    except Exception:
                        pass

        for attempt in range(1, self.max_attempts + 1):
            logger.info(
                f"[AdaptiveFixer] Repair attempt {attempt}/{self.max_attempts} "
                f"(error_type={error_type})"
            )

            # Build repair prompt
            if metamodel_context:
                prompt = _REPAIR_TEMPLATE_WITH_CONTEXT.format(
                    error_message     = error_msg[:500],  # truncate long errors
                    failing_model     = failing_model,
                    metamodel_context = metamodel_context,
                    safety_note       = full_note,
                )
            else:
                prompt = _REPAIR_TEMPLATE.format(
                    error_message = error_msg[:500],
                    failing_model = failing_model,
                    safety_note   = full_note,
                )

            try:
                _provider = self.provider or os.environ.get("LLM_PROVIDER", "deepseek")
                logger.info(f"[AdaptiveFixer] Using LLM provider: {_provider}")
                call_logger.set_context(
                    call_role      = "repair",
                    repair_attempt = attempt,
                    repair_max     = self.max_attempts,
                    source_path    = source_path,
                )
                response = call_llm(prompt, self.api_key, provider=_provider)
            except Exception as e:
                logger.warning(f"[AdaptiveFixer] API call failed: {e}")
                continue

            # Extract XMI from response
            fixed_xmi = self._extract_xmi(response)
            if not fixed_xmi:
                logger.warning("[AdaptiveFixer] No valid XMI in response")
                continue

            # Save repaired model back to original path
            try:
                with open(source_path, "w", encoding="utf-8") as f:
                    f.write(fixed_xmi)
                logger.info(f"[AdaptiveFixer] Saved repaired model → {source_path}")
                return fixed_xmi, True, attempt
            except Exception as e:
                logger.error(f"[AdaptiveFixer] Cannot save repaired model: {e}")
                continue

        logger.warning(f"[AdaptiveFixer] All {self.max_attempts} repair attempts failed")
        return None, False, self.max_attempts

    def _extract_xmi(self, response: str) -> str:
        """Extract clean XMI from LLM response."""
        # Remove markdown code blocks
        response = re.sub(r"```xml\s*", "", response)
        response = re.sub(r"```\s*", "", response)
        response = response.strip()

        # Must start with XML declaration or root element
        if response.startswith("<?xml"):
            return response
        # Try to find XML start
        match = re.search(r"(<\?xml.*)", response, re.DOTALL)
        if match:
            return match.group(1).strip()
        # Try to find root element
        match = re.search(r"(<[a-zA-Z].*)", response, re.DOTALL)
        if match:
            return match.group(1).strip()

        return ""


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

    from src.llm.llm_client import get_api_key

    provider = os.environ.get("LLM_PROVIDER", "deepseek")
    api_key = get_api_key(provider)

    # Simulate a repair attempt with a known error
    test_error = (
        "org.eclipse.emf.ecore.xmi.DanglingHREFException: "
        "The object 'SubCall' is not contained in a resource."
    )
    test_model = """<?xml version="1.0" encoding="ASCII"?>
<CPL:CPLModel xmi:version="2.0" xmlns:CPL="http://cpl/1.0">
  <elements xsi:type="CPL:CPL"/>
  <elements xsi:type="CPL:SubCall" ref="sub1"/>
  <elements xsi:type="CPL:SubAction" id="sub1"/>
</CPL:CPLModel>"""

    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".xmi",
                                     delete=False, encoding="utf-8") as tmp:
        tmp.write(test_model)
        tmp_path = tmp.name

    fixer = AdaptiveFixer(api_key, max_attempts=2)
    fixed, success, attempts = fixer.fix(tmp_path, test_error)
    print(f"Success: {success}, Attempts: {attempts}")
    if fixed:
        print("Fixed XMI (first 200 chars):")
        print(fixed[:200])
    os.unlink(tmp_path)
