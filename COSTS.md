# Costs and latency

*Revised 27 Nov 2026, after the first grading: added time per stage, GPU minutes, a full-regeneration time
estimate and a comparison with frontier models. The first version covered 196 calls up to 13:15 UTC on
26 Nov; this one covers the whole log.*

Every number below is computed from `runs.jsonl` (**287 logged attempts across 55 runs, 2026-11-25 23:59
to 2026-11-26 23:53 UTC**), not estimated afterwards. Each record carries `latency_s` (wall-clock time of
that attempt), `cost_usd` (what I actually paid) and, where a provider publishes a price,
`list_price_usd` (what the same call would cost on a paid plan).

## What I paid

**$0.00.** Every call ran on a free allowance: Gemini API free tier, Cloudflare Workers AI's 10,000 free
neurons a day, Addis AI signup credit, and FFmpeg on my laptop. At list price the whole log comes to
**≈ $0.20 + 4.39 ETB**.

## Cost and time per stage

| Stage | Where it runs | Attempts (ok / retried / failed) | Total time | Median | p95 | Slowest | List price |
|---|---|---|---|---|---|---|---|
| References | Cloudflare `flux-2-klein-4b` | 79 (75 / 3 / 1) | 19.8 min | 11.5 s | 35.3 s | 72.4 s | $0.089 (8,111 neurons) |
| Keyframes | Cloudflare `flux-2-klein-4b` | 49 (41 / 3 / 5) | 8.5 min | 11.1 s | 19.6 s | 19.8 s | $0.053 (4,836 neurons) |
| Narration | Gemini `gemini-3.8-flash-tts` | 21 (17 / 3 / 1) | 10.5 min | 10.9 s | 91.5 s | 92.2 s | $0.051 |
| TTS experiment (E1) | Gemini TTS + Addis AI | 11 (11 / 0 / 0) | 1.4 min | 6.7 s | 15.4 s | 15.4 s | $0.004 + 4.39 ETB |
| Smoke test | Gemini text + TTS | 2 (2 / 0 / 0) | 0.9 min | 28.1 s | 30.6 s | 30.6 s | $0.001 |
| Shots + assembly | FFmpeg, local CPU | 125 (125 / 0 / 0) | **187.4 min** | 32.8 s | 277 s | 2,316 s | $0 |
| Wan 2.2 shots, ACE-Step music | Kaggle GPU (2× T4) | 0 | **0 GPU min** | — | — | — | $0 |

The narration p95 of ~92 s is the hard 90 s deadline cutting off attempts that would otherwise have hung
(FAILURES.md F4). Failed keyframe attempts are the Cloudflare safety filter (code 3030) and the
daily-cap error (code 4006), both in FAILURES.md.

## Where the time went

- **Model calls: 41 min in total. FFmpeg on the laptop: 187 min.** The bottleneck was the 2-core Celeron,
  not the AI. The biggest FFmpeg steps: 16:9 film renders (53 min over 3 renders, median 11 min), shot
  clips (48 min over 53 clips, median 34 s), and mixing with ducking (24 min over 10 runs).
- **GPU: 0 minutes.** Both Kaggle jobs were pushed at 16:27 EAT on deadline day and still queued at 21:25
  (F15). Free GPU time is free, but it isn't guaranteed. The film rendered without it because every shot
  falls back to a local camera move.
- **Renders slowed down when they overlapped.** The slowest single step (2,316 s, a 16:9 render) ran
  while other jobs shared the same two cores (F5). Run-to-run variation is real even when nothing else
  runs: the same 10 s shot clip took 19.2–25.2 s across four identical runs (E10, E11).

## What one full regeneration costs

With nothing cached, `uv run film` makes 3 narration requests (one per scene batch) and 12 keyframes.

| Step | Calls | List price | Time (estimate from the medians above) |
|---|---|---|---|
| Narration | 3 | ≈ $0.01 | ≈ 1 min (incl. the 20–26 s SDK import, F4) |
| Keyframes | 12 | ≈ $0.015 (≈ 1,400 neurons, fits in one free day) | ≈ 2.5 min |
| Shot clips, both aspects | 24 | $0 | ≈ 14 min |
| Mix, master, render both aspects | — | $0 | ≈ 18 min (medians include renders that overlapped other jobs) |
| **Total** | **15 model calls** | **≈ $0.025** | **≈ 35 min, of which ≈ 3.5 min is model time** |

Changing one shot costs one keyframe (≈ $0.0013, ≈ 11 s) or one narration batch (≈ $0.003, ≈ 11 s),
because every other output is reused from the cache. The FFmpeg time is what a re-run mostly pays.

## Compared with frontier models

I only had free-tier access, so **no paid frontier model was called**. This compares published list
prices against what this film actually used; it does not compare quality. Prices read on 27 Nov 2026;
sources are listed below, and third-party ones are marked.

| Stage | Used in this film | Frontier option | Per unit | One full regeneration | Whole project volume |
|---|---|---|---|---|---|
| Images | FLUX.2 klein 4B (Cloudflare) | — | ≈ $0.0013 / image | $0.015 (12) | $0.14 (116 images) |
| | | FLUX.2 [max] (Black Forest Labs) | ≈ $0.07 / image ¹ | $0.84 | $8.12 |
| | | Gemini 3 Pro Image | ≈ $0.134 / image (1K–2K) ² | $1.61 | $15.54 |
| Narration | Gemini 3.8 Flash TTS | — | $9 / 1M audio tokens (25 per s) ³ | ≈ $0.012 (55 s) | $0.05 |
| | | Gemini 2.5 Pro TTS | $20 / 1M audio tokens ³ | ≈ $0.028 | ≈ $0.11 |
| Motion | Ken Burns (local) / Wan 2.2 (free Kaggle) | — | $0 | $0 | $0 |
| | | Veo 3.1 Lite, 1080p | $0.08 / s ⁴ | $4.80 (60 s of clips) | — |
| | | Veo 3.1 Fast, 1080p | $0.12 / s ⁴ | $7.20 | — |
| | | Veo 3.1 Standard, 1080p | $0.40 / s ⁴ | $24.00 | — |

**Trade-offs, stage by stage:**

- **Images: 50–100× the price, aimed at my real weakness.** My two image problems were identity drift
  (Grandma's face) and three-person scenes merging (F17). Those are exactly what a larger model might
  fix. Even at FLUX.2 [max] prices, all 116 images would have cost about $8, but it has no free tier,
  and this project had a zero-budget constraint. The cheapest useful next experiment: re-run only the
  three F17 shots (s06, s11, s12) on a frontier image model, about $0.20–0.40.
- **Narration: price is not the issue.** Every option costs cents per film. The real constraints were
  the free tier's 10 requests a day (solved by batching, E4) and Amharic naturalness, which only a native
  listener can judge (E1). A Pro TTS voice was not tested on Amharic, so I can't claim it would sound
  better. Note: the Flash TTS list price doubles to $18 / 1M from 1 Jan 2027 ³, so re-runs after that
  cost about twice as much (still ≈ $0.025 per film).
- **Motion: the only upgrade with a real price.** Veo would replace both the 5-hour queue and the
  camera-move fallback for about $5–24 per full film, the largest cost of any upgrade here. Wan 2.2 on a
  free GPU costs $0 but delivered 0 minutes this time. For a paid project, Veo 3.1 Lite or Fast would be
  the reliable choice; for a free one, Wan plus the fallback is the right design, pushed on day one.

**Sources:**
¹ [docs.bfl.ai pricing](https://docs.bfl.ai/quick_start/pricing) (official; 1 credit = $0.01), figure
cross-checked with [Puter's FLUX pricing guide](https://developer.puter.com/tutorials/flux-api-pricing/)
(third party). Price scales with resolution.
² [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) (official): $120 / 1M image
tokens, 1,120 tokens per 1K–2K image.
³ [Google Cloud Text-to-Speech pricing](https://cloud.google.com/text-to-speech/pricing) (official). The
Flash TTS price matches the one in `pipeline/narration.py`, read on 26 Nov.
⁴ [Developers Digest, Gemini API video pricing](https://www.developersdigest.tech/models/video-generation/google-gemini-api)
(third party, read from Google's pages on 18 Oct 2026), consistent with
[Magic Hour's Veo 3.1 guide](https://magichour.ai/blog/veo-3-pricing).

## Where the real cost was

Money was not the constraint. **Quota and time were:**

- **Daily caps.** Gemini TTS allows 10 requests a day and Cloudflare 10,000 neurons a day. Both ran out
  on 26 Nov (F7, F14). The design answers were batching (3 TTS requests instead of 12) and caching by
  input hash, so a re-run spends quota only on what changed.
- **Reference iterations used most of the image budget**: 8,111 of the 12,947 estimated neurons, before
  most keyframes existed. My own account hit the 10,000 cap (F14); the v7 keyframes were made with a
  second account (F17). Next time I would approve character sheets at a smaller size first (F12).
- **Laptop time.** 187 minutes of FFmpeg, 4.5× all model time combined. Shot clips are cached separately
  so a re-run only re-encodes what changed.
- **Waiting on free GPUs.** 0 GPU minutes after more than five hours in the queue (F15).
