"""Regression checks for the cross-brain state tool (no network, no real brain)."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOL = Path(__file__).resolve().parents[1] / "tools/brain/brain-state.py"


class BrainStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.work = self.root / "Work"
        self.inbox = self.root / "transcripts"
        self.inbox.mkdir()
        for name in ("a.txt", "b.txt", "c.txt", "summary.md"):
            (self.inbox / name).write_text("x", encoding="utf-8")
        self.make_brain("brain", {"a.txt": {"status": "processed"}})
        self.make_brain("brain-perso", {"b.txt": {"status": "undecided"}})
        (self.work / "brain-notes").mkdir()  # no AGENTS.md: not a brain
        self.env = {**os.environ, "WORK_DIR": str(self.work), "TRANSCRIPTS_DIR": str(self.inbox)}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def make_brain(self, name: str, transcripts: dict) -> None:
        data = self.work / name / ".data"
        data.mkdir(parents=True)
        (self.work / name / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        (data / "transcripts.json").write_text(json.dumps(transcripts), encoding="utf-8")

    def run_tool(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), *args], env=self.env, capture_output=True, text=True)

    def test_lists_brains_default_first(self) -> None:
        result = self.run_tool("brains")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line.split("\t")[0] for line in result.stdout.splitlines()], ["brain", "brain-perso"])

    def declare(self, name: str, scope: str, description: str) -> None:
        (self.work / name / ".data/brain.json").write_text(
            json.dumps({"version": 1, "scope": scope, "description": description}), encoding="utf-8"
        )

    def test_brains_print_scope_and_description(self) -> None:
        self.declare("brain", "employer", "Employer context and its clients; never anything personal.")
        self.declare("brain-perso", "personal", "Personal meetings\n  and career,   never any client.")
        result = self.run_tool("brains")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [line.split("\t") for line in result.stdout.splitlines()]
        self.assertEqual(rows, [
            ["brain", "1 transcript(s) tracked", "employer", "Employer context and its clients; never anything personal."],
            ["brain-perso", "1 transcript(s) tracked", "personal", "Personal meetings and career, never any client."],
        ])

    def test_brains_without_declaration_have_empty_scope_and_description(self) -> None:
        self.declare("brain", "employer", "Employer.")
        rows = [line.split("\t") for line in self.run_tool("brains").stdout.splitlines()]
        self.assertEqual(rows[1], ["brain-perso", "1 transcript(s) tracked", "", ""])

    def test_unreadable_declaration_is_reported(self) -> None:
        (self.work / "brain/.data/brain.json").write_text("{", encoding="utf-8")
        result = self.run_tool("brains")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("brain/.data/brain.json", result.stderr)

    def test_new_ignores_files_tracked_by_any_brain(self) -> None:
        result = self.run_tool("transcripts", "--new")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["c.txt"])

    def test_where_reports_owner(self) -> None:
        result = self.run_tool("transcripts", "--where", "b.txt")
        self.assertEqual(result.stdout.strip(), "b.txt\tbrain-perso\tundecided")
        self.assertEqual(self.run_tool("transcripts", "--where", "c.txt").returncode, 1)

    def test_same_transcript_in_two_brains_is_refused(self) -> None:
        state = self.work / "brain-perso/.data/transcripts.json"
        state.write_text(json.dumps({"a.txt": {"status": "undecided"}}), encoding="utf-8")
        result = self.run_tool("transcripts", "--new")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("several brains", result.stderr)

    def test_missing_expected_brain_stops(self) -> None:
        config = self.work / "brain/.data/local-paths.json"
        config.write_text(json.dumps({"brains": ["brain", "brain-perso", "brain-asso"]}), encoding="utf-8")
        result = self.run_tool("transcripts", "--new")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("brain-asso", result.stderr)

    def test_default_brain_is_the_one_of_the_setting_and_carries_the_shared_config(self) -> None:
        self.make_brain("brain-initech", {})
        (self.work / "work-config.local.json").write_text(json.dumps({"version": 1, "defaultBrain": "brain-initech"}), encoding="utf-8")
        result = self.run_tool("brains")
        self.assertEqual([line.split("\t")[0] for line in result.stdout.splitlines()], ["brain-initech", "brain", "brain-perso"])
        # Only the default brain's local-paths.json counts: the one of `brain` is ignored, the expected brain of the other is missing.
        (self.work / "brain/.data/local-paths.json").write_text(json.dumps({"brains": ["brain-ghost"]}), encoding="utf-8")
        self.assertEqual(self.run_tool("brains").returncode, 0)
        (self.work / "brain-initech/.data/local-paths.json").write_text(json.dumps({"brains": ["brain-asso"]}), encoding="utf-8")
        result = self.run_tool("brains")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("brain-asso", result.stderr)

    def test_renamed_default_brain_is_found_without_a_setting(self) -> None:
        (self.work / "brain").rename(self.work / "brain-initech")
        (self.work / "brain-perso").rename(self.work / "brain-other")  # two brains and no `brain/`: no default, by name
        env = {key: value for key, value in self.env.items() if key != "TRANSCRIPTS_DIR"}
        self.env = env
        result = self.run_tool("brains")
        self.assertEqual([line.split("\t")[0] for line in result.stdout.splitlines()], ["brain-initech", "brain-other"])
        result = self.run_tool("transcripts", "--new")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("defaultBrain", result.stderr)
        (self.work / "brain-other").rename(self.work / "gone")  # a single brain: it is the default
        (self.work / "brain-initech/.data/local-paths.json").write_text(json.dumps({"brains": ["brain-initech"]}), encoding="utf-8")
        result = self.run_tool("transcripts", "--new")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("transcripts_dir missing from brain-initech/.data/local-paths.json", result.stderr)

    def test_invalid_setting_stops_with_a_clear_message(self) -> None:
        (self.work / "work-config.local.json").write_text(json.dumps({"version": 1, "defaultBrain": "brain-nope"}), encoding="utf-8")
        result = self.run_tool("brains")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("defaultBrain brain-nope is not a brain", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_unreadable_transcript_folder_reports_access_error(self) -> None:
        spec = importlib.util.spec_from_file_location("brain_state", TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        brains = [self.work / "brain", self.work / "brain-perso"]
        with patch.dict(os.environ, {"TRANSCRIPTS_DIR": str(self.inbox)}), patch.object(
            Path, "iterdir", side_effect=PermissionError(1, "Operation not permitted", str(self.inbox))
        ):
            with self.assertRaises(SystemExit) as error:
                module.cmd_transcripts(brains, new=True, where=None)
        self.assertIn("Access denied", str(error.exception))
        self.assertIn(str(self.inbox), str(error.exception))


if __name__ == "__main__":
    unittest.main()
