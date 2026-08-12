"""The chapter table in codex/README.md matches the directories on disk.

Two failure directions, both real:

  - a chapter directory exists but is not in the index, so nobody reads it and
    specs anchor to something the index says does not exist;
  - the index lists a chapter whose directory is missing, which is how a
    "we already decided that" turns out to be a link to nothing.

Chapters still marked "not written" in the index are expected to have no
directory yet — that is the honest pre-interview state, not a defect.
"""

import os
import re
import sys
from pathlib import Path

root = sys.argv[1]
index_path = os.path.join(root, "README.md")

if not os.path.exists(index_path):
    print("codex/README.md is missing — there is no chapter index")
    sys.exit(1)

text = Path(index_path).read_text(encoding="utf-8")

# Rows look like: | 00 | [INSTITUTION](00-INSTITUTION/README.md) — ... | status | ... |
listed: dict[str, str] = {}
for match in re.finditer(r"^\|\s*(\d{2})\s*\|\s*(.+?)\s*\|\s*([^|]+?)\s*\|", text, re.MULTILINE):
    number, label, status = match.group(1), match.group(2), match.group(3).strip()
    listed[number] = status

on_disk = {
    name[:2]: name
    for name in os.listdir(root)
    if os.path.isdir(os.path.join(root, name)) and re.match(r"^\d{2}-", name)
}

problems = []

for number, name in sorted(on_disk.items()):
    if number not in listed:
        problems.append(f"{name}/ exists on disk but is not in the README index")
    elif listed[number] == "not written":
        problems.append(f"{name}/ exists but the index still says 'not written'")

for number, status in sorted(listed.items()):
    if status != "not written" and number not in on_disk:
        problems.append(f"index lists chapter {number} as '{status}' but no directory exists")

# Every chapter directory needs an entry document.
for name in sorted(on_disk.values()):
    directory = os.path.join(root, name)
    if not any(f.endswith(".md") for f in os.listdir(directory)):
        problems.append(f"{name}/ has no markdown file")

if problems:
    print(f"{len(problems)} index problem(s):")
    for line in problems:
        print(f"  {line}")
    sys.exit(1)
sys.exit(0)
