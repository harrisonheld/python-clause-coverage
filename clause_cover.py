import ast
import sys
import types

# ============================================================
# Coverage Storage
# ============================================================
CLAUSE_DATA = {}
CLAUSE_META = {}
CLAUSE_ID = 0


def new_clause(expr_src):
    global CLAUSE_ID
    cid = CLAUSE_ID
    CLAUSE_ID += 1

    CLAUSE_DATA[cid] = {"true": False, "false": False}
    CLAUSE_META[cid] = expr_src
    return cid


def __cc__(cid, value):
    """
    Runtime hook: records clause truth value
    without changing program semantics.
    """
    if value:
        CLAUSE_DATA[cid]["true"] = True
    else:
        CLAUSE_DATA[cid]["false"] = True
    return value


# ============================================================
# AST Instrumentation
# ============================================================
class ClauseInstrumenter(ast.NodeTransformer):
    """
    Instruments ONLY boolean clauses appearing inside predicates.
    Prevents false positives like function names or assignments.
    """

    def __init__(self):
        super().__init__()
        self.in_predicate = False

    # --------------------------------------------------------
    # Predicate entry points
    # --------------------------------------------------------
    def visit_If(self, node):
        node.test = self.visit_predicate(node.test)
        node.body = [self.visit(n) for n in node.body]
        node.orelse = [self.visit(n) for n in node.orelse]
        return node

    def visit_While(self, node):
        node.test = self.visit_predicate(node.test)
        node.body = [self.visit(n) for n in node.body]
        node.orelse = [self.visit(n) for n in node.orelse]
        return node

    def visit_IfExp(self, node):  # ternary operator
        node.test = self.visit_predicate(node.test)
        node.body = self.visit(node.body)
        node.orelse = self.visit(node.orelse)
        return node

    def visit_Assert(self, node):
        node.test = self.visit_predicate(node.test)
        return node

    def visit_predicate(self, expr):
        old = self.in_predicate
        self.in_predicate = True
        expr = self.visit(expr)
        self.in_predicate = old
        return expr

    # --------------------------------------------------------
    # Boolean structure traversal
    # --------------------------------------------------------
    def visit_BoolOp(self, node):
        node.values = [self.visit(v) for v in node.values]
        return node

    def visit_UnaryOp(self, node):
        node.operand = self.visit(node.operand)
        return node

    # --------------------------------------------------------
    # ACTUAL CLAUSES
    # --------------------------------------------------------
    def visit_Compare(self, node):
        if self.in_predicate:
            return self.wrap_clause(node)
        return node

    def visit_Name(self, node):
        """
        Bare boolean variables allowed ONLY inside predicates.
        """
        if self.in_predicate and isinstance(node.ctx, ast.Load):
            return self.wrap_clause(node)
        return node

    # --------------------------------------------------------
    def wrap_clause(self, node):
        src = ast.unparse(node)
        cid = new_clause(src)

        return ast.Call(
            func=ast.Name(id="__cc__", ctx=ast.Load()),
            args=[ast.Constant(cid), node],
            keywords=[],
        )


# ============================================================
# Reporting
# ============================================================
def print_report():
    print("\n==== Clause Coverage Report ====\n")

    covered = 0

    for cid in sorted(CLAUSE_DATA):
        data = CLAUSE_DATA[cid]
        expr = CLAUSE_META[cid]

        true_seen = data["true"]
        false_seen = data["false"]

        full = true_seen and false_seen
        status = "FULL" if full else "PARTIAL"

        if full:
            covered += 1

        print(f"[Clause {cid}] {expr}")
        print(f"    True seen : {true_seen}")
        print(f"    False seen: {false_seen}")
        print(f"    Coverage  : {status}\n")

    total = len(CLAUSE_DATA)
    pct = (covered / total * 100) if total else 100.0

    print("--------------------------------")
    print(f"TCC Coverage: {covered}/{total} ({pct:.1f}%)")
    print("--------------------------------")


# ============================================================
# Execution Pipeline
# ============================================================
def instrument_source(source_code):
    tree = ast.parse(source_code)

    instrumenter = ClauseInstrumenter()
    tree = instrumenter.visit(tree)
    ast.fix_missing_locations(tree)

    return tree


def execute_instrumented(tree, filename):
    module = types.ModuleType("__instrumented__")

    # inject runtime hook
    module.__dict__["__cc__"] = __cc__

    code = compile(tree, filename, "exec")
    exec(code, module.__dict__)


# ============================================================
# Main
# ============================================================
def main():
    if len(sys.argv) != 2:
        print("Usage: python clause_cover.py target.py")
        sys.exit(1)

    filename = sys.argv[1]

    with open(filename, "r") as f:
        source = f.read()

    tree = instrument_source(source)
    execute_instrumented(tree, filename)
    print_report()


if __name__ == "__main__":
    main()