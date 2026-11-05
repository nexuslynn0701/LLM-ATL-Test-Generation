from pathlib import Path
import csv
import random
import difflib
import re

SEED = 20260529
N = 10

SUBJECTS = {
    "BibTeX2DocBook": {
        "dir": Path("datasets/models_BibTexML2DocBook/transformations"),
        "original": "BibTeX2DocBook.atl",
    },
    "CPL2SPL": {
        "dir": Path("datasets/models_CPL2SPL/transformations"),
        "original": "CPL2SPL.atl",
    },
    "UML2ER": {
        "dir": Path("datasets/models_UML2ER/transformations"),
        "original": "SimpleUml2ER.atl",
    },
    "Ecore2Maude": {
        "dir": Path("datasets/models_Ecore2Maude/transformations"),
        "original": "Ecore2Maude.atl",
    },
}

audit = Path("results/mutant_audit/mutant_operator_comment_audit.csv")
out_dir = Path("results/mutant_audit/multi_operator_inspection")
out_dir.mkdir(parents=True, exist_ok=True)

rows = []
with audit.open(newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        if row["primary_operator"] == "multi_operator":
            rows.append(row)

random.seed(SEED)
sample = random.sample(rows, min(N, len(rows)))

summary_rows = []

for row in sample:
    subject = row["subject"]
    mutant = row["mutant"]
    cfg = SUBJECTS[subject]

    orig_path = cfg["dir"] / cfg["original"]
    mut_path = cfg["dir"] / f"{mutant}.atl"

    orig_lines = orig_path.read_text(encoding="utf-8", errors="replace").splitlines()
    mut_lines = mut_path.read_text(encoding="utf-8", errors="replace").splitlines()

    diff_lines = list(difflib.unified_diff(
        orig_lines,
        mut_lines,
        fromfile=str(orig_path),
        tofile=str(mut_path),
        lineterm=""
    ))

    hunk_count = sum(1 for line in diff_lines if line.startswith("@@"))

    mutation_comment_lines = [
        line.strip()
        for line in mut_lines
        if "mutation" in line.lower() or "mutant" in line.lower()
    ]

    out_path = out_dir / f"{subject}__{mutant}.diff"
    out_path.write_text("\n".join(diff_lines) + "\n", encoding="utf-8")

    summary_rows.append({
        "subject": subject,
        "mutant": mutant,
        "operators_from_comment": row["operators"],
        "hunk_count": hunk_count,
        "comment_count": len(mutation_comment_lines),
        "diff_file": str(out_path),
        "comment_preview": " || ".join(mutation_comment_lines[:8]),
    })

summary_path = out_dir / "inspection_summary.csv"
with summary_path.open("w", newline="", encoding="utf-8") as f:
    fieldnames = [
        "subject", "mutant", "operators_from_comment", "hunk_count",
        "comment_count", "diff_file", "comment_preview"
    ]
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(summary_rows)

print("sampled:", len(sample))
print("summary:", summary_path)
for r in summary_rows:
    print()
    print(f"{r['subject']} / {r['mutant']}")
    print(f"  operators: {r['operators_from_comment']}")
    print(f"  hunks:     {r['hunk_count']}")
    print(f"  comments:  {r['comment_count']}")
    print(f"  diff:      {r['diff_file']}")
    print(f"  preview:   {r['comment_preview'][:500]}")
