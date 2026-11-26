# Architecture

`storyboard.json` is the single contract. Every stage reads it, writes files whose names include a
hash of their inputs, and logs every model call to `runs.jsonl`. `uv run film` runs the stages in order.
A stage that finds its output already on disk skips the call, so a re-run regenerates only what changed.

```
                      schema/storyboard.schema.json + rule checks + consent gate (ETHICS.md)
                                              │
storyboard.json ──► validate ──► narration ──► keyframes ──► shots ──► assemble ──► outputs/film/
                                 Gemini TTS    FLUX.2 klein   Ken Burns   FFmpeg      film_9x16.mp4
                                 (Addis AI)    (Cloudflare)   or Wan 2.2  mix, duck,  film_16x9.mp4
                                                              (Kaggle)    subtitles,  subtitles_en.srt
                                                                          loudnorm
                                 music: ACE-Step 1.5 on Kaggle/Colab ──────┘
```

## Stages

| Stage | Module | Input | Output | Cache key (what changes it) |
|---|---|---|---|---|
| Validate | `pipeline/storyboard.py` | `storyboard.json` | errors or a loaded dict | — (always runs, before any quota is spent) |
| Narration | `pipeline/narration.py` | narration lines, voice, style | `outputs/narration/am/<shot>-<hash>.wav` | the scene's text, voice, model, style |
| References | `pipeline/keyframes.py` | character/prop prompts | `outputs/references/`, approved copies in `assets/approved/` | prompt, seed, base images |
| Keyframes | `pipeline/keyframes.py` | shot prompt + approved references | `outputs/keyframes/<shot>-<hash>.png` | prompt, seed, size, model, **content hash of each reference image** |
| Shots | `pipeline/shots.py` | keyframe (or Wan clip), camera move, length | `outputs/shots/<size>/<shot>-<hash>.mp4` | source file hash, move, length, frame size |
| Wan clips | `pipeline/kaggle_jobs.py` + `notebooks/wan_shots/` | keyframe + motion prompt | `outputs/wan/<shot>-<hash>.mp4` | keyframe hash, motion prompt, model |
| Music | `pipeline/kaggle_jobs.py` + `notebooks/music/` | caption, bpm, key, seeds | `outputs/music/score-<seed>.wav` | the chosen seed |
| Assembly | `pipeline/assemble.py` | everything above | `outputs/film/` | always re-assembled (cheap compared with the model calls) |

## The important design decisions

**1. One contract, validated before anything is spent.** `load_storyboard()` runs the JSON Schema and
then rule checks the schema can't express: duplicate ids, `{placeholders}` that name no character or
prop, a total length outside 60–90 s, and a `face_from` pointing at an unknown character. A typo fails
in a second, not after ten paid image calls.

**2. Caching by input hash** (`core.input_hash`). Each output's file name carries a 12-character SHA-256
of a canonical JSON of every input that affects it. A changed narration line produces a new hash, so
there's a new file for that shot only. Hashes chain: a keyframe's key includes the *content hash* of
its reference images, so replacing Grandma's approved reference regenerates exactly the keyframes she
appears in, and the shot clips built from them.

**3. Retries that read the error** (`core.call_model`). Up to 4 attempts with exponential backoff
(5 s, 10 s, 20 s) for 408/429/5xx and network errors. A 400 or a bad key fails immediately. Two
special cases were learned the hard way:
- Cloudflare's 429 with code 4006 ("daily allocation used up") fails fast, because no retry can help
  before midnight UTC (F14).
- `run_with_deadline` gives every TTS attempt a hard 90 s limit, because the SDK's own timeout didn't
  cover every code path and one call hung for 15 minutes (F4).

**4. Every call is logged** to `runs.jsonl`, including failures and retries: stage, shot, model,
params, seed, output path, attempt, status, latency, actual cost, list-price estimate, neuron estimate.
Secrets are removed by `core.redact` before anything is written. Provider replies are logged through an
allowlist, so audio payloads and signed links never reach the log.

**5. Consent is enforced in code.** Before generating any character marked `real_person: true`,
`require_consent()` reads that person's record in `ETHICS.md` and refuses unless its status is
`granted`. The ethics document is the source of truth, not a comment.

**6. Graceful degradation for motion.** A shot uses a Wan 2.2 clip only if one exists for its *current*
keyframe and motion prompt. Otherwise it gets a Ken Burns camera move (push-in, pull-out or pan),
rendered locally with FFmpeg. A stale clip can never appear by accident.

**7. One master, two aspect ratios.** Keyframes are square (1024²). Each aspect ratio gets its own
crop, its own clips (cached per frame size) and its own subtitle layout, but one shared audio master.

## Audio chain (assemble.py)

1. Narration lines are placed on a timeline (`build_timeline`), one slot per shot.
2. Voice and music are each normalised to a set loudness first (voice −16 LUFS, music bed −20 LUFS), so
   the balance is a decision, not a repair.
3. The music follows a per-cue volume envelope from the storyboard (for example, a hush for the house of
   mourning, then silence at the reveal), and is ducked under the voice with a sidechain compressor.
4. The mix is mastered with two-pass `loudnorm` to −14 LUFS integrated and −1.5 dBTP true peak, with
   headroom under the −1 dBTP limit.
5. Amharic is spoken and English subtitles are burned in, wrapped at 40 characters and 2 lines.

## Running the GPU stages from a 2-core laptop

`uv run python -m pipeline.kaggle_jobs push|status|pull wan|music` uploads the inputs as a private
Kaggle dataset, starts a GPU script, and later downloads the outputs and appends the GPU-side records
to `runs.jsonl`. The job inputs carry the same cache keys as the local stages, so a downloaded clip is
used only if it matches the current storyboard. The music script also runs on Colab when the Kaggle
queue stalls.

## Repository map

```
storyboard.json            the contract (story, characters, shots, prompts, seeds, music, end card)
schema/                    JSON Schema for the contract
pipeline/                  core (hash, retry, log, redact) and one module per stage; film.py runs them all
notebooks/                 GPU scripts for Kaggle/Colab: Wan 2.2 shots, ACE-Step music
experiments/               standalone experiment scripts (TTS voice comparison)
tests/                     pytest: schema/rules, consent gate, caching keys, references, splitting, assembly
assets/approved/           approved reference images (pinned, so the film can be regenerated)
outputs/                   generated media; outputs/film/ holds the finished films
runs.jsonl                 one line per model call
DESIGN.md                  audience, intent, storyboard iterations, user tests
EXPERIMENTS.md · FAILURES.md · COSTS.md · ETHICS.md
```
