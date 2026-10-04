"""Run from a checkout without installing anything."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from clashlab.cli import main


if __name__ == "__main__":
    main()
