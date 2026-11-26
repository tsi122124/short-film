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

## F9. "Ethiopian" came out Mediterranean

- **What broke:** the first reference sheet showed Spanish- or Mexican-looking streets, a grandmother with
  a Latin face, and a lace scarf instead of a netela. "An Ethiopian city neighbourhood" was too vague a
  label for the model.
- **Fix:** concrete visual words instead of labels:
  - "Habesha Ethiopian, dark brown skin"
  - "corrugated-iron roofs, plastered concrete-block houses, eucalyptus trees, painted metal gates,
    asphalt roads with blue-and-white minibuses"
  - Clothing described from photos I provided. One garment photo was used directly, with its owner's
    permission and cropped to no face (ETHICS.md).

## F10. The street setting overrode "inside the home"

- **What broke:** keyframes s01–s04, which happen inside the house, came out on the street.
- **Root cause:** the global `setting` (streets) was appended to every keyframe prompt, and outweighed
  the shot's own "inside the home".
- **Fix:** each shot has a `location`. Interior shots get `interior_setting` (the home), exterior shots
  get the street, and reference images get neither. A regression test covers it.

## F11. Image edits: one change at a time, and no chains

- **What broke:**
  - Edits asking for several changes applied some and silently ignored others: the lace survived, and
    the crossed veil was missed.
  - "Lengthen her dress" and "shorten the veil" were ignored in every candidate.
  - An edit of an edit of an edit came out blotchy and greenish (generation loss).
- **Fix:** one change per edit. Stop chaining once quality drops. Pin the approved image
  (`reference.approved`) so it is never regenerated, and put remaining details into the keyframe prompt
  instead.

## F12. A 10,000-neuron daily image budget, and a false-positive safety filter

- **What broke:**
  - Reference iterations used about 8,000 of Cloudflare's 10,000 free daily neurons before any keyframe
    existed. The allowance resets at 03:00 EAT, after the deadline.
  - Separately, Cloudflare's output filter rejected an elderly woman in a black veil
    (`"Your output has been flagged"`, code 3030), which stopped the whole run.
- **Fix:**
  - Keyframes at 1024² instead of 1280² (≈120 instead of ≈200 neurons each).
  - Fewer candidates per round (`--candidates`).
  - A flagged *candidate* is logged and the next seed tried; a flagged golden image or keyframe still
    stops the run.
  - Neuron estimates are logged per call (`neurons_est`, `list_price_usd`).

## F13. Keyframes that missed their story point

- **What broke:** s07 ("crossing the asphalt", the image the family laughs about most) had no sweeper at
  all, and in s09 (the reveal) the sweeper was barely visible.
- **Fix:** put the prop first in the prompt, together with its exact pose ("on her right shoulder,
  clearly visible, handle diagonal"), and use a new seed. The s09 retake drew a bristle head at both ends;
  the 9:16 centre crop hides the second one, and the 16:9 version shows it.

## F14. The daily image cap, hit for real, and a broken Kaggle CLI

- **What broke:**
  1. The first full-film run tried to regenerate keyframe s05, whose prompt I had changed without
     regenerating it. Cloudflare answered **429, code 4006: "you have used up your daily free allocation
     of 10,000 neurons"**, and the retry policy retried it four times, because 429 normally means
     "slow down".
  2. `uvx kaggle` crashed with `No module named 'six'`: the kaggle package imports `six` without
     declaring it as a dependency.
- **Fix:**
  1. Code 4006 now fails fast with a clear message, since no retry can help before the reset at
     00:00 UTC. s05 went back to its previous prompt, so its existing keyframe matched the cache key
     again and the film rendered with **zero** image calls. That is the cache doing its job.
  2. `uvx --with six kaggle`. A later "connection aborted" was a one-off network drop; the retry worked.
- **Lesson:** a 429 is not always "slow down". Read the error code before retrying.

## F15. Free GPUs are not guaranteed: five hours in the Kaggle queue

- **What broke:** the Wan 2.2 shot job and the ACE-Step music job were pushed to Kaggle at 16:27 EAT on
  deadline day. At 21:25 both still reported `KernelWorkerStatus.QUEUED`; neither had started.
- **Impact:** no Wan clips and no generated score before the deadline.
- **What held:** the shots stage uses a Wan clip only if one exists for the shot's *current* keyframe
  and motion prompt; otherwise it renders a Ken Burns camera move locally. The film rendered complete
  without the GPU. The music script was made to run on Colab too, as a second free GPU source.
- **Lesson:** a free external dependency needs a fallback path and a deadline of its own. Next time I
  would push GPU jobs on day one, not on the last afternoon.

## F16. A 6.4 MB run log

- **What broke:** `runs.jsonl` had grown to 6.4 MB from 196 lines. Nine Addis AI experiment rows were
  ~800 KB each: the reply carries the audio itself as base64, plus a signed playback link, and the
  logger kept every field except `audio_url`.
- **Root cause:** a blocklist (drop one known key) where an allowlist was needed. Any new field the
  provider adds goes straight into the log.
- **Fix:** `narration.addis_metadata` keeps only named billing and metadata fields, covered by a unit
  test. The nine existing rows were cleaned with the same function (the audio is already saved under
  `outputs/experiments/tts_compare/`, and the signed links had expired). The log is now 194 KB.

## F6. LinkedIn has no AI-label toggle

- **What broke:** the brief asks to post with the platform's AI label switched on. LinkedIn's help page
  describes only automatic Content Credentials (C2PA) detection, no manual toggle.
- **Options considered:** cross-post to YouTube Shorts (has an "AI use" toggle) and link it, or post
  only on LinkedIn and carry the label in the content.
- **Decision:** LinkedIn only, with a written "Made with AI" disclosure as the first line of the post
  and the AI end card burned into the film, so the label survives resharing (ETHICS.md). The missing
  platform flag is recorded as a known gap.

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

