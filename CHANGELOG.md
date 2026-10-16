# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
