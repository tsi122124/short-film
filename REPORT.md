# The Sweeper (መጥረጊያው): a heritage short made by a pipeline

**TRP2 Week 0 — AI-Content Generation: The Heritage Short** · Tsion · 26 November 2026

| | |
|---|---|
| Code | https://github.com/tsi122124/short-film |
| Film, 9:16 | ⟪link⟫ |
| Film, 16:9 | ⟪link⟫ |
| Public post | ⟪LinkedIn post link⟫ |

## 1. Summary

*The Sweeper* is an 82-second film, narrated in Amharic with English subtitles, about a morning when I was
eight. I mistook my grandmother's goodbye for an instruction and carried a brand-new wall sweeper across
an asphalt road into a neighbour's house of mourning. My family still laughs about it. My grandmother
has since died, and the film is a small tribute to her laugh and to the Ethiopian custom of going to
comfort grieving neighbours.

The film is not edited by hand. One file, `storyboard.json`, holds every narration line, prompt, seed,
model id and music cue. It is validated against a JSON Schema, and a single command, `uv run film`,
turns it into both aspect ratios. Every model call is cached by a hash of its inputs, retried when that
makes sense, and logged with its parameters, seed, latency and cost. In total the film cost **$0.00**
(≈ $0.16 at list price), and a full regeneration costs ≈ $0.025.

## 2. Audience and story

**Audience.** My family and neighbours, who know the story, and young Ethiopians at home and in the
diaspora who grew up close to a grandmother. They watch on a phone, vertically, in a feed.

**Intent.** At the end they should feel a warm laugh at a child's innocent mistake, my grandmother's
love, and a thought about their own grandmother.

**Why this story.** I considered a coffee ceremony and a family proverb. I chose the sweeper because it
has one unforgettable image (a small girl, a giant broom, an asphalt road, a house of mourning), a clear
comic turn, few characters, and a real custom at its heart.

**Design rules I followed** (DESIGN.md):
- Voice-over, no on-screen dialogue, because AI video cannot lip-sync Amharic convincingly.
- Every shot must work with the sound off. Narration adds only what the picture cannot show.
- Illustrated gouache style, not photorealism, out of respect for a grandmother who has died.
- The sweeper opens and closes the film. The music falls silent at the reveal so there is room to laugh.
- The mourners stay anonymous. The joke is on me, never on their grief.

## 3. How the pipeline works

```
storyboard.json ─► validate ─► narration ─► keyframes ─► shots ─► assemble ─► film_9x16.mp4
   (contract)      schema +    Gemini TTS   FLUX.2 klein  Ken Burns  FFmpeg     film_16x9.mp4
                   rules +     (Amharic)    + approved    or Wan 2.2 duck, mix,
                   consent                  references   (Kaggle)   subtitles, loudnorm
```

The full design is in ARCHITECTURE.md. These five decisions matter most:

1. **One contract, checked before anything is spent.** JSON Schema plus rule checks the schema cannot
   express: duplicate ids, `{placeholders}` naming no character, a length outside 60–90 s. A typo fails
   in a second instead of after ten paid image calls.
2. **Caching by input hash.** Each output's file name contains a SHA-256 of every input that affects it,
   and the hashes chain. A keyframe's key includes the content hash of its reference images, so
   replacing Grandma's approved reference regenerates exactly the shots she appears in. Editing one
   narration line regenerates one scene batch; everything else is reused.
3. **Retries that read the error.** Four attempts with exponential backoff for 429, 5xx and network
   errors; a 400 fails immediately. Two exceptions were learned the hard way: a Cloudflare 429 with code
   4006 means "daily allocation used up" and fails fast, since no retry can help before midnight UTC; and
   every TTS attempt gets a hard 90-second deadline, because the SDK's own timeout once let a call hang
   for 15 minutes.
4. **Everything is logged.** 196 calls in `runs.jsonl`, including failures and retries, with secrets
   redacted and provider replies filtered through an allowlist.
5. **Consent is enforced in code.** The keyframe stage refuses to draw any character marked
   `real_person: true` unless that person's record in ETHICS.md says `granted`.

**Character consistency without training.** I first generate a reference sheet (three candidates per
character), approve one, and pin it. Then I attach the approved references to every keyframe and name
them in the prompt ("the girl looks exactly like the one in image 0"). The girl and the sweeper stayed
recognisable across all 12 shots (E5).

**Audio.** Voice and music are each normalised to a set loudness before mixing (−16 / −20 LUFS). The music
follows a per-cue envelope (playful, then a hush in the house of mourning, then silence at the reveal) and
is side-chain ducked under the voice. The master gets a two-pass `loudnorm` to −14 LUFS and −1.5 dBTP.
Measured on the delivered MP4s, not the intermediate master: **−14.07 LUFS and −1.33 dBTP** in both
aspect ratios (E8). The AAC encoder raised the peak by 0.17 dB, which is why the master aims 0.5 dB
under the −1 dBTP limit.

## 4. What the experiments showed

| # | Question | Result |
|---|---|---|
| E1 | Which TTS voice sounds like natural Amharic? | A teammate recommended Addis AI. In my comparison of 11 voices, Gemini *Sulafat* with a story-telling style instruction sounded the most natural and expressive. It was also the slowest voice. |
| E2 | Does the style prompt control pace? | No: removing "slow" made the line longer (8.70 → 9.36 s). The lever for length is the script. |
| E3 | Can the script fit 60–90 s? | Cutting every phrase the picture already shows took speech from 104 s to 54.5 s, with every story beat and Grandma's exact words kept. |
| E4 | Can one request read a whole scene and still give one file per shot? | The model ignored "pause between paragraphs", so splitting at the longest pause failed, and the plausibility check caught it. Estimating breaks from the text, then snapping to real pauses, worked: 3 requests per pass instead of 12. |
| E5 | Do reference images keep characters consistent? | Yes for the girl and the sweeper. With four references the model mixed people up until I gave explicit positions. |
| E6 | Edit an approved image or generate fresh? | Edits keep the face but also the old clothes. Best: fresh outfit, then a two-image edit for the face, then single-change edits. |
| E7 | Should references include the setting? | No. Splitting look from place meant I could modernise the streets without changing approved faces. |
| E8 | Does the delivered MP4 still meet −14 LUFS / −1 dBTP? | Yes: −14.07 LUFS, −1.33 dBTP. Encoding added 0.17 dB of peak; mastering to exactly −1.0 would have failed. |

## 5. What failed and what it taught me

FAILURES.md has 16 entries. Four shaped the system:

- **Free-tier caps hit on the same day** (F7, F14). Gemini TTS allows 10 requests a day and Cloudflare
  10,000 neurons. Batching narration by scene cut 12 requests to 3. When the image cap was hit, the
  cache meant the film could still be assembled with zero image calls. *Lesson: a 429 is not always
  "slow down"; read the error code before retrying.*
- **A TTS call hung for 15 minutes** (F4), even with a timeout set. The fix was a hard per-attempt
  deadline in a daemon thread, because a library's timeout setting does not cover every code path.
- **"Ethiopian" came out Mediterranean** (F9), and the street setting overrode "inside the home" (F10).
  Concrete visual language (Habesha features, warm brown skin) and separate interior and exterior
  settings fixed both. A unit test now guards the second.
- **Free GPUs are not guaranteed** (F15). Both Kaggle jobs (Wan 2.2 motion and ACE-Step music) waited
  in the queue for over five hours. The pipeline was built to degrade: shots without a matching Wan clip
  get a Ken Burns camera move, rendered locally. ⟪Music: generated on Colab instead / see below⟫

I also found and fixed a logging bug while preparing this report. The Addis AI reply carries the audio
as base64 and a signed link, and both were going into `runs.jsonl` (6.4 MB). Replies are now logged
through an allowlist, and the log is 194 KB.

## 6. User tests and what changed

Storyboard iterations v1 → v6 came from my own review against what really happened, and from my aunt's
memory of the day (DESIGN.md has the full table). The two audience tests:

**Test 1, radio cut** (narration and music on black, 9:16): ⟪who, how many, what they said⟫
→ changes: ⟪…⟫

**Test 2, near-final cut**: ⟪who, how many, what they said⟫ → storyboard v7: Grandma visibly leads the
walk and the road crossing, the aunt joins the laughter in s11, s12 shows Grandma's portrait beside the
sweeper, and s05 shows the girl actually reaching for the handle. v7 also adds `face_from`, so one person
keeps the same face across two outfits. It is committed on the branch `feat/storyboard-v7` and needs
about 1,400 image neurons, which the daily cap made unavailable before the deadline.

## 7. Ethics

- **Consent.** Three real people appear: me (self-consent), my late grandmother (consent from my aunt,
  as close family), and my aunt. All records are in ETHICS.md, and the pipeline refuses to generate a
  real person without one.
- **No family photograph was uploaded to any model.** Characters come from written descriptions only.
- **No cloned voice.** The narration uses a prebuilt synthetic voice, and Grandma's only words are the
  goodbye she actually said.
- **Labelling.** The film ends on a "Made with AI" card that names each model, so the label travels
  with the video when it is reshared. It is posted on LinkedIn, which has no AI toggle, so the first line
  of the post is the disclosure (F6).
- **Honest credits.** The end card names only the tools actually used in this cut.

## 8. Limitations and next steps

- **Render v7** after the image quota resets, then run the Wan 2.2 job so the key shots move instead of
  using camera moves.
- **Faces still drift** between shots, Grandma's most. A character LoRA, or a larger image model, is the
  next step for identity.
- **The voice choice rests on one listener.** A blind test with five or more Amharic speakers is
  scripted (`--blind`) but not yet run.

## 9. Reflection

⟪Your own words, about half a page. Prompts: What was hardest, and what did you do about it? What
would you do differently on day one? Where did the coding agent help, and where did you have to
overrule it? What did making a film about your grandmother feel like?⟫
