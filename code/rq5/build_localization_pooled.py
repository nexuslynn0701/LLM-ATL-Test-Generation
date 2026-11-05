"""Rebuild Tables 16/17 from shipped mutant-level localization records.

No ATL replay or plotting is performed. Default output stays under rebuild/.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from fractions import Fraction
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'results/rq3/data/mutant_level_exam.csv'
OUTPUT = ROOT / 'rebuild/rq5/pooled_overall_by_formula.csv'
FORMULAS = [
    ('ochiai', 'Ochiai'), ('tarantula', 'Tarantula'), ('dstar2', 'DStar2'),
    ('kulczynski2', 'Kulczynski2'), ('mountford', 'Mountford'), ('zoltar', 'Zoltar'),
    ('arithmetic_mean', 'ArithmeticMean'), ('barinel', 'Barinel'),
    ('braun_banquet', 'BraunBanquet'), ('baroni_urbani_buser', 'BaroniUrbaniBuser'),
    ('cohen', 'Cohen'), ('ochiai2', 'Ochiai2'), ('op2', 'OP2'), ('phi', 'Phi'),
    ('pierce', 'Pierce'), ('rogers_tanimoto', 'RogersTanimoto'),
    ('russell_rao', 'RussellRao'), ('simple_matching', 'SimpleMatching'),
]
LLMS = ('GPT', 'Qwen', 'DeepSeek')
CONDITIONS = (('astmo', 'ASTMO'), ('workflow', 'FD-ASTMO'))
SUBJECTS = {'Ant2Maven', 'BibTeX2DocBook', 'CPL2SPL', 'Ecore2Maude',
            'Grafcet2PetriNet', 'UML2ER'}


def fmt(value, places=15):
    with localcontext() as ctx:
        ctx.prec = 60
        return str((Decimal(value.numerator) / Decimal(value.denominator))
                   .quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_EVEN))


def build(source=SOURCE):
    groups = defaultdict(list)
    seen = set()
    with Path(source).open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            if (row['provider'] not in LLMS or row['condition'] not in {'astmo', 'workflow'}
                    or row['evaluable'] != '1'):
                continue
            key = (row['formula'], row['provider'], row['condition'])
            identity = (*key, row['subject'], row['mutant_id'])
            if identity in seen or row['subject'] not in SUBJECTS:
                raise ValueError(f'Duplicate or unknown localization observation: {identity}')
            seen.add(identity)
            denominator = 2 * int(row['rule_count']) * int(row['n_faulty_rules'])
            raw = Fraction(row['exam_ac'])
            exact = Fraction(round(raw * denominator), denominator)
            if abs(raw - exact) > Fraction(1, 10**10) or not 0 < exact <= 1:
                raise ValueError(f'Invalid EXAM precision or value: {identity}')
            groups[key].append((row['subject'], exact, Fraction(row['best_rank']) <= 1))
    expected = {(f, p, c) for f, _ in FORMULAS for p in LLMS for c, _ in CONDITIONS}
    if set(groups) != expected:
        raise ValueError('Expected all 108 formula/LLM/condition groups')
    result = []
    for formula, label in FORMULAS:
        for llm in LLMS:
            for condition, display in CONDITIONS:
                observations = groups[formula, llm, condition]
                observed = {s for s, _, _ in observations}
                required = SUBJECTS - {'CPL2SPL'} if (llm, condition) == ('Qwen', 'astmo') else SUBJECTS
                if observed != required:
                    raise ValueError(f'Unexpected subject coverage: {formula}/{llm}/{condition}')
                values = [v for _, v, _ in observations]
                n = len(values)
                hits = sum(hit for _, _, hit in observations)
                top = Fraction(hits, n)
                mean = sum(values, Fraction(0)) / n
                med = median(values)
                result.append(dict(formula=label, llm=llm, condition=display,
                    n_subjects_in_design=6, n_subjects_with_evaluable_mutants=len(observed),
                    n_evaluable=n, top1_hits=hits, top1_pct=fmt(100 * top),
                    exam_ac_mean=fmt(mean), exam_ac_median=fmt(med),
                    top1_numerator=top.numerator, top1_denominator=top.denominator,
                    exam_mean_numerator=mean.numerator, exam_mean_denominator=mean.denominator,
                    exam_median_numerator=med.numerator, exam_median_denominator=med.denominator,
                    top1_display=fmt(100 * top, 2), exam_mean_display=fmt(mean, 2),
                    exam_median_display=fmt(med, 2)))
    return result


def write(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=SOURCE)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows = build(args.input)
    write(args.output, rows)
    print(f'Wrote {len(rows)} rows (Tables 16/17) to {args.output}')
