"""Run the bounded compressed-asset scan without installing Clash Lab."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from clashlab.compressed_assets import main


if __name__ == "__main__":
    main()
