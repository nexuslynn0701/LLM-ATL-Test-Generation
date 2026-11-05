import csv, json
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
from collections import defaultdict, Counter

ROOT=Path(r'<bundle-root>/github_minimal_reproduction')
OUT=Path(__file__).resolve().parents[1]/'outputs'
WORK=Path(__file__).resolve().parent
P=['GPT','Qwen','DeepSeek']; C=['sm','stm','astm','astmo']
def read(rel):
    with (ROOT/rel).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def avg(v): return sum(v,F(0))/len(v)
def dec(x):
    with localcontext() as ctx:
        ctx.prec=60
        return Decimal(x.numerator)/Decimal(x.denominator)
def fmt(x,n=12):return str(dec(x).quantize(Decimal(1).scaleb(-n),rounding=ROUND_HALF_EVEN))
cells=read('data/rq3/cell_formula_scores.csv')
mutants=read('data/rq3/mutant_level_exam.csv')
groups=defaultdict(list)
for r in mutants:
    if r['provider'] in P and r['condition'] in C and r['evaluable']=='1':
        groups[(r['subject'],r['provider'],r['condition'],r['formula'])].append(r)

out=[]; mismatches=[]; precision=[]
for cell in cells:
    if cell['provider'] not in P or cell['condition'] not in C:continue
    key=tuple(cell[k] for k in ['subject','provider','condition','formula'])
    rows=groups[key]
    assert len(rows)==int(cell['killed_mutants']),(key,len(rows),cell['killed_mutants'])
    exam=[]; top=0
    for r in rows:
        # Midpoint ranks are half-integers; an average over faulty rules may
        # add a factor n_faulty_rules to the denominator.
        raw=F(r['exam_ac']); bound=2*int(r['rule_count'])*int(r['n_faulty_rules'])
        exact=F(round(raw*bound),bound)
        if abs(exact-raw)>F(1,10**11): precision.append((key,r['mutant_id'],str(raw),str(exact)))
        exam.append(exact)
        top+=F(r['best_rank'])<=1
    ex=avg(exam);t=F(top,len(rows))
    if abs(ex-F(cell['mean_exam_ac']))>F(51,10**8) or abs(t-F(cell['top1_rate']))>F(51,10**6):
        mismatches.append(dict(key=key,n=len(rows),csv_n=cell['killed_mutants'],exam=fmt(ex),csv_exam=cell['mean_exam_ac'],top=fmt(t),csv_top=cell['top1_rate']))
    out.append(dict(key=key,exam=ex,top=t,n=len(rows)))
print('cell checks',len(out),'mismatches',len(mismatches),'rational recovery errors',len(precision))
print(json.dumps(mismatches[:12],indent=2));print(precision[:3])
failure_audit=[]
for r in read('data/rq2/failure_rate_summary.csv'):
    if r['method_id'].replace('DeepSeek-Flash','DeepSeek') not in [p+'-'+c.upper() for p in P for c in C]:continue
    if r['mean_fail_ratio_pct'] in ('','NA','N/A'):continue
    denom=int(r['n_eligible_mutants'])*int(r['n_original_executable_sources'])
    raw=F(r['mean_fail_ratio_pct']);count=round(raw*denom/100)
    # Builder rounds each mutant percentage to 4dp and then the mean to 4dp.
    # The maximum combined error is 0.0001 percentage points. The integer
    # pair-count lattice has spacing > twice this error, so recovery is unique.
    assert F(100,denom)>F(2,10000)
    assert abs(F(count*100,denom)-raw)<=F(1,10000),(r,count)
    assert r['status'] in ('OK','OK_STRICT_CANONICAL'),r
    failure_audit.append((r['method_id'],r['subject'],count,denom,F(count*100,denom),raw))
print('failure reconstructed',len(failure_audit))
fcounts=defaultdict(dict)
for r in mutants:
    if r['provider'] not in P or r['condition'] not in C:continue
    key=(r['subject'],r['provider']+'-'+r['condition'].upper())
    v=int(r['failing_sources'])
    assert r['mutant_id'] not in fcounts[key] or fcounts[key][r['mutant_id']]==v
    fcounts[key][r['mutant_id']]=v
fc_bad=[]
for method,sub,count,denom,exact,raw in failure_audit:
    method=method.replace('DeepSeek-Flash','DeepSeek')
    total=sum(fcounts[(sub,method)].values())
    if total!=count:fc_bad.append((sub,method,count,total,len(fcounts[(sub,method)])))
print('Failure raw count differences',len(fc_bad),fc_bad[:10])
for p in P:
    for c in C:
        subset=[r for r in out if r['key'][1:3]==(p,c)]
        print(p,c,'n_cells',len(subset),'Top1',fmt(avg([r['top'] for r in subset])*100),'EXAM',fmt(avg([r['exam'] for r in subset])))

# Keep fractions until final presentation: no binary floating-point arithmetic.
assert not mismatches and not precision
subjects=['Ant2Maven','BibTeX2DocBook','CPL2SPL','Ecore2Maude','Grafcet2PetriNet','UML2ER']
metrics=['Validity','Coverage','Mutation','Failure','Top-1','EXAM']
valid={(r['Generator'].lower(),r['Cond.']):r for r in read('data/rq1/validity.csv')}
estar={(r['provider'],r['condition'],r['subject']):int(r['n_estar']) for r in read('data/population/estar_population_by_cell.csv')}
cov={(r['llm'],r['prompt_condition'],r['subject']):r for r in read('data/rq1/rule_coverage.csv')}
mut={(r['approach'].replace('DeepSeek-Flash','DeepSeek'),r['prompt_condition'],r['subject']):r for r in read('data/rq2/mutation_score.csv')}
fail={(method.replace('DeepSeek-Flash','DeepSeek'),s):(n,d,x,raw) for method,s,n,d,x,raw in failure_audit}
values={};release_failure={}
for p in P:
    for c in C:
        vv=[];cc=[];mm=[];ff=[];fr=[]
        for s in subjects:
            v=F(valid[(p.lower(),c.upper())][s])
            assert v==estar.get((p,c,s),0)
            vv.append(v)
            cr=cov[(p,c.upper(),s)];mr=mut[(p,c.upper(),s)]
            cc.append(F(100*int(cr['covered_rules'] or 0),int(cr['total_rules'])))
            mm.append(F(100*int(mr['killed_mutants'] or 0),int(mr['eligible_mutants'])))
            fl=fail.get((p+'-'+c.upper(),s))
            if fl:ff.append(fl[2]);fr.append(fl[3])
        subset=[r for r in out if r['key'][1:3]==(p,c)]
        vals=[avg(vv),avg(cc),avg(mm),avg(ff),100*avg([r['top'] for r in subset]),avg([r['exam'] for r in subset])]
        for metric,x in zip(metrics,vals):values[(metric,p,c)]=x
        release_failure[(p,c)]=avg(fr)

def signed(x):
    rounded=fmt(x,2)
    return ('+' if not rounded.startswith('-') else '')+rounded

def write_csv(name,rows):
    with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

provenance={
 'Validity':'Exact E* count / 100 per subject; checked against validity.csv',
 'Coverage':'Exact covered_rules / total_rules; empty Qwen CPL2SPL = 0',
 'Mutation':'Exact killed_mutants / eligible_mutants; empty Qwen CPL2SPL = 0',
 'Failure':'Unique integer pair-count recovery from RQ2 summary and denominators; not raw pair records',
 'Top-1':'Exact count(best_rank <= 1) / evaluable mutant count in each subject/formula',
 'EXAM':'Rank-grid recovery of stored mutant EXAM using denominator 2 * rule_count * n_faulty_rules',
}
absolute=[];deltas=[];wide=[]
for metric in metrics:
    for p in P:
        wide.append({'metric':metric,'LLM':p,**{c.upper():fmt(values[(metric,p,c)],15) for c in C}})
        for c in C:
            x=values[(metric,p,c)]
            absolute.append(dict(metric=metric,LLM=p,context=c.upper(),value_15dp=fmt(x,15),numerator=x.numerator,denominator=x.denominator,display_2dp=fmt(x,2),provenance=provenance[metric]))
            if c=='sm':continue
            base=values[(metric,p,'sm')]
            d=(base-x) if metric=='EXAM' else (x-base)
            deltas.append(dict(metric=metric,LLM=p,context=c.upper(),baseline='SM',direction='SM - context' if metric=='EXAM' else 'context - SM',delta_15dp=fmt(d,15),numerator=d.numerator,denominator=d.denominator,display_2dp=signed(d)))
assert len(absolute)==72 and len(deltas)==54
write_csv('rq4_values_72.csv',absolute)
write_csv('rq4_values_wide.csv',wide)
write_csv('rq4_deltas_54.csv',deltas)
write_csv('rq4_failure_precision.csv',[dict(LLM=p,context=c.upper(),recovered_count_overall=fmt(values[('Failure',p,c)],15),published_4dp_cell_mean=fmt(release_failure[(p,c)],15),recovered_display=fmt(values[('Failure',p,c)],2),published_mean_display=fmt(release_failure[(p,c)],2)) for p in P for c in C])
write_csv('rq4_failure_count_audit.csv',[dict(method=method,subject=s,inferred_RQ2_killed_pairs=n,pair_denominator=d,recovered_percent=fmt(x,15),published_percent=str(raw),RQ3_killed_pairs=sum(fcounts[(s,method.replace('DeepSeek-Flash','DeepSeek'))].values()),RQ3_mutant_count=len(fcounts[(s,method.replace('DeepSeek-Flash','DeepSeek'))])) for method,s,n,d,x,raw in failure_audit])

# Re-read the actual local paper, not an earlier cached parse.
from audit_paper import tables,PAPER
table=next(t for t in tables if t['label']=='tab:rq4-ladder')
paper_rows=[r for r in table['rows'] if len(r['cells'])==8 and r['cells'][1] in [c.upper() for c in C]]
assert len(paper_rows)==12
import re
diffs=[]
for i,r in enumerate(paper_rows):
    p=P[i//4];c=r['cells'][1].lower()
    for metric,cell in zip(metrics,r['cells'][2:]):
        nums=re.findall(r'[+-]?\d+(?:\.\d+)?',cell)
        expected=fmt(values[(metric,p,c)],2)
        if F(nums[0])!=F(expected):diffs.append(dict(line=r['line'],LLM=p,context=c.upper(),metric=metric,kind='absolute',paper=nums[0],recomputed=expected))
        if c!='sm':
            d=next(x for x in deltas if x['metric']==metric and x['LLM']==p and x['context']==c.upper())
            assert len(nums)==2,(cell,nums)
            if F(nums[1])!=F(d['display_2dp']):diffs.append(dict(line=r['line'],LLM=p,context=c.upper(),metric=metric,kind='delta',paper=nums[1],recomputed=d['display_2dp']))
if diffs:write_csv('rq4_paper_differences.csv',diffs)
print('PAPER DIFFERENCES',json.dumps(diffs,indent=2))

lines=['# RQ4 重算结果（2026-10-08）','',
'已导出 72 个绝对值和 54 个相对同一 LLM 的 SM 增量。计算全程用有理数；CSV 保留分子/分母，15 位小数仅用于显示，最终统一 ROUND_HALF_EVEN 到两位。未修改论文。','',
'## 聚合与精度','',
'- Validity：每科目 E* / 100，六科目等权；72 个科目计数与 validity.csv 一致。',
'- Coverage、Mutation：从整数分子/分母重算；六科目等权，Qwen 的空 CPL2SPL 单元格按论文静态梯度口径记 0。此口径与 RQ5 的可用科目均值不同。',
'- Failure：对非 N/A 科目等权，GPT/DeepSeek 各 6 科目、Qwen 5 科目。源脚本先将每变异体百分比舍入 4 位，再将均值舍入 4 位；总误差不超过 0.0001 个百分点。用 N_source × N_mutant 的整数计数网格唯一反推 killed pairs；68 个非空单元格全部通过精度及唯一性检查。属于可验证的计数恢复，并非直接读取原始 pair records。另存直接平均已发布 4 位数的结果，便于区分口径。',
'- Top-1：每个科目/公式内，以 evaluable=1 的变异体为分母，best_rank ≤ 1 为分子。再对科目和 18 个公式等权平均；GPT/DeepSeek 每组合 108 单元格，Qwen 90 个（排除空 CPL2SPL）。',
'- EXAM：每个变异体采用平均并列排名的 EXAM-AC；以 2 × rule_count × n_faulty_rules 的网格恢复有理数，再按上述科目/公式口径聚合。所有恢复值与存储值相差不超过 1e-11；1,224 个科目/公式汇总与 cell_formula_scores.csv 在其存储精度内全部一致。原始逐故障规则排名未在本次直接读取，恢复值不应被称为重新执行 SBFL 得到的原始结果。',
'- 前五列增量 = context − SM；EXAM 增量 = SM − context。百分比列的增量单位为百分点。','',
'## 72 个值（显示 12 位小数；CSV 为 15 位及精确分数）','',
'| 指标 | LLM | SM | STM | ASTM | ASTMO |','|---|---|---:|---:|---:|---:|']
for metric in metrics:
    for p in P:lines.append('| '+' | '.join([metric,p]+[fmt(values[(metric,p,c)]) for c in C])+' |')
lines+=['','## RQ4 可替换数值与 54 个增量','', '| LLM | Context | Validity | Coverage | Mutation | Failure | Top-1 | EXAM |','|---|---|---:|---:|---:|---:|---:|---:|']
for p in P:
    for c in C:
        row=[p,c.upper()]
        for metric in metrics:
            label=fmt(values[(metric,p,c)],2)
            if c!='sm':
                d=next(x for x in deltas if x['metric']==metric and x['LLM']==p and x['context']==c.upper())
                label+=' ('+d['display_2dp']+')'
            row.append(label)
        lines.append('| '+' | '.join(row)+' |')
lines+=['','## 与本机论文的差异','',f'比较文件：`{PAPER}`。用户转述的修改不自动视为本机文件已修改。','', '| 行 | LLM | Context | 指标 | 类型 | 论文 | 重算 |','|---:|---|---|---|---|---:|---:|']
for d in diffs:lines.append('| '+' | '.join(str(d[k]) for k in ['line','LLM','context','metric','kind','paper','recomputed'])+' |')
lines+=['','## 先前两个边界问题','',
'- Qwen/ASTMO/BibTeX2DocBook Failure = 2801 / 4000 × 100 = 70.025，ROUND_HALF_EVEN 后为 **70.02**。此单元格的 RQ3 failing_sources 合计也为 2801。',
'- Qwen/ASTM Failure Overall = '+fmt(values[('Failure','Qwen','astm')],15)+'，小于 72.535，两位显示为 **72.53**，无需改成 72.54。',
'- GPT/ASTMO Failure 未舍入增量 = '+fmt(values[('Failure','GPT','astmo')]-values[('Failure','GPT','sm')],15)+'，两位显示为 **+2.60**。','',
'## RQ2 与 RQ3 来源差异','',
'不能据此宣称所有原始数据完全一致。以下 9 个单元格的 RQ2 恢复总 killed-pair 数与 RQ3 failing_sources 按 mutant_id 去重后之和不同。CPL2SPL 的 RQ3 文件每组合只有 49 个变异体，而 RQ2 分母为 50；此外 GPT/ASTMO/Ant2Maven 两侧均有 100 个变异体，但总数差 14。此次 Failure 使用 RQ2、定位指标使用 RQ3，保留各自来源。差异原因尚未由原始运行记录确认。','',
'| 科目 | 方法 | RQ2 killed pairs（恢复） | RQ3 failing_sources 合计 | RQ3 变异体数 |','|---|---|---:|---:|---:|']
for row in fc_bad:lines.append('| '+' | '.join(map(str,row))+' |')
lines+=['','## 来源文件','']
for rel in ['data/rq1/validity.csv','data/population/estar_population_by_cell.csv','data/rq1/rule_coverage.csv','data/rq2/mutation_score.csv','data/rq2/failure_rate_summary.csv','data/rq3/cell_formula_scores.csv','data/rq3/mutant_level_exam.csv']:
    lines.append(f'- `{ROOT/rel}`')
(OUT/'rq4_recalculation_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Exported 72 absolute values, 54 deltas, and report to',OUT)
