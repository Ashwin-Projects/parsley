"""Dataset integrity only; held-out NLP text is never a tuning assertion."""

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / 'scripts/validate_paraphrases.py'
SPEC = importlib.util.spec_from_file_location('validate_paraphrases', SCRIPT)
validator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validator)


def test_frozen_paraphrase_dataset_and_gold_programs():
    assert validator.validate() == (15, 60)


def test_changed_data_is_rejected(tmp_path):
    changed = tmp_path / 'paraphrases.json'
    changed.write_bytes(validator.DATA.read_bytes() + b' ')
    changed.with_suffix('.sha256').write_text(validator.DATA.with_suffix('.sha256').read_text())
    with pytest.raises(ValueError, match='changed after freezing'):
        validator.validate(changed)
