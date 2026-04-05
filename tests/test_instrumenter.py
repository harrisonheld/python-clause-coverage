import ast
import pytest
import coverage_core
from coverage_core import (
    CoverageRuntime,
    ClauseCallToNameTransformer,
    instrument_source,
    execute_instrumented,
)


# Helper: instrument and execute a source string in one step, return the runtime.
# Used by execution tests that don't need a file on disk.
def _run(src):
    rt = CoverageRuntime()
    tree = instrument_source(src, rt)
    execute_instrumented(tree, "<test>", rt)
    return rt


# ── ClauseCallToNameTransformer ───────────────────────────────────────────────
# This transformer is used internally by visit_predicate to convert
# __cc__(0, expr) call nodes into c0 name nodes so the logic expression
# stored on the predicate uses symbolic clause names instead of calls.

class TestClauseCallToNameTransformer:
    def test_transforms_cc_call_to_cname(self):
        # __cc__(0, a > 0) should become the Name node c0
        node = ast.parse("__cc__(0, a > 0)", mode="eval").body
        result = ClauseCallToNameTransformer().visit(node)
        assert isinstance(result, ast.Name)
        assert result.id == "c0"

    def test_uses_correct_clause_id_in_name(self):
        # The id in the resulting Name must match the integer argument
        node = ast.parse("__cc__(7, x)", mode="eval").body
        result = ClauseCallToNameTransformer().visit(node)
        assert isinstance(result, ast.Name)
        assert result.id == "c7"

    def test_leaves_non_cc_call_unchanged(self):
        node = ast.parse("foo(1, 2)", mode="eval").body
        result = ClauseCallToNameTransformer().visit(node)
        assert isinstance(result, ast.Call)

    def test_transforms_nested_cc_calls_in_boolop(self):
        # Simulates the output of instrumenting `a and b`
        node = ast.parse("__cc__(0, a) and __cc__(1, b)", mode="eval").body
        result = ClauseCallToNameTransformer().visit(node)
        assert ast.unparse(result) == "c0 and c1"


# ── instrument_source: predicate registration ─────────────────────────────────
# Structural tests — only check what gets registered in the runtime during
# instrumentation, without executing the resulting tree.

class TestInstrumentPredicateRegistration:
    def test_if_creates_one_predicate(self):
        rt = CoverageRuntime()
        instrument_source("if x > 0:\n    pass\n", rt)
        assert len(rt.predicate_meta) == 1

    def test_while_creates_one_predicate(self):
        rt = CoverageRuntime()
        instrument_source("while x > 0:\n    break\n", rt)
        assert len(rt.predicate_meta) == 1

    def test_assert_creates_one_predicate(self):
        rt = CoverageRuntime()
        instrument_source("assert x > 0\n", rt)
        assert len(rt.predicate_meta) == 1

    def test_ternary_creates_one_predicate(self):
        rt = CoverageRuntime()
        instrument_source("y = 1 if x > 0 else 0\n", rt)
        assert len(rt.predicate_meta) == 1

    def test_two_if_statements_create_two_predicates(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\nif b < 5:\n    pass\n", rt)
        assert len(rt.predicate_meta) == 2

    def test_nested_ifs_create_two_predicates(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    if b < 5:\n        pass\n", rt)
        assert len(rt.predicate_meta) == 2

    def test_plain_assignment_creates_no_predicates(self):
        rt = CoverageRuntime()
        instrument_source("x = a + b\n", rt)
        assert len(rt.predicate_meta) == 0

    def test_predicate_stores_original_expr_src(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\n", rt)
        assert rt.predicate_meta[0]["expr"] == "a > 0"


# ── instrument_source: clause registration ────────────────────────────────────

class TestInstrumentClauseRegistration:
    def test_single_compare_creates_one_clause(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\n", rt)
        assert len(rt.clause_data) == 1

    def test_and_creates_two_clauses(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0 and b < 5:\n    pass\n", rt)
        assert len(rt.clause_data) == 2

    def test_or_creates_two_clauses(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0 or b < 5:\n    pass\n", rt)
        assert len(rt.clause_data) == 2

    def test_three_clause_and_creates_three_clauses(self):
        rt = CoverageRuntime()
        instrument_source("if a and b and c:\n    pass\n", rt)
        assert len(rt.clause_data) == 3

    def test_bool_name_creates_one_clause(self):
        # A bare Name used as a predicate (e.g. `if x:`) is a clause
        rt = CoverageRuntime()
        instrument_source("if x:\n    pass\n", rt)
        assert len(rt.clause_data) == 1

    def test_not_wraps_operand_as_one_clause(self):
        # `not x` — the operand x is the clause, not the UnaryOp itself
        rt = CoverageRuntime()
        instrument_source("if not x:\n    pass\n", rt)
        assert len(rt.clause_data) == 1

    def test_compare_outside_predicate_creates_no_clause(self):
        # Compares in assignments are never inside a predicate context
        rt = CoverageRuntime()
        instrument_source("result = a > 0\n", rt)
        assert len(rt.clause_data) == 0

    def test_clause_stores_original_expr_src(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\n", rt)
        assert rt.clause_meta[0] == "a > 0"

    def test_clauses_from_two_ifs_belong_to_separate_predicates(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\nif b < 5:\n    pass\n", rt)
        assert rt.predicate_meta[0]["clauses"] == [0]
        assert rt.predicate_meta[1]["clauses"] == [1]

    def test_nested_ifs_clauses_belong_to_separate_predicates(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    if b < 5:\n        pass\n", rt)
        p0 = rt.predicate_meta[0]["clauses"]
        p1 = rt.predicate_meta[1]["clauses"]
        assert len(p0) == 1
        assert len(p1) == 1
        assert p0[0] != p1[0]  # each predicate owns a different clause ID

    def test_mixed_compare_and_name_in_and(self):
        # `if a > 0 and b:` — one Compare clause and one Name clause
        rt = CoverageRuntime()
        instrument_source("if a > 0 and b:\n    pass\n", rt)
        assert len(rt.clause_data) == 2


# ── instrument_source: logic expression generation ───────────────────────────
# visit_predicate uses ClauseCallToNameTransformer to build a symbolic logic
# expression (c0 and c1, etc.) stored on the predicate for later evaluation.

class TestInstrumentLogicExpr:
    def test_single_compare_logic_expr(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\n", rt)
        assert rt.predicate_meta[0]["logic_expr"] == "c0"

    def test_and_logic_expr(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0 and b < 5:\n    pass\n", rt)
        assert rt.predicate_meta[0]["logic_expr"] == "c0 and c1"

    def test_or_logic_expr(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0 or b < 5:\n    pass\n", rt)
        assert rt.predicate_meta[0]["logic_expr"] == "c0 or c1"

    def test_not_logic_expr(self):
        rt = CoverageRuntime()
        instrument_source("if not x:\n    pass\n", rt)
        assert rt.predicate_meta[0]["logic_expr"] == "not c0"

    def test_three_clause_and_logic_expr(self):
        rt = CoverageRuntime()
        instrument_source("if a and b and c:\n    pass\n", rt)
        assert rt.predicate_meta[0]["logic_expr"] == "c0 and c1 and c2"

    def test_logic_code_is_compiled(self):
        # set_predicate_logic must produce a compiled code object, not None
        rt = CoverageRuntime()
        instrument_source("if a > 0 and b < 5:\n    pass\n", rt)
        assert rt.predicate_meta[0]["logic_code"] is not None

    def test_separate_predicates_have_independent_logic(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\nif b:\n    pass\n", rt)
        assert rt.predicate_meta[0]["logic_expr"] == "c0"
        assert rt.predicate_meta[1]["logic_expr"] == "c1"


# ── execute_instrumented ──────────────────────────────────────────────────────
# Behavioral tests — verify what actually gets recorded in the runtime when
# an instrumented source string is executed.

class TestExecuteInstrumented:
    def test_if_true_records_predicate_event(self):
        rt = _run("x = 5\nif x > 0:\n    pass\n")
        assert len(rt.predicate_events) == 1
        assert rt.predicate_events[0]["predicate_value"] is True

    def test_if_false_records_predicate_event_false(self):
        rt = _run("x = -1\nif x > 0:\n    pass\n")
        assert len(rt.predicate_events) == 1
        assert rt.predicate_events[0]["predicate_value"] is False

    def test_true_clause_sets_true_flag(self):
        rt = _run("x = 5\nif x > 0:\n    pass\n")
        assert rt.clause_data[0]["true"] is True
        assert rt.clause_data[0]["false"] is False

    def test_false_clause_sets_false_flag(self):
        rt = _run("x = -1\nif x > 0:\n    pass\n")
        assert rt.clause_data[0]["true"] is False
        assert rt.clause_data[0]["false"] is True

    def test_short_circuit_and_skips_second_clause(self):
        # `False and b` — b is never evaluated due to short-circuit
        rt = _run("a = False\nb = True\nif a and b:\n    pass\n")
        cid_b = rt.predicate_meta[0]["clauses"][1]
        assert rt.clause_data[cid_b]["true"] is False
        assert rt.clause_data[cid_b]["false"] is False

    def test_short_circuit_and_second_clause_absent_from_event(self):
        rt = _run("a = False\nb = True\nif a and b:\n    pass\n")
        event = rt.predicate_events[0]
        cid_a = rt.predicate_meta[0]["clauses"][0]
        cid_b = rt.predicate_meta[0]["clauses"][1]
        assert cid_a in event["clause_values"]
        assert cid_b not in event["clause_values"]

    def test_short_circuit_or_skips_second_clause(self):
        # `True or b` — b never evaluated
        rt = _run("a = True\nb = False\nif a or b:\n    pass\n")
        cid_b = rt.predicate_meta[0]["clauses"][1]
        assert rt.clause_data[cid_b]["true"] is False
        assert rt.clause_data[cid_b]["false"] is False

    def test_while_condition_sets_both_flags_over_iterations(self):
        # Condition is True repeatedly, then False on exit — both flags set
        rt = _run("i = 2\nwhile i > 0:\n    i -= 1\n")
        assert rt.clause_data[0]["true"] is True
        assert rt.clause_data[0]["false"] is True

    def test_assert_true_instruments_condition(self):
        rt = _run("assert 1 == 1\n")
        assert rt.clause_data[0]["true"] is True

    def test_assert_false_instruments_before_raising(self):
        # The clause hook fires before the AssertionError is raised
        rt = CoverageRuntime()
        tree = instrument_source("assert 1 == 2\n", rt)
        with pytest.raises(AssertionError):
            execute_instrumented(tree, "<test>", rt)
        assert rt.clause_data[0]["false"] is True

    def test_ternary_condition_is_instrumented(self):
        rt = _run("x = 5\ny = 1 if x > 0 else 0\n")
        assert len(rt.predicate_events) == 1
        assert rt.clause_data[0]["true"] is True

    def test_event_clause_values_match_execution(self):
        rt = _run("a = 5\nb = 3\nif a > 0 and b < 5:\n    pass\n")
        event = rt.predicate_events[0]
        cid_a, cid_b = rt.predicate_meta[0]["clauses"]
        assert event["clause_values"][cid_a] is True
        assert event["clause_values"][cid_b] is True

    def test_two_if_statements_each_record_own_event(self):
        rt = _run("a = 5\nb = -1\nif a > 0:\n    pass\nif b > 0:\n    pass\n")
        assert len(rt.predicate_events) == 2
        assert rt.predicate_events[0]["predicate_value"] is True
        assert rt.predicate_events[1]["predicate_value"] is False

    def test_not_true_sets_false_flag_and_predicate_false(self):
        rt = _run("x = True\nif not x:\n    pass\n")
        assert rt.clause_data[0]["true"] is True   # x was True
        assert rt.predicate_events[0]["predicate_value"] is False  # not True = False

    def test_not_false_sets_false_flag_and_predicate_true(self):
        rt = _run("x = False\nif not x:\n    pass\n")
        assert rt.clause_data[0]["false"] is True  # x was False
        assert rt.predicate_events[0]["predicate_value"] is True   # not False = True
