"""CI docs-only classification must be explicit and fail closed."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "ci_scope.py"
spec = importlib.util.spec_from_file_location("ci_scope", SCRIPT)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class ScopeTests(unittest.TestCase):
    def test_readme_only(self):
        self.assertTrue(scope.classify([("M", "README.md")]))

    def test_bilingual_readmes_use_fast_path_when_modified(self):
        self.assertTrue(scope.classify([("M", "README.md"), ("M", "README_EN.md")]))

    def test_adding_or_removing_language_file_still_runs_full_checks(self):
        self.assertFalse(scope.classify([("A", "README_EN.md")]))
        self.assertFalse(scope.classify([("D", "README_EN.md")]))

    def test_multiple_existing_docs(self):
        self.assertTrue(scope.classify([("M", "DESIGN.md"), ("M", "web/README.md")]))

    def test_other_documentation_path_forces_full(self):
        self.assertFalse(scope.classify([("M", "SECURITY.md")]))

    def test_code_and_lockfiles_force_full(self):
        for path in ("mcp-server/src/index.ts", "data-pipeline/src/build.py",
                     "mcp-server/package-lock.json", "data-pipeline/uv.lock"):
            with self.subTest(path=path):
                self.assertFalse(scope.classify([("M", "README.md"), ("M", path)]))

    def test_security_and_ci_changes_force_full(self):
        for path in (".github/workflows/ci.yml", "scripts/ci_scope.py",
                     "scripts/tests/test_ci_scope.py", ".env.example"):
            with self.subTest(path=path):
                self.assertFalse(scope.classify([("M", path)]))

    def test_added_deleted_renamed_doc_forces_full(self):
        for status in ("A", "D", "R100"):
            with self.subTest(status=status):
                self.assertFalse(scope.classify([(status, "README.md")]))

    def test_unknown_or_empty_forces_full(self):
        self.assertFalse(scope.classify(None))
        self.assertFalse(scope.classify([]))

    def test_unrecognized_event_forces_full(self):
        self.assertIsNone(scope.list_changes("workflow_dispatch", "b" * 40, "", "a" * 40))

    def test_zero_before_forces_full(self):
        self.assertIsNone(scope.list_changes("push", "b" * 40, "0" * 40, ""))

    def test_malformed_sha_forces_full(self):
        self.assertIsNone(scope.list_changes("pull_request", "not-a-hash", "", "a" * 40))

    @patch.object(scope.subprocess, "run")
    def test_pr_change_scope_uses_base_and_head(self, mock_run):
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 0, b"M\0README.md\0", b""),
        ]
        head = "b" * 40
        base = "a" * 40
        self.assertEqual([("M", "README.md")], scope.list_changes("pull_request", head, "", base))
        self.assertEqual(mock_run.call_args_list[1].args[0][-2:], [base, head])

    @patch.object(scope.subprocess, "run")
    def test_force_push_is_unknown(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess([], 1, b"", b"")
        self.assertIsNone(scope.list_changes("push", "b" * 40, "a" * 40, ""))

    @patch.object(scope.subprocess, "run")
    def test_diff_failure_forces_full(self, mock_run):
        mock_run.side_effect = [
            subprocess.CompletedProcess([], 0, b"", b""),
            subprocess.CompletedProcess([], 1, b"", b"error"),
        ]
        self.assertIsNone(scope.list_changes("push", "b" * 40, "a" * 40, ""))
