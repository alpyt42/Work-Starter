"""Regression checks for the decision registers tool (no network, temporary brain)."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/brain/decision.py"
DECISIONS = """# Decisions — Gamma

> Citation.

## Proposed

### Alpha (2026-10-01, status: proposed)
- **Context:** C1.
- **Decision:** D1.
- **Source:** [CR](../sources/cr.md)

### Beta ronde (2026-10-02, status: proposed)
- **Decision:** D2.
- **Source:** [CR](../sources/cr.md)

### Beta carrée (2026-10-03)
- **Decision:** D3.
- **Source:** [CR](../sources/cr.md)

## Accepted

### Gamma ancienne (2026-09-01, status: active)
- **Decision:** D4.
- **Accepted:** Owner, 2026-09-01.

## Rejected / superseded

### Delta (2026-08-01, status: rejected)
- **Decision:** D5.
"""


class DecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name) / "brain"
        (self.brain / ".data").mkdir(parents=True)
        (self.brain / ".data/doctor.json").write_text('{"owner": "Owner"}\n', encoding="utf-8")
        self.folder = self.brain / "projects/clients/acme/missions/gamma"
        (self.folder / "state").mkdir(parents=True)
        (self.folder / "state/actions.md").write_text("# Actions — Gamma mission\n\n## Open\n", encoding="utf-8")
        self.register = self.folder / "state/decisions.md"
        self.register.write_text(DECISIONS, encoding="utf-8")
        self.env = {**os.environ, "ACTION_NOW": "2026-10-13 14:32"}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_tool(self, *args: str, code: int = 0) -> dict | list | str:
        result = subprocess.run([sys.executable, str(TOOL), "--brain", str(self.brain), *args], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except ValueError:
            return result.stdout

    def text(self) -> str:
        return self.register.read_text(encoding="utf-8")

    # --- reading ---

    def test_list_numbers_sections_and_tolerates_missing_status(self) -> None:
        found = self.run_tool("list", "--project", "acme/gamma")
        self.assertEqual([(d["number"], d["state"], d["status"]) for d in found],
                         [(1, "proposed", "proposed"), (2, "proposed", "proposed"), (3, "proposed", ""),
                          (4, "accepted", "active"), (5, "rejected", "rejected")])
        self.assertEqual(found[2]["date"], "2026-10-03")
        self.assertEqual(len(self.run_tool("list", "--status", "accepted")), 1)
        table = self.run_tool("list", "--project", "acme/gamma", "--table")
        self.assertIn("  1. [proposed] 2026-10-01 — Alpha  (acme / gamma)", table)

    def test_show_by_number_and_substring(self) -> None:
        by_number = self.run_tool("show", "4", "--project", "acme/gamma")
        by_text = self.run_tool("show", "ANCIENNE", "--project", "acme/gamma")
        self.assertEqual(by_number["title"], "Gamma ancienne")
        self.assertEqual(by_number["fields"]["Accepted"], "Owner, 2026-09-01.")
        self.assertEqual(by_number, by_text)

    def test_ambiguous_and_missing_references(self) -> None:
        self.assertEqual(self.run_tool("show", "beta", "--project", "acme/gamma", code=4)["kind"], "conflict")
        self.assertEqual(self.run_tool("show", "inconnue", "--project", "acme/gamma", code=3)["kind"], "not_found")
        self.assertEqual(self.run_tool("show", "42", "--project", "acme/gamma", code=3)["kind"], "not_found")
        self.assertEqual(self.run_tool("show", "1", "--project", "inconnu", code=2)["kind"], "bad_request")

    # --- propose ---

    def test_propose_appends_to_proposed(self) -> None:
        result = self.run_tool("propose", "--project", "acme/gamma", "--title", "Nouvelle (test)", "--decision", "D6",
                               "--source", "[CR](../sources/cr.md)", "--context", "C6", "--consequences", "K6")
        self.assertEqual((result["number"], result["label"]), (4, "proposal “Nouvelle (test)”"))
        self.assertIn(
            "- **Source:** [CR](../sources/cr.md)\n\n"
            "### Nouvelle (test) (2026-10-13, status: proposed)\n"
            "- **Context:** C6\n- **Decision:** D6\n- **Consequences:** K6\n- **Source:** [CR](../sources/cr.md)\n\n"
            "## Accepted\n", self.text())
        self.assertEqual(self.run_tool("list", "--project", "acme/gamma")[3]["title"], "Nouvelle (test)")

    def test_propose_creates_missing_register(self) -> None:
        self.register.unlink()
        result = self.run_tool("propose", "--project", "acme/gamma", "--title", "Première", "--decision", "D",
                               "--source", "s", "--date", "2026-10-10")
        self.assertTrue(result["created_file"])
        text = self.text()
        self.assertTrue(text.startswith("# Decisions — Gamma mission\n\n> "))
        self.assertIn("## Proposed\n\n### Première (2026-10-10, status: proposed)\n- **Decision:** D\n- **Source:** s\n\n## Accepted\n\n## Rejected / superseded\n", text)
        self.assertTrue(text.endswith("## Rejected / superseded\n"))
        self.assertEqual([d["title"] for d in self.run_tool("list", "--project", "acme/gamma")], ["Première"])

    def test_propose_validates_input(self) -> None:
        base = ["propose", "--project", "acme/gamma", "--decision", "D", "--source", "s"]
        for bad in (["--title", "deux\nlignes"], ["--title", "T ➕ 2026-01-01"], ["--title", "T", "--date", "2026-02-30"],
                    ["--title", "T", "--date", "13/10/2026"], ["--title", "Alpha"]):
            self.run_tool(*base, *bad, code=2 if "Alpha" not in bad else 4)
        self.assertEqual(self.text(), DECISIONS)

    # --- accept / reject / supersede ---

    def test_accept_moves_to_top_and_keeps_content(self) -> None:
        result = self.run_tool("accept", "Alpha", "--project", "acme/gamma", "--on", "2026-10-14", "--note", "en comité")
        self.assertEqual((result["label"], result["from"], result["to"]), ("accept “Alpha”", "Proposed", "Accepted"))
        self.assertIn(
            "## Accepted\n\n### Alpha (2026-10-01, status: accepted)\n- **Context:** C1.\n- **Decision:** D1.\n"
            "- **Source:** [CR](../sources/cr.md)\n- **Accepted:** Owner, 2026-10-14 (en comité).\n\n"
            "### Gamma ancienne (2026-09-01, status: active)\n", self.text())
        self.assertEqual(self.text().count("### Alpha"), 1)
        self.assertEqual([d["state"] for d in self.run_tool("list", "--project", "acme/gamma")][:3], ["proposed", "proposed", "accepted"])

    def test_accept_adds_status_when_title_has_none(self) -> None:
        self.run_tool("accept", "carrée", "--project", "acme/gamma", "--by", "Reviewer")
        self.assertIn("### Beta carrée (2026-10-03, status: accepted)\n- **Decision:** D3.\n- **Source:** [CR](../sources/cr.md)\n"
                      "- **Accepted:** Reviewer, 2026-10-13.\n", self.text())

    def test_reject_moves_to_top_of_rejected(self) -> None:
        self.run_tool("reject", "2", "--project", "acme/gamma", "--on", "2026-10-12", "--reason", "hors périmètre")
        self.assertIn(
            "## Rejected / superseded\n\n### Beta ronde (2026-10-02, status: rejected)\n- **Decision:** D2.\n"
            "- **Source:** [CR](../sources/cr.md)\n- **Rejected:** Owner, 2026-10-12 (hors périmètre).\n\n### Delta", self.text())

    def test_supersede_moves_old_and_leaves_new(self) -> None:
        before_new = self.run_tool("show", "Alpha", "--project", "acme/gamma")["block"]
        result = self.run_tool("supersede", "ancienne", "--by", "Alpha", "--project", "acme/gamma", "--on", "2026-10-14")
        self.assertEqual(result["label"], "supersede “Gamma ancienne”")
        self.assertIn(
            "## Rejected / superseded\n\n### Gamma ancienne (2026-09-01, status: superseded)\n- **Decision:** D4.\n"
            "- **Accepted:** Owner, 2026-09-01.\n- **Superseded by:** “Alpha” (2026-10-14).\n\n### Delta", self.text())
        self.assertEqual(self.run_tool("show", "Alpha", "--project", "acme/gamma")["block"], before_new)
        self.assertEqual(self.text().split("## Accepted")[1].split("## Rejected")[0].strip(), "")

    def test_invalid_moves_are_refused(self) -> None:
        self.run_tool("accept", "Delta", "--project", "acme/gamma", code=2)
        self.run_tool("reject", "Gamma", "--project", "acme/gamma", code=2)
        self.run_tool("supersede", "Delta", "--by", "Alpha", "--project", "acme/gamma", code=2)
        self.run_tool("supersede", "Alpha", "--by", "Delta", "--project", "acme/gamma", code=2)
        self.run_tool("supersede", "Alpha", "--by", "1", "--project", "acme/gamma", code=2)
        self.run_tool("accept", "Alpha", "--project", "acme/gamma", "--on", "2026-13-01", code=2)
        self.run_tool("accept", "Alpha", "--project", "acme/gamma", "--note", "a\nb", code=2)
        self.assertEqual(self.text(), DECISIONS)

    def test_moving_last_block_of_a_section_keeps_layout(self) -> None:
        self.register.write_text(DECISIONS.replace("### Delta (2026-08-01, status: rejected)\n- **Decision:** D5.\n", ""), encoding="utf-8")
        self.run_tool("reject", "Alpha", "--project", "acme/gamma")
        self.run_tool("accept", "ronde", "--project", "acme/gamma")
        text = self.text()
        self.assertTrue(text.endswith("- **Rejected:** Owner, 2026-10-13.\n"), text)
        self.assertNotIn("\n\n\n", text)

    def test_dry_run_writes_nothing(self) -> None:
        for args in (["accept", "Alpha"], ["reject", "Alpha"], ["supersede", "ancienne", "--by", "Alpha"]):
            result = self.run_tool(*args, "--project", "acme/gamma", "--dry-run")
            self.assertTrue(result["dry_run"])
        result = self.run_tool("propose", "--project", "acme/gamma", "--title", "T", "--decision", "D", "--source", "s", "--dry-run")
        self.assertTrue(result["dry_run"])
        self.assertEqual(self.text(), DECISIONS)

    def test_conflict_when_file_changed_between_read_and_write(self) -> None:
        spec = importlib.util.spec_from_file_location("decision_tool", TOOL)
        assert spec and spec.loader
        tool = importlib.util.module_from_spec(spec)
        sys.modules["decision_tool"] = tool
        self.addCleanup(sys.modules.pop, "decision_tool", None)
        spec.loader.exec_module(tool)
        existing, lines = tool.read(self.register)
        self.register.write_text(DECISIONS + "\n### Autre (2026-10-13)\n", encoding="utf-8")
        with self.assertRaises(tool.ActionError) as caught:
            tool.commit(self.register, existing, lines, False)
        self.assertEqual(caught.exception.kind, "conflict")
        self.assertIn("### Autre", self.text())
        with self.assertRaises(tool.ActionError):
            tool.commit(self.register, None, lines, False)


FRENCH_DECISIONS = """# Décisions — Gamma

## Validées

### Alpha (2026-10-01, statut : validée)
- **Décision :** D1.
"""


class EarlierFrenchLabelsTest(unittest.TestCase):
    """The tool reads only the English labels: a register still written with the French ones is converted by migrate-english.py."""

    setUp, tearDown, run_tool, text = DecisionTest.setUp, DecisionTest.tearDown, DecisionTest.run_tool, DecisionTest.text

    def test_french_section_titles_are_not_understood(self) -> None:
        self.register.write_text(FRENCH_DECISIONS, encoding="utf-8")
        found = self.run_tool("list", "--project", "acme/gamma")
        self.assertEqual([(d["state"], d["section"]) for d in found], [("", "Validées")])
        self.run_tool("accept", "Alpha", "--project", "acme/gamma", code=2)
        self.assertEqual(self.text(), FRENCH_DECISIONS)


if __name__ == "__main__":
    unittest.main()
