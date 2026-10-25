"""Regression checks for brain boundaries: client names of other brains, the public Work repository against
the names of every brain (and its pre-commit hook), the brain pre-commit hook, the action form.

Everything runs on temporary Work folders with fictitious names; no real brain is read.
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
TEMPLATE = REPO / "kit/brain/templates/templater/new-action.md"
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
        write(self.perso / "notes/a.md", "Meeting with Acme Corp and GLOBEX.\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked client name of another brain (brain) in notes/a.md: acme corp", result.stderr)
        self.assertIn("in notes/a.md: globex", result.stderr)
        self.assertNotIn("asso", result.stderr)

    def test_dashed_spelling_and_file_names_are_scanned(self) -> None:
        write(self.perso / "notes/acme-corp.md", "nothing\n")
        write(self.perso / "notes/b.md", "see (acme-corp).\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 1)
        self.assertIn("in notes/acme-corp.md: acme-corp", result.stderr)
        self.assertIn("in notes/b.md: acme-corp", result.stderr)

    def test_allow_list_of_the_scanned_brain_lets_names_through(self) -> None:
        write(self.perso / "notes/a.md", "Acme Corp and Globex.\n")
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
        write(self.perso / "notes/a.md", "perso-co, abc and _archive are fictitious.\n")
        result = self.scan("--worktree")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_only_whole_words_match(self) -> None:
        write(self.perso / "notes/a.md", "globexcorp, acme-corporation and preglobex.\n")
        self.assertEqual(self.scan("--worktree").returncode, 0)

    def test_staged_mode_reads_the_index_not_the_worktree(self) -> None:
        write(self.perso / "notes/ok.md", "Nothing to report.\n")
        write(self.perso / "notes/bad.md", "Globex.\n")
        git(self.perso, "add", "notes/ok.md")
        staged = self.scan("--staged")
        self.assertEqual(staged.returncode, 0, staged.stdout + staged.stderr)
        self.assertEqual(self.scan("--worktree").returncode, 1)
        git(self.perso, "add", "notes/bad.md")
        self.assertEqual(self.scan("--staged").returncode, 1)
        # An edit that is not staged does not hide the staged content.
        write(self.perso / "notes/bad.md", "Nothing.\n")
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
        write(self.default / "notes/a.md", "Folder asso-client.\n")
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

    def test_without_brain_dir_every_brain_of_the_work_root_provides_the_names(self) -> None:
        work = Path(self._tmp.name).resolve() / "Work"
        (work / "tools/machine").mkdir(parents=True)
        for name in ("check-no-client.py", "work_config.py"):  # a copy, so that the Work root is the temporary one
            shutil.copy(REPO / "tools/machine" / name, work / "tools/machine" / name)
        git(work, "init", "-q")
        write(work / ".gitignore", "brain*/\ntools/\n")
        for brain, client in (("brain", "acme-corp"), ("brain-initech", "globex")):
            write(work / brain / "AGENTS.md", "# test\n")
            (work / brain / ".data").mkdir()
            write(work / brain / f"projects/clients/{client}/{client}.md", f"# {client}\n")
            (work / brain / "people").mkdir()

        def scan(text: str) -> subprocess.CompletedProcess:
            write(work / "notes.md", text)
            env = {key: value for key, value in GIT_ENV.items() if key != "BRAIN_DIR"}
            return subprocess.run([sys.executable, str(work / "tools/machine/check-no-client.py"), "--worktree"],
                                  env=env, capture_output=True, text=True)

        # `brain/` is the default, yet the clients of the other brain are known names too.
        result = scan("Meeting with Globex.\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked known name in notes.md: globex", result.stderr)
        self.assertEqual(scan("Meeting with Acme Corp.\n").returncode, 1)
        result = scan("Nothing to report.\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # The `defaultBrain` setting changes which brain is the default, not which names are known.
        write(work / "work-config.local.json", '{"version": 1, "defaultBrain": "brain-initech"}')
        self.assertEqual(scan("Meeting with Globex.\n").returncode, 1)
        self.assertEqual(scan("Meeting with Acme Corp.\n").returncode, 1)
        (work / "work-config.local.json").unlink()
        shutil.rmtree(work / "brain")  # the only brain left is the default
        result = scan("Meeting with Globex.\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked known name in notes.md: globex", result.stderr)
        self.assertEqual(scan("Meeting with Acme Corp.\n").returncode, 0)


def hook_path_has_uv() -> bool:
    extra = [str(Path.home() / ".local/bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    return shutil.which("uv", path=os.pathsep.join([*extra, os.environ.get("PATH", "")])) is not None


class PublicWorkFolder(unittest.TestCase):
    """A temporary public Work repository: copies of the scan and of its hook, and fictitious private brains.

    `brain` (default, employer scope) holds the client `globex`; `brain-acme` (employer) holds the client
    `initech` and the person `jane-doe`; `brain-perso` (personal) holds the client `hooli`.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        self.install_tools(self.work)
        git(self.work, "init", "-q")
        write(self.work / ".gitignore", "brain*/\ntools/\n__pycache__/\n")
        self.make_brain("brain", "employer", clients=("globex",))
        self.make_brain("brain-acme", "employer", clients=("initech",), people=("jane-doe",))
        self.make_brain("brain-perso", "personal", clients=("hooli",))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    @staticmethod
    def install_tools(repo: Path) -> None:
        """Copies, so that the Work root the scan finds is the temporary one (symlinks would lead back to REPO)."""
        for folder, names in (("tools/machine", ("check-no-client.py", "work_config.py")),
                              ("tools/machine/hooks", ("work-pre-commit", "check-staged-secrets.py"))):
            (repo / folder).mkdir(parents=True, exist_ok=True)
            for name in names:
                shutil.copy(REPO / folder / name, repo / folder / name)

    def make_brain(self, name: str, scope: str | None, clients: tuple[str, ...] = (), people: tuple[str, ...] = ()) -> Path:
        brain = self.work / name
        write(brain / "AGENTS.md", "# test\n")
        write(brain / ".data/brain.json", json.dumps({"version": 1} if scope is None else {"version": 1, "scope": scope}))
        (brain / "people").mkdir(exist_ok=True)
        (brain / "projects/clients").mkdir(parents=True, exist_ok=True)
        for client in clients:
            write(brain / f"projects/clients/{client}/{client}.md", f"# {client}\n")
        for person in people:
            write(brain / f"people/{person}.md", f"# {person}\n")
        return brain

    def remove_brains(self) -> None:
        for brain in self.work.glob("brain*"):
            shutil.rmtree(brain)

    def scan(self, mode: str = "--worktree", repo: Path | None = None) -> subprocess.CompletedProcess:
        repo = repo or self.work
        env = {key: value for key, value in GIT_ENV.items() if key != "BRAIN_DIR"}
        return subprocess.run([sys.executable, str(repo / "tools/machine/check-no-client.py"), mode],
                              cwd=repo, env=env, capture_output=True, text=True)


class WorkScanTest(PublicWorkFolder):
    """check-no-client.py without --brain: the public Work repository against the names of every brain."""

    def blocked(self, text: str) -> subprocess.CompletedProcess:
        write(self.work / "notes.md", text)
        return self.scan()

    def test_employer_folder_suffix_is_blocked(self) -> None:
        result = self.blocked("Weekly sync with Acme.\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked known name in notes.md: acme", result.stderr)

    def test_suffix_is_read_with_dashes_and_spaces_and_as_a_path(self) -> None:
        self.make_brain("brain-stark-industries", "client")
        result = self.blocked("Visit Stark Industries.\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("in notes.md: stark industries", result.stderr)
        write(self.work / "notes.md", "Nothing.\n")
        write(self.work / "docs/stark-industries.md", "Nothing.\n")
        result = self.scan()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("in docs/stark-industries.md: stark-industries", result.stderr)

    def test_personal_suffix_is_not_blocked(self) -> None:
        result = self.blocked("The perso brain, brain-perso, is private.\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Known-name scan OK", result.stdout)

    def test_the_scope_is_compared_without_case_and_spaces(self) -> None:
        self.make_brain("brain-wayne", " Personal ")
        self.assertEqual(self.blocked("Wayne.\n").returncode, 0)

    def test_a_missing_empty_or_unreadable_scope_counts_as_not_personal(self) -> None:
        self.make_brain("brain-umbrella", None)  # no `scope` key
        self.make_brain("brain-wonka", "")  # empty scope, as in a fresh seed
        write(self.work / "brain-hooligan/AGENTS.md", "# test\n")  # no declaration at all
        (self.work / "brain-hooligan/.data").mkdir()
        self.make_brain("brain-pied-piper", "personal")
        write(self.work / "brain-pied-piper/.data/brain.json", "{not json")  # unreadable declaration
        result = self.blocked("Umbrella, Wonka, Hooligan and Pied Piper.\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for name in ("umbrella", "wonka", "hooligan", "pied piper"):
            self.assertIn(f"in notes.md: {name}", result.stderr)

    def test_clients_and_people_of_every_brain_are_blocked(self) -> None:
        result = self.blocked("Globex (default brain), Initech, Jane Doe (other brain) and Hooli (personal brain).\n")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        for name in ("globex", "initech", "jane doe", "hooli"):
            self.assertIn(f"in notes.md: {name}", result.stderr)
        write(self.work / "notes.md", "See jane-doe.\n")
        self.assertIn("in notes.md: jane-doe", self.scan().stderr)

    def test_a_hit_names_the_file_and_the_name_never_the_whole_list(self) -> None:
        result = self.blocked("Initech only.\n")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), "Blocked known name in notes.md: initech")

    def test_short_names_templates_and_the_bare_brain_folder_are_not_blocked(self) -> None:
        self.make_brain("brain-xyz", "employer", clients=("abc", "_archive"), people=("_template", "README"))
        result = self.blocked("abc, xyz, _archive, _template, readme and the brain folder.\n")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_staged_files_are_scanned_not_the_worktree(self) -> None:
        write(self.work / "ok.md", "Nothing to report.\n")
        write(self.work / "bad.md", "Acme.\n")
        git(self.work, "add", "ok.md")
        result = self.scan("--staged")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.scan("--worktree").returncode, 1)
        git(self.work, "add", "bad.md")
        result = self.scan("--staged")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked known name in bad.md: acme", result.stderr)

    def test_a_work_without_any_brain_passes_with_a_notice(self) -> None:
        self.remove_brains()
        write(self.work / "notes.md", "Acme, Globex, Initech and Jane Doe.\n")
        git(self.work, "add", "notes.md")
        for mode in ("--worktree", "--staged"):
            result = self.scan(mode)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("no brain at the Work root", result.stdout)

    def test_a_clone_inside_the_work_root_reads_the_brains_of_the_parent(self) -> None:
        clone = self.work / "agents/clone"
        self.install_tools(clone)
        git(clone, "init", "-q")
        write(clone / ".gitignore", "tools/\n__pycache__/\n")
        write(clone / "notes.md", "Nothing to report.\n")
        self.assertEqual(self.scan(repo=clone).returncode, 0)
        write(clone / "notes.md", "Meeting with Initech.\n")
        result = self.scan(repo=clone)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Blocked known name in notes.md: initech", result.stderr)

    def test_brain_dir_is_scanned_with_the_brains_next_to_it(self) -> None:
        # BRAIN_DIR points at a brain whose folder need not be named brain-*; its parent is the Work root.
        elsewhere = Path(self._tmp.name).resolve() / "elsewhere"
        write(elsewhere / "custom/projects/clients/wonka/wonka.md", "# wonka\n")
        write(elsewhere / "brain-sibling/projects/clients/monsters/monsters.md", "# monsters\n")
        write(self.work / "notes.md", "Wonka, Monsters and Hooli.\n")
        result = subprocess.run([sys.executable, str(self.work / "tools/machine/check-no-client.py"), "--worktree"],
                                cwd=self.work, env={**GIT_ENV, "BRAIN_DIR": str(elsewhere / "custom")},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("in notes.md: wonka", result.stderr)
        self.assertIn("in notes.md: monsters", result.stderr)
        self.assertNotIn("hooli", result.stderr)  # the brains of `elsewhere` only, not those of the repository's folder

    def test_usage_is_unchanged(self) -> None:
        for args in ((), ("--staged", "--worktree"), ("--bogus",)):
            result = subprocess.run([sys.executable, str(self.work / "tools/machine/check-no-client.py"), *args],
                                    cwd=self.work, env=GIT_ENV, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, args)
            self.assertIn("every brain", result.stderr)


@unittest.skipUnless(hook_path_has_uv(), "uv is required by the pre-commit hook")
class WorkPreCommitHookTest(PublicWorkFolder):
    """tools/machine/hooks/work-pre-commit, installed in a temporary Work repository and run by `git commit`."""

    def setUp(self) -> None:
        super().setUp()
        (self.work / ".git/hooks").mkdir(exist_ok=True)
        shutil.copy(self.work / "tools/machine/hooks/work-pre-commit", self.work / ".git/hooks/pre-commit")

    def commit(self, files: dict[str, str]) -> subprocess.CompletedProcess:
        for relative, text in files.items():
            write(self.work / relative, text)
            git(self.work, "add", relative)
        return subprocess.run(
            ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-q", "-m", "docs: test"],
            cwd=self.work, env=GIT_ENV, capture_output=True, text=True,
        )

    def has_commit(self) -> bool:
        return subprocess.run(["git", "rev-parse", "-q", "--verify", "HEAD"], cwd=self.work, env=GIT_ENV,
                              capture_output=True).returncode == 0

    def test_a_commit_naming_the_employer_is_refused(self) -> None:
        result = self.commit({"notes.md": "Weekly sync with Acme.\n"})
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Blocked known name in notes.md: acme", result.stderr)
        self.assertIn("Commit refused", result.stderr)
        for other in ("globex", "initech", "jane", "hooli"):  # the list of names is never printed
            self.assertNotIn(other, result.stderr)
        self.assertFalse(self.has_commit())

    def test_a_commit_naming_a_client_or_a_person_of_any_brain_is_refused(self) -> None:
        for text, name in (("Globex.\n", "globex"), ("Initech.\n", "initech"), ("Jane Doe.\n", "jane doe"), ("Hooli.\n", "hooli")):
            result = self.commit({"notes.md": text})
            self.assertNotEqual(result.returncode, 0, text + result.stderr)
            self.assertIn(f"in notes.md: {name}", result.stderr)
        self.assertFalse(self.has_commit())

    def test_a_clean_commit_is_accepted(self) -> None:
        result = self.commit({"notes.md": "Nothing to report, perso or otherwise.\n"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.has_commit())

    def test_the_staged_content_decides_not_the_worktree(self) -> None:
        write(self.work / "notes.md", "Clean.\n")
        git(self.work, "add", "notes.md")
        write(self.work / "notes.md", "Weekly sync with Acme.\n")  # edited but not staged
        result = self.commit({})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.commit({"other.md": "Initech.\n"})
        self.assertNotEqual(result.returncode, 0)

    def test_the_secrets_check_still_runs_and_both_checks_report(self) -> None:
        result = self.commit({"keys.md": "key: AKIA" + "ABCDEFGHIJKLMNOP\n"})
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.commit({"keys.md": "key: AKIA" + "ABCDEFGHIJKLMNOP\nAcme.\n"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("AWS key", result.stdout + result.stderr)
        self.assertIn("in keys.md: acme", result.stderr)

    def test_a_work_without_any_brain_still_commits(self) -> None:
        self.remove_brains()
        result = self.commit({"notes.md": "Acme, Globex and Initech are only words here.\n"})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.has_commit())


@unittest.skipUnless(hook_path_has_uv(), "uv is required by the pre-commit hook")
class PreCommitHookTest(WorkFolder):
    """tools/machine/hooks/brain-pre-commit on two temporary brains, run on the staged content."""

    def setUp(self) -> None:
        super().setUp()
        self.default = self.new_brain("brain", "--scope", "employer", "--description", "Employer context.")
        self.perso = self.new_brain("brain-perso", "--scope", "personal", "--description", "Personal only.")
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
        self.stage(self.perso, {"notes/a.md": "See [tasks](../../brain/tasks.md).\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CROSS-BRAIN LINK (../../brain/tasks.md)", result.stdout + result.stderr)
        self.assertIn("Commit refused", result.stderr)
        self.stage(self.default, {"notes/a.md": "See [tasks](../../brain-perso/tasks.md).\n"})
        result = self.run_hook(self.default)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CROSS-BRAIN LINK (../../brain-perso/tasks.md)", result.stdout + result.stderr)

    def test_client_name_of_another_brain_is_refused_unless_allowed(self) -> None:
        self.stage(self.perso, {"notes/b.md": "Meeting with Acme Corp.\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Blocked client name of another brain (brain) in notes/b.md: acme corp", result.stderr)
        self.declare_allow(self.perso, "acme-corp")
        git(self.perso, "add", "-A")
        result = self.run_hook(self.perso)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_the_staged_content_decides_not_the_worktree(self) -> None:
        self.stage(self.perso, {"notes/a.md": "See [tasks](../../brain/tasks.md) and Acme Corp.\n"})
        write(self.perso / "notes/a.md", "Clean.\n")  # fixed but not staged
        self.assertNotEqual(self.run_hook(self.perso).returncode, 0)
        git(self.perso, "add", "notes/a.md")
        self.assertEqual(self.run_hook(self.perso).returncode, 0)
        write(self.perso / "notes/a.md", "See [tasks](../../brain/tasks.md) and Acme Corp.\n")  # broken but not staged
        result = self.run_hook(self.perso)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_links_of_the_committed_brain_do_not_resolve_against_the_worktree(self) -> None:
        git(self.perso, "add", "-A")
        write(self.perso / "notes/target.md", "# Unindexed target\n")
        self.stage_only(self.perso, "notes/source.md", "[target](target.md)\n")
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DEAD MD LINK (target.md)", result.stdout + result.stderr)

    def stage_only(self, brain: Path, relative: str, text: str) -> None:
        write(brain / relative, text)
        git(brain, "add", relative)

    def test_existing_checks_are_kept(self) -> None:
        self.stage(self.perso, {"notes/a.md": "[dead](absent.md)\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DEAD MD LINK (absent.md)", result.stdout + result.stderr)
        self.stage(self.perso, {"notes/a.md": "ok\n", "notes/secret.md": "key: AKIA" + "ABCDEFGHIJKLMNOP\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_artifacts_and_repos_targets_do_not_block_a_commit(self) -> None:
        # Fresh machine: artifacts/ exists but holds nothing, repos/ does not exist yet.
        (self.work / "artifacts").mkdir()
        self.stage(self.perso, {"notes/a.md": "[report](../../artifacts/report/README.md)\n[code](../../repos/app/README.md)\n"})
        result = self.run_hook(self.perso)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Dead links inside the brain and links into another brain stay fatal.
        self.stage(self.perso, {"notes/b.md": "[dead](absent.md)\n"})
        result = self.run_hook(self.perso)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DEAD MD LINK (absent.md)", result.stdout + result.stderr)
        self.stage(self.perso, {"notes/b.md": "ok\n", "notes/c.md": "[tasks](../../brain/tasks.md)\n"})
        self.assertNotEqual(self.run_hook(self.perso).returncode, 0)

    def test_the_hook_never_writes_to_the_brain(self) -> None:
        self.stage(self.perso, {"notes/a.md": "Meeting with Acme Corp.\n"})
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
        register = "## Open\n\n- [ ] **{p}-{n}** — Alice — existante\n\n## Done\n"
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
        self.assertLess(written.index("SET-008"), written.index("## Done"))
        self.assertIn("    - source: owner, 21/10 (added from Obsidian)\n    - created: 2026-10-21 10:00\n    - updated: 2026-10-21 10:00", written)

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
      if (placeholder === "Project") { seen.labels = labels; return values[labels.indexOf(scenario.choose)]; }
      return values[0];
    },
    prompt: async (question, fallback) => {
      if (question.startsWith("Title")) return "Faire le point";
      if (question.startsWith("Owner")) { seen.owner = fallback; return fallback; }
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
