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


def ref_ids(refs):
    return [entry["item"]["id"] for entry in refs]


def test_shot_references_are_characters_then_props_and_capped(board):
    refs = keyframes.shot_references(board, shot(board, "s01"))
    assert ref_ids(refs) == ["grandmother_home", "aunt", "child", "sweeper"]
    crowded = copy.deepcopy(shot(board, "s01"))
    crowded["characters"].append("grandmother")
    with pytest.raises(ValueError, match="at most 4"):
        keyframes.shot_references(board, crowded)


def test_face_from_adds_the_face_image_before_the_clothes_image(board):
    # s04: grandmother (mourning look, face_from grandmother_home) and the girl; room for both images
    refs = keyframes.shot_references(board, shot(board, "s04"))
    assert ref_ids(refs) == ["grandmother_home", "grandmother", "child"]
    assert refs[1].get("optional") is True


def test_clothes_image_is_dropped_first_at_the_reference_cap(board):
    # five images (face, clothes, aunt, girl, broom) for a 4-image model: only the optional clothes image goes
    s = copy.deepcopy(shot(board, "s11"))
    s["characters"] = ["grandmother", "aunt", "child"]
    refs = keyframes.shot_references(board, s)
    assert ref_ids(refs) == ["grandmother_home", "aunt", "child", "sweeper"]
    prompt = keyframes.keyframe_prompt(board, s, refs)
    assert "the grandmother has exactly the face, skin tone and hair of the person in image 0" in prompt
    assert "the girl looks exactly like the one in image 2" in prompt
    assert "the broom looks exactly like the one in image 3" in prompt
    assert "wears exactly the clothes" not in prompt


def test_flagged_outputs_are_recognised():
    assert keyframes.is_flagged(Exception('400: {"errors":[{"message":"Your output has been flagged","code":3030}]}'))
    assert not keyframes.is_flagged(Exception("400: bad request"))
