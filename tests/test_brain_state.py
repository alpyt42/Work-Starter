"""Regression checks for the cross-brain state tool (no network, no real brain)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/brain-state.py"


class BrainStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.work = self.root / "Work"
        self.inbox = self.root / "transcripts"
        self.inbox.mkdir()
        for name in ("a.txt", "b.txt", "c.txt", "summary.md"):
            (self.inbox / name).write_text("x", encoding="utf-8")
        self.make_brain("brain", {"a.txt": {"status": "traite"}})
        self.make_brain("brain-perso", {"b.txt": {"status": "a-decider"}})
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

    def test_new_ignores_files_tracked_by_any_brain(self) -> None:
        result = self.run_tool("transcripts", "--new")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split(), ["c.txt"])

    def test_where_reports_owner(self) -> None:
        result = self.run_tool("transcripts", "--where", "b.txt")
        self.assertEqual(result.stdout.strip(), "b.txt\tbrain-perso\ta-decider")
        self.assertEqual(self.run_tool("transcripts", "--where", "c.txt").returncode, 1)

    def test_same_transcript_in_two_brains_is_refused(self) -> None:
        state = self.work / "brain-perso/.data/transcripts.json"
        state.write_text(json.dumps({"a.txt": {"status": "a-decider"}}), encoding="utf-8")
        result = self.run_tool("transcripts", "--new")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("plusieurs brains", result.stderr)

    def test_missing_expected_brain_stops(self) -> None:
        config = self.work / "brain/.data/local-paths.json"
        config.write_text(json.dumps({"brains": ["brain", "brain-perso", "brain-asso"]}), encoding="utf-8")
        result = self.run_tool("transcripts", "--new")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("brain-asso", result.stderr)


if __name__ == "__main__":
    unittest.main()
