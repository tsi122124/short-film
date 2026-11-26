import copy

import pytest

from pipeline import keyframes
from pipeline.storyboard import fill_template, load_storyboard


@pytest.fixture(scope="module")
def board():
    return load_storyboard()


def shot(board, shot_id):
    return next(s for s in board["shots"] if s["id"] == shot_id)


def test_indoor_shots_never_get_the_street_setting(board):
    # Regression: the global street setting once overrode "inside the home" in s01-s04.
    prompt = keyframes.keyframe_prompt(board, shot(board, "s02"), [])
    assert board["interior_setting"] in prompt
    assert board["setting"] not in prompt


def test_reference_prompts_get_no_setting_at_all(board):
    prompt = fill_template(board, "Character reference sheet: {child}", location=None)
    assert board["setting"] not in prompt and board["interior_setting"] not in prompt
    assert board["style_block"] in prompt


def test_shot_references_are_characters_then_props_and_capped(board):
    refs = keyframes.shot_references(board, shot(board, "s01"))
    assert [r["id"] for r in refs] == ["grandmother_home", "aunt", "child", "sweeper"]
    crowded = copy.deepcopy(shot(board, "s01"))
    crowded["characters"].append("grandmother")
    with pytest.raises(ValueError, match="at most 4"):
        keyframes.shot_references(board, crowded)


def test_prompt_names_each_reference_by_its_image_index(board):
    s = shot(board, "s11")
    prompt = keyframes.keyframe_prompt(board, s, keyframes.shot_references(board, s))
    assert "the girl looks exactly like the one in image 0" in prompt
    assert "the broom looks exactly like the one in image 2" in prompt


def test_flagged_outputs_are_recognised():
    assert keyframes.is_flagged(Exception('400: {"errors":[{"message":"Your output has been flagged","code":3030}]}'))
    assert not keyframes.is_flagged(Exception("400: bad request"))
