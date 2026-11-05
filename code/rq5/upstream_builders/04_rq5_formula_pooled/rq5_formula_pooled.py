import csv,json
from pathlib import Path
from collections import defaultdict
from fractions import Fraction as F
from statistics import median
from decimal import Decimal,ROUND_HALF_EVEN,localcontext
out=Path('outputs/rq5_formula_pooled');out.mkdir(exist_ok=True)
subjects=['Ant2Maven','BibTeX2DocBook','CPL2SPL','Ecore2Maude','Grafcet2PetriNet','UML2ER']
models=['GPT','Qwen','DeepSeek'];conditions=['astmo','workflow']
names=['ochiai','tarantula','dstar2','kulczynski2','mountford','zoltar','arithmetic_mean','barinel','braun_banquet','baroni_urbani_buser','cohen','ochiai2','op2','phi','pierce','rogers_tanimoto','russell_rao','simple_matching']
labels=['Ochiai','Tarantula','DStar2','Kulczynski2','Mountford','Zoltar','ArithmeticMean','Barinel','BraunBanquet','BaroniUrbaniBuser','Cohen','Ochiai2','OP2','Phi','Pierce','RogersTanimoto','RussellRao','SimpleMatching']
def read(p):
    with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def fmt(x,n=15):
    with localcontext() as c:
        c.prec=60
        return str((Decimal(x.numerator)/Decimal(x.denominator)).quantize(Decimal(1).scaleb(-n),rounding=ROUND_HALF_EVEN))
def write(name,rows):
    with (out/name).open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
groups=defaultdict(list);seen=set()
for r in read('outputs/mutant47_rebuild/mutant_level_exam.csv'):
    if r['provider'] in models and r['condition'] in conditions and r['evaluable']=='1':
        key=r['formula'],r['provider'],r['condition'],r['subject'],r['mutant_id']
        assert key not in seen;seen.add(key)
        groups[key[:4]].append(r)
old={(r['formula'],r['provider'],r['condition'],r['subject']):r for r in read('outputs/mutant47_rebuild/rq5_localization_by_cell.csv')}
rq3top={r['formula']:r for r in read('outputs/mutant47_rebuild/rq3_top1_pooled.csv')}
rq3exam={r['formula']:r for r in read('outputs/mutant47_rebuild/rq3_exam_pooled.csv')}
detail=[];table=[];round_top=[];round_exam=[];round_median=[];excel_detail=[];denominators=[]
for f,label in zip(names,labels):
    tp=[label];ep=[label];mp=[label]
    for m in models:
        for c in conditions:
            pooled=[];pooled_hits=0;observed_subjects=0
            cond='ASTMO' if c=='astmo' else 'FD-ASTMO'
            for s in subjects:
                key=f,m,c,s;rs=groups[key];n=len(rs)
                hits=sum(F(r['best_rank'])<=1 for r in rs);es=[]
                for r in rs:
                    den=2*int(r['rule_count'])*int(r['n_faulty_rules']);raw=F(r['exam_ac']);v=F(round(raw*den),den)
                    assert abs(v-raw)<=F(1,10**10);es.append(v)
                if n:
                    t=F(hits,n);e=sum(es,F())/n;med=median(es);observed_subjects+=1
                    prior=old[key]
                    assert n==int(prior['n_killed'])
                    assert abs(100*t-F(prior['Top1_pct']))<F(1,10**12)
                    assert abs(e-F(prior['EXAM']))<F(1,10**12)
                else:
                    assert (m,c,s)==('Qwen','astmo','CPL2SPL')
                    t=e=med=None
                pooled.extend(es);pooled_hits+=hits
                status='不纳入：无可定位变异体' if not n else '纳入 pooled'
                excel_detail.append([label,m,cond,s,n,hits,float(sum(es,F())),float(t) if n else 'N/A',float(e) if n else 'N/A',float(med) if n else 'N/A',status])
                detail.append(dict(formula=label,llm=m,condition=cond,subject=s,n_evaluable=n,top1_hits=hits,exam_ac_sum=fmt(sum(es,F())),top1_pct=fmt(t*100) if n else 'N/A',exam_ac_mean=fmt(e) if n else 'N/A',exam_ac_median=fmt(med) if n else 'N/A',status=status))
            n_total=len(pooled);t=F(pooled_hits,n_total);e=sum(pooled,F())/n_total;med=median(pooled)
            if c=='astmo':
                prefix=m+'-ASTMO'
                assert abs(100*t-F(rq3top[f][prefix]))<F(1,10**12)
                assert abs(e-F(rq3exam[f][prefix+'_mean']))<F(1,10**12)
                assert abs(med-F(rq3exam[f][prefix+'_median']))<F(1,10**12)
                assert n_total==int(rq3exam[f][prefix+'_n'])
            tp.append(float(fmt(t*100,2))/100);ep.append(float(fmt(e,2)));mp.append(float(fmt(med,2)))
            row=dict(formula=label,llm=m,condition=cond,n_subjects_in_design=6,n_subjects_with_evaluable_mutants=observed_subjects,n_evaluable=n_total,top1_hits=pooled_hits,top1_pct=fmt(t*100),exam_ac_mean=fmt(e),exam_ac_median=fmt(med),top1_numerator=t.numerator,top1_denominator=t.denominator,exam_mean_numerator=e.numerator,exam_mean_denominator=e.denominator,exam_median_numerator=med.numerator,exam_median_denominator=med.denominator,top1_display=fmt(t*100,2),exam_mean_display=fmt(e,2),exam_median_display=fmt(med,2))
            table.append(row)
            if f=='ochiai':denominators.append([m,cond,6,observed_subjects,n_total])
    round_top.append(tp);round_exam.append(ep);round_median.append(mp)
assert len(detail)==648 and len(table)==108
for m in models:
    for c in ['ASTMO','FD-ASTMO']:assert len({r['n_evaluable'] for r in table if r['llm']==m and r['condition']==c})==1
write('overall_by_formula.csv',table);write('subject_details.csv',detail)
headers=['Formula']+[m+' '+c for m in models for c in ['ASTMO','FD-ASTMO']]
for name,rows,percent in [('top1_matrix.csv',round_top,True),('exam_ac_mean_matrix.csv',round_exam,False),('exam_ac_median_matrix.csv',round_median,False)]:
    write(name,[dict(zip(headers,[r[0]]+[f'{v*(100 if percent else 1):.2f}' for v in r[1:]])) for r in rows])
validation={'passed':True,'overall_configurations':108,'overall_metrics_with_median':324,'subject_formula_cells':648,'observed_cells_verified_against_previous_summary':630,'missing_cells_excluded':18,'rq3_astmo_top1_mean_median_matched':162,'top1_definition':'best_rank <= 1 among evaluable mutants','exam_ac_definition':'mutant EXAM-AC using tie-mid ranks; aggregate mean and median over pooled mutants','aggregation':'pool evaluable mutants across all six subjects for each LLM, condition and formula','missing_convention':'no penalty or zero imputation; Qwen ASTMO CPL2SPL contributes no observations'}
(out/'workbook_input.json').write_text(json.dumps(dict(top1=round_top,exam=round_exam,median=round_median,detail=excel_detail,overall=table,denominators=denominators,validation=validation),ensure_ascii=False),encoding='utf-8')
(out/'validation.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
(out/'README.md').write_text('''# RQ5 定位指标：与 RQ3 相同的 pooled 口径

每个公式、LLM、方法分别合并六个数据集的 evaluable=1 变异体。Top-1 为 best_rank<=1 的变异体数除以可定位变异体数。并列第一算命中，多故障规则取最好排名判断 Top-1。

EXAM-AC 使用并列组的中点排名；多故障规则先平均中点排名，再除以该转换的规则总数。对合并后的逐变异体 EXAM-AC 求 mean 和 median。每个变异体等权，数据集不等权；中位数不是各数据集中位数的平均。

Qwen/ASTMO/CPL2SPL 没有可定位变异体，不填 0，不填 1，不施加失败惩罚。该配置的观测来自其余五个数据集。其他五个 LLM/方法配置均有六个数据集的观测。

本输出取代此前未交付的六科目等权加惩罚草稿。所有数值由重建后的逐变异体记录计算；ASTMO 的 18×3 组 Top-1、EXAM 均值和中位数已与 RQ3 对应列逐项吻合。

Excel 的 Overall 为 ROUND_HALF_EVEN 保留两位的出版数值快照；科目明细保留可定位数、命中数、EXAM 和以及原始精度指标。CSV overall_by_formula.csv 提供 15 位小数与精确分数，可用于进一步核对。

本次没有修改论文正文，也没有改动 RQ5 四指标图的六科目零赋值口径；这里仅调整定位指标。
''',encoding='utf-8')
print(json.dumps(validation));print('denominators',denominators)
print('Ochiai',round_top[0],round_exam[0],round_median[0])
