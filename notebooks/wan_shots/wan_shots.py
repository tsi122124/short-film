"""Kaggle GPU job: Wan 2.2 TI2V-5B image-to-video for the shots marked `wan` in storyboard.json.

Runs on a Kaggle T4. Inputs come from the private dataset pushed by `pipeline/kaggle_jobs.py`:
jobs.json (one entry per shot: keyframe file, motion prompt, seed, output name) and the keyframes.
Outputs go to /kaggle/working: one mp4 per shot plus wan_log.jsonl (latency, params, seed per clip),
which the laptop imports into runs.jsonl.

Recipe (verified against the Wan 2.2 and diffusers sources, see EXPERIMENTS.md): diffusers
WanImageToVideoPipeline, transformer in fp16 (a T4 has no fast bf16), VAE in fp32, model CPU offload and
VAE tiling to fit 16 GB. The official generate.py needs flash-attention 2, which does not run on a T4.
Each clip is saved as soon as it is made, so a session timeout loses at most one clip.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U", "diffusers>=0.35", "transformers",
                "accelerate", "ftfy", "imageio", "imageio-ffmpeg"], check=True)

import numpy as np
import torch
from diffusers import AutoencoderKLWan, WanImageToVideoPipeline, WanTransformer3DModel
from diffusers.utils import export_to_video, load_image
from transformers import UMT5EncoderModel

DATA = next(Path("/kaggle/input").glob("*"))  # the keyframes dataset
OUT = Path("/kaggle/working")
MODEL = "Wan-AI/Wan2.2-TI2V-5B-Diffusers"
NEGATIVE = "static, blurry, distorted, deformed hands, extra limbs, morphing face, flicker, text, watermark"

jobs = json.loads((DATA / "jobs.json").read_text())
settings = jobs["settings"]
print(f"{len(jobs['shots'])} shots; settings {settings}; GPU {torch.cuda.get_device_name(0)}", flush=True)

started = time.time()
text_encoder = UMT5EncoderModel.from_pretrained(MODEL, subfolder="text_encoder", torch_dtype=torch.bfloat16)
transformer = WanTransformer3DModel.from_pretrained(MODEL, subfolder="transformer", torch_dtype=torch.float16)
vae = AutoencoderKLWan.from_pretrained(MODEL, subfolder="vae", torch_dtype=torch.float32)
pipe = WanImageToVideoPipeline.from_pretrained(MODEL, text_encoder=text_encoder, transformer=transformer, vae=vae)
pipe.enable_model_cpu_offload()
pipe.vae.enable_tiling()
print(f"model loaded in {time.time() - started:.0f} s", flush=True)

log = OUT / "wan_log.jsonl"
for job in jobs["shots"]:
    target = OUT / job["output"]
    if target.exists():
        continue
    t0 = time.time()
    try:
        image = load_image(str(DATA / job["keyframe"])).resize((settings["width"], settings["height"]))
        frames = pipe(
            image=image, prompt=job["prompt"], negative_prompt=NEGATIVE,
            height=settings["height"], width=settings["width"], num_frames=settings["num_frames"],
            num_inference_steps=settings["steps"], guidance_scale=settings["guidance"],
            generator=torch.Generator("cpu").manual_seed(job["seed"]),
        ).frames[0]
        if not np.isfinite(frames).all() or float(np.max(frames)) < 0.02:
            raise ValueError("NaN or black frames (fp16 overflow?)")
        export_to_video(frames, str(target), fps=settings["fps"])
        status, error = "ok", None
    except Exception as err:  # noqa: BLE001 - logged per shot; the laptop falls back to a camera move
        status, error = "failed", f"{type(err).__name__}: {err}"[:500]
    record = {"stage": "shots", "shot": job["shot"], "model": MODEL, "seed": job["seed"],
              "params": {**settings, "prompt": job["prompt"]}, "status": status, "error": error,
              "latency_s": round(time.time() - t0, 1), "gpu": torch.cuda.get_device_name(0),
              "output": f"outputs/wan/{job['output']}"}
    with log.open("a") as f:
        f.write(json.dumps(record) + "\n")
    print(json.dumps(record), flush=True)
    torch.cuda.empty_cache()

print(f"done in {(time.time() - started) / 60:.1f} min", flush=True)
