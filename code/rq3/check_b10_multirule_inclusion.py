"""B10 check: does published pooled Top-1/EXAM include multi-faulty-rule mutants?

Read-only against results/rq3/data; prints published vs include/exclude variants.
"""
import csv
from pathlib import Path
from fractions import Fraction as F

D = Path(__file__).resolve().parents[2] / 'results' / 'rq3' / 'data'
rows = list(csv.DictReader((D / 'mutant_level_exam.csv').open(encoding='utf-8-sig')))


def grid(r, name='exam_ac'):
    d = 2 * int(r['rule_count']) * int(r['n_faulty_rules'])
    v = F(r[name])
    x = F(round(v * d), d)
    assert abs(v - x) <= F(1, 10**10)
    return x


P = ['GPT', 'Qwen', 'DeepSeek']
C = ['sm', 'stm', 'astm', 'astmo']
LEGACY = {'BibTeX2DocBook', 'CPL2SPL', 'UML2ER', 'Ecore2Maude'}


def pooled(pool_filter, formula='ochiai'):
    out = {}
    for p in P:
        for c in C:
            rs = [r for r in rows
                  if r['provider'] == p and r['condition'] == c
                  and r['formula'] == formula and r['evaluable'] == '1'
                  and pool_filter(r)]
            if not rs:
                continue
            top = 100 * sum(F(int(F(r['best_rank']) <= 1)) for r in rs) / len(rs)
            ex = sum((grid(r) for r in rs), F(0)) / len(rs)
            out[(p, c)] = (top, ex, len(rs))
    return out


incl = pooled(lambda r: True)
excl_legacy52 = pooled(lambda r: not (r['subject'] in LEGACY and int(r['n_faulty_rules']) > 1))
excl_all72 = pooled(lambda r: int(r['n_faulty_rules']) == 1)

pubmap = {r['formula']: r for r in csv.DictReader((D / 'rq3_top1_pooled.csv').open(encoding='utf-8-sig'))}
exmap = {r['formula']: r for r in csv.DictReader((D / 'rq3_exam_pooled.csv').open(encoding='utf-8-sig'))}

print('formula=ochiai; each cell = Top-1% / EXAM-mean / n_mutants')
hdr = f'{"cell":12s} {"published":>20s} {"incl (all)":>22s} {"excl legacy52":>22s} {"excl all72":>22s}'
print(hdr)
for (p, c) in incl:
    k = p + '-' + c.upper()
    a, b, d = incl[(p, c)], excl_legacy52[(p, c)], excl_all72[(p, c)]
    print(f'{k:12s} {pubmap["ochiai"][k]+"/"+exmap["ochiai"][k+"_mean"]:>20s}'
          f' {a[0]:.2f}/{a[1]:.4f}/{a[2]:<8d} {b[0]:.2f}/{b[1]:.4f}/{b[2]:<8d} {d[0]:.2f}/{d[1]:.4f}/{d[3-1]:d}')

# which variant matches the published bundle numbers cell-for-cell?
def matches(vals):
    ok = True
    for (p, c), (t, e, n) in vals.items():
        k = p + '-' + c.upper()
        if f'{t:.2f}' != pubmap['ochiai'][k] or f'{e:.15f}'[:len(exmap['ochiai'][k+'_mean'])] != exmap['ochiai'][k+'_mean']:
            ok = False
    return ok

for name, vals in [('incl', incl), ('excl_legacy52', excl_legacy52), ('excl_all72', excl_all72)]:
    print(name, 'matches published rq3_top1_pooled/rq3_exam_pooled:', matches(vals))
