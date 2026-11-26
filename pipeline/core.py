"""Shared plumbing used by every stage.

- Paths and secrets (secrets come only from the environment / .env, never from code).
- input_hash(): the cache key. A stage output is reused whenever its inputs hash the same,
  so a re-run regenerates only the shots whose inputs changed.
- call_model(): runs one model call with timing and retries, and appends one line per attempt
  to runs.jsonl (model, params, seed, latency, cost, status).
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeVar

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
OUTPUTS = ROOT / "outputs"
RUNS_LOG = ROOT / "runs.jsonl"

load_dotenv(ROOT / ".env")

# One id per process, so the log shows which calls belong to the same pipeline run.
RUN_ID = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}
SECRET_ENV_VARS = ("GEMINI_API_KEY", "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "ADDIS_API_KEY", "KAGGLE_KEY")

T = TypeVar("T")


class RetryableError(RuntimeError):
    """A failure worth retrying even though it carries no HTTP status (e.g. a reply with no audio)."""


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is missing. Copy .env.example to .env and set it.")
    return value


def input_hash(inputs: dict[str, Any]) -> str:
    """Stable short hash of everything that affects an output. Key order does not matter."""
    canonical = json.dumps(inputs, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def redact(text: str) -> str:
    """Remove secret values from text before it is logged."""
    for name in SECRET_ENV_VARS:
        value = os.environ.get(name, "").strip()
        if value:
            text = text.replace(value, f"<{name}>")
    return text


def status_code_of(err: BaseException) -> int | None:
    for attr in ("code", "status_code"):
        value = getattr(err, attr, None)
        if isinstance(value, int):
            return value
    value = getattr(getattr(err, "response", None), "status_code", None)
    return value if isinstance(value, int) else None


def is_retryable(err: BaseException) -> bool:
    """Retry rate limits, server errors and network failures; never retry a bad request or bad key."""
    if isinstance(err, RetryableError):
        return True
    code = status_code_of(err)
    if code is not None:
        return code in RETRYABLE_STATUS
    network_error = isinstance(err, (ConnectionError, TimeoutError)) or type(err).__module__.startswith(
        ("httpx", "httpcore", "requests", "urllib3")
    )
    return network_error


def run_with_deadline(fn: Callable[[], T], deadline_s: float) -> T:
    """Run fn() but give up after deadline_s, raising TimeoutError (which the retry policy retries).

    Needed because an SDK's own timeout setting does not cover every code path: one TTS call hung
    for 15 minutes (FAILURES.md F4). The worker is a daemon thread, so an abandoned call cannot keep
    the process alive at exit.
    """
    outcome: dict[str, Any] = {}

    def worker() -> None:
        try:
            outcome["value"] = fn()
        except Exception as err:  # noqa: BLE001 - not swallowed: re-raised in the caller's thread below
            outcome["error"] = err

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(deadline_s)
    if thread.is_alive():
        raise TimeoutError(f"no reply within {deadline_s:.0f} s")
    if "error" in outcome:
        raise outcome["error"]
    return outcome["value"]


def append_log(record: dict[str, Any]) -> None:
    line = {"ts": datetime.now(UTC).isoformat(timespec="seconds"), "run_id": RUN_ID, **record}
    with RUNS_LOG.open("a", encoding="utf-8") as log:
        log.write(json.dumps(line, ensure_ascii=False) + "\n")


def call_model(
    fn: Callable[[], T],
    *,
    stage: str,
    model: str,
    params: dict[str, Any],
    seed: int | None = None,
    shot: str | None = None,
    output: str | None = None,
    describe: Callable[[T], dict[str, Any]] | None = None,
    cost_usd: float = 0.0,
    attempts: int = 4,
    base_delay_s: float = 5.0,
    deadline_s: float | None = None,
) -> T:
    """Run fn() with retries and exponential backoff, logging every attempt to runs.jsonl.

    `describe` turns a successful result into extra log fields (token usage, list-price estimate).
    `deadline_s` bounds each attempt even if the client library never times out.
    Errors are always logged; a non-retryable error, or the last attempt's error, is re-raised.
    """
    base = {"stage": stage, "shot": shot, "model": model, "params": params, "seed": seed, "output": output}
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            result = run_with_deadline(fn, deadline_s) if deadline_s else fn()
        except Exception as err:  # logged and then retried or re-raised, never swallowed
            retry = attempt < attempts and is_retryable(err)
            append_log(
                {
                    **base,
                    "attempt": attempt,
                    "status": "retrying" if retry else "failed",
                    "latency_s": round(time.perf_counter() - started, 3),
                    "cost_usd": 0.0,
                    "error": redact(f"{type(err).__name__}: {err}")[:600],
                }
            )
            if not retry:
                raise
            time.sleep(base_delay_s * 2 ** (attempt - 1))
            continue
        latency_s = round(time.perf_counter() - started, 3)
        extra = describe(result) if describe else {}
        append_log({**base, "attempt": attempt, "status": "ok", "latency_s": latency_s, "cost_usd": cost_usd, **extra})
        return result
    raise AssertionError("unreachable: the loop either returns or raises")
