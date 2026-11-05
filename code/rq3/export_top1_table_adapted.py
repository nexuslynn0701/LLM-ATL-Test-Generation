"""Export current ACO baseline fragments and retained-configuration tables."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'code/reproduction'))
from export_current_rq3_tables import main
if __name__ == '__main__':
    main()
