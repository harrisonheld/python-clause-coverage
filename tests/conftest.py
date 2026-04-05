import pytest
import coverage_core

# The 'rt' fixture provides a fresh, empty CoverageRuntime instance to any test
# that declares 'rt' as a parameter. Each test gets its own isolated instance,
# so clause/predicate state from one test never leaks into another.
@pytest.fixture
def rt():
    return coverage_core.CoverageRuntime()

# The 'make_target' fixture is a factory: it gives tests a helper function that
# writes a Python source string to a temporary file on disk and returns its path.
# 'tmp_path' is a built-in pytest fixture that provides a unique temp directory
# per test, so each test's file is isolated and cleaned up automatically.
@pytest.fixture
def make_target(tmp_path):
    def _make(src):
        f = tmp_path / "t.py"   # always named t.py inside the unique temp dir
        f.write_text(src)       # write the source string to disk
        return str(f)           # return the path as a string for run_target_file()
    return _make