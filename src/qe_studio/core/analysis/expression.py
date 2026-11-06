"""A calculator's expression, evaluated over a whitelist of the AST (spec 78 R1).

Numbers, ``+ - * /``, unary ``+ -``, parentheses, the given names, one-argument calls of the given
functions and, when asked, ``**``. Anything else (attributes, indexing, comparisons, strings…) is an
``ExpressionError`` whose text the user reads. A decimal comma is read as a point. Nothing is ever
passed to ``eval``; numbers are floats, so a huge power overflows instead of hanging.
"""

from __future__ import annotations

import ast
import math
import operator
from collections.abc import Callable, Mapping

from ...i18n import _

__all__ = ["ExpressionError", "evaluate"]

_BINARY: dict[type[ast.operator], Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}
_UNARY: dict[type[ast.unaryop], Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class ExpressionError(ValueError):
    """Why an expression cannot be evaluated, in a sentence for the user."""


def incomplete() -> ExpressionError:
    return ExpressionError(_("Expressão incompleta"))


def _too_long() -> ExpressionError:
    return ExpressionError(_("Expressão longa demais"))


def evaluate(
    text: str,
    names: Mapping[str, float] | None = None,
    *,
    functions: Mapping[str, Callable[[float], float]] | None = None,
    power: bool = False,
) -> float:
    """The value of ``text``; ``ExpressionError`` when it is not a finite number."""
    source = text.replace(",", ".").strip()
    if not source:
        raise incomplete()
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, ValueError):  # a null byte is a ValueError before Python 3.12
        raise incomplete() from None
    except (RecursionError, MemoryError):  # too deep for the parser, or for its tree
        raise _too_long() from None
    walker = _Walker(names or {}, functions or {}, power)
    try:
        value = walker.visit(tree.body)
    except ExpressionError:
        raise
    except ZeroDivisionError:
        raise ExpressionError(_("Divisão por zero")) from None
    except RecursionError:
        raise _too_long() from None
    except (OverflowError, ValueError):  # a huge power, or a math domain error of a function
        value = math.inf
    if not math.isfinite(value):
        raise ExpressionError(_("Resultado não é um número finito"))
    return value


class _Walker:
    def __init__(
        self,
        names: Mapping[str, float],
        functions: Mapping[str, Callable[[float], float]],
        power: bool,
    ):
        self.names, self.functions, self.power = names, functions, power

    def visit(self, node: ast.expr) -> float:
        if isinstance(node, ast.Constant):
            value = node.value
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise self.refused(node)
            return float(value)
        if isinstance(node, ast.BinOp):
            op = type(node.op)
            if op is ast.Pow and self.power:
                return math.pow(self.visit(node.left), self.visit(node.right))
            if op not in _BINARY:
                raise self.refused(node.op)
            return _BINARY[op](self.visit(node.left), self.visit(node.right))
        if isinstance(node, ast.UnaryOp):
            if type(node.op) not in _UNARY:
                raise self.refused(node.op)
            return _UNARY[type(node.op)](self.visit(node.operand))
        if isinstance(node, ast.Name):
            if node.id not in self.names:
                raise ExpressionError(_("Nome desconhecido: {name}").format(name=node.id))
            return float(self.names[node.id])
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = self.functions.get(node.func.id)
            if function is None:
                raise ExpressionError(_("Nome desconhecido: {name}").format(name=node.func.id))
            if len(node.args) != 1 or node.keywords or isinstance(node.args[0], ast.Starred):
                raise ExpressionError(_("{name} recebe um argumento").format(name=node.func.id))
            return float(function(self.visit(node.args[0])))
        raise self.refused(node)

    @staticmethod
    def refused(node: ast.AST) -> ExpressionError:
        symbol = SYMBOLS.get(type(node))
        if symbol is None:
            symbol = ast.unparse(node) if isinstance(node, ast.expr) else type(node).__name__
        return ExpressionError(_("Operador não permitido: {op}").format(op=symbol))


SYMBOLS: dict[type[ast.AST], str] = {
    ast.Pow: "**",
    ast.FloorDiv: "//",
    ast.Mod: "%",
    ast.MatMult: "@",
    ast.BitAnd: "&",
    ast.BitOr: "|",
    ast.BitXor: "^",
    ast.LShift: "<<",
    ast.RShift: ">>",
    ast.Invert: "~",
    ast.Not: "not",
    ast.Attribute: ".",
    ast.Subscript: "[]",
    ast.Compare: _("comparação"),
    ast.Lambda: "lambda",
    ast.Call: _("chamada"),
}
