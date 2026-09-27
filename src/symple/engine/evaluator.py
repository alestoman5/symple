"""The evaluator: walks the AST and computes results with SymPy.

User input is never handed to Python's ``eval``; every construct is interpreted
here, and function calls only reach the allow-listed :data:`BUILTINS`.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import sympy as sp

from ..catalog import PROTECTED
from ..lang import ast as A
from ..lang.parser import parse
from .builtins import BUILTINS, basic, items
from .printing import Output, make_output
from .values import (NULL, ArrowFunction, Builtin, Equation, EvalError, ExprFunction, ExprSeq,
                     MList, MRange, MSet, MString, Procedure, eq_parts, is_callable)

CONSTANTS = {
    "Pi": sp.pi, "I": sp.I, "infinity": sp.oo, "true": sp.true, "false": sp.false,
    "gamma": sp.EulerGamma,
}

_RELATIONS = {"=": sp.Eq, "<>": sp.Ne, "<": sp.Lt, "<=": sp.Le, ">": sp.Gt, ">=": sp.Ge}

# Elementary functions shown with their real notation when displaying an arrow
# function's body without evaluating it (x -> sin(x)^2 should render nicely).
_INERT_FUNCS = {
    "sin": sp.sin, "cos": sp.cos, "tan": sp.tan, "exp": sp.exp, "ln": sp.log, "sqrt": sp.sqrt,
    "abs": sp.Abs, "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh, "arcsin": sp.asin,
    "arccos": sp.acos, "arctan": sp.atan, "log": sp.log,
}


class _Signal(Exception):
    pass


class _Return(_Signal):
    def __init__(self, value):
        self.value = value


class _Break(_Signal):
    pass


class _Next(_Signal):
    pass


_UNSET = object()      # a declared but unassigned local variable


@dataclass
class Session:
    env: dict = field(default_factory=dict)
    history: list = field(default_factory=list)   # most recent last, at most 3
    digits: int = 10


class Evaluator:
    def __init__(self):
        self.session = Session()
        self.frames: list[dict] = []      # local scopes of running procedures
        self.outputs: list[Output] = []
        self.src = ""

    # --------------------------------------------------------------- driver

    def run(self, src: str) -> list[Output]:
        """Execute all statements in *src* and return what should be displayed."""
        self.outputs = []
        self.src = src
        result = parse(src)
        if not result.ok:
            for d in result.diagnostics:
                if d.severity == "error":
                    self.outputs.append(Output("error", text=f"Error, {d.describe(src)}"))
            return self.outputs
        for stmt in result.statements:
            try:
                self.exec_stmt(stmt, display=stmt.show)
            except EvalError as e:
                self.outputs.append(Output("error", text=f"Error, {e}"))
                break
            except _Return:
                self.outputs.append(Output("error", text="Error, 'return' outside a procedure"))
                break
            except (_Break, _Next):
                self.outputs.append(Output("error", text="Error, 'break' or 'next' outside a loop"))
                break
            except RecursionError:
                self.frames.clear()
                self.outputs.append(Output("error", text="Error, too many levels of recursion"))
                break
            except ZeroDivisionError:
                self.outputs.append(Output("error", text="Error, numeric exception: division by zero"))
                break
            except Exception as e:  # an internal SymPy failure: report, don't crash
                self.frames.clear()
                msg = str(e) or type(e).__name__
                self.outputs.append(Output("error", text=f"Error, {msg}"))
                break
        return self.outputs

    def reset(self) -> None:
        self.session = Session()

    def emit(self, value, label=None) -> None:
        if isinstance(value, ArrowFunction) and value.display is None:
            value.display = self._display_form(value)
        self.outputs.append(make_output(value, label))

    def defined_names(self) -> list[str]:
        return sorted(self.session.env)

    # ----------------------------------------------------------- statements

    def exec_block(self, stmts, display: bool):
        value = NULL
        for stmt in stmts:
            value = self.exec_stmt(stmt, display)
        return value

    def exec_stmt(self, stmt, display: bool):
        if isinstance(stmt, A.ExprStmt):
            if isinstance(stmt.expr, A.Name) and stmt.expr.id == "restart" and not self.frames:
                self.reset()
                return NULL
            value = self.eval(stmt.expr)
            if not self.frames and not (isinstance(value, ExprSeq) and not value):
                hist = self.session.history
                hist.append(value)
                del hist[:-3]
            if display and not (isinstance(value, ExprSeq) and not value):
                self.emit(value)
            return value
        if isinstance(stmt, A.Assign):
            return self.exec_assign(stmt, display)
        if isinstance(stmt, A.If):
            for cond, body in stmt.branches:
                if self.truth(self.eval(cond)):
                    return self.exec_block(body, display)
            if stmt.orelse is not None:
                return self.exec_block(stmt.orelse, display)
            return NULL
        if isinstance(stmt, A.For):
            return self.exec_for(stmt, display)
        if isinstance(stmt, A.Return):
            raise _Return(NULL if stmt.value is None else self.eval(stmt.value))
        if isinstance(stmt, A.Break):
            raise _Break()
        if isinstance(stmt, A.Next):
            raise _Next()
        raise EvalError(f"unsupported statement {type(stmt).__name__}")

    def exec_assign(self, stmt: A.Assign, display: bool):
        value = self.eval(stmt.value)
        if len(stmt.targets) > 1:
            if not isinstance(value, ExprSeq) or len(value) != len(stmt.targets):
                raise EvalError(f"cannot assign {len(value) if isinstance(value, ExprSeq) else 1} "
                                f"value(s) to {len(stmt.targets)} names")
            values = list(value)
        else:
            values = [value]
        for target, v in zip(stmt.targets, values):
            self.assign(target, v)
            if display:
                label = target.id if isinstance(target, A.Name) else self.src[target.start:target.end]
                self.emit(v, label)
        return value

    def assign(self, target, value) -> None:
        if isinstance(target, A.Name):
            name = target.id
            if name == "Digits":
                n = basic(value, "Digits")
                if not (n.is_Integer and 1 <= n <= 10000):
                    raise EvalError("Digits must be an integer between 1 and 10000")
                self.session.digits = int(n)
                return
            if name in PROTECTED or name in CONSTANTS:
                raise EvalError(f"attempting to assign to '{name}' which is protected")
            if isinstance(value, sp.Symbol) and value.name == name:   # x := 'x'
                self._unassign(name)
                return
            if isinstance(value, sp.Basic) and sp.Symbol(name) in value.free_symbols:
                raise EvalError(f"recursive assignment: '{name}' appears in its own value")
            frame = self._frame_for(name)
            frame[name] = value
            return
        if isinstance(target, A.Index):
            self._assign_index(target, value)
            return
        raise EvalError("invalid assignment target")

    def _frame_for(self, name: str) -> dict:
        """The scope an assignment to *name* goes to."""
        if self.frames:
            frame = self.frames[-1]
            if name in frame:
                return frame
            if "__proc__" in frame and name not in frame["__globals__"]:
                return frame  # undeclared names inside a procedure become local
        return self.session.env

    def _unassign(self, name: str) -> None:
        if self.frames and name in self.frames[-1]:
            self.frames[-1][name] = _UNSET
        else:
            self.session.env.pop(name, None)

    def _assign_index(self, target: A.Index, value) -> None:
        idx = [self.eval(i) for i in target.indices]
        if isinstance(target.base, A.Name):
            name = target.base.id
            container = self.lookup(name)
            if container is _UNSET or container is None:
                key = self._indexed_key(name, idx)
                self.session.env[key] = value
                return
        else:
            container = self.eval(target.base)
        if isinstance(container, sp.MatrixBase):
            pos = [self._py_index(i, "matrix") for i in idx]
            if len(pos) == 1 and 1 in container.shape:
                container[pos[0]] = basic(value, "assign")
            elif len(pos) == 2:
                container[pos[0], pos[1]] = basic(value, "assign")
            else:
                raise EvalError("invalid matrix index")
            return
        if isinstance(container, MList) and len(idx) == 1:
            k = self._py_index(idx[0], "list", len(container))
            container[k] = value
            return
        raise EvalError("cannot assign to this indexed expression")

    def exec_for(self, stmt: A.For, display: bool):
        def run_body() -> bool:
            """Run the loop body; False means 'break'."""
            try:
                self.exec_block(stmt.body, display)
            except _Break:
                return False
            except _Next:
                pass
            return True

        def cond_ok() -> bool:
            return stmt.cond is None or self.truth(self.eval(stmt.cond))

        var = stmt.var
        if stmt.in_ is not None:
            for v in self._iterate(self.eval(stmt.in_)):
                self._set_loop_var(var, v)
                if not cond_ok() or not run_body():
                    break
            return NULL
        if var is None:  # plain while loop
            while cond_ok():
                if not run_body():
                    break
            return NULL
        start = self.eval(stmt.frm) if stmt.frm else sp.Integer(1)
        step = self.eval(stmt.by) if stmt.by else sp.Integer(1)
        stop = self.eval(stmt.to) if stmt.to else None
        for v, what in ((start, "from"), (step, "by"), (stop, "to")):
            if v is not None and not (isinstance(v, sp.Basic) and v.is_number and v.is_real):
                raise EvalError(f"loop '{what}' value must be a real number, got {v}")
        if step == 0:
            raise EvalError("loop 'by' value must not be zero")
        i = start
        while stop is None or (i <= stop if step > 0 else i >= stop):
            self._set_loop_var(var, i)
            if not cond_ok() or not run_body():
                break
            i = i + step
        else:
            self._set_loop_var(var, i)
        return NULL

    def _set_loop_var(self, name, value):
        self._frame_for(name)[name] = value

    def _iterate(self, v):
        if isinstance(v, (MList, MSet, ExprSeq)):
            return list(v)
        if isinstance(v, sp.MatrixBase):
            return list(v)
        if isinstance(v, MRange):
            raise EvalError("use 'for i from a to b' to loop over a range")
        if isinstance(v, (sp.Add, sp.Mul)):
            return list(v.args)
        return [v]

    # ---------------------------------------------------------- expressions

    def eval(self, node):
        method = getattr(self, "eval_" + type(node).__name__, None)
        if method is None:
            raise EvalError(f"cannot evaluate {type(node).__name__}")
        return method(node)

    def eval_Num(self, node: A.Num):
        text = node.text
        if any(c in text for c in ".eE"):
            return sp.Float(text, self.session.digits)
        return sp.Integer(text)

    def eval_Str(self, node: A.Str):
        return MString(node.value)

    def eval_Name(self, node: A.Name):
        return self.eval_name(node.id)

    def eval_Uneval(self, node: A.Uneval):
        if isinstance(node.expr, A.Name):
            return sp.Symbol(node.expr.id)
        return self.eval(node.expr)

    def eval_Ditto(self, node: A.Ditto):
        hist = self.session.history
        if len(hist) < node.depth:
            return NULL
        return hist[-node.depth]

    def eval_Seq(self, node: A.Seq):
        return ExprSeq(self.flatten(self.eval(i) for i in node.items))

    def eval_ListLit(self, node: A.ListLit):
        return MList(self.flatten(self.eval(i) for i in node.items))

    def eval_SetLit(self, node: A.SetLit):
        return MSet(self.flatten(self.eval(i) for i in node.items))

    def eval_Range(self, node: A.Range):
        return MRange(self.eval(node.lo), self.eval(node.hi))

    def eval_Arrow(self, node: A.Arrow):
        return ArrowFunction(node.params, node.body, self.frames[-1] if self.frames else None,
                             self.src[node.start:node.end])

    def eval_Proc(self, node: A.Proc):
        return Procedure(node.params, node.locals, node.globals, node.body,
                         self.frames[-1] if self.frames else None, self.src[node.start:node.end])

    def eval_UnOp(self, node: A.UnOp):
        if node.op == "not":
            v = self.eval(node.operand)
            t = self.try_truth(v)
            return sp.Not(v) if t is None else sp.S(not t)
        v = self.eval(node.operand)
        if node.op == "-":
            return self.arith("*", sp.Integer(-1), v)
        if node.op == "+":
            return v
        if node.op == "!":
            return sp.factorial(basic(v, "factorial"))
        raise EvalError(f"unknown operator {node.op}")

    def eval_BinOp(self, node: A.BinOp):
        op = node.op
        if op == "$":
            return self._dollar(node)
        if op in ("and", "or", "xor", "implies"):
            return self._logic(op, node)
        left, right = self.eval(node.left), self.eval(node.right)
        if op in _RELATIONS:
            if isinstance(left, (sp.Basic, bool)) and isinstance(right, (sp.Basic, bool)) \
                    and not isinstance(left, sp.MatrixBase) and not isinstance(right, sp.MatrixBase):
                return _RELATIONS[op](left, right, evaluate=False)
            if op == "=":
                return Equation(left, right)
            raise EvalError(f"cannot compare {left} and {right}")
        if op in ("union", "intersect", "minus"):
            if not (isinstance(left, MSet) and isinstance(right, MSet)):
                raise EvalError(f"'{op}' needs two sets")
            if op == "union":
                return MSet([*left, *right])
            if op == "intersect":
                return MSet(x for x in left if any(x == y for y in right))
            return MSet(x for x in left if not any(x == y for y in right))
        if op == "mod":
            return sp.Mod(basic(left, "mod"), basic(right, "mod"))
        return self.arith(op, left, right)

    def arith(self, op, left, right):
        """Arithmetic with Maple conventions: equations and lists are handled element-wise."""
        lp, rp = eq_parts(left), eq_parts(right)
        if lp or rp:
            if lp and rp:
                return self._make_eq(self.arith(op, lp[0], rp[0]), self.arith(op, lp[1], rp[1]))
            if lp:
                return self._make_eq(self.arith(op, lp[0], right), self.arith(op, lp[1], right))
            return self._make_eq(self.arith(op, left, rp[0]), self.arith(op, left, rp[1]))
        if isinstance(left, MList) or isinstance(right, MList):
            if isinstance(left, MList) and isinstance(right, MList):
                if len(left) != len(right) or op not in "+-":
                    raise EvalError(f"invalid list operation '{op}'")
                return MList(self.arith(op, a, b) for a, b in zip(left, right))
            if op in "*/" and isinstance(left, MList):
                return MList(self.arith(op, a, right) for a in left)
            if op == "*":
                return MList(self.arith(op, left, b) for b in right)
            raise EvalError(f"invalid list operation '{op}'")
        a, b = self._operand(left, op), self._operand(right, op)
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == ".":
            return a * b
        if op == "/":
            if isinstance(b, sp.MatrixBase):
                return a * b.inv()
            if b == 0 and getattr(a, "is_number", False):
                raise EvalError("numeric exception: division by zero")
            return a / b
        if op == "^":
            if isinstance(a, sp.MatrixBase):
                return a ** b
            if a == 0 and getattr(b, "is_negative", False):
                raise EvalError("numeric exception: division by zero")
            return sp.Pow(a, b)
        raise EvalError(f"unknown operator {op}")

    @staticmethod
    def _make_eq(lhs, rhs):
        if isinstance(lhs, sp.Basic) and isinstance(rhs, sp.Basic):
            return sp.Eq(lhs, rhs, evaluate=False)
        return Equation(lhs, rhs)

    @staticmethod
    def _operand(v, op):
        if isinstance(v, (sp.Basic, sp.MatrixBase)):
            return v
        if isinstance(v, bool):
            return sp.S(v)
        if isinstance(v, ExprSeq):
            raise EvalError(f"invalid use of a sequence with '{op}'")
        what = "a string" if isinstance(v, MString) else "a function" if is_callable(v) else type(v).__name__
        raise EvalError(f"invalid operand for '{op}': {what}")

    def _logic(self, op, node):
        left = self.eval(node.left)
        tl = self.try_truth(left)
        if op == "and" and tl is False:
            return sp.false
        if op == "or" and tl is True:
            return sp.true
        if op == "implies" and tl is False:
            return sp.true
        right = self.eval(node.right)
        tr = self.try_truth(right)
        if tl is not None and tr is not None:
            result = {"and": tl and tr, "or": tl or tr, "xor": tl != tr,
                      "implies": (not tl) or tr}[op]
            return sp.S(result)
        fn = {"and": sp.And, "or": sp.Or, "xor": sp.Xor, "implies": sp.Implies}[op]
        return fn(left, right)

    def _dollar(self, node: A.BinOp):
        right = node.right
        if isinstance(right, A.BinOp) and right.op == "=":
            from .builtins import _seq
            return _seq(self, node.left, right)
        n = basic(self.eval(right), "$")
        if not n.is_Integer or n < 0:
            raise EvalError("the right side of '$' must be a non-negative integer or i = a..b")
        value = self.eval(node.left)
        return ExprSeq([value] * int(n))

    # -------------------------------------------------------- names & calls

    def lookup(self, name: str):
        """Value of *name* from local frames or the session, or None."""
        frame = self.frames[-1] if self.frames else None
        while frame is not None:
            if name in frame:
                return frame[name]
            frame = frame.get("__parent__")
        return self.session.env.get(name)

    def eval_name(self, name: str, _seen=None):
        value = self.lookup(name)
        if value is _UNSET:
            return sp.Symbol(name)
        if value is not None:
            return self._full_eval(value, _seen or {name})
        if name in CONSTANTS:
            return CONSTANTS[name]
        if name == "Digits":
            return sp.Integer(self.session.digits)
        if name in BUILTINS:
            return BUILTINS[name]
        return sp.Symbol(name)

    def _full_eval(self, value, seen):
        """Maple-style full evaluation: substitute names assigned after *value* was stored."""
        if not isinstance(value, sp.Basic) or isinstance(value, sp.MatrixBase):
            return value
        repl = {}
        for s in value.free_symbols:
            if isinstance(s, sp.Symbol) and s.name not in seen and self.lookup(s.name) not in (None, _UNSET):
                v = self.eval_name(s.name, seen | {s.name})
                if isinstance(v, sp.Basic):
                    repl[s] = v
        return value.xreplace(repl) if repl else value

    def eval_Call(self, node: A.Call):
        func = node.func
        if isinstance(func, A.Name):
            name = func.id
            value = self.lookup(name)
            if value is None or value is _UNSET:
                if name in BUILTINS and value is None:
                    b = BUILTINS[name]
                    if b.raw:
                        return b.fn(self, *node.args)
                    args = self.eval_args(node.args)
                    try:
                        return b.fn(self, *args)
                    except TypeError as e:
                        if "positional argument" in str(e):
                            raise EvalError("wrong number of arguments", name) from None
                        raise
                    except EvalError as e:
                        e.where = e.where or name
                        raise
                    except (ValueError, NotImplementedError, sp.PolynomialError) as e:
                        raise EvalError(str(e) or type(e).__name__, name) from None
                if name in CONSTANTS:
                    raise EvalError(f"'{name}' is a constant and cannot be called")
                return self._undefined_call(name, self.eval_args(node.args))
            fval = self._full_eval(value, {name})
            return self.apply(fval, self.eval_args(node.args), name)
        if isinstance(func, A.Index) and isinstance(func.base, A.Name) and func.base.id in ("log", "evalf"):
            (sub,) = [self.eval(i) for i in func.indices] or [None]
            args = self.eval_args(node.args)
            if len(args) != 1:
                raise EvalError("expects 1 argument", func.base.id)
            return BUILTINS[func.base.id].fn(self, args[0], sub)
        fval = self.eval(func)
        return self.apply(fval, self.eval_args(node.args))

    def eval_args(self, nodes) -> list:
        return self.flatten(self.eval(n) for n in nodes)

    @staticmethod
    def flatten(values) -> list:
        out = []
        for v in values:
            if isinstance(v, ExprSeq):
                out.extend(v)
            else:
                out.append(v)
        return out

    def apply(self, fval, args, name: str | None = None):
        if isinstance(fval, Builtin):
            if fval.raw:
                raise EvalError(f"'{fval.name}' cannot be used as a function value")
            return fval.fn(self, *args)
        if is_callable(fval):
            return fval(self, args)
        if isinstance(fval, sp.FunctionClass):
            return fval(*(basic(a, "call") for a in args))
        if isinstance(fval, sp.Symbol):
            return self._undefined_call(fval.name, args)
        raise EvalError(f"'{name or fval}' is not a function")

    def _undefined_call(self, name, args):
        return sp.Function(name)(*(basic(a, name) for a in args))

    def call_user(self, fn, args):
        if len(args) < len(fn.params):
            missing = fn.params[len(args)]
            raise EvalError(f"invalid input: missing argument '{missing}'",
                            "anonymous function" if isinstance(fn, ArrowFunction) else "procedure")
        frame: dict = dict(zip(fn.params, args))
        frame["__parent__"] = fn.closure
        if isinstance(fn, Procedure):
            frame["__proc__"] = True
            frame["__globals__"] = set(fn.globals)
            for name in fn.locals:
                frame[name] = _UNSET
            frame["args"] = ExprSeq(args)
            frame["nargs"] = sp.Integer(len(args))
        if len(self.frames) > 500:
            raise RecursionError()
        self.frames.append(frame)
        try:
            if isinstance(fn, ArrowFunction):
                return self.eval(fn.body)
            try:
                return self.exec_block(fn.body, display=False)
            except _Return as r:
                return r.value
        finally:
            self.frames.pop()

    @contextmanager
    def bind(self, name):
        """Temporarily bind a loop variable (for seq, add, mul)."""
        frame = {"__parent__": self.frames[-1] if self.frames else None}
        self.frames.append(frame)
        try:
            yield lambda v: frame.__setitem__(name, v)
        finally:
            self.frames.pop()

    # ----------------------------------------------------------------- index

    def eval_Index(self, node: A.Index):
        idx = self.flatten(self.eval(i) for i in node.indices)
        if isinstance(node.base, A.Name):
            name = node.base.id
            value = self.lookup(name)
            if value is None or value is _UNSET:
                key = self._indexed_key(name, idx)
                if key in self.session.env:
                    return self.session.env[key]
                if name in BUILTINS or name in CONSTANTS:
                    raise EvalError(f"'{name}' cannot be indexed")
                return sp.Symbol(key.replace("[", "_").replace("]", "").replace(",", ""))
            base = self._full_eval(value, {name})
        else:
            base = self.eval(node.base)
        return self._select(base, idx)

    @staticmethod
    def _indexed_key(name, idx) -> str:
        from .printing import to_text
        return f"{name}[{','.join(to_text(i) for i in idx)}]"

    def _py_index(self, i, what, length=None) -> int:
        if not (isinstance(i, sp.Basic) and i.is_Integer):
            raise EvalError(f"{what} index must be an integer, got {i}")
        k = int(i)
        if k > 0:
            return k - 1
        if k < 0 and length is not None:
            return length + k
        raise EvalError(f"invalid subscript selector {k}")

    def _select(self, base, idx):
        if isinstance(base, (MList, ExprSeq, MSet)):
            if len(idx) != 1:
                raise EvalError("lists take a single index")
            i = idx[0]
            if isinstance(i, MRange):
                lo = self._py_index(i.lo, "list", len(base))
                hi = self._py_index(i.hi, "list", len(base))
                return type(base)(list(base)[lo:hi + 1])
            k = self._py_index(i, "list", len(base))
            if not 0 <= k < len(base):
                raise EvalError(f"index out of range: {i}")
            return list(base)[k]
        if isinstance(base, sp.MatrixBase):
            if len(idx) == 1:
                k = self._py_index(idx[0], "matrix", len(base))
                if 1 in base.shape:
                    return base[k]
                return base.row(k)
            if len(idx) == 2:
                r = self._py_index(idx[0], "matrix", base.rows)
                c = self._py_index(idx[1], "matrix", base.cols)
                if not (0 <= r < base.rows and 0 <= c < base.cols):
                    raise EvalError("matrix index out of range")
                return base[r, c]
        if isinstance(base, MString) and len(idx) == 1:
            k = self._py_index(idx[0], "string", len(base))
            return MString(base[k])
        raise EvalError(f"cannot index into {base}")

    # ----------------------------------------------------------------- truth

    def try_truth(self, v):
        try:
            return self.truth(v)
        except EvalError:
            return None

    def truth(self, v) -> bool:
        if isinstance(v, bool):
            return v
        if v is sp.true or v is sp.false:
            return bool(v)
        if isinstance(v, Equation):
            return v.lhs == v.rhs
        if isinstance(v, (sp.Equality, sp.Unequality)):
            l, r = v.lhs, v.rhs
            equal = l == r
            if not equal:
                try:
                    equal = sp.simplify(l - r) == 0
                except Exception:
                    equal = False
            return equal if isinstance(v, sp.Equality) else not equal
        if isinstance(v, sp.core.relational.Relational):
            evaluated = type(v)(v.lhs, v.rhs)
            if evaluated is sp.true or evaluated is sp.false:
                return bool(evaluated)
            diff = (v.lhs - v.rhs)
            if diff.is_number:
                d = sp.N(diff)
                if d.is_real:
                    return bool(type(v)(d, 0))
            raise EvalError(f"cannot determine if {v} is true or false")
        raise EvalError(f"expected a boolean value but received {v}")

    # ------------------------------------------------------------- display

    def _display_form(self, fn: ArrowFunction):
        """Convert an arrow function's body to an unevaluated SymPy expression for typesetting."""
        try:
            params = tuple(sp.Symbol(p) for p in fn.params)
            return ExprFunction(params, _inert(fn.body))
        except Exception:
            return None


def _inert(node):
    if isinstance(node, A.Num):
        return sp.Float(node.text) if any(c in node.text for c in ".eE") else sp.Integer(node.text)
    if isinstance(node, A.Name):
        return CONSTANTS.get(node.id, sp.Symbol(node.id))
    if isinstance(node, A.BinOp):
        l, r = _inert(node.left), _inert(node.right)
        if node.op == "+":
            return sp.Add(l, r, evaluate=False)
        if node.op == "-":
            return sp.Add(l, sp.Mul(-1, r, evaluate=False), evaluate=False)
        if node.op in ("*", "."):
            return sp.Mul(l, r, evaluate=False)
        if node.op == "/":
            return sp.Mul(l, sp.Pow(r, -1, evaluate=False), evaluate=False)
        if node.op == "^":
            return sp.Pow(l, r, evaluate=False)
        if node.op in _RELATIONS:
            return _RELATIONS[node.op](l, r, evaluate=False)
        raise ValueError(node.op)
    if isinstance(node, A.UnOp):
        v = _inert(node.operand)
        if node.op == "-":
            return sp.Mul(-1, v, evaluate=False)
        if node.op == "!":
            return sp.factorial(v, evaluate=False)
        return v
    if isinstance(node, A.Call) and isinstance(node.func, A.Name):
        args = [_inert(a) for a in node.args]
        fn = _INERT_FUNCS.get(node.func.id)
        if fn is not None:
            return fn(*args, evaluate=False)
        return sp.Function(node.func.id)(*args)
    raise ValueError(type(node).__name__)
