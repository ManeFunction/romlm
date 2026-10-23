# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]
### Added
- Added extraction modes to `-x`/`--extract`: `-x f` extracts every archive into its own folder named after it, and
  `-x p` extracts everything next to the archives.
- `-p`/`--pack` packs the folders of disc-based games as a whole, into a single archive named after the folder, with
  just the files of the folder inside: the opposite of `-x`. A folder is taken for a game when it has a disc sheet
  (`.cue`, `.gdi`, `.ccd`, `.mds`, `.toc` or `.m3u`) or a file with a generic name, and only the files of one game, or
  when it's an extracted disc (PS1/PS2, PS3, PSP, Xbox, Xbox 360).

### Changed
- `-x` without a mode now gives an archive its own folder when it holds more than one file, a file with a generic
  name like `game.iso`, `Disc 1.cue` or `track01.bin`, or a file that would overwrite a file already in the folder or
  one from another archive, instead of always extracting next to the archive. Use `-x p` for the old behavior.
  `--dry-run` reads the archives to show where they would be extracted.
- With `-x` and `-x f`, archives of the same name in different formats with the same files inside get folders with
  the format in the name, like `Game (USA).zip/` and `Game (USA).7z/`.
- The cleanup after processing now also removes `__MACOSX` folders, left by zips made on a Mac.
- Python 3.10+ is now required, as Python 3.9 has reached its end of life.

### Fixed
- Fixed `-r` treating the names that differ only in case (like `Pac-Man (USA)` and `PAC-MAN (Japan)`) as different
  games, including the discs of one multi-disc set.

## [1.2.0] - 2026-10-16
### Added
- Added `-n`/`--dry-run` to preview what would be done without changing anything: duplicates are decided but not
  removed, and the planned moves, packs and unpacks are printed with a summary. Implies `--log`, and doesn't ask
  about ties unless `-r ask` is given.

### Changed
- The command line is now parsed with `argparse`. Usage errors exit with code 2 instead of 1, unknown arguments and
  unknown `--sort` letters are rejected instead of ignored, and values starting with `-` have to be passed as
  `--input=-name`.
- `-r one` now keeps the first of the best files by name instead of a random one, so repeated runs give the same result.
- Multi-disc games are kept from a single edition: the best edition that has all the discs wins as a whole (scored by
  its worst disc), instead of mixing the best disc of each region. Without a complete edition, each disc keeps its
  own best release as before.
- Python 3.9+ and setuptools 77+ are now required (the code already needed them; older versions installed a broken
  package).
- The package version is now defined only in `romlm.py`, so the wheel metadata and `romlm -v` can't disagree.
- Internal refactoring: file names are parsed once into a `Release`, duplicates and file operations are planned
  before being executed, and archive handling moved into its own module. Files that need no operation are no longer
  counted in the progress totals.

### Fixed
- Fixed `[BIOS]` files being treated as duplicates of each other, which removed all but one of them.
- Fixed `[BIOS]` files that were already sorted being packed.
- Fixed `(v1.1)`-style version tags counting as unknown tags, which made an unversioned ROM win over the newer one.
- Fixed a crash on empty or bare-`v` version tags.
- Fixed unversioned Homebrew ROMs outranking any real version on a tie.
- Fixed `--unlicensed h` and `p` not limiting the separation, and a bare `-u` doing nothing. Unknown values are
  now rejected.
- Fixed folders with a dot in the name (e.g. `Vol. 1`) being moved as files and crashing the run.
- Fixed `--sort` combined with `--pack`/`--extract` leaving the files that needed no packing or extracting in place.
- Fixed a failed archive or move aborting the whole run with a traceback. Failures are now listed at the end (with
  7-Zip's own message), processing continues, the exit code is 1, and a half-written archive is removed.
- Fixed upper-case `.ZIP` and `.7Z` extensions not being recognized as archives.

## [1.1.0] - 2026-09-22
### Changed
- Replaced the bundled `py7zr` library with shelling out to a system 7-Zip CLI (`7zz`/`7z`/`7za`) for `.7z`
  archive handling. Behavior is unchanged, but `.7z` support now requires 7-Zip to be installed separately
  (`brew install sevenzip` on macOS/Linux, the [official installer](https://www.7-zip.org/) on Windows) --
  this removed 9 transitive C-extension dependencies that made packaging (especially for Homebrew) fragile.

## [1.0.3] - 2025-08-11
### Fixed
- Fixed an issue when discs marked with a `track` tag was removed as duplicates.

## [1.0.2] - 2025-01-05
### Added
- Added [`pip` installation support](https://pypi.org/project/romlm/).

### Changed
- Changed local `brew` installation from the global python environment to venv.

## [1.0.1] - 2025-01-05
### Added
- Added `brew` installation support via the custom [mane tap](https://github.com/ManeFunction/homebrew-tap).

## [1.0.0] - 2025-01-04
### Added
- Initial release of the tool.
