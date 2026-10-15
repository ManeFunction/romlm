import os
import subprocess
import sys
import tempfile
import unittest

ROMLM = os.path.join(os.path.dirname(__file__), "..", "src", "romlm.py")

FILES = [
    "Zelda (USA).nes", "Zelda (Japan).nes", "Mario (USA).nes", "Hb (Homebrew).nes",
    "[BIOS] Sega CD (USA).bin", "Sub/Contra (USA).nes", "Sub/Contra (USA) (Beta).nes",
]


def tree(root):
    return sorted(os.path.relpath(os.path.join(d, f), root) for d, _, files in os.walk(root) for f in files)


class CommandLineTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for name in FILES:
            path = os.path.join(self.folder.name, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            open(path, "w").close()

    def romlm(self, *args):
        return subprocess.run([sys.executable, ROMLM, "-i", self.folder.name, *args],
                              capture_output=True, text=True, stdin=subprocess.DEVNULL)

    def test_dry_run_changes_nothing_and_reports_the_work(self):
        before = tree(self.folder.name)
        result = self.romlm("-r", "-s", "-p", "zip", "-n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(tree(self.folder.name), before)
        self.assertIn("DRY RUN", result.stdout)
        self.assertIn("Would pack", result.stdout)
        self.assertIn("Summary: 2 duplicate(s) to remove, 1 file(s) to move, 4 file(s) to pack.", result.stdout)

    def test_real_run_does_what_the_dry_run_said(self):
        result = self.romlm("-r", "-s")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(tree(self.folder.name), sorted([
            os.path.join("!!BIOS", "[BIOS] Sega CD (USA).bin"), os.path.join("!Homebrew", "Hb (Homebrew).nes"),
            os.path.join("C", "Contra (USA).nes"), os.path.join("M", "Mario (USA).nes"),
            os.path.join("Z", "Zelda (USA).nes"),
        ]))

    def test_nothing_to_do(self):
        result = self.romlm()
        self.assertEqual(result.returncode, 0)
        self.assertIn("Nothing to do", result.stdout)


if __name__ == "__main__":
    unittest.main()
