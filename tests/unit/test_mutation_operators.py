"""Test-only mutation operators (tests/mutations/operators.py) used by the evaluation."""

import importlib.util
from pathlib import Path

from parsley.compiler.parser import parse

PATH = Path(__file__).resolve().parents[1] / "mutations" / "operators.py"
spec = importlib.util.spec_from_file_location("parsley_test_mutations", PATH)
operators = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operators)


def _names(source):
    return {name for name, _ in operators.mutants(parse(source))}


def test_each_mutant_changes_only_the_last_statement():
    original = parse("LET x = 1; x = x + 2 * 3;")
    for name, mutant in operators.mutants(original):
        assert mutant != original, name
        assert mutant.statements[:1] == original.statements[:1], name


def test_operators_apply_where_their_node_exists():
    assert _names("LET x = 1; x = x + 2;") >= {"arith_op_swap", "literal_off_by_one", "operand_swap",
                                              "drop_statement"}
    assert "compare_flip" in _names('IF 1 > 2 THEN { PRINT "a"; } ELSE { PRINT "b"; }')
    assert "swap_branches" in _names('IF 1 > 2 THEN { PRINT "a"; } ELSE { PRINT "b"; }')
    assert "repeat_count" in _names('REPEAT 3 TIMES { PRINT "a"; }')
    assert "string_change" in _names('PRINT "a";')
    assert "negation_drop" in _names("PRINT -5;")
    assert "variable_swap" in _names("LET a = 1; LET b = 2; PRINT a;")


def test_specific_mutations():
    mutants = dict(operators.mutants(parse("LET x = 1; x = x + 2;")))
    assert mutants["arith_op_swap"] == parse("LET x = 1; x = x - 2;")
    assert mutants["literal_off_by_one"] == parse("LET x = 1; x = x + 3;")
    assert mutants["drop_statement"] == parse("LET x = 1;")


def test_no_mutant_without_a_matching_node():
    assert _names("PRINT 1;") == {"literal_off_by_one", "drop_statement"}
