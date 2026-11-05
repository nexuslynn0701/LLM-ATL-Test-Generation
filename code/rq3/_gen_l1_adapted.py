# One-off generator for build_rq3_latest_adapted.py (same pattern as _gen_adapted.py).
# Verbatim logic; only three path constants repointed at the L1 replay inputs.
from pathlib import Path

HERE = Path(__file__).resolve().parent
src = (HERE / 'build_rq3_latest.py').read_text(encoding='utf-8')
reps = [
    ("ROOT = Path('<old-machine>/research/llm_mt_experiment')",
     "ROOT = Path.home() / 'Desktop' / 'ppt' / 'L1_inputs'"),
    ("OUT_DIR = Path('<old-machine>/Desktop/rq3_latest_v4')",
     "OUT_DIR = Path(__file__).resolve().parent / '_replay' / 'outputs' / 'rq3_latest_v4'"),
    ("_sys.path.insert(0, str(Path(__file__).resolve().parents[2]))",
     "_sys.path.insert(0, str(Path.home() / 'Desktop' / 'ppt' / 'rqx_final_exec_validity_0901' / 'rqx_final_exec_validity_0901'))"),
]
out = src
for old, new in reps:
    assert out.count(old) == 1, old
    out = out.replace(old, new)
(HERE / 'build_rq3_latest_adapted.py').write_text(out, encoding='utf-8', newline='')
print('build_rq3_latest_adapted.py written')
