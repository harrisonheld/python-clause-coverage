import os
import pytest
from coverage_core import run_target_file
from cc import print_report
from cacc import analyze_cacc
from racc import analyze_racc

# Resolve paths to the real target files at the project root
ROOT = os.path.dirname(os.path.dirname(__file__))

def _target(name):
    return os.path.join(ROOT, name)


# ── target1.py ────────────────────────────────────────────────────────────────
# def check(a, b, c):
#     if (a > 0 and b < 5): ...
#     if (1 in c): ...
#
# Calls: check(1,2,[]), check(-1,2,[1]), check(-1,6,[2,3]), check(2,6,[])

class TestTarget1CC:

    def setup_method(self):
        self.rt = run_target_file(_target("target1.py"))

    def test_produces_three_clauses(self):
        assert len(self.rt.clause_data) == 3

    def test_produces_two_predicates(self):
        assert len(self.rt.predicate_meta) == 2

    def test_all_clauses_are_fully_covered(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        assert "PARTIAL" not in out

    def test_cc_reports_three_of_three(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        assert "3/3" in out

    def test_cc_reports_100_percent(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        assert "100.0%" in out


class TestTarget1CACC:

    def setup_method(self):
        rt = run_target_file(_target("target1.py"))
        self.reqs, self.covered = analyze_cacc(rt)

    def test_generates_three_requirements(self):
        assert len(self.reqs) == 3

    def test_all_requirements_satisfied(self):
        assert self.covered == 3

    def test_no_unsatisfied_requirements(self):
        unsat = [r for r in self.reqs if not r["satisfied"]]
        assert unsat == []


class TestTarget1RACC:

    def setup_method(self):
        rt = run_target_file(_target("target1.py"))
        self.reqs, self.covered, self.masked = analyze_racc(rt)

    def test_generates_three_requirements(self):
        assert len(self.reqs) == 3

    def test_two_requirements_satisfied(self):
        assert self.covered == 2

    def test_one_requirement_masked(self):
        assert self.masked == 1

    def test_masked_requirement_is_not_satisfied(self):
        for r in self.reqs:
            if r["masked_by_short_circuit"]:
                assert r["satisfied"] is False

    def test_covered_plus_masked_plus_unsat_equals_total(self):
        plain_unsat = sum(
            1 for r in self.reqs
            if not r["satisfied"] and not r["masked_by_short_circuit"]
        )
        assert self.covered + self.masked + plain_unsat == len(self.reqs)


# ── target2.py ────────────────────────────────────────────────────────────────
# def check(a, b):
#     if (a > 0 and b): ...
#     if (a == 10 and b): ...
#
# Calls: check(5,T), check(10,T), check(-10,F), check(5,F), check(10,F)

class TestTarget2CC:

    def setup_method(self):
        self.rt = run_target_file(_target("target2.py"))

    def test_produces_four_clauses(self):
        assert len(self.rt.clause_data) == 4

    def test_produces_two_predicates(self):
        assert len(self.rt.predicate_meta) == 2

    def test_all_clauses_fully_covered(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        assert "PARTIAL" not in out

    def test_cc_reports_four_of_four(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        assert "4/4" in out

    def test_cc_reports_100_percent(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        assert "100.0%" in out


class TestTarget2CACC:

    def setup_method(self):
        rt = run_target_file(_target("target2.py"))
        self.reqs, self.covered = analyze_cacc(rt)

    def test_generates_four_requirements(self):
        assert len(self.reqs) == 4

    def test_all_requirements_satisfied(self):
        assert self.covered == 4

    def test_no_unsatisfied_requirements(self):
        assert all(r["satisfied"] for r in self.reqs)


class TestTarget2RACC:

    def setup_method(self):
        rt = run_target_file(_target("target2.py"))
        self.reqs, self.covered, self.masked = analyze_racc(rt)

    def test_generates_four_requirements(self):
        assert len(self.reqs) == 4

    def test_two_requirements_satisfied(self):
        assert self.covered == 2

    def test_two_requirements_masked(self):
        # Both `major=leftClause` requirements are masked: when left=False,
        # short-circuit prevents the right clause from being evaluated,
        # so right can never be seen with the required minor context value.
        assert self.masked == 2

    def test_cacc_satisfies_more_than_racc(self):
        rt = run_target_file(_target("target2.py"))
        _, cacc_covered = analyze_cacc(rt)
        assert cacc_covered > self.covered


# ── target3.py ────────────────────────────────────────────────────────────────
# def check(a, b, c):
#     if (a and b and c): ...
#
# Calls: check(True,True,True), check(False,False,False)
# — Only T,T,T and F,F,F are exercised. On the False call, `a=False`
#   short-circuits the entire `and`, so b and c are never evaluated.

class TestTarget3CC:

    def setup_method(self):
        self.rt = run_target_file(_target("target3.py"))

    def test_produces_three_clauses(self):
        assert len(self.rt.clause_data) == 3

    def test_produces_one_predicate(self):
        assert len(self.rt.predicate_meta) == 1

    def test_one_clause_is_full_two_are_partial(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        full_count = out.count("FULL")
        partial_count = out.count("PARTIAL")
        assert full_count == 1
        assert partial_count == 2

    def test_cc_reports_one_of_three(self, capsys):
        print_report(self.rt)
        out = capsys.readouterr().out
        assert "1/3" in out

    def test_b_and_c_never_seen_as_false(self):
        # b (cid1) and c (cid2) short-circuit on the False call — never seen False
        cids = self.rt.predicate_meta[0]["clauses"]
        cid_b, cid_c = cids[1], cids[2]
        assert self.rt.clause_data[cid_b]["false"] is False
        assert self.rt.clause_data[cid_c]["false"] is False


class TestTarget3CACC:

    def setup_method(self):
        rt = run_target_file(_target("target3.py"))
        self.reqs, self.covered = analyze_cacc(rt)

    def test_generates_three_requirements(self):
        assert len(self.reqs) == 3

    def test_one_requirement_satisfied(self):
        # Only major=a is SAT: true side from call(T,T,T), false side from
        # call(F,F,F) — CACC accepts the False call even though b and c
        # were short-circuited (it doesn't require matching minor context).
        assert self.covered == 1

    def test_satisfied_requirement_is_for_first_clause(self):
        # The only SAT requirement must be major=a (cid0), because b and c
        # are never seen as False in any event
        rt = run_target_file(_target("target3.py"))
        cid_a = rt.predicate_meta[0]["clauses"][0]
        sat_reqs = [r for r in self.reqs if r["satisfied"]]
        assert len(sat_reqs) == 1
        assert sat_reqs[0]["major_cid"] == cid_a

    def test_two_requirements_unsatisfied(self):
        unsat = [r for r in self.reqs if not r["satisfied"]]
        assert len(unsat) == 2


class TestTarget3RACC:

    def setup_method(self):
        rt = run_target_file(_target("target3.py"))
        self.reqs, self.covered, self.masked = analyze_racc(rt)

    def test_generates_three_requirements(self):
        assert len(self.reqs) == 3

    def test_zero_requirements_satisfied(self):
        # RACC needs matching minor context on both sides — impossible here
        # because the only False event is from a=False which short-circuits
        # before b and c are evaluated.
        assert self.covered == 0

    def test_one_requirement_masked(self):
        # major=a: false side masked — event with a=False exists but b,c absent
        assert self.masked == 1

    def test_two_requirements_plain_unsat(self):
        plain_unsat = [
            r for r in self.reqs
            if not r["satisfied"] and not r["masked_by_short_circuit"]
        ]
        assert len(plain_unsat) == 2

    def test_racc_satisfies_fewer_than_cacc(self):
        rt = run_target_file(_target("target3.py"))
        _, cacc_covered = analyze_cacc(rt)
        assert self.covered < cacc_covered

    def test_masked_requirement_is_for_first_clause(self):
        rt = run_target_file(_target("target3.py"))
        cid_a = rt.predicate_meta[0]["clauses"][0]
        masked_reqs = [r for r in self.reqs if r["masked_by_short_circuit"]]
        assert len(masked_reqs) == 1
        assert masked_reqs[0]["major_cid"] == cid_a