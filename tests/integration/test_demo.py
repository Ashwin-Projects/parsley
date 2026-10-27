"""The presentation runs the real pipeline and exits nonzero on a broken check."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/demo.py'


def test_demonstration_script_runs_from_repository_root():
    completed = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert 'DEMO PASS' in completed.stdout
    assert 'V2 pass | V3 pass' in completed.stdout
    assert 'Try: set bonus to 50' in completed.stdout
    assert 'did not execute rejected input' in completed.stdout
    assert 'E201' in completed.stdout and 'E103' in completed.stdout
    assert 'context ON=ok; OFF=error' in completed.stdout


def test_demonstration_rejects_a_failed_verifier(monkeypatch):
    spec = importlib.util.spec_from_file_location('parsley_demo', SCRIPT)
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    from parsley.verify import roundtrip
    monkeypatch.setattr(roundtrip, 'check', lambda source, expected: 'injected test-only failure')
    with pytest.raises(RuntimeError, match='V2'):
        demo.demonstrate()
