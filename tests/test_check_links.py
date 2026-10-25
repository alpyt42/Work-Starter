"""Regression checks for portable brain link validation."""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "tools/brain/check-links.py"


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
            self.assertIn("unverified local links: 4", portable.stdout)
            self.assertIn("⚠ DEAD MD LINK (../artifacts/missing.md) — 3× (local, non-blocking)", portable.stdout)
            self.assertIn("⚠ DEAD MD LINK (../repos/missing/README.md) — 1× (local, non-blocking)", portable.stdout)
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
            self.assertIn("⛔ DEAD MD LINK (missing.md)", broken.stdout)
            self.assertIn("⛔ DEAD MD LINK (../../elsewhere.md)", broken.stdout)
            self.assertIn("⚠ DEAD MD LINK (../artifacts/missing.md)", broken.stdout)
            self.assertIn("⚠ DEAD MD LINK (../repos/missing/README.md)", broken.stdout)

    def test_templates_under_skill_assets_are_skipped_but_the_rest_is_checked(self) -> None:
        for use_git in (False, True):
            if use_git and not shutil.which("git"):
                continue
            with self.subTest(git=use_git), tempfile.TemporaryDirectory() as directory:
                brain = Path(directory) / "Work" / "brain"
                files = {
                    "index.md": "[skill](skills/demo/SKILL.md)\n[x](projects/assets/note.md)\n",
                    "projects/assets/note.md": "# Note\n",
                    "skills/demo/SKILL.md": "[guide](references/guide.md)\n",
                    "skills/demo/references/guide.md": "# Guide\n",
                    # placeholders of a template copied elsewhere by the skill
                    "skills/demo/assets/common/AGENTS.md": "[spec](SPEC.md)\n[plan](PLAN.md)\n",
                    "skills/demo/assets/common/docs/deep.md": "[x](../../nothing.md)\n",
                }
                for relative, text in files.items():
                    (brain / relative).parent.mkdir(parents=True, exist_ok=True)
                    (brain / relative).write_text(text, encoding="utf-8")
                if use_git:
                    subprocess.run(["git", "init", "-q", str(brain)], check=True, env={**os.environ, "GIT_CONFIG_GLOBAL": os.devnull})

                def check() -> subprocess.CompletedProcess[str]:
                    return subprocess.run([sys.executable, str(CHECKER)], env={**os.environ, "BRAIN_DIR": str(brain)},
                                          capture_output=True, text=True, check=False)

                result = check()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("files         : 4", result.stdout)
                self.assertIn("dead (md)     : 0", result.stdout)

                # The rest of skills/ and an `assets` folder elsewhere are still checked.
                (brain / "skills/demo/references/guide.md").write_text("[dead](missing.md)\n", encoding="utf-8")
                (brain / "projects/assets/note.md").write_text("[dead](absent.md)\n", encoding="utf-8")
                result = check()
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("⛔ DEAD MD LINK (missing.md)", result.stdout)
                self.assertIn("⛔ DEAD MD LINK (absent.md)", result.stdout)
                self.assertNotIn("SPEC.md", result.stdout)

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
                self.assertNotIn("dead (md)", result.stdout)


class DefaultBrainTest(unittest.TestCase):
    """Without BRAIN_DIR, the checked brain is the default one of the Work root (tools/machine/work_config.py)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.work = Path(self._tmp.name).resolve() / "Work"
        for name, link in (("brain", "[x](missing-a.md)"), ("brain-initech", "[x](missing-b.md)")):
            (self.work / name / ".data").mkdir(parents=True)
            (self.work / name / "AGENTS.md").write_text("# test\n", encoding="utf-8")
            (self.work / name / "index.md").write_text(link + "\n", encoding="utf-8")

    def check(self, **env: str) -> subprocess.CompletedProcess[str]:
        base = {key: value for key, value in os.environ.items() if key not in ("BRAIN_DIR", "BRAIN")}
        return subprocess.run([sys.executable, str(CHECKER)], env={**base, "WORK_DIR": str(self.work), **env},
                              capture_output=True, text=True, check=False)

    def test_brain_then_the_setting_then_the_only_brain(self) -> None:
        self.assertIn("DEAD MD LINK (missing-a.md)", self.check().stdout)
        (self.work / "work-config.local.json").write_text('{"version": 1, "defaultBrain": "brain-initech"}', encoding="utf-8")
        self.assertIn("DEAD MD LINK (missing-b.md)", self.check().stdout)
        self.assertIn("DEAD MD LINK (missing-a.md)", self.check(BRAIN_DIR=str(self.work / "brain")).stdout)  # BRAIN_DIR wins
        (self.work / "work-config.local.json").unlink()
        shutil.rmtree(self.work / "brain")
        self.assertIn("DEAD MD LINK (missing-b.md)", self.check().stdout)  # the only brain

    def test_without_any_brain_or_with_an_invalid_setting_it_fails_clearly(self) -> None:
        shutil.rmtree(self.work / "brain")
        shutil.rmtree(self.work / "brain-initech")
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("brain not found", result.stderr)
        (self.work / "work-config.local.json").write_text('{"version": 1, "defaultBrain": "brain-nope"}', encoding="utf-8")
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertIn("defaultBrain brain-nope is not a brain", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


class CrossBrainLinksTest(unittest.TestCase):
    """A brain is a trust boundary: no Markdown link from one brain into another."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.work = Path(self._tmp.name).resolve() / "Work"
        for name in ("brain", "brain-perso", "brain-asso"):
            (self.work / name / "projects").mkdir(parents=True)
        (self.work / "brain-perso/notes.md").write_text("# Personal notes\n", encoding="utf-8")
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
        self.assertIn("cross-brain   : 1", result.stdout)
        self.assertIn("dead (md)     : 0", result.stdout)
        self.assertIn("⛔ CROSS-BRAIN LINK (../brain-perso/notes.md) — 1×", result.stdout)
        self.assertIn("       index.md", result.stdout)

    def test_nested_file_and_missing_target_are_reported_as_cross_brain_not_dead(self) -> None:
        self.write("brain", "projects/clients/acme/acme.md", "[x](../../../../brain-asso/projects/missing.md)\n")
        result = self.check("brain")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("cross-brain   : 1", result.stdout)
        self.assertIn("dead (md)     : 0", result.stdout)
        self.assertIn("(../../../../brain-asso/projects/missing.md)", result.stdout)

    def test_folder_and_non_markdown_targets_in_another_brain_are_refused(self) -> None:
        self.write("brain", "index.md", "[inbox](../brain-perso/projects/)\n[data](../brain-perso/.data/doctor.json)\n")
        result = self.check("brain")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("cross-brain   : 2", result.stdout)

    def test_allow_missing_local_does_not_excuse_a_cross_brain_link(self) -> None:
        self.write("brain", "index.md", "[perso](../brain-perso/notes.md)\n[art](../artifacts/missing.md)\n")
        result = self.check("brain", "--allow-missing-local")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("CROSS-BRAIN LINK", result.stdout)
        self.assertIn("unverified local links: 1", result.stdout)

    def test_the_rule_applies_from_every_brain(self) -> None:
        self.write("brain-perso", "index.md", "[page](../brain/page.md)\n")
        result = self.check("brain-perso")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("⛔ CROSS-BRAIN LINK (../brain/page.md)", result.stdout)

    def test_links_inside_the_brain_and_to_shared_folders_are_fine(self) -> None:
        (self.work / "artifacts").mkdir()
        (self.work / "artifacts/out.md").write_text("# Out\n", encoding="utf-8")
        self.write("brain-perso", "index.md",
                   "[notes](notes.md)\n[self](../brain-perso/notes.md)\n[kit](../kit/brain/AGENTS.md)\n"
                   "[art](../artifacts/out.md)\n[web](https://example.org/brain-perso/x.md)\n")
        result = self.check("brain-perso")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("cross-brain   : 0", result.stdout)

    def test_names_that_only_look_like_brains_are_not_brains(self) -> None:
        (self.work / "brain-notes-archive").mkdir()
        (self.work / "brainstorm").mkdir()
        (self.work / "brainstorm/x.md").write_text("# x\n", encoding="utf-8")
        self.write("brain", "index.md", "[x](../brainstorm/x.md)\n")
        result = self.check("brain")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(shutil.which("uv") and shutil.which("bash"), "uv and bash are required")
class CheckLinksScriptTest(unittest.TestCase):
    """tools/machine/check-links.sh checks every brain, even after a failing one."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        for source in ("tools/machine/check-links.sh", "tools/machine/work_config.py", "tools/machine/sync-house-skills.py",
                       "tools/brain/check-links.py"):
            (self.root / source).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO / source, self.root / source)
        for name in ("brain", "brain-perso", "brain-zeta"):
            (self.root / name / ".data").mkdir(parents=True)
            (self.root / name / "AGENTS.md").write_text("# brain\n", encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(self.root / "tools/machine/check-links.sh")],
                              env={**os.environ, "WORK_DIR": str(self.root)}, capture_output=True, text=True, check=False)

    def test_every_brain_is_checked_and_any_failure_fails_the_script(self) -> None:
        self.assertEqual(self.check().returncode, 0)
        (self.root / "brain/index.md").write_text("[dead](first-missing.md)\n", encoding="utf-8")
        (self.root / "brain-perso/index.md").write_text("[dead](second-missing.md)\n", encoding="utf-8")
        (self.root / "brain-zeta/index.md").write_text("[ok](index.md)\n", encoding="utf-8")
        result = self.check()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        for expected in ("== brain ==", "== brain-perso ==", "== brain-zeta ==", "first-missing.md", "second-missing.md"):
            self.assertIn(expected, result.stdout)
        self.assertNotIn("Skill links OK", result.stdout)

        (self.root / "brain/index.md").write_text("[ok](index.md)\n", encoding="utf-8")
        later = self.check()  # the first brain is fine, a later one still fails the script
        self.assertNotEqual(later.returncode, 0, later.stdout + later.stderr)
        self.assertIn("second-missing.md", later.stdout)

        (self.root / "brain-perso/index.md").write_text("[ok](index.md)\n", encoding="utf-8")
        clean = self.check()
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertIn("Skill links OK", clean.stdout)


if __name__ == "__main__":
    unittest.main()
