import contextlib
import io
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import archives
import operations
from operations import Kind, Operation


def read(path):
    with open(path) as f:
        return f.read()


def plan(files, target_folder_for=lambda f: os.path.dirname(f), unpack=False, pack=False, fmt="zip"):
    return operations.plan_operations(files, target_folder_for, unpack, pack, fmt)


class PlanOperationsTest(unittest.TestCase):
    def test_nothing_to_do_when_every_file_is_in_place(self):
        self.assertEqual(plan(["Game (USA).nes", "Sub/Game (USA).nes"]), [])

    def test_files_are_moved_to_their_folder(self):
        self.assertEqual(plan(["Game (USA).nes"], lambda f: "G"), [Operation(Kind.MOVE, "Game (USA).nes", "G")])

    def test_file_that_is_already_in_its_folder_is_left_alone(self):
        folder_of = lambda f: os.path.basename(f)[0]
        self.assertEqual(plan(["G/Game (USA).nes", "Zelda (USA).nes"], folder_of),
                         [Operation(Kind.MOVE, "Zelda (USA).nes", "Z")])

    def test_archives_are_unpacked_and_the_rest_is_moved(self):
        operations_list = plan(["A.zip", "B.7z", "C.nes"], lambda f: "out", unpack=True)
        self.assertEqual([op.kind for op in operations_list], [Kind.UNPACK, Kind.UNPACK, Kind.MOVE])

    def test_files_are_packed_but_archives_and_bios_are_not(self):
        operations_list = plan(["A.nes", "B.zip", "!!BIOS/[BIOS] Sega CD (USA).bin"], lambda f: "out", pack=True)
        self.assertEqual(operations_list, [
            Operation(Kind.PACK, "A.nes", "out", "zip"),
            Operation(Kind.MOVE, "B.zip", "out"),
            Operation(Kind.MOVE, "!!BIOS/[BIOS] Sega CD (USA).bin", "out"),
        ])

    def test_packing_format_is_kept(self):
        self.assertEqual(plan(["A.nes"], pack=True, fmt="7z")[0].packing_format, "7z")


class ExecuteTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = self.folder.name

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def touch(self, *parts, content=""):
        os.makedirs(os.path.dirname(self.path(*parts)), exist_ok=True)
        with open(self.path(*parts), "w") as f:
            f.write(content)
        return self.path(*parts)

    def test_move_creates_the_folder(self):
        source = self.touch("Game (USA).nes", content="rom")
        name, log, error = operations.execute(Operation(Kind.MOVE, source, self.path("G")))
        self.assertIsNone(error)
        self.assertEqual(name, source)
        self.assertFalse(os.path.exists(source))
        self.assertEqual(read(self.path("G", "Game (USA).nes")), "rom")

    def test_pack_and_unpack_zip(self):
        source = self.touch("Game (USA).nes", content="rom")
        _, _, error = operations.execute(Operation(Kind.PACK, source, self.path("out"), "zip"))
        self.assertIsNone(error)
        archive = self.path("out", "Game (USA).nes.zip")
        self.assertFalse(os.path.exists(source))
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(z.namelist(), ["Game (USA).nes"])

        _, _, error = operations.execute(Operation(Kind.UNPACK, archive, self.path("back")))
        self.assertIsNone(error)
        self.assertFalse(os.path.exists(archive))
        self.assertEqual(read(self.path("back", "Game (USA).nes")), "rom")

    def test_bad_archive_is_reported_and_kept(self):
        bad = self.touch("Bad (USA).zip", content="not a zip")
        name, log, error = operations.execute(Operation(Kind.UNPACK, bad, self.path("out")))
        self.assertEqual(name, bad)
        self.assertIsNone(log)
        self.assertIn("BadZipFile", error)
        self.assertTrue(os.path.exists(bad))

    def test_run_continues_after_a_failure(self):
        bad = self.touch("Bad (USA).zip", content="not a zip")
        rom = self.touch("Game (USA).nes")
        ops = [Operation(Kind.UNPACK, bad, self.path("out")), Operation(Kind.MOVE, rom, self.path("G"))]
        with contextlib.redirect_stdout(io.StringIO()):
            failures = operations.run_operations(ops, True)
        self.assertEqual([f[0] for f in failures], [bad])
        self.assertTrue(os.path.exists(self.path("G", "Game (USA).nes")))


@unittest.skipUnless(archives.find_seven_zip_binary(), "7-Zip is not installed")
class SevenZipTest(unittest.TestCase):
    def test_pack_and_unpack_7z(self):
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "Game (USA).nes")
            with open(source, "w") as f:
                f.write("rom")
            archive = archives.pack(source, os.path.join(root), "7z")
            self.assertEqual(os.path.basename(archive), "Game (USA).nes.7z")
            self.assertFalse(os.path.exists(source))
            archives.unpack(archive, os.path.join(root, "back"))
            self.assertEqual(read(os.path.join(root, "back", "Game (USA).nes")), "rom")


if __name__ == "__main__":
    unittest.main()
