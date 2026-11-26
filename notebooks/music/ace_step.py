"""Kaggle GPU job: ACE-Step 1.5 score candidates for the film.

Reads music.json from the private dataset pushed by `pipeline/kaggle_jobs.py` (caption, bpm, key,
duration, seeds) and writes one instrumental WAV per seed plus music_log.jsonl to /kaggle/working.

Notes from the ACE-Step sources (see EXPERIMENTS.md): it needs Python 3.11-3.12, so it runs in its own
uv environment; on a T4 (no bf16) it switches to fp16, where lyrics can produce NaN, but instrumentals
work; the language-model planner is skipped to fit memory.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

DATA = next(Path("/kaggle/input").glob("*"))
OUT = Path("/kaggle/working")
REPO = Path("/kaggle/temp/ACE-Step-1.5")
job = json.loads((DATA / "music.json").read_text())
print("job:", json.dumps(job), flush=True)


def sh(cmd: str) -> None:
    print("$", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)


sh("curl -LsSf https://astral.sh/uv/install.sh | sh")
uv = str(Path.home() / ".local" / "bin" / "uv")
REPO.parent.mkdir(parents=True, exist_ok=True)
if not REPO.exists():
    sh(f"git clone --depth 1 https://github.com/ACE-Step/ACE-Step-1.5 {REPO}")
sh(f"cd {REPO} && {uv} sync --python 3.12")

runner = REPO / "run_candidates.py"
runner.write_text(f'''
import json, time
from acestep.handler import AceStepHandler
from acestep.inference import GenerationConfig, GenerationParams, generate_music

job = json.loads(open("{DATA / 'music.json'}").read())
t0 = time.time()
dit = AceStepHandler()
print(dit.initialize_service(project_root=".", config_path="acestep-v15-turbo", device="cuda"), flush=True)
params = GenerationParams(caption=job["caption"], lyrics="[Instrumental]", instrumental=True,
                          duration=job["duration_s"], bpm=job["bpm"], keyscale=job["key"], timesignature="4",
                          inference_steps=8, shift=3.0, thinking=False)
config = GenerationConfig(batch_size=len(job["seeds"]), use_random_seed=False, seeds=job["seeds"],
                          audio_format="wav")
result = generate_music(dit, None, params, config, save_dir="{OUT / 'music'}")
record = {{"stage": "music", "model": "ACE-Step-1.5-turbo", "params": job, "seeds": job["seeds"],
          "status": "ok" if result.success else "failed", "error": result.error,
          "latency_s": round(time.time() - t0, 1),
          "outputs": [a["path"] for a in result.audios] if result.success else []}}
open("{OUT / 'music_log.jsonl'}", "a").write(json.dumps(record) + "\\n")
print(json.dumps(record), flush=True)
''')
started = time.time()
subprocess.run(f"cd {REPO} && {uv} run python {runner}", shell=True, check=False)
print(f"done in {(time.time() - started) / 60:.1f} min", flush=True)
sys.exit(0)
