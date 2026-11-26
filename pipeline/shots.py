"""Stage: moving shots. One clip per shot and aspect ratio, cached by a hash of its inputs.

- If a Wan 2.2 clip exists for the shot (made on a Kaggle GPU, see notebooks/), it is fitted to the
  aspect ratio and length.
- Otherwise the keyframe gets a slow camera move (Ken Burns: push-in, pull-out or pan), as chosen in
  storyboard.json. The brief accepts this as a respectable shot and as the fallback when a clip fails.

Keyframes are square; each is cropped to the target aspect first and only then moved, so nothing is
stretched. Clips are rendered at the film's final size and frame rate so assembly can join them
without re-encoding.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pipeline.core import OUTPUTS, input_hash
from pipeline.keyframes import file_hash, keyframe_path

SHOTS_DIR = OUTPUTS / "shots"
WAN_DIR = OUTPUTS / "wan"
FPS = 24
ZOOM = 0.12  # how far a push-in or pull-out travels: 12 % over the shot
PAN_ZOOM = 1.10  # pans run at 10 % zoom so there is room to move
WAN_CLIP_S = 121 / 24  # Wan 2.2 TI2V-5B clip: 121 frames at 24 fps
MAX_SLOWDOWN = 1.5  # slow a short clip at most this much before holding its last frame

ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS)]

# zoompan expressions: `on` is the output frame number, `d` the number of frames
MOVES = {
    "push_in": ("1+{z}*on/{last}", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "pull_out": ("1+{z}*(1-on/{last})", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"),
    "pan_left": ("{p}", "(iw-iw/zoom)*(1-on/{last})", "ih/2-(ih/zoom/2)"),
    "pan_right": ("{p}", "(iw-iw/zoom)*on/{last}", "ih/2-(ih/zoom/2)"),
    "pan_up": ("{p}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*(1-on/{last})"),
    "pan_down": ("{p}", "iw/2-(iw/zoom/2)", "(ih-ih/zoom)*on/{last}"),
}


def wan_clip(storyboard: dict[str, Any], shot: dict[str, Any]) -> Path | None:
    """The Wan clip made from this exact keyframe and motion prompt, if one has been downloaded."""
    if shot["motion"]["method"] != "wan":
        return None
    key = input_hash({"keyframe": file_hash(keyframe_path(storyboard, shot)), "motion": shot["motion_prompt"],
                      "model": storyboard["models"]["video"]})
    path = WAN_DIR / f"{shot['id']}-{key}.mp4"
    return path if path.exists() else None


def clip_inputs(storyboard: dict[str, Any], shot: dict[str, Any], length_s: float, size: tuple[int, int]) -> dict:
    wan = wan_clip(storyboard, shot)
    return {
        "source": file_hash(wan) if wan else file_hash(keyframe_path(storyboard, shot)),
        "kind": "wan" if wan else "kenburns",
        "move": None if wan else shot["motion"]["kenburns"],
        "length_s": round(length_s, 3),
        "size": list(size),
        "fps": FPS,
    }


def clip_path(storyboard: dict[str, Any], shot: dict[str, Any], length_s: float, size: tuple[int, int]) -> Path:
    key = input_hash(clip_inputs(storyboard, shot, length_s, size))
    return SHOTS_DIR / f"{size[0]}x{size[1]}" / f"{shot['id']}-{key}.mp4"


def aspect_crop(width: int, height: int) -> str:
    """Centre-crop a square keyframe (or any frame) to the output's aspect ratio."""
    return f"crop='min(iw,ih*{width}/{height})':'min(ih,iw*{height}/{width})'"


def kenburns_filter(move: str, frames: int, width: int, height: int) -> str:
    z_expr, x_expr, y_expr = MOVES[move]
    last = max(frames - 1, 1)
    z = z_expr.format(z=ZOOM, p=PAN_ZOOM, last=last)
    # Upscale before zoompan: it moves in whole pixels, so a larger source keeps slow moves smooth.
    return (
        f"{aspect_crop(width, height)},scale={width * 2}:{height * 2},"
        f"zoompan=z='{z}':x='{x_expr.format(last=last)}':y='{y_expr.format(last=last)}'"
        f":d={frames}:s={width}x{height}:fps={FPS},setsar=1,format=yuv420p"
    )


def render_clip(storyboard: dict[str, Any], shot: dict[str, Any], length_s: float, size: tuple[int, int]) -> Path:
    """Make (or reuse) the clip for one shot at one size."""
    from pipeline.assemble import run_ffmpeg  # assembly owns the FFmpeg runner

    path = clip_path(storyboard, shot, length_s, size)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = size
    frames = round(length_s * FPS)
    wan = wan_clip(storyboard, shot)
    partial_path = path.with_name(path.stem + ".part.mp4")
    if wan:
        # Fit the clip: slow it gently (up to 1.5x) toward the shot length, crop to the aspect, scale, and
        # hold the last frame only for whatever is still missing.
        slow = min(max(length_s / WAN_CLIP_S, 1.0), MAX_SLOWDOWN)
        vf = (f"setpts={slow:.3f}*PTS,{aspect_crop(width, height)},scale={width}:{height}:flags=lanczos,setsar=1,"
              f"tpad=stop_mode=clone:stop_duration={length_s:.3f},fps={FPS},format=yuv420p")
        args = ["-i", str(wan), "-vf", vf, "-t", f"{length_s:.3f}", "-an", *ENCODE, str(partial_path)]
    else:
        vf = kenburns_filter(shot["motion"]["kenburns"], frames, width, height)
        args = ["-i", str(keyframe_path(storyboard, shot)), "-vf", vf, "-frames:v", str(frames), *ENCODE,
                str(partial_path)]
    run_ffmpeg(args, step=f"shot_{shot['id']}_{width}x{height}")
    partial_path.replace(path)
    return path
