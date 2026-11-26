"""Run the GPU stages on Kaggle from this laptop: Wan 2.2 moving shots and ACE-Step score candidates.

    uv run python -m pipeline.kaggle_jobs push wan     # upload keyframes (private dataset) + start the GPU job
    uv run python -m pipeline.kaggle_jobs status wan
    uv run python -m pipeline.kaggle_jobs pull wan     # download clips into outputs/wan/, log into runs.jsonl
    (same with `music`)

Needs a Kaggle account with phone verification (for GPU + internet) and an API token in
~/.kaggle/kaggle.json. The kaggle CLI is run through `uvx`, so it is not a project dependency.
Job inputs carry the same cache keys the local stages use, so a downloaded clip is picked up by the
shots stage only if it was made from the current keyframe and motion prompt.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from pipeline.core import OUTPUTS, ROOT, append_log, input_hash, redact
from pipeline.keyframes import file_hash, keyframe_path
from pipeline.shots import WAN_DIR
from pipeline.storyboard import load_storyboard

WORK = OUTPUTS / "_scratch" / "kaggle"
MUSIC_DIR = OUTPUTS / "music"
WAN_SETTINGS = {"width": 640, "height": 640, "num_frames": 121, "fps": 24, "steps": 30, "guidance": 5.0}
JOBS = {
    "wan": {"script": ROOT / "notebooks" / "wan_shots" / "wan_shots.py", "slug": "heritage-short-wan-shots",
            "dataset": "heritage-short-keyframes"},
    "music": {"script": ROOT / "notebooks" / "music" / "ace_step.py", "slug": "heritage-short-music",
              "dataset": "heritage-short-music-brief"},
}


def kaggle_env() -> dict[str, str]:
    """Credentials from ~/.kaggle/kaggle.json, or from .env (KAGGLE_USERNAME + KAGGLE_KEY).

    Newer Kaggle tokens (prefix KGAT_) are read by the CLI from KAGGLE_API_TOKEN, older 32-character keys
    from KAGGLE_KEY, so the token is passed under the name that matches its format.
    """
    env = dict(os.environ)
    key = env.get("KAGGLE_KEY", "").strip()
    if key.startswith("KGAT_"):
        env.setdefault("KAGGLE_API_TOKEN", key)
    return env


def kaggle(*args: str) -> str:
    # `six` is imported by the kaggle package but not declared as its dependency (FAILURES.md F14)
    done = subprocess.run(["uvx", "--with", "six", "kaggle", *args], capture_output=True, text=True, check=False,
                          env=kaggle_env())
    if done.returncode != 0:
        raise RuntimeError(redact(f"kaggle {' '.join(args)} failed:\n{done.stdout[-1000:]}{done.stderr[-1000:]}"))
    return done.stdout


def username() -> str:
    if os.environ.get("KAGGLE_USERNAME", "").strip():
        return os.environ["KAGGLE_USERNAME"].strip()
    token = Path.home() / ".kaggle" / "kaggle.json"
    if not token.exists():
        raise RuntimeError(f"No Kaggle credentials: put kaggle.json in {token.parent} or set KAGGLE_USERNAME and "
                           "KAGGLE_KEY in .env (Kaggle -> Settings -> API -> Create New Token).")
    return json.loads(token.read_text())["username"]


def wan_key(storyboard: dict[str, Any], shot: dict[str, Any]) -> str:
    """Must match pipeline.shots.wan_clip, so the shots stage recognises the downloaded clip."""
    return input_hash({"keyframe": file_hash(keyframe_path(storyboard, shot)), "motion": shot["motion_prompt"],
                       "model": storyboard["models"]["video"]})


def prepare_wan(storyboard: dict[str, Any], data: Path) -> None:
    shots = []
    for shot in storyboard["shots"]:
        if shot["motion"]["method"] != "wan":
            continue
        output = f"{shot['id']}-{wan_key(storyboard, shot)}.mp4"
        if (WAN_DIR / output).exists():
            continue  # already made from this exact keyframe and prompt
        keyframe = keyframe_path(storyboard, shot)
        shutil.copy(keyframe, data / keyframe.name)
        shots.append({"shot": shot["id"], "keyframe": keyframe.name, "prompt": shot["motion_prompt"],
                      "seed": shot["seed"], "output": output})
    (data / "jobs.json").write_text(json.dumps({"settings": WAN_SETTINGS, "shots": shots}, indent=2))
    print(f"wan: {len(shots)} shot(s) to generate: {[s['shot'] for s in shots]}")


def prepare_music(storyboard: dict[str, Any], data: Path) -> None:
    music = storyboard["music"]
    job = {"caption": music["caption"], "bpm": music["bpm"], "key": music["key"],
           "duration_s": music["duration_s"], "seeds": music["candidate_seeds"]}
    (data / "music.json").write_text(json.dumps(job, indent=2))
    print(f"music: {len(job['seeds'])} candidates, {job['duration_s']} s")


def push(job_name: str) -> None:
    user, job = username(), JOBS[job_name]
    storyboard = load_storyboard()
    data, kernel = WORK / job_name / "data", WORK / job_name / "kernel"
    for d in (data, kernel):
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
    (prepare_wan if job_name == "wan" else prepare_music)(storyboard, data)
    dataset_id = f"{user}/{job['dataset']}"
    (data / "dataset-metadata.json").write_text(json.dumps(
        {"title": job["dataset"], "id": dataset_id, "licenses": [{"name": "CC0-1.0"}]}))
    try:
        kaggle("datasets", "version", "-p", str(data), "-m", "update", "--dir-mode", "zip")
    except RuntimeError:  # first time: the dataset does not exist yet (created private by default)
        kaggle("datasets", "create", "-p", str(data), "--dir-mode", "zip")
    shutil.copy(job["script"], kernel / job["script"].name)
    (kernel / "kernel-metadata.json").write_text(json.dumps({
        "id": f"{user}/{job['slug']}", "title": job["slug"], "code_file": job["script"].name,
        "language": "python", "kernel_type": "script", "is_private": True, "enable_gpu": True,
        "enable_internet": True, "dataset_sources": [dataset_id], "competition_sources": [],
        "kernel_sources": [], "machine_shape": "NvidiaTeslaT4",
    }, indent=2))
    print(kaggle("kernels", "push", "-p", str(kernel)).strip())


def status(job_name: str) -> None:
    print(kaggle("kernels", "status", f"{username()}/{JOBS[job_name]['slug']}").strip())


def pull(job_name: str) -> None:
    job = JOBS[job_name]
    out = WORK / job_name / "output"
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    kaggle("kernels", "output", f"{username()}/{job['slug']}", "-p", str(out))
    log = out / ("wan_log.jsonl" if job_name == "wan" else "music_log.jsonl")
    if log.exists():  # GPU-side records go into the same run log as every local call
        for line in log.read_text().splitlines():
            append_log({**json.loads(line), "where": "kaggle"})
    target = WAN_DIR if job_name == "wan" else MUSIC_DIR / "candidates"
    target.mkdir(parents=True, exist_ok=True)
    pattern = "*.mp4" if job_name == "wan" else "**/*.wav"
    copied = [shutil.copy(p, target / p.name) for p in out.glob(pattern)]
    print(f"{job_name}: {len(copied)} file(s) -> {target.relative_to(ROOT).as_posix()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the GPU stages on Kaggle.")
    parser.add_argument("action", choices=["push", "status", "pull"])
    parser.add_argument("job", choices=list(JOBS))
    args = parser.parse_args()
    {"push": push, "status": status, "pull": pull}[args.action](args.job)


if __name__ == "__main__":
    main()
