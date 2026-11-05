# Final population policy

The primary population is **E\***: an attempt belongs to E\* when it is in the execution population and has at least one non-empty, verifiable output-model record under the strict outcome matrix.

The final audit changes two workflow records relative to the earlier execution crosswalk:

- `CPL2SPL/Qwen/workflow/0061` is excluded.
- `CPL2SPL/Qwen/workflow/0080` is excluded.

Both records fail evidence replay before an output model can be produced. `Ant2Maven/GPT/ASTMO/0030` remains included because evidence repair reproduced its output and trace.

Consequently, the workflow population has 1,644 verifiable attempts out of 1,800. The 156 remaining attempts should be described as non-verifiable: 154 are execution failures and two are the records above.
