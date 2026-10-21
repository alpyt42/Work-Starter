"""Regression checks for brain boundaries: client names of other brains, the pre-commit hook, the action form.

Everything runs on temporary Work folders; no real brain is read.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
NEW_BRAIN = REPO / "tools/brain/new-brain.py"
CHECK_NO_CLIENT = REPO / "tools/machine/check-no-client.py"
HOOK = REPO / "tools/machine/hooks/brain-pre-commit"
TEMPLATE = REPO / "kit/brain/templates/templater/nouvelle-action.md"
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, env=GIT_ENV, check=True, capture_output=True)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class WorkFolder(unittest.TestCase):
    """A temporary Work root that reads the real tools and kit."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        self.work.mkdir()
        (self.work / "kit").symlink_to(REPO / "kit")
        (self.work / "tools").symlink_to(REPO / "tools")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def new_brain(self, name: str, *options: str) -> Path:
        result = subprocess.run(
            [sys.executable, str(NEW_BRAIN), name, *options],
            env={**GIT_ENV, "WORK_DIR": str(self.work)}, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.work / name

    def declare_allow(self, brain: Path, *names: str) -> None:
        path = brain / ".data/brain.json"
        declared = json.loads(path.read_text(encoding="utf-8"))
        declared["allow"] = list(names)
        path.write_text(json.dumps(declared, indent=2, sort_keys=True) + "\n", encoding="utf-8")


class ClientNameScanTest(WorkFolder):
    """check-no-client.py --brain: client names of the other brains, minus the brain's `allow` list."""

    def setUp(self) -> None:
        super().setUp()
        self.default = self.new_brain("brain")
        self.perso = self.new_brain("brain-perso")
        self.asso = self.new_brain("brain-asso")
        for client in ("acme-corp", "globex", "_archive", "abc"):
            write(self.default / f"projects/clients/{client}/{client}.md", f"# {client}\n")
        write(self.asso / "projects/clients/asso-client/asso-client.md", "# asso-client\n")
        write(self.perso / "projects/clients/perso-co/perso-co.md", "# perso-co\n")

    def scan(self, *args: str, brain: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(CHECK_NO_CLIENT), "--brain", str(brain or self.perso), *args],
            env=GIT_ENV, capture_output=True, text=True,
        )

    def test_name_of_another_brains_client_is_blocked(self) -> None:
        write(self.perso / "notes/a.md", "Réunion avec Acme Corp et GLOBEX.\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked client name of another brain (brain) in notes/a.md: acme corp", result.stderr)
        self.assertIn("in notes/a.md: globex", result.stderr)
        self.assertNotIn("asso", result.stderr)

    def test_dashed_spelling_and_file_names_are_scanned(self) -> None:
        write(self.perso / "notes/acme-corp.md", "rien\n")
        write(self.perso / "notes/b.md", "voir (acme-corp).\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 1)
        self.assertIn("in notes/acme-corp.md: acme-corp", result.stderr)
        self.assertIn("in notes/b.md: acme-corp", result.stderr)

    def test_allow_list_of_the_scanned_brain_lets_names_through(self) -> None:
        write(self.perso / "notes/a.md", "Acme Corp et Globex.\n")
        self.declare_allow(self.perso, "acme-corp")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("acme", result.stderr)
        self.assertIn("globex", result.stderr)
        self.declare_allow(self.perso, "Acme Corp", "GLOBEX")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_allow_list_of_another_brain_does_not_apply(self) -> None:
        write(self.perso / "notes/a.md", "Globex.\n")
        self.declare_allow(self.asso, "globex")
        self.assertEqual(self.scan("--worktree").returncode, 1)

    def test_own_clients_short_names_and_underscore_folders_are_not_blocked(self) -> None:
        write(self.perso / "notes/a.md", "perso-co, abc et _archive sont fictifs.\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_only_whole_words_match(self) -> None:
        write(self.perso / "notes/a.md", "globexcorp, acme-corporation et preglobex.\n")
        self.assertEqual(self.scan("--worktree").returncode, 0)

    def test_staged_mode_reads_the_index_not_the_worktree(self) -> None:
        write(self.perso / "notes/ok.md", "Rien à signaler.\n")
        write(self.perso / "notes/bad.md", "Globex.\n")
        git(self.perso, "add", "notes/ok.md")
        staged = self.scan("--staged")
        self.assertEqual(staged.returncode, 0, staged.stdout + staged.stderr)
        self.assertEqual(self.scan("--worktree").returncode, 1)
        git(self.perso, "add", "notes/bad.md")
        self.assertEqual(self.scan("--staged").returncode, 1)
        # An edit that is not staged does not hide the staged content.
        write(self.perso / "notes/bad.md", "Rien.\n")
        self.assertEqual(self.scan("--staged").returncode, 1)

    def test_staged_mode_uses_the_staged_allow_list(self) -> None:
        write(self.perso / "notes/a.md", "Globex.\n")
        self.declare_allow(self.perso, "globex")
        git(self.perso, "add", "-A")
        self.assertEqual(self.scan("--staged").returncode, 0)
        self.declare_allow(self.perso)  # unstaged removal of the allow list
        self.assertEqual(self.scan("--staged").returncode, 0)
        self.assertEqual(self.scan("--worktree").returncode, 1)

    def test_default_brain_is_scanned_against_the_other_brains_too(self) -> None:
        write(self.default / "notes/a.md", "Dossier asso-client.\n")
        result = self.scan("--worktree", brain=self.default)
        self.assertEqual(result.returncode, 1)
        self.assertIn("(brain-asso)", result.stderr)

    def test_alone_at_the_work_root_there_is_nothing_to_check(self) -> None:
        shutil.rmtree(self.default)
        shutil.rmtree(self.asso)
        write(self.perso / "notes/a.md", "Globex.\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("no other brain", result.stdout)

    def test_invalid_arguments_and_missing_brain(self) -> None:
        def run(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run([sys.executable, str(CHECK_NO_CLIENT), *args], env=GIT_ENV, capture_output=True, text=True)

        for args in ((), ("--brain", str(self.perso)), ("--brain",), ("--staged", "--worktree"), ("--bogus",)):
            self.assertEqual(run(*args).returncode, 2, args)
        self.assertEqual(run("--brain", str(self.work / "brain-absent"), "--worktree").returncode, 2)


class DefaultScanTest(unittest.TestCase):
    """Without --brain the tool still scans the Work repository against the default brain."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.brain = Path(self._tmp.name).resolve() / "brain"
        (self.brain / "people").mkdir(parents=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def scan(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CHECK_NO_CLIENT), *args],
                              env={**GIT_ENV, "BRAIN_DIR": str(self.brain)}, capture_output=True, text=True)

    def test_known_client_name_in_the_repository_is_blocked(self) -> None:
        # The repository mentions its own "tasks-web" tool: used as a stand-in for a client name.
        write(self.brain / "projects/clients/tasks-web/tasks-web.md", "# x\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked known name in", result.stderr)

    def test_unknown_names_pass(self) -> None:
        write(self.brain / "projects/clients/" / ("zq" + "xv-client") / "client.md", "# x\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Known-name scan OK", result.stdout)

    def test_usage_is_unchanged(self) -> None:
        self.assertEqual(self.scan().returncode, 2)
        self.assertEqual(self.scan("--staged", "--worktree").returncode, 2)


def hook_path_has_uv() -> bool:
    extra = [str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    return shutil.which("uv", path=os.pathsep.join([*extra, os.environ.get("PATH", "")])) is not None


@unittest.skipUnless(hook_path_has_uv(), "uv is required by the pre-commit hook")
class PreCommitHookTest(WorkFolder):
    """tools/machine/hooks/brain-pre-commit on two temporary brains, run on the staged content."""

    def setUp(self) -> None:
        super().setUp()
        self.default = self.new_brain("brain", "--scope", "employeur", "--description", "Contexte de l'employeur.")
        self.perso = self.new_brain("brain-perso", "--scope", "perso", "--description", "Perso uniquement.")
        write(self.default / "projects/clients/acme-corp/acme-corp.md", "# Acme Corp\n")

    def stage(self, brain: Path, files: dict[str, str]) -> None:
        for relative, text in files.items():
            write(brain / relative, text)
        git(brain, "add", "-A")

    def run_hook(self, brain: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["bash", str(HOOK)], cwd=brain, env=GIT_ENV, capture_output=True, text=True)

    def test_clean_seeds_pass(self) -> None:
        for brain in (self.default, self.perso):
            git(brain, "add", "-A")
            result = self.run_hook(brain)
            self.assertEqual(result.returncode, 0, brain.name + result.stdout + result.stderr)

    def test_link_into_another_brain_is_refused_from_any_brain(self) -> None:
        self.stage(self.perso, {"notes/a.md": "Voir [tâches](../../brain/tasks.md).\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LIEN INTER-BRAINS (../../brain/tasks.md)", result.stdout + result.stderr)
        self.assertIn("Commit refusé", result.stderr)
        self.stage(self.default, {"notes/a.md": "Voir [tâches](../../brain-perso/tasks.md).\n"})
        result = self.run_hook(self.default)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LIEN INTER-BRAINS (../../brain-perso/tasks.md)", result.stdout + result.stderr)

    def test_client_name_of_another_brain_is_refused_unless_allowed(self) -> None:
        self.stage(self.perso, {"notes/b.md": "Réunion avec Acme Corp.\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Blocked client name of another brain (brain) in notes/b.md: acme corp", result.stderr)
        self.declare_allow(self.perso, "acme-corp")
        git(self.perso, "add", "-A")
        result = self.run_hook(self.perso)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_staged_content_decides_not_the_worktree(self) -> None:
        self.stage(self.perso, {"notes/a.md": "Voir [tâches](../../brain/tasks.md) et Acme Corp.\n"})
        write(self.perso / "notes/a.md", "Propre.\n")  # fixed but not staged
        self.assertNotEqual(self.run_hook(self.perso).returncode, 0)
        git(self.perso, "add", "notes/a.md")
        self.assertEqual(self.run_hook(self.perso).returncode, 0)
        write(self.perso / "notes/a.md", "Voir [tâches](../../brain/tasks.md) et Acme Corp.\n")  # broken but not staged
        result = self.run_hook(self.perso)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_links_of_the_committed_brain_do_not_resolve_against_the_worktree(self) -> None:
        git(self.perso, "add", "-A")
        write(self.perso / "notes/target.md", "# Cible non indexée\n")
        self.stage_only(self.perso, "notes/source.md", "[cible](target.md)\n")
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LIEN MD MORT (target.md)", result.stdout + result.stderr)

    def stage_only(self, brain: Path, relative: str, text: str) -> None:
        write(brain / relative, text)
        git(brain, "add", relative)

    def test_existing_checks_are_kept(self) -> None:
        self.stage(self.perso, {"notes/a.md": "[mort](absent.md)\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("LIEN MD MORT (absent.md)", result.stdout + result.stderr)
        self.stage(self.perso, {"notes/a.md": "ok\n", "notes/secret.md": "clé : AKIA" + "ABCDEFGHIJKLMNOP\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_hook_never_writes_to_the_brain(self) -> None:
        self.stage(self.perso, {"notes/a.md": "Réunion avec Acme Corp.\n"})
        before = subprocess.run(["git", "status", "--porcelain"], cwd=self.perso, env=GIT_ENV, capture_output=True, text=True).stdout
        self.run_hook(self.perso)
        after = subprocess.run(["git", "status", "--porcelain"], cwd=self.perso, env=GIT_ENV, capture_output=True, text=True).stdout
        self.assertEqual(before, after)


class ActionFormTest(unittest.TestCase):
    """The Templater form lists the registers of every brain."""

    def test_register_pattern_matches_every_brain_and_nothing_else(self) -> None:
        source = TEMPLATE.read_text(encoding="utf-8")
        literal = re.search(r"const REGISTER = /(.+)/;", source).group(1)
        pattern = re.compile(literal.replace("\\/", "/"))
        for path, brain in (
            ("brain/projects/clients/acme/missions/m1/state/actions.md", "brain"),
            ("brain/projects/internal/setup/state/actions.md", "brain"),
            ("brain-perso/projects/internal/setup/state/actions.md", "brain-perso"),
            ("brain-asso-2/projects/internal/x/state/actions.md", "brain-asso-2"),
        ):
            match = pattern.fullmatch(path)
            self.assertIsNotNone(match, path)
            self.assertEqual(match.group(1), brain)
        for path in (
            "brainy/projects/internal/setup/state/actions.md",
            "brain-/projects/internal/setup/state/actions.md",
            "brain-Perso/projects/internal/setup/state/actions.md",
            "notes/brain/projects/internal/setup/state/actions.md",
            "brain/projects/internal/setup/state/decisions.md",
        ):
            self.assertIsNone(pattern.fullmatch(path), path)
        self.assertNotIn('"brain/', source)
        self.assertIn("${brain}/.data/doctor.json", source)

    @unittest.skipUnless(shutil.which("node"), "node is required to run the form")
    def test_form_runs_against_the_chosen_brain(self) -> None:
        register = "## Ouvertes\n\n- [ ] **{p}-{n}** — Alice — existante\n\n## Terminées\n"
        files = {
            "brain/projects/clients/acme/missions/m1/state/actions.md": register.format(p="ACM", n="001"),
            "brain/projects/internal/setup/state/actions.md": register.format(p="SET", n="050"),
            "brain/.data/doctor.json": json.dumps({"owner": "Alice"}),
            "brain-perso/projects/internal/setup/state/actions.md": register.format(p="SET", n="002"),
            "brain-perso/projects/internal/setup/setup.md": "Voir SET-007.\n",
            "brain-perso/.data/doctor.json": json.dumps({"owner": "Bob"}),
        }
        several = self.run_form(files, "brain-perso / setup")
        self.assertEqual(
            sorted(several["labels"]),
            ["brain / acme / m1", "brain / setup", "brain-perso / setup"],
        )
        self.assertEqual(several["owner"], "Bob")
        self.assertEqual(list(several["written"]), ["brain-perso/projects/internal/setup/state/actions.md"])
        written = several["written"]["brain-perso/projects/internal/setup/state/actions.md"]
        self.assertIn("**SET-008** — Bob — Faire le point", written)
        self.assertLess(written.index("SET-008"), written.index("## Terminées"))

        alone = {path: text for path, text in files.items() if path.startswith("brain/")}
        single = self.run_form(alone, "acme / m1")
        self.assertEqual(sorted(single["labels"]), ["acme / m1", "setup"])
        self.assertEqual(single["owner"], "Alice")
        self.assertIn("**ACM-002** — Alice — Faire le point",
                      single["written"]["brain/projects/clients/acme/missions/m1/state/actions.md"])

    def run_form(self, files: dict[str, str], choose: str) -> dict:
        harness = r"""
const fs = require("fs");
const scenario = JSON.parse(process.env.SCENARIO);
const code = fs.readFileSync(process.env.TEMPLATE, "utf8").replace(/^<%\*/, "").replace(/-%>\s*$/, "");
const files = scenario.files, written = {}, seen = { labels: [], owner: null };
class Notice { constructor(message) { seen.notice = message; } }
const app = { vault: {
  getMarkdownFiles: () => Object.keys(files).filter((p) => p.endsWith(".md")).map((path) => ({ path })),
  read: async (f) => files[f.path], cachedRead: async (f) => files[f.path],
  modify: async (f, text) => { files[f.path] = text; written[f.path] = text; },
  adapter: { read: async (p) => { if (!(p in files)) throw new Error("ENOENT"); return files[p]; } },
} };
const tp = {
  system: {
    suggester: async (labels, values, _throw, placeholder) => {
      if (placeholder === "Projet") { seen.labels = labels; return values[labels.indexOf(scenario.choose)]; }
      return values[0];
    },
    prompt: async (question, fallback) => {
      if (question.startsWith("Intitulé")) return "Faire le point";
      if (question.startsWith("Responsable")) { seen.owner = fallback; return fallback; }
      return "";
    },
  },
  date: { now: (format) => (format.includes("HH") ? "2026-10-21 10:00" : format === "DD/MM" ? "21/10" : "2026-10-21") },
};
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
new AsyncFunction("app", "tp", "Notice", code)(app, tp, Notice)
  .then(() => console.log(JSON.stringify({ ...seen, written })))
  .catch((error) => { console.error(error); process.exit(1); });
"""
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "harness.js"
            script.write_text(harness, encoding="utf-8")
            result = subprocess.run(
                ["node", str(script)], capture_output=True, text=True,
                env={**os.environ, "TEMPLATE": str(TEMPLATE), "SCENARIO": json.dumps({"files": files, "choose": choose})},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)


if __name__ == "__main__":
    unittest.main()
