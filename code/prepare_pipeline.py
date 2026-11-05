"""Reconstruct the pipeline's original relative layout from the organized bundle.

Rewritten 2026-10-15: the previous version read the migration manifest from
code/maintenance/relocation_manifest.csv, which was deleted together with
code/maintenance/ per user decision. The mapping is now expressed directly
here and reproduces the same pipeline_toolchain layout the manifest described:

  <output>/datasets/models_<X>/   <- subjects/<X>/ (metamodels, scenarios/,
                                     transformations/) with
                                     data/mutants/<X>/*.atl/.asm merged into
                                     transformations/ and
                                     data/ocl/<X>/OCL_*.txt at the root
  <output>/prompts/generate_test_model_v2.txt (+ condition snippets)
                                 <- data/prompts/templates/
  <output>/reproducibility/frozen_prompts/
                                 <- data/prompts/frozen_prompts/
  <output>/{src,scripts,lib,tests,run_pipeline.sh,requirements_local.txt}
                                 <- code/pipeline/

The six canonical subjects, OCL, mutants and prompts stay in their new
locations; this command only creates a disposable execution copy and runs no
experiment, API call or Java execution.
"""
from pathlib import Path
import argparse
import shutil

ROOT = Path(__file__).resolve().parents[1]

# dataset key (as in src/experiment/run_ladder_experiment.py DATASETS)
#   -> original dataset directory name
DATASET_DIRS = {
    'BibTeX2DocBook': 'models_BibTexML2DocBook',
    'CPL2SPL': 'models_CPL2SPL',
    'UML2ER': 'models_UML2ER',
    'Ecore2Maude': 'models_Ecore2Maude',
    'Ant2Maven': 'models_Ant2Maven',
    'Grafcet2PetriNet': 'models_Grafcet2PetriNet',
}
PIPELINE_ITEMS = ['src', 'scripts', 'lib', 'tests',
                  'run_pipeline.sh', 'requirements_local.txt']


def ocl_source(subject: str) -> Path:
    files = sorted((ROOT / 'data' / 'ocl' / subject).glob('OCL_*'))
    if len(files) != 1:
        raise SystemExit(f'Expected exactly one OCL_* contract in data/ocl/{subject}, found {files}')
    return files[0]


def check() -> None:
    problems = []
    for item in PIPELINE_ITEMS:
        if not (ROOT / 'code' / 'pipeline' / item).exists():
            problems.append(f'code/pipeline/{item}')
    tpl = ROOT / 'data' / 'prompts' / 'templates' / 'generate_test_model_v2.txt'
    if not tpl.is_file():
        problems.append(str(tpl))
    frozen = ROOT / 'data' / 'prompts' / 'frozen_prompts' / 'manifest.json'
    if not frozen.is_file():
        problems.append(str(frozen))
    n_ecore = n_mutants = 0
    for subject, dirname in DATASET_DIRS.items():
        sdir = ROOT / 'subjects' / subject
        if not sdir.is_dir():
            problems.append(f'subjects/{subject}')
            continue
        ecore = list(sdir.glob('*.ecore'))
        trans = list((sdir / 'transformations').glob('*.atl'))
        scen = sdir / 'scenarios'
        muts = list((ROOT / 'data' / 'mutants' / subject).glob('*.atl'))
        ocl = ocl_source(subject)
        if not ecore:
            problems.append(f'subjects/{subject}: no .ecore')
        if not trans:
            problems.append(f'subjects/{subject}/transformations: no .atl')
        if not scen.is_dir():
            problems.append(f'subjects/{subject}/scenarios')
        if not muts:
            problems.append(f'data/mutants/{subject}: no .atl')
        n_ecore += len(ecore)
        n_mutants += len(muts)
    if problems:
        raise SystemExit('Missing pipeline inputs:\n  ' + '\n  '.join(map(str, problems)))
    print(f'PASS: 6 subjects ({n_ecore} ecore, {n_mutants} mutant .atl), OCL contracts, '
          f'prompt template and frozen manifest are all available in the organized bundle.')


def prepare(output: Path) -> None:
    if not output.resolve().is_relative_to(ROOT / 'code') or output in {ROOT / 'code', ROOT / 'code' / 'pipeline'}:
        raise SystemExit('Execution-copy output must be a new subdirectory within code/.')
    if output.exists():
        raise SystemExit(f'Refusing to overwrite an existing execution copy: {output}')

    def copy_tree(src: Path, dst: Path):
        shutil.copytree(src, dst, dirs_exist_ok=True)

    for item in PIPELINE_ITEMS:
        src = ROOT / 'code' / 'pipeline' / item
        if src.is_dir():
            copy_tree(src, output / item)
        else:
            output.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, output / item)
    n_files = 0
    for subject, dirname in DATASET_DIRS.items():
        dsd = output / 'datasets' / dirname
        copy_tree(ROOT / 'subjects' / subject, dsd)
        copy_tree(ROOT / 'data' / 'mutants' / subject, dsd / 'transformations')
        shutil.copy2(ocl_source(subject), dsd / ocl_source(subject).name)
        n_files += sum(1 for p in dsd.rglob('*') if p.is_file())
    copy_tree(ROOT / 'data' / 'prompts' / 'templates', output / 'prompts')
    copy_tree(ROOT / 'data' / 'prompts' / 'frozen_prompts',
              output / 'reproducibility' / 'frozen_prompts')
    print(f'Prepared execution copy: {output}')
    print(f'datasets/: 6 subjects, {n_files} files (metamodels + scenarios + '
          f'transformations incl. mutants + OCL contracts)')
    print('Historical absolute paths, API keys and external raw-evidence '
          'dependencies still need configuration before any real run.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Check inputs without copying files')
    parser.add_argument('--refresh-code', action='store_true', help='Refresh src/scripts/lib/tests and launcher in an existing runtime, preserving datasets and config')
    parser.add_argument('--output', type=Path, default=ROOT / 'code/runtime/pipeline_toolchain')
    args = parser.parse_args()
    check()
    if args.check:
        return
    if args.refresh_code:
        target = args.output.resolve()
        if not target.is_relative_to(ROOT / 'code/runtime') or not (target / 'datasets').is_dir():
            raise SystemExit('--refresh-code requires an existing execution copy under code/runtime/')
        for item in PIPELINE_ITEMS:
            source = ROOT / 'code/pipeline' / item
            if source.is_dir():
                shutil.copytree(source, target / item, dirs_exist_ok=True)
            else:
                shutil.copy2(source, target / item)
        print(f'Refreshed pipeline code and libraries in {target}')
        return
    prepare(args.output.resolve())


if __name__ == '__main__':
    main()
