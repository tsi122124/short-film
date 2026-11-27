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

## How the audience shaped each decision

*Added 27 Nov 2026, after the first grading, to make the audience-to-decision link explicit. The
decisions themselves are unchanged; each row points to where it is implemented or measured.*

| What this audience needs | Decision | Where |
|---|---|---|
| They watch **on a phone, vertically, in a feed** | 9:16 is the main cut; keyframes are square so both aspect ratios crop from one image. Subtitles sit 400 px above the bottom, clear of the buttons and caption bar apps draw there | `assemble.ASPECTS`, ARCHITECTURE.md §7 |
| Feeds often play **with the sound off** | Every shot must work without sound; English subtitles are burned in, not optional | DESIGN.md "Show, don't tell", `write_subtitles` |
| **Diaspora viewers and colleagues** may not understand Amharic | Amharic narration (the family's language) with English subtitles, wrapped at 40 characters and 2 lines to stay readable on a phone | `subtitle_events`, test `test_subtitle_events_respect_two_lines_of_forty_chars` |
| A feed gives **seconds, not minutes**, of attention | 60–90 s, enforced by the storyboard validator; speech cut from 104 s to 54.5 s; the film opens on one striking image (a small girl, a giant broom) | `rule_problems`, E3 |
| **Family who knew my grandmother** will notice anything false | Her real goodbye «መጣሁ ልጄ፣ ቶሎ እመለሳለሁ» kept word for word; details checked against my aunt's memory; consent recorded for every real person | storyboard v2, v5; ETHICS.md |
| **Ethiopian viewers** will notice if it doesn't look Ethiopian | Concrete visual language (Habesha features, corrugated-iron roofs, blue-and-white minibuses), the real mourning dress code | F9, storyboard v4–v5 |
| **Native Amharic listeners** will hear any wrong word | Voice chosen by a native speaker's ear across 11 voices; mispronounced lines re-worded, not ignored | E1, F8 |
| The story touches **grief and a grandmother who has died** | Illustrated, not photorealistic; mourners anonymous; music falls silent at the reveal so the laugh has room | DESIGN.md decisions, music cue at s09 |

## Storyboard iterations before user testing

| Version | What changed | Why |
|---|---|---|
| v1 | First draft from my retelling | — |
| v2 | Age 5 → 8; the sweeper was bought **for my aunt** and she appears trying it (s01); a new shot of me still staring the next morning (s03); Grandma's real goodbye «መጣሁ ልጄ፣ ቶሎ እመለሳለሁ» replaces an invented «ደህና ሁኚ»; her black dress and netela turned down for mourning; wooden handle and corn-silk bristles | I corrected the draft against what actually happened, and my aunt remembers it the same way |
| v3 | Narration cut from ~113 s to ~70 s of speech; lines that repeat the picture removed (e.g. s09 is now just «…እኔ በሩ ላይ ብቅ አልኩ።»); Grandma and my aunt described as they really looked | The first measured TTS pass ran 104 s for 11 of 12 shots: a ~2-minute film. See FAILURES.md F3 |
| v3.1 | s12 now ends with a refrain: «…ያስቃል። አሁንም ያስቃል።» ("It still does.") | My own listen of the radio cut: the TTS mispronounced the final «ያስቃል». The refrain also gives the ending a rhythm. See FAILURES.md F8 |
| v3.2 | s12 opens «ውዷ አያቴ…» ("My dear grandmother…") | My own listen: «አያቴ» was mispronounced at the start of s12 only. The extra word fixed the reading and warmed the tribute (F8) |
| v3.3 | Music bed raised 6 dB (`music.bed_lufs` −26 → −20 LUFS, still ducked under the voice) | My own listen: the score was too quiet to carry any feeling |
| v4 | Concrete Ethiopian visual language: Habesha features and brown skin; me as a clearly 8-year-old girl with middle-parted braids and a well-made dress | My review of the first reference sheet: Mediterranean streets and faces, I looked 5, and the clothes looked cheap (FAILURES.md F9) |
| v5 | Grandma has two looks: at home, a patterned dress with a shawl; for the house of mourning, a black dress with a black veil wrapped around her head and neck, crossing her chest to the shoulder. My aunt wears casual everyday clothes. The neighbourhood is modern, with asphalt roads | My corrections and photos of how the mourning veil is worn. A netela with its ጥለት could not be drawn reliably, so I chose the black veil, which is also how women dress for a house of mourning |
| v6 | s01–s05 take place inside the home (`location: interior`) | My review: the home scenes must be inside the house (F10) |
| v7 | Grandma waves goodbye to the watching girl (s04); the girl reaches for the handle (s05); Grandma leads the walk and the crossing (s06, s07); laughter outside the house of mourning (s11); Grandma's portrait beside the sweeper (s12); the girl's hair as two braids; `face_from` keeps Grandma's face across her two outfits | My corrections to the v6.1 film. Then simplified so the image model can draw them: s06 and s11 show at most two people, and s12 describes the portrait in words (FAILURES.md F17). Keyframes made; film not yet re-rendered |
| v6.1 | s04 narration: «ነጠላዋን አዘቅዝቃ» ("her netela turned down") → «ጥቁር የሃዘን ልብስ ለብሳ» ("dressed in black for mourning"); the end card credits only the tools in this cut | The words must match the picture: since v5 Grandma wears a black dress and veil, not a netela. Credits must be true: this cut has camera moves, not Wan clips, and no generated score (F15) |

## User test: the published film, focused on the goodbye and the sweeper

*Run on 27 Nov 2026, after the first grading. The radio-cut test planned before the deadline was not run.*

**Setup.** The published 9:16 film (storyboard v6.1) sent over Telegram to three viewers, each answering
on their own. The test focused on the moment most likely to confuse people: why the girl picks up the
sweeper after Grandma's goodbye (s04–s07). Questions:

1. In one word, how did you feel at the end?
2. When Grandma says goodbye, why do you think the little girl picks up the sweeper and follows her?
3. Was there any moment you were confused?
4. Did any Amharic word sound wrong or unnatural?

Question 2 is open on purpose: viewers explain the moment in their own words, so I learn whether the
film made it clear without leading them.

| Viewer | Feeling | Why the girl took the sweeper (Q2) | Confused? (Q3) | Amharic (Q4) |
|---|---|---|---|---|
| A, a friend | Bittersweet | So excited about the new sweeper that she misunderstood Grandma's words, and believed Grandma wanted her to bring it | No; liked the contrast between the funny misunderstanding and the emotional ending | «መጣሁ ልጄ፣ ቶሎ እመለሳለሁ» sounds natural and correct |
| B, my brother | Hilarious | Obsessed with the sweeper; connected "I'll be back soon" to it and decided to follow | Briefly surprised when she walked into the house of mourning with it, and called that his favourite part | Nothing unnatural; Grandma's line sounded familiar |
| C, my mom | Heartwarming | Wanted to be part of whatever Grandma was doing; fascinated by the sweeper, she took the goodbye as an invitation | Understood, but would like the moment the girl misunderstands Grandma to be slightly clearer *visually* | The written Amharic is correct and natural; would need to hear the narration to judge pronunciation |

**What the test showed:**

- **3 of 3** explained the goodbye-and-sweeper moment correctly in their own words: a child so taken
  with the sweeper that she heard the goodbye as an invitation. The moment works.
- **0 of 3** were lost. Their one-word feelings (bittersweet, hilarious, heartwarming) match the intent
  above: a warm laugh and a grandmother's love. The surprise at the house of mourning landed as
  humour, not confusion (B).
- **1 of 3** (C) wanted the misunderstanding itself to be clearer in the picture, not only in the
  narration.
- **Amharic:** 2 of 3 found nothing unnatural. C commented on the written words only.

**What changes because of it.** C's comment points at the gap the v7 storyboard targets: in v7, Grandma
waves goodbye *to the watching girl* (s04) and the girl then reaches for the handle (s05), so her
decision to take the sweeper happens on screen. v7 was written from my own review before this test,
and the tested film is v6.1, which shows neither. Next step: render v7 and ask C the same question.

**Limits.** Three viewers, all close to me, so likely kind. Nobody from the part of the audience that
doesn't speak Amharic, so following the story from the English subtitles alone is still untested.
