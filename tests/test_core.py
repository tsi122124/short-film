import pytest

from pipeline import core


def test_input_hash_ignores_key_order():
    assert core.input_hash({"a": 1, "b": "x"}) == core.input_hash({"b": "x", "a": 1})


def test_input_hash_changes_when_any_input_changes():
    base = {"text": "ልጅ እያለሁ", "voice": "Sulafat"}
    assert core.input_hash(base) != core.input_hash({**base, "voice": "Achernar"})
    assert core.input_hash(base) != core.input_hash({**base, "text": "ልጅ እያለሁ።"})


class FakeHTTPError(Exception):
    def __init__(self, code):
        super().__init__(f"HTTP {code}")
        self.code = code


@pytest.mark.parametrize("code, expected", [(429, True), (503, True), (400, False), (401, False), (404, False)])
def test_retry_policy_by_status(code, expected):
    assert core.is_retryable(FakeHTTPError(code)) is expected


def test_call_model_retries_then_succeeds_and_logs_each_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "RUNS_LOG", tmp_path / "runs.jsonl")
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    calls = iter([FakeHTTPError(429), "audio"])

    def flaky():
        result = next(calls)
        if isinstance(result, Exception):
            raise result
        return result

    assert core.call_model(flaky, stage="t", model="m", params={}) == "audio"
    lines = (tmp_path / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    assert [line.count('"status": "retrying"') for line in lines] == [1, 0]
    assert '"status": "ok"' in lines[1]


def test_call_model_does_not_retry_a_bad_request(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "RUNS_LOG", tmp_path / "runs.jsonl")
    attempts = []

    def bad():
        attempts.append(1)
        raise FakeHTTPError(400)

    with pytest.raises(FakeHTTPError):
        core.call_model(bad, stage="t", model="m", params={})
    assert len(attempts) == 1


def test_a_hung_call_is_cut_off_by_the_deadline_and_logged(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "RUNS_LOG", tmp_path / "runs.jsonl")

    def hangs():
        core.time.sleep(5)

    started = core.time.perf_counter()
    with pytest.raises(TimeoutError):
        core.call_model(hangs, stage="t", model="m", params={}, attempts=1, deadline_s=0.2)
    assert core.time.perf_counter() - started < 2
    assert '"status": "failed"' in (tmp_path / "runs.jsonl").read_text(encoding="utf-8")


def test_secrets_are_redacted_from_logged_errors(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-secret-value")
    assert "AIza-secret-value" not in core.redact("failed calling ?key=AIza-secret-value")
