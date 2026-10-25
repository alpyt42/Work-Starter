"""Regression checks for the timeline tool: entries at their date and the monthly roll into journal/ (no network, temporary brain)."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/brain/timeline.py"

ROLLOUT = """# Mission: Rollout

- **Status:** active

## Context
Background in [context](workstreams/context.md).

## Timeline
Previous months: [2026-09](journal/2026-09.md)

- 2026-10-14 — Demo recorded, see [minutes](sources/2026-10/2026-10-14-cr-demo.md) (Sonnet 5)
- 2026-10-14 — Kickoff held (Opus 5.5)
- 2026-10-02 — Scope agreed with [Jane Doe](../../../../people/jane-doe.md) (Opus 5.5)

## Links
- [Sources](sources/2026-10/index.md)
"""

JOURNAL_SEPTEMBER = """# Journal — Rollout — 2026-09

[Back to project](../rollout.md)

> Journal archive of Rollout for September 2026: entries moved from the project page on 2026-10-01. The current month stays on the page.

- 2026-09-28 — Contract signed (Opus 5.5)
- 2026-09-10 — Workshop held, see [notes](../notes/2026-09-10-workshop.md) (Opus 5.5)
"""

SETUP = """# Project: Setup

## Context
Tooling.

## Timeline

- 2026-10-15 — Hooks installed (Opus 5.5)
- 2026-09-30 — Skills linked, see [guide](notes/2026-09-30-skills.md) (Opus 5.5)
"""

GLOBEX = """# Client: Globex

## Missions
- [Rollout](missions/rollout/rollout.md)

## Timeline
- 2026-10-03 — Account review, see [minutes](missions/rollout/sources/2026-10/2026-10-03-cr-review.md) (Opus 5.5)
- 2026-09-12 — Contract renewed (Opus 5.5)

## Contacts
- [Jane Doe](../../people/jane-doe.md)
"""

ACTIONS = "# Actions — {name}\n\n## Open\n\n## Done\n\n## Cancelled\n"


class TimelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name) / "brain-acme"
        self.mission = self.brain / "projects/clients/globex/missions/rollout"
        self.setup_dir = self.brain / "projects/internal/setup"
        self.client = self.brain / "projects/clients/globex"
        for folder, page, text in ((self.mission, "rollout.md", ROLLOUT), (self.setup_dir, "setup.md", SETUP)):
            (folder / "state").mkdir(parents=True)
            (folder / "state/actions.md").write_text(ACTIONS.format(name=folder.name), encoding="utf-8")
            (folder / page).write_text(text, encoding="utf-8")
        (self.client / "globex.md").write_text(GLOBEX, encoding="utf-8")
        (self.mission / "journal").mkdir()
        (self.mission / "journal/2026-09.md").write_text(JOURNAL_SEPTEMBER, encoding="utf-8")
        self.page = self.mission / "rollout.md"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_tool(self, *args: str, code: int = 0, now: str = "2026-10-20 10:00") -> dict | str:
        env = {**os.environ, "ACTION_NOW": now}
        result = subprocess.run([sys.executable, str(TOOL), "--brain", str(self.brain), *args], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        try:
            return json.loads(result.stdout)
        except ValueError:
            return result.stderr

    def add(self, text: str, *extra: str, project: str = "globex/rollout", now: str = "2026-10-20 10:00", code: int = 0) -> dict | str:
        return self.run_tool("add", "--project", project, "--model", "Sonnet 5", *extra, text, now=now, code=code)

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    @staticmethod
    def outside_timeline(text: str) -> str:
        head, rest = text.split("## Timeline")
        return head + (rest[rest.find("\n## "):] if "\n## " in rest else "")

    def snapshot(self) -> dict[str, str]:
        return {p.relative_to(self.brain).as_posix(): p.read_text(encoding="utf-8") for p in sorted(self.brain.rglob("*.md"))}

    # --- add ---

    def test_add_today_goes_on_top_of_the_current_month(self) -> None:
        result = self.add("Wrote the plan")
        self.assertEqual(result["entry"], "- 2026-10-20 — Wrote the plan (Sonnet 5)")
        self.assertEqual((result["file"], result["journal"], result["rolled"]["moved"]), ("projects/clients/globex/missions/rollout/rollout.md", False, 0))
        expected = ROLLOUT.replace(
            "\n- 2026-10-14 — Demo", "\n- 2026-10-20 — Wrote the plan (Sonnet 5)\n- 2026-10-14 — Demo", 1)
        self.assertEqual(self.read(self.page), expected)

    def test_add_defaults_to_the_current_date(self) -> None:
        self.assertEqual(self.add("Late evening", now="2026-10-31 23:30")["date"], "2026-10-31")
        self.assertEqual(self.add("Just after midnight", now="2026-11-01 00:10")["date"], "2026-11-01")

    def test_add_on_a_date_goes_above_the_same_date_and_below_newer_entries(self) -> None:
        self.add("Same day as the demo", "--date", "2026-10-14")
        self.add("Between the kickoff and the scope", "--date", "2026-10-10")
        self.add("Newest", "--date", "2026-10-19")
        entries = [line for line in self.read(self.page).splitlines() if line.startswith("- 2026-")]
        self.assertEqual([line[2:12] for line in entries], ["2026-10-19", "2026-10-14", "2026-10-14", "2026-10-14", "2026-10-10", "2026-10-02"])
        self.assertIn("Same day as the demo", entries[1])
        self.assertIn("Demo recorded", entries[2])
        self.assertIn("Between the kickoff", entries[4])

    def test_add_in_a_past_month_goes_into_the_existing_journal(self) -> None:
        before = self.read(self.page)
        result = self.add("Late event, see [minutes](sources/2026-09/2026-09-20-cr-late.md)", "--date", "2026-09-20")
        self.assertEqual((result["journal"], result["created_file"]), (True, False))
        self.assertEqual(result["file"], "projects/clients/globex/missions/rollout/journal/2026-09.md")
        self.assertEqual(self.read(self.mission / "journal/2026-09.md"), JOURNAL_SEPTEMBER.replace(
            "- 2026-09-10 —",
            "- 2026-09-20 — Late event, see [minutes](../sources/2026-09/2026-09-20-cr-late.md) (Sonnet 5)\n- 2026-09-10 —"))
        self.assertEqual(self.read(self.page), before)  # the month was already listed

    def test_add_in_a_past_month_creates_the_journal_and_lists_it(self) -> None:
        result = self.add("Pre-sales call", "--date", "2026-08-30")
        self.assertTrue(result["created_file"])
        self.assertEqual(self.read(self.mission / "journal/2026-08.md"), (
            "# Journal — Rollout — 2026-08\n\n[Back to project](../rollout.md)\n\n"
            "> Journal archive of Rollout for August 2026: entries moved from the project page on 2026-10-20. The current month stays on the page.\n\n"
            "- 2026-08-30 — Pre-sales call (Sonnet 5)\n"))
        self.assertIn("\nPrevious months: [2026-09](journal/2026-09.md) · [2026-08](journal/2026-08.md)\n", self.read(self.page))

    def test_add_in_a_new_month_rolls_the_older_entries_first(self) -> None:
        result = self.add("Planned the sprint", now="2026-11-02 09:00")
        self.assertEqual(result["rolled"]["moved"], 3)
        self.assertEqual([(m["month"], m["count"], m["created"]) for m in result["rolled"]["months"]], [("2026-10", 3, True)])
        self.assertEqual(self.read(self.page), ROLLOUT.replace(
            "Previous months: [2026-09](journal/2026-09.md)\n\n"
            "- 2026-10-14 — Demo recorded, see [minutes](sources/2026-10/2026-10-14-cr-demo.md) (Sonnet 5)\n"
            "- 2026-10-14 — Kickoff held (Opus 5.5)\n"
            "- 2026-10-02 — Scope agreed with [Jane Doe](../../../../people/jane-doe.md) (Opus 5.5)\n",
            "Previous months: [2026-10](journal/2026-10.md) · [2026-09](journal/2026-09.md)\n\n"
            "- 2026-11-02 — Planned the sprint (Sonnet 5)\n"))
        self.assertEqual(self.read(self.mission / "journal/2026-10.md"), (
            "# Journal — Rollout — 2026-10\n\n[Back to project](../rollout.md)\n\n"
            "> Journal archive of Rollout for October 2026: entries moved from the project page on 2026-11-02. The current month stays on the page.\n\n"
            "- 2026-10-14 — Demo recorded, see [minutes](../sources/2026-10/2026-10-14-cr-demo.md) (Sonnet 5)\n"
            "- 2026-10-14 — Kickoff held (Opus 5.5)\n"
            "- 2026-10-02 — Scope agreed with [Jane Doe](../../../../../people/jane-doe.md) (Opus 5.5)\n"))

    def test_add_dry_run_writes_nothing(self) -> None:
        before = self.snapshot()
        result = self.add("Planned the sprint", "--dry-run", now="2026-11-02 09:00")
        self.assertEqual((result["dry_run"], result["rolled"]["moved"]), (True, 3))
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.mission / "journal/2026-10.md").exists())

    def test_add_a_future_month_stays_on_the_page(self) -> None:
        result = self.add("Planned go-live", "--date", "2026-11-15")
        self.assertEqual((result["journal"], result["rolled"]["moved"]), (False, 0))
        self.assertIn("## Timeline\nPrevious months: [2026-09](journal/2026-09.md)\n\n- 2026-11-15 — Planned go-live (Sonnet 5)\n- 2026-10-14", self.read(self.page))

    def test_add_validates_its_input(self) -> None:
        for args in (("--date", "2026-13-40"), ("--date", "20/10/2026")):
            self.assertEqual(self.add("Text", *args, code=2)["kind"], "bad_request")
        self.assertEqual(self.add("   ", code=2)["kind"], "bad_request")
        self.assertEqual(self.add("two\nlines", code=2)["kind"], "bad_request")
        self.assertEqual(self.add("x" * 2001, code=2)["kind"], "bad_request")
        self.assertIn("--model", self.run_tool("add", "--project", "globex/rollout", "text", code=2))
        self.assertEqual(self.read(self.page), ROLLOUT)

    def test_add_on_a_project_without_timeline_creates_the_section(self) -> None:
        (self.setup_dir / "setup.md").write_text("# Project: Setup\n\n## Context\nTooling.\n", encoding="utf-8")
        self.add("First entry", project="setup")
        self.assertEqual(self.read(self.setup_dir / "setup.md"), "# Project: Setup\n\n## Context\nTooling.\n\n## Timeline\n\n- 2026-10-20 — First entry (Sonnet 5)\n")

    def test_add_replaces_the_seed_placeholder(self) -> None:
        (self.setup_dir / "setup.md").write_text("# Project: Setup\n\n## Timeline\n\n- (no entries yet)\n", encoding="utf-8")
        self.add("First entry", project="setup")
        self.assertEqual(self.read(self.setup_dir / "setup.md"), "# Project: Setup\n\n## Timeline\n\n- 2026-10-20 — First entry (Sonnet 5)\n")

    def test_add_in_an_empty_timeline_followed_by_a_section(self) -> None:
        (self.setup_dir / "setup.md").write_text("# Project: Setup\n\n## Timeline\n\n## Links\n- x\n", encoding="utf-8")
        self.add("First entry", project="setup")
        self.assertEqual(self.read(self.setup_dir / "setup.md"), "# Project: Setup\n\n## Timeline\n\n- 2026-10-20 — First entry (Sonnet 5)\n\n## Links\n- x\n")

    # --- roll ---

    def test_roll_is_a_dry_run_unless_written(self) -> None:
        before = self.snapshot()
        report = self.run_tool("roll", now="2026-11-02 09:00")
        self.assertEqual((report["dry_run"], report["total"], report["checked"]), (True, 7, 3))
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.run_tool("roll", "--dry-run", now="2026-11-02 09:00")["total"], report["total"])
        written = self.run_tool("roll", "--write", now="2026-11-02 09:00")
        self.assertEqual((written["dry_run"], written["total"]), (False, report["total"]))
        self.assertNotEqual(self.snapshot(), before)
        self.assertTrue((self.mission / "journal/2026-10.md").is_file())

    def test_roll_twice_changes_nothing(self) -> None:
        self.run_tool("roll", "--write", now="2026-11-02 09:00")
        after = self.snapshot()
        again = self.run_tool("roll", "--write", now="2026-11-02 09:00")
        self.assertEqual((again["total"], again["projects"]), (0, []))
        self.assertEqual(self.snapshot(), after)

    def test_roll_only_moves_the_months_before_the_current_one(self) -> None:
        report = self.run_tool("roll", "--write")  # 2026-10-20: the September entries of the setup and client pages
        self.assertEqual(sorted((p["project"], p["moved"]) for p in report["projects"]), [("clients/globex", 1), ("setup", 1)])
        self.assertEqual(self.read(self.page), ROLLOUT)

    def test_roll_one_project_only(self) -> None:
        report = self.run_tool("roll", "--project", "setup", "--write", now="2026-11-02 09:00")
        self.assertEqual([(p["project"], p["moved"]) for p in report["projects"]], [("setup", 2)])
        self.assertEqual(self.read(self.page), ROLLOUT)
        self.assertEqual(self.read(self.setup_dir / "journal/2026-10.md"), (
            "# Journal — Setup — 2026-10\n\n[Back to project](../setup.md)\n\n"
            "> Journal archive of Setup for October 2026: entries moved from the project page on 2026-11-02. The current month stays on the page.\n\n"
            "- 2026-10-15 — Hooks installed (Opus 5.5)\n"))

    def test_roll_merges_into_an_existing_journal_without_duplicates(self) -> None:
        late = ("- 2026-09-20 — Late event, see [minutes](sources/2026-09/2026-09-20-cr-late.md) (Opus 5.5)\n"
                "- 2026-09-10 — Workshop held, see [notes](notes/2026-09-10-workshop.md) (Opus 5.5)\n")
        self.page.write_text(ROLLOUT.replace("- 2026-10-14 — Demo", late + "- 2026-10-14 — Demo", 1), encoding="utf-8")
        report = self.run_tool("roll", "--project", "globex/rollout", "--write")
        self.assertEqual([(m["month"], m["count"], m["duplicates"], m["created"]) for m in report["projects"][0]["months"]], [("2026-09", 2, 1, False)])
        self.assertEqual(self.read(self.mission / "journal/2026-09.md"), JOURNAL_SEPTEMBER.replace(
            "- 2026-09-10 —",
            "- 2026-09-20 — Late event, see [minutes](../sources/2026-09/2026-09-20-cr-late.md) (Opus 5.5)\n- 2026-09-10 —"))
        self.assertEqual(self.read(self.page), ROLLOUT)

    def test_roll_keeps_the_order_of_moved_entries_of_the_same_day(self) -> None:
        self.run_tool("roll", "--project", "globex/rollout", "--write", now="2026-11-02 09:00")
        journal = [line for line in self.read(self.mission / "journal/2026-10.md").splitlines() if line.startswith("- ")]
        self.assertTrue(journal[0].startswith("- 2026-10-14 — Demo recorded"))
        self.assertTrue(journal[1].startswith("- 2026-10-14 — Kickoff"))

    def test_roll_corrects_relative_links_only(self) -> None:
        entry = ("- 2026-09-05 — Links: [a](sources/a.md) [b](./b.md) [c](../c.md) [url](https://example.com/x) [mail](mailto:jane@example.com) "
                 "[top](#timeline) [abs](/etc/x.md) [spaced](<notes/my note.md>) ![img](assets/p.png) [titled](notes/t.md \"A title\") `[code](kept.md)` (Opus 5.5)")
        (self.setup_dir / "setup.md").write_text(f"# Project: Setup\n\n## Timeline\n{entry}\n", encoding="utf-8")
        self.run_tool("roll", "--project", "setup", "--write")
        moved = [line for line in self.read(self.setup_dir / "journal/2026-09.md").splitlines() if line.startswith("- ")][0]
        self.assertEqual(moved, (
            "- 2026-09-05 — Links: [a](../sources/a.md) [b](../b.md) [c](../../c.md) [url](https://example.com/x) [mail](mailto:jane@example.com) "
            "[top](#timeline) [abs](/etc/x.md) [spaced](<../notes/my note.md>) ![img](../assets/p.png) [titled](../notes/t.md \"A title\") `[code](kept.md)` (Opus 5.5)"))

    def test_roll_moves_the_continuation_lines_with_their_entry(self) -> None:
        (self.setup_dir / "setup.md").write_text(
            "# Project: Setup\n\n## Timeline\n- 2026-10-15 — Current (m)\n- 2026-09-05 — Old (m)\n    - detail with [link](notes/x.md)\n- 2026-09-01 — Older (m)\n", encoding="utf-8")
        self.run_tool("roll", "--project", "setup", "--write")
        self.assertIn("- 2026-09-05 — Old (m)\n    - detail with [link](../notes/x.md)\n- 2026-09-01 — Older (m)\n", self.read(self.setup_dir / "journal/2026-09.md"))
        self.assertEqual(self.read(self.setup_dir / "setup.md"),
                         "# Project: Setup\n\n## Timeline\nPrevious months: [2026-09](journal/2026-09.md)\n\n- 2026-10-15 — Current (m)\n")

    def test_roll_creates_the_previous_months_line_under_the_heading(self) -> None:
        self.run_tool("roll", "--project", "setup", "--write")
        self.assertEqual(self.read(self.setup_dir / "setup.md"),
                         SETUP.replace("## Timeline\n\n- 2026-10-15 — Hooks installed (Opus 5.5)\n- 2026-09-30 — Skills linked, see [guide](notes/2026-09-30-skills.md) (Opus 5.5)\n",
                                       "## Timeline\nPrevious months: [2026-09](journal/2026-09.md)\n\n- 2026-10-15 — Hooks installed (Opus 5.5)\n"))
        self.assertIn("- 2026-09-30 — Skills linked, see [guide](../notes/2026-09-30-skills.md) (Opus 5.5)\n", self.read(self.setup_dir / "journal/2026-09.md"))

    def test_roll_updates_the_previous_months_line_most_recent_first(self) -> None:
        self.run_tool("roll", "--project", "globex/rollout", "--write", now="2026-11-02 09:00")
        self.assertIn("\nPrevious months: [2026-10](journal/2026-10.md) · [2026-09](journal/2026-09.md)\n", self.read(self.page))
        self.add("December", now="2026-12-03 09:00")
        # the page holds no entry of a past month: the line is already right and the new entry is the only one
        self.assertIn("\nPrevious months: [2026-10](journal/2026-10.md) · [2026-09](journal/2026-09.md)\n\n- 2026-12-03 — December (Sonnet 5)\n", self.read(self.page))

    def test_roll_replaces_the_template_placeholder_line(self) -> None:
        (self.setup_dir / "setup.md").write_text(
            "# Project: Setup\n\n## Timeline\n> Only the current month stays here.\nPrevious months: [YYYY-MM](journal/YYYY-MM.md)\n- 2026-10-15 — Current (m)\n- 2026-09-05 — Old (m)\n", encoding="utf-8")
        self.run_tool("roll", "--project", "setup", "--write")
        self.assertEqual(self.read(self.setup_dir / "setup.md"),
                         "# Project: Setup\n\n## Timeline\n> Only the current month stays here.\nPrevious months: [2026-09](journal/2026-09.md)\n- 2026-10-15 — Current (m)\n")

    def test_roll_relocates_a_previous_months_line_found_among_the_entries(self) -> None:
        (self.setup_dir / "setup.md").write_text(
            "# Project: Setup\n\n## Timeline\n\n- 2026-10-15 — A (m)\n- 2026-10-14 — B (m)\nPrevious months: [2026-08](journal/2026-08.md)\n\n- 2026-10-13 — C (m)\n- 2026-09-02 — Old (m)\n", encoding="utf-8")
        self.run_tool("roll", "--project", "setup", "--write")
        self.assertEqual(self.read(self.setup_dir / "setup.md"), (
            "# Project: Setup\n\n## Timeline\nPrevious months: [2026-09](journal/2026-09.md) · [2026-08](journal/2026-08.md)\n\n"
            "- 2026-10-15 — A (m)\n- 2026-10-14 — B (m)\n- 2026-10-13 — C (m)\n"))

    def test_roll_keeps_the_french_wording_and_creates_french_journals(self) -> None:
        (self.mission / "journal/2026-09.md").write_text(
            "# Journal — Rollout — 2026-09\n\n[Retour au projet](../rollout.md)\n\n"
            "> Archive du journal de Rollout pour septembre 2026 : entrées déplacées depuis la fiche le 2026-10-01. Les mois en cours restent dans la fiche.\n\n"
            "- 2026-09-28 — Contrat signé (Opus 5.5)\n", encoding="utf-8")
        self.page.write_text(ROLLOUT.replace("Previous months:", "Mois précédents :"), encoding="utf-8")
        self.run_tool("roll", "--project", "globex/rollout", "--write", now="2026-11-02 09:00")
        self.assertIn("\nMois précédents : [2026-10](journal/2026-10.md) · [2026-09](journal/2026-09.md)\n", self.read(self.page))
        journal = self.read(self.mission / "journal/2026-10.md")
        self.assertTrue(journal.startswith(
            "# Journal — Rollout — 2026-10\n\n[Retour au projet](../rollout.md)\n\n"
            "> Archive du journal de Rollout pour octobre 2026 : entrées déplacées depuis la fiche le 2026-11-02. Les mois en cours restent dans la fiche.\n\n- 2026-10-14"))

    def test_a_new_journal_follows_the_title_order_of_the_existing_ones(self) -> None:
        (self.mission / "journal/2026-09.md").write_text(
            "# Journal — 2026-09 — Rollout\n\n> Journal archive of Rollout for September 2026: entries moved from the project page on 2026-10-01. The current month stays on the page.\n\n- 2026-09-28 — Contract signed (Opus 5.5)\n", encoding="utf-8")
        self.run_tool("roll", "--project", "globex/rollout", "--write", now="2026-11-02 09:00")
        self.assertTrue(self.read(self.mission / "journal/2026-10.md").startswith("# Journal — 2026-10 — Rollout\n\n[Back to project](../rollout.md)\n"))

    def test_a_new_wording_follows_the_brain_when_the_project_has_none(self) -> None:
        (self.mission / "journal/2026-09.md").unlink()
        self.page.write_text(ROLLOUT.replace("Previous months: [2026-09](journal/2026-09.md)\n", ""), encoding="utf-8")
        (self.setup_dir / "setup.md").write_text(SETUP.replace("## Timeline\n", "## Timeline\nMois précédents : [2026-08](journal/2026-08.md)\n"), encoding="utf-8")
        self.run_tool("roll", "--project", "globex/rollout", "--write", now="2026-11-02 09:00")
        self.assertIn("\nMois précédents : [2026-10](journal/2026-10.md)\n", self.read(self.page))
        self.assertIn("[Retour au projet](../rollout.md)", self.read(self.mission / "journal/2026-10.md"))

    def test_only_the_timeline_section_and_the_journals_change(self) -> None:
        before = self.snapshot()
        self.add("Planned the sprint", now="2026-11-02 09:00")
        self.run_tool("roll", "--write", now="2026-11-02 09:00")
        after = self.snapshot()
        changed = {path for path in after if before.get(path) != after[path]}
        self.assertEqual(changed, {"projects/clients/globex/missions/rollout/rollout.md", "projects/clients/globex/missions/rollout/journal/2026-10.md",
                                   "projects/internal/setup/setup.md", "projects/internal/setup/journal/2026-09.md", "projects/internal/setup/journal/2026-10.md",
                                   "projects/clients/globex/globex.md", "projects/clients/globex/journal/2026-09.md", "projects/clients/globex/journal/2026-10.md"})
        for path in ("projects/clients/globex/missions/rollout/rollout.md", "projects/internal/setup/setup.md", "projects/clients/globex/globex.md"):
            self.assertEqual(self.outside_timeline(before[path]), self.outside_timeline(after[path]), path)

    def test_roll_leaves_archived_projects_alone(self) -> None:
        old = self.client / "archive/legacy"
        (old / "state").mkdir(parents=True)
        (old / "state/actions.md").write_text(ACTIONS.format(name="legacy"), encoding="utf-8")
        (old / "legacy.md").write_text("# Mission: Legacy\n\n## Timeline\n- 2026-03-01 — Old (m)\n", encoding="utf-8")
        report = self.run_tool("roll", "--write", now="2026-11-02 09:00")
        self.assertNotIn("legacy", json.dumps(report))
        self.assertFalse((old / "journal").exists())

    def test_crlf_files_keep_their_line_endings(self) -> None:
        self.page.write_bytes(ROLLOUT.replace("\n", "\r\n").encode("utf-8"))
        self.run_tool("roll", "--project", "globex/rollout", "--write", now="2026-11-02 09:00")
        self.assertNotIn(b"\n", self.page.read_bytes().replace(b"\r\n", b""))
        self.assertIn(b"Previous months: [2026-10](journal/2026-10.md) \xc2\xb7 [2026-09](journal/2026-09.md)\r\n", self.page.read_bytes())

    def test_a_missing_final_newline_is_kept(self) -> None:
        self.page.write_text(ROLLOUT.rstrip("\n"), encoding="utf-8")
        self.add("Planned the sprint")
        self.assertFalse(self.read(self.page).endswith("\n"))
        self.assertIn("- 2026-10-20 — Planned the sprint (Sonnet 5)\n- 2026-10-14", self.read(self.page))

    def test_a_timeline_heading_inside_a_code_block_is_not_the_section(self) -> None:
        text = "# Project: Setup\n\n```\n## Timeline\n- 2026-09-01 — in a code block\n```\n\n## Timeline\n- 2026-10-15 — Current (m)\n"
        (self.setup_dir / "setup.md").write_text(text, encoding="utf-8")
        self.assertEqual(self.run_tool("roll", "--project", "setup", "--write")["total"], 0)
        self.assertEqual(self.read(self.setup_dir / "setup.md"), text)

    # --- projects ---

    def test_unknown_project_and_missing_page(self) -> None:
        self.assertEqual(self.add("Text", project="globex/unknown", code=2)["kind"], "bad_request")
        self.assertEqual(self.add("Text", project="clients/unknown", code=2)["kind"], "bad_request")
        self.assertEqual(self.run_tool("roll", "--project", "nowhere", code=2)["kind"], "bad_request")
        (self.setup_dir / "setup.md").unlink()
        self.assertEqual(self.add("Text", project="setup", code=3)["kind"], "not_found")

    def test_project_forms(self) -> None:
        for project in ("globex/rollout", "clients/globex/missions/rollout", "globex / rollout",
                        "projects/clients/globex/missions/rollout/state/actions.md"):
            self.assertEqual(self.add("Same page", "--dry-run", project=project)["page"], "projects/clients/globex/missions/rollout/rollout.md", project)

    def test_client_index_page(self) -> None:
        report = self.run_tool("roll", "--project", "clients/globex", "--write")
        self.assertEqual([(p["project"], p["moved"]) for p in report["projects"]], [("clients/globex", 1)])
        self.assertEqual(self.read(self.client / "journal/2026-09.md"), (
            "# Journal — Globex — 2026-09\n\n[Back to project](../globex.md)\n\n"
            "> Journal archive of Globex for September 2026: entries moved from the project page on 2026-10-20. The current month stays on the page.\n\n"
            "- 2026-09-12 — Contract renewed (Opus 5.5)\n"))
        self.assertIn("## Timeline\nPrevious months: [2026-09](journal/2026-09.md)\n\n- 2026-10-03 —", self.read(self.client / "globex.md"))
        result = self.add("Account call", project="clients/globex")
        self.assertEqual(result["page"], "projects/clients/globex/globex.md")
        self.assertIn("## Timeline\nPrevious months: [2026-09](journal/2026-09.md)\n\n- 2026-10-20 — Account call (Sonnet 5)\n- 2026-10-03 —", self.read(self.client / "globex.md"))
        self.assertTrue(self.read(self.client / "globex.md").startswith(GLOBEX.split("## Timeline")[0]))

    def load_tool(self):
        spec = importlib.util.spec_from_file_location("timeline_under_test", TOOL)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses look their module up here
        spec.loader.exec_module(module)
        return module

    def test_a_file_changed_after_it_was_read_is_refused(self) -> None:
        module = self.load_tool()
        plan = module.Plan(self.brain.resolve(), self.page.resolve(), module.date(2026, 11, 2))
        self.assertIsNotNone(module.roll_page(plan, "globex / rollout"))
        self.page.write_text(ROLLOUT + "\n- 2026-10-30 — Added by someone else (Opus 5.5)\n", encoding="utf-8")
        with self.assertRaises(module.ActionError) as raised:
            module.commit(plan, dry_run=False)
        self.assertEqual(raised.exception.kind, "conflict")
        self.assertFalse((self.mission / "journal/2026-10.md").exists())
        self.assertIn("Added by someone else", self.read(self.page))

    def test_shift_links_unit(self) -> None:
        module = self.load_tool()
        self.assertEqual(module.shift_links("[a](x.md) and [b](https://e.com) and [c](#h)"), "[a](../x.md) and [b](https://e.com) and [c](#h)")
        self.assertEqual(module.shift_links("no link here"), "no link here")


if __name__ == "__main__":
    unittest.main()
