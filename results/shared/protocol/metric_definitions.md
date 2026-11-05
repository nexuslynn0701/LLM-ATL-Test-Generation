# Metric definitions

## Validity

Validity is the number of E\* attempts divided by 100 attempts in a subject/provider/condition cell. Aggregate validity uses the corresponding summed attempt count as denominator.

## Rule coverage

Rule coverage is the union of transformation rules reached by trace-eligible source models divided by the subject's original, uninstrumented rule count. For Ant2Maven, this universe contains 30 rules. The instrumentation entrypoint `createTrace` is excluded. A legacy Ant2Maven helper can infer coverage from the input model when a trace is empty; the audited final archive contains no empty traces, and this fallback cannot add names outside the original rule set.

## Mutation score

Mutation score is the number of eligible mutants killed by at least one executable source model divided by the number of eligible mutants. The primary oracle compares normalized XMI structures. Only `KILLED` outcomes count as kills. OCL contracts are prompt context only; they do not determine execution validity or mutant kills in the reported main pipeline. For Ant2Maven, only `OUTMaven` and `OUTProject` enter the comparison. The independently extracted `TM` trace resource is excluded by resource selection; the comparator does not delete Trace elements from compared target files.

The strict ACO scores are 32/40 for BibTeX2DocBook, 50/50 for CPL2SPL, and 13/18 for UML2ER.

## Failure rate

For each eligible mutant, failure rate is the number of killed source/mutant pairs divided by the number of executable original source models. Reported summaries aggregate these per-mutant ratios.

## Localization

RQ3 ranks transformation rules with spectrum-based formulas. EXAM is the inspected fraction of ranked rules needed to reach the faulty rule; lower values are better. For Ant2Maven, average-case EXAM is the average faulty-rule rank divided by the original 30-rule universe. The released cell/formula table contains best-, average-, and worst-case tie handling plus Top-k rates.
