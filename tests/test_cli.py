"""Test externally visible commands using Python subprocesses and temporary files."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source import benchmark

DATA = "R (Name, Age) = {\nJohn, 32\nAlice, 28\n'O''Brien', 29\n}\n"


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="python-ra-cli-")
        self.addCleanup(self.directory.cleanup)
        self.data_path = Path(self.directory.name) / "data.ra"
        self.data_path.write_text(DATA, encoding="utf-8")

    def command(self, script, arguments):
        return subprocess.run(
            [sys.executable, str(PROJECT_ROOT / script)] + arguments,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=20,
        )

    def test_tree_printing_without_evaluation_or_data_loading(self):
        result = self.command("ra.py", ["--tree", "--data", "this-file-does-not-exist.ra", "A union B minus C"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("Minus\n"))
        self.assertIn("Union", result.stdout)
        self.assertIn("Relation(A)", result.stdout)

    def test_25_empty_result_prints_schema(self):
        result = self.command("ra.py", ["--data", str(self.data_path), "select[Age>100](R)"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Name", result.stdout)
        self.assertIn("Age", result.stdout)
        self.assertIn("(0 tuples)", result.stdout)
        self.assertNotIn("John", result.stdout)

    def test_results_and_operator_counters(self):
        result = self.command("ra.py", ["--data", str(self.data_path), "--stats", "project[Name](select[Age>=29](R))"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'John'", result.stdout)
        self.assertIn("'O''Brien'", result.stdout)
        self.assertNotIn("Alice", result.stdout)
        self.assertIn("(2 tuples)", result.stdout)
        self.assertIn("select: examined=3, output=2", result.stderr)
        self.assertIn("project: examined=2, output=2", result.stderr)

    def test_five_error_categories_without_tracebacks(self):
        examples = [("Lexical", "select[Name='John](R)"), ("Syntax", "select[Age>30](R"), ("Name", "Missing"), ("Schema", "R union project[Name](R)"), ("Type", "select[Age>'30'](R)")]
        for category, query in examples:
            with self.subTest(category=category):
                result = self.command("ra.py", ["--data", str(self.data_path), query])
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(f"{category} error", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                if category in ("Lexical", "Syntax"):
                    self.assertIn("line 1, column", result.stderr)

    def test_missing_files_and_unknown_flags(self):
        for arguments in (["--data", "no-such-file.ra", "R"], ["--unknown-flag", "R"]):
            result = self.command("ra.py", arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("Traceback", result.stderr)

    def test_generator_roundtrip_and_validation(self):
        generated = self.command("source/generate.py", ["--n", "4", "--m", "4", "--match-rate", "2", "--out", str(self.data_path)])
        self.assertEqual(generated.returncode, 0, generated.stderr)
        result = self.command("ra.py", ["--data", str(self.data_path), "--stats", "R join[R.b=S.b] S"])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("(8 tuples)", result.stdout)
        self.assertIn("join: examined=16, output=8", result.stderr)
        for arguments in (["--n", "-1"], ["--n"], ["--unknown", "1"], ["--match-rate", "NaN"]):
            bad = self.command("source/generate.py", arguments)
            self.assertNotEqual(bad.returncode, 0)
            self.assertNotIn("Traceback", bad.stderr)

    def test_benchmark_smoke_saves_actual_results(self):
        with tempfile.TemporaryDirectory(prefix="python-ra-benchmark-") as directory:
            result = self.command("source/benchmark.py", ["--sizes", "8,16", "--match-size", "8", "--match-rates", "0,1,2", "--out", directory])
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(directory) / "results.json").read_text(encoding="utf-8"))
            self.assertTrue(report["complete"])
            self.assertEqual(len(report["records"]), 9)
            for row in report["records"]:
                self.assertGreaterEqual(row["seconds"], 0)
                if row["operator"] == "join":
                    self.assertEqual(row["examined"], row["n"] * row["m"])
                if row["operator"] == "select":
                    self.assertEqual(row["examined"], row["n"])
            rates = [row for row in report["records"] if row["experiment"] == "match-rate"]
            self.assertEqual([row["output_rows"] for row in rates], [0, 8, 16])
            self.assertEqual([row["actual_matches_per_r"] for row in rates], [0, 1, 2])

    def test_benchmark_default_destination_is_inside_python_project(self):
        # Stop at the first save to inspect the destination without writing
        # files or running measurements. This holds even from another cwd.
        class CapturedDestination(Exception):
            pass

        captured = []

        def capture(report, directory):
            captured.append(directory)
            raise CapturedDestination()

        with patch.object(benchmark, "save", side_effect=capture), \
                patch.object(benchmark.Path, "mkdir"):
            with self.assertRaises(CapturedDestination):
                benchmark.run_benchmark(sizes=[8], match_size=8, match_rates=[0])
        self.assertEqual(captured, [PROJECT_ROOT / "measurements"])


if __name__ == "__main__":
    unittest.main()
