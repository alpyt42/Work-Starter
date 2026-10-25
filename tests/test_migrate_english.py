"""Regression checks for migrate-english.py: French format labels to English, content untouched (temporary brain)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/brain/migrate-english.py"
ACTION = ROOT / "tools/brain/action.py"
DECISION = ROOT / "tools/brain/decision.py"

ACTIONS = """# Actions — Mission

> Registre de test : la citation reste telle quelle, même avec ## Ouvertes ou créée : dedans.

## Ouvertes
- [ ] **ACM-001** — Jane — Préparer l'atelier #lot/ateliers ➕ 2026-10-01 📅 2026-10-20
    - échéance: avant le comité
    - source: [CR](../sources/2026-10/2026-10-01-cr-kickoff.md)
    - créée : 2026-10-01 09:00
    - mise à jour : 2026-10-02 10:00
    - 02/10 : relancée, la réponse « créée : » arrive
    - 03/10 (CR) : point fait
    - limite: fin octobre
- [w] **ACM-002** — Jane — Attendre le retour
    - échéance : semaine prochaine
    - source : mail du 01/10

## Terminées
- [x] **ACM-003** — Jane — Livrer ✅ 2026-10-05
    - source: s
    - faite : livré le 05/10
- [x] **ACM-004** — Jane — Relire ✅ 2026-10-06
    - source: s
    - faite: relu
    - fait le 06/10 : vu en réunion
- [x] **ACM-005** — Jane — Envoyer ✅ 2026-10-06
    - source: s
    - fait : envoyé

## Annulées
- [-] **ACM-006** — Jane — Abandonner ❌ 2026-10-07
    - annulée le 2026-10-07 par Jane — [source](../sources/2026-10/2026-10-01-cr-kickoff.md)
"""

DECISIONS = """# Décisions — Mission

> Garder la source et le statut de chaque décision.

## Proposées

### Choisir l'outil (2026-10-01, statut : proposée)
- **Contexte :** besoin d'un outil.
- **Décision :** prendre l'outil A.
- **Conséquences :** migration.
- **Source :** [CR](../sources/2026-10/2026-10-01-cr-kickoff.md)

## Validées

### Ancienne règle (2026-09-01, statut : active)
- **Décision :** garder B.
- **Source et validation :** Jane, 2026-09-01.

### Règle datée (2026-09-02)
- **Décision :** C.
- **Validation :** Jane, 2026-09-02.
- **Suite :** voir plus tard.

## Refusées / remplacées

### Vieille règle (2026-08-01, statut : remplacée)
- **Décision :** D.
- **Remplacée par :** « Ancienne règle » (2026-09-01).
"""

BULLET_DECISIONS = """# Décisions — Interne

## Proposées
- Passer à l'outil B — proposée par Jane — source : [CR](../sources/x.md)

## Validées

## Refusées / remplacées
"""

PAGE = """# Mission: Mission

## Timeline
Mois précédents : [2026-09](journal/2026-09.md)
- 2026-10-01 — lancement (modèle)
"""

PERSON = """---
nom: Jane Doe
organisation: Acme
missions: [mission]
alias: [Jane]
role: Cheffe de projet
email:
derniere_maj: 2026-10-01
---

# Jane Doe

nom : ce texte du corps ne change pas.
"""

TASKS = """# Actions

> [Pilotage](#pilotage) · [Liste par projet](#liste-par-projet) · [Kanban](#kanban) · [Historique](#historique) · [Inbox](inbox.md)

```meta-bind-button
label: Nouvelle action
actions:
  - type: runTemplaterFile
    templateFile: kit/brain/templates/templater/nouvelle-action.md
```

## Pilotage

> [!task-focus]+ Aujourd'hui
> ```tasks
> path regex matches /^brain\\/projects\\/.*\\/state\\/actions\\.md$/
> (status.type is TODO) OR (status.type is IN_PROGRESS)
> status.name does not include attente
> description regex matches /\\*\\* — [^—]*\\bJane\\b/
> ```

> [!task-wait]+ À relancer
> ```tasks
> status.name includes attente
> ```

> [!task-project]- [Mission](projects/clients/acme/missions/mission/mission.md)
> ```tasks
> path includes brain/projects/clients/acme/missions/mission/state/actions.md
> (status.type is TODO) OR (status.type is IN_PROGRESS)
> ```

> [!task-project]- Mes actions
> ```tasks
> (status.type is IN_PROGRESS) OR (status.name includes attente) OR ((status.type is TODO) AND (status.name does not include attente) AND (description regex matches /x/))
> ```

Une phrase écrite à la main reste en français.
"""

SOURCE = "# CR\n\n## Ouvertes\n    - créée : 2026-10-01 09:00\nMois précédents : rien\n"


class MigrateEnglishTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name)
        (self.work / "kit/brain").mkdir(parents=True)
        (self.work / "kit/brain/AGENTS.md").write_text("# AGENTS\n\n## Where information goes\n\n## Several brains\n", encoding="utf-8")
        self.brain = self.work / "brain"
        self.mission = self.brain / "projects/clients/acme/missions/mission"
        files = {
            "AGENTS.md": "# AGENTS.md — brain\n\n## Périmètre\n",
            "inbox/README.md": "Voir [la carte](../AGENTS.md#ranger-linformation).\n",
            "README.md": "Conventions : [plusieurs brains](../kit/brain/AGENTS.md#plusieurs-brains).\n",
            "tasks.md": TASKS,
            "people/jane-doe.md": PERSON,
            "people/john.md": "# John\n\n- **Role:** test\n",
            "people/README.md": "nom: pas une fiche\n",
            "projects/clients/acme/acme.md": "# Client: Acme\n",
            "projects/clients/acme/missions/mission/mission.md": PAGE,
            "projects/clients/acme/missions/mission/state/actions.md": ACTIONS,
            "projects/clients/acme/missions/mission/state/decisions.md": DECISIONS,
            "projects/clients/acme/missions/mission/sources/2026-10/2026-10-01-cr-kickoff.md": SOURCE,
            "projects/clients/acme/missions/mission/journal/2026-09.md": "# Journal\n\nMois précédents : rien\n",
            "projects/clients/acme/missions/mission/notes/2026-10-01-idee.md": "    - créée : 2026-10-01 09:00\n",
            "projects/internal/interne/interne.md": "# Project: Interne\n",
            "projects/internal/interne/state/actions.md": "# Actions — Interne\n\n## Ouvertes\n\n## Terminées\n\n## Annulées\n",
            "projects/internal/interne/state/decisions.md": BULLET_DECISIONS,
            ".data/transcripts.json": json.dumps({"a.txt": {"status": "traite", "date_traitement": "2026-10-01", "destinations": ["x"], "note": "traite"},
                                                  "b.txt": {"status": "a-decider"}}, ensure_ascii=False, indent=2) + "\n",
            ".data/messages-state.json": '{\n  "mail_processed_ids": [{"id": "1", "status": "traite"}, {"id": "2", "status": "ignore"}]\n}\n',
            ".data/brain.json": '{\n  "scope": "employeur",\n  "description": "perso"\n}\n',
        }
        for name, text in files.items():
            path = self.brain / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.before = {path: path.read_bytes() for path in self.brain.rglob("*") if path.is_file()}

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_tool(self, tool: Path, *args: str, code: int = 0) -> str:
        env = {**os.environ, "WORK_DIR": str(self.work), "BRAIN_DIR": str(self.brain), "ACTION_NOW": "2026-10-13 14:32"}
        result = subprocess.run([sys.executable, str(tool), *args], env=env, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout

    def read(self, name: str) -> str:
        return (self.brain / name).read_text(encoding="utf-8")

    def test_dry_run_reports_and_writes_nothing(self) -> None:
        out = self.run_tool(TOOL, "--diff")
        self.assertIn("projects/clients/acme/missions/mission/state/actions.md:", out)
        self.assertIn("to convert", out)
        self.assertIn("+## Open", out)
        self.assertEqual({path: path.read_bytes() for path in self.brain.rglob("*") if path.is_file()}, self.before)
        self.run_tool(TOOL, "--check", code=1)

    def test_write_converts_only_the_labels(self) -> None:
        out = self.run_tool(TOOL, "--write", "--allow-dirty")
        actions = self.read("projects/clients/acme/missions/mission/state/actions.md")
        expected = (ACTIONS
                    .replace("## Ouvertes\n- [ ]", "## Open\n- [ ]").replace("## Terminées\n- [x]", "## Done\n- [x]")
                    .replace("## Annulées\n- [-]", "## Cancelled\n- [-]")
                    .replace("#lot/ateliers", "#group/ateliers")
                    .replace("    - échéance: avant", "    - due: avant").replace("    - échéance : semaine", "    - due: semaine")
                    .replace("    - créée : 2026-10-01", "    - created: 2026-10-01").replace("    - mise à jour : ", "    - updated: ")
                    .replace("    - 02/10 : relancée", "    - 02/10: relancée").replace("    - source : mail", "    - source: mail")
                    .replace("    - faite : livré", "    - done: livré").replace("    - faite: relu", "    - done: relu")
                    .replace("    - fait : envoyé", "    - done: envoyé")
                    .replace("    - annulée le 2026-10-07 par Jane", "    - cancelled: 2026-10-07 by Jane"))
        self.assertEqual(actions, expected)
        decisions = self.read("projects/clients/acme/missions/mission/state/decisions.md")
        for line in ("# Decisions — Mission", "## Proposed", "## Accepted", "## Rejected / superseded",
                     "### Choisir l'outil (2026-10-01, status: proposed)", "- **Context:** besoin d'un outil.",
                     "- **Decision:** prendre l'outil A.", "- **Consequences:** migration.", "### Ancienne règle (2026-09-01, status: active)",
                     "### Règle datée (2026-09-02)", "- **Accepted:** Jane, 2026-09-02.", "### Vieille règle (2026-08-01, status: superseded)",
                     "- **Superseded by:** « Ancienne règle » (2026-09-01).", "- **Source et validation :** Jane, 2026-09-01.", "- **Suite :** voir plus tard."):
            self.assertIn(line + "\n", decisions)
        self.assertIn("Previous months: [2026-09](journal/2026-09.md)\n", self.read("projects/clients/acme/missions/mission/mission.md"))
        person = self.read("people/jane-doe.md")
        self.assertTrue(person.startswith("---\nname: Jane Doe\norganization: Acme\nmissions: [mission]\naliases: [Jane]\nrole: Cheffe de projet\n"
                                          "email:\nupdated: 2026-10-01\n---\n"), person)
        self.assertIn("\nnom : ce texte du corps ne change pas.\n", person)
        tasks = self.read("tasks.md")
        for line in ("> [Focus](#focus) · [By project](#by-project) · [Kanban](#kanban) · [History](#history) · [Inbox](inbox.md)",
                     "label: New action", "    templateFile: kit/brain/templates/templater/new-action.md", "## Focus",
                     "> [!task-focus]+ Today", "> [!task-wait]+ Follow up", "> status.type is ON_HOLD",
                     "> (status.type is TODO) OR (status.type is IN_PROGRESS) OR (status.type is ON_HOLD)",
                     "> description regex matches /\\*\\* — [^—]*\\bJane\\b/", "> (status.type is IN_PROGRESS) OR (status.type is ON_HOLD) OR ((status.type is TODO) AND (status.type is not ON_HOLD) AND (description regex matches /x/))",
                     "Une phrase écrite à la main reste en français."):
            self.assertIn(line + "\n", tasks)
        self.assertNotIn("attente", tasks)
        focus = tasks.split("[!task-focus]")[1].split("[!task-wait]")[0]
        self.assertIn("> (status.type is TODO) OR (status.type is IN_PROGRESS)\n", focus)  # waiting stays out of Today
        self.assertNotIn("ON_HOLD", focus)
        self.assertEqual(self.read("inbox/README.md"), "Voir [la carte](../../kit/brain/AGENTS.md#where-information-goes).\n")
        self.assertIn("(../kit/brain/AGENTS.md#several-brains)", self.read("README.md"))
        transcripts = json.loads(self.read(".data/transcripts.json"))
        self.assertEqual(transcripts["a.txt"], {"status": "processed", "processed_on": "2026-10-01", "destinations": ["x"], "note": "traite"})
        self.assertEqual(transcripts["b.txt"], {"status": "undecided"})
        self.assertEqual(self.read(".data/messages-state.json"),
                         '{\n  "mail_processed_ids": [{"id": "1", "status": "processed"}, {"id": "2", "status": "ignored"}]\n}\n')
        self.assertEqual(json.loads(self.read(".data/brain.json")), {"scope": "employer", "description": "perso"})
        for name in ("projects/clients/acme/missions/mission/sources/2026-10/2026-10-01-cr-kickoff.md",
                     "projects/clients/acme/missions/mission/journal/2026-09.md",
                     "projects/clients/acme/missions/mission/notes/2026-10-01-idee.md", "people/john.md", "people/README.md", "AGENTS.md"):
            self.assertEqual((self.brain / name).read_bytes(), self.before[self.brain / name], name)
        for left in ("« fait le DD/MM » kept as written", "« limite: » kept as written", "history line with a qualifier",
                     "status « active » kept", "field « Source et validation » kept", "field « Suite » kept",
                     "decision written as a bullet", "people/john.md: left as is — no front matter"):
            self.assertIn(left, out)

    def test_second_run_finds_nothing_and_tools_read_the_result(self) -> None:
        self.run_tool(TOOL, "--write", "--allow-dirty")
        self.assertIn("Total: 0 change(s) to convert in 0 file(s)", self.run_tool(TOOL))
        self.run_tool(TOOL, "--check")
        checked = self.run_tool(ACTION, "check")
        self.assertNotIn("French labels", checked)
        listed = json.loads(self.run_tool(DECISION, "list", "--project", "acme/mission"))
        self.assertEqual([d["state"] for d in listed], ["proposed", "accepted", "accepted", "rejected"])
        shown = json.loads(self.run_tool(ACTION, "show", "ACM-001"))
        self.assertEqual((shown["group"], shown["created_at"], shown["updated_at"]), ("ateliers", "2026-10-01 09:00", "2026-10-02 10:00"))

    def test_write_refuses_files_with_uncommitted_changes(self) -> None:
        git = ["git", "-C", str(self.brain), "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-qm", "chore: init", "--no-verify"], check=True)
        register = self.brain / "projects/internal/interne/state/actions.md"
        register.write_text(register.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        out = self.run_tool(TOOL, "--write", code=1)
        self.assertIn("projects/internal/interne/state/actions.md: 3 change(s), refused (uncommitted changes)", out)
        self.assertIn("## Ouvertes", register.read_text(encoding="utf-8"))
        self.assertIn("## Open", self.read("projects/clients/acme/missions/mission/state/actions.md"))

    def test_default_brain_is_found_under_another_name_without_brain_dir(self) -> None:
        self.brain.rename(self.work / "brain-initech")  # the only brain of the Work root
        env = {key: value for key, value in os.environ.items() if key != "BRAIN_DIR"}
        result = subprocess.run([sys.executable, str(TOOL), "--check"], env={**env, "WORK_DIR": str(self.work)}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("projects/clients/acme/missions/mission/state/actions.md:", result.stdout)

    def test_seed_tasks_page_is_already_english(self) -> None:
        seed = (ROOT / "kit/brain/seed/tasks.md").read_text(encoding="utf-8")
        self.assertNotIn("attente", seed)
        self.assertIn("templater/new-action.md", seed)
        (self.brain / "tasks.md").write_text(seed.replace("{{BRAIN}}", "brain"), encoding="utf-8")
        self.assertNotIn("tasks.md:", self.run_tool(TOOL))


if __name__ == "__main__":
    unittest.main()
