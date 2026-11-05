"""Historical-only entry point, excluded from the current paper protocol.

The original source is retained in the dated external scope-migration backup.
Use code/reproduction/build_tables.py for released evidence aggregation, or
code/run_pipeline.py for a fresh execution. Full historical spectra are not
bundled; no historical values are synthesized here.
"""
# Pure tie/rank arithmetic retained for independent regression checks.
def calc(spec,faults,failing,rulecount):
    if not failing:return {f:dict(evaluable='0',failing_sources='0',n_faulty_rules=str(len(faults)),rule_count=str(rulecount),exam_bc='',exam_ac='',exam_wc='',best_rank='',tie_size='') for f in NAMES}
    output={}
    for name in NAMES:
        scores={r:ns[name](*v) for r,v in spec.items()}
        scores={r:math.inf if math.isinf(s) else round(s,12) for r,s in scores.items()}
        best=[];worst=[];ties=[];ranks=[]
        for rule in faults:
            hi=sum(s>scores[rule] for s in scores.values());eq=sum(s==scores[rule] for s in scores.values())
            best.append(hi+1);worst.append(hi+eq);ties.append(eq);ranks.append(F(2*hi+1+eq,2))
        output[name]=dict(evaluable='1',failing_sources=str(failing),n_faulty_rules=str(len(faults)),rule_count=str(rulecount),exam_bc=f'{min(best)/rulecount:.12g}',exam_ac=f'{float(mean(ranks)/rulecount):.12g}',exam_wc=f'{max(worst)/rulecount:.12g}',best_rank=str(min(best)),tie_size=f'{float(mean(list(map(F,ties)))):.6f}')
    return output

if __name__ == '__main__':
    raise SystemExit('This historical entry point is not part of the current paper. Use code/reproduction/build_tables.py or code/run_pipeline.py.')
