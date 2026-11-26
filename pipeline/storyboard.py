"""Load storyboard.json, validate it against the JSON Schema, then check the rules a schema cannot express.

Every stage calls load_storyboard() first, so no stage ever runs on a broken contract.
"""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pipeline.core import ROOT

STORYBOARD_PATH = ROOT / "storyboard.json"
SCHEMA_PATH = ROOT / "schema" / "storyboard.schema.json"
ETHICS_PATH = ROOT / "ETHICS.md"

FILM_MIN_S, FILM_MAX_S = 60, 90


class StoryboardError(ValueError):
    """The storyboard breaks the contract. The message lists every problem found."""


class ConsentError(PermissionError):
    """A real person would be generated without a granted consent record in ETHICS.md."""


def load_storyboard(path: Path = STORYBOARD_PATH) -> dict[str, Any]:
    storyboard = json.loads(path.read_text(encoding="utf-8"))
    problems = schema_problems(storyboard)
    if not problems:  # the rule checks assume a schema-valid shape
        problems = rule_problems(storyboard)
    if problems:
        raise StoryboardError(f"{path.name} is invalid:\n  - " + "\n  - ".join(problems))
    return storyboard


def schema_problems(storyboard: dict[str, Any]) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(storyboard), key=lambda e: e.json_path)
    return [f"{e.json_path}: {e.message}" for e in errors]


def placeholders(template: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def rule_problems(storyboard: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    shots = storyboard["shots"]
    shot_ids = [s["id"] for s in shots]
    character_ids = {c["id"] for c in storyboard["characters"]}
    prop_ids = {p["id"] for p in storyboard["props"]}
    lang = storyboard["language"]

    duplicates = sorted({i for i in shot_ids if shot_ids.count(i) > 1})
    if duplicates:
        problems.append(f"duplicate shot ids: {duplicates}")
    if character_ids & prop_ids:
        problems.append(f"ids used for both a character and a prop: {sorted(character_ids & prop_ids)}")
    for item in [*storyboard["characters"], *storyboard["props"]]:
        if "reference" in item:
            missing = placeholders(item["reference"]["prompt"]) - character_ids - prop_ids
            if missing:
                problems.append(f"{item['id']}: reference prompt uses undefined placeholders {sorted(missing)}")

    for shot in shots:
        unknown = set(shot["characters"]) - character_ids
        if unknown:
            problems.append(f"{shot['id']}: unknown characters {sorted(unknown)}")
        missing = placeholders(shot["image_prompt"]) - character_ids - prop_ids
        if missing:
            problems.append(f"{shot['id']}: image_prompt uses undefined placeholders {sorted(missing)}")
        shown = placeholders(shot["image_prompt"]) & character_ids
        if shown - set(shot["characters"]):
            problems.append(f"{shot['id']}: prompt shows {sorted(shown)} but 'characters' does not list them")
        if lang not in shot["narration"]:
            problems.append(f"{shot['id']}: narration has no '{lang}' line")

    position = {shot_id: i for i, shot_id in enumerate(shot_ids)}
    for cue in storyboard["music"]["cues"]:
        start, end = position.get(cue["from_shot"]), position.get(cue["to_shot"])
        if start is None or end is None:
            problems.append(f"music cue {cue['id']}: refers to a shot that does not exist")
        elif start > end:
            problems.append(f"music cue {cue['id']}: from_shot comes after to_shot")

    chosen = storyboard["music"]["chosen_seed"]
    if chosen is not None and chosen not in storyboard["music"]["candidate_seeds"]:
        problems.append("music.chosen_seed is not one of music.candidate_seeds")

    planned = sum(s["duration_s"] for s in shots) + storyboard["end_card"]["duration_s"]
    if not FILM_MIN_S <= planned <= FILM_MAX_S:
        problems.append(f"planned length {planned:.1f}s is outside {FILM_MIN_S}-{FILM_MAX_S}s")
    return problems


def consent_status(ethics_text: str, consent_id: str) -> str | None:
    """Read the status of a consent record written as '### C1 ...' followed by '**Status:** granted'."""
    section = re.search(rf"^### {re.escape(consent_id)}\b(.*?)(?=^### |\Z)", ethics_text, re.MULTILINE | re.DOTALL)
    if not section:
        return None
    status = re.search(r"\*\*Status:\*\*\s*([A-Za-z]+)", section.group(1))
    return status.group(1).lower() if status else None


def require_consent(storyboard: dict[str, Any], character_ids: list[str], ethics_path: Path = ETHICS_PATH) -> None:
    """Consent gate: refuse to generate any real person whose consent is not granted in ETHICS.md."""
    ethics_text = ethics_path.read_text(encoding="utf-8") if ethics_path.exists() else ""
    by_id = {c["id"]: c for c in storyboard["characters"]}
    blocked = []
    for cid in character_ids:
        character = by_id[cid]
        if not character["real_person"]:
            continue
        status = consent_status(ethics_text, character["consent_id"])
        if status != "granted":
            blocked.append(f"{cid} (record {character['consent_id']}: {status or 'missing'})")
    if blocked:
        raise ConsentError("No granted consent in ETHICS.md for: " + ", ".join(blocked))


def fill_template(storyboard: dict[str, Any], template: str) -> str:
    """Fill {character}/{prop} placeholders with their fixed descriptions and append the style block.

    Every prompt goes through here, so a character is described with exactly the same words everywhere.
    """
    descriptions = {c["id"]: c["description"] for c in storyboard["characters"]}
    descriptions.update({p["id"]: p["description"] for p in storyboard["props"]})
    return f"{template.format(**descriptions)}. {storyboard['style_block']}"


def expand_prompt(storyboard: dict[str, Any], shot: dict[str, Any]) -> str:
    return fill_template(storyboard, shot["image_prompt"])


def main() -> None:
    storyboard = load_storyboard()
    planned = sum(s["duration_s"] for s in storyboard["shots"]) + storyboard["end_card"]["duration_s"]
    print(f"storyboard.json is valid: {len(storyboard['shots'])} shots, planned {planned:.1f}s")


if __name__ == "__main__":
    main()
