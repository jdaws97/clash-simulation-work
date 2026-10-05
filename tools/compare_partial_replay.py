"""Compare a frozen protocol and prediction trace, or fit a rendered cycle."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from clashlab.replay_calibration import calibrate_rendered_cycle, compare_replay
from clashlab.replay_observations import ObservationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("protocol", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--frame-root", type=Path)
    parser.add_argument("--allow-experimental-projection", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a fresh output path; prior reports are immutable")
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    try:
        case, protocol = read(args.case), read(args.protocol)
        if args.trace:
            report = compare_replay(
                case,
                protocol,
                read(args.trace),
                args.frame_root,
                allow_experimental=args.allow_experimental_projection,
            )
        else:
            report = calibrate_rendered_cycle(case, protocol, args.frame_root)
    except (ObservationError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(args.output)
    verdict = report.get("report", report)["verdict"]
    raise SystemExit(0 if verdict == "compatible" else 2)


if __name__ == "__main__":
    main()
