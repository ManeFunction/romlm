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
from archives import ExtractMode
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

    def test_archive_extensions_are_case_insensitive(self):
        for name in ("A.ZIP", "B.7Z", "C.Zip"):
            self.assertTrue(archives.is_archive(name), name)
        self.assertEqual([op.kind for op in plan(["A.ZIP", "B.7Z"], lambda f: "out", unpack=True)],
                         [Kind.UNPACK, Kind.UNPACK])
        self.assertEqual([op.kind for op in plan(["A.ZIP", "B.7Z"], lambda f: "out", pack=True)],
                         [Kind.MOVE, Kind.MOVE])

    def test_files_are_packed_but_archives_and_bios_are_not(self):
        operations_list = plan(["A.nes", "B.zip", "!!BIOS/[BIOS] Sega CD (USA).bin"], lambda f: "out", pack=True)
        self.assertEqual(operations_list, [
            Operation(Kind.PACK, "A.nes", "out", "zip"),
            Operation(Kind.MOVE, "B.zip", "out"),
            Operation(Kind.MOVE, "!!BIOS/[BIOS] Sega CD (USA).bin", "out"),
        ])

    def test_packing_format_is_kept(self):
        self.assertEqual(plan(["A.nes"], pack=True, fmt="7z")[0].packing_format, "7z")

    def test_extract_mode_is_kept(self):
        self.assertEqual(plan(["A.zip"], unpack=True)[0].extract_mode, ExtractMode.PLAIN)
        operations_list = operations.plan_operations(["A.zip"], lambda f: "", True, False, "7z", ExtractMode.AUTO)
        self.assertEqual(operations_list, [Operation(Kind.UNPACK, "A.zip", "", extract_mode=ExtractMode.AUTO)])


class ResolveExtractionFoldersTest(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)

    def archive(self, name, *entries):
        path = os.path.join(self.folder.name, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with zipfile.ZipFile(path, "w") as z:
            for entry in entries:
                z.writestr(entry, "data")
        return path

    def resolve(self, *archives_list, mode=ExtractMode.AUTO):
        ops = [Operation(Kind.UNPACK, path, os.path.dirname(path), extract_mode=mode) for path in archives_list]
        return {os.path.relpath(op.source, self.folder.name): os.path.relpath(op.target_folder, self.folder.name)
                for op in operations.resolve_extraction_folders(ops)}

    def test_archives_with_the_same_file_get_own_folders(self):
        self.assertEqual(self.resolve(self.archive("Game (USA).zip", "game (usa).nes"),
                                      self.archive("Game (USA) (Rev 1).zip", "Game (USA).nes"),
                                      self.archive("Other (USA).zip", "Other (USA).nes")), {
            "Game (USA).zip": "Game (USA)", "Game (USA) (Rev 1).zip": "Game (USA) (Rev 1)", "Other (USA).zip": ".",
        })

    def test_same_files_in_different_folders_do_not_collide(self):
        self.assertEqual(self.resolve(self.archive(os.path.join("A", "Game (USA).zip"), "Game (USA).nes"),
                                      self.archive(os.path.join("B", "Game (USA).zip"), "Game (USA).nes")),
                         {os.path.join("A", "Game (USA).zip"): "A", os.path.join("B", "Game (USA).zip"): "B"})

    def test_archive_does_not_overwrite_a_file_on_disk(self):
        with open(os.path.join(self.folder.name, "Game (USA).nes"), "w") as f:
            f.write("old")
        self.assertEqual(self.resolve(self.archive("Game (USA) (Rev 1).zip", "Game (USA).nes"),
                                      self.archive("Other (USA).zip", "Other (USA).nes")),
                         {"Game (USA) (Rev 1).zip": "Game (USA) (Rev 1)", "Other (USA).zip": "."})

    def test_archive_does_not_overwrite_a_file_moved_in_by_the_run(self):
        archive = self.archive("Game (USA) (Rev 1).zip", "Game (USA).nes")
        ops = [Operation(Kind.MOVE, os.path.join("Sub", "Game (USA).nes"), self.folder.name),
               Operation(Kind.UNPACK, archive, self.folder.name, extract_mode=ExtractMode.AUTO)]
        self.assertEqual(operations.resolve_extraction_folders(ops)[1].target_folder,
                         os.path.join(self.folder.name, "Game (USA) (Rev 1)"))

    def test_archives_of_one_name_and_the_same_files_get_folders_with_the_format(self):
        for mode in (ExtractMode.AUTO, ExtractMode.FOLDERS):
            with self.subTest(mode=mode):
                self.assertEqual(self.resolve(self.archive("Game (USA).zip", "Game (USA).nes"),
                                              self.archive("Game (USA).7z", "Game (USA).nes"), mode=mode),
                                 {"Game (USA).zip": "Game (USA).zip", "Game (USA).7z": "Game (USA).7z"})

    def test_archives_of_one_name_with_different_files_share_the_folder(self):
        self.assertEqual(self.resolve(self.archive("Game (USA).zip", "game.iso"),
                                      self.archive("Game (USA).7z", "Game (USA).cue", "Game (USA).bin")),
                         {"Game (USA).zip": "Game (USA)", "Game (USA).7z": "Game (USA)"})

    def test_own_folder_already_holding_the_files_is_not_overwritten(self):
        self.archive(os.path.join("Game (USA)", "keep.zip"))
        os.rename(os.path.join(self.folder.name, "Game (USA)", "keep.zip"),
                  os.path.join(self.folder.name, "Game (USA)", "game.iso"))
        self.assertEqual(self.resolve(self.archive("Game (USA).zip", "game.iso")), {"Game (USA).zip": "Game (USA).zip"})

    def test_files_in_the_same_inner_folder_collide(self):
        self.assertEqual(self.resolve(self.archive("A (USA).zip", "Game/track01.bin"),
                                      self.archive("B (USA).zip", "Game/track01.bin"),
                                      self.archive("C (USA).zip", "Other/track01.bin")),
                         {"A (USA).zip": "A (USA)", "B (USA).zip": "B (USA)", "C (USA).zip": "."})

    def test_system_junk_does_not_collide(self):
        self.assertEqual(self.resolve(self.archive("A (USA).zip", "A (USA).nes", ".DS_Store"),
                                      self.archive("B (USA).zip", "B (USA).nes", ".DS_Store")),
                         {"A (USA).zip": ".", "B (USA).zip": "."})

    def test_resolved_operations_do_not_read_the_archive_again(self):
        op = operations.resolve_extraction_folders([Operation(
            Kind.UNPACK, self.archive("G (USA).zip", "game.iso"), self.folder.name, extract_mode=ExtractMode.AUTO)])[0]
        self.assertEqual(op.extract_mode, ExtractMode.PLAIN)
        self.assertEqual(op.target_folder, os.path.join(self.folder.name, "G (USA)"))

    def test_only_auto_mode_looks_for_collisions(self):
        a = self.archive("A (USA).zip", "Game.nes")
        b = self.archive("B (USA).zip", "Game.nes")
        self.assertEqual(self.resolve(a, b, mode=ExtractMode.FOLDERS), {"A (USA).zip": "A (USA)", "B (USA).zip": "B (USA)"})
        self.assertEqual(self.resolve(a, b, mode=ExtractMode.PLAIN), {"A (USA).zip": ".", "B (USA).zip": "."})

    def test_unreadable_archive_is_left_to_fail_on_unpacking(self):
        bad = os.path.join(self.folder.name, "Bad (USA).zip")
        with open(bad, "w") as f:
            f.write("not a zip")
        op = Operation(Kind.UNPACK, bad, self.folder.name, extract_mode=ExtractMode.AUTO)
        self.assertEqual(operations.resolve_extraction_folders([op]), [op])

    def test_other_operations_are_kept(self):
        ops = [Operation(Kind.MOVE, "A.nes", "A"), Operation(Kind.PACK, "B.nes", "B")]
        self.assertEqual(operations.resolve_extraction_folders(ops), ops)


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

    def test_unpacks_an_archive_with_an_upper_case_extension(self):
        archive = self.path("Up (USA).ZIP")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Up (USA).nes", "rom")
        _, _, error = operations.execute(Operation(Kind.UNPACK, archive, self.path("out")))
        self.assertIsNone(error)
        self.assertEqual(read(self.path("out", "Up (USA).nes")), "rom")

    def test_unpacks_into_own_folder_by_the_mode(self):
        archive = self.path("Game (USA).zip")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("Game (USA).cue", "cue")
            z.writestr("Game (USA).bin", "bin")
        _, log, error = operations.execute(Operation(Kind.UNPACK, archive, self.path("out"),
                                                     extract_mode=ExtractMode.AUTO))
        self.assertIsNone(error)
        self.assertIn(os.path.join("out", "Game (USA)"), log)
        self.assertEqual(sorted(os.listdir(self.path("out", "Game (USA)"))), ["Game (USA).bin", "Game (USA).cue"])

    def test_unpacks_into_a_folder_named_as_the_archive(self):
        archive = self.path("Game (USA).zip")
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("game.iso", "iso")
        _, _, error = operations.execute(Operation(Kind.UNPACK, archive, archive))
        self.assertIsNone(error)
        self.assertEqual(os.listdir(self.root), ["Game (USA).zip"])
        self.assertEqual(read(self.path("Game (USA).zip", "game.iso")), "iso")

    def test_bad_archive_is_kept_when_unpacking_into_a_folder_named_as_it(self):
        bad = self.touch("Bad (USA).zip", content="not a zip")
        _, _, error = operations.execute(Operation(Kind.UNPACK, bad, bad))
        self.assertIn("BadZipFile", error)
        self.assertEqual(os.listdir(self.root), ["Bad (USA).zip"])
        self.assertEqual(read(bad), "not a zip")

    def test_bad_archive_is_reported_and_kept(self):
        bad = self.touch("Bad (USA).zip", content="not a zip")
        name, log, error = operations.execute(Operation(Kind.UNPACK, bad, self.path("out")))
        self.assertEqual(name, bad)
        self.assertIsNone(log)
        self.assertIn("BadZipFile", error)
        self.assertTrue(os.path.exists(bad))

    def test_bad_archive_is_reported_and_kept_in_auto_mode(self):
        bad = self.touch("Bad (USA).zip", content="not a zip")
        _, _, error = operations.execute(Operation(Kind.UNPACK, bad, self.path("out"), extract_mode=ExtractMode.AUTO))
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


class DryRunTest(unittest.TestCase):
    def test_nothing_is_touched_and_every_operation_is_described(self):
        with tempfile.TemporaryDirectory() as root:
            source = os.path.join(root, "Game (USA).nes")
            open(source, "w").close()
            ops = [Operation(Kind.MOVE, source, os.path.join(root, "G")),
                   Operation(Kind.PACK, source, os.path.join(root, "G"), "zip"),
                   Operation(Kind.UNPACK, os.path.join(root, "A.zip"), "")]
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                failures = operations.run_operations(ops, True, is_dry_run=True)
            self.assertEqual(failures, [])
            self.assertEqual(os.listdir(root), ["Game (USA).nes"])
            lines = output.getvalue().splitlines()
            self.assertEqual(len(lines), 3)
            for line, word in zip(lines, ("move", "pack", "unpack")):
                self.assertIn(f"Would {word}", line)

    def test_shows_the_own_folder_of_an_archive(self):
        with tempfile.TemporaryDirectory() as root:
            archive = os.path.join(root, "Game (USA).zip")
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("game.iso", "iso")
            line = operations.describe(Operation(Kind.UNPACK, archive, root, extract_mode=ExtractMode.AUTO))
            self.assertIn(os.path.join(root, "Game (USA)"), line)
            self.assertTrue(os.path.exists(archive))

    def test_unreadable_archive_is_noted(self):
        with tempfile.TemporaryDirectory() as root:
            bad = os.path.join(root, "Bad (USA).zip")
            with open(bad, "w") as f:
                f.write("not a zip")
            line = operations.describe(Operation(Kind.UNPACK, bad, root, extract_mode=ExtractMode.FOLDERS))
            self.assertIn("Would unpack", line)
            self.assertIn("can't read the archive", line)


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
