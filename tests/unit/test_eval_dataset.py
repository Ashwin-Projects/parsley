"""eval/dataset.py loads held-out data read-only, checks freezes, and never tunes."""

import hashlib
import json
from pathlib import Path

import pytest

from parsley.eval import dataset

ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, data: dict, *, freeze: bool = False) -> None:
    raw = json.dumps(data).encode("utf-8")
    path.write_bytes(raw)
    if freeze:
        path.with_suffix(".sha256").write_text(f"{hashlib.sha256(raw).hexdigest()}  {path.name}\n")


def test_frozen_paraphrases_load_as_sixty_items_in_fifteen_groups():
    items = dataset.load_held_out(ROOT / "tests/eval_data")
    paraphrases = [i for i in items if i.subset == "paraphrase"]
    assert len(paraphrases) == 60
    assert len({i.group for i in paraphrases}) == 15
    first = next(i for i in paraphrases if i.id == "H08-2")
    assert first.input == "show balance"
    assert first.setup == ("let balance be 45",)
    assert first.setup_minilang == ("LET balance = 45;",)
    assert first.expected_status == "ok" and first.expected_minilang == "PRINT balance;"
    assert first.source == "held_out" and first.context_dependent is True


def test_items_without_setup_are_not_context_dependent():
    items = dataset.load_held_out(ROOT / "tests/eval_data")
    assert next(i for i in items if i.id == "H01-1").context_dependent is False


def test_a_changed_frozen_file_is_refused(tmp_path):
    path = tmp_path / "paraphrases.json"
    data = json.loads((ROOT / "tests/eval_data/paraphrases.json").read_text(encoding="utf-8"))
    _write(path, data, freeze=True)
    assert len(dataset.load_held_out(tmp_path)) == 60
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(dataset.DatasetError, match="digest"):
        dataset.load_held_out(tmp_path)


def test_fixture_style_subsets_are_loaded(tmp_path):
    _write(tmp_path / "ambiguous.json", {"version": 1, "category": "ambiguous", "fixtures": [
        {"id": "HA1", "given": {"symbols": {"score": "number"}, "ref_stack": ["score"]},
         "input": "increase score", "expected_status": "ambiguous"},
    ]})
    _write(tmp_path / "invalid.json", {"version": 1, "category": "invalid", "fixtures": [
        {"id": "HX1", "given": {"symbols": {}, "ref_stack": []}, "input": "store 5 in x",
         "expected_status": "unsupported", "expected_suggestion": "set x to 5"},
    ]})
    _write(tmp_path / "valid.json", {"version": 1, "category": "valid", "fixtures": [
        {"id": "HV1", "given": {"symbols": {"name": "string"}, "ref_stack": ["name"]},
         "input": "print name", "expected_minilang": "PRINT name;"},
    ]})
    items = {i.id: i for i in dataset.load_held_out(tmp_path)}
    assert items["HA1"].expected_status == "ambiguous" and items["HA1"].setup == ("let score be 0",)
    assert items["HX1"].expected_status == "unsupported" and items["HX1"].expected_suggestion == "set x to 5"
    assert items["HV1"].setup_minilang == ('LET name = "text";',)
    assert items["HV1"].expected_minilang == "PRINT name;" and items["HV1"].subset == "valid"


# Small files in the held-out schemas of tests/eval_data (ambiguous, unsupported, sessions).
AMBIGUOUS = {"version": 1, "category": "held_out_ambiguous", "cases": [
    {"id": "HA01", "ambiguity": "missing_slot", "setup": ["let lanternCount be 11"],
     "setup_minilang": "LET lanternCount = 11;", "input": "increase lanternCount",
     "expected_status": "needs_clarification", "expected_question": "By how much?", "expected_options": []},
]}
UNSUPPORTED = {"version": 1, "category": "held_out_unsupported", "cases": [
    {"id": "HU01", "reason": "out_of_scope", "subcategory": "functions", "setup": [], "setup_minilang": "",
     "input": "define a function called farewell", "expected_status": "unsupported", "expected_minilang": None},
]}
SESSIONS = {"version": 1, "category": "held_out_sessions", "sessions": [
    {"id": "HS01", "coverage": ["implicit_declaration", "pronoun_it"], "setup": [], "setup_minilang": "",
     "sentences": ["set lanternCount to 12", "add 7 to it", "print lanternCount"], "expected_status": "ok",
     "expected_minilang": "\n".join(["LET lanternCount = 12;", "lanternCount = lanternCount + 7;",
                                     "PRINT lanternCount;"])},
]}


def test_every_held_out_subset_loads_with_its_expected_status(tmp_path):
    for name, data in (("ambiguous", AMBIGUOUS), ("unsupported", UNSUPPORTED), ("sessions", SESSIONS)):
        _write(tmp_path / f"{name}.json", data, freeze=True)
    statuses = {i.subset: i.expected_status for i in dataset.load_held_out(tmp_path)}
    assert statuses == {"ambiguous": "ambiguous", "unsupported": "unsupported", "session": "ok"}


def test_held_out_ambiguous_case_keeps_its_setup(tmp_path):
    _write(tmp_path / "ambiguous.json", AMBIGUOUS)
    [case] = dataset.load_held_out(tmp_path)
    assert case.id == "HA01" and case.input == "increase lanternCount"
    assert case.setup == ("let lanternCount be 11",) and case.setup_minilang == ("LET lanternCount = 11;",)


def test_session_becomes_one_item_per_sentence_with_earlier_sentences_as_setup(tmp_path):
    _write(tmp_path / "sessions.json", SESSIONS)
    items = dataset.load_held_out(tmp_path)
    assert [i.id for i in items] == ["HS01-1", "HS01-2", "HS01-3"]
    first, second, _ = items
    assert (first.input, first.setup, first.expected_minilang) == ("set lanternCount to 12", (), "LET lanternCount = 12;")
    assert second.setup == ("set lanternCount to 12",) and second.setup_minilang == ("LET lanternCount = 12;",)
    assert second.expected_minilang == "lanternCount = lanternCount + 7;"
    assert all(i.context_dependent for i in items)  # sessions exist to test context
    assert {i.context for i in items} == {"implicit_declaration,pronoun_it"}


def test_every_file_now_in_tests_eval_data_loads():
    items = dataset.load_held_out(ROOT / "tests/eval_data")
    assert len({i.id for i in items}) == len(items) > 0


def test_session_whose_gold_lines_do_not_match_its_sentences_is_refused(tmp_path):
    _write(tmp_path / "sessions.json", {"version": 1, "category": "held_out_sessions", "sessions": [
        {"id": "S", "coverage": [], "setup": [], "setup_minilang": "", "sentences": ["let x be 1", "print x"],
         "expected_status": "ok", "expected_minilang": "LET x = 1;"},
    ]})
    with pytest.raises(dataset.DatasetError, match="S"):
        dataset.load_held_out(tmp_path)


def test_unknown_files_and_categories_are_errors_not_silently_skipped(tmp_path):
    _write(tmp_path / "odd.json", {"version": 1, "category": "mystery", "fixtures": []})
    with pytest.raises(dataset.DatasetError, match="mystery"):
        dataset.load_held_out(tmp_path)


def test_development_fixtures_load_separately_and_are_marked():
    items = dataset.load_development(ROOT / "tests/fixtures")
    assert {i.source for i in items} == {"development"}
    assert {i.subset for i in items} == {"valid", "invalid", "ambiguous", "semantic"}
    semantic = next(i for i in items if i.id == "M01")
    assert semantic.expected_status == "error" and semantic.expected_codes == ("E201",)


def test_loading_never_writes_to_the_data_directory():
    data = ROOT / "tests/eval_data"
    before = {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()}
    dataset.load_held_out(data)
    assert {p.name: p.read_bytes() for p in data.iterdir() if p.is_file()} == before


HUMAN_BLIND = {"version": 1, "category": "human_blind", "provenance": {"author": "a person who never saw the code"},
               "cases": [
    {"id": "HB01", "setup": [], "setup_minilang": "", "input": "let x be 1",
     "expected_status": "ok", "expected_minilang": "LET x = 1;"},
    {"id": "HB02", "setup": ["let x be 1"], "setup_minilang": "LET x = 1;", "input": "increase x",
     "expected_status": "needs_clarification", "expected_minilang": None},
    {"id": "HB03", "setup": [], "setup_minilang": "", "input": "sort the list",
     "expected_status": "unsupported", "expected_minilang": None},
    {"id": "HB04", "setup": [], "setup_minilang": "", "input": "print y times 2",
     "expected_status": "error", "expected_minilang": None},
]}


def test_optional_human_blind_file_is_its_own_subset(tmp_path):
    _write(tmp_path / "human_blind.json", HUMAN_BLIND, freeze=True)
    items = {i.id: i for i in dataset.load_held_out(tmp_path)}
    assert {i.subset for i in items.values()} == {"human_blind"}
    assert [items[k].expected_status for k in ("HB01", "HB02", "HB03", "HB04")] == [
        "ok", "ambiguous", "unsupported", "error"]
    assert items["HB01"].expected_minilang == "LET x = 1;"
    assert items["HB02"].setup == ("let x be 1",) and items["HB02"].context_dependent


@pytest.mark.parametrize("case", [
    {"id": "B", "setup": [], "setup_minilang": "", "input": "x", "expected_status": "maybe"},
    {"id": "B", "setup": [], "setup_minilang": "", "input": "x", "expected_status": "ok", "expected_minilang": None},
])
def test_human_blind_case_with_a_bad_expectation_is_refused(tmp_path, case):
    _write(tmp_path / "human_blind.json", {"version": 1, "category": "human_blind", "cases": [case]})
    with pytest.raises(dataset.DatasetError, match=r"human_blind.json: case B: "):
        dataset.load_held_out(tmp_path)
