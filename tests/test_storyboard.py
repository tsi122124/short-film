import copy

import pytest

from pipeline import storyboard as sb


@pytest.fixture(scope="module")
def board():
    return sb.load_storyboard()


def test_real_storyboard_is_valid(board):
    assert 8 <= len(board["shots"]) <= 12


def test_schema_requires_consent_id_for_real_people(board):
    broken = copy.deepcopy(board)
    del broken["characters"][0]["consent_id"]
    assert any("consent_id" in p for p in sb.schema_problems(broken))


def test_rules_catch_duplicate_ids_and_unknown_placeholders(board):
    broken = copy.deepcopy(board)
    broken["shots"][1]["id"] = broken["shots"][0]["id"]
    broken["shots"][2]["image_prompt"] = "a portrait of {uncle} in the garden at noon"
    problems = " ".join(sb.rule_problems(broken))
    assert "duplicate shot ids" in problems
    assert "undefined placeholders ['uncle']" in problems


def test_rules_catch_face_from_pointing_at_an_unknown_character(board):
    broken = copy.deepcopy(board)
    broken["characters"][0]["face_from"] = "uncle"
    assert any("face_from refers to unknown character uncle" in p for p in sb.rule_problems(broken))


def test_rules_catch_a_film_that_is_too_long(board):
    broken = copy.deepcopy(board)
    for shot in broken["shots"]:
        shot["duration_s"] = 12
    assert any("outside 60-90s" in p for p in sb.rule_problems(broken))


ETHICS = """
### C1 — me
**Status:** granted

### C2 — grandmother
**Status:** pending
"""


def test_consent_status_is_read_per_record():
    assert sb.consent_status(ETHICS, "C1") == "granted"
    assert sb.consent_status(ETHICS, "C2") == "pending"
    assert sb.consent_status(ETHICS, "C9") is None


def test_consent_gate_blocks_real_person_without_granted_record(board, tmp_path):
    ethics = tmp_path / "ETHICS.md"
    ethics.write_text(ETHICS, encoding="utf-8")
    sb.require_consent(board, ["child"], ethics)  # C1 granted: allowed
    with pytest.raises(sb.ConsentError, match="grandmother"):
        sb.require_consent(board, ["child", "grandmother"], ethics)


def test_expand_prompt_fills_descriptions_and_style(board):
    shot = next(s for s in board["shots"] if "{sweeper}" in s["image_prompt"])
    prompt = sb.expand_prompt(board, shot)
    assert "{" not in prompt
    assert board["style_block"] in prompt
