import ast
import pytest
import coverage_core


# Helper: parse a logic string (with c0, c1, ... names) into an AST node
# suitable for passing directly to set_predicate_logic.
def _logic_node(expr_str):
    return ast.parse(expr_str, mode="eval").body


# ── new_clause ────────────────────────────────────────────────────────────────

class TestNewClause:
    def test_returns_sequential_ids(self, rt):
        assert rt.new_clause("a > 0") == 0
        assert rt.new_clause("b < 5") == 1

    def test_initializes_both_flags_false(self, rt):
        cid = rt.new_clause("x == 1")
        assert rt.clause_data[cid]["true"] is False
        assert rt.clause_data[cid]["false"] is False

    def test_stores_expr_src_in_meta(self, rt):
        cid = rt.new_clause("a > 0")
        assert rt.clause_meta[cid] == "a > 0"

    def test_independent_entries_per_clause(self, rt):
        cid0 = rt.new_clause("a > 0")
        cid1 = rt.new_clause("b < 5")
        rt.clause_data[cid0]["true"] = True
        assert rt.clause_data[cid1]["true"] is False


# ── new_predicate ─────────────────────────────────────────────────────────────

class TestNewPredicate:
    def test_returns_sequential_ids(self, rt):
        assert rt.new_predicate("a > 0 and b < 5") == 0
        assert rt.new_predicate("x == 1") == 1

    def test_stores_expr_in_meta(self, rt):
        pid = rt.new_predicate("a > 0")
        assert rt.predicate_meta[pid]["expr"] == "a > 0"

    def test_initializes_clauses_empty(self, rt):
        pid = rt.new_predicate("a > 0")
        assert rt.predicate_meta[pid]["clauses"] == []

    def test_initializes_logic_fields_empty(self, rt):
        pid = rt.new_predicate("a > 0")
        assert rt.predicate_meta[pid]["logic_expr"] == ""
        assert rt.predicate_meta[pid]["logic_code"] is None


# ── add_clause_to_predicate ───────────────────────────────────────────────────

class TestAddClauseToPredicate:
    def test_adds_clause(self, rt):
        pid = rt.new_predicate("a > 0")
        cid = rt.new_clause("a > 0")
        rt.add_clause_to_predicate(pid, cid)
        assert cid in rt.predicate_meta[pid]["clauses"]

    def test_does_not_duplicate(self, rt):
        pid = rt.new_predicate("a > 0")
        cid = rt.new_clause("a > 0")
        rt.add_clause_to_predicate(pid, cid)
        rt.add_clause_to_predicate(pid, cid)
        assert rt.predicate_meta[pid]["clauses"].count(cid) == 1

    def test_multiple_clauses_added_in_order(self, rt):
        pid = rt.new_predicate("a > 0 and b < 5")
        cid0 = rt.new_clause("a > 0")
        cid1 = rt.new_clause("b < 5")
        rt.add_clause_to_predicate(pid, cid0)
        rt.add_clause_to_predicate(pid, cid1)
        assert rt.predicate_meta[pid]["clauses"] == [cid0, cid1]


# ── set_predicate_logic / eval_predicate_logic ────────────────────────────────

class TestPredicateLogic:
    def test_set_stores_logic_expr_string(self, rt):
        pid = rt.new_predicate("c0 and c1")
        rt.set_predicate_logic(pid, _logic_node("c0 and c1"))
        assert rt.predicate_meta[pid]["logic_expr"] == "c0 and c1"

    def test_set_compiles_logic_code(self, rt):
        pid = rt.new_predicate("c0 and c1")
        rt.set_predicate_logic(pid, _logic_node("c0 and c1"))
        assert rt.predicate_meta[pid]["logic_code"] is not None

    def test_eval_and_both_true(self, rt):
        pid = rt.new_predicate("c0 and c1")
        rt.set_predicate_logic(pid, _logic_node("c0 and c1"))
        assert rt.eval_predicate_logic(pid, {0: True, 1: True}) is True

    def test_eval_and_one_false(self, rt):
        pid = rt.new_predicate("c0 and c1")
        rt.set_predicate_logic(pid, _logic_node("c0 and c1"))
        assert rt.eval_predicate_logic(pid, {0: True, 1: False}) is False

    def test_eval_or_one_true(self, rt):
        pid = rt.new_predicate("c0 or c1")
        rt.set_predicate_logic(pid, _logic_node("c0 or c1"))
        assert rt.eval_predicate_logic(pid, {0: False, 1: True}) is True

    def test_eval_or_both_false(self, rt):
        pid = rt.new_predicate("c0 or c1")
        rt.set_predicate_logic(pid, _logic_node("c0 or c1"))
        assert rt.eval_predicate_logic(pid, {0: False, 1: False}) is False

    def test_eval_not_true_becomes_false(self, rt):
        pid = rt.new_predicate("not c0")
        rt.set_predicate_logic(pid, _logic_node("not c0"))
        assert rt.eval_predicate_logic(pid, {0: True}) is False

    def test_eval_not_false_becomes_true(self, rt):
        pid = rt.new_predicate("not c0")
        rt.set_predicate_logic(pid, _logic_node("not c0"))
        assert rt.eval_predicate_logic(pid, {0: False}) is True

    def test_eval_three_clause_and_all_true(self, rt):
        pid = rt.new_predicate("c0 and c1 and c2")
        rt.set_predicate_logic(pid, _logic_node("c0 and c1 and c2"))
        assert rt.eval_predicate_logic(pid, {0: True, 1: True, 2: True}) is True

    def test_eval_three_clause_and_last_false(self, rt):
        pid = rt.new_predicate("c0 and c1 and c2")
        rt.set_predicate_logic(pid, _logic_node("c0 and c1 and c2"))
        assert rt.eval_predicate_logic(pid, {0: True, 1: True, 2: False}) is False

    def test_eval_returns_bool_type(self, rt):
        pid = rt.new_predicate("c0")
        rt.set_predicate_logic(pid, _logic_node("c0"))
        result = rt.eval_predicate_logic(pid, {0: True})
        assert type(result) is bool


# ── hook ──────────────────────────────────────────────────────────────────────

class TestHook:
    def test_sets_true_flag_for_truthy_value(self, rt):
        cid = rt.new_clause("a > 0")
        rt.hook(cid, True)
        assert rt.clause_data[cid]["true"] is True
        assert rt.clause_data[cid]["false"] is False

    def test_sets_false_flag_for_falsy_value(self, rt):
        cid = rt.new_clause("a > 0")
        rt.hook(cid, False)
        assert rt.clause_data[cid]["false"] is True
        assert rt.clause_data[cid]["true"] is False

    def test_accumulates_both_flags(self, rt):
        cid = rt.new_clause("a > 0")
        rt.hook(cid, True)
        rt.hook(cid, False)
        assert rt.clause_data[cid]["true"] is True
        assert rt.clause_data[cid]["false"] is True

    def test_returns_original_value_unchanged(self, rt):
        cid = rt.new_clause("x")
        assert rt.hook(cid, 42) == 42
        assert rt.hook(cid, 0) == 0
        assert rt.hook(cid, "hello") == "hello"

    def test_truthy_int_sets_true_flag(self, rt):
        cid = rt.new_clause("x")
        rt.hook(cid, 5)
        assert rt.clause_data[cid]["true"] is True
        assert rt.clause_data[cid]["false"] is False

    def test_zero_sets_false_flag(self, rt):
        cid = rt.new_clause("x")
        rt.hook(cid, 0)
        assert rt.clause_data[cid]["false"] is True

    def test_updates_predicate_stack_when_active(self, rt):
        cid = rt.new_clause("a > 0")
        ctx = {"predicate_id": 0, "clause_values": {}}
        rt._predicate_stack.append(ctx)
        rt.hook(cid, True)
        assert ctx["clause_values"][cid] is True

    def test_stack_value_coerced_to_bool(self, rt):
        cid = rt.new_clause("x")
        ctx = {"predicate_id": 0, "clause_values": {}}
        rt._predicate_stack.append(ctx)
        rt.hook(cid, 42)
        assert ctx["clause_values"][cid] is True

    def test_does_not_raise_when_stack_empty(self, rt):
        cid = rt.new_clause("a > 0")
        rt.hook(cid, True)  # should not raise
        assert rt._predicate_stack == []

    def test_only_updates_innermost_stack_frame(self, rt):
        cid = rt.new_clause("x")
        outer = {"predicate_id": 0, "clause_values": {}}
        inner = {"predicate_id": 1, "clause_values": {}}
        rt._predicate_stack.append(outer)
        rt._predicate_stack.append(inner)
        rt.hook(cid, True)
        assert cid in inner["clause_values"]
        assert cid not in outer["clause_values"]


# ── predicate_hook ────────────────────────────────────────────────────────────

class TestPredicateHook:
    def test_records_one_event(self, rt):
        pid = rt.new_predicate("x")
        rt.predicate_hook(pid, lambda: True)
        assert len(rt.predicate_events) == 1

    def test_event_has_correct_predicate_id(self, rt):
        pid = rt.new_predicate("x")
        rt.predicate_hook(pid, lambda: True)
        assert rt.predicate_events[0]["predicate_id"] == pid

    def test_event_predicate_value_true(self, rt):
        pid = rt.new_predicate("x")
        rt.predicate_hook(pid, lambda: True)
        assert rt.predicate_events[0]["predicate_value"] is True

    def test_event_predicate_value_false(self, rt):
        pid = rt.new_predicate("x")
        rt.predicate_hook(pid, lambda: False)
        assert rt.predicate_events[0]["predicate_value"] is False

    def test_event_captures_clause_values_from_hook(self, rt):
        pid = rt.new_predicate("x")
        cid = rt.new_clause("x")

        def thunk():
            rt.hook(cid, True)
            return True

        rt.predicate_hook(pid, thunk)
        assert rt.predicate_events[0]["clause_values"] == {cid: True}

    def test_returns_thunk_result(self, rt):
        pid = rt.new_predicate("x")
        result = rt.predicate_hook(pid, lambda: 99)
        assert result == 99

    def test_stack_empty_after_successful_hook(self, rt):
        pid = rt.new_predicate("x")
        rt.predicate_hook(pid, lambda: True)
        assert rt._predicate_stack == []

    def test_stack_cleaned_up_on_exception(self, rt):
        pid = rt.new_predicate("x")

        def bad_thunk():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            rt.predicate_hook(pid, bad_thunk)

        assert rt._predicate_stack == []

    def test_no_event_recorded_on_exception(self, rt):
        pid = rt.new_predicate("x")

        def bad_thunk():
            raise RuntimeError("fail")

        with pytest.raises(RuntimeError):
            rt.predicate_hook(pid, bad_thunk)

        assert rt.predicate_events == []

    def test_nested_predicates_record_separate_events(self, rt):
        pid_outer = rt.new_predicate("outer")
        pid_inner = rt.new_predicate("inner")
        cid_outer = rt.new_clause("a")
        cid_inner = rt.new_clause("b")

        def outer_thunk():
            rt.hook(cid_outer, True)
            rt.predicate_hook(pid_inner, lambda: rt.hook(cid_inner, False))
            return True

        rt.predicate_hook(pid_outer, outer_thunk)

        # inner finishes first, so its event is recorded first
        assert len(rt.predicate_events) == 2
        assert rt.predicate_events[0]["predicate_id"] == pid_inner
        assert rt.predicate_events[1]["predicate_id"] == pid_outer

    def test_nested_predicates_clause_values_are_isolated(self, rt):
        pid_outer = rt.new_predicate("outer")
        pid_inner = rt.new_predicate("inner")
        cid_outer = rt.new_clause("a")
        cid_inner = rt.new_clause("b")

        def outer_thunk():
            rt.hook(cid_outer, True)
            rt.predicate_hook(pid_inner, lambda: rt.hook(cid_inner, False))
            return True

        rt.predicate_hook(pid_outer, outer_thunk)

        inner_event = rt.predicate_events[0]
        outer_event = rt.predicate_events[1]

        # each event should only contain its own clauses
        assert cid_inner in inner_event["clause_values"]
        assert cid_outer not in inner_event["clause_values"]
        assert cid_outer in outer_event["clause_values"]
        assert cid_inner not in outer_event["clause_values"]