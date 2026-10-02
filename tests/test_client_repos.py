"""Regression checks for the client repository catalog tool (no network)."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).resolve().parents[1] / "tools/client-repos.py"
URL_A = "git@git.example.test:acme/app.git"
URL_B = "git@git.example.test:acme/api.git"
URL_BY_REMOTE = "git@git.example.test:by-url/app.git"


class ClientReposTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.work = self.root / "Work"
        (self.work / "brain/.data").mkdir(parents=True)
        (self.work / "repos").mkdir()
        # A test ~/.gitconfig: one folder rule, one remote URL rule, no global identity.
        (self.root / "gitconfig-acme").write_text(
            "[user]\n  name = Acme Author\n  email = acme@example.test\n"
            "[core]\n  sshCommand = ssh -i /keys/id_acme -o IdentitiesOnly=yes\n",
            encoding="utf-8",
        )
        (self.root / "gitconfig-by-url").write_text(
            "[user]\n  name = Url Author\n  email = url@example.test\n", encoding="utf-8"
        )
        self.gitconfig = self.root / "gitconfig"
        self.gitconfig.write_text(
            "[user]\n  useConfigOnly = true\n"
            f'[includeIf "gitdir:{self.work}/repos/acme/"]\n  path = {self.root}/gitconfig-acme\n'
            f'[includeIf "hasconfig:remote.*.url:git@git.example.test:by-url/**"]\n'
            f"  path = {self.root}/gitconfig-by-url\n",
            encoding="utf-8",
        )
        self.env = {
            **os.environ,
            "WORK_DIR": str(self.work),
            "BRAIN_DIR": str(self.work / "brain"),
            "GIT_CONFIG_GLOBAL": str(self.gitconfig),
            "GIT_CONFIG_NOSYSTEM": "1",
        }

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_catalog(self, repositories: list, schema_version: int = 1) -> None:
        (self.work / "brain/.data/client-repos.json").write_text(
            json.dumps({"schema_version": schema_version, "repositories": repositories}),
            encoding="utf-8",
        )

    def run_tool(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(TOOL), *args], env=self.env, capture_output=True, text=True, check=False
        )

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args], env=self.env, capture_output=True, text=True, check=True
        ).stdout.strip()

    def make_clone(self, relative: str, url: str) -> None:
        target = self.work / relative
        target.mkdir(parents=True)
        self.git("init", "-q", str(target))
        self.git("-C", str(target), "remote", "add", "origin", url)

    def serve_locally(self, url: str) -> None:
        """Make `git clone <url>` read a local bare repository instead of the network."""
        bare = self.root / f"bare-{abs(hash(url))}.git"
        source = self.root / f"source-{abs(hash(url))}"
        self.git("init", "-q", "-b", "main", str(source))
        self.git("-C", str(source), "-c", "user.name=T", "-c", "user.email=t@example.test",
                 "commit", "-q", "--allow-empty", "-m", "init")
        self.git("clone", "-q", "--bare", str(source), str(bare))
        with self.gitconfig.open("a", encoding="utf-8") as handle:
            handle.write(f'[url "file://{bare}"]\n  insteadOf = {url}\n')

    def test_list_filters_by_client_or_path(self) -> None:
        self.write_catalog([
            {"path": "repos/acme/app", "url": URL_A},
            {"path": "repos/other/api", "url": URL_B},
        ])
        everything = self.run_tool("list")
        self.assertEqual(everything.returncode, 0, everything.stderr)
        self.assertEqual(len(everything.stdout.splitlines()), 2)

        one_client = self.run_tool("list", "acme")
        self.assertEqual(one_client.stdout.strip(), f"repos/acme/app  {URL_A}")

        one_path = self.run_tool("list", "repos/other/api")
        self.assertEqual(one_path.stdout.strip(), f"repos/other/api  {URL_B}")

        unknown = self.run_tool("list", "nobody")
        self.assertEqual(unknown.returncode, 1)
        self.assertIn("unknown client or repository", unknown.stderr)

    def test_check_reports_ok_absent_and_different_origins(self) -> None:
        self.write_catalog([
            {"path": "repos/acme/app", "url": URL_A},
            {"path": "repos/acme/api", "url": URL_B},
            {"path": "repos/acme/missing", "url": URL_A},
        ])
        self.make_clone("repos/acme/app", URL_A)
        self.make_clone("repos/acme/api", "git@git.example.test:acme/moved.git")

        result = self.run_tool("check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("OK        repos/acme/app", result.stdout)
        self.assertIn("DIFFÉRENT repos/acme/api", result.stdout)
        self.assertIn("ABSENT    repos/acme/missing", result.stdout)

        self.write_catalog([{"path": "repos/acme/app", "url": URL_A}])
        self.assertEqual(self.run_tool("check").returncode, 0)

    def test_check_shows_effective_identity_and_its_origin(self) -> None:
        self.write_catalog([
            {"path": "repos/acme/app", "url": URL_A},
            {"path": "repos/other/by-url", "url": URL_BY_REMOTE},
            {"path": "repos/other/uncovered", "url": URL_B},
        ])
        self.make_clone("repos/acme/app", URL_A)
        self.make_clone("repos/other/by-url", URL_BY_REMOTE)
        self.make_clone("repos/other/uncovered", URL_B)

        result = self.run_tool("check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "OK        repos/acme/app  auteur=acme@example.test (gitconfig-acme) · clé=/keys/id_acme (gitconfig-acme)",
            result.stdout,
        )
        self.assertIn(
            "OK        repos/other/by-url  auteur=url@example.test (gitconfig-by-url) · clé=choisie par ~/.ssh/config",
            result.stdout,
        )
        self.assertIn("IDENTITÉ  repos/other/uncovered  auteur=aucun", result.stdout)

        self.git("-C", str(self.work / "repos/acme/app"), "config", "user.email", "local@example.test")
        local = self.run_tool("check", "repos/acme/app")
        self.assertIn("auteur=local@example.test (clone local)", local.stdout)

    def test_check_masks_non_ssh_origins(self) -> None:
        self.write_catalog([{"path": "repos/acme/app", "url": URL_A}])
        self.make_clone("repos/acme/app", "https://user:secret@git.example.test/acme/app.git")
        result = self.run_tool("check")
        self.assertEqual(result.returncode, 1)
        self.assertIn("<URL non SSH masquée>", result.stdout)
        self.assertNotIn("secret", result.stdout)

    def test_catalog_rejects_unsafe_entries(self) -> None:
        cases = [
            ("unsafe repository path", [{"path": "repos/../etc", "url": URL_A}]),
            ("unsafe repository path", [{"path": "elsewhere/acme/app", "url": URL_A}]),
            ("non-SSH URL", [{"path": "repos/acme/app", "url": "https://git.example.test/acme/app.git"}]),
            ("only path and url", [{"path": "repos/acme/app", "url": URL_A, "branch": "main"}]),
            ("duplicate repository path", [
                {"path": "repos/acme/app", "url": URL_A},
                {"path": "repos/acme/app", "url": URL_B},
            ]),
        ]
        for message, repositories in cases:
            with self.subTest(repositories=repositories):
                self.write_catalog(repositories)
                result = self.run_tool("list")
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn(message, result.stderr)

        self.write_catalog([{"path": "repos/acme/app", "url": URL_A}], schema_version=2)
        self.assertIn("unsupported", self.run_tool("list").stderr)

    def test_clone_inherits_home_rules_without_local_identity(self) -> None:
        self.write_catalog([{"path": "repos/acme/app", "url": URL_A}])
        self.serve_locally(URL_A)
        result = self.run_tool("clone", "acme")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("CLONÉ       repos/acme/app  auteur=acme@example.test (gitconfig-acme)", result.stdout)
        clone = self.work / "repos/acme/app"
        local = subprocess.run(
            ["git", "-C", str(clone), "config", "--local", "--get-regexp", r"^(user\.|core\.sshcommand)"],
            env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(local.stdout, "", "clone must not carry a local identity")

    def test_clone_uses_remote_url_rule_outside_covered_folders(self) -> None:
        self.write_catalog([{"path": "repos/other/by-url", "url": URL_BY_REMOTE}])
        self.serve_locally(URL_BY_REMOTE)
        result = self.run_tool("clone", "other")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("auteur=url@example.test (gitconfig-by-url)", result.stdout)

    def test_clone_refuses_destination_without_home_rule(self) -> None:
        self.write_catalog([{"path": "repos/other/uncovered", "url": URL_B}])
        result = self.run_tool("clone", "other")
        self.assertEqual(result.returncode, 1)
        self.assertIn("no ~/.gitconfig rule gives an author", result.stderr)
        self.assertFalse((self.work / "repos/other/uncovered").exists())

    def test_clone_override_requires_an_owner_only_key_outside_work(self) -> None:
        self.write_catalog([{"path": "repos/acme/app", "url": URL_A}])
        inside = self.work / "key"
        inside.write_text("not a key", encoding="utf-8")
        inside.chmod(0o600)
        outside = self.root / "key"
        outside.write_text("not a key", encoding="utf-8")
        outside.chmod(0o644)
        author = ("--author-name", "Test Author", "--author-email", "author@example.test")

        relative = self.run_tool("clone", "acme", "--identity", "key", *author)
        self.assertIn("absolute key path", relative.stderr)
        in_work = self.run_tool("clone", "acme", "--identity", str(inside), *author)
        self.assertIn("outside Work", in_work.stderr)
        too_open = self.run_tool("clone", "acme", "--identity", str(outside), *author)
        self.assertIn("owner-only", too_open.stderr)
        outside.chmod(0o600)
        incomplete = self.run_tool("clone", "acme", "--identity", str(outside))
        self.assertIn("override needs", incomplete.stderr)
        self.assertFalse((self.work / "repos/acme/app").exists())


if __name__ == "__main__":
    unittest.main()
