"""Spec 78 R1: the calculator's expression, over a whitelist of the AST."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from qe_studio.core.analysis.expression import ExpressionError, evaluate


def test_arithmetic_and_precedence():
    assert evaluate("2 + 3 * (4 - 1) / 2") == 6.5
    assert evaluate("-(2 - 5) + +1") == 4
    assert evaluate("1e3 / 4") == 250
    assert evaluate("2 * -3") == -6


def test_names_functions_and_the_decimal_comma():
    assert evaluate("a - 2 * b", {"a": 1.5, "b": 0.25}) == 1.0
    assert evaluate("1,5 + 1") == 2.5
    assert evaluate("sqrt(16) + 1", functions={"sqrt": math.sqrt}) == 5


@pytest.mark.parametrize(
    "text",
    ["-" * 3000 + "1", "1" + "+1" * 20000, "(" * 5000 + "1" + ")" * 5000, "a" + "+a" * 20000],
)
def test_too_deep_an_expression_is_an_error_the_user_reads(text):
    with pytest.raises(ExpressionError):
        evaluate(text, {"a": 1.0})


def test_a_null_byte_is_an_error_the_user_reads():
    with pytest.raises(ExpressionError):
        evaluate("1 +\0 1")


def test_power_only_when_asked():
    assert evaluate("2 ** 3", power=True) == 8
    with pytest.raises(ExpressionError, match=r"Operador não permitido: \*\*"):
        evaluate("2 ** 3")


@pytest.mark.parametrize(
    "text",
    ["__import__('os')", "a.b", "a[0]", '"x"', "lambda: 1", "1 < 2", "7 // 2", "7 % 2", "not 1"],
)
def test_everything_outside_the_whitelist_is_refused(text):
    with pytest.raises(ExpressionError) as error:
        evaluate(text, {"a": 1.0})
    assert str(error.value).startswith(("Operador não permitido", "Nome desconhecido"))


def test_unknown_names_and_bad_calls():
    with pytest.raises(ExpressionError, match="Nome desconhecido: x"):
        evaluate("x + 1")
    with pytest.raises(ExpressionError, match="Nome desconhecido: f"):
        evaluate("f(1)")
    with pytest.raises(ExpressionError, match="um argumento"):
        evaluate("f(x=1)", functions={"f": abs})  # a comma is a decimal point: one argument


@pytest.mark.parametrize("text", ["", "   ", "1 -", "(1 + 2", "1 +* 2"])
def test_an_incomplete_expression(text):
    with pytest.raises(ExpressionError, match="Expressão incompleta"):
        evaluate(text)


def test_division_by_zero_and_infinite_results():
    with pytest.raises(ExpressionError, match="Divisão por zero"):
        evaluate("1 / (2 - 2)")
    with pytest.raises(ExpressionError, match="finito"):
        evaluate("1e308 * 10")
    with pytest.raises(ExpressionError, match="finito"):
        evaluate("10 ** 400", power=True)


def _leaf():
    return st.integers(-50, 50).map(lambda n: (f"({n})" if n < 0 else str(n), n))


def _combine(children):
    def build(pair):
        (left, a), op, (right, b) = pair
        value = {"+": a + b, "-": a - b, "*": a * b}[op]
        return f"({left} {op} {right})", value

    return st.tuples(children, st.sampled_from("+-*"), children).map(build)


@given(st.recursive(_leaf(), _combine, max_leaves=12))
def test_it_agrees_with_integer_arithmetic(expression):
    text, value = expression
    assert evaluate(text) == pytest.approx(value)
