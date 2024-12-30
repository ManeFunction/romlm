import sys
import os
import re
import shutil
import glob
from enum import Enum, Flag, auto
import py7zr
import zipfile
import colorama
from colorama import Fore, Style
from tqdm import tqdm
from multiprocessing import freeze_support

class Action(Enum):
	NOT_DEFINED = 0
	ASK = 1
	KEEP_ALL = 2
	KEEP_ONE = 3
	
class CategoryOption(Flag):
	HOMEBREW = auto()
	PIRATES = auto()
	SUBFOLDERS = auto()

def create_if_not_exist(folder):
	if not os.path.exists(folder):
		os.makedirs(folder)
		
def get_lettered_folder_name(filename) -> str:
	folder_name = filename[0].upper() if filename else ''
	if folder_name == "[":
		folder_name = "!!BIOS"
	elif not folder_name.isalpha():
		folder_name = "1-9"
	return folder_name

def try_add_subfolder(is_sort_subfolders, folder_name, filename) -> str:
	return (folder_name + "/" + get_lettered_folder_name(filename)) if is_sort_subfolders else folder_name

def get_tags_from_filename(filename: str) -> list[str]:
	name_no_ext = os.path.splitext(filename)[0]
	groups = re.findall(r'\((.*?)\)', name_no_ext)
	all_tags = []
	for g in groups:
		split_tags = [t.strip() for t in g.split(',')]
		all_tags.extend(split_tags)
	return [tag.lower() for tag in all_tags]

def is_homebrew(file_tags) -> bool:
	return "homebrew" in file_tags or "aftermarket" in file_tags

def is_pirate(file_tags) -> bool:
	return "pirate" in file_tags or "unl" in file_tags

def get_new_folder(filename, separation_options, sorting_options, subfolders, excludes) -> str:
	file_tags = get_tags_from_filename(filename)
	excludes = {exclude.lower() for exclude in excludes} if excludes is not None else None
	
	# Check for 'homebrew' or 'aftermarket' tags
	if separation_options & CategoryOption.HOMEBREW and is_homebrew(file_tags):
		folder_name = try_add_subfolder(sorting_options & CategoryOption.HOMEBREW, "!Homebrew", filename)
		
	# Check for 'pirate' or 'unl' tags
	elif separation_options & CategoryOption.PIRATES and is_pirate(file_tags):
		folder_name = try_add_subfolder(sorting_options & CategoryOption.PIRATES, "!Pirates", filename)

	# Check for any user-defined 'subfolders' value matches any tag.
	elif subfolders is not None:
		found_subfolder = ""
		for subfolder in subfolders:
			if subfolder.lower() in file_tags and (excludes is None or not bool(excludes.intersection(file_tags))):
				found_subfolder = "!" + subfolder
				break
		folder_name = try_add_subfolder(sorting_options & CategoryOption.SUBFOLDERS, found_subfolder, filename) \
			if found_subfolder != "" else get_lettered_folder_name(filename)

	# Default to alphabetical folder
	else:
		folder_name = get_lettered_folder_name(filename)

	create_if_not_exist(folder_name)
	return folder_name

def remove_meta_files(path, is_log_enabled):
	for dirpath, dirnames, filenames in os.walk(path):
		for f in filenames:
			if f.lower() in ("desktop.ini", "thumbs.db", ".ds_store"):
				file_path = os.path.join(dirpath, f)
				os.remove(file_path)
				if is_log_enabled:
					print(f"Removed meta file: {Fore.RED}{file_path}{Style.RESET_ALL}")

def remove_empty_subfolders(path, is_log_enabled):
	for dirpath, dirnames, filenames in os.walk(path, topdown=False):
		if not dirnames and not filenames:
			if dirpath != path:
				os.rmdir(dirpath)
				if is_log_enabled:
					print(f"Removed empty folder: {Fore.RED}{dirpath}{Style.RESET_ALL}")
				# Kinda cludgy, but keep removing empty parent folders until we hit the root, to clear empty trees
				parent_dir = os.path.dirname(dirpath)
				while parent_dir != path and not os.listdir(parent_dir):
					os.rmdir(parent_dir)
					if is_log_enabled:
						print(f"Removed empty folder: {Fore.RED}{parent_dir}{Style.RESET_ALL}")
					parent_dir = os.path.dirname(parent_dir)

def get_base_name(filename: str) -> str:
	name_no_ext = os.path.splitext(filename)[0]
	idx = name_no_ext.find('(')
	if idx != -1:
		base = name_no_ext[:idx].strip()
	else:
		base = name_no_ext.strip()
	return base
		
def clean_duplicates(file_list, action, is_log_enabled):
	"""
    For each distinct base name (game):
      1) Partition into normal vs beta/proto.
         - If normal exists => remove all beta/proto.
      2) Among normal => pick exactly one best-scored normal file:
         - Region coverage (more is better)
         - Fewer non-region tags
         - Better (lower) region priority index
         - Higher revision
      3) If no normal => pick exactly one best-scored beta/proto:
         - Region coverage (more is better)
         - No date is better than having a date
         - Higher numeric suffix is better
         - Fewer non-region tags
      4) Remove the rest. Never remove all for a given game; if end up with none, keep them all.
    """

	top_region_priority = "world"
	region_priority = ["usa", "europe"]
	asian_regions = ["japan", "asia", "china", "korea"]

	# Is ROM a part of multi-disc set?
	def get_disc_number(tags_list) -> int:
		"""
		Returns '-1' if the ROM is not a part of a multi-disc set, or disc number otherwise.
		"""
		for t in tags_list:
			m = re.match(r"(disc|disk)\s*(\d+)", t)
			if m:
				return int(m.group(2))
		return -1

	# Helper: parse date like (1993-07-09)
	def parse_date_yyyy_mm_dd(tag: str) -> bool:
		"""
        Return True if tag looks like YYYY-MM-DD, else False.
        We won't parse the integer, we just treat "has date" as a boolean.
        """
		return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", tag))

	# Identify if file is Beta/Proto/Sample
	def is_beta_file(fpath):
		tags_list = get_tags_from_filename(os.path.basename(fpath))
		for t in tags_list:
			# If it starts with "beta", "proto", or "sample", we treat it as Beta/Proto
			if (t.startswith("beta") 
					or t.startswith("proto") 
					or t.startswith("sample")
					or t.startswith("demo")):
				return True
		return False

	# Region coverage + min region index
	def get_region_coverage_and_min_index(tags_list):
		"""
        Returns (coverage, min_index) where:
          coverage = number of recognized region tags
          min_index = the lowest index among recognized tags (or len(region_priority) if none)
        Example: if tags_list has ["usa", "europe"], coverage=2, min_index=1 ("usa")
        """
		# Check if it's a top region priority
		for t in tags_list:
			if t == top_region_priority:
				return len(region_priority), 0
		# Check if it's a recognized prioritized region
		recognized = [r for r in tags_list if r in region_priority]
		coverage = len(recognized)
		if coverage == 0:
			return 0, len(region_priority)
		# find the lowest region index among them
		min_i = min(region_priority.index(r) for r in recognized)
		return coverage, min_i
	
	# Is ROM from an Asian region?
	def is_asian_region_and_not_en(tags_list):
		"""
		Returns True if the ROM is from an Asian region and not in English.
		"""
		is_asian = False
		is_en = False
		for t in tags_list:
			if t in asian_regions:
				is_asian = True
			elif t == "en":
				is_en = True
		return is_asian and not is_en

	# Count how many unknown tags ROM have (excluding rev, beta/proto, sample, known region)
	def count_unknown_tags(tags_list):
		count = 0
		for t in tags_list:
			# Skip known regions tags
			if t == top_region_priority:
				continue
			if t in region_priority:
				continue
			if t in asian_regions:
				continue
			# Revisions and versions tags
			if t.startswith("rev") or t.startswith("v") or re.match(r"^\d+(?:\.\d+){0,3}$", t):
				continue
			# Beta and other in-development tags
			if t.startswith("beta") or t.startswith("proto") or t.startswith("sample"):
				continue
			# Language tags
			if t in ["en", "fr", "de", "es", "it", "nl", "pt", "sv", "no", "da", "fi"]:
				continue
			# anything else is "extra"
			count += 1
		return count
	
	# Get version score for comparison
	def get_version_score(version_tuple) -> int:
		"""
		Convert a version tuple (major, minor, patch) into a single integer for comparison.
		Example: (1, 2, 3, 4) => 001002003004
		"""
		return int("".join(f"{v:03}" for v in version_tuple))
	
	# Get date score for comparison
	def get_date_score(date_str) -> int:
		"""
		Convert a date string (YYYY-MM-DD) into a single integer for comparison.
		Example: "1993-07-09" => 19930709
		"""
		return int(date_str.replace("-", ""))

	# Get video format score for comparison (NTSC > none > PAL)
	def get_video_format_score(tags_list) -> int:
		"""
		Convert a video format tag into a single integer for comparison.
		"""
		for t in tags_list:
			if t == "ntsc":
				return 2
			elif t == "pal":
				return 0
		return 1

	# Normal-file scoring: ( -region_coverage, min_region_index, non_region_tags, -video_format, -revision )
	def score_normal_file(fpath):
		tags_list = get_tags_from_filename(os.path.basename(fpath))
		coverage, min_idx = get_region_coverage_and_min_index(tags_list)
		video_format_score = get_video_format_score(tags_list)
			
		revision = (0,0,0,0)
		revision_found = False
		for t in tags_list:
			m = re.match(r"^(?:rev\s+)?v?(\d+(?:\.\d+){0,3})?$", t)
			if m:
				revision_found = True
				version_str = m.group(1)
				version = tuple(map(int, version_str.split('.')))
				version += (0,) * (4 - len(version))  # ensure 4-tuple
				if version > revision:
					revision = version
					
		non_region = count_unknown_tags(tags_list)
		
		# Set a slight tags penalty for Asian regions to prioritize english versions even it's new (from Virtual Consoles, etc.)
		if is_asian_region_and_not_en(tags_list):
			non_region += 2
			
		# For Homebrew, assume that no explicit revision version is 1.0 (initial release)
		# ...for retro ROMs, it's more likely "Rev 0" (initial release)
		# also compensate missed initial revision for Homebrew 
		if (is_homebrew(tags_list) or is_pirate(tags_list)) and not revision_found:
			revision = (1,0,0,0)
			non_region += 1

		revision_score = get_version_score(revision)
		
		return (
			non_region,
			-coverage,
			min_idx,
			-video_format_score,
			-revision_score
		)

	# Beta/Proto scoring: ( -latest_date, -region_coverage, -beta_number, non_region_tags )
	def score_beta_file(fpath):
		tags_list = get_tags_from_filename(os.path.basename(fpath))
		coverage, _ = get_region_coverage_and_min_index(tags_list)

		best_date_score = 0
		beta_number = (0,0,0,0)
		for t in tags_list:
			# check if it's a date tag
			if parse_date_yyyy_mm_dd(t):
				date_score = get_date_score(t)
				if date_score > best_date_score:
					best_date_score = date_score
			# check if it's a Beta/Proto tag with a numeric suffix
			m = re.match(r"^(?:(beta|proto|sample|demo)\s+)?v?(\d+(?:\.\d+){0,3})?$", t)
			if m:
				version_str = m.group(2)
				version = tuple(map(int, version_str.split('.')))
				version += (0,) * (4 - len(version))  # ensure 4-tuple
				if version > beta_number:
					beta_number = version

		non_region = count_unknown_tags(tags_list)
		version_score = get_version_score(beta_number)
		
		return (
			-best_date_score,
			-coverage,
			-version_score,
			non_region
		)

	# Print list of files in a color
	def print_files_list(files_list, color):
		for file_name in files_list:
			print(f" - {color}{os.path.basename(file_name)}{Style.RESET_ALL}")
			
	# Get a log iteration string formatted as "(N/M)"
	def n(index) -> str:
		return f"({index}/{len(groups_iter)}) "
	
	# Left only one file in the set
	def keep_one(files_set, selected) -> set:
		if is_log_enabled:
			print(f"{n(i)}Removing duplicate(s):")
		for file_name in files_set:
			if file_name != selected:
				if is_log_enabled:
					print(f"- {Fore.RED}{os.path.basename(file_name)}{Style.RESET_ALL}")
				os.remove(file_name)
		if is_log_enabled:
			print(f"| >> Keeping one: {Fore.GREEN}{os.path.basename(selected)}{Style.RESET_ALL}")
		return {selected}

	# Group files by base name
	file_list = list(file_list)
	by_basename = {}

	for f in file_list:
		fname = os.path.basename(f)
		base = get_base_name(fname)
		disc = get_disc_number(get_tags_from_filename(fname))
		if disc > -1:
			base += f" (Disc {disc})"
		by_basename.setdefault(base, []).append(f)

	print(
		">> Removing duplicates safely... \nTotal ROMs:",
		len(file_list),
		"\nActual games:",
		len(by_basename),
	)

	files_to_keep = set()

	# MAIN LOOP of removing duplicates
	if is_log_enabled:
		groups_iter = by_basename.items()
	else:
		groups_iter = tqdm(by_basename.items(), desc="Cleaning Duplicates", total=len(by_basename))

	i = 0
	for base, paths in groups_iter:
		i += 1
		
		# Only one file => trivially keep it
		if len(paths) == 1:
			files_to_keep.add(paths[0])
			if is_log_enabled:
				print(f"{n(i)}Single ROM: {Fore.GREEN}{os.path.basename(paths[0])}{Style.RESET_ALL}")
			continue

		# Partition into normal vs. beta/proto
		normal_files = []
		beta_proto_files = []
		for p in paths:
			if is_beta_file(p):
				beta_proto_files.append(p)
			else:
				normal_files.append(p)

		if normal_files:
			# Remove all Beta/Proto
			chosen_set = normal_files
			if is_log_enabled and beta_proto_files:
				print(f"{n(i)}Removing all Betas: ")
				print_files_list(beta_proto_files, Fore.RED)
				print(f" | >> Has {len(normal_files)} release(s):")
				print_files_list(normal_files, Fore.GREEN)
			for bp in beta_proto_files:
				os.remove(bp)
		else:
			# No normal => only Beta/Proto
			# Pick exactly one best-scored
			if len(beta_proto_files) == 1:
				files_to_keep.add(beta_proto_files[0])
				if is_log_enabled:
					print(f"{n(i)}Single Beta: {Fore.GREEN}{os.path.basename(beta_proto_files[0])}{Style.RESET_ALL}")
				continue

			best_bp = None
			best_score = None
			for bp in beta_proto_files:
				sc = score_beta_file(bp)
				if (best_score is None) or (sc < best_score):
					best_score = sc
					best_bp = bp

			keep_set = {best_bp}
			for bp in beta_proto_files:
				if bp != best_bp:
					if is_log_enabled:
						print(f"{n(i)}Removing earlier Beta: {Fore.RED}{os.path.basename(bp)}{Style.RESET_ALL}")
					os.remove(bp)

			# safety check: never remove all
			if not keep_set:
				# fallback => keep them all
				for p in beta_proto_files:
					files_to_keep.add(p)
				if is_log_enabled:
					print(f"{n(i)}No latest Beta, keeping all:")
					print_files_list(beta_proto_files, Fore.GREEN)
			else:
				for f in keep_set:
					files_to_keep.add(f)
				if is_log_enabled:
					print(f"{n(i)}Latest Beta: {Fore.GREEN}{os.path.basename(best_bp)}{Style.RESET_ALL}")
			continue

		# If chosen_set is empty for some reason, fallback => keep them all
		if not chosen_set:
			for p in paths:
				files_to_keep.add(p)
			if is_log_enabled:
				print(f"{n(i)}No release ROMs, keeping all these:")
				print_files_list(paths, Fore.GREEN)
			continue

		# Among the chosen normal set, pick best scored files
		if len(chosen_set) == 1:
			files_to_keep.add(chosen_set[0])
			if is_log_enabled:
				print(f"{n(i)}Single release ROM: {Fore.GREEN}{os.path.basename(chosen_set[0])}{Style.RESET_ALL}")
			continue

		best_normal = set()
		best_score = None
		for nf in chosen_set:
			sc = score_normal_file(nf)
			if (best_score is None) or (sc < best_score):
				best_score = sc
				best_normal = {nf}
			elif sc == best_score:
				best_normal.add(nf)

		# remove all others
		keep_set = best_normal
		for nf in chosen_set:
			if nf not in best_normal:
				if is_log_enabled:
					print(f"{n(i)}Removing duplicate: {Fore.RED}{os.path.basename(nf)}{Style.RESET_ALL}")
				os.remove(nf)

		# safety check
		if not keep_set:
			# fallback => keep them all
			for f in chosen_set:
				files_to_keep.add(f)
			if is_log_enabled:
				print(f"{n(i)}No best ROM, keeping all:")
				print_files_list(chosen_set, Fore.GREEN)
		else:
			# check what we need to do with the rest of the best
			if len(keep_set) > 1:
				if action == Action.KEEP_ALL:
					if is_log_enabled:
						print(f"{n(i)}Keeping all best ROMs:")
						print_files_list(keep_set, Fore.GREEN)
						
				elif action == Action.KEEP_ONE:
					best_kept = min(keep_set, key=lambda x: x)
					keep_set = keep_one(keep_set, best_kept)
					
				elif action == Action.ASK:
					print(f"{n(i)}Can't decide which one is the best. Please select one to keep:")
					keep_list = list(keep_set)
					for idx, file in enumerate(keep_list, start=1):
						print(f" {idx}. {Fore.YELLOW}{os.path.basename(file)}{Style.RESET_ALL}")
					
					selected_index = -1
					while selected_index < 0 or selected_index > len(keep_list):
						try:
							selected_index = int(input("Enter the number of the file to keep (0 to keep all): "))
						except ValueError:
							print("Invalid input. Please enter a number.")
					
					if selected_index == 0:
						if is_log_enabled:
							print(f"{n(i)}Keeping all best ROMs:")
							print_files_list(keep_set, Fore.GREEN)
					else:
						user_selected = keep_list[selected_index - 1]
						keep_set = keep_one(keep_set, user_selected)
			
			if len(keep_set) == 1:
				if is_log_enabled:
					print(f"{n(i)}Best ROM: {Fore.GREEN}{os.path.basename(next(iter(keep_set)))}{Style.RESET_ALL}")
			
			for f in keep_set:
				files_to_keep.add(f)

	# Return only files we decided to keep
	return [f for f in file_list if f in files_to_keep]

def is_next_optional_parameter(args, i) -> bool:
	return i+1 < len(args) and not args[i+1].startswith("-")

def mane():
	print(">> Initializing...")

	separation_options = CategoryOption.HOMEBREW | CategoryOption.PIRATES
	is_sort_enabled = False
	sort_options = CategoryOption(0)
	is_reverse_sort = False
	is_unpacking_enabled = False
	is_packing_enabled = False
	packing_format = "7z"
	is_log_enabled = False
	is_remove_duplicates = False
	remove_duplicates_action = Action.NOT_DEFINED
	subfolders = None
	exclude_tags = None
	input_folder = "."

	colorama.init()

	# Parse command line arguments
	args = sys.argv[1:]
	skip_next = False
	for i, arg in enumerate(args):
		if skip_next:
			skip_next = False
			continue
		if arg in ("-u", "--unpack"):
			is_unpacking_enabled = True
		elif arg in ("-p", "--pack"):
			is_packing_enabled = True
			if is_next_optional_parameter(args, i):
				pack_param = args[i+1]
				if pack_param == "7z":
					packing_format = "7z"
				elif pack_param == "zip":
					packing_format = "zip"
				else:
					print(f"{Fore.RED}Error: Unknown format '{pack_param}'! --pack only supports '7z' or 'zip'.{Style.RESET_ALL}")
					sys.exit(1)
				skip_next = True
		elif arg in ("-k", "--keep"):
			if is_next_optional_parameter(args, i):
				keep_params = args[i+1]
				if keep_params == "none":
					separation_options = CategoryOption(0)
				elif 'a' in keep_params:
					separation_options = CategoryOption.HOMEBREW | CategoryOption.PIRATES
				else:
					if 'h' in keep_params:
						separation_options |= CategoryOption.HOMEBREW
					if 'p' in keep_params:
						separation_options |= CategoryOption.PIRATES
				skip_next = True
		elif arg in ("-s", "--sort"):
			is_sort_enabled = True
			if is_next_optional_parameter(args, i):
				sort_params = args[i+1]
				if sort_params == "reverse":
					is_reverse_sort = True
				else:
					if sort_params == "none":
						sort_options = CategoryOption(0)
					elif 'a' in sort_params:
						sort_options = CategoryOption.HOMEBREW | CategoryOption.PIRATES | CategoryOption.SUBFOLDERS
					else:
						if 'h' in sort_params:
							sort_options |= CategoryOption.HOMEBREW
						if 'p' in sort_params:
							sort_options |= CategoryOption.PIRATES
						if 's' in sort_params:
							sort_options |= CategoryOption.SUBFOLDERS
				skip_next = True
		elif arg in ("-l", "--log"):
			is_log_enabled = True
		elif arg in ("-r", "--remove-duplicates"):
			is_remove_duplicates = True
			if is_next_optional_parameter(args, i):
				remove_duplicates_param = args[i+1]
				if remove_duplicates_param == "ask":
					remove_duplicates_action = Action.ASK
				elif remove_duplicates_param == "all":
					remove_duplicates_action = Action.KEEP_ALL
				elif remove_duplicates_param == "one":
					remove_duplicates_action = Action.KEEP_ONE
				else:
					print(f"{Fore.RED}Error: Unknown action '{remove_duplicates_param}'! --remove-duplicates only supports 'ask', 'all' or 'one'.{Style.RESET_ALL}")
					sys.exit(1)
				skip_next = True
		elif arg in ("-f", "--subfolders"):
			if i+1 < len(args):
				subfolders = args[i+1].split(",")
				if is_log_enabled:
					print("Subfolders:", subfolders)
				skip_next = True
			else:
				print(f"{Fore.RED}Error: --subfolders requires a comma-separated list of subfolders.{Style.RESET_ALL}")
				sys.exit(1)
		elif arg in ("-e", "--exclude"):
			if i+1 < len(args):
				exclude_tags = args[i+1].split(",")
				if is_log_enabled:
					print("Exclude tags:", exclude_tags)
				skip_next = True
			else:
				print(f"{Fore.RED}Error: --exclude requires a comma-separated list of tags.{Style.RESET_ALL}")
				sys.exit(1)
		elif arg in ("-i", "--input"):
			if i+1 < len(args):
				input_folder = args[i+1]
				skip_next = True
			else:
				print(f"{Fore.RED}Error: --input requires a folder path.{Style.RESET_ALL}")
				sys.exit(1)
				
	# Set default action for duplicates removal
	if remove_duplicates_action == Action.NOT_DEFINED:
		remove_duplicates_action = Action.ASK if is_log_enabled else Action.KEEP_ALL

	# Check for conflicting options
	if is_unpacking_enabled is True and is_packing_enabled is True:
		print(f"{Fore.RED}Error: You cannot --extract and --pack at the same time.{Style.RESET_ALL}")
		sys.exit(1)

	if (is_sort_enabled is False
			and is_unpacking_enabled is False
			and is_packing_enabled is False
			and is_remove_duplicates is False):
		print(f"{Fore.YELLOW}Nothing to do...{Style.RESET_ALL}")
		sys.exit()

	if not os.path.exists(input_folder):
		print(f"{Fore.RED}Error: The specified input folder '{input_folder}' does not exist.{Style.RESET_ALL}")
		sys.exit(1)
	os.chdir(input_folder)
	print(f"Current working directory set to: {os.getcwd()}")

	if exclude_tags is not None and subfolders is None:
		print(f"{Fore.YELLOW}Warning: You cannot use --exclude without --subfolders. Option ignored.{Style.RESET_ALL}")

	# Get files list
	files_list = glob.glob("**/*.*", recursive=True)

	# If duplicates removal is enabled, do it first
	if is_remove_duplicates:
		files_list = clean_duplicates(files_list, remove_duplicates_action, is_log_enabled)
		print("Total ROMs after duplicates removal: ", len(files_list))
		
	# Process files
	if is_sort_enabled is True or is_unpacking_enabled is True or is_packing_enabled is True:
		print(">> Processing files...")
		if is_log_enabled:
			progress = files_list
		else:
			progress = tqdm(files_list, desc="Processing")
	
		i = 0
		for file_name in progress:
			i += 1
			if is_log_enabled:
				print(f"({i}/{len(progress)}) Processing: {Fore.GREEN}{os.path.basename(file_name)}{Style.RESET_ALL}")
	
			# Sorting options
			if is_sort_enabled:
				if is_reverse_sort:
					target_folder = '.'
				else:
					target_folder = get_new_folder(os.path.basename(file_name), separation_options, sort_options, 
												   subfolders, exclude_tags)
			else:
				target_folder = os.path.dirname(file_name)
	
			# Extracting block
			if is_unpacking_enabled:
				if file_name.endswith(".7z"):
					with py7zr.SevenZipFile(file_name, 'r') as archive:
						archive.extractall(target_folder)
				elif file_name.endswith(".zip"):
					with zipfile.ZipFile(file_name, 'r') as archive:
						archive.extractall(target_folder)
				os.remove(file_name)
				if is_log_enabled:
					print(f" >> Unpacked to: {Fore.BLUE}{target_folder}{Style.RESET_ALL}")
			# Packing block
			elif is_packing_enabled and not file_name.endswith(".7z") and not file_name.endswith(".zip"):
				archive_path = os.path.join(target_folder, os.path.basename(file_name))
				if packing_format == "7z":
					with py7zr.SevenZipFile(str(archive_path) + ".7z", 'w') as archive:
						archive.write(file_name, arcname=os.path.basename(file_name))
				elif packing_format == "zip":
					with zipfile.ZipFile(str(archive_path + ".zip"), 'w', zipfile.ZIP_DEFLATED) as archive:
						archive.write(file_name, arcname=os.path.basename(file_name))
				os.remove(file_name)
				if is_log_enabled:
					print(f" >> Packed to: {Fore.BLUE}{archive_path}.{packing_format}{Style.RESET_ALL}")
			# Execute sorting
			else:
				shutil.move(file_name, os.path.join(target_folder, os.path.basename(str(file_name))))
				if is_log_enabled:
					print(f" >> Moved to: {Fore.BLUE}{target_folder}{Style.RESET_ALL}")
	
		remove_meta_files(".", is_log_enabled)
		remove_empty_subfolders(".", is_log_enabled)

	print(">> DONE!")
	sys.exit()

if __name__ == "__main__":
	freeze_support()
	mane()
