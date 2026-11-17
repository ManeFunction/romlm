#!/usr/bin/env python3
"""
Build the body of a GitHub release page. Copy to .github/scripts/release_notes.py.

The body is the release's whole section from CHANGELOG.md, copied verbatim: everything between the
"## [x.y.z] - date" heading and the next "## " heading (the intro, if any, and every "### Added/Changed/
Fixed/..." block), then a "**Full Changelog**: <compare link>" line like the one GitHub generates
(.../compare/<previous tag>...<tag>, or .../commits/<tag> for the first tag). Nothing comes from commit
messages or GitHub's auto-generated notes. Write the section as you want it on the release page (it is
Markdown either way).

The link needs the repo ("owner/name", from --repo or GITHUB_REPOSITORY; left out with a warning when
neither is set) and the previous tag (from --previous-tag, else `git describe --tags --abbrev=0 <tag>^`,
so the CI checkout needs fetch-depth: 0).

The tag comes from --tag or GITHUB_REF_NAME (a leading "v" is ignored when matching the CHANGELOG).
Pure standard library, Python 3.9+. A version missing from CHANGELOG.md is a warning, not an error, and
gives an empty body (check_version.py is the gate).

Usage:
    release_notes.py [--tag v1.2.3] [--changelog CHANGELOG.md] [--repo owner/name]
                     [--previous-tag v1.2.2] [--no-link]
"""
import argparse
import os
import re
import subprocess
import sys


def changelog_section(text, version):
    """Everything between the version's "## " heading and the next "## " heading."""
    heading = re.compile(r"^##\s+\[?v?" + re.escape(version) + r"\]?(?:\s|$)")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if heading.match(line):
            body = []
            for following in lines[i + 1:]:
                if following.startswith("## "):
                    break
                body.append(following)
            return "\n".join(body).strip("\n").rstrip(), True
    return "", False


def previous_tag(tag):
    result = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0", f"{tag}^"],
        capture_output=True, text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def full_changelog_link(repo, tag, prev):
    if prev:
        return f"**Full Changelog**: https://github.com/{repo}/compare/{prev}...{tag}"
    return f"**Full Changelog**: https://github.com/{repo}/commits/{tag}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default=os.environ.get("GITHUB_REF_NAME", ""))
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/name for the link")
    parser.add_argument("--previous-tag", help="tag to compare against (default: the nearest earlier tag)")
    parser.add_argument("--no-link", action="store_true", help="leave out the Full Changelog link")
    args = parser.parse_args()
    if not args.tag:
        parser.error("no tag: pass --tag or set GITHUB_REF_NAME")
    version = args.tag[1:] if args.tag.startswith("v") else args.tag

    section, found = "", False
    if os.path.exists(args.changelog):
        with open(args.changelog, encoding="utf-8") as f:
            section, found = changelog_section(f.read(), version)
    if not found:
        print(f"warning: no '## [{version}]' section in {args.changelog}", file=sys.stderr)

    parts = [section]
    if not args.no_link:
        if args.repo:
            prev = args.previous_tag if args.previous_tag is not None else previous_tag(args.tag)
            parts.append(full_changelog_link(args.repo, args.tag, prev))
        else:
            print("warning: no repo (--repo or GITHUB_REPOSITORY), leaving out the Full Changelog link",
                  file=sys.stderr)

    print("\n\n".join(part for part in parts if part))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
