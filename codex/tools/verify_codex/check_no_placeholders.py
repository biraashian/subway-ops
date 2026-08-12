"""An authoritative chapter contains no placeholders.

`status: authoritative` means specs may anchor to it. A chapter carrying TODO or
TBD is not finished, and a spec anchored to a hole inherits the hole — which is
precisely the "unspecced layer under a specced one" that D-010 exists to
prevent. Draft chapters may contain anything.
"""

import os
import re
import sys
from pathlib import Path

root = sys.argv[1]
MARKERS = re.compile(r"\b(TODO|TBD|TKTK|FIXME|XXX|\?\?\?)\b")

problems = []

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__", "tools")]
    for name in sorted(filenames):
        if not name.endswith(".md"):
            continue
        path = os.path.join(dirpath, name)
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        if not re.search(r"^status:\s*authoritative\s*$", text, re.MULTILINE):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            match = MARKERS.search(line)
            if match:
                rel = os.path.relpath(path, root)
                problems.append(f"{rel}:{lineno}: {match.group(1)} in an authoritative chapter")

if problems:
    print(f"{len(problems)} placeholder(s):")
    for line in problems[:12]:
        print(f"  {line}")
    sys.exit(1)
sys.exit(0)
