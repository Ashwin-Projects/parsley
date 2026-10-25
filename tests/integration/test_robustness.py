"""Seeded hostile-input checks against the real pipeline and CLI."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import (
    ThreadPoolExecutor,
    TimeoutError as FutureTimeout,
)
import multiprocessing
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
import os
from pathlib import Path
import random
import subprocess
import sys
from time import perf_counter
import traceback

import pytest


ROOT = Path(__file__).resolve().parents[2]
SEED = 20261025
PIPELINE_SECONDS = 1.0
KNOWN_STATUSES = {"ok", "needs_clarification", "unsupported", "error"}
CATEGORIES = (
    "empty", "long", "unicode", "control", "quotes", "alternatives",
    "negatives", "keywords", "soup", "boundaries",
)
Case = tuple[str, str]
Outcome = tuple[str, str, float]


def _corpus() -> tuple[Case, ...]:
    rng = random.Random(SEED)
    cases = []
    words = (
        "print", "set", "variable", "hello", "x", "score", "then", "else",
        "plus", "minus", "times", "by", "or", "and", "to", "negative",
        "repeat", "divide", "banana", "42", '"text"', "?", "\\",
    )
    for category in CATEGORIES:
        for index in range(50):
            if category == "empty":
                text = "" if index == 0 else "".join(
                    rng.choices(" \t\r\n.!?", k=rng.randint(1, 80))
                )
            elif category == "long":
                length = (501, 1000, 10000, 100000)[index % 4]
                text = "print " + rng.choice("xλ?") * length
            elif category == "unicode":
                text = 'print "' + "".join(rng.choices(
                    "café\u0301世界🙂λЖ\u200b\u202e\ufeff",
                    k=rng.randint(1, 100),
                )) + '"'
            elif category == "control":
                content = "\x00" if index == 0 else "".join(rng.choices(
                    "\x00\x01\x07\x08\t\n\r\x1b\x1f\x7f", k=rng.randint(1, 30),
                ))
                text = 'print "' + content + '"'
            elif category == "quotes":
                text = rng.choice(("print ", "set x to ", "let x be "))
                text += '"' + "".join(rng.choices(
                    "abc \\λ", k=rng.randint(1, 150),
                ))
            elif category == "alternatives":
                text = "print " + " or ".join(
                    str(rng.randrange(100)) for _ in range(5 + index)
                )
            elif category == "negatives":
                text = "print " + "negative " * (index + 1) + "1"
            elif category == "keywords":
                name = rng.choice((
                    "LET", "print", "If", "THEN", "else", "Repeat", "TIMES",
                ))
                text = f"let {name} be {rng.randrange(100)}"
            elif category == "soup":
                text = " ".join(rng.choices(words, k=rng.randint(1, 100)))
            else:
                text = rng.choice((
                    "repeat 0 times print hi", "repeat 1001 times print hi",
                    "print 1 divided by 0", "print 1 divided by negative 0",
                    'print "a" times 2', "set x to", "increase it",
                    "print " + "(" * 60 + "1" + ")" * 60,
                    "let x be 1", 'print "hello"', "--help",
                ))
            cases.append((f"{category}-{index:02d}", text))
    return tuple(cases)


CASES = _corpus()
# Include each category's first adversarial case, plus two seeded picks.
_sample_rng = random.Random(SEED + 1)
CLI_CASES = tuple(
    CASES[offset + index]
    for offset in range(0, 500, 50)
    for index in (0, *_sample_rng.sample(range(1, 50), 2))
)


def _pipeline_worker(channel: Connection) -> None:
    from parsley.pipeline import run
    from parsley.session import Session

    try:
        channel.send("ready")  # Startup/import time is outside each deadline.
        while True:
            text = channel.recv()
            if text is None:
                return
            start = perf_counter()
            try:
                result = run(text, Session())
                outcome = ("returned", result.status, perf_counter() - start)
            except BaseException:
                outcome = ("raised", traceback.format_exc(),
                           perf_counter() - start)
            channel.send(outcome)
    finally:
        channel.close()


def _start_worker() -> tuple[BaseProcess, Connection]:
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(
        target=_pipeline_worker, args=(child,), daemon=True,
    )
    process.start()
    child.close()
    if not parent.poll(20):
        _stop_worker(process)
        parent.close()
        pytest.fail("Robustness worker could not start within 20 seconds")
    assert parent.recv() == "ready"
    return process, parent


def _stop_worker(process: BaseProcess) -> None:
    if process.is_alive():
        process.terminate()
    process.join(timeout=1)
    if process.is_alive():
        process.kill()
        process.join(timeout=1)


def _exchange(channel: Connection, text: str) -> Outcome:
    channel.send(text)
    return channel.recv()


@pytest.fixture(scope="module")
def pipeline_probe() -> Iterator[Callable[[str], Outcome]]:
    process, channel = _start_worker()
    transport = ThreadPoolExecutor(max_workers=1)

    def probe(text: str) -> Outcome:
        nonlocal process, channel
        if not process.is_alive():
            channel.close()
            process.close()
            process, channel = _start_worker()
        # Bound send and receive together, including a blocked or broken pipe.
        pending = transport.submit(_exchange, channel, text)
        try:
            return pending.result(timeout=PIPELINE_SECONDS)
        except FutureTimeout:
            _stop_worker(process)
            channel.close()
            pytest.fail(
                f"Pipeline exceeded {PIPELINE_SECONDS}s; seed={SEED}; "
                f"exact input={text!r}"
            )
        except (EOFError, OSError) as error:
            _stop_worker(process)
            channel.close()
            pytest.fail(
                f"Pipeline worker failed: {error!r}; seed={SEED}; "
                f"exact input={text!r}"
            )

    try:
        yield probe
    finally:
        if process.is_alive():
            channel.send(None)
            process.join(timeout=2)
        _stop_worker(process)
        channel.close()
        transport.shutdown(wait=True)
        process.close()


def test_seeded_corpus_and_cli_sample_cover_every_category() -> None:
    assert len(CASES) == 500
    assert CASES == _corpus()
    assert len(CLI_CASES) == 30
    for category in CATEGORIES:
        assert sum(name.startswith(category + "-") for name, _ in CASES) == 50
        assert sum(
            name.startswith(category + "-") for name, _ in CLI_CASES
        ) == 3


@pytest.mark.parametrize("name,text", CASES, ids=[name for name, _ in CASES])
def test_pipeline_handles_hostile_input_within_one_second(
    name: str, text: str, pipeline_probe: Callable[[str], Outcome],
) -> None:
    kind, detail, elapsed = pipeline_probe(text)
    context = f"{name}; seed={SEED}; exact input={text!r}"
    assert kind == "returned", f"{context}\nPipeline raised:\n{detail}"
    assert detail in KNOWN_STATUSES, f"{context}\nUnknown status: {detail!r}"
    assert elapsed < PIPELINE_SECONDS, f"{context}\nTook {elapsed:.6f}s"


@pytest.mark.parametrize(
    "name,text", CLI_CASES, ids=[name for name, _ in CLI_CASES],
)
def test_cli_handles_hostile_input_without_traceback(
    name: str, text: str,
) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(ROOT / "src"), env.get("PYTHONPATH", "")) if path
    )
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    context = f"{name}; seed={SEED}; exact input={text!r}"
    # REPL stdin preserves NULs and avoids the OS command-line length limit.
    # Closing stdin also ends clarification prompts without hanging the child.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "parsley"],
            cwd=ROOT, env=env, input=text + "\n", capture_output=True,
            encoding="utf-8", timeout=15, check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(f"{context}\nCLI exceeded its 15-second process deadline")
    assert result.returncode in (0, 1), (
        f"{context}\nExit {result.returncode}\n"
        f"{result.stdout}\n{result.stderr}"
    )
    assert "Traceback (most recent call last)" not in (
        result.stdout + result.stderr
    ), f"{context}\n{result.stdout}\n{result.stderr}"
