"""Stage: keyframes. A reference sheet first, then one keyframe per shot conditioned on it.

Model: FLUX.2 klein 4B on Cloudflare Workers AI (Apache-2.0).

1. `refs`: every character and the sweeper get candidate reference images from a few seeds, plus a
   contact sheet to compare them. The chosen seed is written into storyboard.json (`reference.seed`):
   that image becomes the golden reference.
2. `shots`: each keyframe is generated with the golden references of everyone and everything in the
   shot attached as input images (klein accepts up to 4), so faces, clothes and the broom stay the same.

Caching: file names hold a hash of prompt, model, size, seed and the references used. Editing one
shot's prompt regenerates only that keyframe; editing a character regenerates its reference and every
keyframe that uses it. The consent gate runs before anything of a real person is generated.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import math
from functools import partial
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw

from pipeline.core import OUTPUTS, ROOT, RetryableError, call_model, input_hash, require_env
from pipeline.storyboard import fill_template, load_storyboard, placeholders, require_consent

REF_DIR = OUTPUTS / "references"
KEY_DIR = OUTPUTS / "keyframes"
REF_SIZE = 1024
REF_INPUT_PX = 496  # Cloudflare: each input image must be smaller than 512 x 512
CANDIDATE_SEEDS = (3101, 3102, 3103, 3104, 3105, 3106)  # tried in order until enough candidates exist
MAX_REFERENCES = 4
CALL_DEADLINE_S = 180
# flux-2-klein-4b pricing, read 2026-11-26 from https://developers.cloudflare.com/workers-ai/platform/pricing/
# (10,000 free neurons a day; we stay on the free allowance, this is the list-price equivalent)
NEURONS_PER_OUTPUT_TILE, NEURONS_PER_INPUT_TILE, USD_PER_1K_NEURONS = 26.05, 5.37, 0.011


def items_with_reference(storyboard: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["id"]: i for i in [*storyboard["characters"], *storyboard["props"]] if "reference" in i}


def base_images(item: dict[str, Any]) -> list[Path]:
    """Approved earlier images this reference is edited from (e.g. image 0 = outfit, image 1 = face)."""
    base = item["reference"].get("base_image") or []
    paths = [ROOT / b for b in ([base] if isinstance(base, str) else base)]
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"{item['id']}: reference.base_image not found: {missing}")
    return paths


def reference_inputs(storyboard: dict[str, Any], item: dict[str, Any], seed: int) -> dict[str, Any]:
    return {
        "prompt": fill_template(storyboard, item["reference"]["prompt"], location=None),
        "model": storyboard["models"]["image"],
        "width": REF_SIZE,
        "height": REF_SIZE,
        "seed": seed,
        # content hashes of the base images, so replacing one regenerates this reference
        "base_image": [file_hash(p) for p in base_images(item)] or None,
    }


def reference_path(storyboard: dict[str, Any], item: dict[str, Any], seed: int) -> Path:
    return REF_DIR / item["id"] / f"{seed}-{input_hash(reference_inputs(storyboard, item, seed))}.png"


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def golden_reference(storyboard: dict[str, Any], item: dict[str, Any]) -> Path:
    """The approved image if one is pinned; otherwise the generated image for the chosen seed."""
    approved = item["reference"].get("approved")
    if approved:
        path = ROOT / approved
        if not path.exists():
            raise FileNotFoundError(f"{item['id']}: reference.approved {approved} does not exist")
        return path
    seed = item["reference"]["seed"]
    if seed is None:
        raise RuntimeError(f"{item['id']}: no reference chosen yet. Run `uv run python -m pipeline.keyframes refs`, "
                           "look at the contact sheet and set reference.seed in storyboard.json")
    return reference_path(storyboard, item, seed)


def shot_references(storyboard: dict[str, Any], shot: dict[str, Any]) -> list[dict[str, Any]]:
    """Characters, then props, of this shot that have a reference image, in a stable order."""
    refs = items_with_reference(storyboard)
    ordered = [refs[c] for c in shot["characters"] if c in refs]
    ordered += [refs[p] for p in sorted(placeholders(shot["image_prompt"])) if p in refs and refs[p] not in ordered]
    if len(ordered) > MAX_REFERENCES:
        raise ValueError(f"{shot['id']}: {len(ordered)} references, the model accepts at most {MAX_REFERENCES}")
    return ordered


def keyframe_prompt(storyboard: dict[str, Any], shot: dict[str, Any], refs: list[dict[str, Any]]) -> str:
    lead = "; ".join(f"{item['label']} looks exactly like the one in image {i}" for i, item in enumerate(refs))
    body = fill_template(storyboard, shot["image_prompt"], shot.get("location", "exterior"))
    return f"{lead}. {body}" if lead else body


def keyframe_inputs(storyboard: dict[str, Any], shot: dict[str, Any]) -> dict[str, Any]:
    refs = shot_references(storyboard, shot)
    return {
        "prompt": keyframe_prompt(storyboard, shot, refs),
        "model": storyboard["models"]["image"],
        "width": storyboard["image"]["width"],
        "height": storyboard["image"]["height"],
        "seed": shot["seed"],
        # content hashes of the golden references, so replacing one regenerates every keyframe that uses it
        "references": [file_hash(golden_reference(storyboard, item)) for item in refs],
    }


def keyframe_path(storyboard: dict[str, Any], shot: dict[str, Any]) -> Path:
    return KEY_DIR / f"{shot['id']}-{input_hash(keyframe_inputs(storyboard, shot))}.png"


def as_reference_input(path: Path) -> bytes:
    with Image.open(path) as img:
        small = img.convert("RGB")
        small.thumbnail((REF_INPUT_PX, REF_INPUT_PX))
        buffer = io.BytesIO()
        small.save(buffer, "PNG")
        return buffer.getvalue()


def to_png(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as img:
        buffer = io.BytesIO()
        img.convert("RGB").save(buffer, "PNG")
        return buffer.getvalue()


def generate_image(model: str, prompt: str, width: int, height: int, seed: int, references: list[bytes]) -> bytes:
    """One FLUX.2 klein call. Klein takes multipart/form-data; references go in input_image_0..3."""
    account, token = require_env("CLOUDFLARE_ACCOUNT_ID"), require_env("CLOUDFLARE_API_TOKEN")
    fields: dict[str, Any] = {
        "prompt": (None, prompt),
        "width": (None, str(width)),
        "height": (None, str(height)),
        "seed": (None, str(seed)),
    }
    for i, ref in enumerate(references):
        fields[f"input_image_{i}"] = (f"reference_{i}.png", ref, "image/png")
    reply = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}",
        headers={"Authorization": f"Bearer {token}"},
        files=fields,
        timeout=150,
    )
    if reply.status_code == 429 and '"code":4006' in reply.text:
        # The daily free allocation is used up: retrying cannot help until it resets (00:00 UTC), so fail fast
        # with an error that carries no HTTP status (the retry policy only retries 429 with a status).
        raise RuntimeError("Cloudflare daily free allocation of 10,000 neurons is used up (code 4006)")
    if not reply.ok:
        raise requests.HTTPError(f"{reply.status_code}: {reply.text[:300]}", response=reply)
    if reply.headers.get("content-type", "").startswith("application/json"):
        body = reply.json()
        encoded = (body.get("result") or {}).get("image") or body.get("image")
        if not encoded:
            raise RetryableError(f"reply contained no image: {str(body)[:200]}")
        return to_png(base64.b64decode(encoded))
    return to_png(reply.content)


def is_flagged(err: Exception) -> bool:
    """Cloudflare's output safety filter (error code 3030), which can fire on innocent images."""
    return "flagged" in str(err) or '"code":3030' in str(err)


def cost_fields(width: int, height: int, n_refs: int) -> dict[str, Any]:
    neurons = math.ceil(width * height / 512**2) * NEURONS_PER_OUTPUT_TILE + n_refs * NEURONS_PER_INPUT_TILE
    return {"neurons_est": round(neurons, 1), "list_price_usd": round(neurons * USD_PER_1K_NEURONS / 1000, 6)}


def make_image(path: Path, inputs: dict[str, Any], refs: list[bytes], stage: str, shot: str) -> None:
    image = call_model(
        partial(generate_image, inputs["model"], inputs["prompt"], inputs["width"], inputs["height"],
                inputs["seed"], refs),
        stage=stage,
        shot=shot,
        model=inputs["model"],
        params={"prompt": inputs["prompt"], "width": inputs["width"], "height": inputs["height"],
                "references": inputs.get("references", [])},
        seed=inputs["seed"],
        output=path.relative_to(OUTPUTS.parent).as_posix(),
        describe=lambda _: cost_fields(inputs["width"], inputs["height"], len(refs)),
        deadline_s=CALL_DEADLINE_S,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = path.with_name(path.name + ".part")
    partial_path.write_bytes(image)
    partial_path.replace(path)


def contact_sheet(paths: list[Path], labels: list[str], out: Path, tile: int = 360) -> None:
    sheet = Image.new("RGB", (tile * len(paths), tile + 36), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (path, label) in enumerate(zip(paths, labels)):
        with Image.open(path) as img:
            sheet.paste(img.convert("RGB").resize((tile, tile)), (i * tile, 0))
        draw.text((i * tile + 10, tile + 10), label, fill="black")
    sheet.save(out)


def run_references(storyboard: dict[str, Any], only: set[str] | None = None,
                   candidates: int = 3) -> None:
    """Golden reference if chosen; otherwise candidates from CANDIDATE_SEEDS plus a contact sheet."""
    made = 0
    for item_id, item in items_with_reference(storyboard).items():
        if only and item_id not in only:
            continue
        if item["reference"].get("approved"):
            print(f"  {item_id}: approved reference {golden_reference(storyboard, item).name}")
            continue
        if item_id in {c["id"] for c in storyboard["characters"]}:
            require_consent(storyboard, [item_id])
        chosen = item["reference"]["seed"]
        seeds = [chosen] if chosen is not None else list(CANDIDATE_SEEDS)
        wanted = 1 if chosen is not None else candidates
        paths, used_seeds = [], []
        base_refs = [as_reference_input(p) for p in base_images(item)]
        for seed in seeds:
            if len(paths) == wanted:
                break
            path = reference_path(storyboard, item, seed)
            if not path.exists():
                try:
                    make_image(path, reference_inputs(storyboard, item, seed), base_refs, "references", item_id)
                except requests.HTTPError as err:
                    if chosen is not None or not is_flagged(err):
                        raise
                    # A false positive from the provider's safety filter (logged in runs.jsonl): for
                    # exploratory candidates, try the next seed instead of stopping the whole run.
                    print(f"  {item_id}: seed {seed} flagged by the provider's output filter, trying the next seed")
                    continue
                made += 1
            paths.append(path)
            used_seeds.append(seed)
        if chosen is None:
            sheet = REF_DIR / item_id / "candidates.png"
            contact_sheet(paths, [f"seed {s}" for s in used_seeds], sheet)
            print(f"  {item_id}: {len(paths)} candidates -> {sheet.relative_to(OUTPUTS.parent).as_posix()}")
        else:
            print(f"  {item_id}: golden reference seed {chosen}")
    print(f"references: {made} generated")


def run_keyframes(storyboard: dict[str, Any], only: set[str] | None = None) -> dict[str, Path]:
    paths, made = {}, 0
    for shot in storyboard["shots"]:
        path = keyframe_path(storyboard, shot)
        paths[shot["id"]] = path
        if path.exists() or (only and shot["id"] not in only):
            continue
        require_consent(storyboard, shot["characters"])
        refs = shot_references(storyboard, shot)
        ref_bytes = [as_reference_input(golden_reference(storyboard, item)) for item in refs]
        make_image(path, keyframe_inputs(storyboard, shot), ref_bytes, "keyframes", shot["id"])
        made += 1
        print(f"  keyframe {shot['id']}: new  {path.name}")
    print(f"keyframes: {made} generated, {len(paths) - made} reused from cache")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Reference sheet and keyframes (FLUX.2 klein, cached).")
    parser.add_argument("step", choices=["refs", "shots"])
    parser.add_argument("--only", nargs="*", help="limit to these character/prop ids or shot ids")
    parser.add_argument("--candidates", type=int, default=3, help="reference candidates per item (saves quota)")
    args = parser.parse_args()
    board = load_storyboard()
    only = set(args.only) if args.only else None
    if args.step == "refs":
        run_references(board, only, args.candidates)
    else:
        run_keyframes(board, only)


if __name__ == "__main__":
    main()
