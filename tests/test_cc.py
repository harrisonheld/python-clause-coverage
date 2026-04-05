import pytest
from coverage_core import CoverageRuntime, instrument_source, execute_instrumented
from cc import print_report, run
from racc import analyze_racc, _find_events_for_context, _is_masked_by_short_circuit, run as racc_run
from cacc import analyze_cacc, _format_minor_context, run as cacc_run


# Helper: build a runtime with pre-populated clause_data without running
# instrumentation. Used for testing print_report in isolation.
def _make_runtime_with_clauses(clauses):
    # clauses: list of (expr_src, seen_true, seen_false)
    rt = CoverageRuntime()
    for expr, seen_true, seen_false in clauses:
        cid = rt.new_clause(expr)
        if seen_true:
            rt.hook(cid, True)
        if seen_false:
            rt.hook(cid, False)
    return rt


# Helper: instrument and execute a source string, return the runtime.
def _run_src(src):
    rt = CoverageRuntime()
    tree = instrument_source(src, rt)
    execute_instrumented(tree, "<test>", rt)
    return rt


# ── print_report: coverage status per clause ──────────────────────────────────

class TestPrintReportClauseStatus:

    def test_both_sides_seen_reports_full(self, capsys):
        rt = _make_runtime_with_clauses([("a > 0", True, True)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "FULL" in out

    def test_only_true_seen_reports_partial(self, capsys):
        rt = _make_runtime_with_clauses([("a > 0", True, False)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "PARTIAL" in out

    def test_only_false_seen_reports_partial(self, capsys):
        rt = _make_runtime_with_clauses([("a > 0", False, True)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "PARTIAL" in out

    def test_neither_side_seen_reports_partial(self, capsys):
        rt = _make_runtime_with_clauses([("a > 0", False, False)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "PARTIAL" in out

    def test_full_clause_shows_true_seen_true(self, capsys):
        rt = _make_runtime_with_clauses([("x", True, True)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "True seen : True" in out
        assert "False seen: True" in out

    def test_partial_clause_shows_correct_flags(self, capsys):
        rt = _make_runtime_with_clauses([("x", True, False)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "True seen : True" in out
        assert "False seen: False" in out

    def test_clause_expr_appears_in_output(self, capsys):
        rt = _make_runtime_with_clauses([("my_var > 42", True, False)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "my_var > 42" in out

    def test_multiple_clauses_all_reported(self, capsys):
        rt = _make_runtime_with_clauses([
            ("a > 0", True, True),
            ("b < 5", True, False),
            ("c == 1", False, True),
        ])
        print_report(rt)
        out = capsys.readouterr().out
        assert "a > 0" in out
        assert "b < 5" in out
        assert "c == 1" in out

    def test_clauses_reported_in_sorted_cid_order(self, capsys):
        rt = _make_runtime_with_clauses([
            ("first",  True, True),
            ("second", True, False),
            ("third",  False, True),
        ])
        print_report(rt)
        out = capsys.readouterr().out
        pos_first  = out.index("first")
        pos_second = out.index("second")
        pos_third  = out.index("third")
        assert pos_first < pos_second < pos_third


# ── print_report: coverage totals ─────────────────────────────────────────────

class TestPrintReportTotals:

    def test_zero_clauses_reports_100_percent(self, capsys):
        rt = CoverageRuntime()
        print_report(rt)
        out = capsys.readouterr().out
        assert "0/0" in out
        assert "100.0%" in out

    def test_all_full_reports_100_percent(self, capsys):
        rt = _make_runtime_with_clauses([
            ("a", True, True),
            ("b", True, True),
        ])
        print_report(rt)
        out = capsys.readouterr().out
        assert "2/2" in out
        assert "100.0%" in out

    def test_none_full_reports_0_percent(self, capsys):
        rt = _make_runtime_with_clauses([
            ("a", True, False),
            ("b", False, True),
        ])
        print_report(rt)
        out = capsys.readouterr().out
        assert "0/2" in out
        assert "0.0%" in out

    def test_half_full_reports_50_percent(self, capsys):
        rt = _make_runtime_with_clauses([
            ("a", True, True),
            ("b", True, False),
        ])
        print_report(rt)
        out = capsys.readouterr().out
        assert "1/2" in out
        assert "50.0%" in out

    def test_one_of_three_full_reports_correct_fraction(self, capsys):
        rt = _make_runtime_with_clauses([
            ("a", True, True),
            ("b", True, False),
            ("c", False, False),
        ])
        print_report(rt)
        out = capsys.readouterr().out
        assert "1/3" in out

    def test_report_header_present(self, capsys):
        rt = CoverageRuntime()
        print_report(rt)
        out = capsys.readouterr().out
        assert "Clause Coverage Report (CC)" in out

    def test_tcc_label_present_in_output(self, capsys):
        rt = _make_runtime_with_clauses([("x", True, True)])
        print_report(rt)
        out = capsys.readouterr().out
        assert "TCC Coverage" in out


# ── run: integration ──────────────────────────────────────────────────────────

class TestRun:

    def test_run_produces_report_output(self, make_target, capsys):
        path = make_target("x = True\nif x:\n    pass\n")
        run(path)
        out = capsys.readouterr().out
        assert "Clause Coverage Report (CC)" in out

    def test_run_reports_partial_when_only_one_side_seen(self, make_target, capsys):
        # Only True branch taken — clause never seen as False
        path = make_target("x = True\nif x:\n    pass\n")
        run(path)
        out = capsys.readouterr().out
        assert "PARTIAL" in out

    def test_run_reports_full_when_both_sides_seen(self, make_target, capsys):
        src = "def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n"
        path = make_target(src)
        run(path)
        out = capsys.readouterr().out
        assert "FULL" in out
        assert "PARTIAL" not in out

    def test_run_correct_fraction_in_output(self, make_target, capsys):
        # Two clauses, both fully covered
        src = (
            "def check(a, b):\n"
            "    if a:\n        pass\n"
            "    if b:\n        pass\n"
            "check(True, True)\n"
            "check(False, False)\n"
        )
        path = make_target(src)
        run(path)
        out = capsys.readouterr().out
        assert "2/2" in out
        assert "100.0%" in out

    def test_run_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            run("no_such_file.py")


# ── racc: integration ──────────────────────────────────────────────────────────

class TestRaccRun:
    def test_produces_report_output(self, make_target, capsys):
        path = make_target("def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n")
        racc_run(path)
        out = capsys.readouterr().out
        assert "Restricted Active Clause Coverage" in out

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            racc_run("no_such_file.py")


# ── cacc: integration ──────────────────────────────────────────────────────────

class TestCaccRun:
    def test_produces_report_output(self, make_target, capsys):
        path = make_target("def check(x):\n    if x:\n        pass\ncheck(True)\ncheck(False)\n")
        cacc_run(path)
        out = capsys.readouterr().out
        assert "Correlated Active Clause Coverage" in out

    def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            cacc_run("no_such_file.py")