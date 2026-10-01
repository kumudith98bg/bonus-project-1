"""Run from python_version with: python3 -m unittest discover -s tests -v."""

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from source.language import tokenize, parse_query, parse_definitions, format_tree
from source.engine import evaluate, create_relation, display_name, tuple_equal, TupleSet
from source.errors import RAError, format_error
from source.generate import generate_text


EMPLOYEES = """Employees (EID, Name, Age, DID) = {
E1, John, 32, D1
E2, Alice, 28, D2
E3, Bob, 29, D1
}"""


def database(*relations):
    return {relation.name: relation for relation in relations}


def run(query, relations):
    return evaluate(parse_query(query), relations)


def unary(columns, rows):
    return database(create_relation("R", columns, rows))


def employees():
    return parse_definitions(EMPLOYEES)


def example_sets():
    return database(
        create_relation("A", ["x"], [(1,)]),
        create_relation("B", ["x"], [(2,)]),
        create_relation("C", ["x"], [(1,)]),
        create_relation("D", ["x"], [(1,), (4,)]),
    )


class AlgebraTests(unittest.TestCase):
    def assert_rows(self, actual, expected):
        self.assertCountEqual([tuple(row) for row in actual], [tuple(row) for row in expected])

    def fails(self, action, category, message=""):
        with self.assertRaises(RAError) as caught:
            action()
        error = caught.exception
        self.assertEqual(error.category, category)
        self.assertIn(message.lower(), str(error).lower())
        if category in ("Lexical", "Syntax"):
            self.assertIsInstance(error.position["offset"], int)
            self.assertGreaterEqual(error.position["line"], 1)
            self.assertGreaterEqual(error.position["column"], 1)
        return error

    def test_01_no_whitespace(self):
        self.assert_rows(run("select[x1=3](R)", unary(["x1"], [(3,), (4,)]))["relation"].rows, [(3,)])

    def test_02_whitespace_does_not_change_tree(self):
        self.assertEqual(format_tree(parse_query("select[x1=3](R)")), format_tree(parse_query("select[ x1 = 3 ](R)")))

    def test_03_maximal_munch_greater_equal(self):
        operators = [token["value"] for token in tokenize("select[Age>=30](R)") if token["type"] == "COMPARE"]
        self.assertEqual(operators, [">="])
        self.assert_rows(run("select[Age>=30](R)", unary(["Age"], [(29,), (30,), (31,)]))["relation"].rows, [(30,), (31,)])

    def test_04_negative_number_after_comparison(self):
        tokens = tokenize("select[Age>-30](R)")
        self.assertEqual([token["value"] for token in tokens if token["type"] in ("COMPARE", "NUMBER")], [">", -30])
        self.assert_rows(run("select[Age>-30](R)", unary(["Age"], [(-31,), (-30,), (-29,)]))["relation"].rows, [(-29,)])

    def test_05_parenthesis_inside_string(self):
        self.assert_rows(run("select[Name='Bob)'](R)", unary(["Name"], [("Bob)",), ("Bob",)]))["relation"].rows, [("Bob)",)])

    def test_06_comma_inside_string(self):
        self.assert_rows(run("select[Name='a,b'](R)", unary(["Name"], [("a,b",), ("a",)]))["relation"].rows, [("a,b",)])

    def test_07_doubled_quote(self):
        self.assert_rows(run("select[Name='O''Brien'](R)", unary(["Name"], [("O'Brien",), ("Brien",)]))["relation"].rows, [("O'Brien",)])

    def test_08_keyword_attribute(self):
        self.assert_rows(run("select[union=3](R)", unary(["union"], [(3,), (4,)]))["relation"].rows, [(3,)])

    def test_09_unterminated_string_has_position(self):
        self.fails(lambda: parse_query("select[Name='Bob](R)"), "Lexical", "unterminated")

    def test_10_union_minus_left_grouping(self):
        query = "A union B minus C"
        self.assertEqual(format_tree(parse_query(query)), format_tree(parse_query("(A union B) minus C")))
        self.assertNotEqual(format_tree(parse_query(query)), format_tree(parse_query("A union (B minus C)")))
        self.assert_rows(run(query, example_sets())["relation"].rows, [(2,)])
        self.assert_rows(run("A union (B minus C)", example_sets())["relation"].rows, [(1,), (2,)])

    def test_11_minus_associativity_counterexample(self):
        relations = database(*(create_relation(name, ["x"], [(1,)]) for name in ("A", "B", "C")))
        self.assertEqual(format_tree(parse_query("A minus B minus C")), format_tree(parse_query("(A minus B) minus C")))
        self.assert_rows(run("A minus B minus C", relations)["relation"].rows, [])
        self.assert_rows(run("A minus (B minus C)", relations)["relation"].rows, [(1,)])

    def test_12_not_and_or_precedence(self):
        relations = unary(["a", "b", "c"], [(1, 2, 0), (0, 2, 0), (1, 2, 4)])
        self.assert_rows(run("select[not (a=1 and b=2) or c>3](R)", relations)["relation"].rows, [(0, 2, 0), (1, 2, 4)])

    def test_13_and_before_or(self):
        relations = unary(["a", "b", "c"], [(0, 0, 3), (1, 2, 0), (1, 0, 0)])
        self.assert_rows(run("select[a=1 and b=2 or c=3](R)", relations)["relation"].rows, [(0, 0, 3), (1, 2, 0)])

    def test_14_three_levels_of_nesting_corrected_ascii(self):
        query = "project[Name](select[Age>30](select[DID='D1'](Employees)))"
        self.assert_rows(run(query, employees())["relation"].rows, [("John",)])

    def test_15_parentheses_override_precedence(self):
        self.assert_rows(run("(A union B) minus (C intersect D)", example_sets())["relation"].rows, [(2,)])
        self.assertEqual(format_tree(parse_query("A union B intersect C")), format_tree(parse_query("A union (B intersect C)")))

    def test_16_missing_parenthesis_has_position(self):
        self.fails(lambda: parse_query("select[Age>30](R"), "Syntax", ")")

    def test_17_empty_projection_is_syntax_error(self):
        self.fails(lambda: parse_query("project[](R)"), "Syntax")

    def test_18_attribute_to_attribute_comparison(self):
        self.assert_rows(run("select[A=B](R)", unary(["A", "B"], [(1, 1), (1, 2), (2, 2)]))["relation"].rows, [(1, 1), (2, 2)])

    def test_19_qualified_theta_join_preserves_both_columns(self):
        relations = database(create_relation("Emp", ["EID", "DID"], [("E1", "D1"), ("E2", "D2")]), create_relation("Dept", ["DID", "Name"], [("D1", "Sales")]))
        result = run("Emp join[Emp.DID=Dept.DID] Dept", relations)["relation"]
        self.assertEqual([display_name(attr) for attr in result.attributes], ["Emp.EID", "Emp.DID", "Dept.DID", "Dept.Name"])
        self.assert_rows(result.rows, [("E1", "D1", "D1", "Sales")])

    def test_20_rename_permits_self_join(self):
        relations = database(create_relation("Emp", ["EID", "MgrID"], [("E1", "E1"), ("E2", "E1"), ("E3", "E2")]))
        result = run("rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp", relations)["relation"]
        self.assert_rows(result.rows, [("E1", "E1", "E1", "E1"), ("E1", "E1", "E2", "E1"), ("E2", "E1", "E3", "E2")])
        self.fails(lambda: run("Emp join[Emp.MgrID=Emp.EID] Emp", relations), "Schema")

    def test_21_incompatible_union(self):
        relations = database(create_relation("R", ["x"], [(1,)]), create_relation("S", ["y"], [(1,)]))
        self.fails(lambda: run("R union S", relations), "Schema")

    def test_22_number_versus_string_is_type_error(self):
        self.fails(lambda: run("select[Age>'30'](R)", unary(["Age"], [(31,)])), "Type")

    def test_23_projection_deduplicates(self):
        self.assert_rows(run("project[DID](Employees)", employees())["relation"].rows, [("D1",), ("D2",)])

    def test_24_duplicate_projection_attribute_rejected(self):
        relations = unary(["Name"], [("John",)])
        self.fails(lambda: run("project[Name,Name](R)", relations), "Schema")
        self.fails(lambda: run("project[Name,R.Name](R)", relations), "Schema")

    def test_25_empty_result_preserves_schema(self):
        result = run("select[Age>100](Employees)", employees())["relation"]
        self.assertEqual(result.rows, [])
        self.assertEqual([display_name(attr) for attr in result.attributes], ["EID", "Name", "Age", "DID"])
        self.assertEqual([attr.type for attr in result.attributes], ["string", "string", "number", "string"])

    def test_projection_column_order(self):
        result = run("project[Age,Name](Employees)", employees())["relation"]
        self.assertEqual([display_name(attr) for attr in result.attributes], ["Age", "Name"])
        self.assert_rows(result.rows, [(32, "John"), (28, "Alice"), (29, "Bob")])

    def test_set_operators_compare_complete_tuples(self):
        relations = database(create_relation("R", ["x", "y"], [(1, "a"), (2, "b")]), create_relation("S", ["x", "y"], [(1, "a"), (1, "b")]))
        self.assert_rows(run("R union S", relations)["relation"].rows, [(1, "a"), (2, "b"), (1, "b")])
        self.assert_rows(run("R intersect S", relations)["relation"].rows, [(1, "a")])
        self.assert_rows(run("R minus S", relations)["relation"].rows, [(2, "b")])
        self.assert_rows(run("S minus R", relations)["relation"].rows, [(1, "b")])

    def test_union_compatibility_arity_order_types(self):
        base = create_relation("R", ["x", "y"], [(1, "a")])
        others = [create_relation("S", ["x"], [(1,)]), create_relation("S", ["y", "x"], [(1, "a")]), create_relation("S", ["x", "y"], [("1", "a")])]
        for other in others:
            for operator in ("union", "intersect", "minus"):
                with self.subTest(other=other, operator=operator):
                    self.fails(lambda: run(f"R {operator} S", database(base, other)), "Schema")

    def test_every_comparison_and_repeated_not(self):
        relations = unary(["x"], [(1,), (2,), (3,)])
        for operator, expected in [("=", [2]), ("!=", [1, 3]), ("<", [1]), ("<=", [1, 2]), (">", [3]), (">=", [2, 3])]:
            self.assert_rows(run(f"select[x{operator}2](R)", relations)["relation"].rows, [(value,) for value in expected])
        self.assert_rows(run("select[not not x=2](R)", relations)["relation"].rows, [(2,)])

    def test_keyword_names_in_other_positions(self):
        relations = unary(["not", "and", "or"], [(1, 2, 3), (0, 2, 3)])
        self.assert_rows(run("select[not=1 and and=2 and or=3](R)", relations)["relation"].rows, [(1, 2, 3)])
        self.assert_rows(run("select[not not=1](R)", relations)["relation"].rows, [(0, 2, 3)])
        named = database(create_relation("select", ["x"], [(1,)]), create_relation("union", ["x"], [(2,)]), create_relation("not", ["value"], [(1,)]))
        self.assert_rows(run("select union union", named)["relation"].rows, [(1,), (2,)])
        self.assert_rows(run("select[not.value=1](not)", named)["relation"].rows, [(1,)])

    def test_unknown_ambiguous_and_removed_attributes(self):
        self.fails(lambda: run("Missing", employees()), "Name")
        self.fails(lambda: run("select[Missing=1](Employees)", employees()), "Name")
        self.fails(lambda: run("project[Missing](Employees)", employees()), "Name")
        relations = database(create_relation("R", ["x"], [(1,)]), create_relation("S", ["x"], [(1,)]))
        self.fails(lambda: run("select[x=1](R times S)", relations), "Name", "ambiguous")
        self.fails(lambda: run("select[Age>30](project[Name](Employees))", employees()), "Name")

    def test_empty_and_short_circuit_inputs_do_not_hide_errors(self):
        queries = [("select[Age='x'](select[Age>100](Employees))", "Type"), ("select[Missing=1](select[Age>100](Employees))", "Name"), ("select[Age>0 or Age='x'](Employees)", "Type"), ("select[Age<0 and Missing=1](Employees)", "Name")]
        for query, category in queries:
            self.fails(lambda: run(query, employees()), category)

    def test_empty_input_schema_can_gain_known_types(self):
        relations = database(create_relation("R", ["x"], []), create_relation("S", ["x"], [(1,)]))
        result = run("R union S", relations)["relation"]
        self.assert_rows(result.rows, [(1,)])
        self.assertEqual(result.attributes[0].type, "number")
        self.assertEqual(result.name, "R")

    def test_nested_product_qualifiers_and_rename_collision(self):
        relations = database(create_relation("R", ["x"], [(1,)]), create_relation("S", ["y"], [(2,)]), create_relation("T", ["z"], [(3,)]))
        result = run("R times S times T", relations)["relation"]
        self.assertEqual([display_name(attr) for attr in result.attributes], ["R.x", "S.y", "T.z"])
        colliding = database(create_relation("R", ["x"], [(1,)]), create_relation("S", ["x"], [(2,)]))
        self.fails(lambda: run("rename[X](R times S)", colliding), "Schema")

    def test_theta_join_inequality(self):
        relations = database(create_relation("R", ["x"], [(1,), (3,)]), create_relation("S", ["x"], [(2,), (4,)]))
        self.assert_rows(run("R join[R.x<S.x] S", relations)["relation"].rows, [(1, 2), (1, 4), (3, 4)])

    def test_counters_are_per_operator_and_actual(self):
        relations = parse_definitions(generate_text(5, 3, 1))
        result = run("select[R.a<2](R join[R.b=S.b] S)", relations)
        self.assertEqual([stat["examined"] for stat in result["stats"] if stat["operator"] == "join"], [15])
        self.assertEqual([stat["examined"] for stat in result["stats"] if stat["operator"] == "select"], [5])
        nested = run("select[a<2](select[a<4](R))", relations)
        self.assertEqual([stat["examined"] for stat in nested["stats"] if stat["operator"] == "select"], [5, 4])

    def test_empty_and_zero_match_join_counters(self):
        unmatched = run("R join[R.b=S.b] S", parse_definitions(generate_text(7, 4, 0)))
        self.assertEqual(next(stat["examined"] for stat in unmatched["stats"] if stat["operator"] == "join"), 28)
        self.assertEqual(unmatched["relation"].rows, [])
        empty = run("R join[R.b=S.b] S", parse_definitions(generate_text(0, 4)))
        self.assertEqual(next(stat["examined"] for stat in empty["stats"] if stat["operator"] == "join"), 0)
        self.assertEqual(len(empty["relation"].attributes), 4)

    def test_data_crlf_comments_quotes_and_bare_email(self):
        text = "  // comment\r\n\r\nR (id, value) = {\r\n1, 'a,b'\r\n2, 'Bob)'\r\n// between rows\r\n3, 'O''Brien'\r\n4, al@c.ca\r\n5, ''\r\n6, 'a b'\r\n}\r\n"
        self.assert_rows(parse_definitions(text)["R"].rows, [(1, "a,b"), (2, "Bob)"), (3, "O'Brien"), (4, "al@c.ca"), (5, ""), (6, "a b")])

    def test_input_deduplication_and_tuple_equality(self):
        self.assert_rows(parse_definitions("R(x,y)={\n1,a\n1,a\n1,b\n}")["R"].rows, [(1, "a"), (1, "b")])
        self.assertTrue(tuple_equal((0,), (-0.0,)))
        self.assertTrue(tuple_equal((1,), (1.0,)))
        self.assertFalse(tuple_equal((1,), ("1",)))
        self.assertFalse(tuple_equal(("a,b", "c"), ("a", "b,c")))
        self.assertFalse(tuple_equal((1,), (1, 2)))
        tuples = TupleSet([(1, "a"), (1.0, "a"), ("1", "a"), (1, "b")])
        self.assertEqual(len(tuples.rows), 3)

    def test_hash_collision_still_checks_tuple_equality(self):
        first, second = 0, sys.hash_info.modulus
        self.assertEqual(hash(first), hash(second))
        tuples = TupleSet([(first,), (second,), (first,)])
        self.assert_rows(tuples.rows, [(first,), (second,)])

    def test_invalid_definitions(self):
        self.fails(lambda: parse_definitions("R(x,y)={\n1\n}"), "Schema")
        self.fails(lambda: parse_definitions("R(x,x)={\n1,2\n}"), "Schema")
        self.fails(lambda: parse_definitions("R(x)={\n1\n'1'\n}"), "Type")
        self.fails(lambda: parse_definitions("R(x)={1}\nR(x)={2}"), "Name")

    def test_numeric_literals_decimal_exponent_big_integer(self):
        big = 10 ** 60 + 1
        relations = unary(["x"], [(0.5,), (-0.03,), (100,), (big,)])
        self.assert_rows(run("select[x=.5 or x=-3e-2 or x=+1e2](R)", relations)["relation"].rows, [(0.5,), (-0.03,), (100,)])
        self.assert_rows(run(f"select[x={big}](R)", relations)["relation"].rows, [(big,)])
        self.assertEqual(parse_definitions(f"R(x)={{{big}}}")["R"].rows[0][0], big)
        self.fails(lambda: parse_query("select[x=1e](R)"), "Lexical")
        self.fails(lambda: parse_query("select[x=1e999](R)"), "Type")

    def test_python_numeric_contract(self):
        big = 2 ** 60 + 1
        relation = create_relation("R", ["x"], [(1,), (1.0,), (0,), (-0.0,), (big,), (float(big),)])
        self.assertEqual(len(relation.rows), 4)
        self.assertFalse(tuple_equal((big,), (float(big),)))
        self.assertEqual(relation.attributes[0].type, "number")
        for invalid in (True, False, float("nan"), float("inf"), float("-inf"), None):
            with self.subTest(value=invalid):
                self.fails(lambda: create_relation("R", ["x"], [(invalid,)]), "Type")
        relations = database(create_relation("R", ["x"], [(1,)]), create_relation("S", ["x"], [(1.0,), (2.5,)]))
        self.assert_rows(run("R union S", relations)["relation"].rows, [(1,), (2.5,)])

    def test_missing_operands_trailing_tokens_and_comparison_chains(self):
        for query in ("R union", "select[x=](R)", "R extra", "select[x<2<3](R)", "select[x=1](R))"):
            with self.subTest(query=query):
                self.fails(lambda: parse_query(query), "Syntax")

    def test_positions_and_friendly_error_format(self):
        error = self.fails(lambda: parse_query("select[\n Name='never closes](R)"), "Lexical")
        self.assertEqual(error.position["line"], 2)
        self.assertEqual(error.position["column"], 7)
        self.assertIn("line 2, column 7", format_error(error))
        self.assertNotIn("Traceback", format_error(error))

    def test_generator_sizes_and_match_rates(self):
        for match_rate in (0, 0.5, 1, 2, 4):
            relations = parse_definitions(generate_text(8, 8, match_rate))
            self.assertEqual(len(relations["R"].rows), 8)
            self.assertEqual(len(relations["S"].rows), 8)
            joined = run("R join[R.b=S.b] S", relations)
            self.assertEqual(len(joined["relation"].rows), 8 * match_rate)
            self.assertEqual(next(stat["examined"] for stat in joined["stats"] if stat["operator"] == "join"), 64)
        unequal = parse_definitions(generate_text(3, 7, 1))
        self.assertEqual(len(unequal["R"].rows), 3)
        self.assertEqual(len(unequal["S"].rows), 7)
        for arguments in ((-1,), (1.5,), (True,), (2, 2, -1), (2, 2, 3), (2, 2, float("nan"))):
            with self.assertRaises(ValueError):
                generate_text(*arguments)


if __name__ == "__main__":
    unittest.main()
