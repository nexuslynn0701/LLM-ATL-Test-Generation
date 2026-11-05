"""The published Table 4 must equal the containment-size audit deliverables."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reproduction"))
from common import DATA, read_csv


class ModelSizeTests(unittest.TestCase):
    def test_published_summary_matches_audit_deliverables(self):
        audit_dir = DATA / "rq1/supplementary/model_size_audit"
        gen_map = {"GPT": "GPT", "Qwen": "Qwen", "DeepSeek": "DeepSeek-Flash",
                   "Yekta-ACO": "Yekta-ACO"}
        prompt_map = {"sm": "SM", "stm": "STM", "astm": "ASTM", "astmo": "ASTMO",
                      "random": "N/A", "n/a": "N/A"}
        audit = {(r["subject"], gen_map[r["approach"]], prompt_map[r["prompt"]]): r
                 for r in read_csv(audit_dir / "audit_group_summary.csv")}
        diff = read_csv(audit_dir / "audit_paper_diff.csv")
        summary = read_csv(DATA / "experiment_results/RQ1/model_size.csv")
        self.assertEqual(len(summary), 78)
        self.assertFalse({"q1", "q3", "iqr"} & set(summary[0]))
        ok_groups = empty_cells = not_applicable = 0
        for row in summary:
            key = (row["subject"], row["test_generator"], row["prompt_configuration"])
            if row["status"] == "EMPTY_ESTAR":
                self.assertEqual(row["n"], "0")
                self.assertTrue(all(row[k] == "N/A" for k in ("min", "median", "mean", "max")))
                empty_cells += 1
                continue
            if row["status"] == "NOT_APPLICABLE":
                self.assertNotIn(key, audit)
                self.assertEqual(row["n"], "N/A")
                not_applicable += 1
                continue
            group = audit[key]
            self.assertEqual([row["n"], row["min"], row["median"], row["mean"], row["max"], row["status"]],
                             [group["n"], group["min"], group["median"], group["mean"], group["max"], group["status"]])
            ok_groups += 1
        self.assertEqual((ok_groups, empty_cells, not_applicable), (71, 4, 3))
        self.assertEqual(len(diff), 75)
        index = {(r["subject"], r["test_generator"]): r for r in summary if r["test_generator"] == "Yekta-ACO"}
        self.assertEqual(index["CPL2SPL", "Yekta-ACO"]["n"], "96")
        self.assertEqual(index["CPL2SPL", "Yekta-ACO"]["mean"], "10.00")
        self.assertEqual(index["UML2ER", "Yekta-ACO"]["n"], "100")
        self.assertEqual(index["BibTeX2DocBook", "Yekta-ACO"]["status"], "OK")
        self.assertEqual(index["BibTeX2DocBook", "Yekta-ACO"]["n"], "100")


if __name__ == "__main__":
    unittest.main()
