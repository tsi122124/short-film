# The Sweeper (መጥረጊያው): a heritage short made by a pipeline

**TRP2 Week 0 — AI-Content Generation: The Heritage Short** · Tsion · 26 November 2026

> **Revised 27 November 2026, after the first grading.** Added: three measured experiments (E9–E11),
> time per stage, GPU minutes and a frontier-model cost comparison (COSTS.md), and an explicit table of
> how the audience shaped each decision (DESIGN.md). The empty user-test placeholders were replaced by
> a plain statement that the tests were not run (§6). Nothing in the film or the pipeline changed.

**Code:** https://github.com/tsi122124/short-film. The films (9:16 and 16:9) and the public post are
submitted separately.

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
(≈ $0.20 at list price for all 287 logged attempts), and a full regeneration costs ≈ $0.025 and about
35 minutes, of which only 3.5 are model calls.

## 2. Audience and story

**Audience.** My family and neighbours, who know the story, and young Ethiopians at home and in the
diaspora who grew up close to a grandmother. They watch on a phone, vertically, in a feed.

**Intent.** At the end they should feel a warm laugh at a child's innocent mistake, my grandmother's
love, and a thought about their own grandmother.

**How the audience shaped the film.** Because they watch on a phone in a feed, 9:16 is the main cut and
subtitles sit above the app's buttons. Because feeds often play muted, every shot works without sound
and English subtitles are burned in, which also serves diaspora viewers who don't speak Amharic. Because
a feed gives seconds of attention, the film is 82 s and opens on one striking image. Because family will
notice anything false, Grandma's real words are kept exactly. The full table, with where each decision
is implemented, is in DESIGN.md ("How the audience shaped each decision").

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
4. **Everything is logged.** 287 attempts in `runs.jsonl`, including failures and retries, with secrets
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

Eleven questions, each with a hypothesis, one change and a measured result (EXPERIMENTS.md):

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
| E9 | Is the narration splitter fragile? | No: 33 of 36 re-splits across 12 threshold settings gave the same lines. A 0.5 s minimum pause broke it, and twice the plausibility check missed a boundary 1.4 s off, so listening stays part of the process. |
| E10 | Which x264 preset suits a 2-core laptop? | The shipped `veryfast`: 99.7 % of `medium`'s SSIM in 43 % of the time. `ultrafast` was 1.8× faster but its file 9× larger. |
| E11 | Does upscaling 2× before the camera move earn its cost? | Yes: frozen frames in a slow push-in dropped from 18 to 0 for 27 % more encode time; 3× added little for another 58 %. |

**Cost and time** (COSTS.md). All model calls together took 41 minutes; FFmpeg on the laptop took 187.
GPU time was 0 minutes: both Kaggle jobs stayed in the queue. Against frontier models, images would cost
50–100× more and video $5–24 per film with Veo 3.1, while narration costs cents with any option. The
upgrade worth paying for first is a larger image model for the three F17 shots, about $0.20–0.40.

## 5. What failed and what it taught me

FAILURES.md has 17 entries. Four shaped the system:

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
  get a Ken Burns camera move, rendered locally. The music had no such second source in time, so this
  cut uses the pipeline's placeholder bed, still shaped by the storyboard's music cues and ducked under
  the voice. The end card credits only the tools actually used.

I also found and fixed a logging bug while preparing this report. The Addis AI reply carries the audio
as base64 and a signed link, and both were going into `runs.jsonl` (6.4 MB). Replies are now logged
through an allowlist, and the log is 194 KB.

## 6. User tests and what changed

Storyboard iterations v1 → v7 came from my own review against what really happened and from my
aunt's memory of the day (DESIGN.md has the full table).

**The two planned audience tests were not run before the deadline.** So far the film has been judged
by two people who know the story, my aunt and me, not by the wider audience it is for. The protocol
is ready in DESIGN.md: five questions, at least three viewers per cut, answers recorded by
relationship. The first things I would want to learn: whether viewers who don't speak Amharic can
follow from the subtitles alone, and whether the reveal at s09 gets the laugh the silence leaves room for.

**Storyboard v7: keyframes made, film not yet re-rendered.** Grandma waves goodbye to the watching
girl, the girl reaches for the handle, Grandma leads the walk and the road crossing, and s12 shows
Grandma's portrait beside the sweeper. v7 also adds `face_from`, so one person keeps the same face across
two outfits. Three-person shots failed on every seed, because the image model merges people, so s06 and
s11 were simplified to at most two people (F17). The published film is still v6.1.

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
  using camera moves, and the ACE-Step job to replace the placeholder music.
- **Faces still drift** between shots, Grandma's most. A character LoRA, or a larger image model, is the
  next step for identity.
- **The voice choice rests on one listener.** A blind test with five or more Amharic speakers is
  scripted (`--blind`) but not yet run.

## 9. Reflection

The hardest parts were the quotas and the images. Both free tiers ran out on the same day, so I had to
batch the narration and rely on the cache to keep going (F7, F14). The images were harder: a character
would look right in one shot and different in the next, and shots with three people never came out
right at all (E5, F17). I learned to fix each character's look first with approved reference images,
and to ask the model only for what it can actually draw.

If I started again, on day one I would get Kaggle ready. My GPU jobs went into the queue on the last
afternoon and never started, so this cut uses camera moves instead of real motion, and a placeholder
music bed instead of a generated score (F15).

The coding agent wrote the code fast, and it helped me see things from angles I didn't see myself. But
some things only I could judge: whether the Amharic sounded natural, which words were mispronounced,
and whether a picture matched what really happened and how my grandmother really dressed (E1, F8, and
storyboard v2–v7).

Making this film was a great experience. It made me remember my grandmother and that morning.
