#!/usr/bin/env python3
"""
Print a Features/Fixes/Refactor changelog section from conventional-commit
subject lines in a git range, e.g. "v1.0.0..v1.1.0" (or just "v1.0.0" for
everything up to and including that tag, when there's no previous tag).

Only "feat", "fix", and "refactor" commits are included (optionally with a
"(scope)" and/or a "!" for breaking changes, e.g. "feat(cli)!: ..."). Every
other prefix ("meta", "dev", "chore", etc.) is ignored. Each list item is the
commit subject with the "prefix(scope)!: " part stripped -- everything after
the first ": ".

Usage:
    python3 categorize_changelog.py <git-range>

Prints nothing (empty output) if there are no matching commits in range.
"""
import re
import subprocess
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1

    rng = sys.argv[1]
    subjects = subprocess.run(
        ["git", "log", rng, "--pretty=format:%s"],
        capture_output=True, text=True, check=True,
    ).stdout.splitlines()

    sections = {
        "feat": ("Features", []),
        "fix": ("Fixes", []),
        "refactor": ("Refactor", []),
    }
    pattern = re.compile(r"^(feat|fix|refactor)(\([^)]*\))?!?: (.+)$")

    for subject in subjects:
        m = pattern.match(subject)
        if m:
            prefix, _scope, rest = m.groups()
            sections[prefix][1].append(rest)

    blocks = []
    for title, items in sections.values():
        if items:
            blocks.append("\n".join([f"{title}:", ""] + [f"* {item}" for item in items]))

    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
