"""Regression checks for the cross-brain state tool: brain list, transcript states and map (no network, no real brain)."""

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


class BrainMapTest(unittest.TestCase):
    """`map`: where everything is, on two fictitious brains (`brain-acme` is the default one)."""

    TODAY = "2026-10-25"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        self.work.mkdir()
        self.write("work-config.local.json", json.dumps({"version": 1, "defaultBrain": "brain-acme"}))
        self.env = {**os.environ, "WORK_DIR": str(self.work), "ACTION_NOW": f"{self.TODAY} 09:00"}
        self.make_acme()
        self.make_abacus()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, relative: str, text: str) -> Path:
        path = self.work / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def make_brain(self, name: str, scope: str) -> None:
        self.write(f"{name}/AGENTS.md", "# test\n")
        self.write(f"{name}/.data/brain.json", json.dumps({"version": 1, "scope": scope, "description": "Fixture."}))

    def project(self, folder: str, header: str = "", actions: tuple = (), page: str | None = "", decisions: str | None = None) -> None:
        """A project folder: its register (`actions` are (prefix, state, due) tuples), its page and its decisions when given."""
        lines = [f"- [{state}] **{prefix}-{number:03d}** — Jane Doe — Task {number}" + (f" 📅 {due}" if due else "")
                 for number, (prefix, state, due) in enumerate(actions, 1)]
        sections = {"Open": " /w", "Done": "x", "Cancelled": "-"}
        body = "".join(
            f"## {title}\n" + "".join(line + "\n" for line, (_, state, _) in zip(lines, actions) if state in states) + "\n"
            for title, states in sections.items()
        )
        self.write(f"{folder}/state/actions.md", f"# Actions — {Path(folder).name}\n\n> Register. {header}\n\n{body}")
        if page is not None:
            name = Path(folder).name
            self.write(f"{folder}/{name}.md", page or f"# {name}\n\n- **Status:** active\n\n## Timeline\n- {self.TODAY} — page created\n")
        if decisions is not None:
            self.write(f"{folder}/state/decisions.md", decisions)

    def make_acme(self) -> None:
        self.make_brain("brain-acme", "employer")
        self.write("brain-acme/people/jane-doe.md", "# Jane Doe\n")
        self.write("brain-acme/people/README.md", "# people/\n")
        self.write("brain-acme/people/archive/john-roe.md", "# John Roe\n")
        self.write(
            "brain-acme/inbox/inbox.md",
            "# 📥 Inbox — Scratchpad\n\n> Raw capture.\n\n- call Jane Doe about the schema\nbuy a monitor\n"
            "- 2026-10-20 — triage: 3 item(s) dispatched, 0 question(s) left\n",
        )
        self.write("brain-acme/projects/clients/globex/globex.md", "# Client: Globex\n")
        mission = "brain-acme/projects/clients/globex/missions/migration"
        self.project(
            mission,
            actions=(
                ("GLB", " ", "2026-10-01"),  # to do, overdue
                ("GLB", " ", self.TODAY),  # to do, due today: not overdue
                ("GLB", "/", "2026-10-24"),  # in progress, overdue
                ("GLB", "w", "2026-11-01"),
                ("GLB", "x", "2026-09-01"),  # done: never overdue
                ("GLB", "x", ""),
                ("GLB", "-", ""),  # cancelled: not counted
            ),
            page=(
                "# Mission: Migration\n\n## Summary\n- 2026-12-31 — not a timeline entry\n\n"
                "## Timeline\nPrevious months: [2026-09](journal/2026-09.md)\n- 2026-10-20 — kickoff\n"
                "- 2026-10-24 — workshop\n- 2026-10-02 — preparation\n\n## Notes\n- 2026-12-31 — not a timeline entry\n"
            ),
            decisions=(
                "# Decisions — migration\n\n## Proposed\n\n### Keep the schema (2026-10-01, status: proposed)\n- **Decision:** keep it.\n\n"
                "### Use the batch API (2026-10-02, status: proposed)\n- **Decision:** use it.\n\n"
                "## Accepted\n\n### Archive the logs (2026-09-01, status: accepted)\n- **Decision:** archive.\n\n## Rejected / superseded\n"
            ),
        )
        self.project("brain-acme/projects/clients/globex/missions/support", header="Reserved prefix: `SUP`.", page=None)
        self.project("brain-acme/projects/clients/globex/archive/legacy", actions=(("GLB", "x", "2026-01-05"),))
        self.project("brain-acme/projects/clients/initech/missions/rollout", actions=(("INI", " ", ""),))  # no client index page
        self.project("brain-acme/projects/internal/setup", actions=(("SET", "/", ""),))
        self.project("brain-acme/projects/archive/old-tool", actions=(("OLD", "x", "2025-12-01"),))

    def make_abacus(self) -> None:
        self.make_brain("brain-abacus", "personal")
        self.write("brain-abacus/inbox/inbox.md", "# 📥 Inbox — Scratchpad\n\n> Raw capture.\n\n")
        self.project("brain-abacus/projects/internal/notes", actions=(("NOT", " ", ""),))

    def run_map(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), "map", *args], env=self.env, capture_output=True, text=True)

    def data(self, *args: str) -> dict:
        result = self.run_map("--json", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def brain(self, name: str, *args: str) -> dict:
        return next(brain for brain in self.data(*args)["brains"] if brain["name"] == name)

    def project_of(self, label: str, *args: str) -> dict:
        brain = self.brain("brain-acme", *args)
        projects = [*brain["internal"], *(project for client in brain["clients"] for project in client["projects"])]
        return next(project for project in projects if project["label"] == label)

    def test_default_brain_comes_first_and_is_flagged(self) -> None:
        brains = self.data()["brains"]
        self.assertEqual([(brain["name"], brain["default"], brain["scope"]) for brain in brains],
                         [("brain-acme", True, "employer"), ("brain-abacus", False, "personal")])
        self.assertEqual(self.data()["today"], self.TODAY)

    def test_counts_actions_by_state_and_overdue(self) -> None:
        project = self.project_of("globex / migration")
        self.assertEqual(project["actions"], {"open": 2, "in_progress": 1, "waiting": 1, "done": 2, "overdue": 2})
        self.assertEqual(self.project_of("initech / rollout")["actions"], {"open": 1, "in_progress": 0, "waiting": 0, "done": 0, "overdue": 0})

    def test_prefix_comes_from_the_ids_then_from_the_register_header(self) -> None:
        self.assertEqual(self.project_of("globex / migration")["prefix"], "GLB")
        self.assertEqual(self.project_of("globex / support")["prefix"], "SUP")  # no action yet: reserved in the header
        self.assertEqual(self.brain("brain-abacus")["internal"][0]["prefix"], "NOT")
        self.write("brain-acme/projects/internal/setup/state/actions.md", "# Actions — setup\n\n## Open\n")
        self.assertIsNone(self.project_of("setup")["prefix"])

    def test_page_path_is_relative_to_the_work_root_and_null_when_missing(self) -> None:
        migration = self.project_of("globex / migration")
        self.assertEqual(migration["page"], "brain-acme/projects/clients/globex/missions/migration/migration.md")
        self.assertEqual(migration["register"], "brain-acme/projects/clients/globex/missions/migration/state/actions.md")
        self.assertTrue((self.work / migration["page"]).is_file())
        support = self.project_of("globex / support")
        self.assertIsNone(support["page"])
        self.assertEqual(support["register"], "brain-acme/projects/clients/globex/missions/support/state/actions.md")
        text = self.run_map().stdout
        self.assertIn("brain-acme/projects/clients/globex/missions/support/support.md (missing)", text)

    def test_proposed_decisions_are_counted_when_the_register_exists(self) -> None:
        self.assertEqual(self.project_of("globex / migration")["decisions_proposed"], 2)
        self.assertIsNone(self.project_of("globex / support")["decisions_proposed"])
        self.write("brain-acme/projects/clients/globex/missions/support/state/decisions.md", "# Decisions — support\n\n## Proposed\n\n## Accepted\n")
        self.assertEqual(self.project_of("globex / support")["decisions_proposed"], 0)

    def test_last_timeline_entry_is_the_latest_date_of_the_timeline_section(self) -> None:
        self.assertEqual(self.project_of("globex / migration")["last_timeline"], "2026-10-24")  # not first, not the 2026-12-31 outside it
        self.assertEqual(self.project_of("setup")["last_timeline"], self.TODAY)
        self.assertIsNone(self.project_of("globex / support")["last_timeline"])

    def test_archived_projects_are_hidden_until_all(self) -> None:
        def flags(*args: str) -> dict:
            brain = self.brain("brain-acme", *args)
            projects = [*brain["internal"], *(project for client in brain["clients"] for project in client["projects"])]
            return {project["label"]: project["archived"] for project in projects}

        self.assertEqual(flags(), {"setup": False, "globex / migration": False, "globex / support": False, "initech / rollout": False})
        self.assertEqual(flags("--all"), {
            "setup": False, "old-tool": True, "globex / migration": False, "globex / support": False, "globex / legacy": True,
            "initech / rollout": False,
        })
        self.assertNotIn("[archived]", self.run_map().stdout)
        archived = [line for line in self.run_map("--all").stdout.splitlines() if "[archived]" in line]
        self.assertEqual(sorted(line.split()[0] for line in archived), ["legacy", "old-tool"])

    def test_brain_option_keeps_one_brain_and_refuses_an_unknown_one(self) -> None:
        self.assertEqual([brain["name"] for brain in self.data("--brain", "brain-abacus")["brains"]], ["brain-abacus"])
        result = self.run_map("--brain", "brain-nope")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown brain brain-nope", result.stderr)
        self.assertIn("brain-acme, brain-abacus", result.stderr)

    def test_json_keys_are_stable(self) -> None:
        data = self.data()
        self.assertEqual(sorted(data), ["brains", "today"])
        brain = data["brains"][0]
        self.assertEqual(sorted(brain), ["clients", "default", "inbox_lines", "internal", "name", "people", "scope"])
        client = brain["clients"][0]
        self.assertEqual(sorted(client), ["name", "page", "projects"])
        project = client["projects"][0]
        self.assertEqual(sorted(project), ["actions", "archived", "client", "decisions_proposed", "kind", "label", "last_timeline", "name", "page", "prefix", "register"])
        self.assertEqual(sorted(project["actions"]), ["done", "in_progress", "open", "overdue", "waiting"])
        self.assertEqual((project["kind"], project["client"], project["name"]), ("client", "globex", "migration"))
        internal = brain["internal"][0]
        self.assertEqual((internal["kind"], internal["client"], internal["label"]), ("internal", None, "setup"))

    def test_clients_are_listed_with_their_index_page(self) -> None:
        clients = {client["name"]: client["page"] for client in self.brain("brain-acme")["clients"]}
        self.assertEqual(clients, {"globex": "brain-acme/projects/clients/globex/globex.md", "initech": None})
        self.assertIn("client initech  (no index page)", self.run_map().stdout)

    def test_counts_people_pages_and_inbox_lines(self) -> None:
        acme = self.brain("brain-acme")
        self.assertEqual((acme["people"], acme["inbox_lines"]), (1, 2))  # README, archive and the triage log line do not count
        abacus = self.brain("brain-abacus")
        self.assertEqual((abacus["people"], abacus["inbox_lines"]), (0, 0))
        self.write("brain-abacus/inbox/inbox.md", "# Inbox\n\n> Raw capture.\n\n---\n\n> a quote below the separator\n\n- a line\n")
        self.assertEqual(self.brain("brain-abacus")["inbox_lines"], 2)
        (self.work / "brain-abacus/inbox/inbox.md").unlink()
        self.assertEqual(self.brain("brain-abacus")["inbox_lines"], 0)

    def test_text_has_one_aligned_line_per_project_grouped_by_brain_and_client(self) -> None:
        lines = self.run_map().stdout.splitlines()
        self.assertEqual(lines[0], "brain-acme (employer, default) — people 1 — inbox 2 to triage")
        self.assertEqual([line for line in lines if not line.startswith("    ")][:7], [
            lines[0],
            "  client globex  brain-acme/projects/clients/globex/globex.md",
            "  client initech  (no index page)",
            "  internal",
            "brain-abacus (personal) — people 0 — inbox empty",
            "  internal",
            "",
        ])
        projects = [line for line in lines if line.startswith("    ")]
        self.assertEqual([line.split()[0] for line in projects], ["migration", "support", "rollout", "setup", "notes"])
        acme = projects[:4]
        self.assertEqual(len({line.index("open ") for line in acme}), 1)
        self.assertEqual(len({line.index("brain-acme/") for line in acme}), 1)
        self.assertIn("GLB  open 2  doing 1  wait 1  done 2  late 2  dec 2  last 2026-10-24  brain-acme/projects/clients/globex/missions/migration/migration.md", acme[0])
        self.assertIn("SUP  open 0  doing 0  wait 0  done 0  late 0  dec -  last -", acme[1])

    def test_map_writes_nothing(self) -> None:
        def snapshot() -> list:
            return sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in self.work.rglob("*"))
        before = snapshot()
        self.assertEqual(self.run_map("--all").returncode, 0)
        self.assertEqual(self.run_map("--json").returncode, 0)
        self.assertEqual(snapshot(), before)


if __name__ == "__main__":
    unittest.main()
