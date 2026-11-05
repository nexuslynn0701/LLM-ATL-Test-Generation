"""Validate the current canonical mutant universe and compiled artifacts."""
from pathlib import Path
import sys

RUNTIME = Path(__file__).resolve().parents[1]
ROOT = next(parent for parent in RUNTIME.parents if (parent/'code/run_pipeline.py').is_file())
sys.path.insert(0, str(RUNTIME))
sys.path.insert(0, str(ROOT/'code'))
from src.experiment.subject_config import get_mutant_executor_config
from experiment_pipeline.evidence import protocol

def main():
    universes = protocol()
    count = 0
    for subject, universe in universes.items():
        cfg = get_mutant_executor_config(subject)
        for name in universe['faults']:
            path = Path(cfg['transformations_dir'])/(name+'.asm')
            if not path.is_file():
                raise FileNotFoundError(path)
        count += len(universe['faults'])
        print(f"PASS {subject}: {len(universe['rules'])} rules, {len(universe['faults'])} canonical mutants")
    if count != 288:
        raise ValueError(f'Expected 288 canonical mutants, got {count}')
    print('PASS: six subjects and all 288 canonical compiled mutants')

if __name__ == '__main__':
    main()
