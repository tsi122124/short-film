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

## F4. TTS calls "hung" for up to 15 minutes

- **What broke:** the s12 narration call, one comparison call, and then a whole film run never returned:
  no error, no retry, no log line.
- **First hypothesis (wrong):** no request timeout. I added a 120 s client timeout; the next run still hung.
- **Investigation:**
  1. A `faulthandler` stack dump after 75 s showed the process inside an `import`: the SDK's Interactions
     package takes 20–26 s to import on this laptop, every run (F5).
  2. My own hard deadline then turned the hang into four logged `TimeoutError`s.
  3. A raw REST call to the same endpoint without the SDK returned **HTTP 429: "limit: 10 requests per day
     on Free Tier … retry in 4h3m"**, with a `retry-after` header of 14,593 s.
- **Root cause:** the daily TTS quota was used up, and the SDK retried silently while honouring the
  4-hour `retry-after`, which looks exactly like a hang.
- **Fix:**
  - SDK retries switched off (`retry_options={"attempts": 1}`), so a 429 surfaces at once in `call_model()`,
    the one retry layer that logs every attempt.
  - A hard per-attempt deadline (`run_with_deadline`) as a safety net.
  - The SDK import moved out of the timed section, so logged latency measures only the API. The smoke
    test's "25.6 s TTS latency" was mostly import time.
- **Lesson:** keep one retry layer, and make it observable.

## F5. My laptop is the slowest part of the pipeline

- **What broke:** rendering a black 85 s radio cut took 210 s (9:16) and 600 s (16:9).
- **Investigated:** the machine is an Intel Celeron N4020 (2 cores, 1.1 GHz). A 10 s benchmark showed
  1080p H.264 encoding runs at about real time (10.2 s), burning subtitles adds only ~13 % (11.5 s), and
  the long renders came from other jobs competing for the same two cores.
- **Fix:** render only the 9:16 version for the radio cut; cache each shot's rendered clip by input hash
  so a re-run only re-encodes what changed; run GPU work (Wan 2.2, ACE-Step) on Kaggle, not locally.

## F8. The last word of the film was mispronounced

- **What broke:** listening to the radio cut, I heard the final word of s12, «ያስቃል» ("makes laugh"),
  mispronounced by Gemini TTS. My analysis confirmed the word was present and not clipped by the
  pipeline (speech ends at 20.12–20.18 s at any threshold; the trim kept up to 20.18 s).
- **Options:** Gemini TTS offers no phonetic markup for Amharic, so the fix had to be in the words:
  rephrase, try an alternative spelling, or simply re-record.
- **Fix:** I rewrote the ending as a refrain, «…ያስቃል። አሁንም ያስቃል።» ("…makes them laugh. It still
  does."), and dropped «ዛሬም» to avoid saying "still" twice. Re-recording that scene cost one request.
  The new take exposed a splitting edge case (E4, result 3).
- **Then a second word:** in the new take, «አያቴ» ("my grandmother") at the start of s12 was mispronounced,
  although the same word is said correctly in s01, s04, s08 and s10. The difference is the context:
  in s12 it follows the end of s11 within the same take. I added «ውዷ» ("dear") before it:
  «ውዷ አያቴ ዛሬ በሕይወት የለችም።». The new context changed the reading, and the tribute became warmer.
  This cost one more request.
- **Lesson:** a native-speaker listen catches what no metric does. Each fix cost one request because a
  changed line regenerates only its own scene.

## F6. LinkedIn has no AI-label toggle

- **What broke:** the brief asks to post with the platform's AI label switched on. LinkedIn's help page
  describes only automatic Content Credentials (C2PA) detection, no manual toggle.
- **Fix:** post on YouTube Shorts with "AI use: Yes" switched on, and on LinkedIn with a written
  disclosure in the first line linking the labelled version (ETHICS.md).

## F7. Ten TTS requests a day, twelve narration lines

- **What broke:** one request per shot needs 12 requests per full narration pass, but the free tier allows
  10 a day for `gemini-3.8-flash-tts`. The smoke test, the first full pass and the voice comparison had
  used them up by early morning, before the radio cut existed.
- **Options:**
  - Wait for the reset at about 11:00 EAT. Too late for the first user test.
  - Switch to Addis AI, which has no daily cap. But Gemini Sulafat won on expressiveness (E1).
  - Read several lines per request.
- **Fix:** `narration.batches` in the storyboard. One request per scene (3 for all 12 lines), each take
  split back into lines (E4). The raw takes are cached, so re-splitting costs no quota. A changed line
  costs one request for its scene.
- **Transparency:** my own project's quota was exhausted that morning, so the three batch requests ran on
  a friend's Gemini API key, used with their consent. The key lives only in the gitignored `.env` and
  will be rotated after the challenge.

