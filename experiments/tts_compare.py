"""Experiment: the same narration lines through several TTS providers and voices, for listening tests.

Hypothesis: a provider with native Amharic voices (Addis AI) sounds more natural to Amharic speakers
than Gemini TTS, whose Amharic a native speaker judged "not natural" in the smoke test.

Usage:
    uv run python experiments/tts_compare.py --shots s02 s04 \
        --voices addis:am-hamen addis:am-meron gemini:Sulafat

Writes outputs/experiments/tts_compare/<shot>/<provider>-<voice>.wav and logs every call to runs.jsonl
(stage "experiment"). --blind also writes shuffled copies named A, B, C... plus a separate answer key,
for a blind preference test with listeners.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
from functools import partial

from pipeline import narration
from pipeline.core import OUTPUTS, call_model, input_hash
from pipeline.storyboard import load_storyboard

OUT = OUTPUTS / "experiments" / "tts_compare"
ADDIS_MODEL = "addis-voices-2"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--shots", nargs="+", required=True)
    parser.add_argument("--voices", nargs="+", required=True, help="provider:voice, e.g. addis:am-hamen")
    parser.add_argument("--style", help="Gemini style instruction (default: storyboard narration.style)")
    parser.add_argument("--blind", action="store_true", help="also write shuffled A/B/C copies and a key")
    args = parser.parse_args()

    board = load_storyboard()
    lang = board["language"]
    style = args.style or board["narration"]["style"]
    shots = {s["id"]: s for s in board["shots"]}
    gemini = None

    for shot_id in args.shots:
        text = shots[shot_id]["narration"][lang]
        made = []
        for spec in args.voices:
            provider, voice = spec.split(":", 1)
            model = ADDIS_MODEL if provider == "addis" else board["models"]["tts"]
            path = OUT / shot_id / f"{provider}-{voice}.wav"
            inputs = {"text": text, "model": model, "voice": voice, "style": style, "lang": lang}
            if not path.exists():
                if provider == "gemini":
                    gemini = gemini or narration.make_client()
                wav, _ = call_model(
                    partial(narration.synthesize_line, model, voice, style, text, lang, input_hash(inputs), gemini),
                    stage="experiment", shot=shot_id, model=model,
                    params={"experiment": "tts_compare", "voice": voice, "style": style if provider == "gemini" else None},
                    output=path.relative_to(OUTPUTS.parent).as_posix(), describe=narration.usage_fields,
                )
                narration.save_atomically(path, wav)
            made.append(path)
            print(f"  {shot_id} {provider:6} {voice:16} {narration.wav_duration_s(path):5.2f}s")

        if args.blind:
            shuffled = random.sample(made, len(made))
            key = {}
            for label, path in zip("ABCDEFGHIJKL", shuffled):
                shutil.copyfile(path, OUT / shot_id / f"blind-{label}.wav")
                key[label] = path.stem
            (OUT / shot_id / "blind_key.json").write_text(json.dumps(key, indent=2), encoding="utf-8")
            print(f"  {shot_id}: blind copies A-{chr(64 + len(made))} written; key in blind_key.json")


if __name__ == "__main__":
    main()
