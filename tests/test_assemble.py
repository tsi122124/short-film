from pipeline import assemble


def test_subtitle_events_respect_two_lines_of_forty_chars():
    text = ("The next morning, around ten, Grandma got ready to go and comfort our neighbours, "
            "who were in mourning. She said bye.")
    events = assemble.subtitle_events(text)
    assert all(len(event) <= 2 for event in events)
    assert all(len(line) <= 40 for event in events for line in event)
    assert " ".join(" ".join(e) for e in events) == text


def test_envelope_expression_hits_its_points():
    points = [(0.0, 0.0), (1.0, 1.0), (5.0, 1.0), (6.0, 0.0)]
    expr = assemble.envelope_expr(points)

    def evaluate(t):  # FFmpeg's if(cond,a,b) and lt(x,y), evaluated in Python
        py = expr.replace("if(", "_if(").replace("lt(", "_lt(")
        return eval(py, {"_if": lambda c, a, b: a if c else b, "_lt": lambda x, y: x < y, "t": t})

    assert evaluate(0.0) == 0.0
    assert abs(evaluate(0.5) - 0.5) < 1e-9
    assert evaluate(3.0) == 1.0
    assert abs(evaluate(5.5) - 0.5) < 1e-9
    assert evaluate(7.0) == 0.0


def test_music_cues_set_per_shot_levels():
    board = {
        "shots": [{"id": "s01"}, {"id": "s02"}, {"id": "s03"}],
        "music": {"cues": [{"id": "m", "from_shot": "s02", "to_shot": "s02", "level": 0.0}]},
    }
    assert assemble.music_levels(board) == {"s01": 1.0, "s02": 0.0, "s03": 1.0}


def test_ass_time_format():
    assert assemble.ass_time(83.456) == "0:01:23.46"
