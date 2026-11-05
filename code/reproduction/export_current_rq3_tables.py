"""Export retained-configuration RQ3 tables and ACO-only baseline fragments."""
from pathlib import Path
import csv,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code/rq3'))
import apply_yekta_canonical_population as rq3

def write(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)

def main():
    rows=rq3.read(rq3.EXAM_CSV)
    top,exam=rq3.pooled_tables(rq3.pool_of(rows))
    tests=rq3.pairwise_tests(rows)
    assert len(tests)==216
    counts=rq3.counts_of(tests)
    write(ROOT/'results/rq3/data/rq3_pairwise_tests.csv',tests)
    write(ROOT/'results/rq3/data/rq3_pairwise_counts.csv',counts)
    bdir=ROOT/'results/rq3/supplementary/rq3_baseline_columns'
    long,display,pop,tex,audit=rq3.baseline_columns(exam,rows)
    for name,data in [('baseline_exam_exact.csv',long),('baseline_exam_display.csv',display),('baseline_population.csv',pop)]:
        write(bdir/name,data)
    (bdir/'baseline_columns.tex').write_text(tex,encoding='utf-8')
    (bdir/'audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    out=ROOT/'results/rq3/tables'
    out.mkdir(parents=True,exist_ok=True)
    for name,table in [('rq3_top1.tex',top),('rq3_exam.tex',exam)]:
        headers=list(table[0])
        lines=[r'\begin{tabular}{l'+'r'*(len(headers)-1)+'}',r'\hline',
               ' & '.join(h.replace('_',r'\_') for h in headers)+r' \\',r'\hline']
        lines+=[' & '.join(str(row[h]).replace('_',r'\_') for h in headers)+r' \\' for row in table]
        lines += [r'\hline',r'\end{tabular}']
        (out/name).write_text('\n'.join(lines)+'\n',encoding='utf-8')
    headers=['formula','Yekta-ACO_Worse','Yekta-ACO_Similar','Yekta-ACO_Better']
    lines=[r'\begin{tabular}{lrrr}',r'\hline',r'Formula & Worse & Similar & Better \\',r'\hline']
    lines+=[' & '.join(str(row[h]).replace('_',r'\_') for h in headers)+r' \\' for row in counts]
    lines += [r'\hline',r'\end{tabular}','% Raw two-sided Wilcoxon p < 0.05 for 216 LLM-versus-ACO comparisons.']
    (out/'rq3_pairwise_counts.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print('Exported 13-configuration summaries, 216-test counts and ACO-only fragments.')

if __name__=='__main__':main()
