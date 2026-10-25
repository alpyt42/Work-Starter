"""Regression checks for preflight-push.py and the pre-push hook: origin of the Git identity, brain trust boundary,
SSH account (stub SSH command), fast-forward in hook and manual modes. Local bare remotes only: no network, no real SSH."""

import importlib.util
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/machine/preflight-push.py"
HOOK = ROOT / "tools/machine/hooks/pre-push"
ZEROS = "0" * 40
AUTHOR = {
    "GIT_AUTHOR_NAME": "Test Author", "GIT_AUTHOR_EMAIL": "author@example.test",
    "GIT_COMMITTER_NAME": "Test Author", "GIT_COMMITTER_EMAIL": "author@example.test",
}


def load_module():
    spec = importlib.util.spec_from_file_location("preflight_push", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PreflightCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.home = self.root / "home"
        self.work = self.root / "Work"
        self.remotes = self.root / "remotes"
        for folder in (self.home, self.work, self.remotes):
            folder.mkdir()
        # A clean Git environment: only the temporary global config, with includeIf rules and useConfigOnly.
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_GLOBAL=str(self.home / ".gitconfig"), GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
        self.write_boundary("acme", "ada@acme.example")
        self.write_boundary("globex", "gus@globex.example")
        self.write_global()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # --- fixtures

    def write_boundary(self, name: str, email: str, ssh_command: str | None = None) -> None:
        text = f"[user]\n    name = {name.title()} Person\n    email = {email}\n"
        if ssh_command:
            text += f"[core]\n    sshCommand = {ssh_command}\n"
        (self.home / f".gitconfig-{name}").write_text(text, encoding="utf-8")

    def write_global(self, text: str | None = None) -> None:
        """The global config: no identity of its own, one boundary file per folder (the template of gitconfig.example)."""
        if text is None:
            text = "[user]\n    useConfigOnly = true\n"
            for pattern, boundary in ((f"{self.work}/brain-acme/", "acme"), (f"{self.work}/.git", "acme"), (f"{self.work}/brain-globex/", "globex")):
                text += f'[includeIf "gitdir:{pattern}"]\n    path = {self.home}/.gitconfig-{boundary}\n'
        (self.home / ".gitconfig").write_text(text, encoding="utf-8")

    def git(self, repo: Path, *args: str, check: bool = True, **env: str) -> subprocess.CompletedProcess:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, env={**self.env, **AUTHOR, **env})
        if check:
            self.assertEqual(result.returncode, 0, f"git {' '.join(args)}: {result.stdout}{result.stderr}")
        return result

    def commit(self, repo: Path, message: str = "work") -> str:
        self.git(repo, "commit", "-q", "--allow-empty", "-m", message)
        return self.rev(repo, "HEAD")

    def rev(self, repo: Path, ref: str) -> str:
        return self.git(repo, "rev-parse", ref).stdout.strip()

    def make_bare(self, name: str) -> Path:
        bare = self.remotes / name
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, env=self.env)
        return bare

    def make_repo(self, name: str = "brain-acme", bare: str = "acme.git", remote: str = "origin") -> Path:
        """A repository under the Work folder with one commit on main and a bare remote of the given name."""
        repo = self.work / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True, env=self.env)
        self.git(repo, "remote", "add", remote, str(self.make_bare(bare)))
        self.commit(repo, "first")
        return repo

    def write_brain_json(self, repo: Path, remote: str = "*/remotes/acme.git", email: str = "*@acme.example") -> None:
        (repo / ".data").mkdir(exist_ok=True)
        (repo / ".data/brain.json").write_text(
            f'{{"version": 1, "scope": "s", "description": "d", "remote": "{remote}", "email": "{email}", "allow": []}}\n', encoding="utf-8")

    def pushed_repo(self) -> Path:
        """A brain whose first commit is on the remote, with a matching boundary declaration."""
        repo = self.make_repo()
        self.write_brain_json(repo)
        self.git(repo, "push", "-q", "origin", "main")
        return repo

    def advance_remote(self, remote: str = "acme.git") -> str:
        """Another clone adds a commit to the remote main; returns its sha."""
        other = self.root / "other"
        if not other.exists():
            subprocess.run(["git", "clone", "-q", str(self.remotes / remote), str(other)], check=True, env=self.env)
        self.commit(other, "elsewhere")
        self.git(other, "push", "-q", "origin", "main")
        return self.rev(other, "HEAD")

    def run_tool(self, repo: Path, *args: str, stdin: str | None = None, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), "--repo", str(repo), *args], capture_output=True, text=True,
                              input=stdin if stdin is not None else "", env={**self.env, **env})

    @staticmethod
    def out(result: subprocess.CompletedProcess) -> str:
        return result.stdout + result.stderr

    def hook_line(self, local: str, remote: str, ref: str = "refs/heads/main") -> str:
        return f"{ref} {local} {ref} {remote}\n"


class IdentityTest(PreflightCase):
    def test_clean_brain_passes_with_the_origin_of_each_value(self) -> None:
        repo = self.make_repo()
        self.write_brain_json(repo)
        result = self.run_tool(repo)
        text = self.out(result)
        self.assertEqual(result.returncode, 0, text)
        self.assertIn("OK: GIT_SSH_COMMAND and GIT_SSH are not set", text)
        self.assertIn("OK: user.email = ada@acme.example (from .gitconfig-acme)", text)
        self.assertIn("OK: user.name = Acme Person (from .gitconfig-acme)", text)
        self.assertIn("INFO: core.sshCommand is not set", text)
        self.assertIn('OK: effective user.email matches the "email" pattern of brain.json', text)
        self.assertIn("is not an SSH remote: no SSH test", text)
        self.assertIn("INFO: main is not on origin yet", text)
        self.assertIn("Summary: 0 error(s), 0 warning(s).", text)
        self.assertNotIn("ERROR:", text)

    def test_identity_from_the_repository_config_is_refused(self) -> None:
        repo = self.make_repo()
        self.git(repo, "config", "--local", "user.email", "me@elsewhere.example")
        self.git(repo, "config", "--local", "core.sshCommand", "ssh -o IdentitiesOnly=yes")
        result = self.run_tool(repo)
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertIn("ERROR: user.email = me@elsewhere.example (from .git/config): local override forbidden", text)
        self.assertIn("ERROR: core.sshCommand = ssh -o IdentitiesOnly=yes (from .git/config): local override forbidden", text)
        self.assertIn("OK: user.name = Acme Person (from .gitconfig-acme)", text)  # the value that is not overridden stays fine

    def test_identity_from_the_plain_global_config_is_refused(self) -> None:
        self.write_global("[user]\n    name = Gus Person\n    email = gus@globex.example\n")
        repo = self.make_repo()
        result = self.run_tool(repo)
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertRegex(text, r"ERROR: user\.email = gus@globex\.example \(from (~/)?\.gitconfig\): .*plain global config")
        self.assertRegex(text, r"ERROR: user\.name = Gus Person \(from (~/)?\.gitconfig\)")

    def test_identity_from_the_command_line_environment_is_refused(self) -> None:
        repo = self.make_repo()
        result = self.run_tool(repo, GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="user.email", GIT_CONFIG_VALUE_0="me@elsewhere.example")
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertIn("ERROR: user.email = me@elsewhere.example (from the command line or the GIT_CONFIG_* variables)", text)

    def test_included_file_that_is_not_a_boundary_file_is_a_warning(self) -> None:
        (self.home / "acme-identity.inc").write_text("[user]\n    name = Ada\n    email = ada@acme.example\n", encoding="utf-8")
        self.write_global(f'[includeIf "gitdir:{self.work}/brain-acme/"]\n    path = {self.home}/acme-identity.inc\n')
        repo = self.make_repo()
        result = self.run_tool(repo)
        text = self.out(result)
        self.assertEqual(result.returncode, 0, text)
        self.assertIn("WARN: user.email = ada@acme.example (from acme-identity.inc): not a ~/.gitconfig-<boundary> file", text)

    def test_missing_email_is_an_error(self) -> None:
        repo = self.make_repo("brain-initech", "initech.git")  # no includeIf rule covers this folder
        result = self.run_tool(repo)
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertIn("ERROR: user.email is not set", text)
        self.assertIn("WARN: user.name is not set", text)

    def test_ssh_environment_overrides_are_refused_without_printing_their_value(self) -> None:
        repo = self.make_repo()
        for name in ("GIT_SSH_COMMAND", "GIT_SSH"):
            with self.subTest(name):
                result = self.run_tool(repo, **{name: "/secret/location/key-wrapper"})
                text = self.out(result)
                self.assertEqual(result.returncode, 1, text)
                self.assertIn(f"ERROR: {name} is set in the environment", text)
                self.assertNotIn("/secret/location", text)

    def test_not_a_repository_is_an_error(self) -> None:
        folder = self.root / "plain"
        folder.mkdir()
        result = self.run_tool(folder)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: not a Git working tree", result.stdout)


class BoundaryTest(PreflightCase):
    def test_remote_pattern_mismatch_is_an_error(self) -> None:
        repo = self.make_repo()
        self.write_brain_json(repo, remote="*/remotes/globex.git")
        result = self.run_tool(repo)
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertIn('does not match the "remote" pattern of brain.json (trust boundary)', text)
        self.assertIn('OK: effective user.email matches the "email" pattern', text)

    def test_email_pattern_mismatch_is_an_error(self) -> None:
        repo = self.make_repo()
        self.write_brain_json(repo, email="*@globex.example")
        result = self.run_tool(repo)
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertIn('ERROR: effective user.email ada@acme.example does not match the "email" pattern of brain.json (trust boundary)', text)
        self.assertIn('matches the "remote" pattern of brain.json', text)

    def test_the_push_url_is_the_one_compared(self) -> None:
        repo = self.make_repo()
        self.write_brain_json(repo)
        self.git(repo, "remote", "set-url", "--push", "origin", str(self.make_bare("globex.git")))
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn('does not match the "remote" pattern', self.out(result))

    def test_a_repository_that_is_not_a_brain_has_no_boundary_to_check(self) -> None:
        repo = self.make_repo()
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("INFO: not a brain (no .data/brain.json)", result.stdout)

    def test_unreadable_declaration_is_an_error(self) -> None:
        repo = self.make_repo()
        (repo / ".data").mkdir()
        (repo / ".data/brain.json").write_text("{", encoding="utf-8")
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: .data/brain.json is unreadable", result.stdout)

    def test_undeclared_patterns_are_warnings(self) -> None:
        repo = self.make_repo()
        self.write_brain_json(repo, remote="", email="")
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn('WARN: brain.json declares no "remote" pattern', result.stdout)
        self.assertIn('WARN: brain.json declares no "email" pattern', result.stdout)


class SshTest(PreflightCase):
    def make_stub(self, banner: str, stream: str = "2", exit_code: int = 1) -> Path:
        """An SSH command that records its arguments and answers with a banner (no network)."""
        stub_dir = self.root / "bin"
        stub_dir.mkdir(exist_ok=True)
        (stub_dir / "banner.txt").write_text(banner, encoding="utf-8")
        stub = stub_dir / "ssh-stub"
        stub.write_text(f'#!/usr/bin/env bash\ndir="$(cd "$(dirname "$0")" && pwd)"\nprintf "%s\\n" "$@" > "$dir/args.txt"\ncat "$dir/banner.txt" >&{stream}\nexit {exit_code}\n', encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        self.write_boundary("acme", "ada@acme.example", f"{stub} -o IdentitiesOnly=yes")
        return stub

    def ssh_repo(self, url: str) -> Path:
        repo = self.make_repo()
        self.git(repo, "remote", "set-url", "origin", url)
        return repo

    def stub_args(self) -> list[str]:
        return (self.root / "bin/args.txt").read_text(encoding="utf-8").splitlines()

    def test_github_account_is_reported_through_the_effective_ssh_command(self) -> None:
        self.make_stub("Hi ada-acme! You've successfully authenticated, but GitHub does not provide shell access.\n")
        repo = self.ssh_repo("git@github.example:acme/brain.git")
        result = self.run_tool(repo, "--no-fetch")
        text = self.out(result)
        self.assertEqual(result.returncode, 0, text)
        self.assertIn("OK: SSH authentication to github.example succeeded", text)
        self.assertIn("INFO: SSH account on github.example: ada-acme", text)
        self.assertIn("core.sshCommand = ", text)
        self.assertEqual(self.stub_args(), ["-o", "IdentitiesOnly=yes", "-T", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "git@github.example"])

    def test_gitlab_account_and_port_of_an_ssh_url(self) -> None:
        self.make_stub("Welcome to GitLab, @gus-globex!\n", stream="1", exit_code=0)
        repo = self.ssh_repo("ssh://git@gitlab.example:2222/acme/brain.git")
        result = self.run_tool(repo, "--no-fetch")
        text = self.out(result)
        self.assertEqual(result.returncode, 0, text)
        self.assertIn("INFO: SSH account on gitlab.example: gus-globex", text)
        self.assertEqual(self.stub_args()[-3:], ["-p", "2222", "git@gitlab.example"])

    def test_refused_login_is_an_error(self) -> None:
        self.make_stub("git@github.example: Permission denied (publickey).\n")
        repo = self.ssh_repo("git@github.example:acme/brain.git")
        result = self.run_tool(repo, "--no-fetch")
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertIn("ERROR: SSH authentication to github.example failed: permission denied: the key is not accepted", text)

    def test_unrecognised_answer_is_an_error_and_prints_nothing_of_the_output(self) -> None:
        self.make_stub('Load key "/secret/location/id_test": invalid format\nWelcome, stranger.\n')
        repo = self.ssh_repo("git@github.example:acme/brain.git")
        result = self.run_tool(repo, "--no-fetch")
        text = self.out(result)
        self.assertEqual(result.returncode, 1, text)
        self.assertIn("ERROR: SSH authentication to github.example failed: no GitHub or GitLab account banner", text)
        self.assertNotIn("/secret/location", text)

    def test_no_ssh_skips_the_login_test(self) -> None:
        self.make_stub("Permission denied (publickey).\n")
        repo = self.ssh_repo("git@github.example:acme/brain.git")
        result = self.run_tool(repo, "--no-fetch", "--no-ssh")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertNotIn("SSH authentication", result.stdout)
        self.assertFalse((self.root / "bin/args.txt").exists())

    def test_a_remote_by_path_runs_no_ssh(self) -> None:
        self.make_stub("Permission denied (publickey).\n")
        repo = self.make_repo()
        result = self.run_tool(repo, "--no-fetch")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertFalse((self.root / "bin/args.txt").exists())

    def test_a_silent_ssh_that_hangs_is_cut_after_the_timeout(self) -> None:
        sleeper = self.root / "sleeper"
        sleeper.write_text("#!/usr/bin/env bash\nsleep 30\n", encoding="utf-8")
        sleeper.chmod(sleeper.stat().st_mode | stat.S_IXUSR)
        account, reason = load_module().ssh_probe(str(sleeper), "git", "host.example", None, timeout=1)
        self.assertIsNone(account)
        self.assertIn("no answer within 1 seconds", reason)

    def test_url_parsing_and_redaction(self) -> None:
        module = load_module()
        self.assertEqual(module.ssh_target("git@github.example:acme/brain.git"), ("git", "github.example", None))
        self.assertEqual(module.ssh_target("ssh://git@gitlab.example:2222/acme/brain.git"), ("git", "gitlab.example", "2222"))
        self.assertEqual(module.ssh_target("ssh://gitlab.example/acme/brain.git"), ("git", "gitlab.example", None))
        for url in ("https://host.example/acme/brain.git", "/srv/remotes/acme.git", "../remotes/acme.git", "file:///srv/acme.git"):
            self.assertIsNone(module.ssh_target(url), url)
        self.assertEqual(module.redact("https://user:secret@host.example/acme.git"), "https://***@host.example/acme.git")  # secret-scan: ignore (fictitious URL: tests the redaction)
        self.assertEqual(module.redact("ssh://git:secret@host.example/acme.git"), "ssh://git@host.example/acme.git")  # secret-scan: ignore (fictitious URL: tests the redaction)
        self.assertEqual(module.redact("git@github.example:acme/brain.git"), "git@github.example:acme/brain.git")


class FastForwardTest(PreflightCase):
    def run_hook_mode(self, repo: Path, stdin: str, remote: str = "origin") -> subprocess.CompletedProcess:
        return self.run_tool(repo, "--hook", remote, stdin=stdin)

    def test_hook_fast_forward_new_ref_and_up_to_date(self) -> None:
        repo = self.pushed_repo()
        old = self.rev(repo, "HEAD")
        new = self.commit(repo, "second")
        result = self.run_hook_mode(repo, self.hook_line(new, old))
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("OK: refs/heads/main: fast-forward (1 commit(s))", result.stdout)
        result = self.run_hook_mode(repo, self.hook_line(new, ZEROS, "refs/heads/feature"))
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("OK: refs/heads/feature: new on the remote", result.stdout)
        result = self.run_hook_mode(repo, self.hook_line(new, new))
        self.assertIn("OK: refs/heads/main: already up to date", result.stdout)
        result = self.run_hook_mode(repo, "")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("INFO: no ref update to check", result.stdout)

    def test_hook_remote_that_moved_and_is_unknown_locally_is_an_error(self) -> None:
        repo = self.pushed_repo()
        new = self.commit(repo, "second")
        moved = self.advance_remote()  # not fetched: the commit is unknown here
        result = self.run_hook_mode(repo, self.hook_line(new, moved))
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn("ERROR: refs/heads/main: the remote tip is unknown locally", result.stdout)
        self.assertIn("Push refused", result.stdout)

    def test_hook_non_fast_forward_is_an_error(self) -> None:
        repo = self.pushed_repo()
        new = self.commit(repo, "second")
        moved = self.advance_remote()
        self.git(repo, "fetch", "-q", "origin")
        result = self.run_hook_mode(repo, self.hook_line(new, moved))  # force push over a diverged remote
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn("ERROR: refs/heads/main: history diverged from the remote (force push or remote ahead)", result.stdout)

    def test_hook_remote_ahead_of_the_pushed_commit_is_an_error(self) -> None:
        repo = self.pushed_repo()
        old = self.rev(repo, "HEAD")
        moved = self.advance_remote()
        self.git(repo, "fetch", "-q", "origin")
        result = self.run_hook_mode(repo, self.hook_line(old, moved))
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn("ERROR: refs/heads/main: the remote is ahead by 1 commit(s)", result.stdout)

    def test_hook_remote_ref_deletion_is_an_error(self) -> None:
        repo = self.pushed_repo()
        result = self.run_hook_mode(repo, f"(delete) {ZEROS} refs/heads/old {self.rev(repo, 'HEAD')}\n")
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn("ERROR: refs/heads/old: remote branch deletion refused", result.stdout)

    def test_hook_checks_the_identity_even_without_refs(self) -> None:
        repo = self.pushed_repo()
        self.git(repo, "config", "--local", "user.email", "me@elsewhere.example")
        result = self.run_hook_mode(repo, "")
        self.assertEqual(result.returncode, 1)
        self.assertIn("local override forbidden", result.stdout)

    def test_hook_mode_accepts_a_url_given_by_git(self) -> None:
        repo = self.pushed_repo()
        new = self.commit(repo, "second")
        url = str(self.remotes / "acme.git")
        result = self.run_hook_mode(repo, self.hook_line(new, self.rev(repo, "HEAD~1")), remote=url)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("OK: refs/heads/main: fast-forward", result.stdout)

    def test_manual_ahead_is_fine(self) -> None:
        repo = self.pushed_repo()
        self.commit(repo, "second")
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("OK: main against origin/main: fast-forward (1 commit(s))", result.stdout)

    def test_manual_up_to_date(self) -> None:
        repo = self.pushed_repo()
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("OK: main against origin/main: already up to date", result.stdout)

    def test_manual_behind_is_an_error_after_the_fetch(self) -> None:
        repo = self.pushed_repo()
        self.advance_remote()
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn("ERROR: main against origin/main: the remote is ahead by 1 commit(s)", result.stdout)

    def test_manual_diverged_is_an_error_and_no_fetch_compares_with_the_last_fetch(self) -> None:
        repo = self.pushed_repo()
        self.commit(repo, "second")
        self.advance_remote()
        result = self.run_tool(repo, "--no-fetch")  # stale remote-tracking branch: still a fast-forward
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("INFO: no fetch (--no-fetch)", result.stdout)
        self.assertIn("OK: main against origin/main: fast-forward", result.stdout)
        result = self.run_tool(repo)  # fetches first
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn("ERROR: main against origin/main: history diverged from the remote", result.stdout)

    def test_manual_fetch_failure_is_an_error(self) -> None:
        repo = self.pushed_repo()
        shutil.rmtree(self.remotes / "acme.git")
        result = self.run_tool(repo)
        self.assertEqual(result.returncode, 1, self.out(result))
        self.assertIn("ERROR: fetch of origin failed, remote state unknown", result.stdout)
        self.assertEqual(self.run_tool(repo, "--no-fetch").returncode, 0)

    def test_manual_detached_head_skips_the_check(self) -> None:
        repo = self.pushed_repo()
        self.git(repo, "checkout", "-q", "--detach")
        result = self.run_tool(repo, "--no-fetch")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("WARN: detached HEAD", result.stdout)


class RemoteChoiceTest(PreflightCase):
    def test_upstream_remote_of_the_branch_comes_first(self) -> None:
        repo = self.make_repo()
        self.git(repo, "remote", "add", "backup", str(self.make_bare("backup.git")))
        self.git(repo, "config", "branch.main.remote", "backup")
        self.git(repo, "config", "branch.main.merge", "refs/heads/main")
        result = self.run_tool(repo, "--no-fetch")
        self.assertIn("INFO: remote backup pushes to", result.stdout)

    def test_origin_then_the_only_remote(self) -> None:
        repo = self.make_repo()
        self.git(repo, "remote", "add", "backup", str(self.make_bare("backup.git")))
        self.assertIn("INFO: remote origin pushes to", self.run_tool(repo, "--no-fetch").stdout)
        self.git(repo, "remote", "remove", "origin")
        self.assertIn("INFO: remote backup pushes to", self.run_tool(repo, "--no-fetch").stdout)

    def test_several_remotes_and_none_chosen_is_an_error(self) -> None:
        repo = self.make_repo(remote="alpha")
        self.git(repo, "remote", "add", "beta", str(self.make_bare("beta.git")))
        result = self.run_tool(repo, "--no-fetch")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: no remote to push to", result.stdout)

    def test_unknown_remote_name_is_an_error(self) -> None:
        repo = self.make_repo()
        result = self.run_tool(repo, "nowhere", "--no-fetch")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR: remote nowhere not found", result.stdout)


class PrePushHookTest(PreflightCase):
    """The wrapper end to end: a real `git push` to a bare remote, with the hook installed as bootstrap.sh does."""

    def install_hook(self, repo: Path, work: Path) -> None:
        (work / "tools/machine/hooks").mkdir(parents=True, exist_ok=True)
        shutil.copy2(TOOL, work / "tools/machine/preflight-push.py")
        hook = repo / ".git/hooks/pre-push"
        hook.parent.mkdir(exist_ok=True)
        shutil.copy2(HOOK, hook)
        hook.chmod(0o755)

    def push(self, repo: Path, *args: str) -> subprocess.CompletedProcess:
        return self.git(repo, "push", *args, check=False)

    def remote_main(self, bare: str = "acme.git") -> str | None:
        result = subprocess.run(["git", "--git-dir", str(self.remotes / bare), "rev-parse", "-q", "--verify", "refs/heads/main"],
                                capture_output=True, text=True, env=self.env)
        return result.stdout.strip() or None

    def test_brain_push_passes_the_checks(self) -> None:
        repo = self.make_repo()
        self.write_brain_json(repo)
        self.install_hook(repo, self.work)
        result = self.push(repo, "origin", "main")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("OK: user.email = ada@acme.example (from .gitconfig-acme)", result.stderr)
        self.assertIn("OK: refs/heads/main: new on the remote", result.stderr)
        self.assertEqual(self.remote_main(), self.rev(repo, "HEAD"))
        second = self.commit(repo, "second")
        result = self.push(repo, "origin", "main")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("fast-forward (1 commit(s))", result.stderr)
        self.assertEqual(self.remote_main(), second)

    def test_the_work_repository_itself_is_covered(self) -> None:
        work = self.work
        subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True, env=self.env)
        self.git(work, "remote", "add", "starter", str(self.make_bare("starter.git")))
        self.commit(work, "first")
        self.install_hook(work, work)
        result = self.push(work, "starter", "main")
        self.assertEqual(result.returncode, 0, self.out(result))
        self.assertIn("INFO: not a brain", result.stderr)
        self.assertEqual(self.remote_main("starter.git"), self.rev(work, "HEAD"))

    def test_identity_from_the_clone_config_refuses_the_push(self) -> None:
        repo = self.make_repo()
        self.install_hook(repo, self.work)
        self.git(repo, "config", "--local", "user.email", "me@elsewhere.example")
        result = self.push(repo, "origin", "main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR: user.email = me@elsewhere.example (from .git/config)", result.stderr)
        self.assertIn("Push refused", result.stderr)
        self.assertIsNone(self.remote_main())

    def test_brain_boundary_mismatch_refuses_the_push(self) -> None:
        repo = self.make_repo()
        self.write_brain_json(repo, remote="*/remotes/globex.git")
        self.install_hook(repo, self.work)
        result = self.push(repo, "origin", "main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('does not match the "remote" pattern of brain.json', result.stderr)
        self.assertIsNone(self.remote_main())

    def test_environment_override_refuses_the_push(self) -> None:
        repo = self.make_repo()
        self.install_hook(repo, self.work)
        result = self.git(repo, "push", "origin", "main", check=False, GIT_SSH_COMMAND="ssh -o IdentitiesOnly=yes")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ERROR: GIT_SSH_COMMAND is set in the environment", result.stderr)
        self.assertIsNone(self.remote_main())

    def test_force_push_over_a_diverged_remote_is_refused(self) -> None:
        repo = self.pushed_repo()
        self.install_hook(repo, self.work)
        moved = self.advance_remote()
        self.commit(repo, "local")
        self.git(repo, "fetch", "-q", "origin")
        result = self.push(repo, "--force", "origin", "main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("history diverged from the remote", result.stderr)
        self.assertEqual(self.remote_main(), moved)

    def test_remote_branch_deletion_is_refused(self) -> None:
        repo = self.pushed_repo()
        self.install_hook(repo, self.work)
        result = self.push(repo, "origin", ":main")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remote branch deletion refused", result.stderr)
        self.assertEqual(self.remote_main(), self.rev(repo, "HEAD"))


if __name__ == "__main__":
    unittest.main()
