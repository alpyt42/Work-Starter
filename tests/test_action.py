"""Regression checks for the closed-action archiver (no network, no real brain)."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


TOOL = Path(__file__).resolve().parents[1] / "tools/brain/action.py"
HEADER = (
    "# Actions archive 2026 — Alpha\n\n"
    "> Closed actions of Alpha archived for 2026; the live register is [actions.md](actions.md). IDs stay reserved.\n\n"
    "## Done\n"
)

ALPHA = """# Actions — Alpha

> Registre de test.

## Open
- [ ] **AAA-001** — Jane — Encore ouverte
    - due: 2026-12-01
- [x] **AAA-002** — Jane — Cochée hier, rangée plus tard ✅ 2026-10-11

## Done
- [x] **AAA-010** — Jane — Récente ✅ 2026-10-05
    - source: [x](../sources/x.md)
- [x] **AAA-011** — Jane — Ancienne avec détails ✅ 2026-08-15
    - source: [x](../sources/x.md)
    - 15/08: fait
        - enfant à huit espaces

    - 16/08: après une ligne blanche interne
- [x] **AAA-012** — Jane — Sans date de clôture
    - 10/08: fait sans ✅
- [x] **AAA-013** — Jane — Plus ancienne encore ✅ 2026-07-01

## Cancelled
- [-] **AAA-020** — Jane — Abandonnée tôt ✅ 2026-06-01
    - 01/06: stop
- [-] **AAA-021** — Jane — Abandonnée récemment ❌ 2026-10-01
"""

ALPHA_AFTER = """# Actions — Alpha

> Registre de test.

## Open
- [ ] **AAA-001** — Jane — Encore ouverte
    - due: 2026-12-01
- [x] **AAA-002** — Jane — Cochée hier, rangée plus tard ✅ 2026-10-11

## Done
- [x] **AAA-010** — Jane — Récente ✅ 2026-10-05
    - source: [x](../sources/x.md)
- [x] **AAA-012** — Jane — Sans date de clôture
    - 10/08: fait sans ✅

## Cancelled
- [-] **AAA-021** — Jane — Abandonnée récemment ❌ 2026-10-01
"""

BETA = """# Actions — Beta

## Open

## Done
- [x] **BBB-001** — Jane — Clôturée l'an dernier ✅ 2025-12-20
- [x] **BBB-002** — Jane — Clôturée cette année ✅ 2026-02-03
    - note

## Cancelled
"""


class ArchiveActionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        self.brain = self.work / "brain"
        self.alpha = self.brain / "projects/clients/acme/missions/alpha/state"
        self.beta = self.brain / "projects/internal/beta/state"
        for folder, content in ((self.alpha, ALPHA), (self.beta, BETA)):
            folder.mkdir(parents=True)
            (folder / "actions.md").write_text(content, encoding="utf-8")
        self.env = {**os.environ, "WORK_DIR": str(self.work)}
        self.env.pop("BRAIN_DIR", None)
        self.env.pop("ARCHIVE_TODAY", None)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_tool(self, *args: str, code: int = 0, env: dict | None = None) -> subprocess.CompletedProcess:
        result = subprocess.run(
            [sys.executable, str(TOOL), "--brain", str(self.brain), "archive", "--today", "2026-10-12", *args],
            env=env or self.env, cwd=self.work, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def read(self, folder: Path, name: str = "actions.md") -> str:
        return (folder / name).read_text(encoding="utf-8")

    def test_check_fails_when_something_would_move_and_writes_nothing(self) -> None:
        result = self.run_tool("--check", code=1)
        self.assertIn("Misfiled actions", result.stdout)
        self.assertEqual(self.read(self.alpha), ALPHA)

    def test_check_with_register_filter_and_clean_register(self) -> None:
        clean = self.beta / "actions.md"
        self.run_tool("--check", "--register", str(clean), "--days", "100000")
        self.run_tool("--check", "--register", str(self.alpha / "actions.md"), code=1)

    def test_dry_run_reports_without_writing(self) -> None:
        out = self.run_tool().stdout
        self.assertIn("brain/projects/clients/acme/missions/alpha/state/actions.md: archive 3 action(s) → actions-archive-2026.md (AAA-011, AAA-013, AAA-020)", out)
        self.assertIn("brain/projects/internal/beta/state/actions.md: archive 2 action(s) → actions-archive-2025.md (BBB-001) ; actions-archive-2026.md (BBB-002)", out)
        self.assertIn("Total archive: 5 action(s) to move in 2 register(s)", out)
        self.assertEqual(self.read(self.alpha), ALPHA)
        self.assertEqual(self.read(self.beta), BETA)
        self.assertEqual(sorted(p.name for p in self.alpha.iterdir()), ["actions.md"])

    def test_quiet_prints_only_total(self) -> None:
        out = self.run_tool("--quiet").stdout.strip().splitlines()
        self.assertEqual(len(out), 2)  # total + dry-run hint
        self.assertTrue(out[0].startswith("Total archive: 5 action(s)"))

    def test_write_moves_only_old_dated_closed_actions_with_children(self) -> None:
        out = self.run_tool("--write").stdout
        self.assertIn("3 action(s) moved →", out)
        self.assertEqual(self.read(self.alpha), ALPHA_AFTER)
        archive = self.read(self.alpha, "actions-archive-2026.md")
        self.assertEqual(
            archive,
            HEADER
            + "- [x] **AAA-011** — Jane — Ancienne avec détails ✅ 2026-08-15\n"
            "    - source: [x](../sources/x.md)\n"
            "    - 15/08: fait\n"
            "        - enfant à huit espaces\n\n"
            "    - 16/08: après une ligne blanche interne\n"
            "- [x] **AAA-013** — Jane — Plus ancienne encore ✅ 2026-07-01\n\n"
            "## Cancelled\n"
            "- [-] **AAA-020** — Jane — Abandonnée tôt ✅ 2026-06-01\n"
            "    - 01/06: stop\n",
        )

    def test_year_split_creates_one_archive_per_closure_year(self) -> None:
        self.run_tool("--write")
        self.assertEqual(sorted(p.name for p in self.beta.iterdir()), ["actions-archive-2025.md", "actions-archive-2026.md", "actions.md"])
        self.assertIn("- [x] **BBB-001**", self.read(self.beta, "actions-archive-2025.md"))
        self.assertNotIn("BBB-002", self.read(self.beta, "actions-archive-2025.md"))
        self.assertIn("    - note\n", self.read(self.beta, "actions-archive-2026.md"))
        self.assertIn("# Actions archive 2025 — Beta", self.read(self.beta, "actions-archive-2025.md"))
        self.assertEqual(self.read(self.beta), "# Actions — Beta\n\n## Open\n\n## Done\n\n## Cancelled\n")

    def test_appends_to_existing_archive_sorted_newest_first(self) -> None:
        existing = (
            HEADER
            + "- [x] **AAA-090** — Jane — Très récente ✅ 2026-09-01\n"
            "- [x] **AAA-091** — Jane — Même jour que la nouvelle ✅ 2026-08-15\n"
            "    - ancien\n"
            "- [x] **AAA-092** — Jane — Plus vieille ✅ 2026-03-01\n\n"
            "## Cancelled\n"
            "- [-] **AAA-093** — Jane — Annulée avant ❌ 2026-01-10\n"
        )
        (self.alpha / "actions-archive-2026.md").write_text(existing, encoding="utf-8")
        self.run_tool("--write")
        archive = self.read(self.alpha, "actions-archive-2026.md")
        order = [line.split("**")[1] for line in archive.splitlines() if line.startswith("- [")]
        self.assertEqual(order, ["AAA-090", "AAA-091", "AAA-011", "AAA-013", "AAA-092", "AAA-020", "AAA-093"])
        self.assertEqual(archive.count("## Done"), 1)
        self.assertIn("\n\n## Cancelled\n", archive)
        self.assertNotIn("\n\n\n", archive)

    def test_closed_action_outside_closed_sections_warns_and_stays(self) -> None:
        text = ALPHA.replace("- [ ] **AAA-001** — Jane — Encore ouverte", "- [x] **AAA-001** — Jane — Mal rangée ✅ 2026-05-01")
        (self.alpha / "actions.md").write_text(text, encoding="utf-8")
        out = self.run_tool("--write").stdout
        self.assertIn("WARNING", out)
        self.assertIn("AAA-001", out.split("WARNING", 1)[1])
        self.assertIn("- [x] **AAA-001** — Jane — Mal rangée", self.read(self.alpha))
        self.assertNotIn("AAA-001", self.read(self.alpha, "actions-archive-2026.md"))

    def test_duplicate_id_in_archive_is_an_error_and_changes_nothing(self) -> None:
        archive = HEADER + "- [x] **AAA-013** — Jane — Déjà là ✅ 2026-07-01\n\n## Cancelled\n"
        (self.alpha / "actions-archive-2026.md").write_text(archive, encoding="utf-8")
        result = self.run_tool("--write", code=1)
        self.assertIn("AAA-013", result.stderr)
        self.assertEqual(self.read(self.alpha), ALPHA)
        self.assertEqual(self.read(self.alpha, "actions-archive-2026.md"), archive)
        # The other register is processed independently.
        self.assertEqual(self.read(self.beta), "# Actions — Beta\n\n## Open\n\n## Done\n\n## Cancelled\n")

    def test_second_write_moves_nothing(self) -> None:
        self.run_tool("--write")
        snapshot = {p: p.read_bytes() for p in self.brain.rglob("*.md")}
        out = self.run_tool("--write").stdout
        self.assertIn("Total archive: 0 action(s) moved", out)
        self.assertEqual(snapshot, {p: p.read_bytes() for p in self.brain.rglob("*.md")})

    def test_crlf_register_is_preserved(self) -> None:
        crlf = ALPHA.replace("\n", "\r\n").encode("utf-8")
        (self.alpha / "actions.md").write_bytes(crlf)
        self.run_tool("--write")
        self.assertEqual((self.alpha / "actions.md").read_bytes(), ALPHA_AFTER.replace("\n", "\r\n").encode("utf-8"))
        archive = (self.alpha / "actions-archive-2026.md").read_bytes()
        self.assertEqual(archive.count(b"\r\n"), archive.count(b"\n"))

    def test_register_without_trailing_newline_keeps_none(self) -> None:
        (self.alpha / "actions.md").write_text(ALPHA_AFTER.rstrip("\n") + "\n- [x] **AAA-030** — Jane — Dernière ✅ 2026-01-01", encoding="utf-8")
        self.run_tool("--write")
        text = self.read(self.alpha)
        self.assertFalse(text.endswith("\n"))
        self.assertNotIn("AAA-030", text)
        self.assertTrue(text.rstrip().endswith("❌ 2026-10-01"))

    def test_days_and_today_change_the_cutoff(self) -> None:
        # --days 90 from 2026-10-12: cutoff 2026-07-14, so AAA-011 (2026-08-15) stays.
        out = self.run_tool("--days", "90").stdout
        self.assertIn("Total archive: 4 action(s)", out)
        self.assertNotIn("AAA-011", out)
        # An earlier "today": cutoff 2026-07-21, AAA-011 still too recent.
        out = self.run_tool("--today", "2026-08-20").stdout
        self.assertIn("Total archive: 4 action(s)", out)
        self.assertNotIn("AAA-011", out)

    def test_cutoff_is_strict(self) -> None:
        # Closure 2026-08-15 with today 2026-09-14 and 30 days: exactly on the cutoff, kept.
        out = self.run_tool("--today", "2026-09-14").stdout
        self.assertNotIn("AAA-011", out)
        out = self.run_tool("--today", "2026-09-15").stdout
        self.assertIn("AAA-011", out)

    def test_env_override_for_today(self) -> None:
        env = {**self.env, "ARCHIVE_TODAY": "2026-09-14"}
        result = subprocess.run([sys.executable, str(TOOL), "--brain", str(self.brain), "archive", "--quiet"], env=env, cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Total archive: 4 action(s)", result.stdout)  # cutoff 2026-08-15: AAA-011 (same day) stays

    def test_symlinked_register_is_ignored(self) -> None:
        outside = Path(self._tmp.name).resolve() / "outside"
        (outside / "state").mkdir(parents=True)
        (outside / "state/actions.md").write_text(BETA, encoding="utf-8")
        link = self.brain / "projects/internal/linked"
        link.symlink_to(outside, target_is_directory=True)
        out = self.run_tool("--write").stdout
        self.assertNotIn("linked", out)
        self.assertEqual((outside / "state/actions.md").read_text(encoding="utf-8"), BETA)

    def test_failed_register_write_restores_archives(self) -> None:
        archive = HEADER + "- [x] **AAA-090** — Jane — Déjà archivée ✅ 2026-09-01\n\n## Cancelled\n"
        (self.alpha / "actions-archive-2026.md").write_text(archive, encoding="utf-8")
        spec = importlib.util.spec_from_file_location("archive_actions", TOOL)
        module = importlib.util.module_from_spec(spec)
        sys.modules["archive_actions"] = module
        self.addCleanup(sys.modules.pop, "archive_actions", None)
        spec.loader.exec_module(module)
        plan = module.plan_register(self.alpha / "actions.md", date(2026, 10, 12), 30)
        real = module.atomic_write_text

        def flaky(path: Path, text: str) -> None:
            if path.name == "actions.md":
                raise OSError("disque plein")
            real(path, text)

        with patch.object(module, "atomic_write_text", flaky), self.assertRaises(OSError):
            module.apply_plan(plan)
        self.assertEqual(self.read(self.alpha, "actions-archive-2026.md"), archive)
        self.assertEqual(self.read(self.alpha), ALPHA)
        self.assertEqual(sorted(p.name for p in self.alpha.iterdir()), ["actions-archive-2026.md", "actions.md"])


if __name__ == "__main__":
    unittest.main()


REGISTER = """# Actions — Gamma

## Open
- [ ] **GAM-001** — Jane — Existante 📅 2026-10-20
    - source: s

## Done

## Cancelled
"""


class ActionCommandTest(unittest.TestCase):
    """create / update / history / delete / list / show, as the agents and tasks-web run them."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name) / "brain"
        self.folder = self.brain / "projects/clients/acme/missions/gamma"
        (self.folder / "state").mkdir(parents=True)
        (self.folder / "sources").mkdir()
        (self.folder / "sources/cr.md").write_text("Ancienne mention GAM-007\n", encoding="utf-8")
        self.register = self.folder / "state/actions.md"
        self.register.write_text(REGISTER, encoding="utf-8")
        self.env = {**os.environ, "ACTION_NOW": "2026-10-13 14:32"}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def act(self, *args: str, code: int = 0, now: str | None = None) -> dict | list:
        env = {**self.env, **({"ACTION_NOW": now} if now else {})}
        result = subprocess.run([sys.executable, str(TOOL), "--brain", str(self.brain), *args], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except ValueError:
            return result.stdout

    def text(self) -> str:
        return self.register.read_text(encoding="utf-8")

    def create(self, **extra: str) -> dict:
        args = ["create", "--project", "acme/gamma", "--title", "Préparer la démo", "--owner", "Owner", "--source", "[CR](../sources/cr.md)"]
        for key, value in extra.items():
            args += [f"--{key.replace('_', '-')}={value}"]
        return self.act(*args)

    def test_create_allocates_next_id_of_client_folder_and_writes_stamps(self) -> None:
        result = self.create(priority="high", due="2026-10-14", due_note="avant l'atelier")
        self.assertEqual((result["id"], result["created_at"], result["label"]), ("GAM-008", "2026-10-13 14:32", "creation of GAM-008"))
        self.assertIn(
            "    - source: s\n"
            "- [ ] **GAM-008** — Owner — Préparer la démo ⏫ ➕ 2026-10-13 📅 2026-10-14\n"
            "    - due: avant l'atelier\n"
            "    - source: [CR](../sources/cr.md)\n"
            "    - created: 2026-10-13 14:32\n"
            "    - updated: 2026-10-13 14:32\n\n## Done", self.text())
        shown = self.act("show", "GAM-008")
        self.assertEqual((shown["created_at"], shown["updated_at"], shown["due"]), ("2026-10-13 14:32", "2026-10-13 14:32", "2026-10-14"))
        self.assertEqual([note["deletable"] for note in shown["notes"]], [True, False, False, False])

    def test_project_can_be_named_several_ways(self) -> None:
        for project in ("projects/clients/acme/missions/gamma/state/actions.md", "acme / gamma", "clients/acme/missions/gamma"):
            self.act("create", "--project", project, "--title", "T", "--owner", "A", "--source", "s", "--dry-run")
        self.assertEqual(self.text(), REGISTER)
        self.assertEqual(self.act("create", "--project", "inconnu", "--title", "T", "--owner", "A", "--source", "s", code=2)["kind"], "bad_request")

    def test_validation_messages_are_english_and_the_owner_refuses_the_register_separator(self) -> None:
        base = ["create", "--project", "acme/gamma", "--title", "T", "--source", "s"]
        result = self.act(*base, "--owner", "A — B", code=2)
        self.assertEqual(result["error"], "Owner contains a separator reserved for registers.")
        result = self.act(*base, "--owner", "A", "--due", "demain", code=2)
        self.assertEqual(result["error"], "Due date must use the format YYYY-MM-DD.")
        result = self.act(*base, "--owner", "A", "--scheduled", "2026-02-30", code=2)
        self.assertEqual(result["error"], "Scheduled date is not a valid date.")
        self.assertEqual(self.act("create", "--project", "acme/gamma", "--title", "T — U", "--owner", "A", "--source", "s", "--dry-run")["id"], "GAM-008")
        self.assertEqual(self.act("update", "GAM-999", "--title", "T", code=3)["error"], "Action not found or duplicate ID.")
        self.assertEqual(self.text(), REGISTER)

    def test_update_closes_moves_stamps_and_reopen_drops_closure(self) -> None:
        self.create()
        result = self.act("update", "GAM-008", "--state", "done", now="2026-10-14 09:05")
        self.assertEqual(result["label"], "status of GAM-008 → Done")
        text = self.text()
        self.assertIn("## Done\n- [x] **GAM-008** — Owner — Préparer la démo ➕ 2026-10-13 ✅ 2026-10-14\n", text)
        self.assertIn("    - created: 2026-10-13 14:32\n    - updated: 2026-10-14 09:05\n", text)
        self.act("update", "GAM-008", "--state", "todo", now="2026-10-15 10:00")
        line = next(l for l in self.text().splitlines() if "**GAM-008**" in l)
        self.assertEqual(line, "- [ ] **GAM-008** — Owner — Préparer la démo ➕ 2026-10-13")
        self.assertLess(self.text().index("**GAM-008**"), self.text().index("## Done"))
        self.act("update", "GAM-001", "--state", "x", "--closed-on", "2026-10-10", "--due", "")
        self.assertIn("- [x] **GAM-001** — Jane — Existante ✅ 2026-10-10\n    - source: s\n    - updated: 2026-10-13 14:32", self.text())

    def test_history_add_remove_and_protected_lines(self) -> None:
        self.create()
        self.act("history", "add", "GAM-008", "--text", "slides envoyées", "--date", "2026-10-12", now="2026-10-13 16:00")
        shown = self.act("show", "GAM-008")
        self.assertEqual(shown["notes"][-1]["text"], "- 12/10: slides envoyées")
        self.assertEqual(shown["updated_at"], "2026-10-13 16:00")
        self.assertEqual(self.act("history", "remove", "GAM-008", "--index", "1", code=2)["kind"], "bad_request")
        self.assertEqual(self.act("history", "remove", "GAM-008", "--index", "3", "--expect-text", "autre", code=4)["kind"], "conflict")
        self.act("history", "remove", "GAM-008", "--index", "3", "--expect-text", "- 12/10: slides envoyées", now="2026-10-13 17:00")
        self.assertNotIn("slides envoyées", self.text())
        self.assertIn("    - updated: 2026-10-13 17:00", self.text())

    def test_versions_errors_dry_run_and_delete(self) -> None:
        version = self.act("show", "GAM-001")["version"]
        self.assertEqual(self.act("update", "GAM-001", "--title", "Autre", "--expect-version", "stale", code=4)["kind"], "conflict")
        self.assertEqual(self.act("update", "GAM-404", "--title", "x", code=3)["kind"], "not_found")
        self.assertEqual(self.act("update", "GAM-001", "--due", "2026-02-30", code=2)["kind"], "bad_request")
        self.assertEqual(self.act("update", "GAM-001", "--title", "a 📅 b", code=2)["kind"], "bad_request")
        self.act("update", "GAM-001", "--title", "Autre", "--expect-version", version, "--dry-run")
        self.assertEqual(self.text(), REGISTER)
        self.act("delete", "GAM-001")
        self.assertEqual(self.text(), "# Actions — Gamma\n\n## Open\n\n## Done\n\n## Cancelled\n")

    def test_list_filters_and_table(self) -> None:
        self.create(state="in-progress")
        self.act("update", "GAM-001", "--state", "-")
        self.assertEqual([a["id"] for a in self.act("list", "--project", "acme/gamma")], ["GAM-008"])
        self.assertEqual([a["id"] for a in self.act("list", "--state", "closed")], ["GAM-001"])
        self.assertIn("[/] GAM-008 — Owner — Préparer la démo", self.act("list", "--table"))


class ActionMoreCommandsTest(unittest.TestCase):
    """history edit, move between registers of a client, check (same fixture as ActionCommandTest)."""

    setUp = ActionCommandTest.setUp
    tearDown = ActionCommandTest.tearDown
    act = ActionCommandTest.act
    text = ActionCommandTest.text
    create = ActionCommandTest.create

    def test_history_edit_keeps_date_and_children_and_protects_metadata(self) -> None:
        self.create()
        self.act("history", "add", "GAM-008", "--text", "brouillon", "--date", "2026-10-12")
        index = len(self.act("show", "GAM-008")["notes"]) - 1
        self.act("history", "edit", "GAM-008", "--index", str(index), "--text", "version finale", now="2026-10-13 18:10")
        shown = self.act("show", "GAM-008")
        self.assertEqual(shown["notes"][index]["text"], "- 12/10: version finale")
        self.assertEqual(shown["updated_at"], "2026-10-13 18:10")
        self.act("history", "edit", "GAM-008", "--index", str(index), "--text", "redatée", "--date", "2026-10-11")
        self.assertEqual(self.act("show", "GAM-008")["notes"][index]["text"], "- 11/10: redatée")
        self.assertEqual(self.act("history", "edit", "GAM-008", "--index", "0", "--text", "x", code=2)["kind"], "bad_request")

    def test_move_within_client_rewrites_links_and_refuses_other_client(self) -> None:
        other = self.brain / "projects/clients/acme/missions/delta/state"
        other.mkdir(parents=True)
        (other / "actions.md").write_text("# Actions — Delta\n\n## Open\n\n## Done\n\n## Cancelled\n", encoding="utf-8")
        self.create()
        result = self.act("move", "GAM-008", "--to", "acme/delta", now="2026-10-14 08:00")
        self.assertEqual((result["from"], result["register"]), ("projects/clients/acme/missions/gamma/state/actions.md",
                                                             "projects/clients/acme/missions/delta/state/actions.md"))
        moved = (other / "actions.md").read_text(encoding="utf-8")
        self.assertIn("- [ ] **GAM-008** — Owner — Préparer la démo ➕ 2026-10-13\n    - source: [CR](../../gamma/sources/cr.md)", moved)
        self.assertIn("    - updated: 2026-10-14 08:00", moved)
        self.assertIn("    - 14/10: moved from acme / gamma", moved)
        self.assertNotIn("GAM-008", self.text())
        foreign = self.brain / "projects/clients/beta/missions/one/state"
        foreign.mkdir(parents=True)
        (foreign / "actions.md").write_text("# Actions\n\n## Open\n", encoding="utf-8")
        self.assertEqual(self.act("move", "GAM-001", "--to", "beta/one", code=2)["kind"], "bad_request")

    def test_check_reports_errors_and_warnings(self) -> None:
        self.assertIn("0 error(s), 0 warning(s)", self.act("check"))
        self.register.write_text(REGISTER.replace("## Done\n", "## Done\n- [x] **GAM-001** — Jane — Doublon ✅ 2026-10-01\n"
                                                  "- [x] **GAM-002** — Jane — Sans date\n- [ ] **GAM-003** — Jane — Ouverte ✅ 2026-10-01\n"
                                                  "- [ ] **GAM-004** — Jane — Date 📅 2026-02-30\n- [?] **GAM-005** — Jane — État inconnu\n"), encoding="utf-8")
        out = self.act("check", code=1)
        for expected in ("GAM-001 already present", "GAM-003 open but carries a closing date", "GAM-004 invalid 📅 date",
                         "malformed action line", "GAM-002 closed without a ✅/❌ date", "GAM-002 without a source sub-bullet"):
            self.assertIn(expected, out)


class ActionGroupTest(unittest.TestCase):
    """The optional `#group/<slug>` group tag: parse, rewrite, --group, check (same fixture as ActionCommandTest)."""

    setUp = ActionCommandTest.setUp
    tearDown = ActionCommandTest.tearDown
    act = ActionCommandTest.act
    text = ActionCommandTest.text
    create = ActionCommandTest.create

    def line(self, action_id: str) -> str:
        return next(line for line in self.text().splitlines() if f"**{action_id}**" in line)

    def test_parse_splits_the_trailing_tag_from_the_title(self) -> None:
        self.register.write_text(REGISTER.replace(
            "Existante 📅 2026-10-20", "Atelier [CR](x.md) #group/atelier-ingestion ⏫ ➕ 2026-10-12 📅 2026-10-20 ⏳ 2026-10-18"), encoding="utf-8")
        shown = self.act("show", "GAM-001")
        self.assertEqual((shown["group"], shown["title"], shown["raw_title"], shown["priority"], shown["due"]),
                         ("atelier-ingestion", "Atelier CR", "Atelier [CR](x.md)", "⏫", "2026-10-20"))

    def test_no_group_by_default_and_stray_tags_stay_in_the_title(self) -> None:
        self.assertEqual(self.act("show", "GAM-001")["group"], "")
        for title, group in (("Ouvre #group/a puis ferme", ""), ("Fin #group/Mauvais_Slug", ""), ("Deux #group/a #group/b", "b"),
                             ("Trop long #group/" + "a" * 41, "")):
            self.register.write_text(REGISTER.replace("Existante", title), encoding="utf-8")
            shown = self.act("show", "GAM-001")
            self.assertEqual(shown["group"], group, title)
            self.assertEqual(shown["raw_title"], title if not group else "Deux #group/a", title)

    def test_create_writes_the_tag_before_the_emojis_and_list_shows_it(self) -> None:
        result = self.create(group="atelier-ingestion", priority="high", due="2026-10-20")
        self.assertEqual(result["line"], "- [ ] **GAM-008** — Owner — Préparer la démo #group/atelier-ingestion ⏫ ➕ 2026-10-13 📅 2026-10-20")
        self.assertIn(result["line"] + "\n", self.text())
        self.assertEqual(self.act("list", "--project", "acme/gamma")[1]["group"], "atelier-ingestion")
        self.assertIn("[group: atelier-ingestion]", self.act("list", "--table"))
        self.assertNotIn("#group/", self.line("GAM-001"))

    def test_update_sets_changes_removes_and_keeps_the_group(self) -> None:
        self.act("update", "GAM-001", "--group", "lot-un")
        self.assertEqual(self.line("GAM-001"), "- [ ] **GAM-001** — Jane — Existante #group/lot-un 📅 2026-10-20")
        self.act("update", "GAM-001", "--owner", "Marie", "--due", "2026-10-22")
        self.assertEqual(self.line("GAM-001"), "- [ ] **GAM-001** — Marie — Existante #group/lot-un 📅 2026-10-22")
        self.act("update", "GAM-001", "--title", "Renommée", "--state", "x", "--closed-on", "2026-10-14")
        self.assertEqual(self.line("GAM-001"), "- [x] **GAM-001** — Marie — Renommée #group/lot-un 📅 2026-10-22 ✅ 2026-10-14")
        self.assertEqual(self.act("show", "GAM-001")["group"], "lot-un")
        self.act("update", "GAM-001", "--group", "lot-deux")
        self.assertIn("Renommée #group/lot-deux 📅", self.line("GAM-001"))
        result = self.act("update", "GAM-001", "--group", "")
        self.assertEqual(result["label"], "edit of GAM-001")
        self.assertEqual(self.line("GAM-001"), "- [x] **GAM-001** — Marie — Renommée 📅 2026-10-22 ✅ 2026-10-14")

    def test_update_without_group_leaves_an_ungrouped_line_byte_for_byte(self) -> None:
        before = self.line("GAM-001")
        self.act("update", "GAM-001", "--owner", "Jane")  # same value: only the stamp changes
        self.assertEqual(self.line("GAM-001"), before)
        self.assertEqual(self.text(), REGISTER.replace("    - source: s\n", "    - source: s\n    - updated: 2026-10-13 14:32\n", 1))
        self.create(priority="low", due="2026-10-14")
        created = self.line("GAM-008")
        self.act("update", "GAM-008", "--state", "in-progress")
        self.assertEqual(self.line("GAM-008"), created.replace("[ ]", "[/]"))
        self.act("update", "GAM-008", "--state", "todo")
        self.assertEqual(self.line("GAM-008"), created)

    def test_invalid_slug_and_title_ending_with_a_tag_are_refused(self) -> None:
        for bad in ("Atelier Ingestion", "atelier_ingestion", "-a", "a-", "a--b", "é", "a" * 41, "#group/a"):
            self.assertEqual(self.act("update", "GAM-001", f"--group={bad}", code=2)["kind"], "bad_request", bad)
            self.assertEqual(self.act("create", "--project", "acme/gamma", "--title", "T", "--owner", "A", "--source", "s",
                                      f"--group={bad}", code=2)["kind"], "bad_request", bad)
        self.act("update", "GAM-001", "--group", "a" * 40)  # the limit itself is fine
        self.assertEqual(self.act("update", "GAM-001", "--title", "Titre #group/autre", code=2)["kind"], "bad_request")
        self.assertEqual(self.act("create", "--project", "acme/gamma", "--title", "Titre #group/autre", "--owner", "A",
                                  "--source", "s", code=2)["kind"], "bad_request")
        self.assertEqual(self.act("update", "GAM-001", "--title", "Avec #group/x au milieu")["id"], "GAM-001")  # not a trailing tag
        self.assertEqual(self.act("show", "GAM-001")["group"], "a" * 40)

    def test_check_warns_about_several_invalid_or_misplaced_tags(self) -> None:
        self.assertIn("0 error(s), 0 warning(s)", self.act("check"))
        self.act("update", "GAM-001", "--group", "valide")
        self.assertIn("0 error(s), 0 warning(s)", self.act("check"))
        self.register.write_text(
            REGISTER.replace("## Open\n", "## Open\n- [ ] **GAM-002** — Jane — Deux #group/a #group/b\n    - source: s\n"
                             "- [ ] **GAM-003** — Jane — Mauvais #group/Mauvais_Slug\n    - source: s\n"
                             "- [ ] **GAM-004** — Jane — Au #group/milieu du titre\n    - source: s\n"), encoding="utf-8")
        out = self.act("check")  # warnings only: exit code 0
        self.assertIn("GAM-002 several #group/ tags", out)
        self.assertIn("GAM-003 invalid group slug #group/", out)
        self.assertIn("GAM-004 tag #group/milieu not at the end of the title", out)
        self.assertIn("0 error(s), 3 warning(s)", out)

    def test_sweep_archive_move_history_and_delete_keep_the_tag(self) -> None:
        other = self.brain / "projects/clients/acme/missions/delta/state"
        other.mkdir(parents=True)
        (other / "actions.md").write_text("# Actions — Delta\n\n## Open\n\n## Done\n\n## Cancelled\n", encoding="utf-8")
        self.act("update", "GAM-001", "--group", "lot-un")
        self.act("history", "add", "GAM-001", "--text", "une note")
        self.assertIn("Existante #group/lot-un 📅", self.line("GAM-001"))
        self.act("update", "GAM-001", "--state", "x", "--closed-on", "2026-01-05")
        self.assertIn("## Done\n- [x] **GAM-001** — Jane — Existante #group/lot-un 📅 2026-10-20 ✅ 2026-01-05", self.text())
        result = subprocess.run([sys.executable, str(TOOL), "--brain", str(self.brain), "archive", "--write", "--today", "2026-10-13"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        archive = (self.folder / "state/actions-archive-2026.md").read_text(encoding="utf-8")
        self.assertIn("Existante #group/lot-un 📅 2026-10-20 ✅ 2026-01-05", archive)
        self.create(group="lot-deux", prefix="GAM")  # the archive emptied the register: its prefix is given again
        self.act("move", "GAM-008", "--to", "acme/delta")
        self.assertIn("- [ ] **GAM-008** — Owner — Préparer la démo #group/lot-deux ➕", (other / "actions.md").read_text(encoding="utf-8"))
        self.assertEqual(self.act("show", "GAM-008")["group"], "lot-deux")
        self.act("delete", "GAM-008")
        self.assertNotIn("GAM-008", (other / "actions.md").read_text(encoding="utf-8"))


FRENCH_REGISTER = """# Actions — Gamma

## Ouvertes
- [x] **GAM-001** — Jane — Existante ✅ 2026-10-12
    - source: s

## Terminées

## Annulées
"""


class EarlierFrenchLabelsTest(unittest.TestCase):
    """The tools read only the English labels: a register still written with the French ones is converted by migrate-english.py."""

    tearDown, act = ActionCommandTest.tearDown, ActionCommandTest.act

    def setUp(self) -> None:
        ActionCommandTest.setUp(self)
        self.register.write_text(FRENCH_REGISTER, encoding="utf-8")

    def test_french_section_titles_are_not_understood(self) -> None:
        report = self.act("sweep")
        self.assertIn("GAM-001: filed under 'ouvertes', unknown section, left in place", report)
        self.assertEqual(self.register.read_text(encoding="utf-8"), FRENCH_REGISTER)


class DefaultBrainTest(unittest.TestCase):
    """Without --brain nor BRAIN_DIR, the tools act on the default brain of WORK_DIR (rule of tools/machine/work_config.py)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name).resolve() / "Work"
        self.make_brain("brain", "GAM")
        self.make_brain("brain-initech", "INI")
        self.env = {key: value for key, value in os.environ.items() if key not in ("BRAIN_DIR", "WORK_DIR")}
        self.env["WORK_DIR"] = str(self.work)

    def make_brain(self, name: str, prefix: str) -> None:
        brain = self.work / name
        (brain / ".data").mkdir(parents=True)
        (brain / "AGENTS.md").write_text("# test\n", encoding="utf-8")
        register = brain / "projects/clients/acme/missions/gamma/state/actions.md"
        register.parent.mkdir(parents=True)
        register.write_text(REGISTER.replace("GAM", prefix), encoding="utf-8")

    def listed(self, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), "list", "--project", "acme/gamma"], env={**self.env, **env},
                              capture_output=True, text=True)

    def ids(self, **env: str) -> list[str]:
        result = self.listed(**env)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return [item["id"] for item in json.loads(result.stdout)]

    def set_default(self, name: str) -> None:
        (self.work / "work-config.local.json").write_text(json.dumps({"version": 1, "defaultBrain": name}), encoding="utf-8")

    def test_brain_is_the_default_then_the_setting_then_the_only_brain(self) -> None:
        self.assertEqual(self.ids(), ["GAM-001"])
        self.set_default("brain-initech")
        self.assertEqual(self.ids(), ["INI-001"])
        (self.work / "work-config.local.json").unlink()
        (self.work / "brain").rename(self.work / "brain-old")
        result = self.listed()  # no `brain/` left and two brains: no default, so today's "missing" behaviour on Work/brain
        self.assertEqual(result.returncode, 3)
        self.assertIn(str(self.work / "brain/projects"), result.stdout)
        shutil.rmtree(self.work / "brain-old")
        self.assertEqual(self.ids(), ["INI-001"])  # the only brain

    def test_brain_dir_and_the_brain_option_still_win(self) -> None:
        self.set_default("brain-initech")
        self.assertEqual(self.ids(BRAIN_DIR=str(self.work / "brain")), ["GAM-001"])
        result = subprocess.run([sys.executable, str(TOOL), "--brain", str(self.work / "brain"), "list", "--project", "acme/gamma"],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual([item["id"] for item in json.loads(result.stdout)], ["GAM-001"])

    def test_invalid_setting_is_reported_not_a_traceback(self) -> None:
        self.set_default("brain-nope")
        result = self.listed()
        self.assertEqual(result.returncode, 1)
        self.assertIn("defaultBrain brain-nope is not a brain", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.ids(BRAIN_DIR=str(self.work / "brain")), ["GAM-001"])  # BRAIN_DIR never reads the setting

    def test_the_work_relative_path_of_a_register_names_the_brain_folder(self) -> None:
        path = "brain-initech/projects/clients/acme/missions/gamma/state/actions.md"
        result = subprocess.run([sys.executable, str(TOOL), "--brain", str(self.work / "brain-initech"), "list", "--project", path],
                                env=self.env, capture_output=True, text=True)
        self.assertEqual([item["id"] for item in json.loads(result.stdout)], ["INI-001"], result.stderr)
