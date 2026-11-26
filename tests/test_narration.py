import copy
import math
from array import array

import pytest

from pipeline import narration
from pipeline.storyboard import load_storyboard

RATE = 24_000


def tone(seconds: float) -> list[int]:
    return [int(8000 * math.sin(2 * math.pi * 220 * i / RATE)) for i in range(int(seconds * RATE))]


def silence(seconds: float) -> list[int]:
    return [0] * int(seconds * RATE)


def take(*parts: list[int]) -> bytes:
    return narration.pcm_to_wav(array("h", [s for part in parts for s in part]).tobytes(), RATE)


def test_split_take_cuts_at_the_long_pauses_not_the_short_ones():
    # line 1 has a short breath (0.3 s) inside it; lines are separated by 1.5 s pauses
    audio = take(silence(0.2), tone(1.0), silence(0.3), tone(1.0), silence(1.5), tone(1.0),
                 silence(1.5), tone(1.4), silence(0.2))
    lines = narration.split_take(audio, ["a" * 46, "b" * 22, "c" * 30])
    durations = [narration.wav_duration_s(line) for line in lines]
    assert len(lines) == 3
    assert durations[0] == pytest.approx(2.3 + 2 * narration.EDGE_PAD_S, abs=0.05)
    assert durations[1] == pytest.approx(1.0 + 2 * narration.EDGE_PAD_S, abs=0.05)
    assert durations[2] == pytest.approx(1.4 + 2 * narration.EDGE_PAD_S, abs=0.05)


def test_split_take_uses_the_text_when_all_pauses_look_alike():
    # As in real Gemini takes: pauses between lines (0.6 s) are barely longer than pauses at a full
    # stop inside a line (0.5 s), so only the text proportions can tell them apart.
    audio = take(silence(0.2), tone(1.0), silence(0.5), tone(2.0), silence(0.6), tone(1.5),
                 silence(0.6), tone(1.0), silence(0.5), tone(1.0), silence(0.2))
    lines = narration.split_take(audio, ["a" * 30, "b" * 15, "c" * 20])
    durations = [narration.wav_duration_s(line) for line in lines]
    assert durations == pytest.approx([3.5 + 2 * narration.EDGE_PAD_S, 1.5 + 2 * narration.EDGE_PAD_S,
                                       2.5 + 2 * narration.EDGE_PAD_S], abs=0.05)


def test_split_take_refuses_when_there_are_too_few_pauses():
    with pytest.raises(narration.SplitError, match="need 2"):
        narration.split_take(take(tone(1.0), silence(1.0), tone(1.0)), ["a", "b", "c"])


def test_split_take_refuses_an_implausible_split():
    # the text says line 2 is long, but the audio after the only pause is very short
    with pytest.raises(narration.SplitError, match="look wrong"):
        narration.split_take(take(tone(3.0), silence(1.0), tone(0.3)), ["a" * 10, "b" * 40])


def test_changing_one_line_only_invalidates_its_own_batch():
    board = load_storyboard()
    board["narration"]["batches"] = [["s01", "s02", "s03", "s04", "s05"], ["s06", "s07", "s08", "s09"],
                                     ["s10", "s11", "s12"]]
    before = {s["id"]: narration.narration_path(board, s, "am") for s in board["shots"]}
    edited = copy.deepcopy(board)
    edited["shots"][6]["narration"]["am"] += " ፈጥኜ።"  # s07, in the second batch
    after = {s["id"]: narration.narration_path(edited, s, "am") for s in edited["shots"]}
    changed = sorted(shot_id for shot_id in before if before[shot_id] != after[shot_id])
    assert changed == ["s06", "s07", "s08", "s09"]
