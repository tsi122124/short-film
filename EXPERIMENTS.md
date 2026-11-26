# Experiments

Each entry: hypothesis → change → result, with the evidence (log lines in `runs.jsonl`, files in
`outputs/`). One thing changes per experiment; seeds and inputs stay fixed where they matter.

## E1. Which TTS voice sounds like natural Amharic?

- **Hypothesis:** a teammate on Slack reported that Addis AI, an Ethiopian provider with native Amharic
  voices, sounds better than Gemini TTS. After the smoke test I (a native speaker) also judged Gemini's
  default Amharic "not natural", so I expected an Addis voice to win.
- **Change:** the same two lines (s02, s04) through all 9 female Addis AI Amharic voices and Gemini
  `gemini-3.8-flash-tts` voices Sulafat and Achernar, with the same text.
  Script: `experiments/tts_compare.py`; outputs: `outputs/experiments/tts_compare/`.
- **Result:** I preferred **Gemini, voice Sulafat**, with a natural, story-telling style instruction:
  to me it sounded the most natural and it expressed the feelings of the memory. Notably, the same
  Sulafat voice with the earlier "slow" style instruction (smoke test) had not sounded natural, so the
  style instruction mattered for naturalness even though it did not change pace (E2). Measured
  length of line s02 (`runs.jsonl`, stage `experiment`): Addis voices 4.70–6.96 s, Gemini Achernar 7.46 s,
  Gemini Sulafat 9.36 s. The voice I preferred is also the slowest, which forced the script cut in E3.
- **Caveat:** one listener (me). A blind preference test with at least five Amharic speakers is planned,
  using `--blind`, which writes shuffled A/B/C copies and a separate answer key.
- **Decision:** narration stays on Gemini Sulafat (free tier, and the pipeline stays free to re-run).

## E2. Does the style instruction control speaking pace?

- **Hypothesis:** removing "slow" from the Gemini style instruction shortens the narration.
- **Change:** on line s02 with voice Sulafat, the style went from "slow, warm and gentle, like a woman
  smiling as she remembers her late grandmother…" to "natural conversational pace, warm and gentle, like
  a woman telling a funny family memory to people she loves". Text, voice and model unchanged.
- **Result:** 8.70 s → 9.36 s. Not shorter. The style instruction changed the feeling (I preferred the
  new one) but not the pace.
- **Conclusion:** the lever for length is the script, not the style prompt. See E3.

## E3. Can the script fit 60–90 s without losing the story?

- **Hypothesis:** cutting every narration phrase that the picture already shows brings speech from
  ~113 s to ~70 s while keeping all story beats and my grandmother's real words.
- **Change:** storyboard v2 → v3 (see DESIGN.md); e.g. s09 went from «…እኔ በሩ ላይ ብቅ አልኩ፤ መጥረጊያው
  ትከሻዬ ላይ።» to «…እኔ በሩ ላይ ብቅ አልኩ።», because the image shows the sweeper.
- **Result:** _pending the v3 radio cut measurement._
