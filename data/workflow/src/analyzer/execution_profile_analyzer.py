# src/analyzer/execution_profile_analyzer.py
#
# Utilities for tracking and analysing execution profiles across
# LLM-generated test models.  Used by the SAT_AWARE feedback strategy
# to detect failure saturation and guide distribution-aware generation.
#
# Only Python standard library is used.

from collections import Counter
from typing import Dict, Iterable, List, Optional, Tuple


def normalize_rule_set(rule_set: Iterable[str]) -> Tuple[str, ...]:
    """
    Return a sorted, hashable representation of a rule set.

    Parameters
    ----------
    rule_set : iterable of rule name strings

    Returns
    -------
    tuple[str] — sorted tuple, safe to use as dict key or set element
    """
    return tuple(sorted(set(rule_set)))


def collect_recent_profiles(
    profile_history: List[Iterable[str]],
    window_size: int = 10,
) -> List[Tuple[str, ...]]:
    """
    Return the most recent `window_size` execution profiles as normalised tuples.

    Parameters
    ----------
    profile_history : list of rule sets (each is a set/list of rule names)
    window_size     : how many recent profiles to consider

    Returns
    -------
    list[tuple[str]] — up to window_size most recent normalised profiles
    """
    if not profile_history:
        return []
    return [normalize_rule_set(p) for p in profile_history[-window_size:]]


def get_frequent_rules(
    profile_history: List[Iterable[str]],
    threshold: float = 0.7,
    window_size: int = 10,
) -> Dict[str, float]:
    """
    Return rules whose per-profile occurrence frequency exceeds `threshold`.

    Frequency is computed over the most recent `window_size` profiles.
    A rule counts once per profile regardless of repetition.

    Parameters
    ----------
    profile_history : list of rule sets
    threshold       : minimum frequency (0–1) to include a rule
    window_size     : look-back window

    Returns
    -------
    dict {rule_name: frequency}.  Returns {} if profile_history is empty.
    """
    recent = collect_recent_profiles(profile_history, window_size)
    if not recent:
        return {}
    n = len(recent)
    counts: Counter = Counter()
    for profile in recent:
        for rule in profile:
            counts[rule] += 1
    return {rule: cnt / n for rule, cnt in counts.items() if cnt / n >= threshold}


def get_frequent_rule_combinations(
    profile_history: List[Iterable[str]],
    top_k: int = 3,
    window_size: int = 10,
) -> List[Dict]:
    """
    Return the top-k most common complete execution profiles (rule sets).

    Parameters
    ----------
    profile_history : list of rule sets
    top_k           : number of top profiles to return
    window_size     : look-back window

    Returns
    -------
    list of dicts with keys: "rules" (list[str]), "count" (int), "ratio" (float).
    Returns [] if profile_history is empty.
    """
    recent = collect_recent_profiles(profile_history, window_size)
    if not recent:
        return []
    n = len(recent)
    counts: Counter = Counter(recent)
    return [
        {"rules": list(profile), "count": cnt, "ratio": cnt / n}
        for profile, cnt in counts.most_common(top_k)
    ]


def compute_profile_diversity(
    profile_history: List[Iterable[str]],
    window_size: int = 10,
) -> float:
    """
    Compute the mean pairwise Jaccard distance between recent execution profiles.

    Jaccard distance = 1 - |A ∩ B| / |A ∪ B|.
    Higher values indicate more diverse execution profiles.

    Parameters
    ----------
    profile_history : list of rule sets
    window_size     : look-back window

    Returns
    -------
    float in [0.0, 1.0].  Returns 0.0 if fewer than 2 profiles.
    """
    recent = collect_recent_profiles(profile_history, window_size)
    if len(recent) < 2:
        return 0.0
    sets = [set(p) for p in recent]
    distances = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            a, b = sets[i], sets[j]
            union = a | b
            distances.append(0.0 if not union else 1.0 - len(a & b) / len(union))
    return sum(distances) / len(distances) if distances else 0.0


def build_saturation_feedback_context(
    profile_history: List[Iterable[str]],
    all_rules: Optional[Iterable[str]] = None,
    window_size: int = 10,
    freq_threshold: float = 0.7,
    top_k_combinations: int = 3,
) -> Dict:
    """
    Build a saturation-aware feedback context dict from execution history.

    Main entry point for the SAT_AWARE prompt builder.  Summarises recent
    profile statistics into a single dict consumed by
    `build_saturation_aware_hint()` in prompt_builder.py.

    Parameters
    ----------
    profile_history    : list of per-model fired-rule sets (chronological)
    all_rules          : full rule list for the dataset (unused, reserved)
    window_size        : look-back window for all computations
    freq_threshold     : threshold for classifying a rule as "frequent"
    top_k_combinations : how many top profiles to report

    Returns
    -------
    {
        "frequent_rules":        {rule: freq},
        "frequent_combinations": [{rules, count, ratio}, ...],
        "profile_diversity":     float,
        "num_profiles":          int,
        "window_size":           int,
    }
    Returns safe empty defaults when profile_history is empty.
    """
    if not profile_history:
        return {
            "frequent_rules":        {},
            "frequent_combinations": [],
            "profile_diversity":     0.0,
            "num_profiles":          0,
            "window_size":           window_size,
        }
    return {
        "frequent_rules":        get_frequent_rules(
            profile_history, freq_threshold, window_size),
        "frequent_combinations": get_frequent_rule_combinations(
            profile_history, top_k_combinations, window_size),
        "profile_diversity":     compute_profile_diversity(
            profile_history, window_size),
        "num_profiles":          len(profile_history),
        "window_size":           window_size,
    }