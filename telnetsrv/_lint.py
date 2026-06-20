"""Run black --check and flake8; exit non-zero if either fails."""

import subprocess
import sys

PATHS = ["telnetsrv/", "tests/"]


def main():
    b = subprocess.run(["black", "--check"] + PATHS)
    f = subprocess.run(["flake8"] + PATHS)
    sys.exit(b.returncode or f.returncode)


if __name__ == "__main__":
    main()
