"""Experiments E10 and E11: render choices on the 2-core dev laptop, measured on one real shot.

E10: Is `-preset veryfast` the right x264 setting for this laptop?
    Same shot, same CRF 19, presets ultrafast / veryfast (shipped) / medium. Measures wall-clock encode
    time (two runs each), file size, and SSIM against a lossless encode of the same frames.

E11: Does upscaling 2x before `zoompan` earn its cost?
    zoompan moves the crop in whole pixels, so a slow move can step instead of glide. Same shot, upscale
    factor 1x / 2x (shipped) / 3x. Measures encode time (two runs each) and motion smoothness: the
    coefficient of variation (std / mean) of the difference between consecutive frames. A smooth push-in
    changes every frame by about the same amount (low value); stepping makes it uneven (high value).

Uses the cached keyframe only; makes no model call. Close other programs first: timings are wall-clock.

Usage:
    uv run python experiments/render_tradeoffs.py [--shot s04]

Writes outputs/experiments/render_tradeoffs/results.json; videos go to outputs/_scratch/ (gitignored).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import time
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from pipeline import keyframes, shots
from pipeline.assemble import ASPECTS, ffmpeg_binary
from pipeline.core import OUTPUTS
from pipeline.storyboard import load_storyboard

OUT = OUTPUTS / "experiments" / "render_tradeoffs"
SCRATCH = OUTPUTS / "_scratch" / "render_tradeoffs"
PRESETS = ("ultrafast", "veryfast", "medium")
UPSCALE_FACTORS = (1, 2, 3)
REPEATS = 2


def ffmpeg(args: list[str]) -> str:
    done = subprocess.run([ffmpeg_binary(), "-y", "-hide_banner", *args], capture_output=True, text=True,
                          check=False)  # checked below, so the error shows FFmpeg's own message
    if done.returncode != 0:
        raise RuntimeError(done.stderr[-800:])
    return done.stderr


def timed_encode(source: Path, vf: str, frames: int, codec: list[str], out: Path) -> float:
    started = time.perf_counter()
    ffmpeg(["-i", str(source), "-vf", vf, "-frames:v", str(frames), *codec, str(out)])
    return round(time.perf_counter() - started, 1)


def with_preset(preset: str) -> list[str]:
    codec = list(shots.ENCODE)
    codec[codec.index("-preset") + 1] = preset
    return codec


def ssim(test: Path, reference: Path) -> float:
    report = ffmpeg(["-i", str(test), "-i", str(reference), "-lavfi", "[0:v][1:v]ssim", "-f", "null", "-"])
    return float(re.findall(r"All:([0-9.]+)", report)[-1])


def upscaled_filter(move: str, frames: int, width: int, height: int, factor: int) -> str:
    shipped = shots.kenburns_filter(move, frames, width, height)
    target = f"scale={width * 2}:{height * 2}"
    assert target in shipped, "shots.kenburns_filter changed; update this experiment"
    return shipped.replace(target, f"scale={width * factor}:{height * factor}")


def smoothness(source: Path, vf: str, frames: int, width: int, height: int) -> dict[str, float]:
    """Decode the frames uncompressed (no codec noise) and measure how evenly consecutive frames change."""
    raw = subprocess.run(
        [ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-i", str(source), "-vf", f"{vf},format=gray",
         "-frames:v", str(frames), "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, check=True,
    ).stdout
    size = width * height
    images = [Image.frombytes("L", (width, height), raw[i : i + size]) for i in range(0, len(raw), size)]
    diffs = [ImageStat.Stat(ImageChops.difference(a, b)).mean[0] for a, b in pairwise(images)]
    mean = statistics.fmean(diffs)
    return {"frames": len(images), "mean_frame_change": round(mean, 3),
            "variation_cv": round(statistics.pstdev(diffs) / mean, 3) if mean else 0.0,
            "frozen_frames": sum(d == 0 for d in diffs)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shot", default="s04")
    args = parser.parse_args()

    storyboard = load_storyboard()
    shot = next(s for s in storyboard["shots"] if s["id"] == args.shot)
    source = keyframes.keyframe_path(storyboard, shot)
    width, height = ASPECTS["9x16"]["size"]
    frames = round(shot["duration_s"] * shots.FPS)
    move = shot["motion"]["kenburns"]
    SCRATCH.mkdir(parents=True, exist_ok=True)
    shipped_vf = shots.kenburns_filter(move, frames, width, height)
    print(f"shot {args.shot}: {move}, {frames} frames at {width}x{height}")

    lossless = SCRATCH / "lossless.mkv"
    timed_encode(source, shipped_vf, frames, ["-c:v", "libx264", "-preset", "ultrafast", "-qp", "0",
                                              "-pix_fmt", "yuv420p"], lossless)
    e10 = []
    for preset in PRESETS:
        out = SCRATCH / f"preset_{preset}.mp4"
        seconds = [timed_encode(source, shipped_vf, frames, with_preset(preset), out) for _ in range(REPEATS)]
        row = {"preset": preset, "encode_s": seconds, "size_mb": round(out.stat().st_size / 1e6, 2),
               "ssim_vs_lossless": round(ssim(out, lossless), 4)}
        e10.append(row)
        print("E10", row)

    e11 = []
    for factor in UPSCALE_FACTORS:
        vf = upscaled_filter(move, frames, width, height, factor)
        out = SCRATCH / f"upscale_{factor}x.mp4"
        seconds = [timed_encode(source, vf, frames, list(shots.ENCODE), out) for _ in range(REPEATS)]
        row = {"upscale": factor, "encode_s": seconds, **smoothness(source, vf, frames, width, height)}
        e11.append(row)
        print("E11", row)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(
        {"shot": args.shot, "move": move, "frames": frames, "size": [width, height], "crf": 19,
         "machine": "Intel Celeron N4020, 2 cores", "repeats": REPEATS, "e10_presets": e10, "e11_upscale": e11},
        indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
