"""
title: Deterministic lexer and parser fuzz regressions.
summary: >-
  Exercise a fixed mutation budget in the normal unit-test matrix so malformed
  source can only succeed or fail through a structured frontend exception.
"""

from __future__ import annotations

import random

from collections.abc import Iterator

import pytest

from arx.exceptions import ParserException
from arx.io import ArxIO
from arx.lexer import Lexer, LexerError
from arx.parser import Parser

FUZZ_SEED = 20260901
FUZZ_CASE_COUNT = 384
FUZZ_MAX_RANDOM_LENGTH = 96
FUZZ_ALPHABET = (
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "_+-*/%=!<>()[]{}:,.@;#'\"` \n\t"
    "λé🙂"
)
FUZZ_SEEDS = (
    "",
    "fn main() -> i32:\n  return 0\n",
    "fn add(a: i32, b: i32) -> i32:\n  return a + b\n",
    "if true:\n  var x: i32 = 1\nelse:\n  var x: i32 = 2\n",
    "class Point:\n  x: i32\n  y: i32\n",
    "import std.math\n",
    "var values: list[i32] = [1, 2, 3]\n",
    "@[T: i32]\nfn identity(value: T) -> T:\n  return value\n",
)


def generate_fuzz_cases() -> Iterator[str]:
    """
    title: Yield a deterministic mixture of random and mutated source text.
    returns:
      type: Iterator[str]
    """
    generator = random.Random(FUZZ_SEED)
    for index in range(FUZZ_CASE_COUNT):
        if index % 3 == 0:
            length = generator.randrange(FUZZ_MAX_RANDOM_LENGTH + 1)
            yield "".join(
                generator.choice(FUZZ_ALPHABET) for _ in range(length)
            )
            continue

        seed = generator.choice(FUZZ_SEEDS)
        if not seed:
            yield generator.choice(FUZZ_ALPHABET)
            continue

        position = generator.randrange(len(seed))
        operation = index % 3
        if operation == 1:
            yield seed[:position] + seed[position + 1 :]
            continue
        yield (
            seed[:position]
            + generator.choice(FUZZ_ALPHABET)
            + seed[position + 1 :]
        )


@pytest.mark.parametrize("source", tuple(generate_fuzz_cases()))
def test_frontend_fuzz_case_fails_closed(source: str) -> None:
    """
    title: Random malformed source never escapes as an internal exception.
    parameters:
      source:
        type: str
    """
    ArxIO.string_to_buffer(source)
    try:
        tokens = Lexer().lex()
        Parser().parse(tokens, "fuzz")
    except (LexerError, ParserException):
        return
