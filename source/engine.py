"""Store relations, enforce set semantics, and execute relational operators."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
import operator

from .errors import RAError


# Relations, schemas, and duplicate removal.

@dataclass
class Attribute:
    name: str
    qualifier: str
    qualified: bool = False
    type: str | None = None


@dataclass
class Relation:
    name: str | None
    attributes: list[Attribute]
    rows: list[tuple]


def display_name(attribute: Attribute) -> str:
    """Base tables print 'id'; joined tables print names such as 'Employee.id'."""
    if attribute.qualified:
        return f"{attribute.qualifier}.{attribute.name}"
    return attribute.name


def value_type(value) -> str:
    """Reject bool explicitly: Python otherwise treats True as the integer 1."""
    if type(value) is int:
        return "number"
    if type(value) is float and isfinite(value):
        return "number"
    if type(value) is str:
        return "string"
    raise RAError("Type", "Every value must be a finite number or a string.")


def tuple_equal(left: tuple, right: tuple) -> bool:
    """Compare each value ourselves, including its language-level type."""
    if len(left) != len(right):
        return False
    for left_value, right_value in zip(left, right):
        if value_type(left_value) != value_type(right_value):
            return False
        if left_value != right_value:
            return False
    return True


def _tuple_hash(row: tuple) -> int:
    """Choose candidates to check; tuple_equal still decides every duplicate.

    Hashing does not remove rows. Equal numbers such as 1 and 1.0 hash alike,
    and different rows sharing a hash are kept unless tuple_equal agrees.
    """
    for value in row:
        value_type(value)  # Reject booleans and other unsupported values.
    return hash(row)


class TupleSet:
    """Hash buckets plus our equality rule, retaining first-occurrence order."""

    def __init__(self, rows=()):
        self.buckets: dict[int, list[tuple]] = {}
        self.rows: list[tuple] = []
        for row in rows:
            self.add(row)

    def has(self, row: tuple) -> bool:
        for existing in self.buckets.get(_tuple_hash(row), []):
            if tuple_equal(existing, row):
                return True
        return False

    def add(self, row: tuple) -> bool:
        row = tuple(row)
        key = _tuple_hash(row)
        if key not in self.buckets:
            self.buckets[key] = []
        bucket = self.buckets[key]
        for existing in bucket:
            if tuple_equal(existing, row):
                return False
        bucket.append(row)
        self.rows.append(row)
        return True


def check_unique_attributes(attributes: list[Attribute]) -> None:
    names = {}
    for attribute in attributes:
        name = display_name(attribute)
        if name in names:
            raise RAError(
                "Schema",
                f"Duplicate attribute name '{name}'. Use distinct relation names with rename.",
            )
        names[name] = True


def create_relation(name: str, columns, rows) -> Relation:
    """Validate widths and column types, then remove duplicate input rows.

    String column names create an ordinary base schema. Attribute objects can
    also be supplied, for example to give an empty relation known column types.
    """
    attributes = []
    for column in columns:
        if isinstance(column, str):
            attributes.append(Attribute(column, name))
        else:
            attributes.append(replace(column))
    if not attributes:
        raise RAError("Schema", f"Relation '{name}' needs at least one attribute.")
    check_unique_attributes(attributes)
    for attribute in attributes:
        if attribute.type not in (None, "number", "string"):
            raise RAError("Type", f"Unsupported type for '{display_name(attribute)}'.")

    unique = TupleSet()
    for row_number, input_row in enumerate(rows, start=1):
        row = tuple(input_row)
        if len(row) != len(attributes):
            raise RAError(
                "Schema",
                f"Relation '{name}', row {row_number}: expected "
                f"{len(attributes)} values, received {len(row)}.",
            )
        for attribute, value in zip(attributes, row):
            try:
                actual_type = value_type(value)
            except RAError as error:
                raise RAError(
                    "Type",
                    f"Relation '{name}', row {row_number}, "
                    f"attribute '{display_name(attribute)}': {error}",
                ) from None
            if attribute.type is None:
                attribute.type = actual_type
            elif attribute.type != actual_type:
                raise RAError(
                    "Type",
                    f"Relation '{name}', row {row_number}: attribute "
                    f"'{display_name(attribute)}' mixes {attribute.type} "
                    f"and {actual_type} values.",
                )
        unique.add(row)
    return Relation(name, attributes, unique.rows)


# Schema resolution, condition checking, and query execution.

def _attribute_label(reference: dict) -> str:
    if reference.get("qualifier") is not None:
        return f"{reference['qualifier']}.{reference['name']}"
    return reference["name"]


def _resolve_attribute(reference: dict, attributes: list[Attribute]) -> int:
    """Resolve against the schema, so empty tables still expose name errors."""
    found = None
    for index, attribute in enumerate(attributes):
        if attribute.name != reference["name"]:
            continue
        qualifier = reference.get("qualifier")
        if qualifier is not None and qualifier != attribute.qualifier:
            continue
        if found is not None:
            raise RAError(
                "Name",
                f"Ambiguous attribute '{_attribute_label(reference)}'; "
                "qualify it with a relation name.",
                reference.get("pos"),
            )
        found = index
    if found is None:
        raise RAError(
            "Name", f"Unknown attribute '{_attribute_label(reference)}'.",
            reference.get("pos"),
        )
    return found


@dataclass
class _PreparedOperand:
    """Remember a checked literal or column position before processing rows."""

    type: str | None
    row_side: str
    column_index: int = 0
    literal: object = None

    def value_from(self, left_row: tuple, right_row: tuple | None):
        if self.row_side == "literal":
            return self.literal
        if self.row_side == "left":
            return left_row[self.column_index]
        return right_row[self.column_index]


def _prepare_operand(operand: dict, attributes: list[Attribute], left_column_count: int):
    if operand["kind"] == "literal":
        value = operand["value"]
        return _PreparedOperand(value_type(value), "literal", literal=value)

    # A join schema lists the left columns first, then the right columns.
    # Remember which input row contains this column and its position there.
    index = _resolve_attribute(operand, attributes)
    column_type = attributes[index].type
    if index < left_column_count:
        return _PreparedOperand(column_type, "left", index)
    right_index = index - left_column_count
    return _PreparedOperand(column_type, "right", right_index)


# These standard functions perform the ordinary Python comparisons:
# operator.eq(a, b) means a == b, operator.lt(a, b) means a < b, and so on.
_COMPARISONS = {
    "=": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


def _prepare_condition(condition: dict, attributes: list[Attribute], left_column_count: int):
    """Check names and types once, then return a function that tests rows."""
    kind = condition["kind"]
    if kind == "not":
        child_matches = _prepare_condition(condition["input"], attributes, left_column_count)

        def matches_not(left_row, right_row=None):
            return not child_matches(left_row, right_row)

        return matches_not

    if kind in ("and", "or"):
        # Check both branches before processing rows. Short-circuit execution
        # must not hide a bad name or an incompatible comparison type.
        left_matches = _prepare_condition(condition["left"], attributes, left_column_count)
        right_matches = _prepare_condition(condition["right"], attributes, left_column_count)

        if kind == "and":
            def matches_and(left_row, right_row=None):
                return left_matches(left_row, right_row) and right_matches(left_row, right_row)

            return matches_and

        def matches_or(left_row, right_row=None):
            return left_matches(left_row, right_row) or right_matches(left_row, right_row)

        return matches_or

    left_operand = _prepare_operand(condition["left"], attributes, left_column_count)
    right_operand = _prepare_operand(condition["right"], attributes, left_column_count)
    both_types_known = left_operand.type is not None and right_operand.type is not None
    if both_types_known and left_operand.type != right_operand.type:
        raise RAError(
            "Type",
            f"Cannot compare {left_operand.type} with {right_operand.type} using '{condition['op']}'.",
            condition.get("pos"),
        )
    op = condition["op"]
    if op not in _COMPARISONS:
        raise RAError("Syntax", f"Unknown comparison operator '{op}'.", condition.get("pos"))

    # Equality joins can read two known column positions directly.
    # Avoiding extra function calls matters when there are billions of pairs.
    # This is still an ordinary nested-loop join: every pair is examined.
    if op == "=" and left_operand.row_side == "left" and right_operand.row_side == "right":
        left_index = left_operand.column_index
        right_index = right_operand.column_index

        def matches_equal(left_row, right_row):
            return left_row[left_index] == right_row[right_index]

        return matches_equal

    if op == "=" and left_operand.row_side == "right" and right_operand.row_side == "left":
        right_index = left_operand.column_index
        left_index = right_operand.column_index

        def matches_equal_reversed(left_row, right_row):
            return right_row[right_index] == left_row[left_index]

        return matches_equal_reversed

    compare = _COMPARISONS[op]

    def matches_comparison(left_row, right_row=None):
        left_value = left_operand.value_from(left_row, right_row)
        right_value = right_operand.value_from(left_row, right_row)
        return compare(left_value, right_value)

    return matches_comparison


def _combined_attributes(left: Relation, right: Relation) -> list[Attribute]:
    attributes = []
    for attribute in left.attributes + right.attributes:
        attributes.append(replace(attribute, qualified=True))
    check_unique_attributes(attributes)
    return attributes


def _compatible_attributes(left: Relation, right: Relation, position) -> list[Attribute]:
    if len(left.attributes) != len(right.attributes):
        raise RAError(
            "Schema",
            f"Set operands have different widths ({len(left.attributes)} "
            f"and {len(right.attributes)}).",
            position,
        )
    attributes = []
    for index, (attribute, other) in enumerate(zip(left.attributes, right.attributes), start=1):
        if display_name(attribute) != display_name(other):
            raise RAError(
                "Schema",
                f"Set operands differ at column {index}: "
                f"'{display_name(attribute)}' versus '{display_name(other)}'.",
                position,
            )
        if attribute.type is not None and other.type is not None and attribute.type != other.type:
            raise RAError(
                "Schema",
                f"Set operands have incompatible types for '{display_name(attribute)}': "
                f"{attribute.type} and {other.type}.",
                position,
            )
        # An initially empty input has unknown types. The other side can fill
        # these in, while names and qualifiers always come from the left side.
        column_type = attribute.type
        if column_type is None:
            column_type = other.type
        attributes.append(replace(attribute, type=column_type))
    return attributes


def evaluate(ast: dict, relations: dict[str, Relation]) -> dict:
    """Return the result and separate counters for each operator instance."""
    stats = []

    def record(operator: str, examined: int, relation: Relation) -> Relation:
        stats.append({
            "operator": operator,
            "examined": examined,
            "output_rows": len(relation.rows),
        })
        return relation

    def visit(node: dict) -> Relation:
        kind = node["kind"]
        if kind == "relation":
            if node["name"] not in relations:
                raise RAError("Name", f"Unknown relation '{node['name']}'.", node.get("pos"))
            return relations[node["name"]]

        if kind == "select":
            source = visit(node["input"])
            predicate = _prepare_condition(node["condition"], source.attributes, len(source.attributes))
            rows = []
            examined = 0
            for row in source.rows:
                examined += 1
                if predicate(row):
                    rows.append(row)
            return record(kind, examined, Relation(source.name, source.attributes, rows))

        if kind == "project":
            source = visit(node["input"])
            indices = []
            attributes = []
            for requested_attribute in node["attributes"]:
                index = _resolve_attribute(requested_attribute, source.attributes)
                indices.append(index)
                attributes.append(replace(source.attributes[index]))
            check_unique_attributes(attributes)
            unique = TupleSet()
            examined = 0
            for row in source.rows:
                examined += 1
                projected = []
                for index in indices:
                    projected.append(row[index])
                unique.add(tuple(projected))
            return record(kind, examined, Relation(source.name, attributes, unique.rows))

        if kind == "rename":
            source = visit(node["input"])
            attributes = []
            for attribute in source.attributes:
                attributes.append(replace(attribute, qualifier=node["name"]))
            check_unique_attributes(attributes)
            return record(kind, 0, Relation(node["name"], attributes, source.rows))

        left = visit(node["left"])
        right = visit(node["right"])
        if kind in ("times", "join"):
            attributes = _combined_attributes(left, right)
            predicate = None
            if kind == "join":
                predicate = _prepare_condition(node["condition"], attributes, len(left.attributes))
            rows = []
            examined = 0
            for left_row in left.rows:
                for right_row in right.rows:
                    # Increment the actual counter INSIDE the nested loops.
                    examined += 1
                    if predicate is None or predicate(left_row, right_row):
                        rows.append(left_row + right_row)
            # Set-valued inputs make every concatenated pair unique already.
            return record(kind, examined, Relation(None, attributes, rows))

        attributes = _compatible_attributes(left, right, node.get("pos"))
        if kind == "union":
            unique = TupleSet()
            examined = 0
            for row in left.rows:
                examined += 1
                unique.add(row)
            for row in right.rows:
                examined += 1
                unique.add(row)
            return record(kind, examined, Relation(left.name, attributes, unique.rows))

        if kind in ("intersect", "minus"):
            membership = TupleSet(right.rows)
            rows = []
            examined = 0
            for row in left.rows:
                examined += 1
                present = membership.has(row)
                if (kind == "intersect" and present) or (kind == "minus" and not present):
                    rows.append(row)
            return record(kind, examined, Relation(left.name, attributes, rows))

        raise RAError("Syntax", f"Unknown relational operator '{kind}'.", node.get("pos"))

    return {"relation": visit(ast), "stats": stats}
