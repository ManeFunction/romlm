import os
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

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


class PackGameFoldersTest(unittest.TestCase):
    def test_game_folders_are_packed_and_sorted_as_a_whole(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ("Sonic CD (USA)/Sonic CD (USA).cue", "Sonic CD (USA)/Sonic CD (USA) (Track 01).bin",
                         "Lunar (USA)/game.iso", "Zelda (USA).nes"):
                os.makedirs(os.path.dirname(os.path.join(root, name)), exist_ok=True)
                open(os.path.join(root, name), "w").close()
            result = subprocess.run([sys.executable, ROMLM, "-i", root, "-p", "zip", "-s"],
                                    capture_output=True, text=True, stdin=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(tree(root), sorted([os.path.join("S", "Sonic CD (USA).zip"),
                                                 os.path.join("L", "Lunar (USA).zip"),
                                                 os.path.join("Z", "Zelda (USA).nes.zip")]))
            with zipfile.ZipFile(os.path.join(root, "S", "Sonic CD (USA).zip")) as z:
                self.assertEqual(sorted(z.namelist()), ["Sonic CD (USA) (Track 01).bin", "Sonic CD (USA).cue"])


class ExtractTest(unittest.TestCase):
    ARCHIVES = {
        "Single (USA).zip": ["Single (USA).nes"],
        "Generic (USA).zip": ["game.iso"],
        "Many (USA).zip": ["Many (USA).cue", "Many (USA).bin"],
    }

    def extract(self, *args, existing=()):
        with tempfile.TemporaryDirectory() as root:
            for name in existing:
                open(os.path.join(root, name), "w").close()
            for name, entries in self.ARCHIVES.items():
                with zipfile.ZipFile(os.path.join(root, name), "w") as z:
                    for entry in entries:
                        z.writestr(entry, "data")
            result = subprocess.run([sys.executable, ROMLM, "-i", root, "-x", *args],
                                    capture_output=True, text=True, stdin=subprocess.DEVNULL)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.output = result.stdout
            return tree(root)

    def test_default_makes_folders_only_for_many_files_or_generic_names(self):
        self.assertEqual(self.extract(), sorted([
            "Single (USA).nes", os.path.join("Generic (USA)", "game.iso"),
            os.path.join("Many (USA)", "Many (USA).bin"), os.path.join("Many (USA)", "Many (USA).cue"),
        ]))

    def test_default_makes_folders_for_archives_with_the_same_files(self):
        self.ARCHIVES = {"Game (USA).zip": ["Game.nes"], "Game (USA) (Rev 1).zip": ["Game.nes"],
                         "Other (USA).zip": ["Other.nes"]}
        self.assertEqual(self.extract(), sorted([
            os.path.join("Game (USA)", "Game.nes"), os.path.join("Game (USA) (Rev 1)", "Game.nes"), "Other.nes",
        ]))

    def test_default_does_not_overwrite_the_files_on_disk(self):
        self.assertEqual(self.extract(existing=["Single (USA).nes"]), sorted([
            "Single (USA).nes", os.path.join("Single (USA)", "Single (USA).nes"),
            os.path.join("Generic (USA)", "game.iso"),
            os.path.join("Many (USA)", "Many (USA).bin"), os.path.join("Many (USA)", "Many (USA).cue"),
        ]))

    def test_folders_for_every_archive(self):
        self.assertEqual(self.extract("f"), sorted([
            os.path.join("Single (USA)", "Single (USA).nes"), os.path.join("Generic (USA)", "game.iso"),
            os.path.join("Many (USA)", "Many (USA).bin"), os.path.join("Many (USA)", "Many (USA).cue"),
        ]))

    def test_plain_extraction(self):
        self.assertEqual(self.extract("p"), sorted(["Single (USA).nes", "game.iso", "Many (USA).bin", "Many (USA).cue"]))

    def test_dry_run_shows_the_folders_and_changes_nothing(self):
        self.assertEqual(self.extract("-n"), sorted(self.ARCHIVES))
        output = re.sub(r"\x1b\[\d+m", "", self.output)
        self.assertEqual(set(re.findall(r"Would unpack: (.*)", output)), {
            "Single (USA).zip to .", "Generic (USA).zip to Generic (USA)", "Many (USA).zip to Many (USA)",
        })


if __name__ == "__main__":
    unittest.main()
