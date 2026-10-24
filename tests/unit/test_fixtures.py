"""Fixture files follow the format in TESTING.md (envelope, counts, ids, required keys)."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"

COMMON_KEYS = {"id", "input", "given"}
CATEGORY_KEYS = {
    "valid": {"intent", "rule", "expected_minilang", "expected_diagnostic_levels"},
    "invalid": {"expected_status", "reason"},
    "ambiguous": {"rule", "expected_status", "ambiguity", "expected_question", "options"},
}
MIN_COUNTS = {"valid": 20, "invalid": 10, "ambiguous": 10}
ID_PREFIX = {"valid": "V", "invalid": "X", "ambiguous": "A"}


def load(category):
    return json.loads((FIXTURES / f"{category}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("category", sorted(CATEGORY_KEYS))
def test_fixture_file_shape(category):
    data = load(category)
    assert data["version"] == 1
    assert data["category"] == category
    fixtures = data["fixtures"]
    assert len(fixtures) >= MIN_COUNTS[category]

    ids = [f["id"] for f in fixtures]
    assert len(ids) == len(set(ids)), "fixture ids must be unique"
    for fixture in fixtures:
        missing = (COMMON_KEYS | CATEGORY_KEYS[category]) - fixture.keys()
        assert not missing, f"{fixture['id']} missing {missing}"
        assert fixture["id"].startswith(ID_PREFIX[category])
        assert set(fixture["given"]) == {"symbols", "ref_stack"}
        assert set(fixture["given"]["ref_stack"]) <= set(fixture["given"]["symbols"])
