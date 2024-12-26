import sys
import os
import glob
import re
import math
from tqdm import tqdm
from multiprocessing import Process, freeze_support

def parse_game_info(filename):
	# Extract the base game name, region, and languages from the filename
	base = os.path.basename(filename)
	base_no_ext = os.path.splitext(base)[0]

	# Known region tags and priorities
	region_priority = {
		'usa': 1,
		'europe': 2,
		'germany': 3,
		'france': 3,
		'japan': 99,
	}

	pattern = r"\(([^)]*)\)"
	matches = re.findall(pattern, base_no_ext)
	regions_found = []
	languages_found = []
	other_tags = []

	def classify_tag(tag):
		t = tag.lower().strip()
		if 'usa' in t:
			return ('region','usa')
		if 'europe' in t:
			return ('region','europe')
		if 'japan' in t:
			return ('region','japan')

		langs = ['en','fr','de','es','it','ja','nl','sv','no','da','fi','pt']
		subs = [x.strip().lower() for x in t.split(',')]
		if all(x in langs for x in subs):
			return ('language', subs)
		return ('other', t)

	for m in matches:
		result = classify_tag(m)
		if result[0] == 'region':
			regions_found.append(result[1])
		elif result[0] == 'language':
			languages_found.extend(result[1])
		else:
			other_tags.append(result[1])

	chosen_region = None
	chosen_priority = 999
	for r in regions_found:
		p = region_priority.get(r,50)
		if p < chosen_priority:
			chosen_priority = p
			chosen_region = r

	if not chosen_region:
		chosen_region = 'unknown'
		chosen_priority = 100

	has_english = False
	if languages_found:
		if 'en' in languages_found:
			has_english = True
	else:
		if chosen_region in ['usa','europe']:
			has_english = True

	base_name = re.sub(pattern, '', base_no_ext).strip()
	base_name = re.sub(' +',' ',base_name)

	return {
		'filename': filename,
		'base_name': base_name,
		'region': chosen_region,
		'region_priority': chosen_priority,
		'has_english': has_english
	}

def mane():
	print(">> Initializing...")

	input_folder = "."

	# Parse arguments
	args = sys.argv[1:]
	skip_next = False
	for i, arg in enumerate(args):
		if skip_next:
			skip_next = False
			continue
		if arg in ("-i", "--input"):
			if i+1 < len(args):
				input_folder = args[i+1]
				skip_next = True
			else:
				print("Error: --input requires a folder path.")
				sys.exit(1)

	if not os.path.exists(input_folder):
		print(f"Error: The specified input folder '{input_folder}' does not exist.")
		sys.exit(1)
	os.chdir(input_folder)
	print(f"Current working directory set to: {os.getcwd()}")

	# Get files list
	all_files = glob.glob("**/*.gba", recursive=True)

	# Really great games list (example from previous answer)
	really_great_games = [
		# Nintendo First-Party Classics & Key Franchises
		"Mario & Luigi - Superstar Saga",
		"Metroid Fusion",
		"Metroid - Zero Mission",
		"The Legend of Zelda - The Minish Cap",
		"Wario Land 4",
		"Kirby & The Amazing Mirror",
		"Kirby - Nightmare in Dream Land",
		"Yoshi's Island - Super Mario Advance 3",
		"Super Mario Advance",
		"Super Mario Advance 2 - Super Mario World",
		"Super Mario Advance 4 - Super Mario Bros. 3",
		"F-Zero - Maximum Velocity",
		"F-Zero - GP Legend",
		"Mario Golf - Advance Tour",
		"Mario Tennis - Power Tour",
		"WarioWare, Inc. - Mega Microgame$!",
		"WarioWare - Twisted!",
		"Mario vs. Donkey Kong",
		"Donkey Kong Country",
		"Donkey Kong Country 2",
		"Donkey Kong Country 3",
		"Fire Emblem",
		"Fire Emblem - The Sacred Stones",
		"Advance Wars",
		"Advance Wars 2 - Black Hole Rising",
		"Golden Sun",
		"Golden Sun - The Lost Age",
		"Pokémon Ruby Version",
		"Pokémon Sapphire Version",
		"Pokémon FireRed Version",
		"Pokémon LeafGreen Version",
		"Pokémon Emerald Version",
		"Pokémon Mystery Dungeon - Red Rescue Team",

		# Square Enix (RPGs & Remakes)
		"Final Fantasy I & II - Dawn of Souls",
		"Final Fantasy IV Advance",
		"Final Fantasy V Advance",
		"Final Fantasy VI Advance",
		"Final Fantasy Tactics Advance",
		"Kingdom Hearts - Chain of Memories",
		"Sword of Mana",

		# Other Celebrated RPGs & Strategy Games
		"Tactics Ogre - The Knight of Lodis",
		"Lufia - The Ruins of Lore",
		"Breath of Fire",
		"Breath of Fire II",
		"Harvest Moon - Friends of Mineral Town",
		"Harvest Moon - More Friends of Mineral Town",
		"Lunar Legend",
		"Tales of Phantasia",
		"Shining Soul II",
		"Phantasy Star Collection",
		"Riviera - The Promised Land",
		"Yggdra Union - We'll Never Fight Alone",
		"Summon Night - Swordcraft Story",
		"Summon Night - Swordcraft Story 2",
		"Shining Force - Resurrection of the Dark Dragon",

		# Action & Platformers (Non-Nintendo)
		"Castlevania - Circle of the Moon",
		"Castlevania - Harmony of Dissonance",
		"Castlevania - Aria of Sorrow",
		"Mega Man Zero",
		"Mega Man Zero 2",
		"Mega Man Zero 3",
		"Mega Man Zero 4",
		"Mega Man & Bass",
		"Boktai - The Sun Is in Your Hand",
		"Boktai 2 - Solar Boy Django",
		"Astro Boy - Omega Factor",
		"Gunstar Super Heroes",
		"Ninja Five-O",
		"Klonoa - Empire of Dreams",
		"Klonoa 2 - Dream Champ Tournament",
		"Sonic Advance",
		"Sonic Advance 2",
		"Sonic Advance 3",
		"Sonic Pinball Party",
		"Sonic Battle",
		"Contra Advance - The Alien Wars EX",
		"Iridion II",
		"Drill Dozer",
		"Kuru Kuru Kururin",
		"Kururin Paradise",
		"Rayman Advance",
		"Rayman 3",
		"Wings (Wing Commander: Prophecy)",
		"Car Battler Joe",
		"Spyro - Season of Ice",
		"Spyro 2 - Season of Flame",
		"Spyro - Attack of the Rhynocs",

		# Mega Man Battle Network Series (Highly Regarded by Fans)
		"Mega Man Battle Network",
		"Mega Man Battle Network 2",
		"Mega Man Battle Network 3 White",
		"Mega Man Battle Network 3 Blue",
		"Mega Man Battle Network 4 Red Sun",
		"Mega Man Battle Network 4 Blue Moon",
		"Mega Man Battle Network 5 Team Protoman",
		"Mega Man Battle Network 5 Team Colonel",
		"Mega Man Battle Network 6 Cybeast Gregar",
		"Mega Man Battle Network 6 Cybeast Falzar",

		# Mother Series & Japan-Only Greats (If Allowed)
		"Mother 3",   # widely considered a masterpiece, JP only but fan translations exist

		# Miscellaneous Highly Rated Titles
		"Tony Hawk's Pro Skater 2",
		"Tony Hawk's Pro Skater 3",
		"Mario Kart - Super Circuit",
		"Crash Bandicoot - The Huge Adventure",
		"Crash Bandicoot 2 - N-Tranced",
		"Medal of Honor - Infiltrator",
		"Kuru Kuru Kururin",
		"Baldur's Gate - Dark Alliance",
		"Duke Nukem Advance",
		"Doom",
		"Doom II",
		"ChuChu Rocket!",
		"Pinball of the Dead, The",
		"Super Puzzle Fighter II",
		"SSX 3",
		"Grand Theft Auto Advance",
		"Robot Wars - Extreme Destruction",
		"Hot Wheels - Velocity X",
		"R-Type III - The Third Lightning",
		"Super Ghouls'n Ghosts",

		# More Well-Received Licensed / Niche Titles
		"Dragon Ball Z - The Legacy of Goku II",
		"Dragon Ball Z - Buu's Fury",
		"TMNT (2003)",
		"Bionicle - Maze of Shadows",
		"Iridion 3D",
		"Sabre Wulf",
		"Broken Sword - The Shadow of the Templars",
		"Kim Possible 2 - Drakken's Demise",
		"Lady Sia",
		"Monster Rancher Advance",
		"Monster Rancher Advance 2",
		"Onimusha Tactics",
		"Tomb Raider - The Prophecy",
		"Boulder Dash EX",

		# Puzzle & Misc Classics
		"Puyo Pop",
		"Kuru Kuru Kururin"  # repeated above; keep once
	]

	# Note: Some titles may appear twice if mentioned multiple times above — remove duplicates as needed.

	favorites_set = set(really_great_games)

	print(">> Processing files for duplicates and selecting best versions...")

	roms = []
	for f in all_files:
		info = parse_game_info(f)
		size = os.path.getsize(f)
		info['size'] = size
		roms.append(info)

	from collections import defaultdict
	groups = defaultdict(list)
	for r in roms:
		groups[r['base_name'].lower()].append(r)

	keep_list = []
	for base_n, grp in groups.items():
		if len(grp) == 1:
			candidate = grp[0]
			if candidate['has_english'] or candidate['base_name'] in favorites_set or candidate['region'] in ['usa','europe']:
				keep_list.append(candidate)
			else:
				pass
			continue

		# Multiple duplicates
		grp_sorted = sorted(grp, key=lambda x: (x['region_priority'], 0 if x['has_english'] else 1))
		english_versions = [g for g in grp if g['has_english']]
		if english_versions:
			keep_list.append(english_versions[0])
		else:
			# No English version
			if any(g['base_name'] in favorites_set for g in grp):
				keep_list.append(grp_sorted[0])
			else:
				pass

	# Now remove sports games
	# Define keywords that identify sports games
	sport_keywords = [
		"fifa", "madden", "nhl", "mlb", "nba", "nfl", "nascar", "soccer",
		"football", "baseball", "hockey", "golf", "tennis", "rally",
		"cricket", "rugby", "bowling", "fishing"
	]

	def is_sport_game(name):
		lname = name.lower()
		for kw in sport_keywords:
			if kw in lname:
				return True
		return False

	keep_list = [r for r in keep_list if not is_sport_game(r['base_name'])]

	# Now do the size trimming to 10GB if needed
	max_size = 10 * 1024 * 1024 * 1024
	total_size = sum(r['size'] for r in keep_list)
	if total_size > max_size:
		print("Total size exceeds 10 GB, trimming...")
		# Separate favorites and non-favorites
		favorites_keep = [r for r in keep_list if r['base_name'] in favorites_set]
		non_favorites_keep = [r for r in keep_list if r['base_name'] not in favorites_set]

		non_favorites_keep.sort(key=lambda x: x['size'], reverse=True)

		trimmed_keep = favorites_keep[:]
		current_size = sum(r['size'] for r in trimmed_keep)
		for nf in non_favorites_keep:
			if current_size <= max_size:
				trimmed_keep.append(nf)
			else:
				# skip to reduce size
				pass
			current_size = sum(r['size'] for r in trimmed_keep)
			if current_size <= max_size:
				trimmed_keep += [x for x in non_favorites_keep if x not in trimmed_keep]
				break

		if current_size <= max_size:
			# already done
			pass

		final_names = set(r['filename'] for r in trimmed_keep)
		keep_list = [r for r in keep_list if r['filename'] in final_names]

	keep_files = set(r['filename'] for r in keep_list)
	all_files_set = set(all_files)

	to_delete = all_files_set - keep_files

	print(f"Keeping {len(keep_list)} files, deleting {len(to_delete)} files...")

	for f in tqdm(to_delete, desc="Deleting"):
		os.remove(f)

	print(">> DONE!")
	sys.exit()

if __name__ == "__main__":
	freeze_support()
	Process(target=mane).start()
