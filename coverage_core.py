import ast
import types


class CoverageRuntime:
    def __init__(self):
        self.clause_data = {}
        self.clause_meta = {}
        self.clause_id = 0

        self.predicate_meta = {}
        self.predicate_id = 0
        self.predicate_events = []
        self._predicate_stack = []

    def new_clause(self, expr_src):
        cid = self.clause_id
        self.clause_id += 1

        self.clause_data[cid] = {"true": False, "false": False}
        self.clause_meta[cid] = expr_src
        return cid

    def new_predicate(self, expr_src):
        pid = self.predicate_id
        self.predicate_id += 1

        self.predicate_meta[pid] = {
            "expr": expr_src,
            "clauses": [],
            "logic_expr": "",
            "logic_code": None,
        }
        return pid

    def add_clause_to_predicate(self, pid, cid):
        clauses = self.predicate_meta[pid]["clauses"]
        if cid not in clauses:
            clauses.append(cid)

    def set_predicate_logic(self, pid, logic_expr_node):
        expr = ast.Expression(body=logic_expr_node)
        ast.fix_missing_locations(expr)
        self.predicate_meta[pid]["logic_expr"] = ast.unparse(logic_expr_node)
        self.predicate_meta[pid]["logic_code"] = compile(expr, "<predicate_logic>", "eval")

    def eval_predicate_logic(self, pid, assignment):
        env = {f"c{cid}": bool(value) for cid, value in assignment.items()}
        return bool(eval(self.predicate_meta[pid]["logic_code"], {"__builtins__": {}}, env))

    def hook(self, cid, value):
        if value:
            self.clause_data[cid]["true"] = True
        else:
            self.clause_data[cid]["false"] = True

        if self._predicate_stack:
            self._predicate_stack[-1]["clause_values"][cid] = bool(value)

        return value

    def predicate_hook(self, pid, thunk):
        ctx = {"predicate_id": pid, "clause_values": {}}
        self._predicate_stack.append(ctx)

        try:
            result = thunk()
        except Exception:
            self._predicate_stack.pop()
            raise

        self._predicate_stack.pop()

        self.predicate_events.append(
            {
                "predicate_id": pid,
                "clause_values": dict(ctx["clause_values"]),
                "predicate_value": bool(result),
            }
        )

        return result


class ClauseCallToNameTransformer(ast.NodeTransformer):
    def visit_Call(self, node):
        node = self.generic_visit(node)

        if not isinstance(node, ast.Call):
            return node

        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "__cc__"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, int)
        ):
            cid = node.args[0].value
            return ast.Name(id=f"c{cid}", ctx=ast.Load())

        return node


class ClauseInstrumenter(ast.NodeTransformer):
    def __init__(self, runtime):
        super().__init__()
        self.in_predicate = False
        self.runtime = runtime
        self.current_predicate_id = None

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

    def visit_IfExp(self, node):
        node.test = self.visit_predicate(node.test)
        node.body = self.visit(node.body)
        node.orelse = self.visit(node.orelse)
        return node

    def visit_Assert(self, node):
        node.test = self.visit_predicate(node.test)
        return node

    def visit_predicate(self, expr):
        expr_src = ast.unparse(expr)
        pid = self.runtime.new_predicate(expr_src)

        old = self.in_predicate
        old_pid = self.current_predicate_id

        self.in_predicate = True
        self.current_predicate_id = pid
        expr = self.visit(expr)
        self.in_predicate = old
        self.current_predicate_id = old_pid

        logic_expr = ClauseCallToNameTransformer().visit(
            ast.parse(ast.unparse(expr), mode="eval").body
        )
        self.runtime.set_predicate_logic(pid, logic_expr)

        return ast.Call(
            func=ast.Name(id="__pred__", ctx=ast.Load()),
            args=[
                ast.Constant(pid),
                ast.Lambda(
                    args=ast.arguments(
                        posonlyargs=[],
                        args=[],
                        kwonlyargs=[],
                        kw_defaults=[],
                        defaults=[],
                    ),
                    body=expr,
                ),
            ],
            keywords=[],
        )

    def visit_BoolOp(self, node):
        node.values = [self.visit(v) for v in node.values]
        return node

    def visit_UnaryOp(self, node):
        node.operand = self.visit(node.operand)
        return node

    def visit_Compare(self, node):
        if self.in_predicate:
            return self.wrap_clause(node)
        return node

    def visit_Name(self, node):
        if self.in_predicate and isinstance(node.ctx, ast.Load):
            return self.wrap_clause(node)
        return node

    def wrap_clause(self, node):
        src = ast.unparse(node)
        cid = self.runtime.new_clause(src)

        if self.current_predicate_id is not None:
            self.runtime.add_clause_to_predicate(self.current_predicate_id, cid)

        return ast.Call(
            func=ast.Name(id="__cc__", ctx=ast.Load()),
            args=[ast.Constant(cid), node],
            keywords=[],
        )


def instrument_source(source_code, runtime):
    tree = ast.parse(source_code)

    instrumenter = ClauseInstrumenter(runtime)
    tree = instrumenter.visit(tree)
    ast.fix_missing_locations(tree)

    return tree


def execute_instrumented(tree, filename, runtime):
    module = types.ModuleType("__instrumented__")
    module.__dict__["__cc__"] = runtime.hook
    module.__dict__["__pred__"] = runtime.predicate_hook

    code = compile(tree, filename, "exec")
    exec(code, module.__dict__)


def run_target_file(filename):
    runtime = CoverageRuntime()

    with open(filename, "r") as f:
        source = f.read()

    tree = instrument_source(source, runtime)
    execute_instrumented(tree, filename, runtime)
    return runtime