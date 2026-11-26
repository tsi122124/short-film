# The Sweeper (መጥረጊያው): a heritage short, made by a pipeline

A 60–90 second film, narrated in Amharic with English subtitles, about the morning I followed my
grandmother to a neighbour's house of mourning carrying a brand-new wall sweeper. It was not made by
hand: `storyboard.json` is the single contract, and each pipeline stage reads it and writes its output.

## Run it

```bash
git clone <this repo> && cd <repo>
cp .env.example .env          # then paste your own keys into .env
uv sync                       # installs the exact locked dependencies
uv run smoke                  # calls each provider once; checks keys and model ids
uv run film                   # validates the storyboard and regenerates the film
uv run film --radio           # the radio cut: narration + placeholder music on black
```

Requirements: [uv](https://docs.astral.sh/uv/), Python 3.11+, and [FFmpeg](https://ffmpeg.org/download.html)
on your PATH (or set `FFMPEG=/path/to/ffmpeg` in `.env`). Keys: a Gemini API key (free, AI Studio) and a
Cloudflare account ID and Workers AI token (free daily allowance). Moving shots and music run on a free
Kaggle GPU; see `notebooks/`.

## How it works

```
storyboard.json ──validate(schema/)──► narration ──► keyframes ──► shots ──► music ──► assemble ──► outputs/film/
                                        Gemini TTS   FLUX.2 klein  Wan 2.2   ACE-Step   FFmpeg
```

- **One contract.** Every prompt, seed, model id, narration line and music cue lives in `storyboard.json`,
  validated against `schema/storyboard.schema.json` before any stage runs.
- **Caching by input hash.** Each output's file name contains a hash of the inputs that produced it. Change
  one narration line and only that shot is regenerated; everything else is reused.
- **Every model call is logged** to `runs.jsonl`: model, parameters, seed, latency, cost, status, attempt.
- **Retries** with exponential backoff on rate limits, server errors and network failures; bad requests
  fail fast.
- **Consent gate in code.** The keyframe stage refuses to generate a real person unless `ETHICS.md` holds
  a granted consent record for them.

Details: [ARCHITECTURE.md](ARCHITECTURE.md). Audience and user tests: [DESIGN.md](DESIGN.md).
Experiments: [EXPERIMENTS.md](EXPERIMENTS.md). Failures: [FAILURES.md](FAILURES.md).
Costs: [COSTS.md](COSTS.md). Consent, licences, labelling: [ETHICS.md](ETHICS.md).

## Regenerate one shot

Edit one shot's `narration` or `image_prompt` in `storyboard.json`, then run `uv run film` again. The
console reports which outputs were reused and which were regenerated, and `runs.jsonl` gains only the
new model call(s).
