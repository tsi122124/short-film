"""Stage: narration. One Gemini TTS call per shot, written to outputs/narration/<lang>/<shot>-<hash>.wav.

The file name contains a hash of every input that affects the audio (text, model, voice, style), so
changing one shot's line changes only that shot's hash, and a re-run makes exactly one new call.
"""

from __future__ import annotations

import argparse
import base64
import io
import wave
from functools import partial
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


def narration_inputs(storyboard: dict[str, Any], shot: dict[str, Any], lang: str) -> dict[str, Any]:
    return {
        "text": shot["narration"][lang],
        "lang": lang,
        "model": storyboard["models"]["tts"],
        "voice": storyboard["narration"]["voice"],
        "style": storyboard["narration"]["style"],
    }


def narration_path(storyboard: dict[str, Any], shot: dict[str, Any], lang: str) -> Path:
    key = input_hash(narration_inputs(storyboard, shot, lang))
    return OUTPUTS / STAGE / lang / f"{shot['id']}-{key}.wav"


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
        http_options={"api_version": "v1beta", "timeout": REQUEST_TIMEOUT_MS},
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


def run(storyboard: dict[str, Any], lang: str | None = None, only: set[str] | None = None) -> dict[str, Path]:
    """Make sure every shot has its narration file; return {shot_id: wav path}."""
    lang = lang or storyboard["language"]
    settings = storyboard["narration"]
    model = storyboard["models"]["tts"]
    client = None
    paths: dict[str, Path] = {}
    made = reused = 0
    for shot in storyboard["shots"]:
        path = narration_path(storyboard, shot, lang)
        paths[shot["id"]] = path
        if path.exists():
            reused += 1
            continue
        if only and shot["id"] not in only:
            continue
        if not model.startswith("addis"):
            client = client or make_client()
        text = shot["narration"][lang]
        request_id = input_hash(narration_inputs(storyboard, shot, lang))
        wav_bytes, _ = call_model(
            partial(synthesize_line, model, settings["voice"], settings["style"], text, lang, request_id, client),
            stage=STAGE,
            shot=shot["id"],
            model=model,
            params={"voice": settings["voice"], "style": settings["style"], "lang": lang, "chars": len(text)},
            output=path.relative_to(OUTPUTS.parent).as_posix(),
            describe=usage_fields,
            deadline_s=CALL_DEADLINE_S,
        )
        save_atomically(path, wav_bytes)
        made += 1
        print(f"  narration {shot['id']}: new  {wav_duration_s(path):5.2f}s  {path.name}")
    print(f"narration: {made} generated, {reused} reused from cache")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate one narration file per shot (cached).")
    parser.add_argument("--lang", help="narration language code (default: storyboard.language)")
    parser.add_argument("--only", nargs="*", help="limit to these shot ids, e.g. s03 s07")
    args = parser.parse_args()
    run(load_storyboard(), args.lang, set(args.only) if args.only else None)


if __name__ == "__main__":
    main()
