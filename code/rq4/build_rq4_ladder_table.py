"""Build the pooled RQ4 ladder table (tab:rq4-ladder) from bundle-internal data.

Chain position:
    results/rq3/data/mutant_level_exam.csv
      --(mutant-level pooling: all evaluable mutants of each LLM x context,
         across all subjects and all 18 formulas)-->
    results/rq4/data/rq4_top1_exam_pooled.csv        [pooled CSV]
      --(merge with rq4_values_72.csv / rq4_deltas_54.csv for the four
         capability/effectiveness metrics)-->
    results/rq4/tables/rq4_ladder.tex                [table (tex)]

Aggregation rules (fixed on 2026-10-14 delivery):
  * Top-1  = 100 * #(best_rank <= 1) / #evaluable, pooled over all mutants.
  * EXAM   = mean of per-mutant EXAM-AC over all evaluable mutants; each
    mutant EXAM is recovered exactly onto the 2 * rule_count * n_faulty_rules
    rank grid before averaging.
  * All arithmetic in exact Fractions; display values are ROUND_HALF_EVEN to
    2 decimals; deltas are computed from unrounded values (Top-1 and EXAM:
    context - SM, negative = improvement) and rounded the same way.
  * Validity/Coverage/Mutation/Failure columns and their deltas come from
    rq4_values_72.csv / rq4_deltas_54.csv (subject-equal-weight 口径; see
    recompute_rq4_values72.py; their EXAM rows use the old SM - context
    direction and are NOT used here).
  * Emphasis on displayed values: \\best = best over all 12 cells of a metric
    (ties all marked; EXAM: lower is better), otherwise \\textbf = best within
    that LLM (ties all marked).

`--paper PATH` additionally diffs the generated table against an existing
paper tex (default: Desktop/paper1014/main.tex, skipped if missing).
"""
import argparse, csv, re
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from collections import defaultdict

BUNDLE = Path(__file__).resolve().parents[2]
RQ3_MLE = BUNDLE / 'results' / 'rq3' / 'data' / 'mutant_level_exam.csv'
RQ4_DATA = BUNDLE / 'results' / 'rq4' / 'data'
RQ4_SUPP = BUNDLE / 'results' / 'rq4' / 'supplementary'
RQ4_TABLES = BUNDLE / 'results' / 'rq4' / 'tables'
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--paper', default=str(Path.home() / 'Desktop' / 'paper1014' / 'main.tex'),
                    help='paper tex to diff against (skipped if missing)')
    args = ap.parse_args()

    pooled = pooled_top1_exam()
    values = {(r['metric'], r['LLM'], r['context'].lower()): r['display_2dp']
              for r in read(RQ4_SUPP / 'rq4_values_72_current.csv')}
    deltas = {(r['metric'], r['LLM'], r['context'].lower()): r['display_2dp']
              for r in read(RQ4_SUPP / 'rq4_deltas_54_current.csv')}

    # pooled display values + deltas (context - SM for both columns, matching
    # the current paper style; computed from unrounded fractions)
    disp = {}
    for p in P:
        sm_t, sm_e = pooled[(p, 'sm')]['top1'], pooled[(p, 'sm')]['exam']
        for c in C:
            d = pooled[(p, c)]
            disp[('Top-1', p, c)] = fmt(d['top1'])
            disp[('EXAM', p, c)] = fmt(d['exam'])
            if c != 'sm':
                disp[('dTop-1', p, c)] = signed(d['top1'] - sm_t)
                disp[('dEXAM', p, c)] = signed(d['exam'] - sm_e)

    # write the pooled CSV (the pooled layer of the chain)
    csv_path = RQ4_DATA / 'rq4_top1_exam_pooled.csv'
    with csv_path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['LLM', 'context', 'n_evaluable_mutants',
                    'top1_hits', 'top1_numerator', 'top1_denominator', 'top1_15dp', 'top1_2dp',
                    'exam_numerator', 'exam_denominator', 'exam_15dp', 'exam_2dp',
                    'delta_top1_ctx_minus_sm_2dp', 'delta_exam_ctx_minus_sm_2dp'])
        for p in P:
            sm_t, sm_e = pooled[(p, 'sm')]['top1'], pooled[(p, 'sm')]['exam']
            for c in C:
                d = pooled[(p, c)]
                w.writerow([p, c.upper(), d['n'],
                            d['top1_hits'], d['top1'].numerator, d['top1'].denominator,
                            fmt(d['top1'], 15), fmt(d['top1']),
                            d['exam'].numerator, d['exam'].denominator,
                            fmt(d['exam'], 15), fmt(d['exam']),
                            '' if c == 'sm' else signed(d['top1'] - sm_t),
                            '' if c == 'sm' else signed(d['exam'] - sm_e)])
    print('wrote', csv_path)

    # assemble table cells with emphasis on displayed values
    cell = {}
    for m in METRICS4 + ['Top-1', 'EXAM']:
        for p in P:
            for c in C:
                cell[(m, p, c)] = values[(m, p, c)] if m in METRICS4 else disp[(m, p, c)]

    markup = {}
    for m in METRICS4 + ['Top-1', 'EXAM']:
        allvals = [cell[(m, p, c)] for p in P for c in C]
        overall = min(allvals) if m == 'EXAM' else max(allvals)
        for p in P:
            llmvals = [cell[(m, p, c)] for c in C]
            within = min(llmvals) if m == 'EXAM' else max(llmvals)
            for c in C:
                v = cell[(m, p, c)]
                if v == overall:
                    markup[(m, p, c)] = '\\best{' + v + '}'
                elif v == within:
                    markup[(m, p, c)] = '\\textbf{' + v + '}'
                else:
                    markup[(m, p, c)] = v

    def dstr(m, p, c):
        if c == 'sm':
            return ''
        if m in METRICS4:
            return ' {\\tiny(' + deltas[(m, p, c)] + ')}'
        return ' {\\tiny(' + disp[('d' + m, p, c)] + ')}'

    lines = [
        '\\begin{table*}[t]',
        '\\centering',
        '\\setlength{\\tabcolsep}{3.5pt}',
        '\\renewcommand{\\arraystretch}{0.92}',
        '\\caption{Comparison of four prompt-context configurations across three LLMs for '
        'test model generation, testing effectiveness, and fault localization. '
        '(Bold: best within each LLM; blue: best overall, per metric.)}',
        '\\label{tab:rq4-ladder}',
        '\\begin{tabular}{clcccccc}',
        '\\toprule',
        '',
        '\\multicolumn{2}{c}{} ',
        '  & \\multicolumn{2}{c}{\\textbf{Test Generation Capability}} ',
        '  & \\multicolumn{2}{c}{\\textbf{Testing Effectiveness}} ',
        '  & \\multicolumn{2}{c}{\\textbf{Fault Localization Effectiveness}} \\\\',
        '\\cmidrule(lr){3-4} \\cmidrule(lr){5-6} \\cmidrule(lr){7-8}',
        '',
        ('\\textbf{LLM} & \\textbf{Context} & \\textbf{Validity (\\%)} & \\textbf{Coverage (\\%)} '
         '& \\textbf{Mutation (\\%)} & \\textbf{Failure (\\%)} & \\textbf{Top-1 (\\%)} & \\textbf{EXAM} \\\\'),
        '\\midrule',
        '',
    ]
    for p in P:
        lines.append('\\multirow{4}{*}{' + p + '} & SM & '
                     + ' & '.join(markup[(m, p, 'sm')] for m in METRICS4 + ['Top-1', 'EXAM']) + ' \\\\')
        for c in C[1:]:
            row = ' & ' + c.upper() + ' '
            for m in METRICS4 + ['Top-1', 'EXAM']:
                row += ' & ' + markup[(m, p, c)] + dstr(m, p, c)
            lines.append(row + ' \\\\')
        if p != P[-1]:
            lines.append('\\addlinespace')
    lines += ['\\bottomrule', '\\end{tabular}', '\\end{table*}']

    tex_path = RQ4_TABLES / 'rq4_ladder.tex'
    header = ('% Generated by code/rq4/build_rq4_ladder_table.py\n'
              '% Top-1/EXAM: mutant-level pooling over all evaluable mutants of each LLM x context\n'
              '%   (source: results/rq3/data/mutant_level_exam.csv; see rq4_top1_exam_pooled.csv)\n'
              '% Validity/Coverage/Mutation/Failure: results/rq4/supplementary/'
              'rq4_values_72_current.csv + rq4_deltas_54_current.csv\n'
              '% Emphasis recomputed on displayed 2dp values; EXAM: lower is better.\n')
    tex_path.write_text(header + '\n'.join(lines) + '\n', encoding='utf-8')
    print('wrote', tex_path)

    # optional diff against an existing paper tex
    paper = Path(args.paper)
    if paper.exists():
        t = paper.read_text(encoding='utf-8')
        m = re.search(r'\\label\{tab:rq4-ladder\}', t)
        i = t.rfind('\\begin{table', 0, m.start())
        j = t.find('\\end{table', m.end())
        paper_cells = {}
        cur_p = None
        for s in t[i:j].splitlines():
            s = s.strip()
            if not re.search(r'&\s*(SM|STM|ASTM|ASTMO)\s*&', s):
                continue
            pm = re.search(r'\\multirow\{4\}\{[^}]*\}\{(\w+)\}', s)
            if pm:
                cur_p = pm.group(1)
            ctx = re.search(r'&\s*(SM|STM|ASTM|ASTMO)\s*&', s).group(1)
            nums = re.findall(r'[+-]?\d+\.\d+', s)
            absolutes = [n for n in nums if not n.startswith(('+', '-'))][:6]
            dlt = [n for n in nums if n.startswith(('+', '-'))][:6]
            paper_cells[(cur_p, ctx)] = (absolutes, dlt)

        print('\n--- diff vs', paper, '---')
        n_diff = 0
        for p in P:
            for c in C:
                pa = paper_cells.get((p, c.upper()))
                if not pa:
                    print(f'  MISSING paper row {p}/{c}')
                    continue
                p_abs, p_dlt = pa
                gen_abs = [cell[(m, p, c)] for m in METRICS4 + ['Top-1', 'EXAM']]
                for m, g, e in zip(METRICS4 + ['Top-1', 'EXAM'], gen_abs, p_abs):
                    if g != e:
                        print(f'  {p}/{c}/{m}: generated {g}  vs  paper {e}')
                        n_diff += 1
                if c != 'sm':
                    gen_d = [deltas[(m, p, c)] for m in METRICS4] + \
                            [disp[('dTop-1', p, c)], disp[('dEXAM', p, c)]]
                    for m, g, e in zip(METRICS4 + ['Top-1', 'EXAM'], gen_d, p_dlt):
                        if g.lstrip('+') != e.lstrip('+'):
                            print(f'  {p}/{c}/d{m}: generated {g}  vs  paper {e}')
                            n_diff += 1
        print('total differing cells:', n_diff)
    else:
        print('paper diff skipped (not found):', args.paper)


if __name__ == '__main__':
    main()
