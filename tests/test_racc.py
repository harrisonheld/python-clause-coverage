import pytest
from coverage_core import CoverageRuntime, instrument_source, execute_instrumented
from racc import analyze_racc, _find_events_for_context, _is_masked_by_short_circuit


# Helper: instrument and execute a source string, return the runtime.
def _run(src):
    rt = CoverageRuntime()
    tree = instrument_source(src, rt)
    execute_instrumented(tree, "<test>", rt)
    return rt


# ── _find_events_for_context ──────────────────────────────────────────────────
# Returns events where the major clause was evaluated AND all minor clause
# values match the required minor_ctx exactly.

class TestFindEventsForContext:

    def _make_event(self, pid, clause_values, predicate_value):
        return {
            "predicate_id": pid,
            "clause_values": clause_values,
            "predicate_value": predicate_value,
        }

    def test_returns_empty_when_no_events(self):
        result = _find_events_for_context([], major_cid=0, minor_ctx=())
        assert result == []

    def test_returns_event_when_major_present_and_no_minors(self):
        ev = self._make_event(0, {0: True}, True)
        result = _find_events_for_context([ev], major_cid=0, minor_ctx=())
        assert result == [ev]

    def test_excludes_event_when_major_absent(self):
        ev = self._make_event(0, {1: True}, True)
        result = _find_events_for_context([ev], major_cid=0, minor_ctx=())
        assert result == []

    def test_includes_event_when_minor_matches(self):
        ev = self._make_event(0, {0: True, 1: False}, True)
        result = _find_events_for_context([ev], major_cid=0, minor_ctx=((1, False),))
        assert result == [ev]

    def test_excludes_event_when_minor_value_wrong(self):
        ev = self._make_event(0, {0: True, 1: True}, True)
        result = _find_events_for_context([ev], major_cid=0, minor_ctx=((1, False),))
        assert result == []

    def test_excludes_event_when_minor_absent(self):
        # minor clause simply not evaluated in this event
        ev = self._make_event(0, {0: True}, True)
        result = _find_events_for_context([ev], major_cid=0, minor_ctx=((1, False),))
        assert result == []

    def test_returns_multiple_matching_events(self):
        ev1 = self._make_event(0, {0: True,  1: True}, True)
        ev2 = self._make_event(0, {0: False, 1: True}, False)
        ev3 = self._make_event(0, {0: True,  1: False}, True)  # wrong minor
        result = _find_events_for_context([ev1, ev2, ev3], major_cid=0, minor_ctx=((1, True),))
        assert result == [ev1, ev2]

    def test_requires_all_minors_to_match(self):
        # Event has both minors present and matching
        ev = self._make_event(0, {0: True, 1: True, 2: False}, True)
        result = _find_events_for_context([ev], major_cid=0, minor_ctx=((1, True), (2, False)))
        assert result == [ev]

    def test_excludes_when_one_of_two_minors_wrong(self):
        ev = self._make_event(0, {0: True, 1: True, 2: True}, True)
        result = _find_events_for_context([ev], major_cid=0, minor_ctx=((1, True), (2, False)))
        assert result == []


# ── _is_masked_by_short_circuit ───────────────────────────────────────────────
# Returns True when there exists an event where:
#   - the major clause WAS evaluated with `major_value`
#   - all minor clauses that ARE present match minor_ctx
#   - at least one minor clause is MISSING (short-circuited away)
#
# This means the full minor_ctx context was attempted but couldn't be verified
# because short-circuit evaluation hid a minor clause.

class TestIsMaskedByShortCircuit:

    def _make_event(self, clause_values):
        return {"predicate_id": 0, "clause_values": clause_values, "predicate_value": True}

    def test_returns_false_when_no_events(self):
        result = _is_masked_by_short_circuit([], major_cid=0, major_value=True, minor_ctx=((1, True),))
        assert result is False

    def test_returns_false_when_all_minors_present(self):
        # All clauses evaluated — no short-circuit masking
        ev = self._make_event({0: True, 1: True})
        result = _is_masked_by_short_circuit([ev], major_cid=0, major_value=True, minor_ctx=((1, True),))
        assert result is False

    def test_returns_true_when_minor_missing_and_major_matches(self):
        # major=True is present; minor cid=1 is absent → masked
        ev = self._make_event({0: True})
        result = _is_masked_by_short_circuit([ev], major_cid=0, major_value=True, minor_ctx=((1, True),))
        assert result is True

    def test_returns_false_when_major_value_wrong(self):
        # major IS present but with value=False, not True
        ev = self._make_event({0: False})
        result = _is_masked_by_short_circuit([ev], major_cid=0, major_value=True, minor_ctx=((1, True),))
        assert result is False

    def test_returns_false_when_present_minor_has_wrong_value(self):
        # cid=1 is present but its value contradicts minor_ctx → not compatible
        ev = self._make_event({0: True, 1: False})
        result = _is_masked_by_short_circuit([ev], major_cid=0, major_value=True, minor_ctx=((1, True),))
        assert result is False

    def test_returns_false_when_major_absent(self):
        ev = self._make_event({1: True})
        result = _is_masked_by_short_circuit([ev], major_cid=0, major_value=True, minor_ctx=((1, True),))
        assert result is False

    def test_returns_true_for_false_major_value_when_minor_missing(self):
        ev = self._make_event({0: False})
        result = _is_masked_by_short_circuit([ev], major_cid=0, major_value=False, minor_ctx=((1, True),))
        assert result is True


# ── analyze_racc: requirement generation ─────────────────────────────────────
# Requirement seeding is identical to CACC: events are only seeds when the
# major AND all minor clauses are present AND XOR holds.

class TestAnalyzeRaccRequirementGeneration:

    def test_empty_runtime_returns_empty(self):
        rt = CoverageRuntime()
        reqs, covered, masked = analyze_racc(rt)
        assert reqs == []
        assert covered == 0
        assert masked == 0

    def test_instrumented_but_not_executed_returns_empty(self):
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\n", rt)
        reqs, covered, masked = analyze_racc(rt)
        assert reqs == []

    def test_single_clause_generates_one_requirement(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _, _ = analyze_racc(rt)
        assert len(reqs) == 1

    def test_and_with_both_evaluated_generates_two_requirements(self):
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        assert len(reqs) == 2

    def test_short_circuit_seed_event_skipped(self):
        # check(False) for `a and b`: b never evaluated → cannot seed
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(False, True)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        assert len(reqs) == 0

    def test_requirement_has_correct_structure(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _, _ = analyze_racc(rt)
        r = reqs[0]
        assert "predicate_id" in r
        assert "major_cid" in r
        assert "minor_ctx" in r
        assert "expected" in r


# ── analyze_racc: satisfaction (RACC-specific) ────────────────────────────────
# RACC is stricter than CACC: satisfaction requires finding events where
# minor clause values MATCH the seeded minor_ctx exactly (via _find_events_for_context).

class TestAnalyzeRaccSatisfaction:

    def test_single_clause_satisfied_when_both_sides_seen(self):
        src = "def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n"
        rt = _run(src)
        reqs, covered, _ = analyze_racc(rt)
        assert reqs[0]["satisfied"] is True
        assert covered == 1

    def test_single_clause_unsatisfied_when_only_false_seen(self):
        rt = _run("x = False\nif x:\n    pass\n")
        reqs, covered, _ = analyze_racc(rt)
        assert reqs[0]["satisfied"] is False
        assert covered == 0

    def test_and_satisfied_when_same_minor_context_has_both_sides(self):
        # check(True, True)  → {a=T, b=T} → pred=True
        # check(False, True) → RACC requires a=False WITH b=True together.
        # But check(False, True) short-circuits → b absent → NOT a valid match.
        # check(True, True) and check(False, False) also don't satisfy major=a, minor=(b=T)
        # because check(False, False) has b=False, not b=True.
        # → Requirement (major=a, minor=(b=T)) is UNSAT (b=True never seen with a=False)
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        cid_a = rt.predicate_meta[0]["clauses"][0]
        req_a = next(r for r in reqs if r["major_cid"] == cid_a)
        assert req_a["satisfied"] is False

    def test_racc_sat_when_same_minor_context_has_both_sides(self):
        # For `a or b`:
        # check(False, True)  → {a=F, b=T} → pred=True   (a=False, so b is evaluated)
        # check(False, False) → {a=F, b=F} → pred=False  (a=False, so b is evaluated)
        #
        # Requirement (major=b, minor=(a=F)):
        #   true_side:  events matching (a=F) with b=True  AND pred=True  ✓ (first call)
        #   false_side: events matching (a=F) with b=False AND pred=False ✓ (second call)
        #   → SAT: both sides found with the SAME minor context
        src = "def check(a, b):\n    if a or b:\n        pass\ncheck(False, True)\ncheck(False, False)\n"
        rt = _run(src)
        reqs, covered, _ = analyze_racc(rt)
        cid_b = rt.predicate_meta[0]["clauses"][1]
        req_b = next(r for r in reqs if r["major_cid"] == cid_b)
        assert req_b["satisfied"] is True
        assert covered >= 1

    def test_racc_unsat_where_cacc_would_be_sat(self):
        # This is the core RACC vs CACC distinction.
        # check(True, True)  → {a=T, b=T} → pred=True
        # check(False, True) → {a=F}      → pred=False  (b short-circuited)
        #
        # Requirement (major=a, minor=(b=T)):
        #   RACC looks for events matching minor_ctx (b=True) exactly.
        #   true_side:  events with a=True  AND b=True  AND pred=True  ✓ (first call)
        #   false_side: events with a=False AND b=True  AND pred=False — no such event
        #               (second call has b absent, so it doesn't appear in matches)
        #   → UNSAT under RACC
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, covered, _ = analyze_racc(rt)
        cid_a = rt.predicate_meta[0]["clauses"][0]
        req_a = next(r for r in reqs if r["major_cid"] == cid_a)
        assert req_a["satisfied"] is False

    def test_observed_true_dict_reflects_seen_sides(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _, _ = analyze_racc(rt)
        assert reqs[0]["observed"][True] is True
        assert reqs[0]["observed"][False] is False

    def test_observed_false_dict_after_seeing_false(self):
        rt = _run("x = False\nif x:\n    pass\n")
        reqs, _, _ = analyze_racc(rt)
        assert reqs[0]["observed"][False] is True
        assert reqs[0]["observed"][True] is False

    def test_covered_count_equals_satisfied_requirements(self):
        src = "def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n"
        rt = _run(src)
        reqs, covered, _ = analyze_racc(rt)
        assert covered == sum(1 for r in reqs if r["satisfied"])


# ── analyze_racc: short-circuit masking ───────────────────────────────────────
# When a requirement is unsatisfied, RACC checks whether short-circuit evaluation
# is the reason — i.e., the required minor context was attempted but a minor
# clause was hidden by short-circuit on one or both sides.

class TestAnalyzeRaccMasking:

    def test_masked_set_true_when_minor_short_circuited(self):
        # check(True, True)  → {a=T, b=T} → True  (seeds req for major=a, minor=(b=T))
        # check(False, True) → {a=F}      → False  (b short-circuited)
        #
        # Requirement (major=a, minor=(b=T)):
        #   false_side unsatisfied because no event has a=False AND b=True together.
        #   _is_masked_by_short_circuit for false side:
        #     event {a=F} has major=False, b is missing but minor_ctx expects b=True → masked
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, _, masked_count = analyze_racc(rt)
        cid_a = rt.predicate_meta[0]["clauses"][0]
        req_a = next(r for r in reqs if r["major_cid"] == cid_a)
        assert req_a["masked_by_short_circuit"] is True
        assert req_a["masked"][False] is True

    def test_masked_count_reflects_masked_requirements(self):
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, covered, masked_count = analyze_racc(rt)
        expected_masked = sum(1 for r in reqs if r["masked_by_short_circuit"])
        assert masked_count == expected_masked

    def test_not_masked_when_fully_satisfied(self):
        src = "def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        assert reqs[0]["masked_by_short_circuit"] is False

    def test_not_masked_when_simply_unsat_without_short_circuit(self):
        # check(True, True) only: both clauses evaluated, req for major=a seeded.
        # false_side: need a=False with b=True — never called. No event with a=False at all.
        # _is_masked_by_short_circuit looks for event with a=False: none exist → NOT masked
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        cid_a = rt.predicate_meta[0]["clauses"][0]
        req_a = next(r for r in reqs if r["major_cid"] == cid_a)
        assert req_a["masked_by_short_circuit"] is False
        assert req_a["satisfied"] is False

    def test_masked_false_on_true_side_when_true_short_circuited(self):
        # check(True, False): a=True short-circuits OR, b never evaluated.
        # check(False, False): a=F, b=F both evaluated. → pred=False
        # Req (major=b, minor=(a=F)) seeded from second event:
        #   true_side: b=True with a=False — never called → check masking
        #   event {a=T} has major=b absent → doesn't help.
        #   No event has b=True at all → not masked (no event with b=True)
        src = "def check(a, b):\n    if a or b:\n        pass\ncheck(True, False)\ncheck(False, False)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        cid_b = rt.predicate_meta[0]["clauses"][1]
        req_b = next(r for r in reqs if r["major_cid"] == cid_b)
        # b is never True in any event, so no masking on the true side
        assert req_b["masked"][True] is False

    def test_masked_by_short_circuit_implies_not_satisfied(self):
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        for r in reqs:
            if r["masked_by_short_circuit"]:
                assert r["satisfied"] is False

    def test_masked_and_covered_counts_are_mutually_exclusive(self):
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, covered, masked_count = analyze_racc(rt)
        total = len(reqs)
        # each requirement is at most one of: satisfied, masked, plain-unsat
        assert covered + masked_count <= total

    def test_masked_on_true_side_for_or_predicate(self):
        # check(True, False): a=True short-circuits OR → {a=T} → pred=True
        # check(False, False): both evaluated → {a=F, b=F} → pred=False
        # Req (major=a, minor=(b=F)) — seeded from second event:
        #   true_side: needs a=True with b=False together — impossible (short-circuited)
        #   event {a=T} has b absent → masked[True]=True
        src = "def check(a, b):\n    if a or b:\n        pass\ncheck(True, False)\ncheck(False, False)\n"
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        cid_a = rt.predicate_meta[0]["clauses"][0]
        req_a = next(r for r in reqs if r["major_cid"] == cid_a)
        assert req_a["masked"][True] is True
        assert req_a["masked"][False] is False
        assert req_a["masked_by_short_circuit"] is True

    def test_masked_in_mixed_operator_predicate(self):
        # Event 1 {c0:T,c1:T} has c2 absent — c1=True exists but minor context (c2=F) missing
        # → true_side of req (major=c1, minor=(c0=T,c2=F)) is masked
        src = (
            "def check(a, b, c):\n    if (a and b) or c:\n        pass\n"
            "check(True, True, False)\ncheck(True, False, False)\n"
        )
        rt = _run(src)
        reqs, _, _ = analyze_racc(rt)
        cid_b = rt.predicate_meta[0]["clauses"][1]
        req_b = next(r for r in reqs if r["major_cid"] == cid_b)
        assert req_b["masked_by_short_circuit"] is True
        assert req_b["masked"][True] is True