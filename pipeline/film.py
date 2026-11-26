"""One command for the whole pipeline: `uv run film` (or `uv run film --radio` for the radio cut).

Each stage reads storyboard.json and skips any output whose input hash already exists, so a re-run
after editing one shot regenerates only that shot.
"""

from __future__ import annotations

import argparse

from pipeline import assemble, narration
from pipeline.storyboard import load_storyboard


def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate the film from storyboard.json.")
    parser.add_argument("--radio", action="store_true", help="radio cut: narration + placeholder music on black")
    parser.add_argument("--aspect", choices=[*assemble.ASPECTS, "both"], default="both")
    args = parser.parse_args()

    storyboard = load_storyboard()  # validate the contract before spending any quota
    print(f"storyboard OK: {len(storyboard['shots'])} shots")
    narration.run(storyboard)
    aspects = list(assemble.ASPECTS) if args.aspect == "both" else [args.aspect]
    assemble.run(storyboard, radio=args.radio, aspects=aspects)


if __name__ == "__main__":
    main()
