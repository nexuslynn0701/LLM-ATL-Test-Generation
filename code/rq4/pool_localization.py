"""Pool Top-1 and tie-mid EXAM values using exact fractions; CSV computation only."""
import csv

from pathlib import Path

from fractions import Fraction as F

from decimal import Decimal, localcontext, ROUND_HALF_EVEN

from collections import defaultdict

BUNDLE = Path(__file__).resolve().parents[2]

RQ3_MLE = BUNDLE / 'results/experiment_results/RQ3/mutant_level_exam.csv'

RQ4_DATA = BUNDLE / 'results/experiment_results/RQ4'

RQ4_SUPP = BUNDLE / 'results' / 'rq4' / 'supplementary'

P = ['GPT', 'Qwen', 'DeepSeek']

C = ['sm', 'stm', 'astm', 'astmo']

METRICS4 = ['Validity', 'Coverage', 'Mutation', 'Failure']

def dec(x):
    with localcontext() as ctx:
        ctx.prec = 60
        return Decimal(x.numerator) / Decimal(x.denominator)

def fmt(x, n=2):
    return str(dec(x).quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_EVEN))

def signed(x):
    r = fmt(x)
    return ('+' if not r.startswith('-') else '') + r

def read(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def pooled_top1_exam():
    rows = read(RQ3_MLE)
    acc = defaultdict(lambda: [0, F(0), 0])  # hits, exam sum, n
    for r in rows:
        if r['provider'] in P and r['condition'] in C and r['evaluable'] == '1':
            raw = F(r['exam_ac'])
            bound = 2 * int(r['rule_count']) * int(r['n_faulty_rules'])
            exam = F(round(raw * bound), bound)
            a = acc[(r['provider'], r['condition'])]
            a[0] += 1 if F(r['best_rank']) <= 1 else 0
            a[1] += exam
            a[2] += 1
    return {(p, c): dict(n=acc[(p, c)][2], top1_hits=acc[(p, c)][0],
                         top1=F(acc[(p, c)][0] * 100, acc[(p, c)][2]),
                         exam=acc[(p, c)][1] / acc[(p, c)][2])
            for p in P for c in C}
