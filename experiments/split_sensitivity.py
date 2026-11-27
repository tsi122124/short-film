"""Experiment E9: how sensitive is the narration splitter to its two thresholds?

Hypothesis: the shipped settings (silence below 6 % of loud speech, pauses of at least 0.2 s) are not a
lucky pick. Nearby settings should split all three cached scene takes into the same lines, and the
text-guided method should succeed where splitting at the longest pauses fails (EXPERIMENTS.md E4).

Uses only the cached takes in outputs/narration/<lang>/takes/, so it makes no TTS request.

Usage:
    uv run python experiments/split_sensitivity.py

Writes outputs/experiments/split_sensitivity/results.json and prints a summary table.
"""

from __future__ import annotations

import io
import json
import wave
from array import array
from itertools import pairwise, product

from pipeline import narration
from pipeline.core import OUTPUTS
from pipeline.storyboard import load_storyboard

OUT = OUTPUTS / "experiments" / "split_sensitivity"
SILENCE_RATIOS = (0.03, 0.06, 0.10)
MIN_PAUSES_S = (0.1, 0.2, 0.3, 0.5)


def durations(pieces: list[bytes]) -> list[float]:
    return [round(narration.wav_duration_s(p), 2) for p in pieces]


def split_longest_pauses(wav_bytes: bytes, texts: list[str]) -> list[float]:
    """The method E4 rejected: cut at the longest pauses, then apply the same plausibility check."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        rate = wav.getframerate()
        samples = array("h", wav.readframes(wav.getnframes()))
    frame = int(rate * narration.FRAME_S)
    levels = narration._frame_levels(samples, frame)
    loud = sorted(levels)[int(len(levels) * 0.95)]
    silent = [level < loud * narration.SILENCE_RATIO for level in levels]
    pauses, start = [], None
    for i, is_silent in enumerate([*silent, False]):
        if is_silent and start is None:
            start = i
        elif not is_silent and start is not None:
            if start > 0 and i < len(silent) and (i - start) * narration.FRAME_S >= narration.MIN_PAUSE_S:
                pauses.append((start, i))
            start = None
    needed = len(texts) - 1
    if len(pauses) < needed:
        raise narration.SplitError(f"found {len(pauses)} pauses, need {needed}")
    chosen = sorted(sorted(pauses, key=lambda p: p[1] - p[0], reverse=True)[:needed])
    bounds = [0, *[(a + b) // 2 for a, b in chosen], len(silent)]
    lengths = []
    for lo, hi in pairwise(bounds):
        voiced = [i for i in range(lo, hi) if not silent[i]]
        lengths.append((voiced[-1] - voiced[0] + 1) * frame if voiced else 0)
    for text, length in zip(texts, lengths):
        ratio = (length / sum(lengths)) / (len(text) / sum(len(t) for t in texts))
        if not 1 / narration.MAX_SHARE_RATIO <= ratio <= narration.MAX_SHARE_RATIO:
            raise narration.SplitError(f"line lengths look wrong ({[round(n / rate, 1) for n in lengths]} s)")
    return [round(n / rate, 2) for n in lengths]


def main() -> None:
    storyboard = load_storyboard()
    lang = storyboard["language"]
    takes = []
    for batch in narration.batches(storyboard):
        inputs = narration.batch_inputs(storyboard, batch, lang)
        path = narration.take_path(batch, inputs)
        takes.append((f"{batch[0]}-{batch[-1]}", path.read_bytes(), [text for _, text in inputs["lines"]]))

    shipped = {name: durations(narration.split_take(wav, texts)) for name, wav, texts in takes}
    defaults = (narration.SILENCE_RATIO, narration.MIN_PAUSE_S)
    grid = []
    for ratio, min_pause in product(SILENCE_RATIOS, MIN_PAUSES_S):
        narration.SILENCE_RATIO, narration.MIN_PAUSE_S = ratio, min_pause
        row = {"silence_ratio": ratio, "min_pause_s": min_pause, "takes": {}}
        for name, wav, texts in takes:
            try:
                got = durations(narration.split_take(wav, texts))
                drift = max(abs(a - b) for a, b in zip(got, shipped[name]))
                row["takes"][name] = {"ok": True, "durations_s": got, "max_drift_s": round(drift, 2)}
            except narration.SplitError as err:
                row["takes"][name] = {"ok": False, "error": str(err)}
        grid.append(row)
    narration.SILENCE_RATIO, narration.MIN_PAUSE_S = defaults

    longest = {}
    for name, wav, texts in takes:
        try:
            longest[name] = {"ok": True, "durations_s": split_longest_pauses(wav, texts)}
        except narration.SplitError as err:
            longest[name] = {"ok": False, "error": str(err)}

    OUT.mkdir(parents=True, exist_ok=True)
    results = {"shipped_settings": {"silence_ratio": defaults[0], "min_pause_s": defaults[1]},
               "shipped_durations_s": shipped, "grid": grid, "longest_pause_method": longest}
    (OUT / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    names = [name for name, _, _ in takes]
    print("silence  min pause  " + "  ".join(f"{n:>16}" for n in names))
    for row in grid:
        cells = []
        for n in names:
            t = row["takes"][n]
            if not t["ok"]:
                verdict = "refused"
            elif t["max_drift_s"] <= 0.1:
                verdict = "same"
            else:
                verdict = f"moved {t['max_drift_s']:.1f}s"
            cells.append(f"{verdict:>16}")
        mark = "  <- shipped" if (row["silence_ratio"], row["min_pause_s"]) == defaults else ""
        print(f"{row['silence_ratio']:>7}  {row['min_pause_s']:>9}  " + "  ".join(cells) + mark)
    print("longest-pause method: " + ", ".join(f"{n}: {'ok' if v['ok'] else 'refused'}" for n, v in longest.items()))


if __name__ == "__main__":
    main()
