# Failures: what broke, what I tried, what fixed it

## F1. The Gemini TTS API had moved

- **What broke:** my first narration code called Gemini TTS through `generate_content`, the pattern
  from older examples. The current docs for `gemini-3.8-flash-tts` use the newer **Interactions API**
  (`client.interactions.create`, google-genai ≥ 2.25), and the old ai.google.dev pages now redirect to
  aistudio.google.com/docs.
- **Fix:** re-read the live docs, rewrote `synthesize()` for the Interactions API, raised the SDK floor
  in `pyproject.toml`, and confirmed the model ids against the list my own key can see
  (`uv run smoke` prints it). The brief warned tools would move; this was the first one.

## F2. Gemini's Amharic did not sound natural

- **What broke:** the first smoke-test line in Amharic was intelligible but, to my native ear, not natural.
- **Tried:** 9 Addis AI Amharic voices and 2 Gemini voices on the same lines (EXPERIMENTS.md E1).
- **Result:** Gemini Sulafat with a story-telling style instruction won for expressiveness.

## F3. The narration was far too long

- **What broke:** the first full TTS pass measured 104 s of speech for 11 of 12 shots (s04 alone was
  17.5 s). With pauses and the end card the film would have run about two minutes, against a 90 s limit.
- **Why:** my style instruction asked for "slow" delivery, Amharic sentences were long, and changing the
  style did not shorten the audio (E2).
- **Fix:** cut the script (E3), keeping only what the picture cannot show; shortened lead-in/tail pauses.
- **Prevention:** the assembly stage prints the measured total and flags anything outside 60–90 s.

## F4. A TTS call hung forever

- **What broke:** the s12 narration call (and one comparison call) never returned: no error, no retry,
  no log line.
- **Why:** the Gemini client had no request timeout, so a stalled connection waited forever and the
  retry logic in `call_model()` never got an exception to act on.
- **Fix:** a 120 s timeout on the client (`REQUEST_TIMEOUT_MS`); a timeout is a network error, which the
  retry policy retries with backoff.

## F5. My laptop is the slowest part of the pipeline

- **What broke:** rendering a black 85 s radio cut took 210 s (9:16) and 600 s (16:9).
- **Investigated:** the machine is an Intel Celeron N4020 (2 cores, 1.1 GHz). A 10 s benchmark showed
  1080p H.264 encoding runs at about real time (10.2 s), burning subtitles adds only ~13 % (11.5 s), and
  the long renders came from other jobs competing for the same two cores.
- **Fix:** render only the 9:16 version for the radio cut; cache each shot's rendered clip by input hash
  so a re-run only re-encodes what changed; run GPU work (Wan 2.2, ACE-Step) on Kaggle, not locally.

## F6. LinkedIn has no AI-label toggle

- **What broke:** the brief asks to post with the platform's AI label switched on. LinkedIn's help page
  describes only automatic Content Credentials (C2PA) detection, no manual toggle.
- **Fix:** post on YouTube Shorts with "AI use: Yes" switched on, and on LinkedIn with a written
  disclosure in the first line linking the labelled version (ETHICS.md).
