"""Check rule union semantics, released evidence, and safe repeatability."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "reproduction"))
from common import DATA, read_csv, write_csv
from rule_coverage import rebuild_rule_coverage, union_coverage


class RuleCoverageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.data = Path(temporary.name)
        for name in ("rq1/data/rule_coverage.csv", "rq1/supplementary/source_rule_coverage.csv",
                     "rq1/supplementary/source_population.csv", "rq1/data/subjects.csv"):
            target = self.data / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DATA / name, target)

    def test_union_counts_overlap_once_and_retains_complementary_rules(self):
        covered, percentage = union_coverage(
            [{"a", "b"}, {"b", "c"}, {"c"}, set()], {"a", "b", "c", "d"})
        self.assertEqual(covered, {"a", "b", "c"})
        self.assertEqual(percentage, 75.0)
        with self.assertRaises(ValueError):
            union_coverage([{"unknown"}], {"a"})

    def test_released_results_and_reruns_preserve_original_rows(self):
        path = self.data / "rq1/data/rule_coverage.csv"
        base = [r for r in read_csv(path) if r["prompt_condition"] != "All prompts"]
        rebuild_rule_coverage(self.data)
        updated = read_csv(path)
        self.assertEqual([r for r in updated if r["prompt_condition"] != "All prompts"], base)
        self.assertEqual(len(base), 75)
        self.assertEqual(len(updated), 99)
        table = {r["Approach"]: r for r in read_csv(self.data / "rq1/tables/rq1_rule_coverage_all_prompts.csv")}
        for llm, overall in (("GPT", "97.58"), ("Qwen", "80.81"),
                             ("DeepSeek", "96.71"), ("All LLM", "99.12")):
            self.assertEqual(table[llm]["Overall"], overall)
        index = {(r["subject"], r["llm"]): r for r in updated if r["prompt_condition"] == "All prompts"}
        for llm, covered in (("GPT", "28"), ("Qwen", "27"), ("DeepSeek", "28"), ("All LLM", "30")):
            self.assertEqual(index["Ant2Maven", llm]["covered_rules"], covered)
        self.assertEqual(index["CPL2SPL", "Qwen"]["rule_coverage_pct"], "0.00")
        self.assertEqual(index["CPL2SPL", "Qwen"]["n_trace_eligible"], "0")
        self.assertEqual(index["Ant2Maven", "GPT"]["n_attempts"], "400")
        self.assertEqual(index["Ant2Maven", "All LLM"]["n_attempts"], "1200")
        outputs = [path, self.data / "rq1/data/rule_coverage_overall_pooled.csv",
                   *sorted((self.data / "rq1/tables").glob("*.csv"))]
        first = [p.read_bytes() for p in outputs]
        rebuild_rule_coverage(self.data)
        self.assertEqual(first, [p.read_bytes() for p in outputs])
        pooled = {(r["generator"], r["prompt_condition"]): r
                  for r in read_csv(self.data / "rq1/data/rule_coverage_overall_pooled.csv")}
        self.assertEqual(pooled["GPT", "SM"]["pooled_covered_rules"], "95")
        self.assertEqual(pooled["GPT", "SM"]["pooled_total_rules"], "110")
        self.assertEqual(pooled["GPT", "SM"]["overall_pooled_pct"], "86.36")
        self.assertEqual(pooled["Yekta-ACO", "N/A"]["subjects_included"], "3")
        self.assertEqual(pooled["Yekta-ACO", "N/A"]["overall_pooled_pct"], "88.89")

    def test_missing_source_evidence_fails_without_changing_outputs(self):
        path = self.data / "rq1/supplementary/source_rule_coverage.csv"
        rows = read_csv(path)
        rows = [r for r in rows if not (r["subject"] == "Ant2Maven" and r["provider"] == "gpt"
                                       and r["condition"] == "astmo" and r["source_id"] == "0001")]
        write_csv(path, rows, list(rows[0]))
        output = self.data / "rq1/data/rule_coverage.csv"
        before = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "Missing rule-level evidence"):
            rebuild_rule_coverage(self.data)
        self.assertEqual(before, output.read_bytes())

    def test_changed_rule_count_fails_before_writing(self):
        path = self.data / "rq1/supplementary/source_rule_coverage.csv"
        rows = read_csv(path)
        row = next(r for r in rows if r["subject"] == "Ant2Maven" and r["provider"] == "gpt"
                   and r["condition"] == "astmo" and r["source_id"] == "0001")
        row["covered"] = "1" if row["covered"] == "0" else "0"
        write_csv(path, rows, list(rows[0]))
        with self.assertRaisesRegex(ValueError, "Source coverage differs"):
            rebuild_rule_coverage(self.data)


if __name__ == "__main__":
    unittest.main()
