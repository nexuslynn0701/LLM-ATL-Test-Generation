"""Compatibility alias for current-scope RQ3 recomputation."""
from pathlib import Path
import subprocess,sys
ROOT=Path(__file__).resolve().parents[2]
if __name__ == '__main__':
    raise SystemExit(subprocess.run([sys.executable,str(ROOT/'code/reproduction/build_tables.py'),'--only','rq3']).returncode)
