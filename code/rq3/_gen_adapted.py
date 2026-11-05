"""One-off generator: derive the three *_adapted.py twins from the verbatim
originals by replacing only the path-constant lines. Kept for auditability."""
from pathlib import Path

HERE = Path(__file__).resolve().parent

BANNER = ('# ADAPTED 2026-10-15: logic is byte-identical to the verbatim original\n'
          '# ({orig}); only the path constants were repointed at the replay sandbox\n'
          '# (see replay_sandbox.py). Outputs go to code/rq3/_replay/, never results/.\n')

NL = '\n'

# --- rebuild_top1_source_adapted.py ---
src = (HERE / 'rebuild_top1_source.py').read_text(encoding='utf-8')
old_block = NL.join([
    r"B=Path(r'<bundle-root>')",
    r"R=B/'github_minimal_reproduction';W=Path(__file__).resolve().parent",
    r"O=W.parent/'outputs/mutant47_rebuild';O.mkdir(exist_ok=True)",
    r"E=Path(r'<external-assets>/rqx_final_exec_validity_0901')",
])
new_block = NL.join([
    r"BUND=Path(__file__).resolve().parents[2]",
    r"import replay_sandbox as _rs;_rs.ensure_inputs()",
    r"B=_rs.SANDBOX;E=_rs.SPECTRA_ROOT",
    r"R=B/'github_minimal_reproduction';W=B",
    r"O=B/'outputs'/'mutant47_rebuild';O.mkdir(exist_ok=True)",
])
assert src.count(old_block) == 1, 'rebuild header block not found'
src = src.replace(old_block, new_block)
o2 = r"FORM_SOURCE=B/'all_figure_scripts/04_rq3_localization/formula_redundancy/kendall_redundancy.py'"
n2 = r"FORM_SOURCE=BUND/'code'/'experiment_pipeline'/'sbfl_formulas.py'"
assert src.count(o2) == 1
src = src.replace(o2, n2)
o3 = r"read(W.parent/'outputs/rq23_ant0030_replay.csv')"
n3 = r"read(O.parent/'rq23_ant0030_replay.csv')"
assert src.count(o3) == 1
src = src.replace(o3, n3)
(HERE / 'rebuild_top1_source_adapted.py').write_text(
    BANNER.format(orig='rebuild_top1_source.py') + src, encoding='utf-8')
print('rebuild_top1_source_adapted.py written')

# --- compute_top1_pooled_adapted.py ---
src = (HERE / 'compute_top1_pooled.py').read_text(encoding='utf-8')
old_block = NL.join([
    r"W=Path(__file__).resolve().parent;O=W.parent/'outputs/mutant47_rebuild'",
    r"B=Path(r'<bundle-root>/github_minimal_reproduction')",
])
new_block = NL.join([
    r"import replay_sandbox as _rs;_rs.ensure_inputs()",
    r"W=_rs.SANDBOX;O=W/'outputs'/'mutant47_rebuild'",
    r"B=W/'github_minimal_reproduction'",
])
assert src.count(old_block) == 1, 'summaries header block not found'
src = src.replace(old_block, new_block)
o3 = r"values=read(W.parent/'outputs/rq4_values_72_after_ant0030_replay.csv');deltas=[]"
n3 = r"values=read(O.parent/'rq4_values_72_after_ant0030_replay.csv');deltas=[]"
assert src.count(o3) == 1
src = src.replace(o3, n3)
o5 = r"PAPER=Path(r'<downloads>/main1008.tex')"
n5 = r"PAPER=_rs.INPUTS/'main1008.tex'"
assert src.count(o5) == 1
src = src.replace(o5, n5)
(HERE / 'compute_top1_pooled_adapted.py').write_text(
    BANNER.format(orig='compute_top1_pooled.py') + src, encoding='utf-8')
print('compute_top1_pooled_adapted.py written')

# --- export_top1_table_adapted.py ---
src = (HERE / 'export_top1_table.py').read_text(encoding='utf-8')
o4 = 'import compute_top1_pooled as m'
n4 = 'import compute_top1_pooled_adapted as m'
assert src.count(o4) == 1
src = src.replace(o4, n4)
(HERE / 'export_top1_table_adapted.py').write_text(
    BANNER.format(orig='export_top1_table.py') + src, encoding='utf-8')
print('export_top1_table_adapted.py written')
