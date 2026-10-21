"""Regression checks for portable brain link validation."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "tools/brain/check-links.py"


class CheckLinksTest(unittest.TestCase):
    def test_missing_local_assets_are_reported_without_masking_brain_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            brain = Path(directory) / "Work" / "brain"
            brain.mkdir(parents=True)
            (brain / "index.md").write_text(
                "[page](page.md)\n"
                "[local artifact](../artifacts/missing.md)\n"
                "[local repo](../repos/missing/README.md)\n",
                encoding="utf-8",
            )
            (brain / "page.md").write_text(
                "# Existing page\n"
                "[artifact A](../artifacts/missing.md)\n"
                "[artifact B](../artifacts/missing.md)\n",
                encoding="utf-8",
            )

            def check(*args: str) -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [sys.executable, str(CHECKER), *args],
                    env={**os.environ, "BRAIN_DIR": str(brain)},
                    capture_output=True,
                    text=True,
                    check=False,
                )

            strict = check()
            self.assertEqual(strict.returncode, 1, strict.stdout + strict.stderr)

            portable = check("--allow-missing-local")
            self.assertEqual(portable.returncode, 0, portable.stdout + portable.stderr)
            self.assertIn("liens locaux non vérifiés: 4", portable.stdout)
            self.assertIn("⚠ LIEN MD MORT (../artifacts/missing.md) — 3× (local, non bloquant)", portable.stdout)
            self.assertIn("⚠ LIEN MD MORT (../repos/missing/README.md) — 1× (local, non bloquant)", portable.stdout)
            self.assertIn("       index.md", portable.stdout)
            self.assertIn("       page.md", portable.stdout)

            (brain / "index.md").write_text(
                "[broken brain link](missing.md)\n"
                "[local artifact](../artifacts/missing.md)\n"
                "[local repo](../repos/missing/README.md)\n"
                "[unknown external](../../elsewhere.md)\n",
                encoding="utf-8",
            )
            broken = check("--allow-missing-local")
            self.assertEqual(broken.returncode, 1, broken.stdout + broken.stderr)
            self.assertIn("⛔ LIEN MD MORT (missing.md)", broken.stdout)
            self.assertIn("⛔ LIEN MD MORT (../../elsewhere.md)", broken.stdout)
            self.assertIn("⚠ LIEN MD MORT (../artifacts/missing.md)", broken.stdout)
            self.assertIn("⚠ LIEN MD MORT (../repos/missing/README.md)", broken.stdout)

    def test_missing_or_empty_brain_fails_instead_of_reporting_zero_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            empty = Path(directory) / "empty"
            empty.mkdir()
            for brain in (Path(directory) / "absent", empty):
                result = subprocess.run(
                    [sys.executable, str(CHECKER)],
                    env={**os.environ, "BRAIN_DIR": str(brain)},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn("morts (md)", result.stdout)


class CrossBrainLinksTest(unittest.TestCase):
    """A brain is a trust boundary: no Markdown link from one brain into another."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        for name in ("brain", "brain-perso", "brain-asso"):
            (self.work / name / "projects").mkdir(parents=True)
        (self.work / "brain-perso/notes.md").write_text("# Notes perso\n", encoding="utf-8")
        (self.work / "brain/page.md").write_text("# Page\n", encoding="utf-8")
        (self.work / "kit/brain").mkdir(parents=True)
        (self.work / "kit/brain/AGENTS.md").write_text("# Conventions\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def check(self, brain: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), *args],
            env={**os.environ, "BRAIN_DIR": str(self.work / brain)},
            capture_output=True,
            text=True,
            check=False,
        )

    def write(self, brain: str, relative: str, text: str) -> None:
        path = self.work / brain / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_link_into_another_brain_fails_even_when_the_target_exists(self) -> None:
        self.write("brain", "index.md", "[page](page.md)\n[perso](../brain-perso/notes.md)\n")
        result = self.check("brain")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("inter-brains  : 1", result.stdout)
        self.assertIn("morts (md)    : 0", result.stdout)
        self.assertIn("⛔ LIEN INTER-BRAINS (../brain-perso/notes.md) — 1×", result.stdout)
        self.assertIn("       index.md", result.stdout)

    def test_nested_file_and_missing_target_are_reported_as_cross_brain_not_dead(self) -> None:
        self.write("brain", "projects/clients/acme/acme.md", "[x](../../../../brain-asso/projects/missing.md)\n")
        result = self.check("brain")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("inter-brains  : 1", result.stdout)
        self.assertIn("morts (md)    : 0", result.stdout)
        self.assertIn("(../../../../brain-asso/projects/missing.md)", result.stdout)

    def test_folder_and_non_markdown_targets_in_another_brain_are_refused(self) -> None:
        self.write("brain", "index.md", "[inbox](../brain-perso/projects/)\n[data](../brain-perso/.data/doctor.json)\n")
        result = self.check("brain")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("inter-brains  : 2", result.stdout)

    def test_allow_missing_local_does_not_excuse_a_cross_brain_link(self) -> None:
        self.write("brain", "index.md", "[perso](../brain-perso/notes.md)\n[art](../artifacts/missing.md)\n")
        result = self.check("brain", "--allow-missing-local")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("LIEN INTER-BRAINS", result.stdout)
        self.assertIn("liens locaux non vérifiés: 1", result.stdout)

    def test_the_rule_applies_from_every_brain(self) -> None:
        self.write("brain-perso", "index.md", "[page](../brain/page.md)\n")
        result = self.check("brain-perso")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("⛔ LIEN INTER-BRAINS (../brain/page.md)", result.stdout)

    def test_links_inside_the_brain_and_to_shared_folders_are_fine(self) -> None:
        (self.work / "artifacts").mkdir()
        (self.work / "artifacts/out.md").write_text("# Out\n", encoding="utf-8")
        self.write("brain-perso", "index.md",
                   "[notes](notes.md)\n[self](../brain-perso/notes.md)\n[kit](../kit/brain/AGENTS.md)\n"
                   "[art](../artifacts/out.md)\n[web](https://example.org/brain-perso/x.md)\n")
        result = self.check("brain-perso")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("inter-brains  : 0", result.stdout)

    def test_names_that_only_look_like_brains_are_not_brains(self) -> None:
        (self.work / "brain-notes-archive").mkdir()
        (self.work / "brainstorm").mkdir()
        (self.work / "brainstorm/x.md").write_text("# x\n", encoding="utf-8")
        self.write("brain", "index.md", "[x](../brainstorm/x.md)\n")
        result = self.check("brain")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
