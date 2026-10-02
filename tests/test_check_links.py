"""Regression checks for portable brain link validation."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "tools/check-links.py"


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


if __name__ == "__main__":
    unittest.main()
