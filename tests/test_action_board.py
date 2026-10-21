"""Regression checks for the read-only task board renderer (no network, no real brain)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/brain/action.py"

MISSION = """# Actions

## Ouvertes
- [/] **TST-001** — Jane — Avancer le livrable
    - échéance: 2026-10-01
- [ ] **TST-002** — Jane / John — Préparer la suite
- [ ] **TST-003** — John — Pas à moi
- [w] **TST-004** — John — Envoyer les accès
- [x] **TST-005** — Jane — Cochée hier ✅ 2026-10-10

## Terminées
- [x] **TST-006** — Jane — Cochée avant ✅ 2026-10-02
- [x] **TST-007** — Jane — Faite sans date
- [-] **TST-008** — Jane — Annulée ❌ 2026-10-09
- [x] **TST-010** — John — Close par un autre ✅ 2026-10-11
"""

SETUP = """# Actions

## Ouvertes
- [ ] **SET-001** — Jane — Outiller
"""


class TasksBoardTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        self.brain = self.work / "brain"
        for relative, content in (("projects/clients/acme/missions/m/state", MISSION), ("projects/internal/setup/state", SETUP)):
            folder = self.brain / relative
            folder.mkdir(parents=True)
            (folder / "actions.md").write_text(content, encoding="utf-8")
        (self.brain / ".data").mkdir()
        (self.brain / ".data/doctor.json").write_text('{"owner": "Jane"}', encoding="utf-8")
        self.env = {**os.environ, "WORK_DIR": str(self.work), "BRAIN_DIR": str(self.brain)}
        self.env.pop("BRAIN_OWNER", None)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_board(self, *args: str) -> str:
        result = subprocess.run([sys.executable, str(TOOL), "board", *args], env=self.env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def section(self, out: str, title: str) -> str:
        return out.split(f"## {title}", 1)[1].split("\n## ", 1)[0]

    def group(self, out: str, project: str, label: str) -> str:
        return self.section(out, project).split(f"**{label}**", 1)[1].split("\n**", 1)[0]

    def test_one_section_per_project_with_states_in_order(self) -> None:
        out = self.run_board()
        mission = self.section(out, "acme / m")
        self.assertLess(mission.index("**À faire**"), mission.index("**En cours**"))
        self.assertLess(mission.index("**En cours**"), mission.index("**En attente**"))
        self.assertIn("TST-001", self.group(out, "acme / m", "En cours"))
        self.assertIn("TST-004", self.group(out, "acme / m", "En attente"))
        todo = self.group(out, "acme / m", "À faire")
        self.assertIn("TST-002", todo)
        self.assertNotIn("TST-003", todo)
        self.assertIn("SET-001", self.group(out, "setup", "À faire"))
        self.assertNotIn("**En cours**", self.section(out, "setup"))

    def test_project_without_anything_to_show_is_listed_apart(self) -> None:
        folder = self.brain / "projects/clients/beta/missions/n/state"
        folder.mkdir(parents=True)
        (folder / "actions.md").write_text("## Ouvertes\n- [ ] **TST-020** — John — Pas à moi\n", encoding="utf-8")
        out = self.run_board()
        self.assertNotIn("## beta / n", out)
        self.assertIn("Rien en cours, en attente ou à faire : beta / n.", out)

    def test_recent_closures_cover_every_owner_newest_first(self) -> None:
        done = self.section(self.run_board(), "Terminées récemment")
        self.assertLess(done.index("TST-010"), done.index("TST-005"))
        self.assertLess(done.index("TST-005"), done.index("TST-008"))
        self.assertLess(done.index("TST-008"), done.index("TST-006"))
        self.assertIn("faite le 2026-10-11", done)
        self.assertIn("annulée le 2026-10-09", done)
        self.assertNotIn("TST-007", done)
        self.assertNotIn("✅", done)

    def test_links(self) -> None:
        self.assertIn("(brain/projects/clients/acme/missions/m/state/actions.md#L4)", self.run_board())

    def test_write_uses_links_relative_to_the_board(self) -> None:
        self.run_board("--write")
        board = (self.work / "agents/tasks-board.md").read_text(encoding="utf-8")
        self.assertIn("(../brain/projects/clients/acme/missions/m/state/actions.md#L4)", board)

    def test_watch_rewrites_the_board_when_a_register_changes(self) -> None:
        board = self.work / "agents/tasks-board.md"
        process = subprocess.Popen([sys.executable, str(TOOL), "board", "--write", "--watch"], env=self.env, cwd=self.work,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.wait_for(lambda: board.is_file() and "TST-001" in board.read_text(encoding="utf-8"))
            register = self.brain / "projects/clients/acme/missions/m/state/actions.md"
            register.write_text(register.read_text(encoding="utf-8").replace("- [ ] **TST-003** — John", "- [/] **TST-003** — John"), encoding="utf-8")
            self.wait_for(lambda: "TST-003" in self.group(board.read_text(encoding="utf-8"), "acme / m", "En cours"))
        finally:
            process.terminate()
            process.wait(timeout=5)

    def wait_for(self, condition, timeout: float = 10.0) -> None:
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.2)
        self.fail("condition non atteinte dans le délai")

    def test_watch_needs_write(self) -> None:
        result = subprocess.run([sys.executable, str(TOOL), "board", "--watch"], env=self.env, cwd=self.work, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--watch demande --write", result.stderr)

    def test_owner_is_required(self) -> None:
        (self.brain / ".data/doctor.json").unlink()
        result = subprocess.run([sys.executable, str(TOOL), "board"], env=self.env, cwd=self.work, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("propriétaire inconnu", result.stderr)


if __name__ == "__main__":
    unittest.main()
