"""Stage: narration. Gemini TTS, one request per batch of shots, split into outputs/narration/<lang>/<shot>-<hash>.wav.

Batches (storyboard narration.batches, e.g. one per scene) exist because the free tier allows only 10 TTS
requests a day for 12 lines (FAILURES.md F7). A batch is read as one continuous take, which also gives
more natural intonation across lines, then split at its longest pauses. The raw take is cached too, so a
bad split can be redone without spending another request.

Every file name holds a hash of the inputs that affect it (all lines of its batch, model, voice, style):
changing one line regenerates only that line's batch, with exactly one new request.
"""

from __future__ import annotations

import argparse
import base64
import io
import math
import wave
from array import array
from functools import partial
from itertools import pairwise
from pathlib import Path
from typing import Any

import requests

from pipeline.core import OUTPUTS, RetryableError, call_model, input_hash, require_env
from pipeline.storyboard import load_storyboard

STAGE = "narration"
PCM_RATE = 24_000  # Gemini TTS audio: 24 kHz, mono, 16-bit
REQUEST_TIMEOUT_MS = 120_000  # client-side HTTP timeout; not honoured on every SDK path, hence the deadline
CALL_DEADLINE_S = 90  # hard limit per attempt; the slowest successful TTS call so far took 53 s
# Paid list prices for gemini-3.8-flash-tts (USD per 1M tokens), read 2026-11-26 from
# https://aistudio.google.com/docs/pricing. We use the free tier; this is the "list-price equivalent".
PRICE_TEXT_IN, PRICE_AUDIO_OUT, AUDIO_TOKENS_PER_S = 0.50, 9.00, 25
# Addis AI, an Ethiopian provider with native Amharic voices: 5 ETB per generated minute, read 2026-11-26
# from https://docs.addisassistant.com/docs/platform/pricing (signup includes free credit).
ADDIS_URL = "https://api.addisassistant.com/api/v1/voice/generations"
ADDIS_ETB_PER_MIN = 5

# Splitting a batch take back into lines
BATCH_PAUSE_STYLE = "Leave a clear pause of about two seconds between paragraphs."
FRAME_S = 0.02  # loudness is measured per 20 ms frame
SILENCE_RATIO = 0.06  # a frame is silent below 6 % of loud-speech level (about -24 dB)
MIN_PAUSE_S = 0.2  # a real line break was once only 0.26 s, shorter than a mid-line pause (EXPERIMENTS.md E4)
PAUSE_LENGTH_WEIGHT = 0.5  # when snapping a line break, each frame of pause length counts as half a frame of distance
EDGE_PAD_S = 0.06  # silence kept around each line after trimming
MAX_SHARE_RATIO = 2.0  # a line's share of audio vs its share of text may differ by at most this factor


class SplitError(ValueError):
    """A batch take could not be split into its lines with confidence; the raw take is kept for inspection."""


def batches(storyboard: dict[str, Any]) -> list[list[str]]:
    shot_ids = [s["id"] for s in storyboard["shots"]]
    return storyboard["narration"].get("batches") or [[shot_id] for shot_id in shot_ids]


def batch_inputs(storyboard: dict[str, Any], batch: list[str], lang: str) -> dict[str, Any]:
    by_id = {s["id"]: s for s in storyboard["shots"]}
    return {
        "lines": [[shot_id, by_id[shot_id]["narration"][lang]] for shot_id in batch],
        "lang": lang,
        "model": storyboard["models"]["tts"],
        "voice": storyboard["narration"]["voice"],
        "style": storyboard["narration"]["style"],
    }


def narration_inputs(storyboard: dict[str, Any], shot: dict[str, Any], lang: str) -> dict[str, Any]:
    """Everything that affects one shot's audio. Its whole batch is read in one take, so all of it counts."""
    batch = next(b for b in batches(storyboard) if shot["id"] in b)
    return {**batch_inputs(storyboard, batch, lang), "shot": shot["id"]}


def narration_path(storyboard: dict[str, Any], shot: dict[str, Any], lang: str) -> Path:
    key = input_hash(narration_inputs(storyboard, shot, lang))
    return OUTPUTS / STAGE / lang / f"{shot['id']}-{key}.wav"


def take_path(batch: list[str], inputs: dict[str, Any]) -> Path:
    return OUTPUTS / STAGE / inputs["lang"] / "takes" / f"{batch[0]}-{batch[-1]}-{input_hash(inputs)}.wav"


def _frame_levels(samples: array, frame: int) -> list[float]:
    return [
        math.sqrt(sum(s * s for s in samples[i : i + frame]) / frame)
        for i in range(0, len(samples) - frame + 1, frame)
    ]


def split_take(wav_bytes: bytes, texts: list[str]) -> list[bytes]:
    """Split one take into len(texts) lines at its longest interior pauses, then check the result.

    The check compares each line's share of the audio with its share of the text: a cut in the wrong
    place makes one line far too long and its neighbour far too short, so SplitError is raised instead
    of silently writing mismatched audio.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1:
            raise SplitError("expected 16-bit mono audio")
        rate = wav.getframerate()
        samples = array("h", wav.readframes(wav.getnframes()))
    frame = int(rate * FRAME_S)
    levels = _frame_levels(samples, frame)
    loud = sorted(levels)[int(len(levels) * 0.95)] if levels else 0.0
    silent = [level < loud * SILENCE_RATIO for level in levels]

    pauses, start = [], None  # (first silent frame, frame after the run)
    for i, is_silent in enumerate([*silent, False]):
        if is_silent and start is None:
            start = i
        elif not is_silent and start is not None:
            if start > 0 and i < len(silent) and (i - start) * FRAME_S >= MIN_PAUSE_S:
                pauses.append((start, i))
            start = None
    needed = len(texts) - 1
    if len(pauses) < needed:
        raise SplitError(f"found {len(pauses)} pauses, need {needed}")

    # The model does not lengthen the pauses between lines (EXPERIMENTS.md E4), so the longest pauses
    # are not reliably the line breaks. Instead, estimate each break from the text (a line's share of the
    # characters ~ its share of the time) and snap to the nearest real pause, preferring longer ones.
    total_chars = sum(len(t) for t in texts)
    chosen: list[tuple[int, int]] = []
    for k in range(1, len(texts)):
        expected = len(silent) * sum(len(t) for t in texts[:k]) / total_chars
        later = [p for p in pauses if not chosen or p[0] > chosen[-1][1]]
        if len(later) < len(texts) - k:
            raise SplitError(f"not enough pauses left for line {k + 1}")
        chosen.append(min(later[: len(later) - (len(texts) - k - 1)],
                          key=lambda p: abs((p[0] + p[1]) / 2 - expected) - (p[1] - p[0]) * PAUSE_LENGTH_WEIGHT))
    bounds = [0, *[(a + b) // 2 for a, b in chosen], len(silent)]

    pad = int(EDGE_PAD_S / FRAME_S)
    pieces = []
    for lo, hi in pairwise(bounds):
        voiced = [i for i in range(lo, hi) if not silent[i]]
        if not voiced:
            raise SplitError("a line came out silent")
        first, last = max(lo, voiced[0] - pad), min(hi, voiced[-1] + 1 + pad)
        pieces.append(samples[first * frame : last * frame])

    audio = [len(p) for p in pieces]
    for text, length in zip(texts, audio):
        ratio = (length / sum(audio)) / (len(text) / sum(len(t) for t in texts))
        if not 1 / MAX_SHARE_RATIO <= ratio <= MAX_SHARE_RATIO:
            durations = ", ".join(f"{n / rate:.1f}s" for n in audio)
            raise SplitError(f"line lengths look wrong ({durations}) for texts of {[len(t) for t in texts]} chars")
    return [pcm_to_wav(p.tobytes(), rate) for p in pieces]


def wav_duration_s(source: Path | bytes) -> float:
    handle = io.BytesIO(source) if isinstance(source, bytes) else str(source)
    with wave.open(handle, "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def pcm_to_wav(pcm: bytes, rate: int = PCM_RATE) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def save_atomically(path: Path, data: bytes) -> None:
    """Write to a temporary name first, so an interrupted run never leaves a half file that looks cached."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    partial.replace(path)


def make_client() -> Any:
    from google import genai

    client = genai.Client(
        api_key=require_env("GEMINI_API_KEY"),
        # attempts=1 turns off the SDK's own silent retries: a quota error must surface immediately in
        # call_model(), which logs every attempt (FAILURES.md F7).
        http_options={"api_version": "v1beta", "timeout": REQUEST_TIMEOUT_MS, "retry_options": {"attempts": 1}},
    )
    # Touching .interactions imports a large SDK sub-package (20-26 s on the 2-core dev laptop). Doing it
    # here, before any call is timed, keeps that import out of the latency logged in runs.jsonl.
    _ = client.interactions
    return client


def synthesize(client: Any, model: str, voice: str, style: str, text: str) -> tuple[bytes, Any]:
    """One TTS call through the Interactions API (used by Gemini 3.8 TTS). Returns (wav bytes, usage)."""
    interaction = client.interactions.create(
        model=model,
        input=[{
            "type": "user_input",
            "content": [{"type": "text", "text": text,
                         "annotations": [{"type": "speech_metadata", "style": style}]}],
        }],
        response_format={"type": "audio"},
        generation_config={"speech_config": [{"voice": voice}]},
    )
    data = getattr(getattr(interaction, "output_audio", None), "data", None)
    if not data:
        raise RetryableError("TTS reply contained no audio")
    if isinstance(data, str):
        data = base64.b64decode(data)
    if not data.startswith(b"RIFF"):  # headerless PCM (streaming-style reply): wrap it ourselves
        data = pcm_to_wav(data)
    return data, getattr(interaction, "usage", None)


def synthesize_addis(voice: str, text: str, lang: str, request_id: str) -> tuple[bytes, Any]:
    """One Addis AI ("Addis Voices 2") call. The reply holds a signed link to the audio, which we download.

    request_id is the input hash: if a retry repeats a request the server already handled, Addis treats
    it as the same request (idempotency key) and does not bill it twice.
    """
    reply = requests.post(
        ADDIS_URL,
        headers={"x-api-key": require_env("ADDIS_API_KEY")},
        json={"text": text, "voice_id": voice, "language": lang, "output_format": "wav_44100",
              "client_request_id": request_id},
        timeout=120,
    )
    reply.raise_for_status()
    data = reply.json().get("data") or {}
    if not data.get("audio_url"):
        raise RetryableError(f"Addis reply had no audio_url: {str(data)[:200]}")
    audio = requests.get(data["audio_url"], timeout=120)
    audio.raise_for_status()
    return audio.content, {k: v for k, v in data.items() if k != "audio_url"}


def usage_fields(result: tuple[bytes, Any]) -> dict[str, Any]:
    wav_bytes, usage = result
    audio_s = wav_duration_s(wav_bytes)
    if isinstance(usage, dict):  # Addis: billed per generated minute
        return {"audio_s": round(audio_s, 3), "usage": usage,
                "list_price_etb": round(audio_s / 60 * ADDIS_ETB_PER_MIN, 4)}
    usage_dict = usage.model_dump(exclude_none=True) if hasattr(usage, "model_dump") else None
    usage_dict = usage_dict or {}
    input_tokens = next(
        (usage_dict[k] for k in ("total_input_tokens", "initial_input_tokens", "input_tokens") if usage_dict.get(k)), 0
    )
    list_price = (input_tokens * PRICE_TEXT_IN + audio_s * AUDIO_TOKENS_PER_S * PRICE_AUDIO_OUT) / 1e6
    return {"audio_s": round(audio_s, 3), "usage": usage_dict, "list_price_usd": round(list_price, 6)}


def synthesize_line(model: str, voice: str, style: str, text: str, lang: str, request_id: str,
                    gemini_client: Any = None) -> tuple[bytes, Any]:
    """Route one line to its provider, chosen by the model id in storyboard.json."""
    if model.startswith("addis"):
        return synthesize_addis(voice, text, lang, request_id)  # Addis accepts no style prompt
    return synthesize(gemini_client or make_client(), model, voice, style, text)


def record_take(batch: list[str], inputs: dict[str, Any], client: Any) -> Path:
    """One TTS request for a whole batch; the raw take is cached so splitting can be redone for free."""
    path = take_path(batch, inputs)
    if path.exists():
        return path
    texts = [text for _, text in inputs["lines"]]
    style = inputs["style"] if len(batch) == 1 else f"{inputs['style']}. {BATCH_PAUSE_STYLE}"
    joined = "\n\n".join(texts)
    wav_bytes, _ = call_model(
        partial(synthesize_line, inputs["model"], inputs["voice"], style, joined, inputs["lang"],
                input_hash(inputs), client),
        stage=STAGE,
        shot="-".join([batch[0], batch[-1]]) if len(batch) > 1 else batch[0],
        model=inputs["model"],
        params={"voice": inputs["voice"], "style": style, "lang": inputs["lang"], "lines": len(batch),
                "chars": len(joined)},
        output=path.relative_to(OUTPUTS.parent).as_posix(),
        describe=usage_fields,
        deadline_s=CALL_DEADLINE_S,
    )
    save_atomically(path, wav_bytes)
    return path


def run(storyboard: dict[str, Any], lang: str | None = None, only: set[str] | None = None) -> dict[str, Path]:
    """Make sure every shot has its narration file; return {shot_id: wav path}."""
    lang = lang or storyboard["language"]
    by_id = {s["id"]: s for s in storyboard["shots"]}
    client = None
    paths: dict[str, Path] = {}
    requests_made = reused = 0
    for batch in batches(storyboard):
        shot_paths = {shot_id: narration_path(storyboard, by_id[shot_id], lang) for shot_id in batch}
        paths.update(shot_paths)
        if all(p.exists() for p in shot_paths.values()):
            reused += len(batch)
            continue
        if only and not only & set(batch):
            continue
        inputs = batch_inputs(storyboard, batch, lang)
        if not take_path(batch, inputs).exists():
            if not inputs["model"].startswith("addis"):
                client = client or make_client()
            requests_made += 1
        take = record_take(batch, inputs, client)
        lines = split_take(take.read_bytes(), [text for _, text in inputs["lines"]])
        for shot_id, wav_bytes in zip(batch, lines):
            save_atomically(shot_paths[shot_id], wav_bytes)
            print(f"  narration {shot_id}: new  {wav_duration_s(wav_bytes):5.2f}s  {shot_paths[shot_id].name}")
    print(f"narration: {requests_made} TTS request(s), {reused} line(s) reused from cache")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one narration file per shot (cached).")
    parser.add_argument("--lang", help="narration language code (default: storyboard.language)")
    parser.add_argument("--only", nargs="*", help="limit to these shot ids, e.g. s03 s07")
    args = parser.parse_args()
    run(load_storyboard(), args.lang, set(args.only) if args.only else None)


if __name__ == "__main__":
    main()
