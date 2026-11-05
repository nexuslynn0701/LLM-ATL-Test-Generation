# src/analyzer/oracle_evaluator.py
#
# RQ3: Oracle Quality Evaluation
#
# Compares the LLM-generated DocBook target model (oracle) against the
# actual ATL transformation output to measure oracle accuracy.
#
# Metrics:
#   oracle_accuracy      : fraction of models where oracle == actual output
#   avg_similarity       : mean element-level similarity score (0.0 – 1.0)

import logging
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Namespace normalisation ────────────────────────────────────────────────────

_NS_RE = re.compile(r'\{[^}]+\}')

def _strip_ns(tag: str) -> str:
    """Remove XML namespace URI from a tag, keeping only the local name."""
    return _NS_RE.sub('', tag)


# ── Element-level structural similarity ───────────────────────────────────────

def _get_all_elements(root: ET.Element) -> list[dict]:
    """
    Flatten an XML tree into a list of normalised element descriptors.

    Normalisation applied:
    - namespace URIs stripped from tags
    - xmi:id and similar id attributes removed
    - attributes sorted by key
    - text whitespace stripped
    """
    _ID_KEYS = {"xmi:id", "id"}

    records = []
    for elem in root.iter():
        attribs = {}
        for k, v in elem.attrib.items():
            local_k = _strip_ns(k)
            if local_k in _ID_KEYS:
                continue
            attribs[local_k] = v

        records.append({
            "tag":     _strip_ns(elem.tag),
            "attribs": dict(sorted(attribs.items())),
            "text":    (elem.text or "").strip(),
        })
    return records


def compute_structural_similarity(path1: str, path2: str) -> float:
    """
    Compute an element-level structural similarity score between two XMI files.

    Score = matched_elements / max(len(elements_in_path1),
                                   len(elements_in_path2))

    Namespaces are stripped before comparison so DocBook::DocBook matches
    regardless of namespace prefix differences between oracle and actual output.

    Returns a float in [0.0, 1.0], or 0.0 on parse error.
    """
    try:
        elems1 = _get_all_elements(ET.parse(path1).getroot())
        elems2 = _get_all_elements(ET.parse(path2).getroot())
    except ET.ParseError as e:
        logger.warning(f"XML parse error during similarity: {e}")
        return 0.0
    except Exception as e:
        logger.warning(f"Failed to read file for similarity: {e}")
        return 0.0

    if not elems1 or not elems2:
        return 0.0

    shorter, longer = ((elems1, elems2) if len(elems1) <= len(elems2)
                       else (elems2, elems1))

    longer_copy = list(longer)
    matched = 0
    for elem in shorter:
        if elem in longer_copy:
            longer_copy.remove(elem)
            matched += 1

    return round(matched / max(len(elems1), len(elems2)), 4)


# ── Oracle accuracy (exact structural match) ──────────────────────────────────

def evaluate_oracle(
    oracle_path: str,
    actual_path: str,
) -> dict:
    """
    Evaluate a single LLM-generated oracle against the ATL actual output.

    Parameters
    ----------
    oracle_path : LLM-generated DocBook XMI (expected output)
    actual_path : ATL transformation output XMI (ground truth)

    Returns
    -------
    {
        "oracle_correct":  bool,
        "similarity":      float,
        "oracle_elements": int,
        "actual_elements": int,
        "oracle_path":     str,
        "actual_path":     str,
        "error":           str | None,
    }
    """
    for path, label in [(oracle_path, "oracle"), (actual_path, "actual")]:
        if not os.path.isfile(path):
            return {
                "oracle_correct":  False,
                "similarity":      0.0,
                "oracle_elements": 0,
                "actual_elements": 0,
                "oracle_path":     oracle_path,
                "actual_path":     actual_path,
                "error":           f"{label} file not found: {path}",
            }

    try:
        oracle_elems = _get_all_elements(ET.parse(oracle_path).getroot())
        actual_elems = _get_all_elements(ET.parse(actual_path).getroot())
    except ET.ParseError as e:
        return {
            "oracle_correct":  False,
            "similarity":      0.0,
            "oracle_elements": 0,
            "actual_elements": 0,
            "oracle_path":     oracle_path,
            "actual_path":     actual_path,
            "error":           f"XML parse error: {e}",
        }

    similarity     = compute_structural_similarity(oracle_path, actual_path)
    oracle_correct = similarity >= 1.0

    logger.info(
        f"[oracle_evaluator] {Path(oracle_path).name} | "
        f"correct={oracle_correct} | similarity={similarity:.2%} | "
        f"oracle_elems={len(oracle_elems)} actual_elems={len(actual_elems)}"
    )

    return {
        "oracle_correct":   oracle_correct,
        "similarity":       similarity,
        "oracle_elements":  len(oracle_elems),
        "actual_elements":  len(actual_elems),
        "oracle_path":      oracle_path,
        "actual_path":      actual_path,
        "error":            None,
    }


# ── Batch evaluation ───────────────────────────────────────────────────────────

def evaluate_oracle_batch(pairs: list[tuple[str, str]]) -> dict:
    """
    Evaluate multiple (oracle_path, actual_path) pairs.

    Returns
    -------
    {
        "total":           int,
        "correct":         int,
        "oracle_accuracy": float,
        "avg_similarity":  float,
        "per_model":       [ evaluate_oracle() result dict, ... ],
    }
    """
    results = []
    correct = 0
    sims    = []

    for oracle_path, actual_path in pairs:
        result = evaluate_oracle(oracle_path, actual_path)
        results.append(result)
        if result["oracle_correct"]:
            correct += 1
        if result["error"] is None:
            sims.append(result["similarity"])

    total    = len(pairs)
    accuracy = correct / total  if total > 0 else 0.0
    avg_sim  = sum(sims) / len(sims) if sims  else 0.0

    return {
        "total":           total,
        "correct":         correct,
        "oracle_accuracy": round(accuracy, 4),
        "avg_similarity":  round(avg_sim,  4),
        "per_model":       results,
    }


# ── Integration helper ─────────────────────────────────────────────────────────

def evaluate_oracles_for_config(
    config_name: str,
    results_dir: str = "results",
    n_models: int = 10,
) -> dict:
    """
    Evaluate all oracles for a given experiment config using the standard
    directory layout:

        results/generated_models/{config}/target_model_{id}.xmi  ← oracle
        results/outputs/{config}/output_{id}.xmi                 ← actual ATL output
    """
    base   = Path(results_dir)
    gen    = base / "generated_models" / config_name
    actual = base / "outputs"          / config_name

    pairs = []
    for i in range(1, n_models + 1):
        index    = f"{i:04d}"
        oracle_p = str(gen    / f"target_model_{index}.xmi")
        actual_p = str(actual / f"output_{index}.xmi")
        pairs.append((oracle_p, actual_p))

    summary = evaluate_oracle_batch(pairs)

    print(f"\nOracle evaluation — config={config_name}")
    print(f"  Total            : {summary['total']}")
    print(f"  Correct oracles  : {summary['correct']}")
    print(f"  Oracle accuracy  : {summary['oracle_accuracy']:.2%}")
    print(f"  Avg similarity   : {summary['avg_similarity']:.2%}")

    return summary


# ── main ───────────────────────────────────────────────────────────────────────

def main():
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    root    = Path(__file__).resolve().parents[2]
    gen_dir = root / "results" / "generated_models" / "core"
    out_dir = root / "results" / "outputs"           / "core"

    if not gen_dir.exists() or not out_dir.exists():
        print("No experiment results found. Run multi_config_experiment.py first.")
        return

    pairs = []
    for oracle in sorted(gen_dir.glob("target_model_*.xmi")):
        index  = oracle.stem.replace("target_model_", "")
        actual = out_dir / f"output_{index}.xmi"
        if actual.is_file():
            pairs.append((str(oracle), str(actual)))

    if not pairs:
        print("No matching oracle/actual pairs found.")
        return

    print(f"Evaluating {len(pairs)} oracle/actual pair(s)…")
    summary = evaluate_oracle_batch(pairs)

    print(f"\nRQ3 Oracle Quality Summary")
    print(f"  Total          : {summary['total']}")
    print(f"  Correct        : {summary['correct']}")
    print(f"  Accuracy       : {summary['oracle_accuracy']:.2%}")
    print(f"  Avg similarity : {summary['avg_similarity']:.2%}")
    print()
    for r in summary["per_model"]:
        name = Path(r["oracle_path"]).name
        if r["error"]:
            print(f"  {name}: ERROR — {r['error']}")
        else:
            print(f"  {name}: correct={r['oracle_correct']} | "
                  f"similarity={r['similarity']:.2%} | "
                  f"oracle_elems={r['oracle_elements']} "
                  f"actual_elems={r['actual_elements']}")


if __name__ == "__main__":
    main()