# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "markdown-it-py==3.0.0",
# ]
# ///
"""Local task manager checks against a temporary brain, never the real registers."""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
TOOL = Path(__file__).resolve().parents[1] / "tools/tasks-web/tasks-web.py"
spec = importlib.util.spec_from_file_location("tasks_web", TOOL)
tasks_web = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tasks_web)


RICH_REGISTER = "# Actions\n\n## Open\n- [ ] **EXM-001** — Jane — Préparer la livraison 📅 2026-10-15\n    - Source: note initiale\n    - 12/10: une note\n        - sous-détail\n\n## Done\n- [x] **EXM-009** — Jane — Ancienne clôture sans date\n"


class TasksWebTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.brain = Path(self.temp.name) / "brain"
        self.register = self.brain / "projects/clients/example/missions/test/state/actions.md"
        self.register.parent.mkdir(parents=True)
        self.register.write_text("# Actions\n\n## Open\n- [ ] **EXM-001** — Jane — Préparer la livraison 📅 2026-10-15\n    - source: note initiale\n\n## Done\n- [x] **EXM-009** — Jane — Ancienne clôture sans date\n", encoding="utf-8")
        (self.brain / ".data").mkdir()
        (self.brain / ".data/doctor.json").write_text('{"owner":"Jane"}', encoding="utf-8")
        self.server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(self.brain))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, payload=None, token=True, origin=True):
        headers = {}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Tasks-Token"] = self.server.token
        if origin:
            headers["Origin"] = self.base
        request = Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None, method=method, headers=headers)
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def test_empty_client_register_keeps_its_client_in_the_label(self):
        empty = self.brain / "projects/clients/acme/missions/rollout/state/actions.md"
        empty.parent.mkdir(parents=True)
        empty.write_text("# Actions — rollout\n\n## Open\n\n## Done\n\n## Cancelled\n", encoding="utf-8")
        status, data = self.request("GET", "/api/actions")
        self.assertEqual(status, 200)
        labels = {register["path"]: register["label"] for register in data["registers"]}
        self.assertEqual(labels["projects/clients/acme/missions/rollout/state/actions.md"], "acme / rollout")
        self.assertEqual(labels["projects/clients/example/missions/test/state/actions.md"], "example / test")

    def test_vague_due_wording_is_exposed_as_due_note_only_without_a_date(self):
        self.register.write_text(
            "# Actions\n\n## Open\n"
            "- [ ] **EXM-001** — Jane Doe — Dated 📅 2026-10-15\n    - due: before 15/10\n"
            "- [ ] **EXM-002** — Jane Doe — Vague\n    - source: kickoff\n    - DUE:   week   of 05/10  \n"
            "- [ ] **EXM-003** — Jane Doe — Explicitly none\n    - due: —\n"
            "- [ ] **EXM-004** — Jane Doe — Nothing at all\n"
            "- [ ] **EXM-005** — Jane Doe — Long\n    - due: " + "x" * 300 + "\n"
            "\n## Done\n- [x] **EXM-009** — Jane Doe — Closed\n", encoding="utf-8")
        status, data = self.request("GET", "/api/actions")
        self.assertEqual(status, 200)
        notes = {action["id"]: (action["due"], action["due_note"]) for action in data["actions"]}
        self.assertEqual(notes["EXM-001"], ("2026-10-15", ""))  # the 📅 date is authoritative
        self.assertEqual(notes["EXM-002"], ("", "week of 05/10"))
        self.assertEqual(notes["EXM-003"], ("", ""))
        self.assertEqual(notes["EXM-004"], ("", ""))
        self.assertEqual(notes["EXM-005"], ("", "x" * 200))
        self.assertEqual(notes["EXM-009"], ("", ""))

    def test_planning_a_deadline_by_dragging_is_the_due_date_update_and_undo_restores_the_register(self):
        # What the Timeline sends when a card is dropped on a day, a chip is moved, or a chip goes back to the tray: the line of the action
        # as the page holds it, with the one new `due`.
        self.register.write_text(
            "# Actions\n\n## Open\n"
            "- [ ] **EXM-001** — Jane Doe — Dated 📅 2026-10-15\n"
            "- [/] **EXM-002** — Jane Doe — Undated\n    - source: kickoff\n"
            "- [ ] **EXM-003** — Jane Doe — Vague\n    - due: week of 05/10\n", encoding="utf-8")
        original = self.register.read_bytes()

        def change(action_id, **fields):
            current = next(item for item in self.request("GET", "/api/actions")[1]["actions"] if item["id"] == action_id)
            body = {"title": current["raw_title"], "owner": current["owner"], "state": current["state"], "priority": current["priority"],
                    "due": current["due"], "scheduled": current["scheduled"], **fields}
            status, result = self.request("PATCH", f"/api/actions/{action_id}", {"version": current["version"], "action": body})
            self.assertEqual(status, 200, result)
            return result

        def due(action_id):
            return next(item for item in self.request("GET", "/api/actions")[1]["actions"] if item["id"] == action_id)

        # A card from the tray onto a day: the undated action gets its 📅 date, nothing else changes.
        result = change("EXM-002", due="2026-10-28")
        self.assertEqual(due("EXM-002")["due"], "2026-10-28")
        self.assertIn("**EXM-002** — Jane Doe — Undated 📅 2026-10-28", self.register.read_text(encoding="utf-8"))
        self.assertTrue(result["undo"]["available"])
        # A vague action: it gets a date too, its `due:` wording stays in the register but is no longer what the page shows.
        change("EXM-003", due="2026-11-02")
        vague = due("EXM-003")
        self.assertEqual((vague["due"], vague["due_note"]), ("2026-11-02", ""))
        self.assertIn("    - due: week of 05/10", self.register.read_text(encoding="utf-8"))
        # A chip moved by a day (Alt+→), then back onto the tray (no deadline): the date is replaced, then removed.
        change("EXM-001", due="2026-10-16")
        self.assertEqual(due("EXM-001")["due"], "2026-10-16")
        change("EXM-001", due="")
        self.assertEqual(due("EXM-001")["due"], "")
        self.assertNotIn("📅 2026-10-15", self.register.read_text(encoding="utf-8").split("EXM-002")[0])
        # Each of them is one undo step, newest first, and the register comes back byte for byte.
        for _step in range(4):
            state = self.request("GET", "/api/undo")[1]
            self.assertTrue(state["available"])
            status, _ = self.request("POST", "/api/undo", {"label": state["label"]})
            self.assertEqual(status, 200)
        self.assertEqual(self.register.read_bytes(), original)
        # A drop on an action another write has changed meanwhile is refused, not applied.
        stale = due("EXM-002")
        change("EXM-002", due="2026-10-29")
        status, _ = self.request("PATCH", "/api/actions/EXM-002", {"version": stale["version"], "action": {
            "title": stale["raw_title"], "owner": stale["owner"], "state": stale["state"], "priority": stale["priority"], "due": "2026-10-30", "scheduled": ""}})
        self.assertEqual(status, 409)
        self.assertEqual(due("EXM-002")["due"], "2026-10-29")

    def test_reads_real_register_format(self):
        status, data = self.request("GET", "/api/actions")
        self.assertEqual(status, 200)
        self.assertEqual(data["owner"], "Jane")
        self.assertEqual(data["actions"][0]["title"], "Préparer la livraison")
        self.assertEqual(data["actions"][0]["due"], "2026-10-15")
        self.assertEqual(data["registers"][0]["prefix"], "EXM")

    def test_loads_action_details_without_adjacent_actions(self):
        status, detail = self.request("GET", "/api/actions/EXM-001/details")
        self.assertEqual(status, 200)
        self.assertEqual(detail["details"], ["- source: note initiale"])
        self.assertNotIn("EXM-009", str(detail["details"]))
        status, _ = self.request("GET", "/api/actions/EXM-999/details")
        self.assertEqual(status, 404)

    def test_tool_launcher_is_allowlisted_and_protected(self):
        status, catalog = self.request("GET", "/api/tools")
        self.assertEqual(status, 200)
        self.assertIn("links", {tool["id"] for tool in catalog["tools"]})
        commands = [tool["command"] for tool in catalog["tools"]]
        self.assertFalse(any("--apply" in command for command in commands))
        by_id = {tool["id"]: tool for tool in catalog["tools"]}
        self.assertTrue(by_id["archive_write"]["command"].endswith("action.py archive --write"))
        self.assertIn("Archive the actions", by_id["archive_write"]["confirm"])
        self.assertEqual(by_id["archive_preview"]["command"], "uv run tools/brain/action.py archive")
        self.assertIsNone(by_id["archive_preview"]["confirm"])
        self.assertEqual({tool_id for tool_id, tool in by_id.items() if tool["confirm"]}, {"archive_write", "sweep_write"})
        self.assertFalse(any("client-repos.py clone" in command for command in commands))
        # The memory tools added next to "brains" only read: no `--write`, no confirmation, and the brain map is limited to the chosen brain.
        self.assertEqual(by_id["map"]["command"], "uv run tools/brain/brain-state.py map --brain <brain>")
        self.assertEqual(by_id["timeline-roll"]["command"], "uv run tools/brain/timeline.py roll")
        for tool_id in ("map", "timeline-roll"):
            self.assertEqual(by_id[tool_id]["group"], "Memory")
            self.assertIsNone(by_id[tool_id]["confirm"])
            self.assertNotIn("--write", by_id[tool_id]["command"])
        self.assertEqual(by_id["map"]["label"], "Brain map")
        self.assertEqual(by_id["timeline-roll"]["label"], "Timeline months to move")
        self.assertEqual({tool["group"] for tool in catalog["tools"]}, {"Memory", "Actions", "Repositories"})
        for tool_id, (_group, _label, _description, script, _args) in tasks_web.TOOLS.items():
            self.assertTrue((tasks_web.TOOLS_ROOT / "tools" / script).is_file(), f"{tool_id}: tools/{script} not found")
        status, _ = self.request("POST", "/api/tools/run", {"id": "links"}, token=False)
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/tools/run", {"id": "links"}, origin=False)
        self.assertEqual(status, 403)
        with patch.object(tasks_web, "run_tool", return_value={"id": "links", "ok": True, "output": "OK", "truncated": False}) as runner:
            status, result = self.request("POST", "/api/tools/run", {"id": "links"})
        self.assertEqual(status, 200)
        self.assertEqual(result["output"], "OK")
        runner.assert_called_once_with("links", self.brain.resolve())
        status, _ = self.request("POST", "/api/tools/run", {"id": "arbitrary-command"})
        self.assertEqual(status, 404)

    def test_create_then_move_preserves_source_and_adds_completion_date(self):
        action = {"title": "Relancer le client", "owner": "Jane", "state": " ", "priority": "🔼", "due": "2026-10-20", "scheduled": ""}
        register = "projects/clients/example/missions/test/state/actions.md"
        status, result = self.request("POST", "/api/actions", {"register": register, "action": action})
        self.assertEqual(status, 201)
        self.assertEqual(result["id"], "EXM-010")
        snapshot = self.request("GET", "/api/actions")[1]
        created = next(item for item in snapshot["actions"] if item["id"] == "EXM-010")
        action["state"] = "x"
        status, _ = self.request("PATCH", "/api/actions/EXM-010", {"version": created["version"], "action": action})
        self.assertEqual(status, 200)
        text = self.register.read_text(encoding="utf-8")
        self.assertIn(f"**EXM-010** — Jane — Relancer le client 🔼 ➕ {datetime.now(ZoneInfo('Europe/Paris')).date().isoformat()} 📅 2026-10-20 ✅ ", text)
        self.assertIn("source: entered in the local interface", text)
        self.assertIn("source: note initiale", text)
        self.assertEqual(text.count("**EXM-010**"), 1)

    def test_rejects_stale_and_invalid_writes(self):
        action = {"title": "Préparer la livraison", "owner": "Jane", "state": "/", "priority": "", "due": "2026-10-15", "scheduled": ""}
        before = self.register.read_text(encoding="utf-8")
        status, _ = self.request("PATCH", "/api/actions/EXM-001", {"version": "stale", "action": action})
        self.assertEqual(status, 409)
        status, _ = self.request("PATCH", "/api/actions/EXM-001", {"version": "stale", "action": action}, token=False)
        self.assertEqual(status, 403)
        status, _ = self.request("PATCH", "/api/actions/EXM-001", {"version": "stale", "action": action}, origin=False)
        self.assertEqual(status, 403)
        action["state"] = []
        version = self.request("GET", "/api/actions")[1]["actions"][0]["version"]
        status, _ = self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": action})
        self.assertEqual(status, 400)
        self.assertEqual(self.register.read_text(encoding="utf-8"), before)

    def test_validation_messages_are_english_and_the_owner_refuses_the_register_separator(self):
        register = "projects/clients/example/missions/test/state/actions.md"
        before = self.register.read_text(encoding="utf-8")
        action = {"title": "T", "owner": "A — B", "state": " ", "priority": "", "due": "", "scheduled": ""}
        status, data = self.request("POST", "/api/actions", {"register": register, "action": action})
        self.assertEqual((status, data["error"]), (400, "Owner contains a separator reserved for registers."))
        for field, label in (("due", "Due date"), ("scheduled", "Scheduled date")):
            status, data = self.request("POST", "/api/actions", {"register": register, "action": {**action, "owner": "A", field: "tomorrow"}})
            self.assertEqual((status, data["error"]), (400, f"{label} must use the format YYYY-MM-DD."))
        status, data = self.request("POST", "/api/actions", {"register": register, "action": {**action, "owner": " ", "title": "T"}})
        self.assertEqual((status, data["error"]), (400, "Owner must be 1 to 120 characters on one line."))
        status, data = self.request("POST", "/api/actions", {"register": register, "action": {**action, "owner": "A", "state": "x"}})
        self.assertEqual((status, data["error"]), (400, "A new action must be to do, in progress or waiting."))
        self.assertEqual(self.register.read_text(encoding="utf-8"), before)
        status, data = self.request("POST", "/api/actions", {"register": register, "action": {**action, "owner": "A", "title": "T — U"}})
        self.assertEqual(status, 201)

    def test_editing_old_closed_action_does_not_invent_completion_date(self):
        old = next(item for item in self.request("GET", "/api/actions")[1]["actions"] if item["id"] == "EXM-009")
        action = {"title": "Ancienne clôture annotée", "owner": "Jane", "state": "x", "priority": "", "due": "", "scheduled": ""}
        status, _ = self.request("PATCH", "/api/actions/EXM-009", {"version": old["version"], "action": action})
        self.assertEqual(status, 200)
        self.assertIn("**EXM-009** — Jane — Ancienne clôture annotée\n", self.register.read_text(encoding="utf-8"))

    def notes_url(self, suffix=""):
        return "/api/actions/EXM-001/notes" + suffix

    def details(self):
        return self.request("GET", "/api/actions/EXM-001/details")[1]

    def test_exposes_notes_structure_and_version(self):
        self.register.write_text(RICH_REGISTER, encoding="utf-8")
        detail = self.details()
        self.assertEqual([note["index"] for note in detail["notes"]], [0, 1])
        self.assertEqual(detail["notes"][0], {"index": 0, "text": "- Source: note initiale", "deletable": False})
        self.assertEqual(detail["notes"][1], {"index": 1, "text": "- 12/10: une note\n    - sous-détail", "deletable": True})
        self.assertEqual(len(detail["details_version"]), 16)
        self.assertEqual(detail["details"][-1], "    - sous-détail")
        self.register.write_text(RICH_REGISTER.replace("sous-détail", "sous-détail modifié"), encoding="utf-8")
        self.assertNotEqual(self.details()["details_version"], detail["details_version"])

    def test_adds_two_dated_notes_in_a_row_inside_action_history(self):
        version = self.details()["details_version"]
        status, detail = self.request("POST", self.notes_url(), {"details_version": version, "note": "Décision : [compte rendu](../source.md) 📅 confirmé"})
        self.assertEqual(status, 201)
        self.assertEqual(len(detail["notes"]), 3)  # source, updated stamp, note
        self.assertNotEqual(detail["details_version"], version)
        status, detail = self.request("POST", self.notes_url(), {"details_version": detail["details_version"], "note": "Seconde note"})
        self.assertEqual(status, 201)
        self.assertTrue(detail["notes"][2]["text"].endswith("📅 confirmé") and detail["notes"][3]["text"].endswith(": Seconde note"))
        self.assertFalse(detail["notes"][1]["deletable"])
        text = self.register.read_text(encoding="utf-8")
        self.assertRegex(text, r"    - source: note initiale\n    - updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n    - \d{2}/\d{2}: Décision : \[compte rendu\]\(\.\./source\.md\) 📅 confirmé\n    - \d{2}/\d{2}: Seconde note\n\n## Done")
        self.assertTrue(text.endswith("Ancienne clôture sans date\n"))

    def test_rejects_stale_or_invalid_note_writes(self):
        version = self.details()["details_version"]
        before = self.register.read_text(encoding="utf-8")
        status, _ = self.request("POST", self.notes_url(), {"details_version": "stale", "note": "Note"})
        self.assertEqual(status, 409)
        for note in ("première ligne\n    - fausse action", "première ligne" + chr(0x2028) + "fausse action", "", "x" * 1001, 3):
            status, _ = self.request("POST", self.notes_url(), {"details_version": version, "note": note})
            self.assertEqual(status, 400, note)
        status, _ = self.request("POST", self.notes_url(), {"details_version": version, "note": "Note", "extra": 1})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", self.notes_url(), {"details_version": version, "note": "Note"}, token=False)
        self.assertEqual(status, 403)
        status, _ = self.request("POST", self.notes_url(), {"details_version": version, "note": "Note"}, origin=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.register.read_text(encoding="utf-8"), before)
        action_version = self.request("GET", "/api/actions")[1]["actions"][0]["version"]
        action = {"title": "Préparer la livraison", "owner": "Jane", "state": "/", "priority": "", "due": "2026-10-15", "scheduled": ""}
        status, _ = self.request("PATCH", "/api/actions/EXM-001", {"version": action_version, "action": action, "note": "n'existe plus"})
        self.assertEqual(status, 400)
        self.assertEqual(self.register.read_text(encoding="utf-8"), before)

    def test_deletes_note_with_its_children(self):
        self.register.write_text(RICH_REGISTER, encoding="utf-8")
        detail = self.details()
        note = detail["notes"][1]
        status, fresh = self.request("DELETE", self.notes_url("/1"), {"details_version": detail["details_version"], "text": note["text"]})
        self.assertEqual(status, 200)
        self.assertEqual([item["text"].split(": ")[0] for item in fresh["notes"]], ["- Source", "- updated"])
        text = self.register.read_text(encoding="utf-8")
        self.assertNotIn("une note", text)
        self.assertNotIn("sous-détail", text)
        self.assertRegex(text, r"    - Source: note initiale\n    - updated: \d{4}-\d{2}-\d{2} \d{2}:\d{2}\n\n## Done")

    def test_delete_keeps_register_tidy_between_notes(self):
        self.register.write_text(RICH_REGISTER.replace("    - 12/10", "    - 11/10: première\n\n    - 12/10"), encoding="utf-8")
        detail = self.details()
        note = detail["notes"][1]
        self.assertEqual(note["text"], "- 11/10: première")
        status, _ = self.request("DELETE", self.notes_url("/1"), {"details_version": detail["details_version"], "text": note["text"]})
        self.assertEqual(status, 200)
        self.assertRegex(self.register.read_text(encoding="utf-8"), r"    - Source: note initiale\n    - updated: [0-9: -]{16}\n\n    - 12/10: une note\n        - sous-détail\n\n## Done")

    def test_rejects_unsafe_note_deletions(self):
        self.register.write_text(RICH_REGISTER, encoding="utf-8")
        detail = self.details()
        before = self.register.read_text(encoding="utf-8")
        version = detail["details_version"]
        status, _ = self.request("DELETE", self.notes_url("/0"), {"details_version": version, "text": detail["notes"][0]["text"]})
        self.assertEqual(status, 400)
        status, _ = self.request("DELETE", self.notes_url("/7"), {"details_version": version, "text": "- x"})
        self.assertEqual(status, 400)
        status, _ = self.request("DELETE", self.notes_url("/1"), {"details_version": version, "text": "- autre texte"})
        self.assertEqual(status, 409)
        status, _ = self.request("DELETE", self.notes_url("/1"), {"details_version": "stale", "text": detail["notes"][1]["text"]})
        self.assertEqual(status, 409)
        status, _ = self.request("DELETE", self.notes_url("/1"), {"details_version": version, "text": detail["notes"][1]["text"]}, token=False)
        self.assertEqual(status, 403)
        status, _ = self.request("DELETE", self.notes_url("/1"), {"details_version": version, "text": detail["notes"][1]["text"]}, origin=False)
        self.assertEqual(status, 403)
        self.assertEqual(self.register.read_text(encoding="utf-8"), before)

    def raw(self):
        return self.register.read_bytes()

    def create_action(self, title="Relancer le client"):
        action = {"title": title, "owner": "Jane", "state": " ", "priority": "", "due": "", "scheduled": ""}
        return self.request("POST", "/api/actions", {"register": "projects/clients/example/missions/test/state/actions.md", "action": action})

    GROUP_REGISTER = "projects/clients/example/missions/test/state/actions.md"

    def test_api_exposes_group_and_register_groups(self):
        self.register.write_text(self.register.read_text(encoding="utf-8").replace(
            "Préparer la livraison 📅", "Préparer la livraison #group/atelier-ingestion 📅").replace(
            "Ancienne clôture sans date", "Ancienne clôture sans date #group/cadrage"), encoding="utf-8")
        data = self.request("GET", "/api/actions")[1]
        by_id = {a["id"]: a for a in data["actions"]}
        self.assertEqual((by_id["EXM-001"]["group"], by_id["EXM-001"]["title"], by_id["EXM-001"]["raw_title"]),
                         ("atelier-ingestion", "Préparer la livraison", "Préparer la livraison"))
        self.assertEqual(by_id["EXM-001"]["due"], "2026-10-15")
        self.assertEqual(data["registers"][0]["groups"], ["atelier-ingestion", "cadrage"])

    def test_actions_without_group_expose_an_empty_group(self):
        data = self.request("GET", "/api/actions")[1]
        self.assertEqual([a["group"] for a in data["actions"]], ["", ""])
        self.assertEqual(data["registers"][0]["groups"], [])

    def test_create_and_patch_accept_group_and_undo_restores_bytes(self):
        original = self.raw()
        action = {"title": "Planifier l'atelier", "owner": "Jane", "state": " ", "priority": "⏫", "due": "2026-10-20", "scheduled": "", "group": "atelier-ingestion"}
        status, result = self.request("POST", "/api/actions", {"register": self.GROUP_REGISTER, "action": action})
        self.assertEqual(status, 201)
        today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        self.assertIn(f"**EXM-010** — Jane — Planifier l'atelier #group/atelier-ingestion ⏫ ➕ {today} 📅 2026-10-20\n", self.register.read_text(encoding="utf-8"))
        current = next(a for a in self.request("GET", "/api/actions")[1]["actions"] if a["id"] == "EXM-010")
        self.assertEqual((current["group"], current["raw_title"]), ("atelier-ingestion", "Planifier l'atelier"))
        # The editor sends raw_title (no tag) and the group on its own: the tag is neither doubled nor lost.
        edited = {**action, "title": current["raw_title"], "group": "cadrage"}
        status, patched = self.request("PATCH", "/api/actions/EXM-010", {"version": current["version"], "action": edited})
        self.assertEqual((status, patched["undo"]["label"]), (200, "edit of EXM-010"))
        text = self.register.read_text(encoding="utf-8")
        self.assertIn("Planifier l'atelier #group/cadrage ⏫", text)
        self.assertEqual(text.count("#group/"), 1)
        current = next(a for a in self.request("GET", "/api/actions")[1]["actions"] if a["id"] == "EXM-010")
        status, _ = self.request("PATCH", "/api/actions/EXM-010", {"version": current["version"], "action": {**edited, "group": ""}})
        self.assertEqual(status, 200)
        self.assertNotIn("#group/", self.register.read_text(encoding="utf-8"))
        self.assertEqual(self.request("POST", "/api/undo", {"label": "edit of EXM-010"})[0], 200)
        self.assertIn("#group/cadrage", self.register.read_text(encoding="utf-8"))
        self.request("POST", "/api/undo", {"label": "edit of EXM-010"})
        self.request("POST", "/api/undo", {"label": "creation of EXM-010"})
        self.assertEqual(self.raw(), original)

    def test_patch_without_group_keeps_it_and_status_change_survives(self):
        self.register.write_text(self.register.read_text(encoding="utf-8").replace(
            "Préparer la livraison 📅", "Préparer la livraison #group/atelier-ingestion 📅"), encoding="utf-8")
        current = self.request("GET", "/api/actions")[1]["actions"][0]
        action = {"title": current["raw_title"], "owner": "Jane", "state": "/", "priority": "", "due": "2026-10-15", "scheduled": ""}
        status, result = self.request("PATCH", "/api/actions/EXM-001", {"version": current["version"], "action": action})
        self.assertEqual((status, result["undo"]["label"]), (200, "status of EXM-001 → In progress"))
        self.assertIn("Préparer la livraison #group/atelier-ingestion 📅 2026-10-15", self.register.read_text(encoding="utf-8"))

    def test_invalid_group_and_title_ending_with_a_tag_are_rejected(self):
        original = self.raw()
        base = {"title": "Planifier", "owner": "Jane", "state": " ", "priority": "", "due": "", "scheduled": ""}
        version = self.request("GET", "/api/actions")[1]["actions"][0]["version"]
        for bad in ("Atelier Ingestion", "atelier_ingestion", "a--b", "-a", "é", "a" * 41, 3, None, ["a"]):
            status, data = self.request("POST", "/api/actions", {"register": self.GROUP_REGISTER, "action": {**base, "group": bad}})
            self.assertEqual(status, 400, bad)
            self.assertIn("Invalid group", data["error"])
            status, _ = self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": {**base, "group": bad}})
            self.assertEqual(status, 400, bad)
        status, data = self.request("POST", "/api/actions", {"register": self.GROUP_REGISTER, "action": {**base, "title": "Planifier #group/autre"}})
        self.assertEqual(status, 400)
        self.assertIn("Group", data["error"])
        self.assertEqual(self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": {**base, "title": "Planifier #group/autre"}})[0], 400)
        self.assertEqual(self.request("POST", "/api/actions", {"register": self.GROUP_REGISTER, "action": {**base, "group": "a" * 40}})[0], 201)
        self.request("POST", "/api/undo", {"label": "creation of EXM-010"})
        self.assertEqual(self.raw(), original)
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)

    def test_undo_is_initially_unavailable(self):
        self.assertEqual(self.request("GET", "/api/undo"), (200, {"available": False, "label": None, "depth": 0}))
        status, _ = self.request("POST", "/api/undo", {"label": "x"})
        self.assertEqual(status, 409)

    def test_write_responses_include_undo_state(self):
        status, created = self.create_action()
        self.assertEqual((status, created["undo"]), (201, {"available": True, "label": "creation of EXM-010", "depth": 1}))
        status, detail = self.request("POST", self.notes_url(), {"details_version": self.details()["details_version"], "note": "Note"})
        self.assertEqual((status, detail["undo"]["label"], detail["undo"]["depth"]), (201, "note added to EXM-001", 2))
        version = self.request("GET", "/api/actions")[1]["actions"][0]["version"]
        action = {"title": "Préparer la livraison", "owner": "Jane", "state": "/", "priority": "", "due": "2026-10-15", "scheduled": ""}
        status, updated = self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": action})
        self.assertEqual((status, updated["undo"]["label"]), (200, "status of EXM-001 → In progress"))
        self.assertEqual(self.request("GET", "/api/undo")[1], updated["undo"])

    def test_status_change_moves_action_to_its_section_and_undo_restores(self):
        original = self.raw()
        current = self.request("GET", "/api/actions")[1]["actions"][0]
        version = current["version"]
        action = {"title": current["raw_title"], "owner": current["owner"], "state": "x", "priority": current["priority"], "due": current["due"], "scheduled": current["scheduled"]}
        status, _ = self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": action})
        self.assertEqual(status, 200)
        text = self.register.read_text(encoding="utf-8")
        self.assertGreater(text.index("**EXM-001**"), text.index("## Done"))
        reopened = {**action, "state": " "}
        version = next(a["version"] for a in self.request("GET", "/api/actions")[1]["actions"] if a["id"] == "EXM-001")
        self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": reopened})
        text = self.register.read_text(encoding="utf-8")
        self.assertLess(text.index("**EXM-001**"), text.index("## Done"))
        self.request("POST", "/api/undo", {"label": "status of EXM-001 → To do"})
        self.request("POST", "/api/undo", {"label": "status of EXM-001 → Done"})
        self.assertEqual(self.raw(), original)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_noop_and_return_to_synced_state_keep_the_previous_updated_stamp(self):
        self.register.write_text(self.register.read_text(encoding="utf-8").replace(
            "    - source: note initiale\n", "    - source: note initiale\n    - created: 2026-10-01 09:00\n    - updated: 2026-10-20 16:24\n"),
            encoding="utf-8")
        environment = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}

        def git(*args):
            return subprocess.run(["git", "-C", str(self.brain), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                                  env=environment, check=True, capture_output=True, text=True)

        for args in (("init", "-q"), ("add", "-A"), ("commit", "-q", "-m", "test: register")):
            git(*args)
        branch = git("branch", "--show-current").stdout.strip()
        git("branch", "sync-point")
        git("config", f"branch.{branch}.remote", ".")
        git("config", f"branch.{branch}.merge", "refs/heads/sync-point")

        original = self.raw()
        before = self.register.stat()
        current = self.request("GET", "/api/actions")[1]["actions"][0]
        action = {"title": current["raw_title"], "owner": current["owner"], "state": current["state"],
                  "priority": current["priority"], "due": current["due"], "scheduled": current["scheduled"]}
        status, result = self.request("PATCH", "/api/actions/EXM-001", {"version": current["version"], "action": action})
        after = self.register.stat()
        self.assertEqual((status, result["undo"]["available"]), (200, False))
        self.assertEqual((after.st_ino, after.st_mtime_ns), (before.st_ino, before.st_mtime_ns))

        action["state"] = "/"
        self.assertEqual(self.request("PATCH", "/api/actions/EXM-001", {"version": current["version"], "action": action})[0], 200)
        git("add", "-A")
        git("commit", "-q", "-m", "test: unsent local change")
        current = next(item for item in self.request("GET", "/api/actions")[1]["actions"] if item["id"] == "EXM-001")
        action["state"] = " "
        self.assertEqual(self.request("PATCH", "/api/actions/EXM-001", {"version": current["version"], "action": action})[0], 200)
        self.assertEqual(self.raw(), original)
        relative = self.register.relative_to(self.brain).as_posix()
        self.assertEqual(git("diff", "--name-only", "sync-point", "--", relative).stdout, "")

    def test_created_date_is_written_exposed_and_kept_on_update(self):
        status, created = self.create_action("Préparer la revue")
        self.assertEqual(status, 201)
        action_id = created["id"]
        today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        self.assertIn(f"**{action_id}** — Jane — Préparer la revue ➕ {today}", self.register.read_text(encoding="utf-8"))
        current = next(a for a in self.request("GET", "/api/actions")[1]["actions"] if a["id"] == action_id)
        self.assertEqual((current["created"], current["title"]), (today, "Préparer la revue"))
        action = {"title": current["raw_title"], "owner": current["owner"], "state": "/", "priority": "⏫", "due": "2026-10-20", "scheduled": ""}
        self.assertEqual(self.request("PATCH", f"/api/actions/{action_id}", {"version": current["version"], "action": action})[0], 200)
        line = next(l for l in self.register.read_text(encoding="utf-8").splitlines() if f"**{action_id}**" in l)
        self.assertIn(f"⏫ ➕ {today} 📅 2026-10-20", line)
        again = next(a for a in self.request("GET", "/api/actions")[1]["actions"] if a["id"] == action_id)
        self.assertEqual((again["created"], again["title"]), (today, "Préparer la revue"))

    def test_undo_create_restores_exact_bytes(self):
        original = self.raw()
        self.create_action()
        self.assertNotEqual(self.raw(), original)
        status, result = self.request("POST", "/api/undo", {"label": "creation of EXM-010"})
        self.assertEqual(status, 200)
        self.assertEqual((result["undone"], result["action_id"]), ("creation of EXM-010", "EXM-010"))
        self.assertEqual(result["undo"], {"available": False, "label": None, "depth": 0})
        self.assertEqual(self.raw(), original)
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)

    def test_undo_walks_back_in_lifo_order_with_status_label(self):
        original = self.raw()
        version = self.request("GET", "/api/actions")[1]["actions"][0]["version"]
        action = {"title": "Préparer la livraison", "owner": "Jane", "state": "/", "priority": "", "due": "2026-10-15", "scheduled": ""}
        self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": action})
        after_status = self.raw()
        self.request("POST", self.notes_url(), {"details_version": self.details()["details_version"], "note": "Note"})
        self.assertEqual(self.request("GET", "/api/undo")[1], {"available": True, "label": "note added to EXM-001", "depth": 2})
        status, result = self.request("POST", "/api/undo", {"label": "note added to EXM-001"})
        self.assertEqual((status, result["undo"]["label"]), (200, "status of EXM-001 → In progress"))
        self.assertEqual(self.raw(), after_status)
        status, result = self.request("POST", "/api/undo", {"label": "status of EXM-001 → In progress"})
        self.assertEqual((status, result["undo"]["depth"]), (200, 0))
        self.assertEqual(self.raw(), original)
        action["title"] = "Autre titre"
        version = self.request("GET", "/api/actions")[1]["actions"][0]["version"]
        self.assertEqual(self.request("PATCH", "/api/actions/EXM-001", {"version": version, "action": action})[1]["undo"]["label"], "edit of EXM-001")

    def test_undo_note_deletion(self):
        self.register.write_text(RICH_REGISTER, encoding="utf-8")
        original = self.raw()
        detail = self.details()
        self.request("DELETE", self.notes_url("/1"), {"details_version": detail["details_version"], "text": detail["notes"][1]["text"]})
        self.assertNotEqual(self.raw(), original)
        status, result = self.request("POST", "/api/undo", {"label": "note deleted from EXM-001"})
        self.assertEqual(status, 200)
        self.assertEqual(self.raw(), original)

    def test_undo_preserves_crlf_and_missing_trailing_newline(self):
        original = "# Actions\r\n\r\n## Open\r\n- [ ] **EXM-001** — Jane — Titre\r\n    - source: x".encode("utf-8")
        self.register.write_bytes(original)
        status, created = self.create_action()
        self.assertEqual(status, 201)
        self.assertEqual(self.request("POST", "/api/undo", {"label": created["undo"]["label"]})[0], 200)
        self.assertEqual(self.raw(), original)

    def test_undo_with_wrong_label_is_refused(self):
        self.create_action()
        after = self.raw()
        status, _ = self.request("POST", "/api/undo", {"label": "autre chose"})
        self.assertEqual(status, 409)
        status, _ = self.request("POST", "/api/undo", {"label": 3})
        self.assertEqual(status, 400)
        status, _ = self.request("POST", "/api/undo", {})
        self.assertEqual(status, 400)
        self.assertEqual(self.raw(), after)
        self.assertEqual(self.request("GET", "/api/undo")[1]["depth"], 1)

    def test_undo_refused_and_dropped_when_register_changed_externally(self):
        self.create_action()
        self.create_action("Seconde")
        external = self.raw() + b"\n- modification externe\n"
        self.register.write_bytes(external)
        status, result = self.request("POST", "/api/undo", {"label": "creation of EXM-011"})
        self.assertEqual(status, 409)
        self.assertIn("cannot be undone", result["error"])
        self.assertEqual(self.raw(), external)
        self.assertEqual(self.request("GET", "/api/undo")[1], {"available": False, "label": None, "depth": 0})

    def test_undo_is_protected_like_other_writes(self):
        self.create_action()
        after = self.raw()
        self.assertEqual(self.request("POST", "/api/undo", {"label": "creation of EXM-010"}, token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/undo", {"label": "creation of EXM-010"}, origin=False)[0], 403)
        self.assertEqual(self.raw(), after)
        self.assertEqual(self.request("GET", "/api/undo")[1]["depth"], 1)

    def test_undo_stack_is_capped_at_twenty(self):
        original = self.raw()
        for number in range(22):
            self.create_action(f"Action {number}")
        self.assertEqual(self.request("GET", "/api/undo")[1], {"available": True, "label": "creation of EXM-031", "depth": 20})
        for _ in range(20):
            label = self.request("GET", "/api/undo")[1]["label"]
            self.assertEqual(self.request("POST", "/api/undo", {"label": label})[0], 200)
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)
        self.assertIn("**EXM-011**", self.register.read_text(encoding="utf-8"))
        self.assertNotIn("**EXM-012**", self.register.read_text(encoding="utf-8"))
        self.assertNotEqual(self.raw(), original)

    DELETE_REGISTER = ("# Actions\n\n## Open\n- [ ] **EXM-001** — Jane — Première\n    - source: x\n    - 12/10: une note\n        - sous-détail\n\n"
                       "    - 13/10: après un blanc interne\n- [ ] **EXM-002** — Jane — Voisine\n    - source: y\n\n## Done\n- [x] **EXM-009** — Jane — Ancienne\n")

    def delete_payload(self, action_id="EXM-001"):
        action = next(item for item in self.request("GET", "/api/actions")[1]["actions"] if item["id"] == action_id)
        return {"version": action["version"], "details_version": self.request("GET", f"/api/actions/{action_id}/details")[1]["details_version"]}

    def test_delete_action_removes_whole_block_and_keeps_neighbours(self):
        self.register.write_text(self.DELETE_REGISTER, encoding="utf-8")
        status, result = self.request("DELETE", "/api/actions/EXM-001", self.delete_payload())
        self.assertEqual((status, result["deleted"]), (200, "EXM-001"))
        self.assertEqual(result["undo"]["label"], "deletion of EXM-001")
        self.assertEqual(self.raw().decode("utf-8"), "# Actions\n\n## Open\n- [ ] **EXM-002** — Jane — Voisine\n    - source: y\n\n## Done\n- [x] **EXM-009** — Jane — Ancienne\n")
        self.assertEqual(self.request("GET", "/api/actions/EXM-001/details")[0], 404)

    def test_delete_last_open_action_keeps_single_blank_before_next_heading(self):
        self.register.write_text(self.DELETE_REGISTER, encoding="utf-8")
        status, _ = self.request("DELETE", "/api/actions/EXM-002", self.delete_payload("EXM-002"))
        self.assertEqual(status, 200)
        text = self.raw().decode("utf-8")
        self.assertIn("après un blanc interne\n\n## Done\n", text)
        self.assertNotIn("\n\n\n", text)
        self.assertTrue(text.endswith("Ancienne\n"))
        self.register.write_text(RICH_REGISTER, encoding="utf-8")
        self.assertEqual(self.request("DELETE", "/api/actions/EXM-009", self.delete_payload("EXM-009"))[0], 200)
        self.assertEqual(self.raw().decode("utf-8"), RICH_REGISTER.split("- [x]")[0].rstrip("\n") + "\n")

    def test_delete_action_rejects_stale_versions_and_unprotected_requests(self):
        self.register.write_text(self.DELETE_REGISTER, encoding="utf-8")
        before = self.raw()
        good = self.delete_payload()
        self.assertEqual(self.request("DELETE", "/api/actions/EXM-001", {**good, "version": "stale"})[0], 409)
        self.assertEqual(self.request("DELETE", "/api/actions/EXM-001", {**good, "details_version": "stale"})[0], 409)
        self.assertEqual(self.request("DELETE", "/api/actions/EXM-001", {"version": good["version"]})[0], 400)
        self.assertEqual(self.request("DELETE", "/api/actions/EXM-001", good, token=False)[0], 403)
        self.assertEqual(self.request("DELETE", "/api/actions/EXM-001", good, origin=False)[0], 403)
        self.assertEqual(self.request("DELETE", "/api/actions/EXM-999", good)[0], 404)
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.request("GET", "/api/undo")[1]["depth"], 0)

    def test_undo_action_deletion_restores_exact_bytes(self):
        self.register.write_text(self.DELETE_REGISTER, encoding="utf-8")
        original = self.raw()
        self.request("DELETE", "/api/actions/EXM-001", self.delete_payload())
        self.assertEqual(self.request("GET", "/api/undo")[1]["label"], "deletion of EXM-001")
        status, _ = self.request("POST", "/api/undo", {"label": "deletion of EXM-001"})
        self.assertEqual(status, 200)
        self.assertEqual(self.raw(), original)

    def test_shutdown_requires_local_token_and_origin(self):
        status, _ = self.request("POST", "/api/shutdown", {}, token=False)
        self.assertEqual(status, 403)
        status, _ = self.request("POST", "/api/shutdown", {}, origin=False)
        self.assertEqual(status, 403)
        status, result = self.request("POST", "/api/shutdown", {})
        self.assertEqual(status, 200)
        self.assertTrue(result["stopping"])
        self.thread.join(timeout=2)
        self.assertFalse(self.thread.is_alive())

    def test_does_not_serve_arbitrary_paths(self):
        status, _ = self.request("GET", "/../../brain/.data/doctor.json")
        self.assertEqual(status, 404)


class NotesTest(unittest.TestCase):
    CLIENT = "projects/clients/acme/missions/demo-migration"
    INTERNAL = "projects/internal/setup"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.brain = root / "brain"
        self.outside = root / "outside.md"
        self.outside.write_text("# Secret\n\nhors du brain\n", encoding="utf-8")
        client = self.brain / self.CLIENT
        internal = self.brain / self.INTERNAL
        for folder, line in ((client, "- [ ] **ACM-001** — Jane — Livrer"), (internal, "- [ ] **SET-001** — Jane — Ranger")):
            (folder / "state").mkdir(parents=True)
            (folder / "state/actions.md").write_text(f"# Actions\n\n## Open\n{line}\n", encoding="utf-8")
        (client / "demo-migration.md").write_text("# Migration Demo\n", encoding="utf-8")
        (client / "notes/archive").mkdir(parents=True)
        (client / "notes/archive/2026-01-01-ancienne.md").write_text("# Archivée\n", encoding="utf-8")
        (client / "notes/2026-10-01-existante.md").write_text(
            "# Note existante\n\n> Note from 01/10/2026 · project: [x](../demo-migration.md)\n\nContenu de la\n  note   existante.\n", encoding="utf-8")
        (client / "notes/README.md").write_text("# Index\n", encoding="utf-8")
        (client / "notes/lien.md").symlink_to(self.outside)
        (internal / "notes").mkdir()
        self.undated = internal / "notes/sans-date.md"
        self.undated.write_text("Pas de titre ici, juste du texte.\n", encoding="utf-8")
        os.utime(self.undated, (1786795200, 1786795200))  # 2026-08-15 12:00 UTC
        # A leftover root notes/ folder is never scanned: every note belongs to a project.
        (self.brain / "notes/2026-09-30-sujet-libre").mkdir(parents=True)
        (self.brain / "notes/2026-09-30-sujet-libre/sujet-libre.md").write_text("# Sujet libre\n\nCorps du sujet.\n", encoding="utf-8")
        self.today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        self.server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(self.brain))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.register = f"{self.CLIENT}/state/actions.md"
        self.internal_register = f"{self.INTERNAL}/state/actions.md"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    request = TasksWebTest.request

    def create(self, title="Ma note", register=None, content="Texte"):
        return self.request("POST", "/api/notes", {"title": title, "register": register, "content": content})

    def undo(self):
        _, state = self.request("GET", "/api/undo")
        return self.request("POST", "/api/undo", {"label": state["label"]})

    def test_listing_fields_and_exclusions(self):
        status, data = self.request("GET", "/api/notes")
        self.assertEqual(status, 200)
        by_id = {note["id"]: note for note in data["notes"]}
        self.assertEqual(set(by_id), {
            f"{self.CLIENT}/notes/2026-10-01-existante.md", f"{self.INTERNAL}/notes/sans-date.md",
        })
        existing = by_id[f"{self.CLIENT}/notes/2026-10-01-existante.md"]
        self.assertEqual((existing["title"], existing["project"], existing["register"], existing["date"]),
                         ("Note existante", "acme / demo-migration", self.register, "2026-10-01"))
        self.assertEqual(existing["excerpt"], "Contenu de la note existante.")
        self.assertEqual(existing["size"], (self.brain / self.CLIENT / "notes/2026-10-01-existante.md").stat().st_size)
        self.assertRegex(existing["modified"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
        undated = by_id[f"{self.INTERNAL}/notes/sans-date.md"]
        self.assertEqual((undated["title"], undated["project"], undated["register"], undated["date"]), ("sans-date", "setup", self.internal_register, "2026-08-15"))
        self.assertEqual(undated["excerpt"], "Pas de titre ici, juste du texte.")
        self.assertEqual([note["date"] for note in data["notes"]], sorted((note["date"] for note in data["notes"]), reverse=True))

    def test_long_excerpt_is_clipped(self):
        (self.brain / self.CLIENT / "notes/2026-10-01-existante.md").write_text("# T\n\n" + "mot " * 200, encoding="utf-8")
        note = next(item for item in self.request("GET", "/api/notes")[1]["notes"] if item["title"] == "T")
        self.assertLessEqual(len(note["excerpt"]), 161)
        self.assertTrue(note["excerpt"].endswith("…"))

    def test_content_by_id_and_unknown_ids(self):
        note_id = f"{self.CLIENT}/notes/2026-10-01-existante.md"
        status, data = self.request("GET", "/api/notes/content?id=" + note_id)
        self.assertEqual(status, 200)
        raw = (self.brain / note_id).read_bytes()
        self.assertEqual(data["content"], raw.decode())
        self.assertEqual((data["id"], data["title"], data["project"], data["register"]), (note_id, "Note existante", "acme / demo-migration", self.register))
        self.assertEqual(data["version"], hashlib.sha256(raw).hexdigest()[:16])
        for bad in ("../outside.md", "notes/../../outside.md", f"{self.CLIENT}/notes/lien.md", "notes/2026-09-30-sujet-libre/sujet-libre.md", f"{self.CLIENT}/notes/archive/2026-01-01-ancienne.md", f"{self.CLIENT}/state/actions.md",
                    f"{self.CLIENT}/notes/README.md", "/etc/passwd", "notes/%2e%2e/x.md", ""):
            self.assertEqual(self.request("GET", "/api/notes/content?id=" + bad.replace("%", "%25"))[0], 404, bad)
        self.assertEqual(self.request("GET", "/api/notes/content")[0], 400)
        self.assertEqual(self.request("GET", "/api/notes/content?id=a&id=b")[0], 400)

    def test_create_project_note_with_page_link(self):
        status, data = self.create("Réunion d'équipe — Été", self.register, "Ligne 1\r\nLigne 2")
        self.assertEqual(status, 201)
        relative = f"{self.CLIENT}/notes/{self.today}-reunion-d-equipe-ete.md"
        self.assertEqual(data["id"], relative)
        path = self.brain / relative
        day = f"{self.today[8:10]}/{self.today[5:7]}/{self.today[:4]}"
        self.assertEqual(path.read_text(encoding="utf-8"),
                         f"# Réunion d'équipe — Été\n\n> Note from {day} · project: [acme / demo-migration](../demo-migration.md)\n\nLigne 1\nLigne 2\n")
        self.assertTrue((path.parent / "../demo-migration.md").resolve().is_file())
        self.assertEqual((data["note"]["id"], data["note"]["title"], data["note"]["register"]), (relative, "Réunion d'équipe — Été", self.register))
        self.assertEqual(data["note"]["content"], path.read_text(encoding="utf-8"))
        self.assertTrue(data["undo"]["available"])
        self.assertEqual(data["undo"]["label"], "note \"Réunion d'équipe — Été\" created")
        self.assertIn(relative, {note["id"] for note in self.request("GET", "/api/notes")[1]["notes"]})

    def test_create_project_note_without_page_links_to_register_and_makes_folder(self):
        folder = self.brain / "projects/internal/neuf"
        (folder / "state").mkdir(parents=True)
        (folder / "state/actions.md").write_text("# Actions\n\n## Open\n- [ ] **NEU-001** — Jane — Un\n", encoding="utf-8")
        status, data = self.create("Idée", "projects/internal/neuf/state/actions.md", "")
        self.assertEqual(status, 201)
        path = self.brain / data["id"]
        self.assertEqual(path.parent, folder / "notes")
        text = path.read_text(encoding="utf-8")
        self.assertIn("[neuf (register)](../state/actions.md)", text)
        self.assertTrue(text.endswith("(register)](../state/actions.md)\n"))
        self.assertTrue((path.parent / "../state/actions.md").resolve().is_file())
        status, data = self.create("Idée interne", self.internal_register, "x")
        self.assertIn("[setup (register)](../state/actions.md)", (self.brain / data["id"]).read_text(encoding="utf-8"))

    def test_create_requires_a_known_register(self):
        self.assertEqual(self.request("POST", "/api/notes", {"title": "Sans projet", "register": None, "content": "x"})[0], 400)
        self.assertEqual(self.request("POST", "/api/notes", {"title": "Sans projet", "content": "x"})[0], 400)
        self.assertEqual(self.request("POST", "/api/notes", {"title": "Sans projet", "register": "", "content": "x"})[0], 400)
        self.assertEqual(sorted(path.name for path in (self.brain / "notes").iterdir()), ["2026-09-30-sujet-libre"])

    def test_slug_collisions_and_fallback(self):
        first = self.create("Même titre", self.register)[1]["id"]
        second = self.create("Même titre", self.register)[1]["id"]
        third = self.create("Même titre", self.register)[1]["id"]
        stem = f"{self.CLIENT}/notes/{self.today}-meme-titre"
        self.assertEqual([first, second, third], [f"{stem}.md", f"{stem}-2.md", f"{stem}-3.md"])
        self.assertIn("Texte", (self.brain / first).read_text(encoding="utf-8"))
        self.assertEqual(self.create("Œuvre ÀÉÎ", self.register)[1]["id"], f"{self.CLIENT}/notes/{self.today}-oeuvre-aei.md")
        self.assertEqual(self.create("!!! ???", self.register)[1]["id"], f"{self.CLIENT}/notes/{self.today}-note.md")
        long_id = self.create("Très " * 30, self.register)[1]["id"]
        slug = Path(long_id).stem[len(self.today) + 1:]
        self.assertTrue(0 < len(slug) <= 60 and not slug.endswith("-"), slug)

    def test_rejects_invalid_notes(self):
        for payload in (
            {"title": "", "register": self.register, "content": "x"}, {"title": "  ", "register": self.register, "content": "x"}, {"title": "a\nb", "register": self.register, "content": "x"},
            {"title": "a\x00b", "register": self.register, "content": "x"}, {"title": "a" * 151, "register": self.register, "content": "x"}, {"title": 3, "register": self.register, "content": "x"},
            {"title": "ok", "register": "projects/inconnu/state/actions.md", "content": "x"}, {"title": "ok", "register": 5, "content": "x"},
            {"title": "ok", "register": "../outside.md", "content": "x"}, {"title": "ok", "register": self.register, "content": 7},
            {"title": "ok", "register": self.register, "content": "a\x00b"}, {"title": "ok", "register": None, "content": "x"},
            {"title": "ok", "register": self.register}, {"title": "ok", "register": self.register, "content": "x", "extra": 1},
        ):
            self.assertEqual(self.request("POST", "/api/notes", payload)[0], 400, payload)
        self.assertEqual(self.create("ok", self.register, "x" * 102399)[0], 201)
        self.assertEqual(self.create("ok", self.register, "x" * 102400)[0], 400)
        request = Request(self.base + "/api/notes", data=b'{"title":"' + b"a" * 140000 + b'"}', method="POST",
                          headers={"Content-Type": "application/json", "X-Tasks-Token": self.server.token, "Origin": self.base})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        caught.exception.close()
        self.assertEqual(caught.exception.code, 413)
        self.assertEqual(len(list((self.brain / self.CLIENT / "notes").glob(f"{self.today}-*"))), 1)

    def test_note_writes_are_protected(self):
        payload = {"title": "Non", "register": self.register, "content": "x"}
        self.assertEqual(self.request("POST", "/api/notes", payload, token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/notes", payload, origin=False)[0], 403)
        note_id = f"{self.CLIENT}/notes/2026-10-01-existante.md"
        patch_payload = {"id": note_id, "version": "x", "content": "y"}
        self.assertEqual(self.request("PATCH", "/api/notes", patch_payload, token=False)[0], 403)
        self.assertEqual(self.request("PATCH", "/api/notes", patch_payload, origin=False)[0], 403)
        self.assertFalse(list(self.brain.glob(f"notes/{self.today}-*")))

    def test_patch_replaces_whole_file_and_detects_stale_version(self):
        note_id = f"{self.CLIENT}/notes/2026-10-01-existante.md"
        version = self.request("GET", "/api/notes/content?id=" + note_id)[1]["version"]
        status, data = self.request("PATCH", "/api/notes", {"id": note_id, "version": version, "content": "# Nouveau titre\r\n\r\nNouveau corps"})
        self.assertEqual(status, 200)
        self.assertEqual((self.brain / note_id).read_text(encoding="utf-8"), "# Nouveau titre\n\nNouveau corps\n")
        self.assertEqual(data["id"], note_id)
        self.assertEqual(data["version"], hashlib.sha256((self.brain / note_id).read_bytes()).hexdigest()[:16])
        self.assertEqual(data["undo"]["label"], 'note "Nouveau titre" edited')
        status, stale = self.request("PATCH", "/api/notes", {"id": note_id, "version": version, "content": "# Autre\n"})
        self.assertEqual(status, 409)
        self.assertIn("changed", stale["error"])
        self.assertEqual((self.brain / note_id).read_text(encoding="utf-8"), "# Nouveau titre\n\nNouveau corps\n")
        for payload in ({"id": note_id, "version": data["version"], "content": "   \n"}, {"id": note_id, "version": data["version"], "content": "x" * 102401},
                        {"id": note_id, "version": data["version"], "content": "a\x00"}, {"id": note_id, "version": data["version"]},
                        {"id": note_id, "version": 5, "content": "x"}, {"id": note_id, "version": data["version"], "content": "x", "title": "t"}):
            self.assertEqual(self.request("PATCH", "/api/notes", payload)[0], 400, payload)
        for bad in ("../outside.md", f"{self.CLIENT}/notes/lien.md", "notes/archive/2026-01-01-vieux/vieux.md", f"{self.CLIENT}/state/actions.md", "nope"):
            self.assertEqual(self.request("PATCH", "/api/notes", {"id": bad, "version": "x", "content": "y"})[0], 404, bad)
        self.assertEqual(self.outside.read_text(encoding="utf-8"), "# Secret\n\nhors du brain\n")
        depth = self.request("GET", "/api/undo")[1]["depth"]
        status, same = self.request("PATCH", "/api/notes", {"id": note_id, "version": data["version"], "content": "# Nouveau titre\n\nNouveau corps\n"})
        self.assertEqual((status, same["version"], same["undo"]["depth"]), (200, data["version"], depth))

    def test_undo_create_removes_file_and_dirs_created_by_the_write(self):
        project = self.brain / "projects/internal/neuf"
        (project / "state").mkdir(parents=True)
        (project / "state/actions.md").write_text("- [ ] **NEU-001** — Jane — Un\n", encoding="utf-8")
        data = self.create("Projet sans notes", "projects/internal/neuf/state/actions.md")[1]
        self.assertTrue((project / "notes").is_dir())
        status, result = self.undo()
        self.assertEqual((status, result["undone"]), (200, 'note "Projet sans notes" created'))
        self.assertFalse((project / "notes").exists())
        self.assertTrue((project / "state").is_dir())
        self.assertFalse(result["undo"]["available"])
        data = self.create("Dans un dossier existant", self.register)[1]
        self.assertEqual(self.undo()[0], 200)
        self.assertFalse((self.brain / data["id"]).exists())
        self.assertTrue((self.brain / self.CLIENT / "notes").is_dir())
        self.assertTrue((self.brain / self.CLIENT / "notes/2026-10-01-existante.md").is_file())

    def test_undo_create_keeps_notes_folder_with_other_files(self):
        project = self.brain / "projects/internal/neuf"
        (project / "state").mkdir(parents=True)
        (project / "state/actions.md").write_text("- [ ] **NEU-001** — Jane — Un\n", encoding="utf-8")
        data = self.create("Avec voisin", "projects/internal/neuf/state/actions.md")[1]
        folder = (self.brain / data["id"]).parent
        (folder / "piece-jointe.txt").write_text("garder", encoding="utf-8")
        self.assertEqual(self.undo()[0], 200)
        self.assertFalse((self.brain / data["id"]).exists())
        self.assertEqual((folder / "piece-jointe.txt").read_text(encoding="utf-8"), "garder")

    def test_create_inbox_note_with_to_sort_header_and_collision_suffix(self):
        self.assertFalse((self.brain / "inbox").exists())
        status, data = self.create("Idée à creuser", "inbox", "Ligne 1\r\nLigne 2")
        self.assertEqual(status, 201)
        relative = f"inbox/{self.today}-idee-a-creuser.md"
        self.assertEqual(data["id"], relative)
        day = f"{self.today[8:10]}/{self.today[5:7]}/{self.today[:4]}"
        self.assertEqual((self.brain / relative).read_text(encoding="utf-8"), f"# Idée à creuser\n\n> Note from {day} · to triage\n\nLigne 1\nLigne 2\n")
        self.assertEqual((data["note"]["project"], data["note"]["register"], data["undo"]["label"]), ("Inbox", "inbox", 'note "Idée à creuser" created'))
        self.assertEqual(self.create("Idée à creuser", "inbox")[1]["id"], f"inbox/{self.today}-idee-a-creuser-2.md")
        self.assertEqual(self.create("Idée à creuser", "inbox")[1]["id"], f"inbox/{self.today}-idee-a-creuser-3.md")
        self.assertEqual((self.brain / f"inbox/{self.today}-idee-a-creuser-2.md").read_text(encoding="utf-8").splitlines()[2:], [f"> Note from {day} · to triage", "", "Texte"])
        listed = {note["id"]: note for note in self.request("GET", "/api/notes")[1]["notes"]}
        self.assertEqual((listed[relative]["project"], listed[relative]["register"], listed[relative]["date"]), ("Inbox", "inbox", self.today))
        self.assertEqual(self.create("", "inbox")[0], 400)
        self.assertEqual(self.create("ok", "inbox", "x" * 102400)[0], 400)
        self.assertEqual(self.request("POST", "/api/notes", {"title": "Non", "register": "inbox", "content": "x"}, token=False)[0], 403)
        self.assertEqual(self.request("POST", "/api/notes", {"title": "Non", "register": "inbox", "content": "x"}, origin=False)[0], 403)
        self.assertEqual(len(list((self.brain / "inbox").iterdir())), 3)

    def test_inbox_readme_is_neither_listed_nor_editable_but_notes_are(self):
        inbox = self.brain / "inbox"
        inbox.mkdir()
        (inbox / "README.md").write_text("# Inbox\n\nMode d'emploi.\n", encoding="utf-8")
        (inbox / "inbox.md").write_text("# Inbox\n\n---\n- une ligne à trier\n", encoding="utf-8")  # the scratchpad, not a note
        (inbox / "2026-10-02-brute.md").write_text("# Brute\n\nÀ trier.\n", encoding="utf-8")
        (inbox / "lien.md").symlink_to(self.outside)
        listed = {note["id"]: note for note in self.request("GET", "/api/notes")[1]["notes"]}
        self.assertIn("inbox/2026-10-02-brute.md", listed)
        self.assertEqual({key for key in listed if key.startswith("inbox/")}, {"inbox/2026-10-02-brute.md"})
        self.assertEqual((listed["inbox/2026-10-02-brute.md"]["project"], listed["inbox/2026-10-02-brute.md"]["register"]), ("Inbox", "inbox"))
        self.assertEqual(self.request("GET", "/api/notes/content?id=inbox/README.md")[0], 404)
        self.assertEqual(self.request("GET", "/api/notes/content?id=inbox/inbox.md")[0], 404)
        self.assertEqual(self.request("PATCH", "/api/notes", {"id": "inbox/README.md", "version": "x", "content": "y"})[0], 404)
        self.assertEqual(self.request("PATCH", "/api/notes", {"id": "inbox/lien.md", "version": "x", "content": "y"})[0], 404)
        version = self.request("GET", "/api/notes/content?id=inbox/2026-10-02-brute.md")[1]["version"]
        self.assertEqual(self.request("PATCH", "/api/notes", {"id": "inbox/2026-10-02-brute.md", "version": version, "content": "# Triée\n"})[0], 200)
        self.assertEqual((inbox / "2026-10-02-brute.md").read_text(encoding="utf-8"), "# Triée\n")
        self.assertEqual(self.create("README", "inbox")[1]["id"], f"inbox/{self.today}-readme.md")
        self.assertEqual((inbox / "README.md").read_text(encoding="utf-8"), "# Inbox\n\nMode d'emploi.\n")
        status, rendered = self.request("GET", "/api/docs/render?id=inbox/2026-10-02-brute.md")
        self.assertEqual((status, rendered["project"], rendered["note"]), (200, "Inbox", True))
        self.assertFalse(self.request("GET", "/api/docs/render?id=inbox/README.md")[1]["note"])
        results = self.request("GET", "/api/search?q=emploi&project=inbox")[1]["results"]
        self.assertEqual([(item["id"], item["project"], item["register"]) for item in results], [("inbox/README.md", "Inbox", "inbox")])
        self.assertEqual(self.request("GET", "/api/search?q=emploi&project=none")[1]["results"], [])

    def test_undo_create_inbox_note_removes_the_folder_only_if_the_write_created_it(self):
        data = self.create("Dans l'inbox", "inbox")[1]
        self.assertTrue((self.brain / "inbox").is_dir())
        status, result = self.undo()
        self.assertEqual((status, result["undone"]), (200, "note \"Dans l'inbox\" created"))
        self.assertFalse((self.brain / data["id"]).exists())
        self.assertFalse((self.brain / "inbox").exists())
        (self.brain / "inbox").mkdir()
        (self.brain / "inbox/README.md").write_text("# Inbox\n", encoding="utf-8")
        data = self.create("Avec README", "inbox")[1]
        self.assertEqual(self.undo()[0], 200)
        self.assertFalse((self.brain / data["id"]).exists())
        self.assertEqual((self.brain / "inbox/README.md").read_text(encoding="utf-8"), "# Inbox\n")

    def test_undo_edit_restores_exact_bytes(self):
        note_id = f"{self.CLIENT}/notes/2026-10-01-existante.md"
        path = self.brain / note_id
        path.write_bytes(b"# Titre\r\n\r\nSans retour final")
        original = path.read_bytes()
        version = self.request("GET", "/api/notes/content?id=" + note_id)[1]["version"]
        self.assertEqual(self.request("PATCH", "/api/notes", {"id": note_id, "version": version, "content": "# Titre\n\nChangé"})[0], 200)
        self.assertNotEqual(path.read_bytes(), original)
        status, result = self.undo()
        self.assertEqual((status, result["undone"]), (200, 'note "Titre" edited'))
        self.assertEqual(path.read_bytes(), original)

    def test_undo_is_refused_when_the_note_changed_meanwhile(self):
        data = self.create("Fragile", self.register)[1]
        path = self.brain / data["id"]
        path.write_text("modifiée ailleurs\n", encoding="utf-8")
        status, result = self.undo()
        self.assertEqual(status, 409)
        self.assertIn("note", result["error"].lower())
        self.assertEqual(path.read_text(encoding="utf-8"), "modifiée ailleurs\n")
        self.assertFalse(self.request("GET", "/api/undo")[1]["available"])
        note_id = f"{self.CLIENT}/notes/2026-10-01-existante.md"
        version = self.request("GET", "/api/notes/content?id=" + note_id)[1]["version"]
        self.request("PATCH", "/api/notes", {"id": note_id, "version": version, "content": "# A\n"})
        (self.brain / note_id).unlink()
        self.assertEqual(self.undo()[0], 409)
        self.assertFalse((self.brain / note_id).exists())

    def test_note_undo_labels_are_truncated_and_stack_is_lifo_with_actions(self):
        long_title = "T" * 60
        self.create(long_title, self.register)
        self.assertEqual(self.request("GET", "/api/undo")[1]["label"], f"note \"{'T' * 40}…\" created")
        status, _ = self.request("POST", "/api/actions", {"register": self.register, "action": {"title": "Nouveau", "owner": "Jane", "state": " ", "priority": "", "due": "", "scheduled": ""}})
        self.assertEqual(status, 201)
        self.assertEqual(self.undo()[0], 200)
        self.assertEqual(self.request("GET", "/api/undo")[1]["label"], f"note \"{'T' * 40}…\" created")
        self.assertEqual(self.undo()[0], 200)
        self.assertEqual(list((self.brain / self.CLIENT / "notes").glob(f"{self.today}-*")), [])


class WrittenFormatTest(unittest.TestCase):
    """What the interface writes into a brain file: the source of a new action and the header of a new note."""
    ENGLISH = "projects/clients/acme/missions/demo-migration"
    OPEN_EN = "# Actions\n\n## Open\n- [ ] **{prefix}-001** — Jane — Deliver\n\n## Done\n"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)  # last: the servers are stopped first
        self.root = Path(self.temp.name)
        self.today = datetime.now(ZoneInfo("Europe/Paris")).date().isoformat()
        self.day = f"{self.today[8:10]}/{self.today[5:7]}"

    request = TasksWebTest.request

    def make_brain(self, name, registers):
        """registers: project folder -> register text; the ENGLISH project also gets its project page."""
        brain = self.root / name
        for folder, text in registers.items():
            (brain / folder / "state").mkdir(parents=True)
            (brain / folder / "state/actions.md").write_text(text, encoding="utf-8")
        (brain / ".data").mkdir(parents=True, exist_ok=True)
        if self.ENGLISH in registers:
            (brain / self.ENGLISH / "demo-migration.md").write_text("# Demo migration\n", encoding="utf-8")
        return brain

    def serve(self, brain):
        self.server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(brain))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.stop, self.server, thread)
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        return brain

    @staticmethod
    def stop(server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    def new_action(self, folder):
        action = {"title": "Follow up", "owner": "Jane", "state": " ", "priority": "", "due": "", "scheduled": ""}
        return self.request("POST", "/api/actions", {"register": f"{folder}/state/actions.md", "action": action})

    def note(self, title, register):
        return self.request("POST", "/api/notes", {"title": title, "register": register, "content": "Body"})

    def test_action_created_in_an_english_register_has_an_english_source(self):
        brain = self.serve(self.make_brain("brain", {self.ENGLISH: self.OPEN_EN.format(prefix="ACM")}))
        status, result = self.new_action(self.ENGLISH)
        self.assertEqual((status, result["id"], result["undo"]["label"]), (201, "ACM-002", "creation of ACM-002"))
        text = (brain / self.ENGLISH / "state/actions.md").read_text(encoding="utf-8")
        self.assertIn(f"    - source: entered in the local interface, {self.day}\n", text)
        self.assertIn("    - created: ", text)

    def test_project_note_header_is_english_in_an_english_register(self):
        brain = self.serve(self.make_brain("brain", {self.ENGLISH: self.OPEN_EN.format(prefix="ACM"), "projects/internal/neuf": self.OPEN_EN.format(prefix="NEU")}))
        date = f"{self.today[8:10]}/{self.today[5:7]}/{self.today[:4]}"
        status, data = self.note("Kickoff", f"{self.ENGLISH}/state/actions.md")
        self.assertEqual(status, 201)
        self.assertEqual((brain / data["id"]).read_text(encoding="utf-8"),
                         f"# Kickoff\n\n> Note from {date} · project: [acme / demo-migration](../demo-migration.md)\n\nBody\n")
        self.assertEqual(data["undo"]["label"], 'note "Kickoff" created')
        status, data = self.note("Idea", "projects/internal/neuf/state/actions.md")
        self.assertEqual(status, 201)
        text = (brain / data["id"]).read_text(encoding="utf-8")
        self.assertIn("> Note from ", text)
        self.assertTrue(text.split("\n")[2].endswith("project: [neuf (register)](../state/actions.md)"), text)

    def test_inbox_note_header_has_no_project_link(self):
        date = f"{self.today[8:10]}/{self.today[5:7]}/{self.today[:4]}"
        brain = self.serve(self.make_brain("brain", {self.ENGLISH: self.OPEN_EN.format(prefix="ACM")}))
        status, data = self.note("Loose thought", "inbox")
        self.assertEqual(status, 201)
        self.assertEqual((brain / data["id"]).read_text(encoding="utf-8"), f"# Loose thought\n\n> Note from {date} · to triage\n\nBody\n")


def uv_on_hook_path():
    """The Git hooks of the brains run `uv`: they look for it in the usual places."""
    extra = [str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    return shutil.which("uv", path=os.pathsep.join([*extra, os.environ.get("PATH", "")])) is not None


@unittest.skipUnless(uv_on_hook_path(), "uv is required by the Git hooks")
class GitViewTest(unittest.TestCase):
    """The Sync view on a scratch Work: fictitious brains, each with a local bare remote, an upstream and the real hooks.

    Nothing here touches the real Work or its brains: the identity comes from a scratch ~/.gitconfig (includeIf rules
    and boundary files), the remotes are local bare repositories (no SSH) and every hook is the one of tools/machine/hooks.
    """
    NOTES = "projects/clients/acme/missions/rollout/notes"
    REGISTER = "projects/clients/acme/missions/rollout/state/actions.md"
    SETUP = "projects/internal/setup"
    OPEN = "# Actions — rollout\n\n## Open\n- [ ] **ACM-001** — Jane Doe — Prepare the kickoff\n    - source: kickoff\n\n## Done\n\n## Cancelled\n"
    LONG = "# Long note\n\n" + "".join(f"line {number}\n" for number in range(1, 31))
    ACME = {
        REGISTER: OPEN,
        f"{NOTES}/2026-10-01-kickoff.md": "# Kickoff meeting\n\nAgenda one\nAgenda two\n",
        f"{NOTES}/2026-10-02-budget.md": "# Budget\n\nFirst line\n",
        f"{NOTES}/2026-10-03-long.md": LONG,
        f"{SETUP}/state/actions.md": "# Actions — setup\n\n## Open\n\n## Done\n\n## Cancelled\n",
        f"{SETUP}/notes/no-heading.md": "Just text, no heading.\n",
    }
    GLOBEX = {"projects/clients/initech/initech.md": "# Initech\n", "projects/internal/ops/state/actions.md": "# Actions — ops\n\n## Open\n\n## Done\n\n## Cancelled\n"}

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.home, self.work, self.remotes, self.no_hooks = (self.root / name for name in ("home", "Work", "remotes", "no-hooks"))
        for folder in (self.home, self.work, self.remotes, self.no_hooks):
            folder.mkdir()
        (self.work / "tools").symlink_to(REPO / "tools")
        (self.work / "kit").symlink_to(REPO / "kit")
        # A clean Git environment for the test and for the server it runs: only the scratch global config, with includeIf rules and
        # useConfigOnly (no identity without a rule), no optional index refresh, no SSH override, no prompt.
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment.update(GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"), GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0",
                           GIT_OPTIONAL_LOCKS="0", WORK_DIR=str(self.work))
        patcher = patch.dict(os.environ, environment, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        text = "[user]\n    useConfigOnly = true\n"
        for name, boundary in (("brain-acme", "acme"), ("brain-globex", "globex"), ("brain-local", "acme"), ("brain-plain", "acme")):
            text += f'[includeIf "gitdir:{self.work}/{name}/"]\n    path = {self.home}/.gitconfig-{boundary}\n'
            (self.home / f".gitconfig-{boundary}").write_text(f"[user]\n    name = {boundary.title()} Person\n    email = ada@{boundary}.example\n", encoding="utf-8")
        (self.home / ".gitconfig").write_text(text, encoding="utf-8")
        self.acme = self.make_brain("brain-acme", "acme", self.ACME)
        self.globex = self.make_brain("brain-globex", "globex", self.GLOBEX)
        self.server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(self.acme), work=self.work)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(timeout=2)))
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    # --- fixtures

    def git(self, repo, *args, check=True):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
        if check:
            self.assertEqual(result.returncode, 0, f"git {' '.join(args)}: {result.stdout}{result.stderr}")
        return result.stdout

    def commit(self, brain, message="chore: change"):
        """A commit without hooks, for the fixtures only."""
        self.git(brain, "-c", f"core.hooksPath={self.no_hooks}", "add", "-A")
        self.git(brain, "-c", f"core.hooksPath={self.no_hooks}", "commit", "-q", "-m", message)

    def write(self, brain, relative, text):
        path = brain / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def make_brain(self, name, boundary, files, remote=True):
        """A brain created from the seed (hooks installed after its first commit, as bootstrap.sh does), pushed to a local bare remote."""
        result = subprocess.run([sys.executable, str(REPO / "tools/brain/new-brain.py"), name, "--scope", "employer", "--description", "Fictitious brain.",
                                 "--remote", f"*/remotes/{name}.git", "--email", f"*@{boundary}.example"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        brain = self.work / name
        for relative, text in files.items():
            self.write(brain, relative, text)
        self.commit(brain, "chore: seed")
        if remote:
            bare = self.remotes / f"{name}.git"
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
            self.git(brain, "remote", "add", "origin", str(bare))
            self.git(brain, "push", "-q", "-u", "origin", "main")
        for hook, installed in (("brain-pre-commit", "pre-commit"), ("commit-msg", "commit-msg"), ("pre-push", "pre-push")):
            target = brain / ".git/hooks" / installed
            shutil.copy2(REPO / "tools/machine/hooks" / hook, target)
            target.chmod(0o755)
        return brain

    def head(self, brain):
        return self.git(brain, "rev-parse", "HEAD").strip()

    def remote_head(self, name="brain-acme"):
        return subprocess.run(["git", "--git-dir", str(self.remotes / f"{name}.git"), "rev-parse", "refs/heads/main"], capture_output=True, text=True).stdout.strip()

    def other_clone_pushes(self, name="brain-acme"):
        """Another computer adds a commit to the online copy; the brain only learns about it at its next fetch."""
        other = self.root / "other"
        if not other.exists():
            subprocess.run(["git", "clone", "-q", str(self.remotes / f"{name}.git"), str(other)], check=True)
        self.write(other, "elsewhere.md", "# Elsewhere\n")
        self.git(other, "add", "-A")
        self.git(other, "-c", "user.name=Other Person", "-c", "user.email=other@acme.example", "-c", f"core.hooksPath={self.no_hooks}", "commit", "-q", "-m", "chore: elsewhere")
        self.git(other, "push", "-q", "origin", "main")

    def snapshot(self, brain):
        """HEAD, the staged names and the bytes of the index and of every file: what a refused save must leave as it found it."""
        files = {str(path.relative_to(brain)): path.read_bytes() for path in sorted(brain.rglob("*")) if path.is_file() and ".git" not in path.relative_to(brain).parts}
        return {"head": self.head(brain), "staged": self.git(brain, "diff", "--cached", "--name-only"), "index": (brain / ".git/index").read_bytes(), "files": files}

    # --- requests

    def request(self, method, path, payload=None, token=True, origin=True, headers=None):
        headers = dict(headers or {})
        if payload is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["X-Tasks-Token"] = self.server.token
        if origin:
            headers["Origin"] = self.base
        request = Request(self.base + path, data=json.dumps(payload).encode() if payload is not None else None, method=method, headers=headers)
        try:
            with urlopen(request, timeout=120) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def cards(self, query=""):
        status, data = self.request("GET", "/api/git" + query)
        self.assertEqual(status, 200, data)
        return {card["name"]: card for card in data["brains"]}

    def card(self, name="brain-acme"):
        return self.cards()[name]

    def save(self, name="brain-acme", route="save", version=None):
        return self.request("POST", f"/api/git/{route}?brain={name}", {"version": version or self.card(name)["version"]})

    # --- who is listed

    def test_only_the_brains_are_listed_never_work_and_never_a_path(self):
        self.git(self.work, "init", "-q", "-b", "main")
        self.write(self.work, "notes-of-work.md", "# Work file\n")
        before = self.snapshot(self.acme)
        status, data = self.request("GET", "/api/git")
        self.assertEqual(status, 200)
        self.assertEqual([card["name"] for card in data["brains"]], ["brain-acme", "brain-globex"])
        self.assertEqual([card["label"] for card in data["brains"]], ["Acme", "Globex"])
        self.assertNotIn("Work", json.dumps(data))
        self.assertNotIn(str(self.work), json.dumps(data))  # no folder of Work or of a brain (the online copy URLs live elsewhere)
        for value in ("Work", "..", ".", str(self.work), str(self.acme), "brain-acme/..", "../Work", "brain-nope", "", "BRAIN-ACME", "%2e%2e"):
            query = "?brain=" + quote(value, safe="")
            self.assertEqual(self.request("GET", "/api/git" + query), (400, {"error": "Unknown brain."}), value)
            self.assertEqual(self.request("GET", "/api/git/changes" + query + "&path=a.md")[0], 400, value)
            self.assertEqual(self.request("POST", "/api/git/save" + query, {"version": "0" * 32})[0], 400, value)
            self.assertEqual(self.request("POST", "/api/git/send" + query, {"version": "0" * 32})[0], 400, value)
        self.assertEqual(self.request("GET", "/api/git?brain=brain-acme&brain=brain-globex"), (400, {"error": "Invalid brain parameter."}))
        # Work has not been touched: it has no commit, and nothing was written to a brain.
        self.assertEqual(self.git(self.work, "rev-parse", "--verify", "-q", "HEAD", check=False), "")
        self.assertEqual(self.snapshot(self.acme), before)

    def test_the_chosen_brain_comes_first_and_every_other_brain_follows(self):
        self.assertEqual(list(self.cards("?brain=brain-globex")), ["brain-globex", "brain-acme"])
        self.assertEqual(list(self.cards("?brain=brain-acme")), ["brain-acme", "brain-globex"])
        self.assertEqual(list(self.cards()), ["brain-acme", "brain-globex"])
        self.make_brain("brain-local", "acme", {}, remote=False)
        self.assertEqual(list(self.cards("?brain=brain-local")), ["brain-local", "brain-acme", "brain-globex"])

    def test_the_old_repository_routes_are_gone(self):
        for path in ("/api/git/diff?repo=work&path=a.md", f"/api/git/commit?repo=work&hash={'0' * 40}"):
            self.assertEqual(self.request("GET", path)[0], 404, path)

    # --- the sentence of each state

    def test_each_state_has_one_plain_sentence_with_the_last_save(self):
        clean = self.card()
        self.assertEqual((clean["state"], clean["message"], clean["pending"], clean["action"], clean["count"], clean["unsent"]),
                         ("clean", "Everything is saved and sent.", False, None, 0, 0))
        self.assertRegex(clean["last_saved"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertEqual(set(clean), {"name", "label", "state", "message", "pending", "action", "count", "unsent", "changes", "more", "last_saved", "version", "url", "web_url"})
        self.write(self.acme, f"{self.NOTES}/2026-10-01-kickoff.md", "# Kickoff meeting\n\nChanged\n")
        one = self.card()
        self.assertEqual((one["state"], one["message"], one["pending"], one["action"]), ("changes", "1 note changed since the last save.", True, "save"))
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        self.write(self.acme, f"{self.NOTES}/2026-10-05-plan.md", "# Plan\n")
        three = self.card()
        self.assertEqual((three["state"], three["message"], three["count"]), ("changes", "3 notes changed since the last save.", 3))
        self.assertNotEqual(one["version"], three["version"])
        self.commit(self.acme)
        unsent = self.card()
        self.assertEqual((unsent["state"], unsent["message"], unsent["pending"], unsent["action"], unsent["unsent"], unsent["count"]),
                         ("unsent", "Saved on this computer, not sent yet.", True, "send", 1, 0))
        self.assertEqual(self.card("brain-globex")["state"], "clean")

    def test_the_online_copy_is_known_as_of_the_last_fetch_only(self):
        self.other_clone_pushes()
        self.assertEqual(self.card()["state"], "clean")  # no automatic network call: the page does not fetch
        self.git(self.acme, "fetch", "-q", "origin")
        behind = self.card()
        self.assertEqual((behind["state"], behind["message"], behind["action"], behind["pending"]),
                         ("behind", "This brain was changed on another computer. Ask your agent to bring those changes here before saving.", None, False))
        # With notes to save, the brain is behind all the same, and still has something waiting.
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        both = self.card()
        self.assertEqual((both["state"], both["count"], both["action"], both["pending"]), ("behind", 1, None, True))

    def test_saving_is_unavailable_where_it_cannot_be_done_safely(self):
        plain = self.work / "brain-plain"
        (plain / ".data").mkdir(parents=True)
        (plain / "projects").mkdir()
        (plain / "AGENTS.md").write_text("# Brain\n", encoding="utf-8")
        local = self.make_brain("brain-local", "acme", {}, remote=False)
        cases = {
            "brain-plain": "Saving is unavailable here (this brain is not set up for saving): ask your agent to set it up.",
            "brain-local": "Saving is unavailable here (this brain has no online copy yet): ask your agent to connect it.",
        }
        for name, sentence in cases.items():
            card = self.card(name)
            self.assertEqual((card["state"], card["message"], card["action"], card["pending"], card["version"] == ""), ("unavailable", sentence, None, False, name == "brain-plain"), name)
        self.git(self.globex, "checkout", "-q", "--detach")
        self.assertEqual(self.card("brain-globex")["message"], "Saving is unavailable here (this brain is not on its working branch): ask your agent to fix it.")
        self.git(self.globex, "checkout", "-q", "main")
        self.assertEqual(self.card("brain-globex")["state"], "clean")
        (self.globex / ".git/MERGE_HEAD").write_text(self.head(self.globex) + "\n", encoding="utf-8")
        self.assertEqual(self.card("brain-globex")["message"], "Saving is unavailable here (a merge or a rebase is in progress): ask your agent to finish it.")
        (self.globex / ".git/MERGE_HEAD").unlink()
        (self.globex / ".git/rebase-merge").mkdir()
        self.assertEqual(self.card("brain-globex")["state"], "unavailable")
        (self.globex / ".git/rebase-merge").rmdir()
        self.assertEqual(self.card("brain-globex")["state"], "clean")
        # An unreadable repository is one more sentence, never a traceback.
        (local / ".git/HEAD").write_text("garbage\n", encoding="utf-8")
        self.assertIn("(Git could not read this brain)", self.card("brain-local")["message"])
        # What the person is told never carries a command, a branch or a path.
        for card in self.cards().values():
            self.assertNotRegex(card["message"], r"git (add|commit|push)|origin|main|/")

    def test_the_online_copy_url_is_the_push_url_of_the_upstream_remote(self):
        self.assertEqual(self.card()["url"], str(self.remotes / "brain-acme.git"))
        self.assertIsNone(self.card()["web_url"])  # a local path has no web page
        self.assertEqual(self.card("brain-globex")["url"], str(self.remotes / "brain-globex.git"))
        # Another remote becomes the upstream: its URL is shown, not the one of origin.
        backup = self.root / "mirror/remotes/brain-acme.git"  # still inside the boundary the brain declares, so the pre-push check accepts it
        backup.parent.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(backup)], check=True)
        self.git(self.acme, "remote", "add", "backup", str(backup))
        self.git(self.acme, "push", "-q", "backup", "main")
        self.git(self.acme, "config", "branch.main.remote", "backup")
        card = self.card()
        self.assertEqual((card["url"], card["state"]), (str(backup), "clean"))
        # A push URL of its own is the one a push goes to.
        self.git(self.acme, "remote", "set-url", "--push", "backup", str(self.remotes / "pushing.git"))
        self.assertEqual(self.card()["url"], str(self.remotes / "pushing.git"))

    def test_without_an_upstream_the_origin_url_is_shown_and_without_a_remote_there_is_none(self):
        local = self.make_brain("brain-local", "acme", {}, remote=False)
        self.assertEqual((self.card("brain-local")["url"], self.card("brain-local")["web_url"]), ("", None))
        self.git(local, "remote", "add", "origin", str(self.remotes / "somewhere.git"))
        card = self.card("brain-local")
        self.assertEqual((card["state"], card["url"]), ("unavailable", str(self.remotes / "somewhere.git")))
        # A remote that is not origin and is not the upstream is not the online copy.
        self.git(local, "remote", "rename", "origin", "elsewhere")
        self.assertEqual(self.card("brain-local")["url"], "")
        # Not a repository, or one that cannot be read: nothing to show.
        plain = self.work / "brain-plain"
        (plain / ".data").mkdir(parents=True)
        (plain / "projects").mkdir()
        (plain / "AGENTS.md").write_text("# Brain\n", encoding="utf-8")
        self.assertEqual(self.card("brain-plain")["url"], "")
        (local / ".git/HEAD").write_text("garbage\n", encoding="utf-8")
        self.assertEqual(self.card("brain-local")["url"], "")

    def test_credentials_in_the_url_are_never_shown(self):
        cases = {
            "https://jane:secret-token@git.example.test/acme/brain.git": "https://***@git.example.test/acme/brain.git",  # secret-scan: ignore (fictitious URL: tests redaction)
            "https://secret-token@git.example.test/acme/brain.git": "https://***@git.example.test/acme/brain.git",  # secret-scan: ignore (fictitious URL: tests redaction)
            "ssh://git:secret-token@git.example.test/acme/brain.git": "ssh://git@git.example.test/acme/brain.git",  # secret-scan: ignore (fictitious URL: tests redaction)
            "ssh://git:secret-token@git.example.test:2222/acme/brain.git": "ssh://git@git.example.test:2222/acme/brain.git",  # secret-scan: ignore (fictitious URL: tests redaction)
            "ssh://git@git.example.test/acme/brain.git": "ssh://git@git.example.test/acme/brain.git",
            "git@git.example.test:acme/brain.git": "git@git.example.test:acme/brain.git",
            "https://git.example.test/acme/brain.git": "https://git.example.test/acme/brain.git",
        }
        checks = load_script("tools/machine/preflight-push.py", self.work)  # the rule of the push checks, loaded on its own
        for url, shown in cases.items():
            self.git(self.acme, "remote", "set-url", "origin", url)
            data = self.cards()
            self.assertEqual(data["brain-acme"]["url"], shown, url)
            self.assertEqual(data["brain-acme"]["web_url"], "https://git.example.test/acme/brain", url)  # the page of the repository, from the hidden URL
            self.assertEqual(shown, checks.redact(url), url)
            self.assertNotIn("secret-token", json.dumps(data), url)
        # The push URL is the one shown, hidden the same way.
        self.git(self.acme, "remote", "set-url", "--push", "origin", "https://jane:secret-token@push.example.test/acme/brain.git")  # secret-scan: ignore (fictitious URL: tests redaction)
        card = self.card()
        self.assertEqual(card["url"], "https://***@push.example.test/acme/brain.git")
        self.assertEqual(card["web_url"], "https://push.example.test/acme/brain")
        self.assertEqual(tasks_web.git_online_copy(self.acme, "origin"), "https://***@push.example.test/acme/brain.git")

    def test_nothing_unavailable_can_be_saved_or_sent(self):
        plain = self.work / "brain-plain"
        (plain / ".data").mkdir(parents=True)
        (plain / "projects").mkdir()
        (plain / "AGENTS.md").write_text("# Brain\n", encoding="utf-8")
        self.write(plain, "note.md", "# Note\n")
        for route in ("save", "send"):
            status, data = self.request("POST", f"/api/git/{route}?brain=brain-plain", {"version": "0" * 32})
            self.assertEqual(status, 409, route)
            self.assertIn("Saving is unavailable here", data["error"])
        self.assertFalse((plain / ".git").exists())

    # --- the changed notes

    def test_changed_notes_have_a_title_a_project_and_the_change_in_a_word(self):
        a = self.acme
        self.write(a, f"{self.NOTES}/2026-10-01-kickoff.md", "# Kickoff meeting\n\nChanged\n")
        self.write(a, f"{self.NOTES}/2026-10-05-new-ideas.md", "---\ntags: x\n# not a title\n---\n\n```\n# not a title either\n```\n\n# New ideas\n\ntext\n")
        self.write(a, f"{self.SETUP}/notes/plain-text.md", "No heading here.\n")
        (a / f"{self.NOTES}/2026-10-02-budget.md").unlink()
        self.write(a, "inbox/2026-10-06-loose-thought.md", "# Loose thought\n")
        self.write(a, "me/extra-profile.md", "# Extra profile\n")
        self.write(a, self.REGISTER, self.OPEN.replace("Prepare the kickoff", "Prepare the kickoff and the plan"))
        self.write(a, "me/credentials.json", '{"user": "jane"}\n')
        (a / f"{self.SETUP}/notes/no-heading.md").rename(a / f"{self.SETUP}/notes/moved-note.md")
        (a / f"{self.NOTES}/2026-10-03-long.md").write_text(self.LONG.replace("line 3\n", "line three\n"), encoding="utf-8")
        card = self.card()
        by_path = {item["path"]: item for item in card["changes"]}
        self.assertEqual(card["count"], len(card["changes"]), by_path.keys())
        expected = {
            f"{self.NOTES}/2026-10-01-kickoff.md": ("Kickoff meeting", "acme / rollout", "Edited"),
            f"{self.NOTES}/2026-10-05-new-ideas.md": ("New ideas", "acme / rollout", "New"),
            f"{self.SETUP}/notes/plain-text.md": ("plain-text", "setup", "New"),
            f"{self.NOTES}/2026-10-02-budget.md": ("Budget", "acme / rollout", "Deleted"),
            "inbox/2026-10-06-loose-thought.md": ("Loose thought", "Inbox", "New"),
            "me/extra-profile.md": ("Extra profile", "", "New"),
            self.REGISTER: ("Actions — rollout", "acme / rollout", "Edited"),
            "me/credentials.json": ("credentials", "", "New"),
            f"{self.SETUP}/notes/moved-note.md": ("moved-note", "setup", "Renamed"),
            f"{self.NOTES}/2026-10-03-long.md": ("Long note", "acme / rollout", "Edited"),
        }
        self.assertEqual({path: (item["title"], item["project"], item["change"]) for path, item in by_path.items()}, expected)
        self.assertEqual(by_path[f"{self.SETUP}/notes/moved-note.md"]["from"], f"{self.SETUP}/notes/no-heading.md")
        self.assertNotIn(f"{self.SETUP}/notes/no-heading.md", by_path)
        self.assertEqual({path for path, item in by_path.items() if item["hidden"]}, {"me/credentials.json"})
        for item in card["changes"]:
            self.assertEqual(set(item), {"path", "title", "project", "change", "from", "hidden"})
        # In human terms only: no hash, no branch, no line counts.
        text = json.dumps(card)
        self.assertNotRegex(text, r"[0-9a-f]{40}")
        for word in ("main", "origin", "+", "ahead", "behind", "staged"):
            self.assertNotIn(word, [item["title"] for item in card["changes"]])
        self.assertEqual(card["more"], 0)

    def test_a_staged_change_is_listed_once_and_a_deleted_project_keeps_its_name(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-01-kickoff.md", "# Kickoff meeting\n\nStaged\n")
        self.git(self.acme, "add", "-A")
        self.write(self.acme, f"{self.NOTES}/2026-10-01-kickoff.md", "# Kickoff meeting\n\nStaged, then edited\n")
        self.git(self.acme, "mv", f"{self.NOTES}/2026-10-02-budget.md", f"{self.NOTES}/2026-10-02-budget-v2.md")
        shutil.rmtree(self.acme / "projects/internal/setup")
        card = self.card()
        by_path = {item["path"]: (item["title"], item["project"], item["change"]) for item in card["changes"]}
        self.assertEqual(by_path[f"{self.NOTES}/2026-10-01-kickoff.md"], ("Kickoff meeting", "acme / rollout", "Edited"))
        self.assertEqual(by_path[f"{self.NOTES}/2026-10-02-budget-v2.md"], ("Budget", "acme / rollout", "Renamed"))
        # The project folder and its register are gone: the name still comes from the path.
        self.assertEqual(by_path[f"{self.SETUP}/state/actions.md"], ("Actions — setup", "setup", "Deleted"))
        self.assertEqual(by_path[f"{self.SETUP}/notes/no-heading.md"], ("no-heading", "setup", "Deleted"))

    def test_the_list_is_capped_but_the_count_stays_exact(self):
        for number in range(tasks_web.GIT_CHANGE_LIMIT + 5):
            self.write(self.acme, f"inbox/2026-10-07-note-{number:03d}.md", f"# Note {number}\n")
        card = self.card()
        self.assertEqual((card["count"], len(card["changes"]), card["more"]), (tasks_web.GIT_CHANGE_LIMIT + 5, tasks_web.GIT_CHANGE_LIMIT, 5))
        self.assertEqual(card["message"], f"{tasks_web.GIT_CHANGE_LIMIT + 5} notes changed since the last save.")

    def test_listing_never_uses_the_network_nor_writes(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-01-kickoff.md", "# Kickoff meeting\n\nChanged\n")
        calls = []
        real = tasks_web.subprocess.run

        def spy(command, **kwargs):
            calls.append((command, kwargs))
            return real(command, **kwargs)

        before = self.snapshot(self.acme)
        with patch.object(tasks_web.subprocess, "run", side_effect=spy), patch.object(tasks_web, "run_git_write", side_effect=AssertionError("no write")):
            self.card()
            self.request("GET", f"/api/git/changes?brain=brain-acme&path={self.NOTES}/2026-10-01-kickoff.md")
        self.assertTrue(calls)
        forbidden = {"fetch", "pull", "push", "ls-remote", "clone", "commit", "add", "reset", "checkout", "merge", "rebase"}
        for command, kwargs in calls:
            self.assertIsInstance(command, list)
            self.assertFalse(forbidden & set(command[:10]), command)
            if "remote" in command[:10]:
                self.assertEqual(command[command.index("remote") + 1:command.index("remote") + 3], ["get-url", "--push"], command)  # only reads a configured URL
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["timeout"], tasks_web.GIT_READ_TIMEOUT)
            self.assertEqual((kwargs["env"]["GIT_TERMINAL_PROMPT"], kwargs["env"]["GIT_OPTIONAL_LOCKS"]), ("0", "0"))
            self.assertEqual(kwargs["stdin"], tasks_web.subprocess.DEVNULL)
        self.assertEqual(self.snapshot(self.acme), before)

    # --- See changes

    def changes(self, relative, name="brain-acme"):
        status, data = self.request("GET", f"/api/git/changes?brain={name}&path={quote(relative, safe='/')}")
        self.assertEqual(status, 200, data)
        return data

    def test_see_changes_shows_before_and_after_with_the_unchanged_part_collapsed(self):
        long = self.acme / f"{self.NOTES}/2026-10-03-long.md"
        long.write_text(self.LONG.replace("line 15\n", "line 15 edited\n").replace("line 25\n", "line 25 edited\n"), encoding="utf-8")
        data = self.changes(f"{self.NOTES}/2026-10-03-long.md")
        self.assertEqual((data["title"], data["project"], data["change"]), ("Long note", "acme / rollout", "Edited"))
        self.assertEqual(data["blocks"], [
            ["gap", 14], ["ctx", "line 13"], ["ctx", "line 14"], ["del", "line 15"], ["add", "line 15 edited"], ["ctx", "line 16"], ["ctx", "line 17"],
            ["gap", 5], ["ctx", "line 23"], ["ctx", "line 24"], ["del", "line 25"], ["add", "line 25 edited"], ["ctx", "line 26"], ["ctx", "line 27"],
            ["gap", 3],
        ])
        kinds = [block[0] for block in data["blocks"]]
        self.assertEqual(kinds.count("del"), 2)
        self.assertEqual(kinds.count("add"), 2)
        self.assertEqual(kinds[0], "gap")
        self.assertEqual(kinds[-1], "gap")
        # The unchanged lines far from a change are not sent at all, only their number.
        sent = [block[1] for block in data["blocks"] if block[0] != "gap"]
        self.assertNotIn("line 1", sent)
        self.assertNotIn("line 30", sent)
        self.assertEqual(sum(block[1] for block in data["blocks"] if block[0] == "gap") + len(sent) - kinds.count("add"), len(tasks_web.to_lines(self.LONG.encode())))
        # No diff header, no hunk marker, no hash.
        text = json.dumps(data)
        for marker in ("diff --git", "@@", "index ", "--- a/", "+++ b/"):
            self.assertNotIn(marker, text)
        self.assertEqual(set(data), {"path", "title", "project", "change", "hidden", "binary", "too_large", "unchanged", "truncated", "blocks"})

    def test_see_changes_of_a_new_a_deleted_and_a_moved_note(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n\nNone yet.\n")
        self.assertEqual(self.changes(f"{self.NOTES}/2026-10-04-risks.md")["blocks"], [["add", "# Risks"], ["add", ""], ["add", "None yet."]])
        (self.acme / f"{self.NOTES}/2026-10-02-budget.md").unlink()
        deleted = self.changes(f"{self.NOTES}/2026-10-02-budget.md")
        self.assertEqual((deleted["change"], deleted["title"], deleted["blocks"]), ("Deleted", "Budget", [["del", "# Budget"], ["del", ""], ["del", "First line"]]))
        (self.acme / f"{self.SETUP}/notes/no-heading.md").rename(self.acme / f"{self.SETUP}/notes/moved.md")
        moved = self.changes(f"{self.SETUP}/notes/moved.md")
        self.assertEqual((moved["change"], moved["unchanged"], moved["blocks"]), ("Renamed", True, []))
        self.write(self.acme, f"{self.SETUP}/notes/empty.md", "")
        self.assertEqual(self.changes(f"{self.SETUP}/notes/empty.md")["unchanged"], True)

    def test_see_changes_of_a_secret_a_binary_and_a_huge_file(self):
        self.write(self.acme, "me/id_rsa", "TOKEN=abc123\n")
        self.write(self.acme, "me/server.pem", "KEY-MATERIAL\n")
        hidden = self.changes("me/id_rsa")
        self.assertEqual((hidden["hidden"], hidden["blocks"]), (True, []))
        self.assertNotIn("abc123", json.dumps(hidden))
        self.assertNotIn("KEY-MATERIAL", json.dumps(self.changes("me/server.pem")))
        (self.acme / "me/picture.bin").write_bytes(b"\x00\x01\x02")
        binary = self.changes("me/picture.bin")
        self.assertEqual((binary["binary"], binary["blocks"]), (True, []))
        self.write(self.acme, "me/huge.md", "x" * (tasks_web.GIT_COMPARE_LIMIT + 10))
        huge = self.changes("me/huge.md")
        self.assertEqual((huge["too_large"], huge["blocks"]), (True, []))
        self.write(self.acme, "me/many.md", "".join(f"row {number}\n" for number in range(tasks_web.GIT_COMPARE_LINES + 50)))
        many = self.changes("me/many.md")
        self.assertEqual((many["truncated"], len(many["blocks"])), (True, tasks_web.GIT_COMPARE_LINES))

    def test_see_changes_only_answers_for_a_note_that_has_a_change(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        for value in ("../x", "..%2Fbrain-globex%2FAGENTS.md", "%2Fetc%2Fpasswd", "AGENTS.md", "projects", "nothing.md", f"{self.NOTES}/../notes/2026-10-04-risks.md"):
            status, data = self.request("GET", f"/api/git/changes?brain=brain-acme&path={value}")
            self.assertEqual(status, 404, value)
            self.assertIn("error", data)
        self.assertEqual(self.request("GET", "/api/git/changes?brain=brain-acme")[0], 400)
        self.assertEqual(self.request("GET", "/api/git/changes?brain=brain-acme&path=a&path=b")[0], 400)
        # A note of another brain is not a note of this one.
        self.write(self.globex, "projects/internal/ops/notes/ops-note.md", "# Ops\n")
        self.assertEqual(self.request("GET", "/api/git/changes?brain=brain-acme&path=projects/internal/ops/notes/ops-note.md")[0], 404)
        self.assertEqual(self.request("GET", "/api/git/changes?brain=brain-globex&path=projects/internal/ops/notes/ops-note.md")[0], 200)

    def test_a_symbolic_link_is_never_followed(self):
        outside = self.root / "outside.md"
        outside.write_text("# Private\n\nnot for the page\n", encoding="utf-8")
        (self.acme / "me").mkdir(exist_ok=True)
        (self.acme / "me/link.md").symlink_to(outside)
        card = self.card()
        self.assertEqual({item["path"]: item["title"] for item in card["changes"]}, {"me/link.md": "link"})
        status, data = self.request("GET", "/api/git/changes?brain=brain-acme&path=me/link.md")
        self.assertEqual(status, 404)
        self.assertNotIn("Private", json.dumps(data))

    # --- Save and send

    def test_save_and_send_end_to_end(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-01-kickoff.md", "# Kickoff meeting\n\nAgenda changed\n")
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n\nNone yet.\n")
        (self.acme / f"{self.NOTES}/2026-10-02-budget.md").unlink()
        old_head = self.head(self.acme)
        status, result = self.save()
        self.assertEqual(status, 200, result)
        self.assertEqual((result["ok"], result["stage"], result["saved"], result["message"]), (True, "done", True, "Saved and sent."))
        self.assertEqual((result["brain"]["state"], result["brain"]["message"], result["brain"]["count"], result["brain"]["unsent"]), ("clean", "Everything is saved and sent.", 0, 0))
        # The commit exists, was accepted by the hooks, and the online copy has it.
        self.assertNotEqual(self.head(self.acme), old_head)
        self.assertEqual(self.remote_head(), self.head(self.acme))
        message = self.git(self.acme, "log", "-1", "--format=%B")
        subject, _, body = message.strip().partition("\n\n")
        self.assertEqual(subject, "docs: save 3 notes from tasks-web")
        self.assertEqual(body.splitlines(), [f"- edited: {self.NOTES}/2026-10-01-kickoff.md", f"- deleted: {self.NOTES}/2026-10-02-budget.md", f"- new: {self.NOTES}/2026-10-04-risks.md"])
        self.assertNotRegex(message, r"(?i)claude|anthropic|co-authored|generated|noreply")
        self.assertEqual(self.git(self.acme, "log", "-1", "--format=%an <%ae>").strip(), "Acme Person <ada@acme.example>")
        # Every hook ran: the pre-push checks print what they verified, and the commit-msg check would have refused another subject.
        self.assertIn("OK: user.email = ada@acme.example", result["details"])
        self.assertIn("fast-forward (1 commit(s))", result["details"])
        self.assertEqual(self.card()["state"], "clean")
        self.assertEqual(self.card("brain-globex")["state"], "clean")

    def test_one_note_is_saved_with_a_singular_subject(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        status, result = self.save()
        self.assertEqual((status, result["ok"]), (200, True), result)
        self.assertEqual(self.git(self.acme, "log", "-1", "--format=%s").strip(), "docs: save 1 note from tasks-web")

    def test_the_commit_subject_follows_the_conventional_commits_check(self):
        check = load_script("tools/machine/hooks/check-commit-msg.py", self.work)
        for count in (1, 2, 17, 205):
            card = {"count": count, "changes": [{"path": f"inbox/n{n}.md", "from": "", "change": "New"} for n in range(min(count, 60))]}
            subject, body = tasks_web.git_commit_message(card)
            self.assertRegex(subject, check.SUBJECT.pattern)
            self.assertLessEqual(len(subject), 72)
            self.assertFalse(subject.endswith("."))
            self.assertFalse(check.AI_MARKS.search(f"{subject}\n{body}"))
            self.assertLessEqual(len(body.splitlines()), tasks_web.GIT_BODY_LIMIT + 1)
        self.assertTrue(subject.startswith("docs: save 205 notes"))
        self.assertEqual(body.splitlines()[-1], f"- and {205 - tasks_web.GIT_BODY_LIMIT} more")
        _, moved = tasks_web.git_commit_message({"count": 1, "changes": [{"path": "b.md", "from": "a.md", "change": "Renamed"}]})
        self.assertEqual(moved, "- renamed: a.md -> b.md")

    def assertRefusedBeforeCommit(self, result, before, reason):
        self.assertEqual(result["ok"], False)
        self.assertEqual((result["stage"], result["saved"]), ("commit", False))
        self.assertTrue(result["message"].startswith("Not saved: "), result["message"])
        self.assertTrue(result["message"].endswith(". Nothing was changed."), result["message"])
        self.assertIn(reason, result["message"])
        self.assertNotIn("--no-verify", result["message"])
        self.assertTrue(result["details"])  # the raw output stays available, behind "Details"
        self.assertEqual(self.snapshot(self.acme), before)  # HEAD, the index (byte for byte) and every file as they were
        self.assertFalse((self.acme / ".git/index.lock").exists())
        self.assertEqual(self.remote_head(), before["head"])
        self.assertEqual(result["brain"]["state"], "changes")

    def refuse(self, files, reason, staged=None):
        for relative, text in files.items():
            self.write(self.acme, relative, text)
        if staged:
            self.git(self.acme, "add", staged)
        before = self.snapshot(self.acme)
        status, result = self.save()
        self.assertEqual(status, 200, result)
        self.assertRefusedBeforeCommit(result, before, reason)
        if staged:
            self.assertEqual(before["staged"].split(), [staged])
        return result

    def test_a_link_to_a_missing_note_refuses_the_save_and_changes_nothing(self):
        result = self.refuse({f"{self.NOTES}/2026-10-01-kickoff.md": "# Kickoff meeting\n\nSee [the plan](missing-plan.md).\n", f"{self.NOTES}/2026-10-04-risks.md": "# Risks\n"},
                             "a link in “Kickoff meeting” points to a note that does not exist (missing-plan.md)", staged=f"{self.NOTES}/2026-10-04-risks.md")
        self.assertIn("DEAD MD LINK", result["details"])

    def test_a_secret_refuses_the_save_without_showing_it(self):
        token = "ghp_" + "x" * 36
        result = self.refuse({f"{self.NOTES}/2026-10-04-access.md": f"# Access\n\ntoken: {token}\n"}, "“Access” seems to contain a password, a key or a token")
        self.assertNotIn(token, json.dumps(result))

    def test_a_credentials_file_refuses_the_save(self):
        self.refuse({"me/server.pem": "KEY=1\n"}, "“server” looks like a file of credentials")

    def test_a_name_from_another_brain_refuses_the_save(self):
        self.refuse({f"{self.NOTES}/2026-10-04-call.md": "# Call\n\nWe spoke about Initech today.\n"},
                    "“Call” mentions a name that belongs to another brain (initech)")

    def test_a_misfiled_action_refuses_the_save(self):
        misfiled = self.OPEN.replace("- [ ] **ACM-001** — Jane Doe — Prepare the kickoff", "- [x] **ACM-001** — Jane Doe — Prepare the kickoff ✅ 2026-10-20")
        self.refuse({self.REGISTER: misfiled}, "action ACM-001 is not under the section of its status (Done)")

    def test_a_malformed_action_refuses_the_save(self):
        self.refuse({self.REGISTER: self.OPEN.replace("## Done", "- [ ] **ACM-002** no owner and no dash\n\n## Done")},
                    "an action line in “Actions — rollout” is not written the way registers expect")

    def test_a_check_that_takes_too_long_is_stopped_and_changes_nothing(self):
        hook = self.acme / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nsleep 60\n", encoding="utf-8")
        hook.chmod(0o755)
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        before = self.snapshot(self.acme)
        with patch.object(tasks_web, "GIT_COMMIT_TIMEOUT", 1):
            status, result = self.save()
        self.assertEqual(status, 200, result)
        self.assertEqual(result["message"], "Not saved: the checks did not finish in time. Nothing was changed.")
        self.assertEqual(self.snapshot(self.acme), before)

    def test_a_failed_push_keeps_the_commit_and_send_retries_the_push_only(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        bare = self.remotes / "brain-acme.git"
        away = self.remotes / "away.git"
        bare.rename(away)
        status, result = self.save()
        self.assertEqual(status, 200, result)
        self.assertEqual((result["ok"], result["stage"], result["saved"]), (False, "send", True))
        self.assertEqual(result["message"], "Saved on this computer, but not sent: the online copy could not be reached (check the network).")
        self.assertIn("Could not read from remote repository", result["details"])
        self.assertEqual(self.git(self.acme, "log", "-1", "--format=%s").strip(), "docs: save 1 note from tasks-web")
        retry = result["brain"]
        self.assertEqual((retry["state"], retry["message"], retry["action"], retry["count"], retry["unsent"]), ("unsent", "Saved on this computer, not sent yet.", "send", 0, 1))
        # Sending again while the online copy is away fails the same way and commits nothing more.
        head = self.head(self.acme)
        status, again = self.save(route="send")
        self.assertEqual((status, again["ok"], again["stage"]), (200, False, "send"))
        self.assertEqual(self.head(self.acme), head)
        away.rename(bare)
        status, sent = self.request("POST", "/api/git/send?brain=brain-acme", {"version": self.card()["version"]})
        self.assertEqual(status, 200, sent)
        self.assertEqual((sent["ok"], sent["message"], sent["brain"]["state"]), (True, "Saved and sent.", "clean"))
        self.assertEqual(self.remote_head(), head)
        self.assertEqual(self.head(self.acme), head)

    def test_a_push_refused_by_the_identity_checks_is_explained(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        with patch.dict(os.environ, {"GIT_SSH_COMMAND": "ssh -o IdentitiesOnly=yes"}):
            status, result = self.save()
        self.assertEqual(status, 200, result)
        self.assertEqual((result["ok"], result["stage"], result["saved"]), (False, "send", True))
        self.assertEqual(result["message"], "Saved on this computer, but not sent: this computer overrides the connection settings of Git (GIT_SSH_COMMAND): ask your agent to check it.")
        self.assertIn("Push refused", result["details"])
        self.assertNotEqual(self.remote_head(), self.head(self.acme))
        # The brain's own hook did the refusing: nothing was bypassed, and the server never set the variable.
        self.assertEqual(self.card()["state"], "unsent")

    def test_a_brain_that_is_behind_is_refused_and_nothing_is_committed(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        version = self.card()["version"]
        self.other_clone_pushes()
        self.git(self.acme, "fetch", "-q", "origin")
        head = self.head(self.acme)
        for route in ("save", "send"):
            status, data = self.request("POST", f"/api/git/{route}?brain=brain-acme", {"version": self.card()["version"]})
            self.assertEqual(status, 409, route)
            self.assertEqual(data["error"], "This brain was changed on another computer. Ask your agent to bring those changes here before saving.")
        self.assertEqual(self.head(self.acme), head)
        self.assertEqual(self.git(self.acme, "diff", "--cached", "--name-only"), "")
        self.assertNotEqual(version, self.card()["version"])

    def test_the_notes_must_be_the_ones_the_person_confirmed(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        version = self.card()["version"]
        self.write(self.acme, f"{self.NOTES}/2026-10-05-plan.md", "# Plan\n")  # one more note appears after the confirmation was shown
        head = self.head(self.acme)
        status, data = self.save(version=version)
        self.assertEqual((status, data), (409, {"error": tasks_web.GIT_STALE}))
        self.assertEqual(self.head(self.acme), head)
        self.assertEqual(self.git(self.acme, "diff", "--cached", "--name-only"), "")
        # The same note edited again is a change as well.
        version = self.card()["version"]
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n\nA second line\n")
        self.assertEqual(self.save(version=version)[0], 409)
        self.assertNotEqual(self.card()["version"], version)

    def test_nothing_to_do_is_refused(self):
        status, data = self.save()
        self.assertEqual((status, data), (409, {"error": "Everything is already saved and sent."}))
        status, data = self.save(route="send")
        self.assertEqual((status, data), (409, {"error": "Nothing is waiting to be sent."}))
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        self.assertEqual(self.save(route="send"), (409, {"error": "Nothing is waiting to be sent."}))

    def test_a_save_in_progress_blocks_a_second_one(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        version = self.card()["version"]
        self.assertTrue(tasks_web.GIT_LOCK.acquire(blocking=False))
        try:
            status, data = self.save(version=version)
        finally:
            tasks_web.GIT_LOCK.release()
        self.assertEqual((status, data), (409, {"error": "Another save is already running."}))
        self.assertEqual(self.card()["state"], "changes")

    def test_send_pushes_what_is_saved_even_with_notes_still_to_save(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        self.commit(self.acme)
        self.write(self.acme, f"{self.NOTES}/2026-10-05-plan.md", "# Plan\n")
        card = self.card()
        self.assertEqual((card["state"], card["action"], card["unsent"], card["count"]), ("changes", "save", 1, 1))
        head = self.head(self.acme)
        status, sent = self.request("POST", "/api/git/send?brain=brain-acme", {"version": card["version"]})
        self.assertEqual((status, sent["ok"]), (200, True), sent)
        self.assertEqual(self.remote_head(), head)
        self.assertEqual((sent["brain"]["state"], sent["brain"]["count"]), ("changes", 1))  # the new note is still waiting

    def test_save_acts_on_the_named_brain_only(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        self.write(self.globex, "projects/internal/ops/notes/ops-note.md", "# Ops note\n")
        acme_head = self.head(self.acme)
        status, result = self.save("brain-globex")
        self.assertEqual((status, result["ok"], result["brain"]["name"]), (200, True, "brain-globex"), result)
        self.assertEqual(self.remote_head("brain-globex"), self.head(self.globex))
        self.assertEqual(self.head(self.acme), acme_head)
        self.assertEqual(self.card()["state"], "changes")
        self.assertEqual(self.git(self.globex, "log", "-1", "--format=%ae").strip(), "ada@globex.example")

    def test_git_is_run_without_terminal_prompt_ssh_override_or_bypass(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        calls = []
        real = tasks_web.subprocess.Popen

        def spy(command, **kwargs):
            calls.append((command, kwargs))
            return real(command, **kwargs)

        with patch.object(tasks_web.subprocess, "Popen", side_effect=spy):
            status, result = self.save()
        self.assertEqual((status, result["ok"]), (200, True), result)
        git_calls = [(command, kwargs) for command, kwargs in calls if kwargs.get("start_new_session")]  # the writes (the reads have no session of their own)
        arguments = [[part for part in command[1:] if part not in ("--no-pager", "-c", "core.quotepath=false", "color.ui=false")] for command, _ in git_calls]
        self.assertEqual(arguments, [["add", "-A"],
                                     ["commit", "-m", "docs: save 1 note from tasks-web", "-m", f"- new: {self.NOTES}/2026-10-04-risks.md"],
                                     ["push", "--", "origin", "HEAD:refs/heads/main"]])
        for command, kwargs in git_calls:
            self.assertEqual(kwargs["stdin"], tasks_web.subprocess.DEVNULL)
            self.assertTrue(kwargs["start_new_session"])  # no controlling terminal: SSH can never wait for a passphrase
            self.assertEqual(kwargs["cwd"], self.acme)
            environment = kwargs["env"]
            self.assertEqual((environment["GIT_TERMINAL_PROMPT"], environment["GIT_EDITOR"]), ("0", "true"))
            for name in ("GIT_SSH_COMMAND", "GIT_SSH", "SSH_ASKPASS", "GIT_ASKPASS", "DISPLAY"):
                self.assertNotIn(name, environment)
            for option in ("--no-verify", "-n", "--force", "-f", "--force-with-lease", "--amend", "--no-gpg-sign"):
                self.assertNotIn(option, command)
        for limit in (tasks_web.GIT_ADD_TIMEOUT, tasks_web.GIT_COMMIT_TIMEOUT, tasks_web.GIT_PUSH_TIMEOUT):
            self.assertTrue(0 < limit <= 300)

    def test_a_server_environment_with_askpass_or_a_display_is_cleaned_for_git_writes(self):
        calls = []
        real = tasks_web.subprocess.Popen

        def spy(command, **kwargs):
            calls.append(kwargs)
            return real(command, **kwargs)

        with patch.dict(os.environ, {"SSH_ASKPASS": "/usr/bin/x", "SSH_ASKPASS_REQUIRE": "force", "GIT_ASKPASS": "/usr/bin/y", "DISPLAY": ":0"}), \
                patch.object(tasks_web.subprocess, "Popen", side_effect=spy):
            code, output = tasks_web.run_git_write(self.acme, ["status", "--short"], 20)
        self.assertEqual(code, 0, output)
        for name in ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "GIT_ASKPASS", "DISPLAY"):
            self.assertNotIn(name, calls[0]["env"])

    def test_a_command_with_no_end_is_killed_with_its_children(self):
        started = self.root / "started"
        script = self.root / "slow.sh"
        script.write_text(f"#!/bin/sh\ntouch {started}\nsleep 60 &\nwait\n", encoding="utf-8")
        script.chmod(0o755)
        self.git(self.acme, "config", "--local", "alias.slow", f"!{script}")
        begin = datetime.now()
        code, _ = tasks_web.run_git_write(self.acme, ["slow"], 1)
        self.assertEqual(code, 124)
        self.assertTrue(started.exists())
        self.assertLess((datetime.now() - begin).total_seconds(), 15)

    # --- who may ask

    def test_the_write_routes_keep_the_token_the_origin_and_the_localhost_rules(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        version = self.card()["version"]
        head = self.head(self.acme)
        url = "/api/git/save?brain=brain-acme"
        self.assertEqual(self.request("POST", url, {"version": version}, token=False)[0], 403)
        self.assertEqual(self.request("POST", url, {"version": version}, origin=False)[0], 403)
        self.assertEqual(self.request("POST", url, {"version": version}, token=False, headers={"X-Tasks-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("POST", url, {"version": version}, headers={"Origin": "http://evil.example"}, origin=False)[0], 403)
        self.assertEqual(self.request("POST", url, {"version": version}, headers={"Host": "evil.example"})[0], 403)
        request = Request(self.base + url, data=b'{"version": "x"}', method="POST", headers={"Content-Type": "text/plain", "Origin": self.base, "X-Tasks-Token": self.server.token})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 415)
        caught.exception.close()
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.base + "/api/git", headers={"Host": "evil.example"}), timeout=5)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        self.assertEqual(self.head(self.acme), head)
        self.assertEqual(self.git(self.acme, "diff", "--cached", "--name-only"), "")

    def test_the_write_routes_validate_the_request(self):
        self.write(self.acme, f"{self.NOTES}/2026-10-04-risks.md", "# Risks\n")
        version = self.card()["version"]
        for payload in (None, [], {}, {"version": 1}, {"version": "short"}, {"version": version[:-1] + "G"}, {"version": version, "files": ["x"]}, {"version": version, "brain": "brain-globex"},
                        {"version": "z" * 32}):
            status, _ = self.request("POST", "/api/git/save?brain=brain-acme", payload if payload is not None else {})
            self.assertEqual(status, 400, payload)
        self.assertEqual(self.request("POST", "/api/git/save", {"version": version}), (400, {"error": "Unknown brain."}))  # the brain is never implied
        self.assertEqual(self.request("POST", "/api/git/save?brain=brain-acme&brain=brain-globex", {"version": version}), (400, {"error": "Invalid brain parameter."}))
        request = Request(self.base + "/api/git/save?brain=brain-acme", data=b"{not json", method="POST", headers={"Content-Type": "application/json", "Origin": self.base, "X-Tasks-Token": self.server.token})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=5)
        self.assertEqual(caught.exception.code, 400)
        caught.exception.close()
        self.assertEqual(self.request("POST", "/api/git/push?brain=brain-acme", {"version": version})[0], 404)
        self.assertEqual(self.git(self.acme, "diff", "--cached", "--name-only"), "")
        self.assertEqual(self.card()["state"], "changes")

    # --- what a refusal says

    def test_hook_refusals_are_rewritten_in_plain_words(self):
        titles = {"notes/a.md": "Kickoff meeting"}
        reason = tasks_web.git_commit_reason
        links = "files         : 12\nmd links      : 3\ndead (md)     : 1\n\n  ⛔ DEAD MD LINK (missing.md) — 1×\n       notes/a.md\nCommit refused: fix the problems and stage again (or use --no-verify to bypass).\n"
        self.assertEqual(reason(links, 1, titles), "a link in “Kickoff meeting” points to a note that does not exist (missing.md)")
        wiki = "  ⛔ DEAD WIKILINK [[Missing page]] — 2×\n       notes/a.md\n       notes/b.md\n"
        self.assertEqual(reason(wiki, 1, titles), "a link in “Kickoff meeting” points to a note that does not exist (Missing page)")
        cross = "  ⛔ CROSS-BRAIN LINK (../brain-globex/x.md) — 1× (a brain never links to another brain)\n       notes/b.md\n"
        self.assertEqual(reason(cross, 1, titles), "a link in “b” points into another brain")
        secret = "Possible secrets in the index (values not shown):\n  - notes/a.md:7: GitHub token\nRemove the value.\n"
        self.assertEqual(reason(secret, 1, titles), "“Kickoff meeting” seems to contain a password, a key or a token")
        keyfile = "Possible secrets in the index (values not shown):\n  - me/server.pem: credentials file (forbidden name)\n"
        self.assertEqual(reason(keyfile, 1, titles), "“server” looks like a file of credentials")
        other = "Blocked client name of another brain (brain-globex) in notes/a.md: initech\n"
        self.assertEqual(reason(other, 1, titles), "“Kickoff meeting” mentions a name that belongs to another brain (initech)")
        sweep = "projects/x/state/actions.md: sweep ACM-004 Open → Cancelled\nTotal sweep: 1 action(s) to move in 1 register(s)\nMisfiled actions: run `uv run tools/brain/action.py sweep --write` (then stage again).\n"
        self.assertEqual(reason(sweep, 1, titles), "action ACM-004 is not under the section of its status (Cancelled)")
        twice = "ERROR projects/x/state/actions.md:9: ACM-001 already present (projects/x/state/actions.md:3)\nAction check: 1 error(s), 0 warning(s)\n"
        self.assertEqual(reason(twice, 1, titles), "an action number is used twice in “actions”")
        self.assertEqual(reason("ERROR a/state/actions.md:2: ACM-001 invalid ✅ date '2026-13-40'\n", 1, titles), "an action register has a problem (a/state/actions.md:2: ACM-001 invalid ✅ date '2026-13-40')")
        self.assertEqual(reason("", 124, titles), "the checks did not finish in time")
        self.assertEqual(reason("On branch main\nnothing to commit, working tree clean\n", 1, titles), "there was nothing new to save")
        self.assertEqual(reason("Commit refused:\n  - subject does not follow the convention\n", 1, titles), "subject does not follow the convention")
        # Whatever else a hook prints, the person is not told to bypass it, and gets a sentence even from silence.
        self.assertEqual(reason("Commit refused: fix the problems and stage again (or use --no-verify to bypass).\n", 1, titles), "a check of the brain refused it")
        self.assertEqual(reason("", 1, titles), "a check of the brain refused it")
        self.assertEqual(reason("error: something odd happened here.\n", 1, titles), "something odd happened here")

    def test_push_failures_are_rewritten_in_plain_words(self):
        reason = tasks_web.git_push_reason
        self.assertEqual(reason("", 124), "the online copy did not answer in time")
        self.assertEqual(reason("ERROR: GIT_SSH_COMMAND is set in the environment: it overrides core.sshCommand\nSummary: 1 error(s), 0 warning(s).\n", 1),
                         "this computer overrides the connection settings of Git (GIT_SSH_COMMAND): ask your agent to check it")
        self.assertEqual(reason("ERROR: user.email = me@elsewhere.example (from .git/config): local override forbidden\n", 1),
                         "the Git identity of this computer does not match this brain: ask your agent to check it")
        self.assertEqual(reason("ERROR: push URL git@github.com:x/y.git does not match the \"remote\" pattern of brain.json (trust boundary)\n", 1),
                         "the online copy is not the one this brain is declared to use: ask your agent to check it")
        self.assertEqual(reason("ERROR: SSH authentication to github.com failed: permission denied: the key is not accepted\n", 1),
                         "the online copy refused the connection (the SSH key is locked or not accepted)")
        self.assertEqual(reason("git@github.com: Permission denied (publickey).\nfatal: Could not read from remote repository.\n", 128),
                         "the online copy refused the connection (the SSH key is locked or not accepted)")
        self.assertEqual(reason("ERROR: SSH authentication to github.com failed: host name not resolved\n", 1), "the online copy could not be reached (check the network)")
        self.assertEqual(reason("ERROR: SSH authentication to github.com failed: host key not verified\n", 1), "the identity of the online copy could not be verified: ask your agent to check it")
        self.assertEqual(reason("ERROR: refs/heads/main: the remote is ahead by 2 commit(s): fetch and integrate first\n", 1),
                         "the online copy has newer changes: ask your agent to bring them here before sending")
        self.assertEqual(reason(" ! [rejected]        HEAD -> main (fetch first)\nerror: failed to push some refs\n", 1),
                         "the online copy has newer changes: ask your agent to bring them here before sending")
        self.assertEqual(reason("fatal: unable to access 'https://x.example/y.git/': Could not resolve host: x.example\n", 128), "the online copy could not be reached (check the network)")
        self.assertEqual(reason("remote: Something unusual happened.\nfatal: the remote hung up.\n", 128), "the remote hung up")
        self.assertEqual(reason("", 1), "the online copy did not accept the changes")


class GitWebUrlTest(unittest.TestCase):
    """`git_web_url`: the web page of a repository from its Git URL, https only and built from checked parts."""

    def test_each_form_gives_the_https_page_without_user_port_credentials_or_dot_git(self):
        cases = {
            "git@git.example.test:acme/brain.git": "https://git.example.test/acme/brain",
            "git@git.example.test:acme/brain": "https://git.example.test/acme/brain",
            "git.example.test:acme/brain.git": "https://git.example.test/acme/brain",
            "git@git.example.test:group/sub/brain.git": "https://git.example.test/group/sub/brain",
            "ssh://git@git.example.test/acme/brain.git": "https://git.example.test/acme/brain",
            "ssh://git.example.test/acme/brain.git": "https://git.example.test/acme/brain",
            "ssh://git@git.example.test:2222/acme/brain.git": "https://git.example.test/acme/brain",
            "ssh+git://git@git.example.test/acme/brain.git": "https://git.example.test/acme/brain",
            "git+ssh://git@git.example.test/acme/brain.git": "https://git.example.test/acme/brain",
            "ssh://git@git.example.test:2222/group/sub/brain.git/": "https://git.example.test/group/sub/brain",
            "https://git.example.test/acme/brain.git": "https://git.example.test/acme/brain",
            "https://git.example.test/acme/brain": "https://git.example.test/acme/brain",
            "https://git.example.test/acme/brain/": "https://git.example.test/acme/brain",
            "https://***@git.example.test/acme/brain.git": "https://git.example.test/acme/brain",
            "https://jane:secret-token@git.example.test/acme/brain.git": "https://git.example.test/acme/brain",  # secret-scan: ignore (fictitious URL: tests redaction)
            "HTTPS://GIT.EXAMPLE.TEST/acme/Brain.git": "https://git.example.test/acme/Brain",
            "https://git.example.test:8443/acme/brain.git": "https://git.example.test:8443/acme/brain",
            "http://git.example.test/acme/brain.git": "http://git.example.test/acme/brain",
            "https://git.example.test/acme/brain-v2.0_x~y+z.git": "https://git.example.test/acme/brain-v2.0_x~y+z",
            "https://git.example.test/acme/caf%C3%A9.git": "https://git.example.test/acme/caf%C3%A9",
            "https://192.0.2.10/acme/brain.git": "https://192.0.2.10/acme/brain",
            "  https://git.example.test/acme/brain.git  ": "https://git.example.test/acme/brain",
        }
        for url, page in cases.items():
            self.assertEqual(tasks_web.git_web_url(url), page, url)

    def test_local_paths_and_every_other_form_give_nothing(self):
        for url in ("", "   ", "/Users/jane/Work/brain.git", "./brain.git", "../remotes/brain.git", "remotes/brain.git", "C:\\repos\\brain.git", "file:///srv/git/brain.git",
                    "file://git.example.test/acme/brain.git", "git://git.example.test/acme/brain.git", "ftp://git.example.test/acme/brain.git",
                    "ssh://git.example.test", "https://git.example.test", "https://git.example.test/", "https://git.example.test/acme", "https://git.example.test/.git",
                    "https://git.example.test/acme/.git", "git@git.example.test:brain.git", "git@alias:acme/brain.git", "https://localhost/acme/brain.git"):
            self.assertIsNone(tasks_web.git_web_url(url), url)

    def test_hostile_inputs_never_give_a_script_a_query_or_a_foreign_host(self):
        for url in ("javascript:alert(1)", "javascript:alert(1)//acme/brain", "javascript://git.example.test/acme/brain%0aalert(1)", "JaVaScRiPt://git.example.test/acme/brain",
                    "data:text/html,<script>alert(1)</script>", "vbscript:msgbox(1)", "blob:https://git.example.test/acme/brain",
                    "https://git.example.test/acme/brain?x=1", "https://git.example.test/acme/brain#frag", "https://git.example.test/acme/brain.git?service=git-upload-pack",
                    "https://git.example.test/../brain", "https://git.example.test/acme/..", "https://git.example.test/./acme/brain", "https://git.example.test/acme//brain",
                    "https://git.example.test//acme/brain", "https://git.example.test/acme/brain name", "https://git.example.test/acme/<script>", "https://git.example.test/acme/\"onmouseover=x",
                    "https://git.example.test/acme/brain'", "https://git.example.test/acme/brain\\x", "https://git.example.test/acme/brain\x00",
                    "https://git.example.test/acme/brain%0d%0aSet-Cookie:x", "https://git.example.test/acme/brain%00", "https://git.example.test/acme/brain%2f..%2fx",
                    "https://git.example.test/acme/brain%5cx", "https://git.example.test/acme/brain%zz", "https://git.example.test/acme/brain%", "https://git.example.test/acme/%7f",
                    "https://git.example.test\\@evil.example/acme/brain", "https://git.example.test@/acme/brain", "https://[::1]/acme/brain", "https://exa mple.test/acme/brain",
                    "https://git.example.test:abc/acme/brain", "https://git.example.test:0/acme/brain", "https://git.example.test:99999/acme/brain", "ssh://git@git.example.test:abc/acme/brain.git",
                    "https://.example.test/acme/brain", "https://example..test/acme/brain", "https://-example.test/acme/brain", "https://example.test-/acme/brain",
                    "evil.example:../../brain", "git.example.test:acme/../brain", "git@git.example.test:acme/brain?x", "@git.example.test:acme/brain", "git@:acme/brain.git",
                    "https://git.example.test/" + "a/" * 200 + "brain", "https://" + "a" * 300 + ".test/acme/brain", None, 5, b"https://git.example.test/acme/brain"):
            self.assertIsNone(tasks_web.git_web_url(url), url)
        # An address that survives is always http(s), with nothing but a host, an optional port and plain path segments.
        for url in ("https://evil.example@git.example.test/acme/brain.git", "ssh://git@evil.example@git.example.test/acme/brain.git", "https://a:b@c@git.example.test/acme/brain"):
            page = tasks_web.git_web_url(url)
            self.assertRegex(page, r"^https://git\.example\.test/acme/brain$", url)
        # Whitespace around the address is not part of it; the result carries none.
        self.assertEqual(tasks_web.git_web_url("https://git.example.test/acme/brain\n"), "https://git.example.test/acme/brain")


class GitViewPageTest(unittest.TestCase):
    """The Sync view in the page: its markup, its wiring and its style (the behaviour is checked by GitViewTest and in the browser)."""
    STATIC = TOOL.parent / "static"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        brain = Path(self.temp.name) / "brain"
        (brain / "projects").mkdir(parents=True)
        server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(brain), work=Path(self.temp.name))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))
        with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=3) as response:
            self.page = response.read().decode("utf-8")
        self.script = (self.STATIC / "app.js").read_text(encoding="utf-8")
        self.styles = (self.STATIC / "app.css").read_text(encoding="utf-8")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_script_parses(self):
        done = subprocess.run(["node", "--check", str(self.STATIC / "app.js")], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_the_page_has_cards_and_two_dialogs_and_nothing_of_the_old_view(self):
        view = self.page[self.page.index('<div id="gitView"'):self.page.index("</main>")]
        self.assertIn('<div id="gitCards" class="git-cards"></div>', view)
        for old in ("gitRepos", "gitDetail", "gitDiff", "Diff", "commit"):
            self.assertNotIn(old, view)
        for old in ("gitRepos", "gitDetail", "gitDiff", "gitSelected", "GIT_GROUPS", "/api/git/diff", "/api/git/commit", "git-loading", "git-error"):
            self.assertNotIn(old, self.script)
        confirm = self.page[self.page.index('<dialog id="gitConfirmDialog"'):self.page.index('<dialog id="gitChangesDialog"')]
        self.assertIn('aria-labelledby="gitConfirmHeading" aria-describedby="gitConfirmText"', confirm)
        self.assertIn('<ul id="gitConfirmList" class="git-confirm-list"></ul>', confirm)
        self.assertIn('<button class="button" type="submit" value="cancel" autofocus>Cancel</button>', confirm)  # Cancel is the default
        self.assertIn('<button id="gitConfirmGo" class="button button-primary" type="button">Save and send</button>', confirm)
        changes = self.page[self.page.index('<dialog id="gitChangesDialog"'):self.page.index('<dialog id="quitDialog"')]
        for fragment in ('class="dialog dialog-wide"', 'aria-labelledby="gitChangesTitle"', 'id="gitChangesBody"', 'id="gitChangesClose"', 'aria-label="Close"'):
            self.assertIn(fragment, changes)
        self.assertIn('data-view="git"', self.page)
        self.assertIn("Nothing is saved or sent until you click.", self.page)
        self.assertNotIn("Read only", self.page)

    def test_the_view_lists_the_brains_and_never_work(self):
        self.assertIn("await request('/api/git')", self.script)
        self.assertIn("orderedGitCards()", self.script)
        self.assertIn("Number(b.name === currentBrain) - Number(a.name === currentBrain)", self.script)  # the current brain first
        self.assertNotIn("'Work'", self.script)
        self.assertNotIn("Repository", self.script)
        git = re.sub(r"\s//.*", "", self.script[self.script.index("// ---------- Git: save and send"):self.script.index("// ---------- Undo ----------")])  # the code, not its comments
        for word in ("branch", "ahead", "hash", "upstream", "commit", "staged", "diff"):
            self.assertNotIn(word, git)

    def test_the_view_is_called_sync_and_explains_itself_with_an_info_tip(self):
        # The visible name is Sync; the ids and routes keep `git`.
        self.assertIn('<span class="nav-label">Sync</span><span id="gitCount" class="nav-count"></span>', self.page)
        self.assertNotIn('<span class="nav-label">Git</span>', self.page)
        self.assertIn("git: 'Sync'}", self.script)
        self.assertIn("`Sync, ${plural(pending, 'brain')} to save or send` : 'Sync'", self.script)
        self.assertIn("showToast(`Sync: ${error.message}`)", self.script)
        self.assertNotIn("Git: ${", self.script)
        title = self.page[self.page.index('<span id="syncInfo"'):self.page.index('<span id="resultCount"')]
        self.assertIn('class="info info-title" hidden>', title)
        self.assertIn('<button id="syncInfoButton" class="info-button" type="button" aria-label="About Sync" aria-describedby="syncInfoTip">', title)
        self.assertIn('<span id="syncInfoTip" class="info-tip" role="tooltip">', title)
        self.assertIn("Each brain is a Git repository. Save and send records the changed notes and sends them to the brain's online copy.", title)
        self.assertLess(self.page.index('<h1 id="viewTitle">'), self.page.index('<span id="syncInfo"'))
        self.assertIn("ids.syncInfo.hidden = next !== 'git';", self.script)  # only on this view

    def test_each_card_has_an_online_copy_popover_that_is_a_disclosure_with_a_real_link(self):
        info = self.script[self.script.index("function onlineCopyPopover(card)"):self.script.index("// ---------- Git: save and send")]
        # A button that discloses a panel (not a tooltip: a link inside a tooltip cannot be reached).
        for fragment in ("const info = element('span', 'info info-pop');", "const button = element('button', 'info-button');", "button.type = 'button';",
                         "button.setAttribute('aria-label', label);", "button.setAttribute('aria-expanded', 'false');", "button.setAttribute('aria-controls', `${id}Panel`);",
                         "panel.setAttribute('role', 'group');", "button.append(svgIcon(ICONS.info));"):
            self.assertIn(fragment, info)
        self.assertNotIn("tooltip", info)
        self.assertNotIn(".title", info)
        # "Git", then the URL as a link to the page of the repository (new tab, no opener), or plain text, or why there is nothing.
        for fragment in ("element('span', 'info-tip-line info-tip-head', 'Git')", "link.href = card.web_url;", "link.target = '_blank';", "link.rel = 'noopener noreferrer';",
                         "svgIcon(ICONS.open)", "' (opens in a new tab)'", "/^https?:\\/\\//i.test(card.web_url)",
                         "line.textContent = known ? 'No online copy' : 'Restart tasks-web to see the online copy';", "breakableUrl(line, card.url)"):
            self.assertIn(fragment, info)
        self.assertIn("const label = !known ? 'Restart tasks-web to see the online copy' : card.url ? `Online copy: ${card.url}` : 'No online copy';", info)
        self.assertIn("const known = 'url' in card;", info)  # an older server sends no `url` at all
        self.assertIn("head.append(onlineCopyPopover(card));", self.script)
        self.assertNotIn("infoTip(", self.script)
        self.assertIn("if (!Array.isArray(data.brains)) throw new Error('Restart tasks-web: this page is newer than the server that is running.');", self.script)
        self.assertRegex(self.styles, r"\.info-link:hover \.info-link-text, \.info-link:focus-visible \.info-link-text \{ text-decoration: underline;")
        self.assertRegex(self.styles, r"\.info-link:focus-visible \{ outline: 2px solid")
        self.assertRegex(self.styles, r"\.info-link svg \{ flex: none; width: 12px; height: 12px;")

    def test_the_popover_opens_on_hover_click_enter_and_space_and_closes_on_esc_outside_click_and_focus_loss(self):
        behaviour = self.script[self.script.index("// ---------- Info tips and popovers"):self.script.index("function onlineCopyPopover(card)")]
        for fragment in (
                "document.addEventListener('pointerover'",  # hover opens it, and the pointer may move from the button into the panel
                "!info.contains(event.relatedTarget) && !info.dataset.pinned && !info.matches(':focus-within')",
                "document.addEventListener('click'", "event.target.closest('.info-pop .info-button')", "togglePopover(infoOf(button))",  # click, Enter and Space are a button's click
                "setAttribute('aria-expanded', 'true')", "setAttribute('aria-expanded', 'false')",
                "document.addEventListener('pointerdown'", "if (!info.contains(event.target)) closeInfo(info);",  # a click outside
                "document.addEventListener('focusout'", "if (!info || info.contains(event.relatedTarget)) return;",  # the focus leaving both the button and the panel
                "if (info && !isPopover(info)) openInfo(info);",  # a popover does not open on focus alone; Tab then reaches the link
                "if (isPopover(info)) infoButton(info).focus();"):  # Esc gives the focus back to the button
            self.assertIn(fragment, behaviour)
        escape = self.script[self.script.index("function handleEscape(event)"):]
        self.assertLess(escape.index("document.querySelector('dialog[open]')"), escape.index("dismissInfoTip()"))
        self.assertLess(escape.index("dismissInfoTip()"), escape.index("closePopover()"))
        self.assertIn("if (dismissInfoTip()) { event.preventDefault(); return; }", escape)
        # The panel is real content that follows the button in the page, so Tab goes from the button to the link; it is not displayed while closed.
        self.assertRegex(self.styles, r"\.info-tip \{ display: none;")
        self.assertIn(".info.is-open .info-tip { display: block; }", self.styles)
        self.assertIn('.info-button[aria-expanded="true"]', self.styles)
        # The title of the view keeps a plain tooltip: no link there.
        title = self.page[self.page.index('<span id="syncInfo"'):self.page.index('<span id="resultCount"')]
        self.assertIn('role="tooltip"', title)
        self.assertNotIn("<a ", title)
        self.assertNotIn("aria-expanded", title)

    def test_one_primary_button_per_card_and_a_confirmation_before_saving(self):
        self.assertIn("const label = card.action === 'save' ? 'Save and send' : 'Send';", self.script)
        self.assertIn("card.action === 'save' ? askGitSave(card) : runGit(card, 'send')", self.script)
        self.assertIn("Save ${plural(count, 'changed note')} of ${card.label} and send ${count === 1 ? 'it' : 'them'} to its online copy?", self.script)
        self.assertIn("runGit(card, 'save');", self.script)
        # The write names its brain explicitly and carries the token and the version of the card the person confirmed.
        self.assertIn("request(`/api/git/${action}`, {", self.script)
        self.assertIn("'X-Tasks-Token': token", self.script)
        self.assertIn("body: JSON.stringify({version: card.version})", self.script)
        self.assertIn("}, card.name);", self.script)
        self.assertIn("async function request(url, options = {}, brain = currentBrain)", self.script)

    def test_results_are_plain_with_the_raw_output_behind_details(self):
        for fragment in ("element('summary', '', 'Details')", "element('pre', '', result.details)", "result.ok ? 'status' : 'alert'", "'Dismiss this message'",
                         "button.setAttribute('aria-busy', String(busy));", "`${verb}…`"):
            self.assertIn(fragment, self.script)
        # Nothing the server sends is ever parsed as markup.
        self.assertNotIn("innerHTML = result", self.script)
        git = self.script[self.script.index("// ---------- Git: save and send"):self.script.index("// ---------- Undo ----------")]
        self.assertNotIn("innerHTML", git)
        self.assertNotIn("insertAdjacentHTML", git)

    def test_the_sidebar_count_is_the_number_of_brains_with_something_to_save_or_send(self):
        self.assertIn("function gitPendingCount() { return gitCards.filter(card => card.pending).length; }", self.script)
        self.assertIn("ids.gitCount.textContent = gitLoaded && pending ? String(pending) : '';", self.script)
        # It follows the writes made from the page and Refresh, without a network call (the server only reads local Git state).
        self.assertIn("loadGit({quiet: view !== 'git'});", self.script)
        self.assertIn("loadGit({quiet: true});", self.script)

    def test_a_change_of_brain_closes_the_dialogs_and_keeps_the_cards(self):
        reset = self.script[self.script.index("function resetBrainState()"):self.script.index("function enterBrain(")]
        self.assertIn("closeGitDialogs();", reset)
        self.assertIn("gitLoadId += 1;", reset)

    def test_the_style_has_the_cards_the_comparison_and_both_colour_schemes(self):
        for selector in (".git-card", ".git-notes", ".git-note", ".git-result", ".git-details", ".git-changes-body", ".git-line-add", ".git-line-del", ".git-gap", ".dialog-wide"):
            self.assertIn(selector, self.styles)
        self.assertRegex(self.styles, r"\.git-line-del \{[^}]*text-decoration: line-through")
        for state in ("clean", "changes", "unsent", "behind"):
            self.assertIn(f'.git-card[data-state="{state}"]', self.styles)
        # The state colours exist for the light and for the dark scheme, like every other token.
        light, dark = self.styles.split("@media (prefers-color-scheme: dark)", 1)
        for token in ("--git-ok:", "--git-warn:", "--git-info:", "--git-ok-tint:", "--git-warn-tint:", "--git-info-tint:"):
            self.assertIn(token, light.split("/* Brain accents")[0])
            self.assertIn(token, dark)
        for old in (".git-repos", ".git-diff", ".git-badge-", ".git-commit"):
            self.assertNotIn(old, self.styles)
        # Narrow screens: one column, a full-width button.
        self.assertRegex(self.styles, r"@container main \(max-width: 640px\) \{[^@]*\.git-actions \.button \{ width: 100%")
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.styles)


class NoteDeleteTest(unittest.TestCase):
    """Deleting a note from the interface: which files, the pages that link to it, the version, the undo."""
    CLIENT = "projects/clients/acme/missions/rollout"
    SETUP = "projects/internal/setup"
    NOTE = f"{CLIENT}/notes/2026-10-01-kickoff.md"
    OTHER = f"{CLIENT}/notes/2026-10-02-budget.md"
    INBOX = "inbox/2026-10-03-loose-thought.md"
    SETUP_NOTE = f"{SETUP}/notes/plain.md"
    KICKOFF = "# Kickoff meeting\n\nAgenda one\n"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.brain = root / "brain"
        self.outside = root / "outside"
        self.outside.mkdir()
        (self.outside / "secret.md").write_text("# Secret\n\nnot in the brain\n", encoding="utf-8")
        files = {
            f"{self.CLIENT}/state/actions.md": "# Actions — rollout\n\n## Open\n- [ ] **ACM-001** — Jane Doe — Prepare the kickoff\n    - source: kickoff\n",
            f"{self.SETUP}/state/actions.md": "# Actions — setup\n\n## Open\n",
            f"{self.CLIENT}/rollout.md": "# Rollout\n\nThe project page.\n",
            self.NOTE: self.KICKOFF,
            self.OTHER: "# Budget\n\nFirst line\n",
            self.SETUP_NOTE: "Just text, no heading.\n",
            f"{self.CLIENT}/notes/README.md": "# Notes index\n",
            f"{self.CLIENT}/notes/archive/2026-01-01-old.md": "# Old\n",
            f"{self.CLIENT}/sources/2026-10-01-call.md": "# Call transcript\n\nWhat was said.\n",
            self.INBOX: "# Loose thought\n\nTo triage.\n",
            "inbox/inbox.md": "- a line to triage\n",
            "inbox/README.md": "# Inbox\n",
            "docs/guide.md": "# Guide\n",
            "me/profile.md": "# Profile\n",
            "people/jane-doe.md": "# Jane Doe\n",
            "tasks.md": "# Tasks\n",
            ".data/hidden.md": "# Hidden\n",
        }
        for relative, text in files.items():
            path = self.brain / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        (self.brain / f"{self.CLIENT}/notes/link.md").symlink_to(self.outside / "secret.md")
        self.server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(self.brain), work=root)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(timeout=2)))
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    request = TasksWebTest.request

    def version(self, note_id):
        status, data = self.request("GET", f"/api/notes/content?id={quote(note_id, safe='')}")
        self.assertEqual(status, 200, data)
        return data["version"]

    def delete(self, note_id, version=None, **options):
        return self.request("DELETE", "/api/notes", {"id": note_id, "version": version or self.version(note_id)}, **options)

    def undo(self):
        state = self.request("GET", "/api/undo")[1]
        return self.request("POST", "/api/undo", {"label": state["label"]})

    def write(self, relative, text):
        path = self.brain / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    # --- which files

    def test_only_working_notes_are_deletable(self):
        for note_id in (self.NOTE, self.OTHER, self.SETUP_NOTE, self.INBOX):
            status, data = self.request("GET", f"/api/docs/render?id={quote(note_id, safe='')}")
            self.assertEqual((status, data["note"], data["deletable"]), (200, True, True), note_id)
            self.assertTrue(self.request("GET", f"/api/notes/content?id={quote(note_id, safe='')}")[1]["deletable"], note_id)
        for doc_id in (f"{self.CLIENT}/rollout.md", f"{self.CLIENT}/state/actions.md", f"{self.CLIENT}/sources/2026-10-01-call.md", f"{self.CLIENT}/notes/README.md",
                       f"{self.CLIENT}/notes/archive/2026-01-01-old.md", "inbox/inbox.md", "inbox/README.md", "docs/guide.md", "me/profile.md", "people/jane-doe.md", "tasks.md"):
            status, data = self.request("GET", f"/api/docs/render?id={quote(doc_id, safe='')}")
            self.assertEqual((status, data["note"], data["deletable"]), (200, False, False), doc_id)

    def test_every_other_kind_of_file_is_refused_and_left_alone(self):
        before = {path: path.read_bytes() for path in sorted(self.brain.rglob("*.md")) if not path.is_symlink()}
        forbidden = (f"{self.CLIENT}/rollout.md", f"{self.CLIENT}/state/actions.md", f"{self.CLIENT}/sources/2026-10-01-call.md", f"{self.CLIENT}/notes/README.md",
                     f"{self.CLIENT}/notes/archive/2026-01-01-old.md", "inbox/inbox.md", "inbox/README.md", "docs/guide.md", "me/profile.md", "people/jane-doe.md", "tasks.md")
        for doc_id in forbidden:
            status, data = self.request("DELETE", "/api/notes", {"id": doc_id, "version": "0" * 16})
            self.assertEqual((status, data), (400, {"error": "Only a working note can be deleted from here."}), doc_id)
        # Not documents of the catalogue at all: a dot folder, a missing file, a symbolic link, the ids a path traversal would use.
        for doc_id in (".data/hidden.md", "nothing.md", f"{self.CLIENT}/notes/link.md", "../outside/secret.md", "../brain/tasks.md", f"{self.CLIENT}/notes/../rollout.md",
                       f"{self.CLIENT}/notes/./2026-10-01-kickoff.md", f"/{self.NOTE}", str(self.outside / "secret.md"), "..", ".", "", f"{self.CLIENT}/notes/%2e%2e/rollout.md",
                       f"{self.CLIENT}\\notes\\2026-10-01-kickoff.md", "inbox\x00/inbox.md", self.NOTE + "\x00"):
            status, data = self.request("DELETE", "/api/notes", {"id": doc_id, "version": "0" * 16})
            self.assertEqual((status, data), (404, {"error": "Note not found."}), repr(doc_id))
        for value in (None, 7, ["x"], {"id": self.NOTE}):
            self.assertEqual(self.request("DELETE", "/api/notes", {"id": value, "version": "0" * 16})[0], 400, value)
        after = {path: path.read_bytes() for path in sorted(self.brain.rglob("*.md")) if not path.is_symlink()}
        self.assertEqual(after, before)
        self.assertEqual((self.outside / "secret.md").read_text(encoding="utf-8"), "# Secret\n\nnot in the brain\n")
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)

    def test_a_symbolic_link_or_a_linked_folder_is_never_followed(self):
        link = self.brain / f"{self.CLIENT}/notes/link.md"
        self.assertTrue(link.is_symlink())
        for note_id in (f"{self.CLIENT}/notes/link.md",):
            self.assertEqual(self.request("DELETE", "/api/notes", {"id": note_id, "version": "0" * 16})[0], 404)
            self.assertEqual(self.request("GET", f"/api/notes/backlinks?id={quote(note_id, safe='')}")[0], 404)
        self.assertTrue(link.is_symlink())
        # A notes folder that is a link to somewhere else holds no note of the brain.
        shutil.rmtree(self.brain / f"{self.SETUP}/notes")
        (self.outside / "notes").mkdir()
        (self.outside / "notes/plain.md").write_text("# Plain\n", encoding="utf-8")
        (self.brain / f"{self.SETUP}/notes").symlink_to(self.outside / "notes")
        status, data = self.request("DELETE", "/api/notes", {"id": self.SETUP_NOTE, "version": "0" * 16})
        self.assertEqual(status, 404)
        self.assertTrue((self.outside / "notes/plain.md").exists())
        # A note that became a link after it was shown is not deleted either, and what it pointed to stays.
        version = self.version(self.NOTE)
        (self.brain / self.NOTE).unlink()
        (self.brain / self.NOTE).symlink_to(self.outside / "secret.md")
        self.assertEqual(self.request("DELETE", "/api/notes", {"id": self.NOTE, "version": version})[0], 404)
        self.assertTrue((self.outside / "secret.md").exists())

    # --- the deletion

    def test_a_note_is_deleted_with_its_version_and_leaves_the_lists(self):
        before_other = (self.brain / self.OTHER).read_bytes()
        version = self.version(self.NOTE)
        status, data = self.request("DELETE", "/api/notes", {"id": self.NOTE, "version": version})
        self.assertEqual(status, 200, data)
        self.assertEqual((data["deleted"], data["title"]), (self.NOTE, "Kickoff meeting"))
        self.assertEqual((data["undo"]["available"], data["undo"]["label"]), (True, 'note "Kickoff meeting" deleted'))
        self.assertFalse((self.brain / self.NOTE).exists())
        self.assertTrue((self.brain / f"{self.CLIENT}/notes").is_dir())  # the folder stays
        self.assertNotIn(self.NOTE, [item["id"] for item in self.request("GET", "/api/notes")[1]["notes"]])
        self.assertEqual(self.request("GET", f"/api/notes/content?id={quote(self.NOTE, safe='')}")[0], 404)
        self.assertEqual(self.request("GET", f"/api/docs/render?id={quote(self.NOTE, safe='')}")[0], 404)
        self.assertEqual(self.request("GET", "/api/search?q=agenda")[1]["results"], [])
        self.assertEqual((self.brain / self.OTHER).read_bytes(), before_other)
        # Deleted once: a second request finds nothing.
        self.assertEqual(self.request("DELETE", "/api/notes", {"id": self.NOTE, "version": version})[0], 404)

    def test_an_inbox_note_and_a_note_without_heading_can_be_deleted(self):
        status, data = self.delete(self.INBOX)
        self.assertEqual((status, data["title"]), (200, "Loose thought"))
        self.assertFalse((self.brain / self.INBOX).exists())
        self.assertTrue((self.brain / "inbox/inbox.md").exists())  # the scratchpad and the README are not the note
        status, data = self.delete(self.SETUP_NOTE)
        self.assertEqual((status, data["title"]), (200, "plain"))
        self.assertFalse((self.brain / self.SETUP_NOTE).exists())

    def test_a_note_that_changed_since_it_was_shown_is_not_deleted(self):
        version = self.version(self.NOTE)
        self.write(self.NOTE, self.KICKOFF + "Edited elsewhere\n")
        status, data = self.request("DELETE", "/api/notes", {"id": self.NOTE, "version": version})
        self.assertEqual((status, data), (409, {"error": "The note changed on disk. Reload it before deleting it."}))
        self.assertEqual((self.brain / self.NOTE).read_text(encoding="utf-8"), self.KICKOFF + "Edited elsewhere\n")
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)

    def test_the_write_keeps_the_token_the_origin_the_host_and_the_json_rules(self):
        version = self.version(self.NOTE)
        payload = {"id": self.NOTE, "version": version}
        self.assertEqual(self.request("DELETE", "/api/notes", payload, token=False)[0], 403)
        self.assertEqual(self.request("DELETE", "/api/notes", payload, origin=False)[0], 403)
        for headers in ({"X-Tasks-Token": "wrong"}, {"Origin": "http://evil.example"}, {"Host": "evil.example"}):
            request = Request(self.base + "/api/notes", data=json.dumps(payload).encode(), method="DELETE",
                              headers={"Content-Type": "application/json", "Origin": self.base, "X-Tasks-Token": self.server.token, **headers})
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=3)
            self.assertEqual(caught.exception.code, 403, headers)
            caught.exception.close()
        request = Request(self.base + "/api/notes", data=json.dumps(payload).encode(), method="DELETE",
                          headers={"Content-Type": "text/plain", "Origin": self.base, "X-Tasks-Token": self.server.token})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 415)
        caught.exception.close()
        for bad in ({"id": self.NOTE}, {"version": version}, {"id": self.NOTE, "version": version, "force": True}, {"id": self.NOTE, "version": 5}, {"id": [self.NOTE], "version": version}):
            self.assertEqual(self.request("DELETE", "/api/notes", bad)[0], 400, bad)
        self.assertEqual(self.request("DELETE", "/api/notes?brain=nope", payload), (400, {"error": "Unknown brain."}))
        self.assertTrue((self.brain / self.NOTE).exists())
        self.assertEqual(self.request("DELETE", "/api/notes", payload)[0], 200)

    # --- the pages that link to the note

    def link_pages(self):
        """Pages that link to NOTE in the forms a brain uses, and pages that only look as if they did."""
        self.write(f"{self.CLIENT}/rollout.md", "# Rollout\n\nSee [the kickoff](notes/2026-10-01-kickoff.md) and [its agenda](notes/2026-10-01-kickoff.md#agenda-one).\n")
        self.write(self.OTHER, "# Budget\n\nFrom [the kickoff](2026-10-01-kickoff.md#agenda-one).\n")
        self.write(f"{self.CLIENT}/state/actions.md", "# Actions — rollout\n\n## Open\n- [ ] **ACM-001** — Jane Doe — Prepare the kickoff\n    - source: [kickoff](../notes/2026-10-01-kickoff.md)\n")
        self.write("me/profile.md", "# Profile\n\nSee [[2026-10-01-kickoff]] and [[2026-10-01-kickoff|the kickoff]].\n")
        self.write(f"{self.SETUP_NOTE}", "# Plain\n\n[kickoff](../../../clients/acme/missions/rollout/notes/2026-10-01-kickoff.md)\n")
        # Not links to the note: code, another file, another place, an external address, an anchor, a missing note with the same ending.
        self.write("docs/guide.md", "# Guide\n\n```\n[x](../projects/clients/acme/missions/rollout/notes/2026-10-01-kickoff.md)\n```\nand `[y](../projects/clients/acme/missions/rollout/notes/2026-10-01-kickoff.md)`.\n")
        self.write("people/jane-doe.md", "# Jane Doe\n\n[budget](../projects/clients/acme/missions/rollout/notes/2026-10-02-budget.md) [web](https://example.test/2026-10-01-kickoff.md) [top](#top) "
                                           "[mail](mailto:jane@example.test)\n")
        self.write(self.INBOX, "# Loose thought\n\n[the kickoff](../" + self.NOTE + ") and [itself](2026-10-03-loose-thought.md)\n")

    def test_a_note_that_is_linked_is_not_deleted_and_the_pages_are_listed(self):
        self.link_pages()
        expected = [
            {"id": f"{self.CLIENT}/rollout.md", "title": "Rollout", "project": "acme / rollout"},
            {"id": f"{self.CLIENT}/notes/2026-10-02-budget.md", "title": "Budget", "project": "acme / rollout"},
            {"id": f"{self.CLIENT}/state/actions.md", "title": "Actions — rollout", "project": "acme / rollout"},
            {"id": f"{self.SETUP_NOTE}", "title": "Plain", "project": "setup"},
            {"id": "me/profile.md", "title": "Profile", "project": None},
            {"id": self.INBOX, "title": "Loose thought", "project": "Inbox"},
        ]
        expected.sort(key=lambda page: page["id"])
        status, data = self.request("GET", f"/api/notes/backlinks?id={quote(self.NOTE, safe='')}")
        self.assertEqual(status, 200, data)
        self.assertEqual((data["id"], data["title"], data["count"], data["pages"]), (self.NOTE, "Kickoff meeting", len(expected), expected))
        self.assertEqual(data["version"], self.version(self.NOTE))
        before = (self.brain / self.NOTE).read_bytes()
        status, data = self.request("DELETE", "/api/notes", {"id": self.NOTE, "version": data["version"]})
        self.assertEqual(status, 409)
        self.assertEqual(data["error"], f"This note is linked from {len(expected)} pages. Remove those links first, or ask your agent.")
        self.assertEqual((data["count"], data["backlinks"]), (len(expected), expected))
        self.assertEqual((self.brain / self.NOTE).read_bytes(), before)
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)

    def test_one_link_is_one_page_and_the_message_is_singular(self):
        self.write(self.OTHER, "# Budget\n\n[the kickoff](2026-10-01-kickoff.md)\n[again](2026-10-01-kickoff.md#agenda-one)\n")
        status, data = self.delete(self.NOTE)
        self.assertEqual((status, data["error"], data["count"], [page["id"] for page in data["backlinks"]]),
                         (409, "This note is linked from 1 page. Remove those links first, or ask your agent.", 1, [self.OTHER]))
        # Once the link is gone, the note can go.
        self.write(self.OTHER, "# Budget\n\nNo link left.\n")
        self.assertEqual(self.delete(self.NOTE)[0], 200)

    def test_a_wikilink_blocks_only_when_no_other_note_has_that_name(self):
        self.write("me/profile.md", "# Profile\n\nSee [[2026-10-01-kickoff]].\n")
        self.assertEqual(self.request("GET", f"/api/notes/backlinks?id={quote(self.NOTE, safe='')}")[1]["count"], 1)
        self.write(f"{self.SETUP}/notes/2026-10-01-kickoff.md", "# Another kickoff\n")  # the link still finds a file with that name
        self.assertEqual(self.request("GET", f"/api/notes/backlinks?id={quote(self.NOTE, safe='')}")[1]["count"], 0)
        self.assertEqual(self.delete(self.NOTE)[0], 200)

    def test_a_long_list_is_cut_but_counted(self):
        for number in range(tasks_web.NOTE_BACKLINK_LIMIT + 7):
            self.write(f"{self.SETUP}/notes/ref-{number:03d}.md", f"# Ref {number}\n\n[kickoff](../../../clients/acme/missions/rollout/notes/2026-10-01-kickoff.md)\n")
        data = self.request("GET", f"/api/notes/backlinks?id={quote(self.NOTE, safe='')}")[1]
        self.assertEqual((data["count"], len(data["pages"])), (tasks_web.NOTE_BACKLINK_LIMIT + 7, tasks_web.NOTE_BACKLINK_LIMIT))
        status, refused = self.delete(self.NOTE)
        self.assertEqual((status, refused["count"], len(refused["backlinks"])), (409, tasks_web.NOTE_BACKLINK_LIMIT + 7, tasks_web.NOTE_BACKLINK_LIMIT))

    def test_backlinks_are_what_the_link_check_would_report_once_the_note_is_gone(self):
        """The rules are those of tools/brain/check-links.py: delete the file behind the server's back and let that tool judge."""
        self.link_pages()
        data = self.request("GET", f"/api/notes/backlinks?id={quote(self.NOTE, safe='')}")[1]
        (self.brain / self.NOTE).unlink()
        done = subprocess.run([sys.executable, str(REPO / "tools/brain/check-links.py")], capture_output=True, text=True, timeout=60,
                              env={**os.environ, "BRAIN_DIR": str(self.brain), "WORK_DIR": str(self.brain.parent)})
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        reported = set(re.findall(r"^ {7}(\S.*)$", done.stdout, re.MULTILINE))
        self.assertEqual(reported, {page["id"] for page in data["pages"]}, done.stdout)

    def test_unknown_notes_have_no_backlinks_to_ask_for(self):
        for note_id in ("nothing.md", f"{self.CLIENT}/rollout.md", "../outside/secret.md", ""):
            self.assertEqual(self.request("GET", f"/api/notes/backlinks?id={quote(note_id, safe='')}")[0], 404, note_id)
        self.assertEqual(self.request("GET", "/api/notes/backlinks")[0], 400)
        self.assertEqual(self.request("GET", "/api/notes/backlinks?brain=nope&id=x")[0], 400)

    # --- undo

    def test_undo_brings_back_the_exact_bytes_the_path_and_the_mode(self):
        raw = b"\xef\xbb\xbf# Kickoff meeting\r\n\r\nCaf\xc3\xa9 \xe2\x80\x94 no final newline"
        path = self.brain / self.NOTE
        path.write_bytes(raw)
        path.chmod(0o640)
        self.assertEqual(self.delete(self.NOTE)[0], 200)
        shutil.rmtree(self.brain / f"{self.CLIENT}/notes")  # even the folder may be gone by then
        status, data = self.undo()
        self.assertEqual(status, 200, data)
        self.assertEqual((data["undone"], data["action_id"], data["restored"], data["undo"]["available"]), ('note "2026-10-01-kickoff" deleted', self.NOTE, True, False))  # the first line carries a BOM: no title
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(path.stat().st_mode & 0o777, 0o640)
        self.assertIn(self.NOTE, [item["id"] for item in self.request("GET", "/api/notes")[1]["notes"]])
        self.assertEqual(self.request("GET", f"/api/docs/render?id={quote(self.NOTE, safe='')}")[0], 200)

    def test_undo_is_refused_when_the_path_is_taken(self):
        self.assertEqual(self.delete(self.NOTE)[0], 200)
        path = self.brain / self.NOTE
        path.write_text("# A new note with the same name\n", encoding="utf-8")
        status, data = self.undo()
        self.assertEqual((status, data), (409, {"error": "A file now exists where this note was: it cannot be restored."}))
        self.assertEqual(path.read_text(encoding="utf-8"), "# A new note with the same name\n")  # what is there is never overwritten
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)  # an undo that cannot happen is no longer offered
        for taken in ("directory", "link", "dangling link"):
            self.write(self.OTHER, "# Budget\n\nFirst line\n")
            self.assertEqual(self.delete(self.OTHER)[0], 200)
            target = self.brain / self.OTHER
            if taken == "directory":
                target.mkdir()
            elif taken == "link":
                target.symlink_to(self.outside / "secret.md")
            else:
                target.symlink_to(self.outside / "missing.md")
            self.assertEqual(self.undo()[0], 409, taken)
            self.assertTrue(target.is_dir() or target.is_symlink(), taken)
            if target.is_dir():
                target.rmdir()
            else:
                target.unlink()
        self.assertEqual((self.outside / "secret.md").read_text(encoding="utf-8"), "# Secret\n\nnot in the brain\n")

    def test_undo_never_writes_through_a_folder_that_became_a_link(self):
        self.assertEqual(self.delete(self.NOTE)[0], 200)
        shutil.rmtree(self.brain / f"{self.CLIENT}/notes")
        (self.brain / f"{self.CLIENT}/notes").symlink_to(self.outside)
        status, data = self.undo()
        self.assertEqual(status, 409, data)
        self.assertEqual(sorted(path.name for path in self.outside.iterdir()), ["secret.md"])

    def test_undo_follows_the_order_of_the_changes(self):
        status, created = self.request("POST", "/api/notes", {"title": "Fresh", "register": f"{self.CLIENT}/state/actions.md", "content": "x"})
        self.assertEqual(status, 201)
        self.assertEqual(self.delete(self.NOTE)[0], 200)
        self.assertEqual(self.undo()[1]["undone"], 'note "Kickoff meeting" deleted')  # the deletion first,
        self.assertTrue((self.brain / self.NOTE).exists())
        self.assertEqual(self.undo()[1]["undone"], 'note "Fresh" created')  # then the creation before it
        self.assertFalse((self.brain / created["id"]).exists())


class NoteDeletePageTest(unittest.TestCase):
    """Deleting a note in the page: the button, the confirmation, the pages that still link to the note, the toast and the undo."""
    STATIC = TOOL.parent / "static"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        brain = Path(self.temp.name) / "brain"
        (brain / "projects").mkdir(parents=True)
        server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(brain), work=Path(self.temp.name))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))
        with urlopen(f"http://127.0.0.1:{server.server_port}/", timeout=3) as response:
            self.page = response.read().decode("utf-8")
        self.script = (self.STATIC / "app.js").read_text(encoding="utf-8")
        self.styles = (self.STATIC / "app.css").read_text(encoding="utf-8")

    def test_the_delete_button_sits_next_to_edit_and_only_shows_for_a_deletable_note(self):
        actions = self.page[self.page.index('<div class="doc-pane-actions">'):self.page.index('<p id="docPaneEmpty"')]
        self.assertLess(actions.index('id="docEdit"'), actions.index('id="docDelete"'))
        self.assertIn('<button id="docDelete" class="button button-danger" type="button" hidden title="Delete this note">', actions)
        self.assertIn("ids.docDelete.hidden = !doc || !doc.deletable || docEditing;", self.script)  # not while editing, not for a page or a source
        self.assertIn("ids.docDelete.addEventListener('click', askDeleteNote);", self.script)
        self.assertIn("if (!doc || !doc.deletable || docEditing || docSaving || ids.docDelete.getAttribute('aria-busy') === 'true') return;", self.script)
        self.assertNotIn("ids.docDelete.disabled", self.script)  # a disabled button loses the focus the dialog gives back to it

    def test_the_confirmation_asks_first_with_cancel_as_the_default(self):
        dialog = self.page[self.page.index('<dialog id="deleteNoteDialog"'):self.page.index('<dialog id="gitConfirmDialog"')]
        self.assertIn('aria-labelledby="deleteNoteHeading" aria-describedby="deleteNoteText"', dialog)
        self.assertIn('<button id="deleteNoteCancel" class="button" type="submit" value="cancel" autofocus>Cancel</button>', dialog)
        self.assertIn('<button id="deleteNoteConfirm" class="button button-danger-solid" type="button">Delete</button>', dialog)
        self.assertIn('<ul id="deleteNoteLinks" class="delete-note-links" hidden></ul>', dialog)
        self.assertIn('<p id="deleteNoteError" class="form-error" role="alert" hidden></p>', dialog)
        delete = self.script[self.script.index("// ---------- Deleting a note ----------"):self.script.index("function refreshDocsView()")]
        self.assertIn("ids.deleteNoteHeading.textContent = `Delete the note \u201c${title}\u201d?`;", delete)
        self.assertIn("'The note is removed from this brain. You can undo it right after.'", delete)
        self.assertIn("ids.deleteNoteDialog.showModal();", delete)

    def test_a_linked_note_lists_its_pages_and_offers_no_delete(self):
        delete = self.script[self.script.index("// ---------- Deleting a note ----------"):self.script.index("function refreshDocsView()")]
        self.assertIn("`This note is linked from ${plural(count, 'page')}. Remove those links first, or ask your agent.`", delete)
        self.assertIn("ids.deleteNoteConfirm.hidden = linked;", delete)
        self.assertIn("ids.deleteNoteCancel.textContent = linked ? 'Close' : 'Cancel';", delete)
        # Each page opens in the reader; the list comes from the server before the dialog opens, and again when the server refuses the deletion.
        self.assertIn("open.addEventListener('click', () => openLinkingPage(page.id));", delete)
        self.assertIn("openDoc(id, {nav: 'root'});", delete)
        self.assertIn("request(`/api/notes/backlinks?id=${encodeURIComponent(doc.id)}`)", delete)
        self.assertIn("if (error.status === 409 && Array.isArray(data.backlinks)) showDeleteNoteDialog(target.title, data.count, data.backlinks);", delete)
        self.assertIn("error.data = payload;", self.script)

    def test_a_deletion_is_one_request_with_the_version_then_a_toast_with_undo_and_fresh_lists(self):
        delete = self.script[self.script.index("// ---------- Deleting a note ----------"):self.script.index("function refreshDocsView()")]
        for fragment in ("method: 'DELETE', headers: {'Content-Type': 'application/json', 'X-Tasks-Token': token},", "body: JSON.stringify({id: target.id, version: target.version})",
                         "noteToDelete = {id: doc.id, version: doc.version, title: info.title};",  # the version of the note the person was reading
                         "setUndo(result.undo);", "clearDocPane();", "showToast('Note deleted', {undo: true});", "await refresh();", "await loadNotes();"):  # refresh: the lists, and the number next to Sync
            self.assertIn(fragment, delete)
        self.assertLess(delete.index("clearDocPane();"), delete.index("showToast('Note deleted'"))
        pane = delete[delete.index("function clearDocPane()"):delete.index("async function confirmDeleteNote()")]
        for fragment in ("docSelectedId = null;", "docCurrent = null;", "docRenderRequest += 1;", "Choose a document to read it."):
            self.assertIn(fragment, pane)
        # Undo gives the note back and shows it again.
        self.assertIn("if (result.restored && isDocsView()) openDoc(result.action_id, {nav: 'root'});", self.script)
        # A note that is not what the person saw is reloaded, with the reason in the pane.
        self.assertIn("await openDoc(target.id, {nav: 'keep'});", delete)
        self.assertIn("setDocError(error.message);", delete)
        self.assertRegex(self.styles, r"\.delete-note-links \{[^}]*overflow: auto")


class DocsTest(unittest.TestCase):
    """Search and rendering over a temporary brain."""
    CLIENT = "projects/clients/acme/missions/migration"
    INTERNAL = "projects/internal/setup"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.brain = root / "brain"
        self.outside = root / "outside"
        self.outside.mkdir()
        (self.outside / "dehors.md").write_text("# Dehors\n\nmot-secret-externe\n", encoding="utf-8")
        for folder, line in ((self.CLIENT, "- [ ] **ACM-001** — Jane — Livrer"), (self.INTERNAL, "- [ ] **SET-001** — Jane — Ranger")):
            (self.brain / folder / "state").mkdir(parents=True)
            (self.brain / folder / "state/actions.md").write_text(f"# Actions\n\n## Open\n{line}\n", encoding="utf-8")
        self.page = self.write(f"{self.CLIENT}/migration.md", "# Migration Demo\n\n## Périmètre\n\nTexte de la fiche mission.\n")
        self.meeting = self.write(f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md", "# Compte rendu\n\nLa RÉUNION du lundi a validé le budget annuel.\n")
        self.write(f"{self.INTERNAL}/notes/2026-10-02-autre.md", "# Autre note\n\nBudget revu : annuel puis trimestriel, sans réunion.\n")
        self.write("context/glossaire.md", "# Glossaire\n\nDéfinition du budget et de la réunion hors projet.\n")
        self.write("context/roadmap.md", "# Roadmap\n\nRien d'autre ici.\n")
        self.write("context/divers.md", "# Divers\n\nroadmap roadmap roadmap dans le corps.\n")
        self.write(".hidden/secret.md", "# Secret\n\nmot-cache\n")
        self.write(".data/etat.md", "# Etat\n\nmot-cache\n")
        self.write("projects/.vscode/a.md", "# VS\n\nmot-cache\n")
        self.write("context/.prive.md", "# Prive\n\nmot-cache\n")
        (self.brain / "context/lien.md").symlink_to(self.outside / "dehors.md")
        (self.brain / "lié").symlink_to(self.outside, target_is_directory=True)
        (self.brain / "context/gros.md").write_text("# Gros\n\nmot-gros\n" + "x" * 1_000_001, encoding="utf-8")
        self.server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(self.brain))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.register = f"{self.CLIENT}/state/actions.md"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    request = TasksWebTest.request

    def write(self, relative, text):
        path = self.brain / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def get(self, path):
        try:
            with urlopen(self.base + path, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def search(self, query, project=None):
        from urllib.parse import urlencode
        params = {"q": query}
        if project is not None:
            params["project"] = project
        status, data = self.get("/api/search?" + urlencode(params))
        self.assertEqual(status, 200, data)
        return data

    def ids(self, query, project=None):
        return [item["id"] for item in self.search(query, project)["results"]]

    def render(self, doc_id):
        from urllib.parse import quote
        status, data = self.get("/api/docs/render?id=" + quote(doc_id))
        self.assertEqual(status, 200, data)
        return data

    # --- Search ---------------------------------------------------------------------------------------

    def test_fold_keeps_offsets_consistent(self):
        for sample in ("Réunion  du\n\nLUNDI", "Straße ﬁn ÉCOLE 📅 façade", "été   x", ""):
            folded, origin = tasks_web.fold_mapped(sample)
            self.assertEqual(folded, tasks_web.fold(sample))
            self.assertEqual(len(folded), len(origin))
        self.assertEqual(tasks_web.fold("RÉUNION"), "reunion")
        self.assertEqual(tasks_web.fold("Straße"), "strasse")

    def test_matching_ignores_case_and_accents(self):
        expected = [f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md"]
        for query in ("réunion lundi", "REUNION lundi", "reunion LUNDI", "RÉUNION"):
            self.assertIn(expected[0], self.ids(query), query)
        self.assertEqual(self.ids("reunion lundi"), expected)
        self.assertEqual(self.search("RÉUNION")["terms"], ["reunion"])

    def test_all_terms_are_required(self):
        both = self.ids("budget reunion")
        self.assertIn("context/glossaire.md", both)
        self.assertIn(f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md", both)
        self.assertEqual(self.ids("budget reunion lundi"), [f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md"])
        self.assertEqual(self.ids("budget absentabsent"), [])

    def test_quoted_phrase_is_one_term(self):
        self.assertEqual(self.ids('"budget annuel"'), [f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md"])
        self.assertEqual(self.search('"budget annuel"')["terms"], ["budget annuel"])
        self.assertNotIn(f"{self.INTERNAL}/notes/2026-10-02-autre.md", self.ids('"budget annuel"'))
        self.assertIn(f"{self.INTERNAL}/notes/2026-10-02-autre.md", self.ids("budget annuel"))
        self.write("context/coupe.md", "# Coupe\n\nle budget\n   annuel\n")
        self.assertIn("context/coupe.md", self.ids('"budget annuel"'))

    def test_title_outranks_body_matches(self):
        results = self.search("roadmap")["results"]
        self.assertEqual([item["id"] for item in results][:2], ["context/roadmap.md", "context/divers.md"])
        self.assertGreater(results[0]["score"], results[1]["score"])
        self.assertEqual(results[0]["title"], "Roadmap")

    def test_path_and_headings_count(self):
        self.write("context/ordinaire.md", "# Ordinaire\n\n## Zanzibar\n\ntexte\n")
        self.write("context/zanzibar-voyage.md", "# Voyage\n\ntexte\n")
        self.write("context/corps.md", "# Corps\n\nZanzibar\n")
        order = self.ids("zanzibar")
        self.assertEqual(order[0], "context/zanzibar-voyage.md")
        self.assertLess(order.index("context/ordinaire.md"), order.index("context/corps.md"))

    def test_results_fields_and_filename_title(self):
        self.write("context/sans-titre.md", "Juste du texte avec marqueurpresent.\n")
        data = self.search("marqueurpresent")
        self.assertEqual((data["total"], data["truncated"], data["query"]), (1, False, "marqueurpresent"))
        item = data["results"][0]
        self.assertEqual((item["id"], item["title"], item["project"], item["register"]), ("context/sans-titre.md", "sans-titre", None, None))

    def test_snippets_ranges_point_at_the_matched_text(self):
        filler = "mot " * 80
        self.write("context/long.md", f"# Long\n\n{filler}\n📅 Chez Électricité de FRANCE, la réunion annuelle\ndu comité a lieu.\n\n{filler}\n{filler} fin RÉUNION finale\n")
        data = self.search("reunion électricité")
        item = next(result for result in data["results"] if result["id"] == "context/long.md")
        self.assertTrue(1 <= len(item["snippets"]) <= 2)
        for snippet in item["snippets"]:
            self.assertLessEqual(len(snippet["text"]), 200)
            self.assertNotIn("\n", snippet["text"])
            self.assertTrue(snippet["ranges"])
            for start, end in snippet["ranges"]:
                self.assertIn(tasks_web.fold(snippet["text"][start:end]), {"reunion", "electricite"})
        first = item["snippets"][0]
        marked = [tasks_web.fold(first["text"][start:end]) for start, end in first["ranges"]]
        self.assertEqual(sorted(marked), ["electricite", "reunion"])
        self.assertTrue(first["text"].startswith("…") or first["text"].startswith("mot"))
        self.assertTrue(first["text"].endswith("…"))

    def test_snippet_without_cut_has_no_ellipsis(self):
        item = self.search("lundi")["results"][0]
        snippet = item["snippets"][0]
        self.assertFalse(snippet["text"].startswith("…") or snippet["text"].endswith("…"))
        start, end = snippet["ranges"][0]
        self.assertEqual(snippet["text"][start:end], "lundi")

    def test_project_filter(self):
        everything = set(self.ids("budget"))
        self.assertEqual(everything, {f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md", f"{self.INTERNAL}/notes/2026-10-02-autre.md", "context/glossaire.md"})
        self.assertEqual(self.ids("budget", self.register), [f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md"])
        self.assertEqual(self.ids("budget", "none"), ["context/glossaire.md"])
        self.assertEqual(self.ids("budget", ""), self.ids("budget"))
        self.assertEqual(self.ids("budget", "projects/inconnu/state/actions.md"), [])
        item = self.search("lundi", self.register)["results"][0]
        self.assertEqual(item["register"], self.register)
        self.assertEqual(item["project"], "acme / migration")

    def test_hidden_symlinked_oversized_and_outside_files_are_excluded(self):
        for term in ("mot-cache", "mot-gros", "mot-secret-externe", "dehors"):
            self.assertEqual(self.ids(term), [], term)
        catalogue = {entry.id for entry in tasks_web.Store(self.brain).docs()}
        self.assertIn("context/glossaire.md", catalogue)
        self.assertFalse({"context/lien.md", "context/gros.md", "context/.prive.md", ".hidden/secret.md", ".data/etat.md", "lié/dehors.md"} & catalogue)

    def test_query_limits_and_short_terms(self):
        status, data = self.get("/api/search?q=" + "+".join(f"mot{n}" for n in range(11)))
        self.assertEqual(status, 400)
        self.assertIn("error", data)
        status, _ = self.get("/api/search?q=" + "x" * 61)
        self.assertEqual(status, 400)
        status, _ = self.get("/api/search?q=" + "a" * 301)
        self.assertEqual(status, 400)
        status, _ = self.get("/api/search?q=a&q=b")
        self.assertEqual(status, 400)
        ten = "+".join(f"mot{n}" for n in range(10))
        status, _ = self.get("/api/search?q=" + ten)
        self.assertEqual(status, 200)
        for query in ("a", "", "   ", '""', "é"):
            data = self.search(query)
            self.assertEqual((data["results"], data["total"]), ([], 0), query)
        self.assertEqual(self.ids("a lundi"), self.ids("lundi"))
        self.assertTrue(self.ids("lundi"))
        self.assertEqual(self.search("lundi LUNDI lundi")["terms"], ["lundi"])

    def test_results_are_capped_at_fifty(self):
        for number in range(55):
            self.write(f"bulk/doc{number:02d}.md", f"# Doc {number}\n\nmotbulkpartage\n")
        data = self.search("motbulkpartage")
        self.assertEqual((len(data["results"]), data["total"], data["truncated"]), (50, 55, True))

    def test_catalogue_is_cached_per_file_and_invalidated_on_change(self):
        built = []
        real = tasks_web.DocEntry

        class Counting(real):
            __slots__ = ()

            def __init__(self, doc_id, *args):
                built.append(doc_id)
                super().__init__(doc_id, *args)

        with patch.object(tasks_web, "DocEntry", Counting):
            self.assertEqual(self.ids("nouveaumot"), [])
            total = len(built)
            self.assertGreater(total, 5)
            self.ids("lundi")
            self.assertEqual(len(built), total)
            target = self.brain / "context/glossaire.md"
            target.write_text("# Glossaire\n\nnouveaumot ajouté dedans\n", encoding="utf-8")
            self.assertEqual(self.ids("nouveaumot"), ["context/glossaire.md"])
            self.assertEqual(built[total:], ["context/glossaire.md"])
            target.write_text("# Glossaire\n\nnouveaumot ajouté dedans\n", encoding="utf-8")
            os.utime(target, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
            self.ids("nouveaumot")
            self.assertEqual(built[total:], ["context/glossaire.md"] * 2)
            target.unlink()
            self.assertEqual(self.ids("nouveaumot"), [])

    def test_search_refuses_foreign_hosts_and_writes(self):
        for path in ("/api/search?q=lundi", "/api/docs/render?id=context/glossaire.md"):
            with self.assertRaises(HTTPError) as caught:
                urlopen(Request(self.base + path, headers={"Host": "evil.example"}), timeout=3)
            self.assertEqual(caught.exception.code, 403)
            caught.exception.close()
        status, _ = self.request("POST", "/api/search", {"q": "lundi"})
        self.assertNotEqual(status, 200)

    # --- Rendering ------------------------------------------------------------------------------------

    def test_render_unknown_and_unsafe_ids_are_404(self):
        for doc_id in ("inconnu.md", "../outside/dehors.md", "context/../../outside/dehors.md", "/etc/passwd", ".hidden/secret.md",
                       "context/lien.md", "lié/dehors.md", "context/gros.md", "context/glossaire.md/", "context\\glossaire.md", "CONTEXT/glossaire.md", ""):
            from urllib.parse import quote
            status, data = self.get("/api/docs/render?id=" + quote(doc_id))
            self.assertEqual(status, 404, doc_id)
            self.assertIn("error", data)
        status, _ = self.get("/api/docs/render")
        self.assertEqual(status, 400)
        self.assertEqual(self.render("context/glossaire.md")["title"], "Glossaire")

    def test_render_escapes_raw_html_and_neutralises_scripts(self):
        self.write("context/xss.md", "# Page\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>\n\n"
                   "[js](javascript:alert(3)) [data](data:text/html;base64,AAAA) [vb](vbscript:x) [file](file:///etc/passwd) [tel](tel:123)\n\n"
                   "<div onclick=\"x()\">bloc</div>\n")
        html = self.render("context/xss.md")["html"]
        self.assertNotIn("<script", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertNotIn("<img", html)
        self.assertNotIn("<div onclick", html)
        for scheme in ("javascript:", "data:text", "vbscript:", "file:"):
            self.assertNotIn(f'href="{scheme}', html)
        self.assertNotIn("<a ", html)
        self.assertIn('class="doc-link-off"', html)

    def test_render_front_matter_as_properties_not_heading(self):
        self.write("context/props.md", '---\ndate: 2026-09-25\ntitle: "<b>Titre</b>"\nparticipants: [A, B]\n---\n\n# Corps\n\nTexte.\n')
        html = self.render("context/props.md")["html"]
        self.assertIn('<dl class="doc-props"><dt>date</dt><dd>2026-09-25</dd>', html)
        self.assertIn("&lt;b&gt;Titre&lt;/b&gt;", html)
        self.assertNotIn("<h2", html)
        self.assertIn("<h1", html)
        self.write("context/rule.md", "# Titre\n\nTexte\n\n---\n\nSuite\n")
        self.assertNotIn("doc-props", self.render("context/rule.md")["html"])

    def test_recent_docs_lists_all_kinds_newest_first(self):
        self.write("context/old.md", "# Vieux\n\nAncien texte.\n")
        self.write("context/new.md", "---\ndate: 2026-10-01\n---\n\n# Neuf\n\nTexte récent.\n")
        os.utime(self.brain / "context/old.md", (1_000_000_000, 1_000_000_000))
        status, data = self.get("/api/docs/recent")
        self.assertEqual(status, 200)
        ids = [doc["id"] for doc in data["docs"]]
        self.assertLess(ids.index("context/new.md"), ids.index("context/old.md"))
        new = next(doc for doc in data["docs"] if doc["id"] == "context/new.md")
        self.assertEqual(new["excerpt"], "Texte récent.")
        self.assertTrue(all(doc["project"] is None for doc in self.get("/api/docs/recent?project=none")[1]["docs"]))

    def test_render_internal_links_point_at_catalogue_documents(self):
        self.write(f"{self.CLIENT}/notes/liens.md", "# Liens\n\n[fiche](../migration.md#Périmètre) [encodé](../migration.md#p%C3%A9rim%C3%A8tre) "
                   "[frère](2026-10-01-compte-rendu.md) [ancre](<#Mon titre>) [autre](../../../../../internal/setup/notes/2026-10-02-autre.md)\n\n## Mon titre\n")
        html = self.render(f"{self.CLIENT}/notes/liens.md")["html"]
        page = f"{self.CLIENT}/migration.md"
        self.assertEqual(html.count(f'data-doc="{page}" data-anchor="h-perimetre"'), 2)
        self.assertIn(f'data-doc="{self.CLIENT}/notes/2026-10-01-compte-rendu.md"', html)
        self.assertIn(f'data-doc="{self.INTERNAL}/notes/2026-10-02-autre.md"', html)
        self.assertIn(f'data-doc="{self.CLIENT}/notes/liens.md" data-anchor="h-mon-titre"', html)
        self.assertIn('href="#doc" class="doc-link"', html)
        self.assertIn('<h2 id="h-mon-titre">', html)
        self.assertNotIn("../", html)

    def test_render_links_outside_the_brain_or_missing_are_plain_text(self):
        self.write(f"{self.CLIENT}/notes/hors.md", "# Hors\n\n[outil](../../../../../../tools/x.md) [artefact](../../../../../../../artifacts/a/README.md) "
                   "[absent](../absent.md) [pdf](../fichier.pdf) [abs](/etc/passwd.md) [dir](../) [cache](../../../../../.hidden/secret.md) "
                   "[ext](https://example.com/a?b=1&c=2) [mail](mailto:a@example.com)\n")
        html = self.render(f"{self.CLIENT}/notes/hors.md")["html"]
        self.assertEqual(html.count('<span class="doc-link-off" title="File not shown here">'), 7)
        for text in ("outil", "artefact", "absent", "pdf", "abs", "dir", "cache"):
            self.assertIn(f'title="File not shown here">{text}</span>', html)
        self.assertEqual(html.count("<a "), 2)
        self.assertNotIn("data-doc", html)
        self.assertNotIn("tools/x.md", html)
        self.assertIn('<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">ext</a>', html)
        self.assertIn('<a href="mailto:a@example.com" target="_blank" rel="noopener noreferrer">mail</a>', html)

    def test_render_tables_headings_images_and_code(self):
        self.write("context/riche.md", "# Titre\n\n## Même titre\n\n## Même titre\n\n### Éléments *clés* `code`\n\n"
                   "| a | b |\n|---|---|\n| 1 | 2 |\n\n~~barré~~\n\n![schéma <b>](x.png)\n\n```py\nprint('<tag>')\n```\n\n> citation\n\n- un\n  - deux\n")
        html = self.render("context/riche.md")["html"]
        self.assertIn('<div class="table-wrap"><table>', html)
        self.assertIn("</table>\n</div>", html)
        self.assertIn('<h1 id="h-titre">', html)
        self.assertIn('<h2 id="h-meme-titre">', html)
        self.assertIn('<h2 id="h-meme-titre-2">', html)
        self.assertIn('id="h-elements-cles-code"', html)
        self.assertIn("<s>barré</s>", html)
        self.assertNotIn("<img", html)
        self.assertIn('<span class="doc-image-off" title="Image not shown here">schéma &lt;b&gt;</span>', html)
        self.assertIn("print('&lt;tag&gt;')", html)
        self.assertIn("<blockquote>", html)

    def test_render_underline_tags_become_underline_and_nothing_else_does(self):
        self.write("context/underline.md", "# Plan <u>acme</u>\n\nA <u>word</u>, <U>another</U> and <u>**bold** inside</u>.\n\n- <u>item</u>\n\n"
                   "| head |\n|---|\n| <u>cell</u> |\n\n[<u>link</u>](https://example.com)\n\n`<u>code</u>`\n\n```\n<u>block</u>\n```\n")
        html = self.render("context/underline.md")["html"]
        self.assertIn('<h1 id="h-plan-acme">Plan <u>acme</u></h1>', html)
        self.assertIn("<p>A <u>word</u>, <u>another</u> and <u><strong>bold</strong> inside</u>.</p>", html)
        self.assertIn("<li><u>item</u></li>", html)
        self.assertIn("<td><u>cell</u></td>", html)
        self.assertIn('rel="noopener noreferrer"><u>link</u></a>', html)
        self.assertIn("<code>&lt;u&gt;code&lt;/u&gt;</code>", html)
        self.assertIn("&lt;u&gt;block&lt;/u&gt;", html)
        self.assertEqual(html.count("<u>"), html.count("</u>"))

    def test_render_underline_keeps_every_other_piece_of_html_escaped(self):
        payloads = [
            '<u onclick="alert(1)">x</u>', "<u style=x>x</u>", "<u/onclick=alert(1)>x</u>", "< u>x</u>", "<u\n>x</u>", "<u >x</u>",
            "<uu>x</uu>", "<u>x</u onclick=y>", "<u><img src=x onerror=alert(1)></u>", "<u><script>alert(1)</script></u>",
            "<u>a<b>b</b></u>", "<u>&lt;b&gt;</u><script>", "<u><svg onload=alert(1)></u>", "<u>x</u><iframe src=//evil.example>",
        ]
        for payload in payloads:
            with self.subTest(payload=payload):
                html = tasks_web.MARKDOWN.render(payload)
                self.assertOnlyPlainMarkup(html)
                for tag in ("<script", "<img", "<svg", "<iframe", "<b>"):
                    self.assertNotIn(tag, html)
                for tag in re.findall(r"</?u[^<>]*>", html):
                    self.assertIn(tag, ("<u>", "</u>"))
        self.assertIn("&lt;u onclick=&quot;alert(1)&quot;&gt;x&lt;/u&gt;", tasks_web.MARKDOWN.render(payloads[0]))
        self.assertEqual(tasks_web.MARKDOWN.render("<u><script>alert(1)</script></u>"), "<p><u>&lt;script&gt;alert(1)&lt;/script&gt;</u></p>\n")

    def test_render_underline_tags_stay_balanced_whatever_the_input(self):
        texts = ["<u>", "</u>", "<u></u>", "<u>open only", "close only</u>", "</u>before<u>", "<u>a<u>b</u>c</u>", "<u>a\n\nb</u>",
                 "<u>**a</u>**", "**<u>a**</u>", "<u>`</u>`", "<u>[a</u>](b)", "<u>a</u> <u>b", "> <u>quote\n\n</u>", "- <u>a\n- b</u>"]
        for text in texts:
            with self.subTest(text=text):
                html = tasks_web.MARKDOWN.render(text)
                self.assertOnlyPlainMarkup(html)
                self.assertEqual(html.count("<u>"), html.count("</u>"))
        # An unmatched tag is shown as text, like the raw HTML it is.
        self.assertEqual(tasks_web.MARKDOWN.render("<u>open only"), "<p>&lt;u&gt;open only</p>\n")
        self.assertEqual(tasks_web.MARKDOWN.render("a</u>"), "<p>a&lt;/u&gt;</p>\n")

    def assertOnlyPlainMarkup(self, html):
        """Nothing but the tags the Markdown rules produce (here: paragraphs, emphasis, code and the bare underline) is unescaped."""
        rest = re.sub(r"</?(?:p|u|strong|em|code|blockquote|ul|li)>", "", html)
        self.assertEqual(re.findall(r"<[^>]*>", rest), [], html)

    def test_render_note_flag_and_version_match_the_patch_contract(self):
        note_id = f"{self.CLIENT}/notes/2026-10-01-compte-rendu.md"
        data = self.render(note_id)
        self.assertEqual((data["id"], data["title"], data["project"], data["register"], data["note"]), (note_id, "Compte rendu", "acme / migration", self.register, True))
        self.assertEqual(data["version"], hashlib.sha256(self.meeting.read_bytes()).hexdigest()[:16])
        status, saved = self.request("PATCH", "/api/notes", {"id": note_id, "version": data["version"], "content": "# Compte rendu\n\nMis à jour.\n"})
        self.assertEqual(status, 200, saved)
        after = self.render(note_id)
        self.assertNotEqual(after["version"], data["version"])
        self.assertIn("Mis à jour.", after["html"])
        for doc_id in (f"{self.CLIENT}/migration.md", "context/glossaire.md", f"{self.CLIENT}/state/actions.md"):
            other = self.render(doc_id)
            self.assertEqual((other["note"], other["version"]), (False, None), doc_id)
        self.assertEqual(self.render("context/glossaire.md")["project"], None)
        self.assertEqual(self.render(f"{self.CLIENT}/migration.md")["register"], self.register)


def load_script(relative, work):
    """Import a tools/ script as a module while WORK_DIR points to a temporary Work."""
    path = Path(__file__).resolve().parents[1] / relative
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(os.environ, {"WORK_DIR": str(work)}):
        spec.loader.exec_module(module)
    return module


class BrainSwitchTest(unittest.TestCase):
    """Several brains in one Work: discovery, `brain=` selection, isolated stores."""
    DEFAULT_PROJECT = "projects/internal/alpha"
    OTHER_PROJECT = "projects/internal/perso"

    def make_brain(self, name, prefix=None, title=None, boundary=None, agents=True, data=True):
        brain = self.root / name
        brain.mkdir(parents=True, exist_ok=True)
        if agents:
            (brain / "AGENTS.md").write_text("# Brain\n", encoding="utf-8")
        if data:
            (brain / ".data").mkdir(exist_ok=True)
        if boundary is not None:
            (brain / ".data/brain.json").write_text(boundary, encoding="utf-8")
        if prefix:
            project = self.DEFAULT_PROJECT if name == "brain" else self.OTHER_PROJECT
            (brain / project / "state").mkdir(parents=True)
            (brain / project / "state/actions.md").write_text(f"# Actions\n\n## Open\n- [ ] **{prefix}-001** — Jane — {title}\n", encoding="utf-8")
        else:
            (brain / "projects").mkdir(exist_ok=True)
        return brain

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)  # last: the servers are stopped first
        self.root = Path(self.temp.name) / "work"
        self.root.mkdir()
        self.default = self.make_brain("brain", "ALP", "Action du brain par défaut")
        self.other = self.make_brain("brain-perso", "PER", "Action perso",
                                     boundary='{"scope": "Personnel", "description": "Notes  et\\ncarrière", "version": 1}')
        self.make_brain("brain-acme", boundary='{"scope": 3, "description": ["x"]}')
        # Not brains: no AGENTS.md, no .data/, or a name outside `brain` / `brain-<name>`.
        self.make_brain("brain-vide", agents=False)
        self.make_brain("brain-sans-data", data=False)
        self.make_brain("brain_old")
        self.make_brain("brain-Majuscule")
        self.make_brain("brains")
        (self.root / "brain-fichier").write_text("pas un dossier", encoding="utf-8")
        self.server = self.start(tasks_web.Store(self.default))
        self.registers = {
            "default": self.default / self.DEFAULT_PROJECT / "state/actions.md",
            "other": self.other / self.OTHER_PROJECT / "state/actions.md",
        }

    def start(self, store, work=None):
        """Serve `store` as the default brain of a Work; the requests of the test then go to this server."""
        server = tasks_web.TaskServer(("127.0.0.1", 0), store, work=work or self.root)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.stop, server, thread)
        self.server = server
        self.base = f"http://127.0.0.1:{server.server_port}"
        return server

    @staticmethod
    def stop(server, thread):
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    def request(self, method, path, payload=None):
        return TasksWebTest.request(self, method, path, payload)

    def actions(self, query=""):
        status, data = self.request("GET", "/api/actions" + query)
        self.assertEqual(status, 200, data)
        return data

    def new_action(self, title="Nouvelle action", register=None, query=""):
        action = {"title": title, "owner": "Jane", "state": " ", "priority": "", "due": "", "scheduled": ""}
        return self.request("POST", "/api/actions" + query, {"register": register, "action": action})

    def test_brains_endpoint_lists_discovered_brains_with_scope_and_description(self):
        status, data = self.request("GET", "/api/brains")
        self.assertEqual(status, 200)
        self.assertEqual(data["default"], "brain")
        self.assertEqual(data["brains"], [
            {"name": "brain", "label": "Brain", "scope": "", "description": "", "default": True},
            {"name": "brain-acme", "label": "Acme", "scope": "", "description": "", "default": False},
            {"name": "brain-perso", "label": "Perso", "scope": "Personnel", "description": "Notes et carrière", "default": False},
        ])
        # No Store is built just to list the brains.
        self.assertEqual(self.server._stores, {})

    def test_brains_carry_a_short_label_but_keep_the_folder_name_as_value(self):
        self.make_brain("brain-acme-corp", "ACC", "Action du lot")
        by_name = {brain["name"]: brain for brain in self.request("GET", "/api/brains")[1]["brains"]}
        self.assertEqual({name: brain["label"] for name, brain in by_name.items()},
                         {"brain": "Brain", "brain-acme": "Acme", "brain-acme-corp": "Acme-corp", "brain-perso": "Perso"})
        # The label is only displayed: the folder name is what selects the brain.
        self.assertEqual(self.actions("?brain=brain-acme-corp")["actions"][0]["id"], "ACC-001")
        self.assertEqual(self.request("GET", "/api/actions?brain=Acme-corp")[0], 400)
        self.assertEqual(self.request("GET", "/api/actions?brain=Perso")[0], 400)
        self.assertEqual([tasks_web.brain_label(name) for name in ("brain", "brain-perso", "brain-studio", "brain-acme-corp", "brain-", "solo")],
                         ["Brain", "Perso", "Studio", "Acme-corp", "Brain-", "Solo"])

    def test_label_strips_the_brain_prefix_whichever_brain_is_the_default(self):
        self.assertEqual([tasks_web.brain_label(name) for name in ("brain-initech", "brain-perso", "brain")], ["Initech", "Perso", "Brain"])
        self.make_brain("brain-initech", "INI", "Action du brain renommé")
        (self.root / "work-config.local.json").write_text('{"version": 1, "defaultBrain": "brain-initech"}', encoding="utf-8")
        brains = self.request("GET", "/api/brains")[1]["brains"]
        self.assertEqual([(brain["name"], brain["label"]) for brain in brains],
                         [("brain-initech", "Initech"), ("brain", "Brain"), ("brain-acme", "Acme"), ("brain-perso", "Perso")])

    def test_brains_are_rediscovered_on_each_call(self):
        self.make_brain("brain-nouveau", "NEW", "Arrivé après le démarrage")
        names = [brain["name"] for brain in self.request("GET", "/api/brains")[1]["brains"]]
        self.assertEqual(names, ["brain", "brain-acme", "brain-nouveau", "brain-perso"])
        self.assertEqual(self.actions("?brain=brain-nouveau")["actions"][0]["id"], "NEW-001")
        (self.root / "brain-nouveau/AGENTS.md").unlink()
        names = [brain["name"] for brain in self.request("GET", "/api/brains")[1]["brains"]]
        self.assertNotIn("brain-nouveau", names)
        self.assertEqual(self.request("GET", "/api/actions?brain=brain-nouveau")[0], 400)

    def test_discovery_rule_is_the_one_of_the_other_tools(self):
        expected = [path.name for path in tasks_web.discover_brains(self.root)]
        self.assertEqual(expected, ["brain", "brain-acme", "brain-perso"])
        self.assertEqual([path.name for path in load_script("tools/brain/brain-state.py", self.root).discover()], expected)
        self.assertEqual([path.name for path in load_script("tools/machine/work_config.py", self.root).discover_brains()], expected)

    def test_default_brain_comes_first_and_follows_the_setting_or_the_rename(self):
        config = self.root / "work-config.local.json"
        config.write_text('{"version": 1, "defaultBrain": "brain-perso"}', encoding="utf-8")
        expected = ["brain-perso", "brain", "brain-acme"]
        self.assertEqual([path.name for path in tasks_web.discover_brains(self.root)], expected)
        self.assertEqual([path.name for path in load_script("tools/brain/brain-state.py", self.root).discover()], expected)
        self.assertEqual([path.name for path in load_script("tools/machine/work_config.py", self.root).discover_brains()], expected)
        with patch.object(tasks_web, "WORK", self.root):
            self.assertEqual(tasks_web.default_brain_dir(), self.root / "brain-perso")
        # A setting that cannot be applied leaves the brains by name instead of breaking the page.
        config.write_text('{"version": 1, "defaultBrain": "brain-nope"}', encoding="utf-8")
        self.assertEqual([path.name for path in tasks_web.discover_brains(self.root)], ["brain", "brain-acme", "brain-perso"])
        self.assertEqual(self.request("GET", "/api/brains")[0], 200)
        # Without setting, the folder `brain/` renamed: the other brains no longer lead, the choice is explicit.
        config.unlink()
        (self.root / "brain").rename(self.root / "brain-initech")
        self.assertEqual([path.name for path in tasks_web.discover_brains(self.root)], ["brain-acme", "brain-initech", "brain-perso"])
        config.write_text('{"version": 1, "defaultBrain": "brain-initech"}', encoding="utf-8")
        self.assertEqual([path.name for path in tasks_web.discover_brains(self.root)], ["brain-initech", "brain-acme", "brain-perso"])

    def test_default_brain_of_the_server_without_brain_option(self):
        with patch.object(tasks_web, "WORK", self.root):
            self.assertEqual(tasks_web.default_brain_dir(), self.root / "brain")
            (self.root / "brain").rename(self.root / "brain-initech")
            self.assertEqual(tasks_web.default_brain_dir(), self.root / "brain")  # several brains, no default: today's fallback
            for name in ("brain-perso", "brain-acme"):
                (self.root / name / "AGENTS.md").unlink()
            self.assertEqual(tasks_web.default_brain_dir(), self.root / "brain-initech")  # the only brain

    def test_default_brain_without_parameter_and_selected_brain_with_it(self):
        default = self.actions()
        self.assertEqual([action["id"] for action in default["actions"]], ["ALP-001"])
        self.assertEqual([register["path"] for register in default["registers"]], [f"{self.DEFAULT_PROJECT}/state/actions.md"])
        self.assertEqual(self.actions("?brain=brain"), default)
        other = self.actions("?brain=brain-perso")
        self.assertEqual([action["id"] for action in other["actions"]], ["PER-001"])
        self.assertEqual(other["actions"][0]["title"], "Action perso")
        self.assertEqual([register["path"] for register in other["registers"]], [f"{self.OTHER_PROJECT}/state/actions.md"])
        self.assertEqual(self.actions("?brain=brain-perso&x=1"), other)
        details = self.request("GET", "/api/actions/PER-001/details?brain=brain-perso")
        self.assertEqual(details[0], 200)
        self.assertEqual(self.request("GET", "/api/actions/PER-001/details")[0], 404)

    def test_stores_are_built_lazily_and_kept(self):
        self.assertEqual(self.server._stores, {})
        self.actions("?brain=brain-perso")
        store = self.server._stores["brain-perso"]
        self.assertIs(self.server.store_for("brain-perso"), store)
        self.assertIs(self.server.store_for(None), self.server.store)
        self.assertIs(self.server.store_for("brain"), self.server.store)
        self.assertEqual(store.brain, self.other.resolve())

    def test_unknown_brain_is_a_400_on_every_route(self):
        gets = ["/api/actions", "/api/actions/ALP-001/details", "/api/tools", "/api/notes", "/api/notes/content?id=x.md",
                "/api/search?q=alpha", "/api/docs/render?id=x.md", "/api/docs/recent", "/api/git", "/api/git/changes?path=a.md", "/api/undo"]
        for path in gets:
            joiner = "&" if "?" in path else "?"
            status, data = self.request("GET", f"{path}{joiner}brain=brain-inconnu")
            self.assertEqual((path, status), (path, 400))
            self.assertEqual(data, {"error": "Unknown brain."})
        before = {key: register.read_bytes() for key, register in self.registers.items()}
        with patch.object(tasks_web, "run_tool") as runner:
            for method, path, payload in (
                ("POST", "/api/actions?brain=brain-inconnu", {"register": f"{self.DEFAULT_PROJECT}/state/actions.md", "action": {}}),
                ("POST", "/api/actions/ALP-001/notes?brain=brain-inconnu", {"details_version": "x", "note": "n"}),
                ("POST", "/api/notes?brain=brain-inconnu", {"title": "t", "register": "inbox", "content": "c"}),
                ("PATCH", "/api/notes?brain=brain-inconnu", {"id": "a.md", "version": "x", "content": "c"}),
                ("PATCH", "/api/actions/ALP-001?brain=brain-inconnu", {"version": "x", "action": {}}),
                ("DELETE", "/api/actions/ALP-001?brain=brain-inconnu", {"version": "x", "details_version": "y"}),
                ("POST", "/api/undo?brain=brain-inconnu", {"label": "x"}),
                ("POST", "/api/tools/run?brain=brain-inconnu", {"id": "links"}),
                ("POST", "/api/git/save?brain=brain-inconnu", {"version": "0" * 32}),
                ("POST", "/api/git/send?brain=brain-inconnu", {"version": "0" * 32}),
            ):
                status, data = self.request(method, path, payload)
                self.assertEqual((method, path, status), (method, path, 400))
                self.assertEqual(data, {"error": "Unknown brain."})
            runner.assert_not_called()
        self.assertEqual({key: register.read_bytes() for key, register in self.registers.items()}, before)
        self.assertFalse((self.default / "inbox").exists() or (self.other / "inbox").exists())

    def test_only_discovered_names_are_accepted_never_paths(self):
        values = ["../x", "brain/../brain", "./brain", "brain/", "/brain", str(self.other), str(self.other.resolve()),
                  "brain-perso/../brain", "..", ".", "", " brain", "brain ", "BRAIN", "brain\x00", "brain-vide", "brain-sans-data",
                  "brain_old", "brain-Majuscule", "brains", "brain-fichier", "%2e%2e%2fx"]
        for value in values:
            status, data = self.request("GET", "/api/actions?brain=" + quote(value, safe=""))
            self.assertEqual((value, status), (value, 400))
            self.assertEqual(data, {"error": "Unknown brain."})
        # A repeated parameter is ambiguous: refused too.
        status, data = self.request("GET", "/api/actions?brain=brain&brain=brain-perso")
        self.assertEqual((status, data), (400, {"error": "Invalid brain parameter."}))
        status, _ = self.request("POST", "/api/actions?brain=../brain", {"register": f"{self.DEFAULT_PROJECT}/state/actions.md", "action": {}})
        self.assertEqual(status, 400)

    def test_a_brain_without_projects_folder_is_listed_but_not_served(self):
        empty = self.root / "brain-vide-de-projets"
        (empty / ".data").mkdir(parents=True)
        (empty / "AGENTS.md").write_text("# Brain\n", encoding="utf-8")
        self.assertIn("brain-vide-de-projets", [brain["name"] for brain in self.request("GET", "/api/brains")[1]["brains"]])
        status, data = self.request("GET", "/api/actions?brain=brain-vide-de-projets")
        self.assertEqual(status, 404)
        self.assertIn("projects", data["error"])
        self.assertNotIn(str(empty), data["error"])
        self.assertNotIn("brain-vide-de-projets", self.server._stores)

    def test_undo_stacks_are_isolated_per_brain(self):
        status, created = self.new_action("Dans le défaut", f"{self.DEFAULT_PROJECT}/state/actions.md")
        self.assertEqual((status, created["id"]), (201, "ALP-002"))
        self.assertEqual(created["undo"]["depth"], 1)
        status, created = self.new_action("Dans le perso", f"{self.OTHER_PROJECT}/state/actions.md", "?brain=brain-perso")
        self.assertEqual((status, created["id"]), (201, "PER-002"))
        self.assertEqual(created["undo"]["depth"], 1)
        self.new_action("Encore dans le perso", f"{self.OTHER_PROJECT}/state/actions.md", "?brain=brain-perso")
        self.assertEqual(self.request("GET", "/api/undo")[1]["depth"], 1)
        self.assertEqual(self.request("GET", "/api/undo")[1]["label"], self.request("GET", "/api/undo?brain=brain")[1]["label"])
        state = self.request("GET", "/api/undo?brain=brain-perso")[1]
        self.assertEqual((state["available"], state["depth"]), (True, 2))
        default_before = self.registers["default"].read_bytes()
        status, undone = self.request("POST", "/api/undo?brain=brain-perso", {"label": state["label"]})
        self.assertEqual(status, 200, undone)
        self.assertEqual(undone["undo"]["depth"], 1)
        self.assertEqual(self.registers["default"].read_bytes(), default_before)
        self.assertEqual([action["id"] for action in self.actions("?brain=brain-perso")["actions"]], ["PER-001", "PER-002"])
        self.assertEqual(self.request("GET", "/api/undo")[1]["depth"], 1)
        # An undo asked on the default brain only touches the default brain.
        perso_before = self.registers["other"].read_bytes()
        status, _ = self.request("POST", "/api/undo", {"label": self.request("GET", "/api/undo")[1]["label"]})
        self.assertEqual(status, 200)
        self.assertEqual([action["id"] for action in self.actions()["actions"]], ["ALP-001"])
        self.assertEqual(self.registers["other"].read_bytes(), perso_before)
        self.assertEqual(self.request("GET", "/api/undo")[1]["available"], False)
        self.assertEqual(self.request("GET", "/api/undo?brain=brain-perso")[1]["depth"], 1)

    def test_create_with_brain_writes_only_into_that_brain(self):
        default_before = self.registers["default"].read_bytes()
        status, created = self.new_action("Appel de la banque", f"{self.OTHER_PROJECT}/state/actions.md", "?brain=brain-perso")
        self.assertEqual((status, created["id"]), (201, "PER-002"))
        self.assertEqual(self.registers["default"].read_bytes(), default_before)
        self.assertIn("**PER-002**", self.registers["other"].read_text(encoding="utf-8"))
        self.assertIn("Appel de la banque", self.registers["other"].read_text(encoding="utf-8"))
        self.assertNotIn("PER-002", [action["id"] for action in self.actions()["actions"]])
        # A register of another brain is not a register of the selected one.
        other_before = self.registers["other"].read_bytes()
        status, data = self.new_action("Mauvais brain", f"{self.OTHER_PROJECT}/state/actions.md")
        self.assertEqual((status, data), (400, {"error": "Unknown project."}))
        status, data = self.new_action("Mauvais brain", f"{self.DEFAULT_PROJECT}/state/actions.md", "?brain=brain-perso")
        self.assertEqual((status, data), (400, {"error": "Unknown project."}))
        self.assertEqual(self.registers["other"].read_bytes(), other_before)
        self.assertEqual(self.registers["default"].read_bytes(), default_before)
        # The ID counter and the notes belong to the selected brain too.
        status, detail = self.request("GET", "/api/actions/PER-002/details?brain=brain-perso")
        self.assertEqual(status, 200)
        status, _ = self.request("POST", "/api/actions/PER-002/notes?brain=brain-perso", {"details_version": detail["details_version"], "note": "Rappelé"})
        self.assertEqual(status, 201)
        self.assertIn("Rappelé", self.registers["other"].read_text(encoding="utf-8"))
        self.assertNotIn("Rappelé", self.registers["default"].read_text(encoding="utf-8"))

    def test_notes_and_search_follow_the_selected_brain(self):
        note = self.other / self.OTHER_PROJECT / "notes/2026-10-01-banque.md"
        note.parent.mkdir()
        note.write_text("# Rendez-vous banque\n\nCompte épargne personnel.\n", encoding="utf-8")
        status, created = self.request("POST", "/api/notes?brain=brain-perso", {"title": "Idée vélo", "register": f"{self.OTHER_PROJECT}/state/actions.md", "content": "Texte"})
        self.assertEqual(status, 201, created)
        perso_notes = {item["id"] for item in self.request("GET", "/api/notes?brain=brain-perso")[1]["notes"]}
        self.assertIn(f"{self.OTHER_PROJECT}/notes/2026-10-01-banque.md", perso_notes)
        self.assertEqual(len(perso_notes), 2)
        self.assertEqual(self.request("GET", "/api/notes")[1]["notes"], [])
        found = self.request("GET", "/api/search?q=%C3%A9pargne&brain=brain-perso")[1]
        self.assertEqual([item["id"] for item in found["results"]], [f"{self.OTHER_PROJECT}/notes/2026-10-01-banque.md"])
        self.assertEqual(self.request("GET", "/api/search?q=%C3%A9pargne")[1]["results"], [])
        rendered = self.request("GET", f"/api/docs/render?id={quote(self.OTHER_PROJECT, safe='')}%2Fnotes%2F2026-10-01-banque.md&brain=brain-perso")
        self.assertEqual(rendered[0], 200)
        self.assertEqual(self.request("GET", f"/api/docs/render?id={quote(self.OTHER_PROJECT, safe='')}%2Fnotes%2F2026-10-01-banque.md")[0], 404)
        self.assertFalse((self.default / "inbox").exists())

    def test_tool_runs_receive_the_selected_brain(self):
        result = {"id": "links", "ok": True, "output": "OK", "truncated": False}
        with patch.object(tasks_web, "run_tool", return_value=result) as runner:
            self.assertEqual(self.request("POST", "/api/tools/run?brain=brain-perso", {"id": "links"})[0], 200)
            runner.assert_called_once_with("links", self.other.resolve())
            runner.reset_mock()
            self.assertEqual(self.request("POST", "/api/tools/run", {"id": "links"})[0], 200)
            runner.assert_called_once_with("links", self.default.resolve())
            runner.reset_mock()
            self.assertEqual(self.request("POST", "/api/tools/run?brain=brain", {"id": "links"})[0], 200)
            runner.assert_called_once_with("links", self.default.resolve())

    def test_run_tool_sets_brain_dir_for_the_command(self):
        completed = tasks_web.subprocess.CompletedProcess([], 0, stdout="ok\n", stderr="")
        with patch.object(tasks_web.shutil, "which", return_value="/usr/bin/uv"), \
                patch.object(tasks_web.subprocess, "run", return_value=completed) as runner:
            tasks_web.run_tool("links", self.other.resolve())
        self.assertEqual(runner.call_args.kwargs["env"]["BRAIN_DIR"], str(self.other.resolve()))
        self.assertEqual(runner.call_args.args[0][2], str(tasks_web.TOOLS_ROOT / "tools/brain/check-links.py"))

    def test_read_only_memory_tools_run_on_the_selected_brain(self):
        completed = tasks_web.subprocess.CompletedProcess([], 0, stdout="ok\n", stderr="")
        for tool_id, script, tail in (("map", "brain-state.py", ["map", "--brain", "brain-perso"]), ("timeline-roll", "timeline.py", ["roll"])):
            with self.subTest(tool=tool_id), patch.object(tasks_web.shutil, "which", return_value="/usr/bin/uv"), \
                    patch.object(tasks_web.subprocess, "run", return_value=completed) as runner:
                self.assertTrue(tasks_web.run_tool(tool_id, self.other.resolve())["ok"])
            command = runner.call_args.args[0]
            self.assertEqual(command, ["/usr/bin/uv", "run", str(tasks_web.TOOLS_ROOT / "tools/brain" / script), *tail])
            self.assertNotIn("--write", command)
            self.assertEqual(runner.call_args.kwargs["env"]["BRAIN_DIR"], str(self.other.resolve()))
            self.assertEqual(runner.call_args.kwargs["cwd"], tasks_web.WORK)

    def test_git_cards_follow_the_selected_brain_and_never_list_work(self):
        status, data = self.request("GET", "/api/git?brain=brain-perso")
        self.assertEqual(status, 200)
        self.assertEqual([(card["name"], card["label"]) for card in data["brains"]], [("brain-perso", "Perso"), ("brain", "Brain"), ("brain-acme", "Acme")])
        data = self.request("GET", "/api/git")[1]
        self.assertEqual([card["name"] for card in data["brains"]], ["brain", "brain-acme", "brain-perso"])
        # These brains are plain folders: saving is unavailable, said in one sentence, and the folders are left alone.
        self.assertEqual({card["state"] for card in data["brains"]}, {"unavailable"})
        self.assertNotIn("Work", [card["label"] for card in data["brains"]])
        self.assertEqual(self.request("POST", "/api/git/save?brain=brain-perso", {"version": "0" * 32})[0], 409)
        self.assertFalse((self.other / ".git").exists())

    def test_default_brain_can_be_another_discovered_brain(self):
        server = self.start(tasks_web.Store(self.other))
        status, data = self.request("GET", "/api/brains")
        self.assertEqual(status, 200)
        self.assertEqual(data["default"], "brain-perso")
        self.assertEqual([(brain["name"], brain["default"]) for brain in data["brains"]],
                         [("brain", False), ("brain-acme", False), ("brain-perso", True)])
        self.assertEqual([action["id"] for action in self.actions()["actions"]], ["PER-001"])
        self.assertEqual([action["id"] for action in self.actions("?brain=brain")["actions"]], ["ALP-001"])
        self.assertIs(server.store_for("brain-perso"), server.store)

    def test_default_brain_outside_work_is_offered_first(self):
        elsewhere = Path(self.temp.name) / "ailleurs/brain-externe"
        (elsewhere / "projects/internal/ext/state").mkdir(parents=True)
        (elsewhere / "projects/internal/ext/state/actions.md").write_text("# Actions\n\n## Open\n- [ ] **EXT-001** — Jane — Hors de Work\n", encoding="utf-8")
        self.start(tasks_web.Store(elsewhere))
        data = self.request("GET", "/api/brains")[1]
        self.assertEqual(data["default"], "brain-externe")
        self.assertEqual([(brain["name"], brain["default"]) for brain in data["brains"]],
                         [("brain-externe", True), ("brain", False), ("brain-acme", False), ("brain-perso", False)])
        self.assertEqual([action["id"] for action in self.actions()["actions"]], ["EXT-001"])
        self.assertEqual([action["id"] for action in self.actions("?brain=brain-externe")["actions"]], ["EXT-001"])
        self.assertEqual([action["id"] for action in self.actions("?brain=brain")["actions"]], ["ALP-001"])
        self.assertEqual([action["id"] for action in self.actions("?brain=brain-perso")["actions"]], ["PER-001"])

    def test_default_brain_outside_work_is_offered_alone_when_work_has_none(self):
        elsewhere = Path(self.temp.name) / "ailleurs/solo"
        (elsewhere / "projects/internal/ext/state").mkdir(parents=True)
        (elsewhere / "projects/internal/ext/state/actions.md").write_text("# Actions\n\n## Open\n- [ ] **EXT-001** — Jane — Seul\n", encoding="utf-8")
        empty_work = Path(self.temp.name) / "work-vide"
        empty_work.mkdir()
        self.start(tasks_web.Store(elsewhere), work=empty_work)
        data = self.request("GET", "/api/brains")[1]
        self.assertEqual(data, {"brains": [{"name": "solo", "label": "Solo", "scope": "", "description": "", "default": True}], "default": "solo"})
        self.assertEqual(self.request("GET", "/api/actions?brain=brain-perso")[0], 400)
        self.assertEqual(self.request("GET", "/api/actions?brain=solo")[0], 200)

    def test_default_brain_shadows_a_discovered_brain_of_the_same_name(self):
        elsewhere = Path(self.temp.name) / "ailleurs/brain"
        (elsewhere / "projects/internal/ext/state").mkdir(parents=True)
        (elsewhere / "projects/internal/ext/state/actions.md").write_text("# Actions\n\n## Open\n- [ ] **EXT-001** — Jane — Autre dossier\n", encoding="utf-8")
        self.start(tasks_web.Store(elsewhere))
        data = self.request("GET", "/api/brains")[1]
        self.assertEqual([brain["name"] for brain in data["brains"]], ["brain", "brain-acme", "brain-perso"])
        self.assertEqual(data["default"], "brain")
        self.assertEqual([action["id"] for action in self.actions("?brain=brain")["actions"]], ["EXT-001"])

    def test_brain_list_refuses_foreign_hosts_and_the_page_carries_the_switcher(self):
        request = Request(self.base + "/api/brains", headers={"Host": "evil.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        with urlopen(self.base + "/?brain=brain-perso", timeout=3) as response:
            page = response.read().decode("utf-8")
        for fragment in ('id="brainSwitch"', 'id="brainButton"', 'id="brainMenu"', 'id="brainStatic"'):
            self.assertIn(fragment, page)

    def test_scope_is_a_tooltip_of_the_brain_entry_not_a_second_line(self):
        with urlopen(self.base + "/", timeout=3) as response:
            page = response.read().decode("utf-8")
        static = TOOL.parent / "static"
        script, styles = (static / "app.js").read_text(encoding="utf-8"), (static / "app.css").read_text(encoding="utf-8")
        for text in (page, script, styles):
            self.assertNotIn("brainScope", text)
            self.assertNotIn("brainStaticScope", text)
            self.assertNotIn("brain-scope", text)
            self.assertNotIn("brain-option-scope", text)
        self.assertIn("option.title = brainTitle(brain);", script)
        self.assertIn("brain.scope ? `${brain.name} (${brain.scope})`", script)


class MarkdownToolbarTest(unittest.TestCase):
    """The Markdown toolbar of the note editors: its markup in the page, its tool table, and the text edits (run under node)."""
    STATIC = TOOL.parent / "static"
    EDITORS = {"newNoteToolbar": "newNoteContent", "docEditorToolbar": "docEditor"}
    # «…» marks the selection (an empty pair is a caret) before and after the edit.
    EDITS = [
        ("bold", "say «hi» now", "say **«hi»** now"),
        ("bold", "say «» now", "say **«»** now"),
        ("bold", "say **«hi»** now", "say «hi» now"),
        ("bold", "say «**hi**» now", "say «hi» now"),
        ("bold", "say **«»** now", "say «» now"),
        ("bold", "say« hi »now", "say **«hi»** now"),
        ("italic", "«hi»", "*«hi»*"),
        ("italic", "*«hi»*", "«hi»"),
        ("italic", "**«hi»**", "***«hi»***"),
        ("italic", "***«hi»***", "**«hi»**"),
        ("bold", "***«hi»***", "*«hi»*"),
        ("underline", "«hi»", "<u>«hi»</u>"),
        ("underline", "<u>«hi»</u>", "«hi»"),
        ("underline", "«<u>hi</u>»", "«hi»"),
        ("strike", "«hi»", "~~«hi»~~"),
        ("strike", "~~«hi»~~", "«hi»"),
        ("code", "«hi»", "`«hi»`"),
        ("code", "`«hi»`", "«hi»"),
        ("bullets", "«a\nb»", "«- a\n- b»"),
        ("bullets", "«- a\n- b»", "«a\nb»"),
        ("bullets", "a«»b", "- a«»b"),
        ("bullets", "«a\n\nb»", "«- a\n\n- b»"),
        ("bullets", "«- a\nb»", "«- a\n- b»"),
        ("bullets", "«a\nb\n»c", "«- a\n- b»\nc"),
        ("bullets", "\n«»a", "\n- «»a"),
        ("bullets", "«  - a»", "«  a»"),
        ("bullets", "«- [ ] a»", "«- a»"),
        ("numbers", "«a\nb\nc»", "«1. a\n2. b\n3. c»"),
        ("numbers", "«- a\n- b»", "«1. a\n2. b»"),
        ("numbers", "«1. a\n1. b\nc»", "«1. a\n2. b\n3. c»"),
        ("numbers", "«3. a\n7. b»", "«a\nb»"),
        ("numbers", "1. a\n2. b\nc«»", "1. a\n2. b\n3. c«»"),
        ("numbers", "«  a»", "«  1. a»"),
        ("tasks", "«a\nb»", "«- [ ] a\n- [ ] b»"),
        ("tasks", "«- [ ] a\n- [x] b»", "«a\nb»"),
        ("tasks", "«a\n- [x] b»", "«- [ ] a\n- [x] b»"),
        ("tasks", "«- a»", "«- [ ] a»"),
        ("quote", "«a\nb»", "«> a\n> b»"),
        ("quote", "«> a\n> b»", "«a\nb»"),
        ("quote", "«a\n\nb»", "«> a\n>\n> b»"),
        ("quote", "«»", "> «»"),
        ("link", "«hi»", "[hi](«url»)"),
        ("link", "a«»b", "a[text](«url»)b"),
        ("link", "say« hi »now", "say [hi](«url») now"),
        ("link", "«https://example.com/x»", "[«text»](https://example.com/x)"),
        ("link", "«[hi](https://example.com)»", "«hi»"),
        ("arrow", "a«»b", "a→«»b"),
        ("arrow", "a«b»c", "a→«»c"),
    ]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        brain = Path(self.temp.name) / "brain"
        (brain / "projects/clients/acme/missions/rollout/state").mkdir(parents=True)
        (brain / "projects/clients/acme/missions/rollout/state/actions.md").write_text("# Actions\n\n## Open\n- [ ] **ACM-001** — Jane — Prepare the globex demo\n", encoding="utf-8")
        self.server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(brain))
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(timeout=2)))
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        with urlopen(self.base + "/", timeout=3) as response:
            self.page = response.read().decode("utf-8")
        self.script = (self.STATIC / "app.js").read_text(encoding="utf-8")

    def test_both_note_editors_have_the_toolbar_right_above_their_text(self):
        self.assertEqual(sorted(re.findall(r'<div id="(\w+)" class="md-toolbar"', self.page)), sorted(self.EDITORS))
        for toolbar, field in self.EDITORS.items():
            with self.subTest(toolbar=toolbar):
                self.assertRegex(self.page, rf'<div id="{toolbar}" class="md-toolbar" role="toolbar" aria-label="Markdown formatting" aria-controls="{field}"[^>]*></div>\s*<textarea id="{field}"')
        self.assertEqual(sorted(re.findall(r"mountMarkdownToolbar\(ids\.(\w+), ids\.(\w+)\)", self.script)), sorted(self.EDITORS.items()))

    def test_the_history_note_form_of_an_action_has_no_toolbar(self):
        form = self.page[self.page.index('<div id="noteForm"'):self.page.index('<p id="noteError"')]
        self.assertIn('<textarea id="noteInput"', form)
        self.assertNotIn("toolbar", form)
        self.assertNotIn("md-toolbar", form)
        self.assertEqual(self.page.count('role="toolbar"'), 2)
        self.assertNotIn("noteInput", "".join(re.findall(r"mountMarkdownToolbar\([^)]*\)", self.script)))

    def test_the_text_edits_are_served_before_the_app(self):
        self.assertLess(self.page.index('src="/md-edit.js"'), self.page.index('src="/app.js"'))
        with urlopen(self.base + "/md-edit.js", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(response.headers["Content-Type"].startswith("text/javascript"))
            self.assertIn("const MarkdownEdit", response.read().decode("utf-8"))

    def test_every_button_has_a_label_an_icon_a_tool_and_the_shortcuts_stay_clear_of_the_app(self):
        table = self.script[self.script.index("const MD_TOOLS = ["):self.script.index("const MD_ARROWS")]
        tools = re.findall(r"\{id: '(\w+)', label: '([^']+)', icon: ICONS\.(\w+)(?:, key: '(\w)')?(, shift: true)?", table)
        icons = self.script[self.script.index("const ICONS = {"):self.script.index("function plural")]
        edits = (self.STATIC / "md-edit.js").read_text(encoding="utf-8")
        implemented = re.findall(r"^    (\w+)[:,]", edits[edits.index("const TOOLS = {"):edits.index("function edit(")], re.M)
        self.assertEqual(sorted(tool[0] for tool in tools), sorted(implemented))
        self.assertEqual(len(tools), 11)
        for _id, label, icon, _key, _shift in tools:
            self.assertTrue(label)
            self.assertRegex(icons, rf"\n  {icon}: '<")
        shortcuts = {(key, bool(shift)) for _id, _label, _icon, key, shift in tools if key}
        self.assertEqual(shortcuts, {("b", False), ("i", False), ("u", False), ("x", True), ("k", False)})
        # The app's own shortcuts with a modifier (⌘ Z, ⌘ Enter) differ from them; its single keys are ignored while typing.
        app_keys = {key.lower() for key in re.findall(r"\(event\.metaKey \|\| event\.ctrlKey\)[^\n]*?key(?:\.toLowerCase\(\))? === '(\w+)'", self.script)}
        self.assertEqual(app_keys, {"z", "enter"})
        self.assertTrue(app_keys.isdisjoint(key for key, _shift in shortcuts))
        self.assertRegex(self.script, r"function isTyping\(target\)")
        self.assertIn("aria-keyshortcuts", self.script)
        self.assertIn("setRangeText", self.script)
        self.assertIn("document.execCommand('insertText'", self.script)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_text_edits(self):
        script = """
          const edits = require(process.argv[1]);
          const cases = JSON.parse(require('fs').readFileSync(0, 'utf8'));
          process.stdout.write(JSON.stringify(cases.map(([tool, before]) => {
            const start = before.indexOf('«'), end = before.indexOf('»') - 1;
            const value = before.replace('«', '').replace('»', '');
            const out = edits.apply(value, edits.edit(tool, value, start, end));
            return out.value.slice(0, out.start) + '«' + out.value.slice(out.start, out.end) + '»' + out.value.slice(out.end);
          })));
        """
        done = subprocess.run(["node", "-e", script, str(self.STATIC / "md-edit.js")], input=json.dumps(self.EDITS), capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        for (tool, before, expected), got in zip(self.EDITS, json.loads(done.stdout), strict=True):
            with self.subTest(tool=tool, before=before):
                self.assertEqual(got, expected)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_the_arrow_tool_inserts_the_chosen_symbol_and_exposes_every_tool(self):
        script = """
          const edits = require(process.argv[1]);
          const out = edits.apply('a b', edits.edit('arrow', 'a b', 1, 1, '⇒'));
          process.stdout.write(JSON.stringify([out.value, edits.tools]));
        """
        done = subprocess.run(["node", "-e", script, str(self.STATIC / "md-edit.js")], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        value, tools = json.loads(done.stdout)
        self.assertEqual(value, "a⇒ b")
        self.assertEqual(len(tools), 11)


def node_json(script, payload=None):
    """Run `script` under node (the module path is `process.argv[1]`, the payload is JSON on stdin) and return its JSON output."""
    done = subprocess.run(["node", "-e", script, str(TOOL.parent / "static/timeline-view.js")], input=json.dumps(payload), capture_output=True, text=True, timeout=30)
    if done.returncode:
        raise AssertionError(done.stderr)
    return json.loads(done.stdout)


class TimelineViewTest(unittest.TestCase):
    """The Timeline view: its markup and wiring in the page, and the logic of timeline-view.js (run under node)."""
    STATIC = TOOL.parent / "static"
    ACM = "projects/clients/acme/missions/rollout/state/actions.md"
    GLO = "projects/clients/globex/missions/pilot/state/actions.md"
    SET = "projects/internal/setup/state/actions.md"
    LAB = "projects/clients/initech/missions/lab/state/actions.md"
    TODAY = "2026-10-25"  # a Sunday; the default range is then 2026-10-12 to 2026-11-22

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        brain = Path(self.temp.name) / "brain"
        (brain / "projects/clients/acme/missions/rollout/state").mkdir(parents=True)
        (brain / "projects/clients/acme/missions/rollout/state/actions.md").write_text("# Actions\n\n## Open\n- [ ] **ACM-001** — Jane Doe — Prepare the globex demo 📅 2026-10-30\n", encoding="utf-8")
        server = tasks_web.TaskServer(("127.0.0.1", 0), tasks_web.Store(brain))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (server.shutdown(), server.server_close(), thread.join(timeout=2)))
        self.base = f"http://127.0.0.1:{server.server_port}"
        with urlopen(self.base + "/", timeout=3) as response:
            self.page = response.read().decode("utf-8")
        self.script = (self.STATIC / "app.js").read_text(encoding="utf-8")
        self.styles = (self.STATIC / "app.css").read_text(encoding="utf-8")

    def test_timeline_is_a_sidebar_view_right_after_the_board(self):
        views = re.findall(r'<button id="(\w+)" class="nav-item[^"]*" type="button" data-view="(\w+)" title="([^"]*)"', self.page)
        self.assertEqual([view for _id, view, _title in views], ["today", "list", "board", "timeline", "notes", "search", "tools", "git"])
        titles = {view: title for _id, view, title in views}
        self.assertEqual([titles[view] for view in ("timeline", "notes", "search")], ["Timeline (4)", "Notes (5)", "Search (6)"])
        self.assertIn('<button id="timelineButton"', self.page)
        self.assertIn("<kbd>1</kbd> to <kbd>6</kbd></dt><dd>Today, Actions, Board, Timeline, Notes, Search", self.page)
        self.assertIn("<kbd>Alt</kbd> <kbd>←</kbd> <kbd>→</kbd></dt><dd>On the Timeline: move the deadline by a day", self.page)

    def test_keyboard_scheme_follows_the_sidebar_order(self):
        self.assertIn("const VIEWS = ['today', 'list', 'board', 'timeline', 'notes', 'search', 'tools', 'git'];", self.script)
        self.assertIn("setView(['today', 'list', 'board', 'timeline', 'notes', 'search'][Number(digit) - 1]);", self.script)
        self.assertIn("/^[1-6]$/.test(key)", self.script)
        self.assertIn("/^Digit[1-6]$/.test(event.code)", self.script)
        # The timeline is an action view: filters, j/k, Enter, the detail panel and the quick edits work there as in the list and the board.
        self.assertRegex(self.script, r"const ACTION_VIEWS = \[[^\]]*'timeline'[^\]]*\];")
        self.assertIn("timeline: 'timelineButton'", self.script)

    def test_timeline_markup(self):
        view = self.page[self.page.index('<div id="timelineView"'):self.page.index('<div id="docsView"')]
        self.assertTrue(view.startswith('<div id="timelineView" class="timeline-view" aria-label="Timeline" hidden>'))
        self.assertLess(self.page.index('<div id="boardView"'), self.page.index('<div id="timelineView"'))
        self.assertEqual(re.findall(r'data-range="(\w+)" aria-pressed="false"', view), ["two", "six", "quarter"])
        for fragment in ('id="timelineToday"', 'id="timelineBack"', 'id="timelineForward"', 'id="timelineLate"', 'id="timelineScale"',
                         'id="timelineDone" class="tl-switch" type="button" role="switch" aria-checked="false"',
                         '<div id="timelineSummary" class="tl-summary" role="group" aria-label="Deadlines at a glance"></div>',
                         '<div id="timelineScroll" class="tl-scroll" role="region" aria-label="Timeline frieze"></div>'):
            self.assertIn(fragment, view)
        # The tray of the actions with no deadline sits under the frieze: collapsible, searchable, with its list.
        self.assertLess(view.index('id="timelineScroll"'), view.index('id="timelineTray"'))
        self.assertIn('<section id="timelineTray" class="tl-tray" aria-labelledby="timelineTrayTitle" hidden>', view)
        self.assertIn('<button id="timelineTrayToggle" class="tl-tray-toggle" type="button" aria-expanded="true" aria-controls="timelineTrayBody">', view)
        self.assertIn('<input id="timelineTraySearch" type="search"', view)
        self.assertIn("Search the actions without a deadline", view)
        self.assertIn('id="timelineTrayBody"', view)
        self.assertIn('id="timelineTrayList"', view)
        self.assertIn("Show done", view)
        self.assertNotIn("timelineVague", self.page)
        # The Status filter does not apply there: "Show done" is its equivalent.
        self.assertIn("(view === 'list' || view === 'board')", self.script)

    def test_timeline_scripts_are_served_before_the_app(self):
        self.assertLess(self.page.index('src="/timeline-view.js"'), self.page.index('src="/app.js"'))
        self.assertLess(self.page.index('src="/md-edit.js"'), self.page.index('src="/app.js"'))
        with urlopen(self.base + "/timeline-view.js", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertTrue(response.headers["Content-Type"].startswith("text/javascript"))
            self.assertIn("const TimelineView", response.read().decode("utf-8"))

    def test_chips_are_focusable_lists_with_full_names_and_the_page_respects_reduced_motion(self):
        for fragment in ("role', 'list'", "role', 'listitem'", "button.setAttribute('aria-label', entryName(entry));", "TimelineView.neighbour(",
                         "(prefers-reduced-motion: reduce)", "ids.timelineScroll.addEventListener('keydown', timelineKey);", "ids.timelineTray.addEventListener('keydown', trayKey);"):
            self.assertIn(fragment, self.script)
        for part in ("`Status: ${statusLabel(action.state)}`", "`Due ${dayText(entry.date)}", "`Scheduled ${dayText(entry.scheduled)}`", "`Owner: ${action.owner}`"):
            self.assertIn(part, self.script)
        for selector in (".tl-chip:focus-visible", ".tl-card-main:focus-visible", ".tl-shade", ".tl-today", ".timeline-view.is-agenda", ".tl-cell.is-overdue", ".tl-cell.is-done",
                         ".tl-marker", ".tl-late", ".tl-stat", ".tl-tray", ".tl-drop"):
            self.assertIn(selector, self.styles)
        # Dates are formatted like the rest of the app (the browser's locale, through the shared formatters), never capitalised by the style.
        self.assertIn("new Intl.DateTimeFormat(LOCALE,", self.script)
        self.assertNotIn("text-transform: capitalize", self.styles)

    def test_planning_by_dragging_and_by_keyboard_goes_through_the_due_date_update(self):
        # A chip or a tray card is dragged onto a day, a chip back onto the tray; Alt+arrows move the deadline; all of them are `updateDue`,
        # the write of the quick edit (the same request as the detail panel, with its undo toast).
        for fragment in ("cell.draggable = true;", "item.draggable = true;", "startTimelineDrag(event, action, 'chip')", "startTimelineDrag(event, action, 'card')",
                         "updateDue(action, target.day.iso)", "updateDue(action, '')", "event.altKey && (event.key === 'ArrowLeft' || event.key === 'ArrowRight')",
                         "TimelineView.moveDue(action.due,", "if (pendingWrites > 0) return;", "openDueMenu(action, date)"):
            self.assertIn(fragment, self.script)
        # Clicking an empty day starts a new action in that project, due that day, through the existing form.
        self.assertIn("openEditor(null, {register: event.target.closest('.tl-lane').dataset.register, due: target.day.iso});", self.script)
        self.assertIn("ids.editorDue.value = action?.due || (!action && preset?.due) || '';", self.script)
        # A plain wheel scrolls sideways when that is the only way to scroll.
        self.assertIn("ids.timelineScroll.addEventListener('wheel'", self.script)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_dates_weekends_and_iso_weeks(self):
        got = node_json("""
          const T = require(process.argv[1]);
          process.stdout.write(JSON.stringify({
            weekdays: ['2026-10-26', '2026-10-31', '2026-11-01'].map(day => [T.weekday(day), T.isWeekend(day)]),
            mondays: ['2026-10-25', '2026-10-26', '2027-01-03'].map(T.mondayOf),
            weeks: ['2026-01-01', '2026-12-31', '2027-01-03', '2027-01-04', '2024-12-30', '2021-01-03', '2020-12-31'].map(T.isoWeek),
            added: [T.addDays('2026-02-27', 2), T.addDays('2028-02-28', 1), T.addDays('2026-12-31', 1), T.addDays('2026-03-29', 1), T.addDays('2026-10-26', -7)],
            diffs: [T.diffDays('2026-10-25', '2026-11-01'), T.diffDays('2026-11-01', '2026-10-25'), T.diffDays('2026-03-28', '2026-03-30'), T.diffDays('2026-10-25', '2026-10-25')],
            plain: ['2026-10-25', '2026-02-30', '2026-1-5', 'week of 05/10', '', null, undefined, 20261025, '0050-01-01', '2026-10-25 '].map(T.isPlainDate),
            moves: [T.moveDue('2026-10-31', 1), T.moveDue('2026-10-31', -7), T.moveDue('2026-12-31', 1), T.moveDue('', 1), T.moveDue('week of 05/10', 1), T.moveDue(null, 1)]
          }));
        """)
        self.assertEqual(got["weekdays"], [[0, False], [5, True], [6, True]])
        self.assertEqual(got["mondays"], ["2026-10-19", "2026-10-26", "2026-12-28"])
        self.assertEqual(got["weeks"], [{"year": 2026, "week": 1}, {"year": 2026, "week": 53}, {"year": 2026, "week": 53}, {"year": 2027, "week": 1},
                                        {"year": 2025, "week": 1}, {"year": 2020, "week": 53}, {"year": 2020, "week": 53}])
        self.assertEqual(got["added"], ["2026-03-01", "2028-02-29", "2027-01-01", "2026-03-30", "2026-10-19"])
        self.assertEqual(got["diffs"], [7, -7, 2, 0])
        self.assertEqual(got["plain"], [True, False, False, False, False, False, False, False, False, False])
        # A deadline moves by calendar days (across a month and a year); no plain date, nothing to move.
        self.assertEqual(got["moves"], ["2026-11-01", "2026-10-24", "2027-01-01", None, None, None])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_ranges_start_on_the_monday_of_last_week_and_cover_whole_weeks(self):
        got = node_json("""
          const T = require(process.argv[1]);
          const brief = r => ({key: r.key, weeks: r.weeks, start: r.start, end: r.end, days: r.days.length, months: r.months, weekSpans: r.weekSpans.map(w => `${w.year}W${w.week}+${w.span}`),
            weekend: r.days.map(d => d.weekend ? 1 : 0).join(''), today: r.days.filter(d => d.today).map(d => d.index)});
          process.stdout.write(JSON.stringify({
            ranges: T.ranges, six: brief(T.range('2026-10-25')), two: brief(T.range('2026-10-25', 'two')), quarter: brief(T.range('2026-10-25', 'quarter')),
            unknown: T.range('2026-10-25', 'year').key, monday: T.range('2026-10-26').start, newYear: brief(T.range('2026-12-30', 'quarter')),
            first: T.range('2026-10-25').days[13]
          }));
        """)
        self.assertEqual(got["ranges"], ["two", "six", "quarter"])
        six = got["six"]
        self.assertEqual((six["key"], six["weeks"], six["start"], six["end"], six["days"]), ("six", 6, "2026-10-12", "2026-11-22", 42))
        self.assertEqual(six["weekend"], "0000011" * 6)
        self.assertEqual(six["today"], [13])
        self.assertEqual(six["months"], [{"year": 2026, "month": 10, "start": 0, "span": 20}, {"year": 2026, "month": 11, "start": 20, "span": 22}])
        self.assertEqual(six["weekSpans"], [f"2026W{week}+7" for week in range(42, 48)])
        self.assertEqual((got["two"]["end"], got["two"]["days"], got["two"]["today"]), ("2026-10-25", 14, [13]))
        self.assertEqual((got["quarter"]["end"], got["quarter"]["days"], got["quarter"]["weeks"]), ("2027-01-10", 91, 13))
        self.assertEqual(got["unknown"], "six")
        self.assertEqual(got["monday"], "2026-10-19")
        new_year = got["newYear"]
        self.assertEqual((new_year["start"], new_year["end"]), ("2026-12-21", "2027-03-21"))
        self.assertEqual(new_year["weekSpans"][:4], ["2026W52+7", "2026W53+7", "2027W1+7", "2027W2+7"])
        self.assertEqual([(month["year"], month["month"], month["span"]) for month in new_year["months"]], [(2026, 12, 11), (2027, 1, 31), (2027, 2, 28), (2027, 3, 21)])
        self.assertEqual(got["first"], {"iso": "2026-10-25", "index": 13, "weekday": 6, "weekend": True, "today": True, "year": 2026, "month": 10, "day": 25, "week": 43, "weekYear": 2026})

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_two_and_six_weeks_fit_the_width_and_a_quarter_compresses_to_week_ticks(self):
        got = node_json("""
          const T = require(process.argv[1]);
          const brief = sc => ({dayW: Number(sc.dayW.toFixed(2)), endW: Number(sc.endW.toFixed(2)), total: sc.total, overflow: sc.overflow, density: sc.density, days: sc.days,
            increasing: sc.xs.every((x, i) => i === 0 || x > sc.xs[i - 1]), first: sc.xs.slice(0, 8)});
          const six = T.scale({width: 1192, weeks: 6, key: 'six'});
          process.stdout.write(JSON.stringify({
            six: brief(six), two: brief(T.scale({width: 1192, weeks: 2, key: 'two'})), quarter: brief(T.scale({width: 1192, weeks: 13, key: 'quarter'})),
            narrowSix: brief(T.scale({width: 776, weeks: 6, key: 'six', labelW: 124, lateW: 120})), tooNarrow: brief(T.scale({width: 500, weeks: 6, key: 'six'})),
            slim: brief(T.scale({width: 1192, weeks: 6, key: 'six', lateW: 44})),
            at: [T.dayAt(six, 0), T.dayAt(six, six.xs[5]), T.dayAt(six, six.xs[5] - 1), T.dayAt(six, six.xs[6]), T.dayAt(six, six.total - 1), T.dayAt(six, six.total), T.dayAt(six, -1), T.dayAt(six, NaN)]
          }));
        """)
        # 1192 px, less 150 for the projects and 148 for the overdue zone, shared by 30 weekdays and 12 weekend days at three quarters of one.
        six = got["six"]
        self.assertEqual((six["total"], six["overflow"], six["density"], six["days"]), (894, False, "day", 42))
        self.assertAlmostEqual(six["dayW"], 894 / 39, places=2)
        self.assertAlmostEqual(six["endW"] / six["dayW"], 0.75, places=2)
        self.assertEqual(six["first"], [0, 23, 46, 69, 92, 115, 132, 149])
        self.assertTrue(six["increasing"])
        self.assertEqual((got["two"]["total"], got["two"]["overflow"], got["two"]["density"]), (894, False, "day"))
        self.assertGreater(got["two"]["dayW"], 60)
        quarter = got["quarter"]
        self.assertEqual((quarter["total"], quarter["overflow"], quarter["density"], quarter["days"]), (894, False, "week", 91))
        self.assertTrue(quarter["increasing"])
        self.assertEqual((got["narrowSix"]["total"], got["narrowSix"]["overflow"]), (532, False))
        # Only when even the narrowest day would not fit does the frieze scroll.
        self.assertEqual((got["tooNarrow"]["overflow"], got["tooNarrow"]["dayW"]), (True, 12))
        self.assertGreater(got["tooNarrow"]["total"], 202)
        self.assertGreater(got["slim"]["dayW"], six["dayW"])  # an empty overdue zone gives its room to the days
        # The day under a pointer, from the left edge of the days.
        self.assertEqual(got["at"], [0, 5, 4, 6, 41, -1, -1, -1])

    def fixture(self):
        def action(id_, register, project, **fields):
            return {"id": id_, "state": " ", "owner": "Jane Doe", "title": f"Title of {id_}", "register": register, "project": project, "priority": "",
                    "due": "", "scheduled": "", "done": "", "due_note": "", **fields}
        acme = (self.ACM, "acme / rollout")
        globex = (self.GLO, "globex / pilot")
        return [
            action("ACM-001", *acme, due="2026-10-30", scheduled="2026-10-27"),
            action("ACM-002", *acme, due="2026-10-30"),
            action("ACM-003", *acme, due="2026-10-03"),
            action("ACM-004", *acme, state="/", due="2026-10-17"),
            action("ACM-005", *acme, state="x", due="2026-10-31", done="2026-10-20"),
            action("ACM-006", *acme, due_note="week of 05/10"),
            action("ACM-007", *acme),
            action("ACM-008", *acme, due="2027-02-01"),
            action("ACM-009", *acme, state="-", due="2026-10-25"),
            action("ACM-010", *acme, due="semaine du 05/10"),
            action("ACM-011", *acme, scheduled="2026-10-27"),
            action("ACM-012", *acme, due="2026-10-26", scheduled="2026-10-26"),
            action("ACM-013", *acme, state="x", due="2026-10-01", done="2026-09-01"),
            action("ACM-014", *acme, state="x", due="2026-10-21"),
            action("ACM-015", *acme, due="2026-11-20"),
            action("GLO-001", *globex, state="w", due="2026-10-24"),
            action("GLO-002", *globex, due="2026-10-25"),
            action("SET-001", self.SET, "internal / setup"),
            action("SET-002", self.SET, "internal / setup", owner="John Smith", priority="⏫"),
            action("LAB-001", self.LAB, "initech / lab", state="-"),
        ]

    # Lanes in register order (globex, acme, internal, initech), as the page gives them; the axis is the one of a 1192 px page.
    SETUP = """
      const T = require(process.argv[1]);
      const {actions, showDone} = JSON.parse(require('fs').readFileSync(0, 'utf8'));
      const range = T.range('2026-10-25');
      const sc = T.scale({width: 1192, weeks: 6, key: 'six'});
      const order = ['projects/clients/globex/missions/pilot/state/actions.md', 'projects/clients/acme/missions/rollout/state/actions.md',
        'projects/internal/setup/state/actions.md', 'projects/clients/initech/missions/lab/state/actions.md'];
      const result = T.layout(actions, {today: '2026-10-25', start: range.start, end: range.end, showDone, order, scale: sc, chipW: 132});
    """
    LAYOUT = SETUP + """
      const entry = e => [e.id, e.column, e.track, e.x, e.w, e.flip, e.overdue, e.done, e.sched, e.marker && e.marker.x];
      process.stdout.write(JSON.stringify({
        lanes: result.lanes.map(lane => ({project: lane.project, tracks: lane.tracks, lateTracks: lane.lateTracks, open: lane.open, undated: lane.undated, entries: lane.entries.map(entry)})),
        late: result.late.map(e => e.id), later: result.later.map(a => a.id), total: result.total
      }));
    """

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_layout_gives_every_project_with_open_actions_a_lane_and_places_the_dated_ones(self):
        got = node_json(self.LAYOUT, {"actions": self.fixture(), "showDone": False})
        # A lane for every project that has an open action, dated or not (setup has none dated); none for initech, whose only action is cancelled.
        self.assertEqual([lane["project"] for lane in got["lanes"]], ["globex / pilot", "acme / rollout", "internal / setup"])
        globex, acme, setup = got["lanes"]
        # Each lane counts its open actions and the undated ones among them (a vague wording, a text due date, a scheduled date alone, nothing).
        self.assertEqual((globex["open"], globex["undated"], acme["open"], acme["undated"], setup["open"], setup["undated"]), (2, 0, 11, 4, 2, 2))
        self.assertEqual((setup["tracks"], setup["entries"]), (0, []))
        # A chip starts on its day (x is the left edge of its column) and runs 132 px to the right: the two of globex overlap, so they stack.
        self.assertEqual(globex["tracks"], 2)
        self.assertEqual(globex["entries"], [["GLO-001", 12, 0, 264, 132, False, 1, False, "", None], ["GLO-002", 13, 1, 281, 132, False, 0, False, "", None]])
        # Acme, by date then ID: ACM-003 is before the range (the overdue zone, column -1, stacked there), ACM-004 is a Saturday and overdue,
        # ACM-012 is scheduled the day it is due (an hourglass on the chip, no marker), ACM-001 is scheduled on the 27th (a marker at its
        # day, joined to the chip) and shares its day with ACM-002 (a third track), ACM-015 is on the last week and would leave the range
        # to the right: it ends on its day instead (flip).
        self.assertEqual(acme["tracks"], 3)
        self.assertEqual(acme["lateTracks"], 1)
        self.assertEqual(acme["entries"], [
            ["ACM-003", -1, 0, 0, 0, False, 22, False, "", None], ["ACM-004", 5, 0, 115, 132, False, 8, False, "", None],
            ["ACM-012", 14, 0, 298, 132, False, 0, False, "same", None], ["ACM-001", 18, 1, 390, 132, False, 0, False, "before", 333],
            ["ACM-002", 18, 2, 390, 132, False, 0, False, "", None], ["ACM-015", 39, 0, 728, 132, True, 0, False, "", None]])
        self.assertEqual(got["late"], ["ACM-003"])
        self.assertEqual(got["later"], ["ACM-008"])
        self.assertEqual(got["total"], 8)
        shown = {entry[0] for lane in got["lanes"] for entry in lane["entries"]}
        self.assertTrue({"ACM-005", "ACM-006", "ACM-007", "ACM-009", "ACM-010", "ACM-011", "ACM-013", "ACM-014", "LAB-001"}.isdisjoint(shown))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_done_actions_show_on_request_at_their_done_date(self):
        got = node_json(self.LAYOUT, {"actions": self.fixture(), "showDone": True})
        acme = got["lanes"][1]["entries"]
        done = {entry[0]: entry for entry in acme if entry[7]}
        # At the done date when there is one (the 20th, column 8), else at the due date (the 21st); never before the range or as late;
        # the cancelled action is still left out.
        self.assertEqual(set(done), {"ACM-005", "ACM-014"})
        self.assertEqual((done["ACM-005"][1], done["ACM-005"][6]), (8, 0))
        self.assertEqual((done["ACM-014"][1], done["ACM-014"][6]), (9, 0))
        self.assertEqual(got["late"], ["ACM-003"])
        self.assertEqual(got["total"], 10)
        self.assertNotIn("ACM-009", {entry[0] for entry in acme})

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_summary_counts_and_spotlights(self):
        got = node_json(self.SETUP + """
          const spots = ['overdue', 'week', 'next'].map(kind => actions.filter(a => T.inSpot(a, kind, '2026-10-25')).map(a => a.id));
          process.stdout.write(JSON.stringify({summary: T.summary(actions, '2026-10-25'), spots, other: T.inSpot(actions[0], 'unknown', '2026-10-25'),
            monday: T.summary(actions, '2026-10-26')}));
        """, {"actions": self.fixture(), "showDone": False})
        # Today is a Sunday: this week is today alone, the next two weeks are the 26th to the 8th. Open actions only: done, cancelled and
        # (for the counts of dates) the undated are not in them.
        self.assertEqual(got["summary"], {"today": "2026-10-25", "weekEnd": "2026-10-25", "nextStart": "2026-10-26", "nextEnd": "2026-11-08",
                                          "overdue": 3, "week": 1, "next": 3, "vague": 2, "none": 4})
        self.assertEqual(got["spots"], [["ACM-003", "ACM-004", "GLO-001"], ["GLO-002"], ["ACM-001", "ACM-002", "ACM-012"]])
        self.assertFalse(got["other"])
        # On a Monday the week is seven days: the 26th is "this week", and the next two weeks start on the 2nd.
        self.assertEqual((got["monday"]["weekEnd"], got["monday"]["nextStart"], got["monday"]["week"], got["monday"]["next"]), ("2026-11-01", "2026-11-02", 3, 0))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_tray_lists_open_actions_without_a_date_by_project(self):
        got = node_json(self.SETUP + """
          const brief = data => ({counts: data.counts, vague: data.vague.map(g => [g.project, g.items.map(i => [i.action.id, i.text])]), none: data.none.map(g => [g.project, g.items.map(i => i.action.id)])});
          process.stdout.write(JSON.stringify({all: brief(T.tray(actions, {order})), john: brief(T.tray(actions, {query: 'john', order})), week: brief(T.tray(actions, {query: 'WEEK of', order})),
            project: brief(T.tray(actions, {query: 'acme rollout', order})), nothing: brief(T.tray(actions, {query: 'zzzz', order}))}));
        """, {"actions": self.fixture(), "showDone": False})
        # Vague deadlines first, then the rest; groups in register order; in a group the in-progress, then the to do, by priority, then ID.
        self.assertEqual(got["all"], {"counts": {"vague": 2, "none": 4},
                                      "vague": [["acme / rollout", [["ACM-006", "week of 05/10"], ["ACM-010", "semaine du 05/10"]]]],
                                      "none": [["acme / rollout", ["ACM-007", "ACM-011"]], ["internal / setup", ["SET-002", "SET-001"]]]})
        self.assertEqual(got["john"]["none"], [["internal / setup", ["SET-002"]]])
        self.assertEqual(got["john"]["counts"], {"vague": 0, "none": 1})
        self.assertEqual(got["week"]["vague"], [["acme / rollout", [["ACM-006", "week of 05/10"]]]])
        self.assertEqual(got["project"]["counts"], {"vague": 2, "none": 2})
        self.assertEqual(got["nothing"]["counts"], {"vague": 0, "none": 0})

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_initials_for_chips_of_other_owners(self):
        got = node_json("""
          const T = require(process.argv[1]);
          process.stdout.write(JSON.stringify(['Jane Doe', 'John Smith', 'Marie-Claire de la Poe', 'Mary', 'Zoe', '', '  Sam   Poe  ', null].map(T.initials)));
        """)
        self.assertEqual(got, ["JD", "JS", "MP", "MA", "ZO", "", "SP", ""])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_arrow_keys_walk_a_project_by_date_and_change_project_on_the_closest_date(self):
        got = node_json(self.SETUP + """
          const moves = [['ACM-001', 'right'], ['ACM-001', 'left'], ['ACM-001', 'up'], ['ACM-001', 'down'], ['GLO-002', 'down'], ['GLO-001', 'up'], ['ACM-002', 'home'],
            ['ACM-003', 'end'], ['ACM-003', 'left'], ['ACM-015', 'right'], ['ACM-001', 'sideways'], ['NOPE-1', 'right'], ['ACM-015', 'down']];
          process.stdout.write(JSON.stringify({moves: moves.map(([id, direction]) => T.neighbour(result.lanes, id, direction))}));
        """, {"actions": self.fixture(), "showDone": False})
        # Up and down skip the lane that has no chip (setup): nothing under acme, and globex above it is reached on the closest date.
        self.assertEqual(got["moves"], ["ACM-002", "ACM-012", "GLO-002", None, "ACM-012", None, "ACM-003", "ACM-015", None, None, None, None, None])

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_agenda_lists_each_day_with_its_chips_and_markers(self):
        got = node_json(self.SETUP.replace("scale: sc, chipW: 132", "scale: null") + """
          const agenda = T.agenda(result, range.days);
          process.stdout.write(JSON.stringify({days: agenda.length,
            agenda: agenda.filter(d => d.entries.length || d.markers.length).map(d => [d.day.iso, d.entries.map(e => e.id), d.markers.map(e => e.id)])}));
        """, {"actions": self.fixture(), "showDone": False})
        self.assertEqual(got["days"], 42)
        self.assertEqual(got["agenda"], [["2026-10-17", ["ACM-004"], []], ["2026-10-24", ["GLO-001"], []], ["2026-10-25", ["GLO-002"], []],
                                         ["2026-10-26", ["ACM-012"], []], ["2026-10-27", [], ["ACM-001"]], ["2026-10-30", ["ACM-001", "ACM-002"], []],
                                         ["2026-11-20", ["ACM-015"], []]])


if __name__ == "__main__":
    unittest.main()
