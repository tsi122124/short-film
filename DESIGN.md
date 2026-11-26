# Design: audience, intent, and what the audience changed

## Audience and intent (written 2026-11-26, before any image was generated)

- **Who watches:** my family and neighbours, who know this story and still laugh about it; and young
  Ethiopians at home and in the diaspora who grew up close to a grandmother (my LinkedIn network, the
  TRP cohort on Slack).
- **Where:** on a phone, vertically, in a feed (LinkedIn, YouTube Shorts, shared on WhatsApp and Telegram).
- **What they should feel at the end:** a warm laugh at a child's innocent mistake; my grandmother's love;
  the neighbourly custom of going to comfort a grieving family; and a thought about their own grandmother.

**Define:** How might I keep my late grandmother's laugh alive for the family who remember her, and share
a small Ethiopian custom of care with people who never met her?

## Ideate: stories considered

| Option | Why not / why |
|---|---|
| A coffee ceremony in three rounds | Beautiful, but a ritual rather than a story; no turning point |
| A family proverb | Abstract; hard to show in pictures |
| **The sweeper** (chosen) | One unforgettable image (a child, a giant broom, an asphalt road, a house of mourning), a clear comic turn, few characters, and a real custom at its heart |

**The story in five sentences.** When I was eight, my grandmother bought my aunt a long wall sweeper and I
could not stop staring at it. The next morning Grandma put on her black dress, turned her netela down for
mourning, and left to comfort grieving neighbours, saying «መጣሁ ልጄ፣ ቶሎ እመለሳለሁ». I was so full of the
sweeper that I heard "bring the sweeper and follow me", so I carried it on my shoulder across the asphalt
road behind her. Just as she sat down in the house of mourning, I appeared at the door. She jumped up in
shock, then laughed, and sent me and the sweeper home with my aunt.

## Design decisions and their reasons

- **Voice-over film, no on-screen dialogue.** AI video cannot lip-sync Amharic convincingly; a narrator
  remembering the day is honest and keeps every shot about the picture.
- **Show, don't tell.** Every shot must work with the sound off; narration only adds what the picture
  cannot show (what I was thinking). Each shot's reason is written in `storyboard.json`.
- **Illustrated, not photorealistic.** Respect for a grandmother who has died (no realistic digital double),
  and illustration hides small identity drift between shots.
- **The sweeper is the motif.** It opens the film and closes it, as a tribute.
- **Music falls silent at the reveal (s09)** so the audience has room to laugh.
- **The mourners stay anonymous and out of focus.** The humour is about me, never about their grief.

## Storyboard iterations before user testing

| Version | What changed | Why |
|---|---|---|
| v1 | First draft from my retelling | — |
| v2 | Age 5 → 8; the sweeper was bought **for my aunt** and she appears trying it (s01); a new shot of me still staring the next morning (s03); Grandma's real goodbye «መጣሁ ልጄ፣ ቶሎ እመለሳለሁ» replaces an invented «ደህና ሁኚ»; her black dress and netela turned down for mourning; wooden handle and corn-silk bristles | I corrected the draft against what actually happened, and my aunt remembers it the same way |
| v3 | Narration cut from ~113 s to ~70 s of speech; lines that repeat the picture removed (e.g. s09 is now just «…እኔ በሩ ላይ ብቅ አልኩ።»); Grandma and my aunt described as they really looked | The first measured TTS pass ran 104 s for 11 of 12 shots: a ~2-minute film. See FAILURES.md F3 |

## User test 1: the radio cut

Narration over placeholder music on a black screen, 9:16, shared with at least three people from the
audience. Questions asked:

1. How did you feel at the end, in one word?
2. Was there any moment you were confused or lost?
3. Which line made you smile or laugh?
4. Did any Amharic word or name sound wrong or unnatural?
5. (Family only) Is anything different from how it really happened?

| # | Who (relationship, no names) | Watched on | What they said | What I will change |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

**Storyboard changes because of test 1:** _to be filled in._

## User test 2: the near-final cut

_To be filled in after the near-final cut._
