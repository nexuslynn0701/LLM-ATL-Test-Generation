"""Compute all 18 formulas and pooled EXAM/Top-1 from a fresh run, without replay archives."""
from pathlib import Path
import argparse
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiment_pipeline.evidence import load_run
from experiment_pipeline.aggregate import rq3

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-run',type=Path,required=True)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    out = args.output or args.from_run/'derived/rq3'
    rows = rq3(load_run(args.from_run),out)
    print(f'Wrote {len(rows)} mutant/formula records to {out}')
