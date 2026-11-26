# Ethics: consent, privacy, licences and labelling

This film retells a true family story about three real people: me as an eight-year-old, my late
grandmother, and my aunt. This file records how each ethical question was handled. The consent records are read
by the pipeline itself (`pipeline/storyboard.py::require_consent`): the keyframe stage refuses to
generate a character marked `real_person: true` in `storyboard.json` unless their record below says
`**Status:** granted`.

## Consent records

Each record states who consented, to what exact use, how the consent was captured, and when.

### C1 — The narrator as a child (myself)

- **Person:** Tsion, the author of this film, shown as an eight-year-old.
- **Use:** an illustrated (not photorealistic) likeness of me as a child in keyframes and moving shots;
  the narration is my own account, written by me, read by a synthetic voice.
- **Captured:** self-consent, 2026-11-26.
- **Status:** granted

### C2 — My late grandmother

My grandmother has passed away and cannot consent herself. Following common practice for depicting
a deceased person, consent was asked of close family: my aunt, who is also part of the story.

- **Consenting family member:** my aunt.
- **What she agreed to:** telling this story in a short film made with AI, with my grandmother shown as
  an illustrated (not photorealistic) character built from a written description only, never from a
  photograph, and shared publicly. The only words attributed to my grandmother are the goodbye she
  actually said, «መጣሁ ልጄ፣ ቶሎ እመለሳለሁ» ("I'll be right back, my child"), as my aunt and I remember it.
- **Captured:** by phone on Tuesday 2026-11-24, when the challenge was set and this story came up.
  My aunt granted it for my grandmother's depiction and for her own (record C3).
- **Status:** granted

Grandma appears in two looks (`grandmother` in mourning clothes, `grandmother_home` at home). Both are
the same person, and both are covered by this record.

### C3 — My aunt

- **Person:** my aunt, for whom the sweeper was bought, shown trying it on the wall (shot s01) and
  named in the narration as the one who took me home (shot s11).
- **Use:** an illustrated (not photorealistic) likeness built from a written description only, in the
  film and its public post. She is never voiced.
- **Captured:** by phone in the same call on Tuesday 2026-11-24.
- **Status:** granted

## How real people are depicted

- **No photograph of my family is uploaded to any model.** The characters are generated from short written
  descriptions in `storyboard.json`, never from a family photo, so no model receives a real family face.
- **One garment reference photo, used with permission.** To show how an Ethiopian mourning veil is worn,
  I used one photo of women at a mourning gathering, with the consent of the photo's owner. Before use it
  was cropped to a single woman seen from behind, with no face visible, so the model received only the
  veil's drape. It is kept privately in the gitignored `assets/private/`, is not published in this
  repository, and nobody in it appears in the film. Once Grandma's mourning reference was approved, that
  image was pinned, so the photo is no longer needed to regenerate the film.
- **Illustrated, not photorealistic.** A hand-painted gouache style was chosen out of respect for my
  grandmother (no realistic digital double of a person who has died) and because illustration hides
  the small identity drift that image models show between shots.
- **No cloned voices.** The narration uses a prebuilt synthetic Gemini TTS voice, not a recording or
  clone of any real person's voice.
- **The mourning family stays anonymous.** The neighbours who were grieving are shown only softly,
  from behind and out of focus, and are never named. The humour is about a child's mistake, never
  about their grief.

## Private data

Free endpoints may use submitted data to train models: the Gemini API free tier, and Addis AI, whose
terms (s6) allow training on submitted text and audio with no self-service opt-out. Prompts and
narration therefore contain no real names, no neighbourhood or street names, and no other identifying
details: the characters are "Grandma", "the child" and "my aunt". The narration is written to be
published anyway, so sending it to a TTS provider discloses nothing beyond the film itself.

## Licences

Checked 2026-11-26 from the sources linked; re-check if a model is swapped.

| Component | Model / tool | Licence / terms | Output use |
|---|---|---|---|
| Narration | `gemini-3.8-flash-tts` (Gemini API) | [Gemini API terms](https://ai.google.dev/gemini-api/terms) | Free tier; outputs usable, with AI disclosure |
| Narration (comparison) | Addis AI "Addis Voices 2" | [Addis AI terms](https://addisassistant.com/terms): output rights assigned to user (s5); commercial use for paid API customers (s4); synthetic audio must be disclosed (s8) | Experiment only unless it wins the blind test |
| Keyframes | `@cf/black-forest-labs/flux-2-klein-4b` (Cloudflare Workers AI) | Apache-2.0 (Hugging Face model card); Cloudflare links [BFL terms](https://bfl.ai/legal/terms-of-service) | Permissive. The 9B variant is non-commercial and is deliberately not used |
| Moving shots | Wan 2.2 TI2V-5B | Apache 2.0 | Permissive |
| Score | ACE-Step 1.5 | MIT; trained on licensed, royalty-free and synthetic data | Outputs usable commercially |
| Assembly | FFmpeg | LGPL/GPL (tool only, not distributed) | n/a |

## Labelling plan

- A visible end card states the film was made with AI and names each model.
- **LinkedIn has no manual AI-disclosure toggle** (its help page describes only automatic Content
  Credentials / C2PA detection: https://www.linkedin.com/help/linkedin/answer/a6282984). So:
  - the film is posted on **YouTube Shorts with "AI use: Yes" switched on** in YouTube Studio, which
    satisfies "post with the platform's AI label switched on"
    (https://support.google.com/youtube/answer/14328491);
  - the LinkedIn post carries the film plus an explicit written disclosure in its first line
    ("Made with AI: ...") and links the labelled YouTube version.
- Watermarks and provenance metadata from the models are left intact.
