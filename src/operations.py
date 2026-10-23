import os
import shutil
from collections import defaultdict
from dataclasses import dataclass, replace
from enum import Enum
from multiprocessing import Pool
from colorama import Fore, Style
from tqdm import tqdm

import archives
from tags import Release

class Kind(Enum):
    MOVE = 1
    PACK = 2
    UNPACK = 3

@dataclass(frozen=True)
class Operation:
    """One thing to do with one file."""
    kind: Kind
    source: str
    target_folder: str
    packing_format: str = "7z"
    extract_mode: archives.ExtractMode = archives.ExtractMode.PLAIN

def plan_operations(files_list, target_folder_for, is_unpacking_enabled, is_packing_enabled, packing_format,
                    extract_mode=archives.ExtractMode.PLAIN) -> list:
    """
    Decides what to do with every file, without touching the disk:
      - archives are unpacked with `is_unpacking_enabled`, the `extract_mode` decides on their own folders later,
      - other files (but [BIOS]) are packed with `is_packing_enabled`,
      - the rest is moved into its target folder, unless it is already there.
    `target_folder_for` tells where a file belongs.
    """
    operations = []
    for file_name in files_list:
        target_folder = target_folder_for(file_name)
        if is_unpacking_enabled and archives.is_archive(file_name):
            operations.append(Operation(Kind.UNPACK, file_name, target_folder, extract_mode=extract_mode))
        elif is_packing_enabled and not archives.is_archive(file_name) and not Release.parse(file_name).is_bios:
            operations.append(Operation(Kind.PACK, file_name, target_folder, packing_format))
        elif os.path.normpath(os.path.dirname(file_name) or ".") != os.path.normpath(target_folder):
            operations.append(Operation(Kind.MOVE, file_name, target_folder))
    return operations

def read_files(operation):
    """The files inside the operation's archive, or None if it can't be read."""
    try:
        return archives.list_files(operation.source)
    except Exception:
        return None

def _path_key(path) -> str:
    """The same key for the paths of one file (case-insensitive, as file systems often are)."""
    return os.path.normpath(path).lower()

def resolve_extraction_folders(operations) -> list:
    """
    Reads the archives that may need their own folders, and decides where each one goes (see archives.ExtractMode).
    An archive whose files would overwrite another archive's ones, or the files on disk (or moved there by this run),
    goes to its next folder of archives.extraction_folders, until nothing is overwritten or no folders are left.
    Colliding archives move on together. The archives that can't be read are left as they are, to fail on unpacking.
    """
    to_read = [op for op in operations if op.kind == Kind.UNPACK and op.extract_mode != archives.ExtractMode.PLAIN]
    if not to_read:
        return operations
    with Pool(processes=os.cpu_count()) as pool:
        listings = {op: files for op, files in zip(to_read, pool.map(read_files, to_read)) if files is not None}

    choices = {op: archives.extraction_folders(op.source, op.target_folder, op.extract_mode, files)
               for op, files in listings.items()}
    choice = dict.fromkeys(listings, 0)
    moved_in = {_path_key(os.path.join(op.target_folder, os.path.basename(op.source)))
                for op in operations if op.kind == Kind.MOVE}

    def is_taken(path):
        return _path_key(path) in moved_in or os.path.exists(path)

    while True:
        owners = defaultdict(set)
        for op, files in listings.items():
            for path in files:
                owners[_path_key(os.path.join(choices[op][choice[op]], path))].add(op)
        colliding = {op for ops in owners.values() if len(ops) > 1 for op in ops}
        colliding |= {op for op, files in listings.items() if op not in colliding
                      and any(is_taken(os.path.join(choices[op][choice[op]], path)) for path in files)}
        moving_on = [op for op in colliding if choice[op] + 1 < len(choices[op])]
        if not moving_on:
            break
        for op in moving_on:
            choice[op] += 1

    return [replace(op, target_folder=choices[op][choice[op]], extract_mode=archives.ExtractMode.PLAIN)
            if op in listings else op for op in operations]

def execute(operation) -> tuple[str, str, str]:
    """Carries out the operation. Returns the file name, a log line and an error message."""
    try:
        # Unpacking makes its folder itself, as the folder may take the archive's place
        if operation.target_folder and operation.kind != Kind.UNPACK:
            os.makedirs(operation.target_folder, exist_ok=True)
        target = f"{Fore.BLUE}{operation.target_folder}{Style.RESET_ALL}"
        if operation.kind == Kind.UNPACK:
            folder = archives.extraction_folder(operation.source, operation.target_folder, operation.extract_mode)
            archives.unpack(operation.source, folder)
            result_log = f" >> Unpacked to: {Fore.BLUE}{folder or '.'}{Style.RESET_ALL}"
        elif operation.kind == Kind.PACK:
            archive_file = archives.pack(operation.source, operation.target_folder, operation.packing_format)
            result_log = f" >> Packed to: {Fore.BLUE}{archive_file}{Style.RESET_ALL}"
        else:
            shutil.move(operation.source, os.path.join(operation.target_folder, os.path.basename(operation.source)))
            result_log = f" >> Moved to: {target}"
    except Exception as error:
        return operation.source, None, archives.describe_error(error)
    return operation.source, result_log, None

def describe(operation) -> str:
    """What the operation does, for the dry run."""
    target = operation.target_folder or "."
    if operation.kind == Kind.UNPACK:
        # Reading the archive to find its folder changes nothing, so the dry run shows the real destination
        try:
            target = archives.extraction_folder(operation.source, operation.target_folder, operation.extract_mode) or "."
            note = ""
        except Exception as error:
            note = f" ({Fore.RED}can't read the archive{Style.RESET_ALL}: {archives.describe_error(error)})"
        return (f" >> Would unpack: {Fore.GREEN}{operation.source}{Style.RESET_ALL} "
                f"to {Fore.BLUE}{target}{Style.RESET_ALL}{note}")
    if operation.kind == Kind.PACK:
        return (f" >> Would pack: {Fore.GREEN}{operation.source}{Style.RESET_ALL} to {operation.packing_format} "
                f"in {Fore.BLUE}{target}{Style.RESET_ALL}")
    return f" >> Would move: {Fore.GREEN}{operation.source}{Style.RESET_ALL} to {Fore.BLUE}{target}{Style.RESET_ALL}"

def run_operations(operations, is_log_enabled, is_dry_run=False) -> list:
    """
    Carries out the operations and returns the failed ones as (file name, error message) pairs.
    A dry run only prints what would be done.
    """
    if is_dry_run:
        for operation in operations:
            print(describe(operation))
        return []

    failures = []

    # Archives take time, so they are processed in parallel. Moves are quick and go one by one.
    if any(op.kind != Kind.MOVE for op in operations):
        with Pool(processes=os.cpu_count()) as pool:
            results = pool.imap_unordered(execute, operations)
            if is_log_enabled:
                for i, (f_name, result_log, error) in enumerate(results, start=1):
                    if error is not None:
                        failures.append((f_name, error))
                        print(f"({i}/{len(operations)}) Failed: {Fore.RED}{f_name}{Style.RESET_ALL} ({error})")
                    else:
                        print(f"({i}/{len(operations)}) Processed: {Fore.GREEN}{f_name}{Style.RESET_ALL}")
                        if result_log is not None:
                            print(result_log)
            else:
                for f_name, _, error in tqdm(results, total=len(operations), desc="Processing"):
                    if error is not None:
                        failures.append((f_name, error))
    else:
        for f_name, result_log, error in map(execute, tqdm(operations, desc="Processing", disable=is_log_enabled)):
            if error is not None:
                failures.append((f_name, error))
                if is_log_enabled:
                    print(f"Failed: {Fore.RED}{f_name}{Style.RESET_ALL} ({error})")
            elif is_log_enabled:
                print(result_log)
    return failures
