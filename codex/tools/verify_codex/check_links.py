"""Every relative markdown link inside the codex resolves.

Ported from the Burst cleanup kit. The sibling-repo special case is dropped —
this codex is in-repo, so every link is either http or a plain relative path.
"""

import os
import re
import sys
from pathlib import Path

root = sys.argv[1]
broken = []
total = 0

for dirpath, dirnames, filenames in os.walk(root):
    dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
    for name in filenames:
        if not name.endswith(".md"):
            continue
        path = os.path.join(dirpath, name)
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r"\]\(([^)#\s]+\.md)(?:#[^)]*)?\)", text):
            target = match.group(1)
            if target.startswith("http"):
                continue
            total += 1
            if not os.path.exists(os.path.normpath(os.path.join(dirpath, target))):
                broken.append((os.path.relpath(path, root), target))

if broken:
    print(f"broken links: {len(broken)} of {total}")
    for source, target in broken[:12]:
        print(f"  {source} -> {target}")
    sys.exit(1)
sys.exit(0)
