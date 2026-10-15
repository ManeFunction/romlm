import os
import shutil
from dataclasses import dataclass
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

def plan_operations(files_list, target_folder_for, is_unpacking_enabled, is_packing_enabled, packing_format) -> list:
    """
    Decides what to do with every file, without touching the disk:
      - archives are unpacked with `is_unpacking_enabled`,
      - other files (but [BIOS]) are packed with `is_packing_enabled`,
      - the rest is moved into its target folder, unless it is already there.
    `target_folder_for` tells where a file belongs.
    """
    operations = []
    for file_name in files_list:
        target_folder = target_folder_for(file_name)
        if is_unpacking_enabled and archives.is_archive(file_name):
            operations.append(Operation(Kind.UNPACK, file_name, target_folder))
        elif is_packing_enabled and not archives.is_archive(file_name) and not Release.parse(file_name).is_bios:
            operations.append(Operation(Kind.PACK, file_name, target_folder, packing_format))
        elif os.path.normpath(os.path.dirname(file_name) or ".") != os.path.normpath(target_folder):
            operations.append(Operation(Kind.MOVE, file_name, target_folder))
    return operations

def execute(operation) -> tuple[str, str, str]:
    """Carries out the operation. Returns the file name, a log line and an error message."""
    try:
        if operation.target_folder:
            os.makedirs(operation.target_folder, exist_ok=True)
        target = f"{Fore.BLUE}{operation.target_folder}{Style.RESET_ALL}"
        if operation.kind == Kind.UNPACK:
            archives.unpack(operation.source, operation.target_folder)
            result_log = f" >> Unpacked to: {target}"
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
        return f" >> Would unpack: {Fore.GREEN}{operation.source}{Style.RESET_ALL} to {Fore.BLUE}{target}{Style.RESET_ALL}"
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
