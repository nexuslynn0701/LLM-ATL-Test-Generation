# Ant2Maven execution and rule scope

This note records the execution semantics used by the reported Ant2Maven results.

## Mutation oracle and trace separation

Ant2Maven produces two target resources, `OUTMaven` and `OUTProject`, plus a separate trace resource registered as `TM`. The Java runner extracts the three resources into separate XMI files. Mutation classification iterates only over the target entries in the runner's `outputs` map; the separately returned trace path is not an oracle input.

The normalized-XMI comparator recursively compares the complete XML trees of the selected target files. It does not remove elements by EClass or filter elements named `Trace` or `TraceLink`. Original and mutant target outputs receive the same normalization. The implementation should therefore be described as excluding trace by resource selection, rather than deleting trace elements before comparison.

The archived implementation checks have the following expected outcomes:

- changing only the separately stored trace leaves the mutant `ALIVE`;
- changing target-model content makes the mutant `KILLED`;
- embedding a Trace element inside a compared target file makes the mutant `KILLED`.

The stored-output audit covered 2,202 target XMI files and found no trace elements mixed into those target resources.

## Rule universe and EXAM denominator

The uninstrumented Ant2Maven transformation contains 30 ordinary ATL rules. Its instrumented form contains the same 30 rules plus the entrypoint rule `createTrace`. The entrypoint creates the trace resource and is not part of the transformation-rule universe.

Coverage and localization use the 30-rule set extracted from the uninstrumented transformation. The rule extractor excludes entrypoint rules, the trace parser excludes `createTrace`, and observed rule names are intersected with the original rule set. EXAM is computed as the average faulty-rule rank divided by 30.

The final audit covered 16 configurations and 4,449,000 spectrum records. Every test-mutant spectrum block used the original 30-rule set. All 34,560 expanded EXAM records used denominator 30, and all 13,500 evaluable records satisfied `EXAM = rank_average / 30`.

The legacy coverage helper retains a fallback that infers Ant2Maven coverage from the input model when a trace is empty. It therefore should not be claimed that every historical path derives coverage exclusively from a dynamic trace. The fallback can only select names from the original rule set and cannot add `createTrace`. In the audited final archive, all 1,101 trace files were non-empty and none contained a rule name outside the original 30-rule set.

The machine-readable summary is in `results/rq1/supplementary/audit/ant2maven_trace_scope_audit.json`.
