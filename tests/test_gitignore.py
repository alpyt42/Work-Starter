"""Regression checks for the ignore rules: local files that can name clients stay out of Git (no network)."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def ignored(repo: Path, relative: str) -> bool:
    """True when Git ignores the path (check-ignore exits 0), False when it does not (exit 1)."""
    (repo / relative).parent.mkdir(parents=True, exist_ok=True)
    (repo / relative).write_text("x\n", encoding="utf-8")
    result = subprocess.run(["git", "check-ignore", "-q", relative], cwd=repo, env=GIT_ENV, capture_output=True, text=True)
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


@unittest.skipUnless(shutil.which("git"), "git is required")
class RootIgnoreRulesTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name).resolve()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True, env=GIT_ENV)
        shutil.copy(REPO / ".gitignore", self.repo / ".gitignore")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_dotfiles_at_the_root_of_tools_are_ignored_except_the_env_example(self) -> None:
        for private in ("tools/.local-cache.json", "tools/.some-config.json", "tools/.env", "tools/.env.local"):
            self.assertTrue(ignored(self.repo, private), private)
        self.assertFalse(ignored(self.repo, "tools/.env.example"))

    def test_other_files_of_tools_are_still_tracked(self) -> None:
        for public in ("tools/README.md", "tools/machine/.hidden-but-versioned", "tools/brain/check-links.py"):
            self.assertFalse(ignored(self.repo, public), public)


if __name__ == "__main__":
    unittest.main()
