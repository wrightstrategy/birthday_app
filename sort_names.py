#!/usr/bin/env python3
"""Print the names in a text file in alphabetical order (one name per line)."""

import sys


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else "names.txt"

    try:
        with open(path, encoding="utf-8") as f:
            names = [line.strip() for line in f if line.strip()]
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    for name in sorted(names, key=str.casefold):
        print(name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
