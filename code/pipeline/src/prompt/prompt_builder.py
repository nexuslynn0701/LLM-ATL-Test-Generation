# src/prompt/prompt_builder.py
import os


def build_prompt(
    template_path: str,
    metamodel_paths: list,
    ocl_path: str,
    example_paths: list,
    atl_path: str,
    safety_note: str = "",
) -> str:
    """
    Fill the prompt template with metamodel, OCL, ATL, and example content.
    example_paths may be either:
    - a list of source XMI paths (old behaviour, no DocBook pairing)
    - a list of (source_xmi_path, docbook_xmi_path) tuples (new behaviour)
    """
    with open(template_path, "r", encoding="utf-8") as f:
        prompt = f.read()
    # ── Metamodel content ─────────────────────────────────────────────────
    metamodel_content = ""
    for path in metamodel_paths:
        if not os.path.isfile(path):
            print(f"[WARNING] Metamodel file not found, skipped: {path}")
            continue
        filename = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        metamodel_content += f"--- {filename} ---\n{content}\n\n"
    metamodel_content = metamodel_content.rstrip()
    # ── OCL constraints ───────────────────────────────────────────────────
    ocl_content = ""
    if os.path.isfile(ocl_path):
        with open(ocl_path, "r", encoding="utf-8") as f:
            ocl_content = f.read().strip()
    # ── Example models (source + optional DocBook output) ─────────────────
    example_models = ""
    for i, entry in enumerate(example_paths, start=1):
        if isinstance(entry, tuple):
            source_path, docbook_path = entry
        else:
            source_path  = entry
            docbook_path = None
        if not os.path.isfile(source_path):
            continue
        source_filename = os.path.basename(source_path)
        with open(source_path, "r", encoding="utf-8") as f:
            source_content = f.read()
        if docbook_path and os.path.isfile(docbook_path):
            docbook_filename = os.path.basename(docbook_path)
            with open(docbook_path, "r", encoding="utf-8") as f:
                docbook_content = f.read()
            example_models += (
                f"--- Example {i}: {source_filename} ---\n"
                f"{source_content}\n\n"
                f"--- Example {i} ATL output: {docbook_filename} ---\n"
                f"{docbook_content}\n\n"
            )
        else:
            example_models += (
                f"--- Example {i}: {source_filename} ---\n"
                f"{source_content}\n\n"
            )
    example_models = example_models.rstrip()
    # ── ATL transformation code ───────────────────────────────────────────
    atl_content = ""
    if os.path.isfile(atl_path):
        with open(atl_path, "r", encoding="utf-8", errors="replace") as f:
            atl_content = f.read().strip()
    # ── Fill template ─────────────────────────────────────────────────────
    prompt = prompt.replace("{METAMODEL_CONTENT}", metamodel_content)
    prompt = prompt.replace("{OCL_CONSTRAINTS}",   ocl_content)
    prompt = prompt.replace("{EXAMPLE_MODELS}",    example_models)
    prompt = prompt.replace("{ATL_CODE}",          atl_content)
    # {SOURCE_FORMAT_NOTES} 和 {SAFETY_NOTE} 都支持
    # 当 safety_note 为空时，连同 SOURCE FORMAT NOTES 区块整体去掉
    if safety_note:
        prompt = prompt.replace("{SOURCE_FORMAT_NOTES}", safety_note)
    else:
        import re
        prompt = re.sub(
            r'\n--------------------------------\nSOURCE FORMAT NOTES\n--------------------------------\n\{SOURCE_FORMAT_NOTES\}\n',
            '\n',
            prompt
        )
    prompt = prompt.replace("{SAFETY_NOTE}", safety_note if safety_note else "")
    return prompt


def get_metamodel_paths(dataset_dir: str, config: str = "core") -> list:
    """Return metamodel paths for a given dataset directory and config type."""
    import glob
    pattern   = os.path.join(dataset_dir, "*.ecore")
    all_ecore = sorted(glob.glob(pattern))
    if config == "full":
        return all_ecore
    return [
        p for p in all_ecore
        if os.path.basename(p).lower() not in ("trace.ecore",)
    ]


def get_example_paths(scenarios_dir: str, max_scenarios: int = 3) -> list:
    """Return example (source, target) path pairs from a scenarios directory."""
    import glob
    pairs = []
    for i in range(1, max_scenarios + 1):
        sdir = os.path.join(scenarios_dir, f"scenario{i}")
        if not os.path.isdir(sdir):
            break
        sources = sorted(glob.glob(os.path.join(sdir, "AutomaticModel_*.xmi")))
        targets = [
            p for p in sorted(glob.glob(os.path.join(sdir, "*_out*.xmi")))
            if "Trace" not in p and "Joint" not in p
        ]
        if sources:
            src = sources[0]
            tgt = targets[0] if targets else None
            pairs.append((src, tgt) if tgt else src)
    return pairs


# ── SAT_AWARE hint builder ────────────────────────────────────────────────────
# New function for the SAT_AWARE feedback strategy.
# All functions above are UNCHANGED — zero behavioural difference for existing configs.

def build_saturation_aware_hint(
    uncovered_rules: list = None,
    covered_rules: list = None,
    profile_context: dict = None,
    target_rules: list = None,
    max_rules_hint: int = None,
    safety_note: str = "",
) -> str:
    """
    Build a saturation-aware prompt hint for the SAT_AWARE feedback strategy.

    Steers the LLM toward distribution control rather than coverage maximisation.
    Discourages repeating frequent rule combinations and avoids failure saturation
    while preserving aggregate coverage.

    Parameters
    ----------
    uncovered_rules  : rules not yet covered by any model in this batch
    covered_rules    : rules already covered (for context)
    profile_context  : dict from build_saturation_feedback_context():
                         "frequent_rules"        {rule: freq}
                         "frequent_combinations" [{rules, count, ratio}]
                         "profile_diversity"     float
                         "num_profiles"          int
                         "window_size"           int
    target_rules     : specific rules to encourage (overrides uncovered_rules)
    max_rules_hint   : soft cap on rules to target in one model (default 2)
    safety_note      : dataset-specific constraints appended at end

    Returns
    -------
    str — complete SAT_AWARE hint block to append to the base prompt
    """
    lines = [
        "",
        "--- SATURATION-AWARE GENERATION ---",
        "",
        "This generation targets fault localization quality, not only coverage.",
        "Do NOT try to maximize rule coverage for this single model.",
        "The goal is to preserve aggregate coverage while avoiding failure saturation.",
        "Keep model complexity moderate — avoid both trivially minimal and overly complex models.",
        "Generate a source model with a distinct execution profile from previous models.",
        "Keep the model structurally valid and conformant to the metamodel.",
        "",
    ]

    # ── Frequent rules warning ────────────────────────────────────────────
    if profile_context:
        frequent_rules = profile_context.get("frequent_rules", {})
        if frequent_rules:
            lines.append(
                "Frequently triggered rules in recent models — "
                "avoid overusing these unless necessary:"
            )
            for rule, freq in sorted(frequent_rules.items(), key=lambda x: -x[1]):
                lines.append(f"  - {rule}  (freq={freq:.2f})")
            lines.append("")

        # ── Frequent combinations warning ──────────────────────────────────
        frequent_combos = profile_context.get("frequent_combinations", [])
        if frequent_combos:
            lines.append("Frequent execution profiles to avoid repeating:")
            n_window = profile_context.get("window_size", 10)
            for combo in frequent_combos:
                rules  = combo.get("rules", [])
                count  = combo.get("count", 0)
                ratio  = combo.get("ratio", 0.0)
                lines.append(
                    f"  - {{{', '.join(rules)}}}  "
                    f"appeared {count}/{n_window} times ({ratio:.0%})"
                )
            lines.append("")

        # ── Low diversity warning ──────────────────────────────────────────
        diversity = profile_context.get("profile_diversity")
        if diversity is not None and diversity < 0.3:
            lines.append(
                f"Recent execution profile diversity is LOW ({diversity:.2f}).  "
                "Please generate a model with a substantially different "
                "rule execution pattern from previous ones."
            )
            lines.append("")

    # ── Rule targeting ────────────────────────────────────────────────────
    rules_to_show = target_rules or uncovered_rules or []
    cap = max_rules_hint if max_rules_hint is not None else 2

    if rules_to_show:
        lines.append(
            f"Prefer ONE or TWO of the following uncovered or under-differentiated rules "
            f"(do not try to cover all of them at once):"
        )
        for rule in rules_to_show[:8]:
            lines.append(f"  - {rule}")
        if len(rules_to_show) > cap:
            lines.append(
                f"  ... ({len(rules_to_show)} uncovered total; target at most {cap})"
            )
        lines.append("")
    elif covered_rules:
        lines.append(
            "All rules have been covered.  "
            "Generate a model with a distinctly different execution profile "
            "to increase coverage diversity.  "
            "It is acceptable if this model does not expose additional faults."
        )
        lines.append("")

    lines += [
        "--- END SATURATION-AWARE GUIDANCE ---",
        safety_note,
    ]
    return "\n".join(lines)


def main():
    import sys
    print("prompt_builder module — call build_prompt() or build_saturation_aware_hint() directly.")


if __name__ == "__main__":
    main()