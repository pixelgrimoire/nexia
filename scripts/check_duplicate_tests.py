#!/usr/bin/env python3
"""Check for duplicate test basenames under services/*/tests.

Exit code 0 when no duplicates. Exit code 1 when duplicates found and print them.
"""
from pathlib import Path
from collections import Counter
import sys

root = Path(__file__).resolve().parents[1]
patterns = list(root.glob('services/*/tests/test_*.py'))
names = [p.name for p in patterns]
counts = Counter(names)
dups = [name for name, c in counts.items() if c > 1]
if not dups:
    print('No duplicate test basenames found')
    sys.exit(0)

print('Duplicate test basenames found:')
for name in sorted(dups):
    print(' -', name)
    for p in sorted([str(pp) for pp in patterns if pp.name == name]):
        print('    ', p)
sys.exit(1)
