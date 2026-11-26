"""Smoke test: call each provider once, log every call to runs.jsonl, and report what works.

Run it first on a new machine or key: `uv run smoke`. It also lists the TTS models this key can see,
so the model ids in storyboard.json are checked against reality, not memory.
"""

from __future__ import annotations

import base64
import sys
from collections.abc import Callable

import requests

from pipeline import narration
from pipeline.core import OUTPUTS, call_model, redact, require_env
from pipeline.storyboard import load_storyboard

SMOKE_DIR = OUTPUTS / "smoke"
AMHARIC_SAMPLE = "ልጅ እያለሁ፣ አያቴ አንድ ረጅም የግድግዳ መጥረጊያ ገዛች።"


def gemini_models(client) -> str:
    names = [m.name.removeprefix("models/") for m in client.models.list()]
    tts = sorted(n for n in names if "tts" in n)
    flash = sorted(n for n in names if "flash" in n and "tts" not in n and "image" not in n)
    print("  TTS models visible to this key:", ", ".join(tts) or "none")
    print("  Flash text models:", ", ".join(flash[:12]) or "none")
    return f"{len(tts)} TTS models, {len(flash)} flash models"


def gemini_text(client, model: str) -> str:
    reply = call_model(
        lambda: client.models.generate_content(model=model, contents="Reply with the single word: ready"),
        stage="smoke", model=model, params={"prompt": "Reply with the single word: ready"},
        describe=lambda r: {"usage": {"input_tokens": r.usage_metadata.prompt_token_count,
                                      "output_tokens": r.usage_metadata.candidates_token_count}},
        attempts=2,
    )
    return f"replied {reply.text.strip()!r}"


def gemini_tts(client, model: str, voice: str, style: str) -> str:
    wav_bytes, _ = call_model(
        lambda: narration.synthesize(client, model, voice, style, AMHARIC_SAMPLE),
        stage="smoke", model=model, params={"voice": voice, "lang": "am", "chars": len(AMHARIC_SAMPLE)},
        output="outputs/smoke/tts_am.wav", describe=narration.usage_fields, attempts=2,
    )
    path = SMOKE_DIR / "tts_am.wav"
    narration.save_atomically(path, wav_bytes)
    return f"{narration.wav_duration_s(path):.2f}s of Amharic audio -> {path.relative_to(OUTPUTS.parent).as_posix()}"


def cloudflare_image(model: str) -> str:
    account = require_env("CLOUDFLARE_ACCOUNT_ID")
    token = require_env("CLOUDFLARE_API_TOKEN")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"
    body = {"prompt": "a long red broom leaning on a whitewashed wall, gouache illustration", "steps": 4, "seed": 7}

    def post() -> bytes:
        response = requests.post(url, headers={"Authorization": f"Bearer {token}"}, json=body, timeout=120)
        response.raise_for_status()
        return base64.b64decode(response.json()["result"]["image"])

    image = call_model(post, stage="smoke", model=model, params={"steps": 4}, seed=7,
                       output="outputs/smoke/flux.jpg", attempts=2)
    path = SMOKE_DIR / "flux.jpg"
    path.write_bytes(image)
    return f"{len(image) // 1024} KB image -> {path.relative_to(OUTPUTS.parent).as_posix()}"


def main() -> None:
    storyboard = load_storyboard()
    models = storyboard["models"]
    SMOKE_DIR.mkdir(parents=True, exist_ok=True)
    client = narration.make_client()

    checks: list[tuple[str, Callable[[], str]]] = [
        ("gemini: list models", lambda: gemini_models(client)),
        (f"gemini text: {models['text']}", lambda: gemini_text(client, models["text"])),
        (f"gemini tts: {models['tts']}",
         lambda: gemini_tts(client, models["tts"], storyboard["narration"]["voice"], storyboard["narration"]["style"])),
        (f"cloudflare: {models['image']}", lambda: cloudflare_image(models["image"])),
    ]
    failures = 0
    for name, check in checks:
        print(f"- {name}")
        try:
            print(f"  OK   {check()}")
        except Exception as err:  # noqa: BLE001 - report every provider, not just the first failure
            failures += 1
            print(f"  FAIL {type(err).__name__}: {redact(str(err))[:300]}")
    print(f"\nsmoke test: {len(checks) - failures}/{len(checks)} passed (details in runs.jsonl)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
