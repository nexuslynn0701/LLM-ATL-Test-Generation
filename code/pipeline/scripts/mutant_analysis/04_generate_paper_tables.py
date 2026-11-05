#!/usr/bin/env python3
"""
04_generate_paper_tables.py
===========================
Generate LaTeX tables for the TOSEM paper from the analysis outputs.

Tables produced
~~~~~~~~~~~~~~~
  Table A  – Mutant classification breakdown (main paper, per-dataset)
             Columns: Dataset | Generated | Compile-failed | Stillborn |
                      Runnable | Killed | Surv-Uncov | Surv-Cov |
                      Susp-Equiv | Effective | MS_nom | MS_eff

  Table B  – Mutation operator breakdown (supplementary / appendix)
             Columns: Operator | Equiv-prone | Run | Killed | Surv | KillRate

  Table C  – Sensitivity analysis (main paper or appendix)
             Columns: Dataset | MS_nominal | MS_excl_SuspEq | Δ | Stable?

All tables are written to:
  results_v2/analysis/paper_tables/
    table_mutant_classification.tex
    table_operator_breakdown.tex
    table_sensitivity.tex

Usage
~~~~~
  python 04_generate_paper_tables.py [--base BASE_DIR]
"""

import argparse
import csv
import json
from pathlib import Path

DEFAULT_BASE = Path.home() / "research" / "llm_mt_experiment"
DATASETS     = ["BibTeX2DocBook", "CPL2SPL", "UML2ER", "Ecore2Maude"]

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _v(x, fmt=None):
    """Format value; return '–' if None/empty."""
    if x is None or x == "":
        return "--"
    if fmt:
        return fmt.format(x)
    return str(x)

def _pct(x):
    if x is None:
        return "--"
    try:
        return f"{float(x)*100:.1f}\\%"
    except (ValueError, TypeError):
        return "--"

def _load_json(path: Path) -> list | dict | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)

def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ──────────────────────────────────────────────────────────────────────────────
# Table A – Mutant classification
# ──────────────────────────────────────────────────────────────────────────────

TABLE_A_TEMPLATE = r"""
% ── Table A: Mutant Classification Breakdown ──────────────────────────────
% Paste into your paper. Requires booktabs package.
\begin{table}[tbp]
\centering
\caption{Mutant Classification Breakdown per Subject Transformation.
  \textit{Susp-Eq} = survived with mutant location covered (suspected equivalent);
  \textit{Uncov}   = survived with mutant location not covered (not triggered);
  \textit{Eff.}    = runnable $-$ Susp-Eq (effective mutants);
  $MS_{nom}$       = killed / runnable;
  $MS_{eff}$       = killed / Eff.}
\label{tab:mutant_classification}
\small
\begin{tabular}{@{}lrrrrrrrrrr@{}}
\toprule
\textbf{Subject} &
  \textbf{Gen.} &
  \textbf{CF} &
  \textbf{SB} &
  \textbf{Run.} &
  \textbf{Killed} &
  \textbf{Uncov} &
  \textbf{Susp-Eq} &
  \textbf{Eff.} &
  $\mathbf{MS_{nom}}$ &
  $\mathbf{MS_{eff}}$ \\
\midrule
{ROWS}
\midrule
{TOTAL_ROW}
\bottomrule
\end{tabular}
\end{table}
"""

def build_table_a(cov_dir: Path, se_dir: Path) -> str:
    rows = []
    totals = {k: 0 for k in [
        "total", "cf", "sb", "run", "killed", "uncov", "se", "eff"
    ]}

    for ds in DATASETS:
        # Load coverage aggregate
        cov_agg_path = cov_dir / f"{ds}_coverage_aggregate.json"
        cov_agg = _load_json(cov_agg_path)

        # Load sensitivity
        sens_path = se_dir / f"{ds}_sensitivity.json"
        sens = _load_json(sens_path)

        if not cov_agg or not sens:
            rows.append(f"  {ds} & \\multicolumn{{9}}{{c}}{{data not available}} \\\\")
            continue

        gen   = cov_agg.get("total_mutants_seen",  0)
        cf    = cov_agg.get("compile_failed",       0)
        sb    = cov_agg.get("stillborn",            0)
        run   = sens.get("runnable_nominal",        0)
        kil   = sens.get("killed",                  0)
        uncov = sens.get("survived_uncovered",      0)
        se    = sens.get("suspected_equivalent",    0)
        eff   = sens.get("effective_mutants",       0)
        ms_n  = sens.get("ms_nominal")
        ms_e  = sens.get("ms_effective")

        totals["total"] += gen
        totals["cf"]    += cf
        totals["sb"]    += sb
        totals["run"]   += run
        totals["killed"]+= kil
        totals["uncov"] += uncov
        totals["se"]    += se
        totals["eff"]   += eff

        rows.append(
            f"  {ds} & {gen} & {cf} & {sb} & {run} & "
            f"{kil} & {uncov} & {se} & {eff} & "
            f"{_pct(ms_n)} & {_pct(ms_e)} \\\\"
        )

    row_text = "\n".join(rows)

    # Totals row
    t = totals
    ms_n_t = _pct(t["killed"] / t["run"] if t["run"] else None)
    ms_e_t = _pct(t["killed"] / t["eff"] if t["eff"] else None)
    total_row = (
        f"  \\textbf{{Total}} & \\textbf{{{t['total']}}} & "
        f"\\textbf{{{t['cf']}}} & \\textbf{{{t['sb']}}} & "
        f"\\textbf{{{t['run']}}} & \\textbf{{{t['killed']}}} & "
        f"\\textbf{{{t['uncov']}}} & \\textbf{{{t['se']}}} & "
        f"\\textbf{{{t['eff']}}} & "
        f"\\textbf{{{ms_n_t}}} & \\textbf{{{ms_e_t}}} \\\\"
    )

    return TABLE_A_TEMPLATE.replace("{ROWS}", row_text).replace("{TOTAL_ROW}", total_row)


# ──────────────────────────────────────────────────────────────────────────────
# Table B – Operator breakdown (cross-dataset aggregate)
# ──────────────────────────────────────────────────────────────────────────────

TABLE_B_TEMPLATE = r"""
% ── Table B: Mutation Operator Breakdown ─────────────────────────────────
% Place in appendix or Section 5.
% * = operator documented as equivalence-prone in mutation testing literature.
\begin{table}[tbp]
\centering
\caption{Kill and survival rates by mutation operator across all subjects.
  Operators marked $^*$ are known to produce equivalence-prone mutants.}
\label{tab:operator_breakdown}
\small
\begin{tabular}{@{}lcrrrrrr@{}}
\toprule
\textbf{Operator} &
  \textbf{Eq.} &
  \textbf{Run.} &
  \textbf{Killed} &
  \textbf{Surv.} &
  \textbf{Surv-Cov} &
  \textbf{Kill Rate} &
  \textbf{Surv Rate} \\
\midrule
{ROWS}
\bottomrule
\end{tabular}
\end{table}
"""

OP_SHORTNAMES = {
    "rule_deletion":              "RD",
    "binding_feature_change":     "BFC",
    "binding_value_change":       r"BVC$^*$",
    "guard_mutation":             "GM",
    "navigation_mutation":        r"NM$^*$",
    "helper_expression_mutation": r"HEM$^*$",
    "unknown_operator":           "UNK",
}

def build_table_b(mt_dir: Path) -> str:
    overall = _load_json(mt_dir / "operator_breakdown_overall.json")
    if not overall:
        return "% operator_breakdown_overall.json not found – run 02_mutant_type_breakdown.py\n"

    rows = []
    for r in overall:
        op_key   = r["mutation_op"]
        op_short = OP_SHORTNAMES.get(op_key, op_key)
        ep       = r.get("equiv_prone", "no")
        ep_mark  = "$\\checkmark$" if ep == "yes" else ""
        run      = r["runnable"]
        kil      = r["killed"]
        surv     = r["survived_total"]
        scov     = r.get("survived_covered", 0)
        kr       = _pct(r["kill_rate"])
        sr       = _pct(r["survival_rate"])
        rows.append(
            f"  {op_short} & {ep_mark} & {run} & {kil} & {surv} & {scov} & {kr} & {sr} \\\\"
        )

    return TABLE_B_TEMPLATE.replace("{ROWS}", "\n".join(rows))


# ──────────────────────────────────────────────────────────────────────────────
# Table C – Sensitivity analysis
# ──────────────────────────────────────────────────────────────────────────────

TABLE_C_TEMPLATE = r"""
% ── Table C: Sensitivity Analysis ────────────────────────────────────────
\begin{table}[tbp]
\centering
\caption{Sensitivity analysis: mutation score with and without suspected-equivalent
  mutants excluded. $MS_{nom}$ = killed / runnable; $MS_{eff}$ = killed /
  (runnable $-$ suspected-equivalent); $\Delta$ = $|MS_{nom} - MS_{eff}|$.
  ``Stable'' = $\Delta < 0.05$.}
\label{tab:sensitivity}
\small
\begin{tabular}{@{}lrrrrr@{}}
\toprule
\textbf{Subject} &
  \textbf{Run.} &
  $\mathbf{MS_{nom}}$ &
  $\mathbf{MS_{eff}}$ &
  $\boldsymbol{\Delta}$ &
  \textbf{Stable?} \\
\midrule
{ROWS}
\bottomrule
\end{tabular}
\end{table}
"""

def build_table_c(se_dir: Path) -> str:
    rows = []
    for ds in DATASETS:
        sens = _load_json(se_dir / f"{ds}_sensitivity.json")
        if not sens:
            rows.append(f"  {ds} & \\multicolumn{{4}}{{c}}{{n/a}} \\\\")
            continue
        run  = sens.get("runnable_nominal", 0)
        ms_n = _pct(sens.get("ms_nominal"))
        ms_e = _pct(sens.get("ms_excl_suspected_equiv"))
        dlt  = _pct(sens.get("ms_delta"))
        stab = sens.get("conclusion_stable", "--")
        if stab == "yes":
            stab = r"\checkmark"
        elif stab == "check_carefully":
            stab = r"\textbf{!}"
        rows.append(f"  {ds} & {run} & {ms_n} & {ms_e} & {dlt} & {stab} \\\\")

    return TABLE_C_TEMPLATE.replace("{ROWS}", "\n".join(rows))


# ──────────────────────────────────────────────────────────────────────────────
# Additional: textual description for inline LaTeX paragraph
# ──────────────────────────────────────────────────────────────────────────────

def build_inline_description(cov_dir: Path, se_dir: Path, mt_dir: Path) -> str:
    lines = [
        "% ── Inline paragraph template for Section 5 / Threats to Validity ──────",
        "%",
        "% Copy and adapt the following paragraph:",
        "%",
        r"\paragraph{Equivalent Mutant Threat.}",
        r"To mitigate the equivalent mutant threat, we classify survived mutants",
        r"into two categories based on rule-coverage evidence.",
        r"A mutant whose injected rule is \emph{not} exercised by any test in the",
        r"union pool is labelled \textit{survived\_uncovered} and is likely never",
        r"triggered; its survival does not indicate a weakness in the test oracle.",
        r"A mutant whose location \emph{is} covered yet still survives all",
        r"generated tests is labelled \textit{suspected\_equivalent}, following",
        r"the convention recommended for fault-based testing studies",
        r"\cite{yao2014study,just2014mutants}.",
        r"We do not claim formal equivalence, as deciding semantic equivalence",
        r"of ATL transformations is undecidable in general.",
        r"Table~\ref{tab:mutant_classification} shows the full breakdown.",
        r"The sensitivity analysis (Table~\ref{tab:sensitivity}) confirms that",
        r"the mutation scores reported in our main results change by at most",
        r"$\Delta$ percentage points when suspected-equivalent mutants are",
        r"excluded, indicating that our conclusions are robust to this threat.",
        "%",
    ]
    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Generate LaTeX tables for TOSEM paper")
    parser.add_argument("--base", default=str(DEFAULT_BASE))
    args = parser.parse_args()

    base       = Path(args.base).expanduser()
    results_v2 = base / "results_v2"
    cov_dir    = results_v2 / "analysis" / "coverage"
    se_dir     = results_v2 / "analysis" / "suspected_equiv"
    mt_dir     = results_v2 / "analysis" / "mutation_types"
    out_dir    = results_v2 / "analysis" / "paper_tables"
    out_dir.mkdir(parents=True, exist_ok=True)

    tables = {
        "table_mutant_classification.tex": build_table_a(cov_dir, se_dir),
        "table_operator_breakdown.tex":    build_table_b(mt_dir),
        "table_sensitivity.tex":           build_table_c(se_dir),
        "inline_paragraph_template.tex":   build_inline_description(cov_dir, se_dir, mt_dir),
    }

    for fname, content in tables.items():
        path = out_dir / fname
        path.write_text(content, encoding="utf-8")
        print(f"  Wrote {path}")

    print(f"\nDone. LaTeX tables in: {out_dir}")
    print("\n  Usage in your paper:")
    print("  \\input{table_mutant_classification}")
    print("  \\input{table_operator_breakdown}  % appendix")
    print("  \\input{table_sensitivity}")
    print("  -- see inline_paragraph_template.tex for the threat-to-validity paragraph --")


if __name__ == "__main__":
    main()