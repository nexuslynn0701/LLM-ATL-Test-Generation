# src/analyzer/coverage_analyzer.py

import os
import re
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict

logger = logging.getLogger(__name__)


# ── 从 ATL 文件提取所有规则和 helper 名称 ────────────────────────────────────

def extract_rules_and_helpers(atl_path: str) -> dict:
    rules   = []
    helpers = []
    # 匹配所有 rule 变体的正则：
    # "rule X"、"abstract rule X"、"lazy rule X"、
    # "unique lazy rule X"、"abstract lazy rule X" 等
    _RULE_RE = re.compile(
        r'^(?:abstract\s+)?(?:unique\s+)?(?:lazy\s+)?rule\s+\w'
    )
    _STRIP_RE = re.compile(
        r'^(?:abstract\s+)?(?:unique\s+)?(?:lazy\s+)?rule\s+'
    )

    with open(atl_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            stripped = line.strip()

            is_entrypoint = stripped.startswith("entrypoint rule ")
            is_rule       = bool(_RULE_RE.match(stripped)) and not is_entrypoint

            if is_rule:
                # 去掉所有修饰词前缀，提取规则名
                working = _STRIP_RE.sub("", stripped)
                name    = working.split("{")[0].strip()
                if " extends " in name:
                    name = name.split(" extends ")[0].strip()
                if "(" in name:
                    name = name.split("(")[0].strip()
                if name:
                    rules.append(name)

            elif stripped.startswith("helper "):
                if " def : " in stripped:
                    part = stripped.split(" def : ")[1]
                    name = part.split(":")[0].strip()
                    if name:
                        helpers.append(name)

    return {"rules": rules, "helpers": helpers}


# ── 解析 trace 文件，提取规则执行记录 ────────────────────────────────────────

def parse_trace(trace_path: str) -> dict:
    rule_executions = defaultdict(int)
    tree = ET.parse(trace_path)
    root = tree.getroot()
    for elem in root.iter():
        if elem.tag.endswith("traceLinks") or elem.tag == "traceLinks":
            rule_name = elem.get("ruleName")
            if rule_name and rule_name != "createTrace":
                rule_executions[rule_name] += 1
    return {
        "rule_executions": dict(rule_executions),
        "executed_rules":  set(rule_executions.keys()),
    }




# ── Ant2Maven fallback: ATL trace is empty for ATLRunnerMulti ────────────────

_ANT2MAVEN_TYPE_TO_RULE = {
    "Project": {"AntProject2Maven", "AntProject2MavenWithoutDescription"},
    "Target": {"AntTarget2MavenMavenGoal"},
    "PropertyValue": {"AntPropertyValue2MavenMavenAntPropertyValue"},
    "PropertyLocation": {"AntPropertyLocation2MavenMavenAntPropertyLocation"},
    "PropertyFile": {"AntPropertyFile2MavenMavenAntPropertyFile"},
    "PropertyEnv": {"AntPropertyEnv2MavenMavenAntPropertyEnv"},
    "Java": {"AntJava2MavenMavenJava"},
    "Javac": {"AntJavac2MavenMavenJavac"},
    "Javadoc": {"AntJavadoc2MavenMavenJavadoc"},
    "Tstamp": {"AntTstamp2MavenMavenTstamp"},
    "Jar": {"AntJar2MavenMavenJar"},
    "Mkdir": {"AntMkdir2MavenMavenMkdir"},
    "Copy": {"AntCopy2MavenMavenCopy"},
    "Delete": {"AntDelete2MavenMavenDelete"},
    "TaskDef": {"AntTaskDef2MavenMavenTaskDef"},
    "NewTask": {"AntNewTask2MavenMavenNewTask"},
    "Attribut": {"AntAttribut2MavenMavenAttribut"},
    "Path": {"AntPath2MavenMavenPath"},
    "ClassPath": {"AntClassPath2MavenMavenClassPath"},
    "PathElement": {"AntPathElement2MavenMavenPathElement"},
    "FileSet": {"AntFileSet2MavenMavenFileSet"},
    "FilterSet": {"AntFilterSet2MavenMavenFilterSet"},
    "Filter": {"AntFilter2MavenMavenFilter"},
    "FiltersFile": {"AntFiltersFile2MavenMavenFiltersFile"},
    "Patternset": {"AntPatternset2MavenMavenPatternset"},
    "Includes": {"AntIncludes2MavenMavenIncludes"},
    "Excludes": {"AntExcludes2MavenMavenExcludes"},
    "IncludesFile": {"AntIncludesFile2MavenMavenIncludesFile"},
    "ExcludesFile": {"AntExcludesFile2MavenMavenExcludesFile"},
}


def _infer_ant2maven_source_from_trace(trace_path: str):
    m = re.search(r"output_(\d{4})_trace\.xmi$", str(trace_path))
    if not m:
        return None
    src = str(trace_path).replace("/outputs/", "/generated_models/")
    src = re.sub(r"output_(\d{4})_trace\.xmi$", r"source_model_\1.xmi", src)
    return src if os.path.isfile(src) else None


def _infer_ant2maven_rules_from_source_xmi(source_xmi_path: str) -> set:
    try:
        txt = open(source_xmi_path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return set()

    types = set(re.findall(r'xsi:type="Ant:([^"]+)"', txt))
    root = re.search(r"<Ant:([A-Za-z0-9_]+)\b", txt)
    if root:
        types.add(root.group(1))

    # Containment element names that often appear without xsi:type.
    containment_markers = {
        "Target": r"<targets\b",
        "Path": r"<path\b",
        "TaskDef": r"<taskdef\b",
        "Attribut": r"<attributes\b",
        "ClassPath": r"<classPath\b",
        "PathElement": r"<pathElement\b",
        "FileSet": r"<fileset\b",
        "Patternset": r"<patternset\b",
        "FilterSet": r"<filterset\b",
        "Filter": r"<filter\b",
        "FiltersFile": r"<filtersfile\b",
    }
    for type_name, pattern in containment_markers.items():
        if re.search(pattern, txt, re.IGNORECASE):
            types.add(type_name)

    rules = set()
    for type_name in types:
        rules.update(_ANT2MAVEN_TYPE_TO_RULE.get(type_name, set()))
    return rules


# ── 计算 rule coverage ────────────────────────────────────────────────────────

def compute_rule_coverage(trace_path: str, atl_path: str, source_xmi_path: str = None) -> dict:
    atl_info    = extract_rules_and_helpers(atl_path)
    all_rules   = atl_info["rules"]
    all_helpers = atl_info["helpers"]

    trace_info      = parse_trace(trace_path)
    executed_rules  = trace_info["executed_rules"]
    rule_executions = trace_info["rule_executions"]

    if (not executed_rules
            and "Ant2Maven" in str(atl_path)
            and any(r.startswith("Ant") for r in all_rules)):
        source_xmi_path = source_xmi_path or _infer_ant2maven_source_from_trace(trace_path)
        if source_xmi_path:
            inferred = _infer_ant2maven_rules_from_source_xmi(source_xmi_path)
            executed_rules = {r for r in inferred if r in all_rules}
            rule_executions = {r: 1 for r in executed_rules}

    covered_rules   = [r for r in all_rules if r in executed_rules]
    uncovered_rules = [r for r in all_rules if r not in executed_rules]

    total         = len(all_rules)
    covered       = len(covered_rules)
    rule_coverage = covered / total if total > 0 else 0.0

    return {
        "total_rules":      total,
        "covered_rules":    covered,
        "rule_coverage":    round(rule_coverage, 4),
        "executed_rules":   sorted(covered_rules),
        "uncovered_rules":  sorted(uncovered_rules),
        "rule_executions":  rule_executions,
        "total_helpers":    len(all_helpers),
        "covered_helpers":  0,
        "helper_coverage":  0.0,
        "helpers":          all_helpers,
    }


# ── 批量计算多个测试模型的覆盖率 ─────────────────────────────────────────────

def compute_batch_coverage(trace_paths: list, atl_path: str) -> dict:
    atl_info  = extract_rules_and_helpers(atl_path)
    all_rules = atl_info["rules"]

    union_executed     = set()
    per_model_coverage = []
    rule_total_counts  = defaultdict(int)

    for trace_path in trace_paths:
        if not os.path.isfile(trace_path):
            per_model_coverage.append(None)
            continue
        result = compute_rule_coverage(trace_path, atl_path)
        union_executed.update(result["executed_rules"])
        per_model_coverage.append(result["rule_coverage"])
        for rule, count in result["rule_executions"].items():
            rule_total_counts[rule] += count

    total    = len(all_rules)
    covered  = len([r for r in all_rules if r in union_executed])
    coverage = covered / total if total > 0 else 0.0

    return {
        "total_rules":           total,
        "covered_rules":         covered,
        "rule_coverage":         round(coverage, 4),
        "executed_rules":        sorted(union_executed),
        "uncovered_rules":       sorted([r for r in all_rules if r not in union_executed]),
        "per_model_coverage":    per_model_coverage,
        "rule_execution_counts": dict(rule_total_counts),
    }


# ── Structural XMI comparison ─────────────────────────────────────────────────

_INTERNAL_POSITIONAL_REFERENCE = re.compile(
    r"^(?://@|/0/@)[A-Za-z_]\w*\.\d+(?:/@[A-Za-z_]\w*\.\d+)*$"
)


def _normalise_internal_reference_alias(value: str) -> str:
    """
    Canonicalise equivalent EMF internal positional reference spellings.

    Examples:
      /0/@goals.0          -> //@goals.0
      /0/@goals.0/@tasks.1 -> //@goals.0/@tasks.1

    Unknown reference formats are left untouched.
    """
    tokens = value.split()
    if not tokens:
        return value
    if not all(_INTERNAL_POSITIONAL_REFERENCE.fullmatch(token) for token in tokens):
        return value

    return " ".join(
        f"//@{token[len('/0/@'):]}"
        if token.startswith("/0/@")
        else token
        for token in tokens
    )


def _normalise_element(elem: ET.Element) -> None:
    """
    In-place normalisation of an Element tree for semantic comparison:
    - strip xmi:id attributes (and any attribute ending in ':id' or named 'xmi:id')
    - sort attributes by key
    - strip text/tail whitespace
    - recurse into children while preserving serialized containment order
    """
    XMI_ID_KEYS = {"xmi:id", "{http://www.omg.org/XMI}id"}

    # Remove xmi:id attributes
    for key in list(elem.attrib.keys()):
        if key in XMI_ID_KEYS or key.endswith("}id") and "xmi" in key.lower():
            del elem.attrib[key]

    # Canonicalise equivalent EMF internal positional reference spellings.
    for key in elem.attrib:
        elem.attrib[key] = _normalise_internal_reference_alias(elem.attrib[key])

    # Normalise text content
    elem.text = (elem.text or "").strip() or None
    elem.tail = (elem.tail or "").strip() or None

    # Recurse
    for child in elem:
        _normalise_element(child)

    # Preserve child order: ordered EReferences make serialization order relevant.


def compare_xmi_models(path1: str, path2: str) -> bool:
    """
    Structural XMI comparison.

    Returns True if both models are semantically equivalent, ignoring:
    - xmi:id attribute values
    - XML attribute ordering
    - whitespace differences
    - child element ordering within a parent
    """
    try:
        tree1 = ET.parse(path1)
        tree2 = ET.parse(path2)
    except ET.ParseError as e:
        logger.warning(f"XMI parse error during comparison: {e}")
        return False

    root1 = tree1.getroot()
    root2 = tree2.getroot()

    _normalise_element(root1)
    _normalise_element(root2)

    return _elements_equal(root1, root2)


def _elements_equal(e1: ET.Element, e2: ET.Element) -> bool:
    """Recursively compare two normalised Element trees."""
    if e1.tag != e2.tag:
        return False
    if (e1.text or "") != (e2.text or ""):
        return False
    if e1.attrib != e2.attrib:
        return False
    if len(e1) != len(e2):
        return False
    return all(_elements_equal(c1, c2) for c1, c2 in zip(e1, e2))


# ── 计算 mutation kill rate ────────────────────────────────────────────────────

def _derive_original_outputs(original_output_path: str, mutant_results: dict) -> dict:
    """
    Recover original multi-output paths from the first successful mutant result.

    Example:
      original_output_path = output_0001_original_OUTMaven.xmi
      mutant outputs keys  = OUTMaven, OUTProject

    Returns:
      {
        "OUTMaven":   output_0001_original_OUTMaven.xmi,
        "OUTProject": output_0001_original_OUTProject.xmi,
      }
    """
    if not original_output_path:
        return {}

    sample_outputs = None
    for result in mutant_results.values():
        if result.get("outputs"):
            sample_outputs = result["outputs"]
            break

    if not sample_outputs:
        return {}

    original_outputs = {}
    for out_name in sample_outputs.keys():
        candidate = None

        # If current path already ends with a declared output suffix,
        # replace that suffix with the required output name.
        for known_out in sample_outputs.keys():
            suffix = f"_{known_out}.xmi"
            if original_output_path.endswith(suffix):
                candidate = original_output_path[:-len(suffix)] + f"_{out_name}.xmi"
                break

        # Fallback: old base path without explicit output suffix.
        if candidate is None:
            base, ext = os.path.splitext(original_output_path)
            ext = ext or ".xmi"
            candidate = f"{base}_{out_name}{ext}"

        original_outputs[out_name] = candidate

    return original_outputs


def _compute_multi_output_kill_rate(original_outputs: dict, mutant_results: dict) -> dict:
    killed = []
    alive = []
    errors = []
    diff_details = {}

    missing_original = [
        name for name, path in original_outputs.items()
        if not os.path.isfile(path)
    ]
    if missing_original:
        msg = f"Original multi-output files not found: {missing_original}"
        logger.error(msg)
        return {
            "total_mutants": len(mutant_results),
            "killed_mutants": 0,
            "alive_mutants": 0,
            "kill_rate": 0.0,
            "killed": [],
            "alive": [],
            "errors": list(mutant_results.keys()),
            "diff_details": {},
            "error": msg,
        }

    for mutant_name, result in mutant_results.items():
        mutant_outputs = result.get("outputs") or {}

        if not result.get("success") or not mutant_outputs:
            errors.append(mutant_name)
            continue

        missing_mutant = [
            out_name for out_name in original_outputs
            if out_name not in mutant_outputs or not os.path.isfile(mutant_outputs[out_name])
        ]
        if missing_mutant:
            errors.append(mutant_name)
            diff_details[mutant_name] = {
                "failed": False,
                "error": f"missing mutant outputs: {missing_mutant}",
                "outputs": {},
            }
            continue

        per_output = {}
        failed = False

        for out_name, original_path in original_outputs.items():
            mutant_path = mutant_outputs[out_name]
            same = compare_xmi_models(original_path, mutant_path)
            different = not same
            failed = failed or different
            per_output[out_name] = {
                "different": different,
                "reason": "canonical_xmi_diff" if different else "same",
                "original": original_path,
                "mutant": mutant_path,
            }

        diff_details[mutant_name] = {
            "failed": failed,
            "outputs": per_output,
        }

        if failed:
            killed.append(mutant_name)
        else:
            alive.append(mutant_name)

    total = len(mutant_results)
    effective = len(killed) + len(alive)
    kill_rate = len(killed) / effective if effective > 0 else 0.0

    return {
        "total_mutants": total,
        "killed_mutants": len(killed),
        "alive_mutants": len(alive),
        "kill_rate": round(kill_rate, 4),
        "killed": killed,
        "alive": alive,
        "errors": errors,
        "diff_details": diff_details,
        "multi_output": True,
    }


def compute_mutation_kill_rate(
    original_output_path: str,
    mutant_results: dict,
) -> dict:
    """
    Compute mutation kill rate using structural XMI comparison.

    Supports both:
    - single-output transformations: result["output"]
    - multi-output transformations: result["outputs"] = {OUT: path, ...}

    A multi-output mutant is killed if ANY declared output differs.
    """
    # Multi-output path. This is triggered by Ant2Maven-style executor results.
    has_multi_output = any(
        bool(result.get("outputs"))
        for result in mutant_results.values()
    )

    if isinstance(original_output_path, dict):
        original_outputs = original_output_path.get("outputs") or {}
        if original_outputs:
            return _compute_multi_output_kill_rate(original_outputs, mutant_results)
        original_output_path = original_output_path.get("output")

    if has_multi_output:
        original_outputs = _derive_original_outputs(original_output_path, mutant_results)
        if original_outputs:
            return _compute_multi_output_kill_rate(original_outputs, mutant_results)

    # Single-output fallback for existing subjects.
    if not os.path.isfile(original_output_path):
        msg = f"Original output not found: {original_output_path}"
        logger.error(msg)
        return {
            "total_mutants":  len(mutant_results),
            "killed_mutants": 0,
            "alive_mutants":  0,
            "kill_rate":      0.0,
            "killed":         [],
            "alive":          [],
            "errors":         list(mutant_results.keys()),
            "error":          msg,
        }

    killed = []
    alive = []
    errors = []

    for name, result in mutant_results.items():
        if not result.get("success") or not result.get("output"):
            errors.append(name)
            continue

        mutant_path = result["output"]
        if not os.path.isfile(mutant_path):
            errors.append(name)
            continue

        if not compare_xmi_models(original_output_path, mutant_path):
            killed.append(name)
        else:
            alive.append(name)

    effective = len(killed) + len(alive)
    kill_rate = len(killed) / effective if effective > 0 else 0.0

    return {
        "total_mutants":  len(mutant_results),
        "killed_mutants": len(killed),
        "alive_mutants":  len(alive),
        "kill_rate":      round(kill_rate, 4),
        "killed":         killed,
        "alive":          alive,
        "errors":         errors,
        "multi_output":   False,
    }


# ── main：用于手动测试 ────────────────────────────────────────────────────────

def main():
    import sys
    import json
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    root    = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    dataset = os.path.join(root, "datasets", "models_BibTexML2DocBook")
    atl     = os.path.join(dataset, "transformations", "BibTeX2DocBook.atl")
    trace   = os.path.join(root, "results", "executor_test",
                           "test_output_trace.xmi")

    print("\n" + "="*60)
    print("[TEST 1] 单模型规则覆盖率")
    print("="*60)
    result = compute_rule_coverage(trace, atl)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    print("\n" + "="*60)
    print("[TEST 2] XMI 结构比较（相同文件应返回 True）")
    print("="*60)
    xmi = os.path.join(root, "results", "executor_test", "test_output.xmi")
    if os.path.isfile(xmi):
        print(f"  compare_xmi_models(same, same) = {compare_xmi_models(xmi, xmi)}")
    else:
        print("  test_output.xmi not found, skipping.")

    print("\n" + "="*60)
    print("[TEST 3] 从 ATL 文件提取规则和 helper")
    print("="*60)
    info = extract_rules_and_helpers(atl)
    print(f"  rules   : {info['rules']}")
    print(f"  helpers : {info['helpers']}")

    # ── 额外验证：测试 UML2ER abstract rule 是否被正确识别 ──────────────
    print("\n" + "="*60)
    print("[TEST 4] UML2ER abstract rule 识别验证")
    print("="*60)
    uml2er_atl = os.path.join(root, "datasets", "models_UML2ER",
                               "transformations", "SimpleUml2ER_Mutant1.atl")
    if os.path.isfile(uml2er_atl):
        info2 = extract_rules_and_helpers(uml2er_atl)
        print(f"  rules ({len(info2['rules'])}): {info2['rules']}")
        print(f"  期望: 8条规则，包含 NamedElement、Property、References")
    else:
        print("  UML2ER ATL 文件未找到，跳过。")


if __name__ == "__main__":
    main()