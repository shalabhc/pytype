# -*- coding:utf-8; python-indent:2; indent-tabs-mode:nil -*-
# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for type_match.py."""

import textwrap
import unittest


from pytype.pyi import parser
from pytype.pytd import booleq
from pytype.pytd import pytd
from pytype.pytd import type_match
from pytype.pytd import utils as pytd_utils
from pytype.pytd.parse import parser_test_base
from pytype.pytd.parse import visitors


_BUILTINS = """
  class object: ...
  class classobj: ...
"""


class TestTypeMatch(parser_test_base.ParserTest):
  """Test algorithms and datastructures of booleq.py."""

  def setUp(self):
    builtins = parser.parse_string(textwrap.dedent(_BUILTINS),
                                   name="__builtin__")
    typing = parser.parse_string("class Generic: ...", name="typing")
    self.mini_builtins = pytd_utils.Concat(builtins, typing)

  def LinkAgainstSimpleBuiltins(self, ast):
    ast = ast.Visit(visitors.NamedTypeToClassType())
    ast = ast.Visit(visitors.AdjustTypeParameters())
    ast.Visit(visitors.FillInModuleClasses({"": ast}))
    ast = ast.Visit(visitors.LookupFullNames([self.mini_builtins]))
    ast.Visit(visitors.VerifyLookup())
    return ast

  def assertMatch(self, m, t1, t2):
    eq = m.match_type_against_type(t1, t2, {})
    self.assertEquals(eq, booleq.TRUE)

  def assertNoMatch(self, m, t1, t2):
    eq = m.match_type_against_type(t1, t2, {})
    self.assertEquals(eq, booleq.FALSE)

  def testAnything(self):
    m = type_match.TypeMatch({})
    self.assertMatch(m, pytd.AnythingType(), pytd.AnythingType())
    self.assertMatch(m, pytd.AnythingType(), pytd.NamedType("x"))
    self.assertMatch(m, pytd.NamedType("x"), pytd.AnythingType())

  def testAnythingAsTop(self):
    m = type_match.TypeMatch({}, any_also_is_bottom=False)
    self.assertMatch(m, pytd.AnythingType(), pytd.AnythingType())
    self.assertNoMatch(m, pytd.AnythingType(), pytd.NamedType("x"))
    self.assertMatch(m, pytd.NamedType("x"), pytd.AnythingType())

  def testNothingLeft(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.NothingType(),
                                   pytd.NamedType("A"), {})
    self.assertEquals(eq, booleq.TRUE)

  def testNothingRight(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.NamedType("A"), pytd.NothingType(), {})
    self.assertEquals(eq, booleq.FALSE)

  def testNothingNothing(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.NothingType(), pytd.NothingType(), {})
    self.assertEquals(eq, booleq.TRUE)

  def testNothingAnything(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.NothingType(), pytd.AnythingType(), {})
    self.assertEquals(eq, booleq.TRUE)

  def testAnythingNothing(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.AnythingType(), pytd.NothingType(), {})
    self.assertEquals(eq, booleq.TRUE)

  def testNamed(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.NamedType("A"), pytd.NamedType("A"), {})
    self.assertEquals(eq, booleq.TRUE)
    eq = m.match_type_against_type(pytd.NamedType("A"), pytd.NamedType("B"), {})
    self.assertNotEquals(eq, booleq.TRUE)

  def testNamedAgainstGeneric(self):
    m = type_match.TypeMatch({})
    eq = m.match_type_against_type(pytd.GenericType(pytd.NamedType("A"), ()),
                                   pytd.NamedType("A"), {})
    self.assertEquals(eq, booleq.TRUE)

  def testFunction(self):
    ast = parser.parse_string(textwrap.dedent("""
      def left(a: int) -> int
      def right(a: int) -> int
    """))
    m = type_match.TypeMatch()
    self.assertEquals(m.match(ast.Lookup("left"), ast.Lookup("right"), {}),
                      booleq.TRUE)

  def testReturn(self):
    ast = parser.parse_string(textwrap.dedent("""
      def left(a: int) -> float
      def right(a: int) -> int
    """))
    m = type_match.TypeMatch()
    self.assertNotEquals(m.match(ast.Lookup("left"), ast.Lookup("right"), {}),
                         booleq.TRUE)

  def testOptional(self):
    ast = parser.parse_string(textwrap.dedent("""
      def left(a: int) -> int
      def right(a: int, ...) -> int
    """))
    m = type_match.TypeMatch()
    self.assertEquals(m.match(ast.Lookup("left"), ast.Lookup("right"), {}),
                      booleq.TRUE)

  def testGeneric(self):
    ast = parser.parse_string(textwrap.dedent("""
      T = TypeVar('T')
      class A(typing.Generic[T], object):
        pass
      left = ...  # type: A[?]
      right = ...  # type: A[?]
    """))
    ast = self.LinkAgainstSimpleBuiltins(ast)
    m = type_match.TypeMatch()
    self.assertEquals(m.match_type_against_type(
        ast.Lookup("left").type,
        ast.Lookup("right").type, {}), booleq.TRUE)

  def testClassMatch(self):
    ast = parser.parse_string(textwrap.dedent("""
      class Left():
        def method(self) -> ?
      class Right():
        def method(self) -> ?
        def method2(self) -> ?
    """))
    ast = visitors.LookupClasses(ast, self.mini_builtins)
    m = type_match.TypeMatch()
    left, right = ast.Lookup("Left"), ast.Lookup("Right")
    self.assertEquals(m.match(left, right, {}), booleq.TRUE)
    self.assertNotEquals(m.match(right, left, {}), booleq.TRUE)

  def testSubclasses(self):
    ast = parser.parse_string(textwrap.dedent("""
      class A():
        pass
      class B(A):
        pass
      a = ...  # type: A
      def left(a: B) -> B
      def right(a: A) -> A
    """))
    ast = visitors.LookupClasses(ast, self.mini_builtins)
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    left, right = ast.Lookup("left"), ast.Lookup("right")
    self.assertEquals(m.match(left, right, {}), booleq.TRUE)
    self.assertNotEquals(m.match(right, left, {}), booleq.TRUE)

  def _TestTypeParameters(self, reverse=False):
    ast = parser.parse_string(textwrap.dedent("""
      import typing
      class `~unknown0`():
        def next(self) -> ?
      T = TypeVar('T')
      class A(typing.Generic[T], object):
        def next(self) -> ?
      class B():
        pass
      def left(x: `~unknown0`) -> ?
      def right(x: A[B]) -> ?
    """))
    ast = self.LinkAgainstSimpleBuiltins(ast)
    m = type_match.TypeMatch()
    left, right = ast.Lookup("left"), ast.Lookup("right")
    match = m.match(right, left, {}) if reverse else m.match(left, right, {})
    self.assertEquals(match, booleq.And((booleq.Eq("~unknown0", "A"),
                                         booleq.Eq("~unknown0.A.T", "B"))))
    self.assertIn("~unknown0.A.T", m.solver.variables)

  def testUnknownAgainstGeneric(self):
    self._TestTypeParameters()

  def testGenericAgainstUnknown(self):
    self._TestTypeParameters(reverse=True)

  def testStrict(self):
    ast = parser.parse_string(textwrap.dedent("""
      import typing

      T = TypeVar('T')
      class list(typing.Generic[T], object):
        pass
      class A():
        pass
      class B(A):
        pass
      class `~unknown0`():
        pass
      a = ...  # type: A
      def left() -> `~unknown0`
      def right() -> list[A]
    """))
    ast = self.LinkAgainstSimpleBuiltins(ast)
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    left, right = ast.Lookup("left"), ast.Lookup("right")
    self.assertEquals(m.match(left, right, {}),
                      booleq.And((booleq.Eq("~unknown0", "list"),
                                  booleq.Eq("~unknown0.list.T", "A"))))

  def testBaseClass(self):
    ast = parser.parse_string(textwrap.dedent("""
      class Base():
        def f(self, x:Base) -> Base
      class Foo(Base):
        pass

      class Match():
        def f(self, x:Base) -> Base
    """))
    ast = self.LinkAgainstSimpleBuiltins(ast)
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    eq = m.match_Class_against_Class(ast.Lookup("Match"), ast.Lookup("Foo"), {})
    self.assertEquals(eq, booleq.TRUE)

  def testHomogeneousTuple(self):
    ast = self.ParseWithBuiltins("""
      from typing import Tuple
      x1 = ...  # type: Tuple[bool, ...]
      x2 = ...  # type: Tuple[int, ...]
    """)
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    x1 = ast.Lookup("x1").type
    x2 = ast.Lookup("x2").type
    self.assertEquals(m.match_Generic_against_Generic(x1, x1, {}), booleq.TRUE)
    self.assertEquals(m.match_Generic_against_Generic(x1, x2, {}), booleq.TRUE)
    self.assertEquals(m.match_Generic_against_Generic(x2, x1, {}), booleq.FALSE)
    self.assertEquals(m.match_Generic_against_Generic(x2, x2, {}), booleq.TRUE)

  def testHeterogeneousTuple(self):
    ast = self.ParseWithBuiltins("""
      from typing import Tuple
      x1 = ...  # type: Tuple[int]
      x2 = ...  # type: Tuple[bool, str]
      x3 = ...  # type: Tuple[int, str]
    """)
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    x1 = ast.Lookup("x1").type
    x2 = ast.Lookup("x2").type
    x3 = ast.Lookup("x3").type
    self.assertEquals(m.match_Generic_against_Generic(x1, x1, {}), booleq.TRUE)
    self.assertEquals(m.match_Generic_against_Generic(x1, x2, {}), booleq.FALSE)
    self.assertEquals(m.match_Generic_against_Generic(x1, x3, {}), booleq.FALSE)
    self.assertEquals(m.match_Generic_against_Generic(x2, x1, {}), booleq.FALSE)
    self.assertEquals(m.match_Generic_against_Generic(x2, x2, {}), booleq.TRUE)
    self.assertEquals(m.match_Generic_against_Generic(x2, x3, {}), booleq.TRUE)
    self.assertEquals(m.match_Generic_against_Generic(x3, x1, {}), booleq.FALSE)
    self.assertEquals(m.match_Generic_against_Generic(x3, x2, {}), booleq.FALSE)
    self.assertEquals(m.match_Generic_against_Generic(x3, x3, {}), booleq.TRUE)

  def testTuple(self):
    ast = self.ParseWithBuiltins("""
      from typing import Tuple
      x1 = ...  # type: Tuple[bool, ...]
      x2 = ...  # type: Tuple[int, ...]
      y1 = ...  # type: Tuple[bool, int]
    """)
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    x1 = ast.Lookup("x1").type
    x2 = ast.Lookup("x2").type
    y1 = ast.Lookup("y1").type
    # Tuple[T, ...] matches Tuple[U, V] when T matches both U and V.
    self.assertEquals(m.match_Generic_against_Generic(x1, y1, {}), booleq.TRUE)
    self.assertEquals(m.match_Generic_against_Generic(x2, y1, {}), booleq.FALSE)
    # Tuple[U, V] matches Tuple[T, ...] when Union[U, V] matches T.
    self.assertEquals(m.match_Generic_against_Generic(y1, x1, {}), booleq.FALSE)
    self.assertEquals(m.match_Generic_against_Generic(y1, x2, {}), booleq.TRUE)

  def testUnknownAgainstTuple(self):
    ast = self.ParseWithBuiltins("""
      from typing import Tuple
      class `~unknown0`():
        pass
      x = ...  # type: Tuple[int, str]
    """)
    unk = ast.Lookup("~unknown0")
    tup = ast.Lookup("x").type
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    match = m.match_Unknown_against_Generic(unk, tup, {})
    self.assertListEqual(sorted(match.extract_equalities()),
                         [("~unknown0", "__builtin__.tuple"),
                          ("~unknown0.__builtin__.tuple.T", "int"),
                          ("~unknown0.__builtin__.tuple.T", "str")])

  def testFunctionAgainstTupleSubclass(self):
    ast = self.ParseWithBuiltins("""
      from typing import Tuple
      class A(Tuple[int, str]): ...
      def f(x): ...
    """)
    a = ast.Lookup("A")
    f = ast.Lookup("f")
    m = type_match.TypeMatch(type_match.get_all_subclasses([ast]))
    # Smoke test for the TupleType logic in match_Function_against_Class
    self.assertEquals(m.match_Function_against_Class(f, a, {}, {}),
                      booleq.FALSE)


if __name__ == "__main__":
  unittest.main()
