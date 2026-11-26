"""Stage: assembly. Pure FFmpeg, no AI: the same inputs always give the same film.

Steps:
1. Timeline: each shot lasts max(planned duration, lead-in + its narration + tail). Picture is cut to the voice.
2. Narration track: every shot's narration placed at its start time (built in Python, sample-exact).
3. Music: brought to a quiet reference loudness, shaped by the storyboard's music cues, ducked under the
   voice with sidechaincompress, then mixed with the voice.
4. Two-pass loudnorm to -14 LUFS integrated, -1 dBTP true peak.
5. Subtitles (ASS, max 2 lines x ~40 chars, inside the vertical safe area) and the AI end card, burned in.

`--radio` renders the radio cut: the same sound and subtitles over a black screen.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import textwrap
import wave
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from pipeline.core import OUTPUTS, call_model
from pipeline.narration import narration_path, wav_duration_s
from pipeline.storyboard import load_storyboard

STAGE = "assembly"
WORK = OUTPUTS / "assembly"
FILM_DIR = OUTPUTS / "film"
FPS = 24
MIX_RATE = 48_000
# Target -1.5 dBTP, not -1.0: linear loudnorm can overshoot its peak target slightly (the v3 radio cut
# measured -0.88 dBTP when aiming at -1.0), and the platform ceiling is -1.0.
LOUDNESS = {"I": -14.0, "TP": -1.5, "LRA": 11.0}
DUCKING = "sidechaincompress=threshold=0.02:ratio=6:attack=300:release=1500"
RAMP_S = 0.5

# Output size, subtitle size and bottom margin per aspect. The 9:16 margin keeps captions above the
# buttons and caption bar that phone apps draw over the bottom of a vertical video.
ASPECTS = {
    "9x16": {"size": (1080, 1920), "font_size": 58, "margin_v": 400, "margin_lr": 90},
    "16x9": {"size": (1920, 1080), "font_size": 52, "margin_v": 70, "margin_lr": 160},
}


@dataclass(frozen=True)
class Slot:
    shot_id: str
    start_s: float
    length_s: float
    voice_start_s: float
    voice_len_s: float
    subtitle: str


def ffmpeg_binary() -> str:
    found = os.environ.get("FFMPEG") or shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("FFmpeg not found. Install it (https://ffmpeg.org/download.html) or set FFMPEG=<path>.")
    return found


def run_ffmpeg(args: list[str], *, step: str, cwd: Path | None = None) -> str:
    """Run FFmpeg, log its latency as an assembly step, and return stderr (where FFmpeg reports)."""

    def invoke() -> str:
        done = subprocess.run(  # check=False: we raise our own error that includes FFmpeg's stderr
            [ffmpeg_binary(), "-hide_banner", "-y", *args],
            cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if done.returncode != 0:
            raise RuntimeError(f"ffmpeg {step} failed:\n{done.stderr[-2000:]}")
        return done.stderr

    return call_model(invoke, stage=STAGE, model="ffmpeg", params={"step": step}, attempts=1)


def build_timeline(storyboard: dict[str, Any], voice: dict[str, Path]) -> list[Slot]:
    lead, tail = storyboard["narration"]["lead_in_s"], storyboard["narration"]["tail_s"]
    slots, t = [], 0.0
    for shot in storyboard["shots"]:
        voice_len = wav_duration_s(voice[shot["id"]])
        length = round(max(shot["duration_s"], lead + voice_len + tail), 3)
        slots.append(Slot(shot["id"], t, length, t + lead, voice_len, shot["narration"]["en"]))
        t = round(t + length, 3)
    return slots


def build_voice_track(slots: list[Slot], voice: dict[str, Path], total_s: float, out: Path) -> None:
    """Place each narration file at its slot's start, in silence, as one mono track."""
    rate = None
    track = bytearray()
    for slot in slots:
        with wave.open(str(voice[slot.shot_id]), "rb") as wav:
            if rate is None:
                rate = wav.getframerate()
                track = bytearray(int(total_s * rate) * 2)
            if wav.getframerate() != rate or wav.getsampwidth() != 2 or wav.getnchannels() != 1:
                raise ValueError(f"{slot.shot_id}: narration must be 16-bit mono at {rate} Hz")
            pcm = wav.readframes(wav.getnframes())
        offset = int(slot.voice_start_s * rate) * 2
        track[offset : offset + len(pcm)] = pcm
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(bytes(track[: int(total_s * rate) * 2]))


def music_levels(storyboard: dict[str, Any]) -> dict[str, float]:
    order = [s["id"] for s in storyboard["shots"]]
    levels = {shot_id: 1.0 for shot_id in order}
    for cue in storyboard["music"]["cues"]:
        start, end = order.index(cue["from_shot"]), order.index(cue["to_shot"])
        for shot_id in order[start : end + 1]:
            levels[shot_id] = cue["level"]
    return levels


def envelope_points(slots: list[Slot], levels: dict[str, float], total_s: float) -> list[tuple[float, float]]:
    """Gain over time: fade in, short ramps where a cue changes level, fade out across the end card."""
    first = levels[slots[0].shot_id]
    points = [(0.0, 0.0), (1.0, first)]
    for prev, nxt in pairwise(slots):
        a, b = levels[prev.shot_id], levels[nxt.shot_id]
        if a != b:
            points += [(nxt.start_s - RAMP_S / 2, a), (nxt.start_s + RAMP_S / 2, b)]
    film_end = slots[-1].start_s + slots[-1].length_s
    points += [(film_end, levels[slots[-1].shot_id]), (total_s, 0.0)]
    return points


def envelope_expr(points: list[tuple[float, float]]) -> str:
    """Piecewise-linear FFmpeg expression of t through the given (time, gain) points."""
    expr = f"{points[-1][1]:.3f}"
    for (t0, g0), (t1, g1) in reversed(list(pairwise(points))):
        if t1 <= t0:
            continue
        segment = f"{g0:.3f}+({g1 - g0:.3f})*(t-{t0:.3f})/{t1 - t0:.3f}"
        expr = f"if(lt(t,{t1:.3f}),{segment},{expr})"
    return expr


def placeholder_music(total_s: float, out: Path) -> None:
    """Temp track for the radio cut: a soft, slowly breathing A-major drone."""
    source = (
        "aevalsrc='(0.10*sin(2*PI*220*t)+0.07*sin(2*PI*277.18*t)+0.06*sin(2*PI*329.63*t))"
        f"*(0.65+0.35*sin(2*PI*0.2*t))':s={MIX_RATE}:d={total_s:.3f}"
    )
    run_ffmpeg(["-f", "lavfi", "-i", source, "-ac", "2", str(out)], step="placeholder_music")


def mix(voice_wav: Path, music: Path, envelope: str, total_s: float, out: Path) -> None:
    graph = (
        f"[0:a]aresample={MIX_RATE},aformat=channel_layouts=stereo,"
        f"loudnorm=I=-16:TP=-2:LRA=11,aresample={MIX_RATE},asplit=2[voice][key];"
        f"[1:a]aresample={MIX_RATE},aformat=channel_layouts=stereo,apad,atrim=0:{total_s:.3f},"
        f"loudnorm=I=-26:TP=-2:LRA=11,aresample={MIX_RATE},volume='{envelope}':eval=frame[music];"
        f"[music][key]{DUCKING}[ducked];"
        "[voice][ducked]amix=inputs=2:normalize=0:duration=first[mix]"
    )
    run_ffmpeg(
        ["-i", str(voice_wav), "-i", str(music), "-filter_complex", graph, "-map", "[mix]", str(out)],
        step="mix_and_duck",
    )


def loudness_report(stderr: str) -> dict[str, str]:
    return json.loads(stderr[stderr.rindex("{") : stderr.rindex("}") + 1])


def master(mix_wav: Path, out: Path) -> dict[str, str]:
    """Two-pass loudnorm: measure first, then normalise linearly with the measured values."""
    target = f"I={LOUDNESS['I']}:TP={LOUDNESS['TP']}:LRA={LOUDNESS['LRA']}"
    measured = loudness_report(
        run_ffmpeg(["-i", str(mix_wav), "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                   step="loudnorm_pass1")
    )
    second = (
        f"loudnorm={target}:measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true:print_format=json,aresample={MIX_RATE}"
    )
    run_ffmpeg(["-i", str(mix_wav), "-af", second, str(out)], step="loudnorm_pass2")
    check = loudness_report(
        run_ffmpeg(["-i", str(out), "-af", f"loudnorm={target}:print_format=json", "-f", "null", "-"],
                   step="loudness_check")
    )
    return {"integrated_lufs": check["input_i"], "true_peak_dbtp": check["input_tp"]}


def subtitle_events(text: str, max_chars: int = 40, max_lines: int = 2) -> list[list[str]]:
    """Split a line into on-screen events of at most `max_lines` lines of about `max_chars` characters."""
    events: list[list[str]] = []
    for sentence in re.split(r"(?<=[.!?…])\s+", text.strip()):
        lines = textwrap.wrap(sentence, width=max_chars)
        events += [lines[i : i + max_lines] for i in range(0, len(lines), max_lines)]
    return events


def ass_time(seconds: float) -> str:
    centis = round(seconds * 100)
    h, rem = divmod(centis, 360_000)
    m, rem = divmod(rem, 6_000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    """ASS treats {...} as style overrides and backslash as a command prefix; keep narration literal."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")")


def write_subtitles(slots: list[Slot], end_card: dict[str, Any], total_s: float, aspect: str, out: Path) -> None:
    spec = ASPECTS[aspect]
    width, height = spec["size"]
    header = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Sub,Arial,{spec['font_size']},&H00FFFFFF,&H000000FF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,3,1,"
        f"2,{spec['margin_lr']},{spec['margin_lr']},{spec['margin_v']},1\n"
        f"Style: Card,Arial,{spec['font_size']},&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,"
        f"5,{spec['margin_lr']},{spec['margin_lr']},0,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    lines = []
    for slot in slots:
        events = subtitle_events(slot.subtitle)
        weights = [sum(len(line) for line in event) for event in events]
        shown_until = min(slot.voice_start_s + slot.voice_len_s + 0.3, slot.start_s + slot.length_s)
        t, span = slot.voice_start_s, shown_until - slot.voice_start_s
        for event, weight in zip(events, weights):
            end = t + span * weight / sum(weights)
            text = "\\N".join(ass_escape(line) for line in event)
            lines.append(f"Dialogue: 0,{ass_time(t)},{ass_time(end)},Sub,,0,0,0,,{text}")
            t = end
    card_start = total_s - end_card["duration_s"]
    first, *rest = end_card["lines"]
    card = f"{{\\fs{int(spec['font_size'] * 1.6)}\\b1}}{ass_escape(first)}{{\\fs{int(spec['font_size'] * 0.7)}\\b0}}"
    card += "".join(f"\\N\\N{ass_escape(line)}" for line in rest)
    lines.append(f"Dialogue: 1,{ass_time(card_start)},{ass_time(total_s)},Card,,0,0,0,,{card}")
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")


def write_srt(slots: list[Slot], out: Path) -> None:
    """Plain subtitle file to upload as captions on platforms that accept them."""
    def stamp(sec: float) -> str:
        ms = round(sec * 1000)
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    blocks = [
        f"{i}\n{stamp(slot.voice_start_s)} --> {stamp(slot.voice_start_s + slot.voice_len_s + 0.3)}\n{slot.subtitle}\n"
        for i, slot in enumerate(slots, start=1)
    ]
    out.write_text("\n".join(blocks), encoding="utf-8")


def render_radio(aspect: str, total_s: float, audio: Path, subs: Path, out: Path) -> None:
    width, height = ASPECTS[aspect]["size"]
    run_ffmpeg(
        [
            "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:r={FPS}:d={total_s:.3f}",
            "-i", str(audio),
            "-vf", f"subtitles={subs.name}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "192k", "-ar", str(MIX_RATE),
            "-shortest", "-movflags", "+faststart", str(out),
        ],
        step=f"render_radio_{aspect}",
        cwd=subs.parent,  # the subtitles filter gets a bare file name, avoiding Windows path escaping
    )


def run(storyboard: dict[str, Any], *, radio: bool, aspects: list[str]) -> list[Path]:
    lang = storyboard["language"]
    voice = {s["id"]: narration_path(storyboard, s, lang) for s in storyboard["shots"]}
    missing = [shot_id for shot_id, path in voice.items() if not path.exists()]
    if missing:
        raise RuntimeError(f"narration missing for {missing}; run the narration stage first")
    if not radio:
        raise NotImplementedError("picture assembly lands with the keyframes and shots stages; use --radio")

    work = WORK / "radio"
    work.mkdir(parents=True, exist_ok=True)
    FILM_DIR.mkdir(parents=True, exist_ok=True)

    slots = build_timeline(storyboard, voice)
    total_s = round(slots[-1].start_s + slots[-1].length_s + storyboard["end_card"]["duration_s"], 3)
    build_voice_track(slots, voice, total_s, work / "voice.wav")
    placeholder_music(total_s, work / "music.wav")
    envelope = envelope_expr(envelope_points(slots, music_levels(storyboard), total_s))
    mix(work / "voice.wav", work / "music.wav", envelope, total_s, work / "mix.wav")
    loudness = master(work / "mix.wav", work / "master.wav")
    write_srt(slots, FILM_DIR / "subtitles_en.srt")

    outputs = []
    for aspect in aspects:
        subs = work / f"subs_{aspect}.ass"
        write_subtitles(slots, storyboard["end_card"], total_s, aspect, subs)
        out = FILM_DIR / f"radio_cut_{aspect}.mp4"
        render_radio(aspect, total_s, work / "master.wav", subs, out)
        outputs.append(out)

    (work / "timeline.json").write_text(
        json.dumps({"total_s": total_s, "loudness": loudness, "slots": [s.__dict__ for s in slots]},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    verdict = "OK" if 60 <= total_s <= 90 else "OUTSIDE 60-90s"
    print(f"assembly: {total_s:.1f}s ({verdict}), loudness {loudness['integrated_lufs']} LUFS, "
          f"true peak {loudness['true_peak_dbtp']} dBTP")
    for out in outputs:
        print(f"  wrote {out.relative_to(OUTPUTS.parent).as_posix()}")
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble the film (or the radio cut) from the storyboard.")
    parser.add_argument("--radio", action="store_true", help="narration + placeholder music on black")
    parser.add_argument("--aspect", choices=[*ASPECTS, "both"], default="both")
    args = parser.parse_args()
    aspects = list(ASPECTS) if args.aspect == "both" else [args.aspect]
    run(load_storyboard(), radio=args.radio, aspects=aspects)


if __name__ == "__main__":
    main()
