import os
import re

def is_homebrew(file_tags) -> bool:
    return "homebrew" in file_tags or "aftermarket" in file_tags

def is_pirate(file_tags) -> bool:
    return "pirate" in file_tags or "unl" in file_tags

def get_from_filename(filename: str) -> list[str]:
    name_no_ext = os.path.splitext(filename)[0]
    groups = re.findall(r'[(\[](.*?)[)\]]', name_no_ext)
    all_tags = []
    for g in groups:
        split_tags = [t.strip() for t in g.split(',')]
        all_tags.extend(split_tags)
    return [tag.lower() for tag in all_tags]

def get_base_name(filename: str) -> str:
    name_no_ext = os.path.splitext(filename)[0]
    idx_1 = name_no_ext.find('(')
    idx_2 = name_no_ext.find('[')
    idx = min(idx_1, idx_2) if idx_1 != -1 and idx_2 != -1 else max(idx_1, idx_2)
    if idx != -1:
        base = name_no_ext[:idx].strip()
    else:
        base = name_no_ext.strip()
    return base