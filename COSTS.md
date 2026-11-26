# Costs

Every number below is computed from `runs.jsonl` (196 calls across 40 runs, 2026-11-25 23:59 UTC to
2026-11-26 13:15 UTC), not estimated afterwards. Each record carries `cost_usd` (what I actually paid),
and where a provider publishes a price, `list_price_usd` (what the same call would cost on a paid plan).

## What I paid

**$0.00.** Every call ran on a free allowance: Gemini API free tier, Cloudflare Workers AI's 10,000 free
neurons a day, Addis AI signup credit, and FFmpeg on my laptop.

## What it would cost at list price

| Stage | Provider / model | Calls (ok) | List price | Notes |
|---|---|---|---|---|
| References (character sheets) | Cloudflare `flux-2-klein-4b` | 79 (75) | $0.089 | ≈108 neurons per image; iterating on the look was the most expensive part |
| Keyframes | Cloudflare `flux-2-klein-4b` | 23 (19) | $0.024 | ≈116 neurons per image at 1024² |
| Narration | Gemini `gemini-3.8-flash-tts` | 20 (16) | $0.045 | 197 s of Amharic audio generated in total |
| TTS experiment (E1) | Gemini TTS + Addis AI | 11 (11) | $0.004 + 4.39 ETB | blind voice comparison |
| Smoke test | Gemini text + TTS | 2 (2) | $0.001 | key and model-id check |
| Shots + assembly | FFmpeg (local) | 61 (61) | $0 | 72 min of laptop CPU time |
| **Total** | | **196** | **≈ $0.16 + 4.39 ETB** | |

Neurons used on 2026-11-26 (UTC): **10,306 of 10,000**. That overrun is the 429 / code 4006 in FAILURES.md F14.

## What one full regeneration costs

With nothing cached, `uv run film` makes 3 narration requests (one per scene batch) and 12 keyframes:

- Narration: 3 × ≈$0.003 ≈ **$0.01**
- Keyframes: 12 × ≈$0.0013 ≈ **$0.015** (≈1,400 neurons, so it fits in one free day)
- Assembly: $0, about 4 minutes per aspect ratio on a 2-core Celeron

**≈ $0.025 per full film at list price.** Changing one shot costs one keyframe (≈$0.0013) or one narration
batch (≈$0.003), because every other output is reused from the cache.

## Where the real cost was

Money was not the constraint. **Quota and time were:**

- **Daily caps.** Gemini TTS allows 10 requests a day and Cloudflare 10,000 neurons a day. Both ran out
  on the same day (F7, F14). The design answers were batching (3 TTS requests instead of 12) and
  caching by input hash, so a re-run spends quota only on what changed.
- **Laptop time.** 72 minutes of FFmpeg across the day. A full render is ≈3.5 min per aspect ratio
  (`render_film_9x16` 218 s, `render_film_16x9` 206 s), so shot clips are cached separately.
- **Waiting on free GPUs.** The Kaggle jobs (Wan 2.2 shots, ACE-Step music) were queued for over five
  hours without starting (F15). Free GPU time is free, but it isn't guaranteed.
- **Reference iterations used 80% of the image budget** (8,111 of 10,306 neurons) before any keyframe
  existed. Next time I would approve the character sheets at a smaller size first (F12).
