# Experiments

Each entry: hypothesis → change → result, with the evidence (log lines in `runs.jsonl`, files in
`outputs/`). One thing changes per experiment; seeds and inputs stay fixed where they matter.

## E8. Does the delivered film still meet −14 LUFS / −1 dBTP after video encoding?

- **Hypothesis:** mastering to −1.5 dBTP, not exactly −1, leaves enough headroom for the AAC encoder
  in the final MP4, which can push peaks up slightly.
- **Change:** none to the pipeline. I measured the two delivered files themselves, not the WAV master:
  `ffmpeg -i outputs/film/film_9x16.mp4 -vn -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null -`
  (same for 16:9).
- **Result:** both files: **−14.07 LUFS integrated, −1.33 dBTP true peak**, LRA 5.3 LU, 81.76 s,
  H.264 + AAC 48 kHz. AAC raised the peak by 0.17 dB (−1.5 → −1.33). That is still under −1 dBTP, so
  the headroom was needed and was enough.
- **Conclusion:** measure the delivered file, not the intermediate. A master set to exactly −1.0 dBTP
  would have shipped at about −0.8 dBTP, over the limit.

## E5. Do reference images keep characters consistent across shots?

- **Hypothesis:** attaching approved reference images (FLUX.2 klein `input_image_0..3`) to every keyframe
  keeps the same girl, grandmother and sweeper across 12 shots without training anything.
- **Change:** a reference sheet first (3 candidates per character, I chose one), then every keyframe
  generated with the references of everyone in it, and the prompt naming each one ("the girl looks
  exactly like the one in image 0").
- **Result:**
  - The girl stayed recognisable in all 12 shots (braids, yellow dress, socks, shoes), and so did the
    sweeper's shape. Grandma's face varied more.
  - With four references in one shot (s01), the model mixed people up: two grandmothers and no girl.
    Explicit positions ("on the left… in the middle… on the right, a small girl…") fixed it.
  - As the narrator, I still judged the faces not identical in every shot. That residual drift is the
    case for a LoRA or a larger model as ceiling work.

## E6. Edit an approved image, or generate fresh?

- **Hypothesis:** editing an image I already liked (base image + instruction) keeps the face while
  changing the clothes.
- **Result:**
  - Edits kept the face, but also kept the old garment's drape: the lace and veil shapes survived
    "replace the netela".
  - Fresh generation fixed the clothing but changed the face.
  - What worked: fresh generation for the outfit, then a **two-image edit** (image 0 = outfit,
    image 1 = face), then **single-change edits**.
  - Edits stop being useful after 2–3 generations (F11).

## E7. Should references include the setting?

- **Hypothesis:** references should show only people and objects. If the street setting is in their
  prompt, changing the streets regenerates (and changes) faces that were already approved.
- **Change:** split `style_block` (the look) from `setting` (the place). References get the look only,
  and approved references are pinned by file (`reference.approved`).
- **Result:** references came out on plain backgrounds. When I changed the neighbourhood to modern
  asphalt streets, my approved child and sweeper images stayed exactly as chosen.

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
- **Result:** speech went from 104 s (11 of 12 shots, v2) to **54.5 s for all 12 shots** (v3, batched),
  so the planned film is 81 s. This is not a one-variable result: the text cut, the new style
  instruction and batched reading all changed together. All story beats and Grandma's exact words survived.

## E4. Can one request read a whole scene and still give one file per shot?

- **Hypothesis:** with "leave a clear pause of about two seconds between paragraphs" in the style, the
  pauses between lines will be clearly longer than pauses inside lines, so splitting at the longest
  pauses recovers the lines.
- **Change:** `narration.batches` = three scenes (s01–s05, s06–s09, s10–s12), one request each, lines
  joined as paragraphs.
- **Result 1 (hypothesis rejected):** the model ignored the pause instruction. In take s01–s05 the
  breaks between lines lasted 0.50–0.76 s, the same as pauses at full stops inside lines (0.50 s).
  Longest-pause splitting cut inside s04, giving it 2.5 s for 71 characters. The plausibility check
  (`SplitError`) caught this before any wrong audio was written.
- **Change 2:** estimate each break from the text (a line's share of the characters is roughly its share
  of the time), then snap to the nearest real pause, preferring longer ones. I re-split the cached take,
  so this cost no new request.
- **Result 2:** all three takes split and passed the check: s01–s05 = 5.0 / 5.1 / 3.2 / 7.4 / 3.0 s,
  s06–s09 = 4.7 / 3.3 / 2.3 / 1.6 s, s10–s12 = 6.1 / 5.7 / 6.9 s. Requests per full pass dropped from
  12 to 3. To be confirmed by ear: whether reading a scene as one take sounds more natural than isolated lines.
- **Result 3 (an edge case):** after s12 was reworded (F8), the new take s10–s12 failed the check
  (2.9 / 8.8 / 7.8 s). The model had paused 0.62 s at a mid-line «፤» in s10, but only **0.26 s** at the
  real break between s10 and s11. That was below the 0.3 s minimum, so the true break was not even a
  candidate. I lowered the minimum to 0.2 s. Regression check: re-splitting the two earlier takes with
  the new setting gave byte-identical files for all 9 lines, and the new take split as 5.9 / 6.3 / 7.8 s.
  The case is now a unit test.
