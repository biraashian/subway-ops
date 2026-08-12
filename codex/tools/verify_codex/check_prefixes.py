"""Chapter numbers are unique.

Two directories sharing a prefix is how a codex ends up with two chapter 04s and
a spec anchored to the wrong one. The Verity codex hit exactly this and had to
renumber a duplicate 004 during its cutover.
"""

import os
import re
import sys
from collections import defaultdict

root = sys.argv[1]
by_prefix = defaultdict(list)

for name in sorted(os.listdir(root)):
    if os.path.isdir(os.path.join(root, name)) and re.match(r"^\d{2}-", name):
        by_prefix[name[:2]].append(name)

duplicates = {prefix: names for prefix, names in by_prefix.items() if len(names) > 1}

if duplicates:
    print(f"{len(duplicates)} duplicate chapter prefix(es):")
    for prefix, names in sorted(duplicates.items()):
        print(f"  {prefix}: {', '.join(names)}")
    sys.exit(1)
sys.exit(0)
