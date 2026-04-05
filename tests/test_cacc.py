import pytest
from coverage_core import CoverageRuntime, instrument_source, execute_instrumented
from cacc import analyze_cacc, _format_minor_context


# Helper: instrument and execute a source string, return the runtime.
def _run(src):
    rt = CoverageRuntime()
    tree = instrument_source(src, rt)
    execute_instrumented(tree, "<test>", rt)
    return rt


# ── Requirement generation ────────────────────────────────────────────────────
# A requirement is seeded from an event only when:
#   (a) both the major clause AND all minor clauses appear in clause_values
#       (i.e. no short-circuit dropped any of them), AND
#   (b) flipping the major clause would change the predicate outcome (XOR holds).

class TestAnalyzeCaccRequirementGeneration:

    def test_empty_runtime_returns_empty(self):
        rt = CoverageRuntime()
        reqs, covered = analyze_cacc(rt)
        assert reqs == []
        assert covered == 0

    def test_instrumented_but_not_executed_returns_empty(self):
        # Predicates are registered during instrumentation but no events exist
        rt = CoverageRuntime()
        instrument_source("if a > 0:\n    pass\n", rt)
        reqs, covered = analyze_cacc(rt)
        assert reqs == []
        assert covered == 0

    def test_single_clause_predicate_generates_one_requirement(self):
        # `if x:` has one clause and no minors; flipping x always changes outcome
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _ = analyze_cacc(rt)
        assert len(reqs) == 1

    def test_single_clause_requirement_has_empty_minor_ctx(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _ = analyze_cacc(rt)
        assert reqs[0]["minor_ctx"] == ()

    def test_and_with_both_clauses_evaluated_generates_two_requirements(self):
        # check(True, True): a=T, b=T, both evaluated. Provides seeds for both majors.
        # major=a, minor=(b=T): T∧T=T vs F∧T=F → XOR → req
        # major=b, minor=(a=T): T∧T=T vs T∧F=F → XOR → req
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        assert len(reqs) == 2

    def test_and_no_requirement_when_minor_deactivates_xor(self):
        # check(True, False): a=T, b=F — no short-circuit, both evaluated.
        # major=a, minor=(b=F): T∧F=F vs F∧F=F → XOR=False → NO req for major=a
        # major=b, minor=(a=T): T∧T=T vs T∧F=F → XOR=True  → req for major=b only
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, False)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        assert len(reqs) == 1
        cid_b = rt.predicate_meta[0]["clauses"][1]
        assert reqs[0]["major_cid"] == cid_b

    def test_or_generates_requirement_only_for_activating_minor_context(self):
        # check(False, True) and check(False, False): a=False on both → b always evaluated.
        # major=a, minor=(b=T): T∨T=T vs F∨T=T → XOR=False → NO req for minor=(b=T)
        # major=a, minor=(b=F): T∨F=T vs F∨F=F → XOR=True  → req for minor=(b=F)
        # major=b, minor=(a=F): seeded from first event → req (second event deduped)
        src = "def check(a, b):\n    if a or b:\n        pass\ncheck(False, True)\ncheck(False, False)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        assert len(reqs) == 2

    def test_event_skipped_as_seed_when_minor_short_circuited(self):
        # check(False, True) for `a and b`: a=False short-circuits AND, b never evaluated.
        # For major=a: minor=[b], b absent from clause_values → skip.
        # For major=b: b (major) absent from clause_values → skip.
        # → 0 requirements
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(False, True)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        assert len(reqs) == 0

    def test_event_skipped_as_seed_when_major_short_circuited(self):
        # check(True, False) for `a or b`: a=True short-circuits OR, b never evaluated.
        # For major=a: minor=[b], b absent → skip.
        # For major=b: b (major) absent from clause_values → skip.
        # → 0 requirements
        src = "def check(a, b):\n    if a or b:\n        pass\ncheck(True, False)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        assert len(reqs) == 0

    def test_seen_contexts_deduplication(self):
        # Two identical calls produce the same minor_ctx twice for each major.
        # seen_contexts ensures only one requirement per (major, minor_ctx) pair.
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(True, True)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        assert len(reqs) == 2  # one per major, not four

    def test_requirement_stores_correct_predicate_id(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _ = analyze_cacc(rt)
        assert reqs[0]["predicate_id"] == 0

    def test_requirement_stores_correct_major_cid(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _ = analyze_cacc(rt)
        cid = rt.predicate_meta[0]["clauses"][0]
        assert reqs[0]["major_cid"] == cid

    def test_requirement_expected_values_for_single_clause(self):
        # For `if x:`, major=True → pred=True, major=False → pred=False
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _ = analyze_cacc(rt)
        assert reqs[0]["expected"] == {True: True, False: False}

    def test_requirements_from_separate_predicates_have_distinct_pids(self):
        src = "def f(a, b):\n    if a:\n        pass\n    if b:\n        pass\nf(True, False)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        pids = {r["predicate_id"] for r in reqs}
        assert len(pids) == 2


# ── Satisfaction checking ─────────────────────────────────────────────────────
# CACC satisfaction: a requirement is satisfied when there exists *any* event
# where (major=True AND pred=expected[True]) AND *any* event where
# (major=False AND pred=expected[False]) — regardless of what the minor clauses
# were in those events. This is the key difference from RACC.

class TestAnalyzeCaccSatisfaction:

    def test_single_clause_both_sides_seen_is_satisfied(self):
        src = "def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n"
        rt = _run(src)
        reqs, covered = analyze_cacc(rt)
        assert len(reqs) == 1
        assert reqs[0]["satisfied"] is True
        assert covered == 1

    def test_single_clause_only_true_seen_is_unsatisfied(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, covered = analyze_cacc(rt)
        assert reqs[0]["satisfied"] is False
        assert covered == 0

    def test_single_clause_only_false_seen_is_unsatisfied(self):
        rt = _run("x = False\nif x:\n    pass\n")
        reqs, covered = analyze_cacc(rt)
        assert reqs[0]["satisfied"] is False
        assert covered == 0

    def test_observed_true_when_only_true_side_seen(self):
        rt = _run("x = True\nif x:\n    pass\n")
        reqs, _ = analyze_cacc(rt)
        assert reqs[0]["observed"][True] is True
        assert reqs[0]["observed"][False] is False

    def test_observed_both_true_when_both_sides_seen(self):
        src = "def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        assert reqs[0]["observed"][True] is True
        assert reqs[0]["observed"][False] is True

    def test_cacc_sat_where_racc_would_be_unsat(self):
        # Core CACC property: the two sides may be satisfied by events with
        # DIFFERENT minor contexts.
        #
        # check(True, True)  → Event: {a=T, b=T} → pred=True
        # check(False, True) → Event: {a=F}      → pred=False  (b short-circuited)
        #
        # Requirement (major=a, seed minor=(b=T)):
        #   true_side:  any event with a=True  AND pred=True  ✓ (first call)
        #   false_side: any event with a=False AND pred=False ✓ (second call —
        #               CACC accepts this even though b was short-circuited)
        #   → SAT
        #
        # RACC would require a=False with b=True together, which never happens.
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, covered = analyze_cacc(rt)
        cid_a = rt.predicate_meta[0]["clauses"][0]
        req_a = next(r for r in reqs if r["major_cid"] == cid_a)
        assert req_a["satisfied"] is True
        assert covered >= 1

    def test_and_major_b_unsat_when_b_never_seen_as_false(self):
        # check(True, True) and check(False, True): b is always True or absent.
        # Requirement (major=b, seed minor=(a=T)):
        #   true_side:  b=True  AND pred=True  ✓ (first call)
        #   false_side: b=False AND pred=False  — b is never False in any event → UNSAT
        src = "def check(a, b):\n    if a and b:\n        pass\ncheck(True, True)\ncheck(False, True)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        cid_b = rt.predicate_meta[0]["clauses"][1]
        req_b = next(r for r in reqs if r["major_cid"] == cid_b)
        assert req_b["satisfied"] is False

    def test_or_requirement_satisfied_with_matching_context(self):
        # check(False, True)→pred=True; check(False, False)→pred=False
        # Requirement (major=b, seed minor=(a=F)):
        #   true_side:  b=True  AND pred=True  ✓ (first call)
        #   false_side: b=False AND pred=False ✓ (second call) → SAT
        src = "def check(a, b):\n    if a or b:\n        pass\ncheck(False, True)\ncheck(False, False)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        cid_b = rt.predicate_meta[0]["clauses"][1]
        req_b = next(r for r in reqs if r["major_cid"] == cid_b)
        assert req_b["satisfied"] is True

    def test_or_cross_context_satisfaction(self):
        # check(True, False): a=True short-circuits OR. Event: {a=T}→True
        # check(False, False): a=F, b=F both evaluated. Event: {a=F, b=F}→False
        #
        # Requirement (major=a, seed minor=(b=F)) — seeded from second event:
        #   true_side:  a=True  AND pred=True  ✓ (first call, b was absent)
        #   false_side: a=False AND pred=False ✓ (second call)
        #   → SAT via cross-context evidence on the true side
        src = "def check(a, b):\n    if a or b:\n        pass\ncheck(True, False)\ncheck(False, False)\n"
        rt = _run(src)
        reqs, _ = analyze_cacc(rt)
        cid_a = rt.predicate_meta[0]["clauses"][0]
        req_a = next(r for r in reqs if r["major_cid"] == cid_a)
        assert req_a["satisfied"] is True

    def test_covered_count_equals_number_of_satisfied_requirements(self):
        src = "def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n"
        rt = _run(src)
        reqs, covered = analyze_cacc(rt)
        satisfied_count = sum(1 for r in reqs if r["satisfied"])
        assert covered == satisfied_count

    def test_zero_covered_when_nothing_satisfied(self):
        rt = _run("x = True\nif x:\n    pass\n")
        _, covered = analyze_cacc(rt)
        assert covered == 0


# ── _format_minor_context ─────────────────────────────────────────────────────

class TestFormatMinorContext:

    def test_empty_minor_ctx_returns_none_string(self):
        rt = CoverageRuntime()
        assert _format_minor_context(rt, ()) == "<none>"

    def test_single_minor_clause_formatted_correctly(self):
        rt = CoverageRuntime()
        cid = rt.new_clause("a > 0")
        result = _format_minor_context(rt, ((cid, True),))
        assert result == "a > 0=True"

    def test_multiple_minor_clauses_comma_separated(self):
        rt = CoverageRuntime()
        cid0 = rt.new_clause("a > 0")
        cid1 = rt.new_clause("b < 5")
        result = _format_minor_context(rt, ((cid0, True), (cid1, False)))
        assert result == "a > 0=True, b < 5=False"

    def test_false_value_formatted_correctly(self):
        rt = CoverageRuntime()
        cid = rt.new_clause("x")
        result = _format_minor_context(rt, ((cid, False),))
        assert result == "x=False"