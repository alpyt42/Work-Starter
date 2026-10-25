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
import subprocess
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


class GitViewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.brain = root / "brain"
        (self.brain / "projects").mkdir(parents=True)
        self.work = root / "work"
        self.work.mkdir()
        self.nogit = root / "nogit"
        self.nogit.mkdir()
        self.git("init", "-q", "-b", "main")
        (self.work / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
        (self.work / "b.txt").write_text("keep\n", encoding="utf-8")
        (self.work / "gone.txt").write_text("bye\nbye\n", encoding="utf-8")
        (self.work / "old.txt").write_text("".join(f"line {n}\n" for n in range(20)), encoding="utf-8")
        (self.work / "both.txt").write_text("x\n", encoding="utf-8")
        (self.work / ".env.prod").write_text("TOKEN=1\n", encoding="utf-8")
        self.git("add", "-A")
        self.commit("first")
        (self.work / "c.txt").write_text("c\n", encoding="utf-8")
        self.git("add", "c.txt")
        self.commit("second")
        self.server = tasks_web.TaskServer(
            ("127.0.0.1", 0), tasks_web.Store(self.brain),
            git_repos=[("work", "Work", self.work), ("brain", "brain", self.nogit)],
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.work, check=True, capture_output=True, text=True).stdout

    def commit(self, message):
        self.git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-m", message)

    def change(self):
        """Modified, staged, both, untracked, deleted, renamed and sensitive files."""
        (self.work / "a.txt").write_text("one\nTWO\nthree\nfour\n", encoding="utf-8")
        (self.work / "gone.txt").unlink()
        self.git("mv", "old.txt", "new.txt")
        (self.work / "new.txt").write_text("".join(f"line {n}\n" for n in range(20)) + "extra\n", encoding="utf-8")
        (self.work / "b.txt").write_text("keep\nstaged\n", encoding="utf-8")
        self.git("add", "b.txt")
        (self.work / "both.txt").write_text("x\ny\n", encoding="utf-8")
        self.git("add", "both.txt")
        (self.work / "both.txt").write_text("x\ny\nz\nw\n", encoding="utf-8")
        (self.work / "fresh.txt").write_text("alpha\nbeta", encoding="utf-8")
        (self.work / "blob.bin").write_bytes(b"\x00\x01\x02")
        (self.work / ".env").write_text("SECRET=hunter2\n", encoding="utf-8")

    def get(self, path):
        try:
            with urlopen(self.base + path, timeout=5) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def files(self):
        status, data = self.get("/api/git")
        self.assertEqual(status, 200)
        return {item["path"]: item for item in data["repos"][0]["files"]}

    def test_clean_repo_and_missing_git_directory(self):
        status, data = self.get("/api/git")
        self.assertEqual(status, 200)
        work, other = data["repos"]
        self.assertEqual((work["id"], work["label"], work["available"], work["branch"]), ("work", "Work", True, "main"))
        self.assertEqual((work["files"], work["upstream"], work["ahead"], work["behind"], work["detached"]), ([], None, None, None, False))
        self.assertEqual([item["subject"] for item in work["commits"]], ["second", "first"])
        self.assertRegex(work["commits"][0]["hash"], r"^[0-9a-f]{40}$")
        self.assertEqual(work["commits"][0]["author"], "T")
        self.assertEqual(other["available"], False)
        self.assertEqual(other["files"], [])

    def test_status_parsing_and_line_counts(self):
        self.change()
        files = self.files()
        self.assertEqual({k: files["a.txt"][k] for k in ("index", "worktree", "staged", "unstaged", "added", "deleted")}, {"index": ".", "worktree": "M", "staged": False, "unstaged": True, "added": 2, "deleted": 1})
        self.assertEqual((files["b.txt"]["index"], files["b.txt"]["staged"], files["b.txt"]["unstaged"], files["b.txt"]["added"]), ("M", True, False, 1))
        self.assertEqual((files["gone.txt"]["worktree"], files["gone.txt"]["deleted"], files["gone.txt"]["added"]), ("D", 2, 0))
        self.assertEqual((files["both.txt"]["staged"], files["both.txt"]["unstaged"], files["both.txt"]["added"]), (True, True, 3))
        self.assertEqual((files["both.txt"]["staged_added"], files["both.txt"]["unstaged_added"]), (1, 2))
        renamed = files["new.txt"]
        self.assertEqual((renamed["index"], renamed["orig_path"], renamed["staged"]), ("R", "old.txt", True))
        self.assertNotIn("old.txt", files)
        fresh = files["fresh.txt"]
        self.assertEqual((fresh["untracked"], fresh["worktree"], fresh["index"], fresh["added"], fresh["deleted"], fresh["staged"], fresh["unstaged"]), (True, "?", ".", 2, 0, False, False))
        self.assertEqual((files["blob.bin"]["binary"], files["blob.bin"]["added"]), (True, None))
        self.assertTrue(files[".env"]["sensitive"])

    def test_binary_tracked_file_is_flagged_from_numstat(self):
        (self.work / "img.bin").write_bytes(b"\x00\x01")
        self.git("add", "img.bin")
        self.commit("binary")
        (self.work / "img.bin").write_bytes(b"\x00\x02\x03")
        item = self.files()["img.bin"]
        self.assertEqual((item["binary"], item["added"], item["deleted"]), (True, None, None))
        status, data = self.get("/api/git/diff?repo=work&path=img.bin&staged=0")
        self.assertEqual((status, data["binary"]), (200, True))

    def test_unpushed_and_ahead_behind_use_local_refs_only(self):
        remote = Path(self.temp.name) / "remote.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        self.git("remote", "add", "origin", str(remote))
        self.git("push", "-q", "-u", "origin", "main")
        (self.work / "c.txt").write_text("c2\n", encoding="utf-8")
        self.git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-am", "third")
        status, data = self.get("/api/git")
        work = data["repos"][0]
        self.assertEqual((work["upstream"], work["ahead"], work["behind"]), ("origin/main", 1, 0))
        self.assertEqual([item["unpushed"] for item in work["commits"]], [True] + [False] * (tasks_web.GIT_COMMIT_LIMIT - 1))

    def test_diff_for_unstaged_staged_both_and_rename(self):
        self.change()
        status, data = self.get("/api/git/diff?repo=work&path=a.txt&staged=0")
        self.assertEqual(status, 200)
        self.assertIn("-two", data["diff"])
        self.assertIn("+TWO", data["diff"])
        self.assertEqual((data["hidden"], data["binary"], data["truncated"], data["staged"]), (False, False, False, False))
        status, data = self.get("/api/git/diff?repo=work&path=both.txt&staged=1")
        self.assertIn("+y", data["diff"])
        self.assertNotIn("+z", data["diff"])
        status, data = self.get("/api/git/diff?repo=work&path=both.txt&staged=0")
        self.assertIn("+z", data["diff"])
        self.assertFalse(data["staged"])
        # Only staged changes: staged=0 falls back to the staged diff.
        status, data = self.get("/api/git/diff?repo=work&path=b.txt&staged=0")
        self.assertEqual(status, 200)
        self.assertIn("+staged", data["diff"])
        self.assertTrue(data["staged"])
        status, data = self.get("/api/git/diff?repo=work&path=new.txt&staged=1")
        self.assertIn("rename from old.txt", data["diff"])
        status, _ = self.get("/api/git/diff?repo=work&path=a.txt&staged=1")
        self.assertEqual(status, 404)

    def test_untracked_diff_is_a_pseudo_diff_and_binary_is_refused(self):
        self.change()
        status, data = self.get("/api/git/diff?repo=work&path=fresh.txt&staged=0")
        self.assertEqual(status, 200)
        self.assertIn("+++ b/fresh.txt", data["diff"])
        self.assertIn("@@ -0,0 +1,2 @@", data["diff"])
        self.assertIn("+alpha\n+beta\n", data["diff"])
        status, data = self.get("/api/git/diff?repo=work&path=blob.bin&staged=0")
        self.assertEqual((status, data["binary"], data["diff"]), (200, True, ""))

    def test_rejects_unknown_repo_path_traversal_and_clean_files(self):
        self.change()
        for query in ("repo=nope&path=a.txt", "repo=brain&path=a.txt", "repo=work&path=../x", "repo=work&path=b.txt%2F..%2Fa.txt",
                      "repo=work&path=c.txt", "repo=work&path=%2Fetc%2Fpasswd", "repo=work&path=nothing.txt"):
            status, data = self.get(f"/api/git/diff?{query}&staged=0")
            self.assertEqual(status, 404, query)
            self.assertIn("error", data)
        self.assertEqual(self.get("/api/git/diff?repo=work&staged=0")[0], 400)
        self.assertEqual(self.get("/api/git/diff?repo=work&path=a.txt&staged=2")[0], 400)

    def test_untracked_symlink_is_not_followed(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("private\n", encoding="utf-8")
        (self.work / "link.txt").symlink_to(outside)
        self.assertIn("link.txt", self.files())
        status, data = self.get("/api/git/diff?repo=work&path=link.txt&staged=0")
        self.assertEqual(status, 404)
        self.assertNotIn("private", json.dumps(data))

    def test_sensitive_files_are_hidden(self):
        self.change()
        for name in (".env", ".env.local", "server.pem", "my.key", "Credentials.json", "app-secret.txt", "id_rsa", "a.kdbx", "x.token", "id_ed25519.pub"):
            (self.work / name).write_text("SECRET=hunter2\n", encoding="utf-8")
            status, data = self.get(f"/api/git/diff?repo=work&path={name}&staged=0")
            self.assertEqual(status, 200, name)
            self.assertTrue(data["hidden"], name)
            self.assertEqual(data["diff"], "", name)
        # Tracked and modified sensitive file: still hidden.
        (self.work / ".env.prod").write_text("TOKEN=2\n", encoding="utf-8")
        status, data = self.get("/api/git/diff?repo=work&path=.env.prod&staged=0")
        self.assertTrue(data["hidden"])
        self.assertNotIn("TOKEN", json.dumps(data))

    def test_commit_endpoint_validates_hash_and_hides_sensitive_hunks(self):
        (self.work / "plain.txt").write_text("visible content\n", encoding="utf-8")
        (self.work / "prod.env").write_text("x\n", encoding="utf-8")
        (self.work / ".env").write_text("SECRET=hunter2\n", encoding="utf-8")
        (self.work / "tls.pem").write_text("PRIVATE-KEY-DATA\n", encoding="utf-8")
        self.git("add", "-f", "-A")
        self.commit("add files")
        head = self.git("rev-parse", "HEAD").strip()
        status, data = self.get(f"/api/git/commit?repo=work&hash={head}")
        self.assertEqual(status, 200)
        self.assertEqual((data["repo"], data["hash"], data["truncated"]), ("work", head, False))
        self.assertIn("add files", data["show"])
        self.assertIn("+visible content", data["show"])
        self.assertIn(".env", data["show"])
        self.assertIn("tls.pem", data["show"])
        self.assertNotIn("hunter2", data["show"])
        self.assertNotIn("PRIVATE-KEY-DATA", data["show"])
        self.assertIn("hidden", data["show"])
        self.assertEqual(self.get(f"/api/git/commit?repo=work&hash={'0' * 40}")[0], 404)
        for bad in ("zzz", head[:7], head.upper(), "--output=x", ""):
            self.assertEqual(self.get(f"/api/git/commit?repo=work&hash={bad}")[0], 404, bad)
        self.assertEqual(self.get(f"/api/git/commit?repo=nope&hash={head}")[0], 404)

    def test_commit_beyond_the_listed_limit_is_refused(self):
        first = self.git("rev-list", "--max-parents=0", "HEAD").strip()
        for number in range(10):
            (self.work / "c.txt").write_text(f"{number}\n", encoding="utf-8")
            self.git("-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-q", "-am", f"n{number}")
        status, data = self.get("/api/git")
        self.assertEqual(len(data["repos"][0]["commits"]), tasks_web.GIT_COMMIT_LIMIT)
        self.assertEqual(self.get(f"/api/git/commit?repo=work&hash={first}")[0], 404)

    def test_diff_and_commit_output_is_truncated(self):
        big = "".join(f"line number {n} with padding\n" for n in range(20000))
        self.assertGreater(len(big), 300_000)
        (self.work / "big.txt").write_text(big, encoding="utf-8")
        status, data = self.get("/api/git/diff?repo=work&path=big.txt&staged=0")
        self.assertEqual(status, 200)
        self.assertTrue(data["truncated"])
        self.assertLessEqual(len(data["diff"].encode()), 300_000)
        self.git("add", "big.txt")
        self.commit("big")
        head = self.git("rev-parse", "HEAD").strip()
        status, data = self.get(f"/api/git/commit?repo=work&hash={head}")
        self.assertTrue(data["truncated"])
        self.assertLessEqual(len(data["show"].encode()), 300_000)

    def test_git_endpoints_refuse_foreign_hosts_and_writes(self):
        request = Request(self.base + "/api/git", headers={"Host": "evil.example"})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)
        caught.exception.close()
        status, _ = self.request_post("/api/git")
        self.assertNotEqual(status, 200)

    def request_post(self, path):
        request = Request(self.base + path, data=b"{}", method="POST", headers={"Content-Type": "application/json", "Origin": self.base, "X-Tasks-Token": self.server.token})
        try:
            with urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            with error:
                return error.code, json.loads(error.read())

    def test_git_failure_is_reported_without_traceback(self):
        with patch.object(tasks_web.subprocess, "run", side_effect=tasks_web.subprocess.TimeoutExpired("git", 10)):
            status, data = self.get("/api/git")
            self.assertEqual(status, 200)
            self.assertIn("10 seconds", data["repos"][0]["error"])
            status, data = self.get("/api/git/diff?repo=work&path=a.txt&staged=0")
            self.assertEqual(status, 502)
            self.assertIn("error", data)

    def test_git_commands_are_fixed_argv_without_network(self):
        self.change()
        calls = []
        real = tasks_web.subprocess.run

        def spy(command, **kwargs):
            calls.append((command, kwargs))
            return real(command, **kwargs)

        with patch.object(tasks_web.subprocess, "run", side_effect=spy):
            self.get("/api/git")
            self.get("/api/git/diff?repo=work&path=a.txt&staged=0")
        self.assertTrue(calls)
        forbidden = {"fetch", "pull", "push", "ls-remote", "remote", "clone", "commit", "add", "reset", "checkout"}
        for command, kwargs in calls:
            self.assertIsInstance(command, list)
            self.assertEqual(command[1:5], ["--no-pager", "-c", "core.quotepath=false", "-c"])
            self.assertFalse(forbidden & set(command[:8]), command)
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["timeout"], 10)
            for key in ("GIT_TERMINAL_PROMPT", "GIT_OPTIONAL_LOCKS"):
                self.assertEqual(kwargs["env"][key], "0")
            self.assertEqual(kwargs["env"]["LC_ALL"], "C")
            if "diff" in command:
                self.assertIn("--no-ext-diff", command)
                self.assertIn("--no-textconv", command)

    def test_default_repos_are_work_and_brain(self):
        store = tasks_web.Store(self.brain)
        self.assertEqual(tasks_web.default_git_repos(store.brain), [("work", "Work", tasks_web.WORK), ("brain", "brain", store.brain)])


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
                "/api/search?q=alpha", "/api/docs/render?id=x.md", "/api/docs/recent", "/api/git", "/api/git/diff?repo=work&path=a",
                "/api/git/commit?repo=work&hash=" + "0" * 40, "/api/undo"]
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

    def test_git_repositories_follow_the_selected_brain(self):
        store = self.server.store_for("brain-perso")
        self.assertEqual(self.server.git_repos_for(store), [("work", "Work", self.root.resolve()), ("brain", "brain-perso", self.other.resolve())])
        self.assertEqual(self.server.git_repos_for(self.server.store), [("work", "Work", self.root.resolve()), ("brain", "brain", self.default.resolve())])
        status, data = self.request("GET", "/api/git?brain=brain-perso")
        self.assertEqual(status, 200)
        self.assertEqual([(repo["id"], repo["label"]) for repo in data["repos"]], [("work", "Work"), ("brain", "brain-perso")])
        data = self.request("GET", "/api/git")[1]
        self.assertEqual([(repo["id"], repo["label"]) for repo in data["repos"]], [("work", "Work"), ("brain", "brain")])

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


if __name__ == "__main__":
    unittest.main()
