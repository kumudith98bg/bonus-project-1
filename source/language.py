"""Scan query text, parse its structure, and print the resulting operation tree."""

import math

from .errors import RAError
from .engine import create_relation


# Character-by-character scanning. Tokens remember their source positions.

def is_digit(character):
    return character is not None and "0" <= character <= "9"


def is_identifier_start(character):
    return character is not None and (
        "a" <= character <= "z" or "A" <= character <= "Z" or character == "_"
    )


def is_identifier_part(character):
    return is_identifier_start(character) or is_digit(character)


def is_number_text(text):
    """Recognize a complete signed decimal or exponent spelling by hand."""
    index = 0

    def current():
        return text[index] if index < len(text) else None

    if current() in ("+", "-"):
        index += 1
    digits = 0
    while is_digit(current()):
        index += 1
        digits += 1
    if current() == ".":
        index += 1
        while is_digit(current()):
            index += 1
            digits += 1
    if digits == 0:
        return False
    if current() in ("e", "E"):
        index += 1
        if current() in ("+", "-"):
            index += 1
        exponent_start = index
        while is_digit(current()):
            index += 1
        if index == exponent_start:
            return False
    return index == len(text)


def number_value(text, position):
    """Integers stay exact; decimal/exponent spellings use finite floats."""
    try:
        if "." not in text and "e" not in text and "E" not in text:
            return int(text)
        value = float(text)
    except (ValueError, OverflowError) as error:
        raise RAError("Type", "numeric literal exceeds the supported input limits", position) from error
    if not math.isfinite(value):
        raise RAError("Type", "number must be finite", position)
    return value


class Scanner:
    def __init__(self, source, mode="query"):
        self.source = source
        self.mode = mode
        self.index = 0
        self.line = 1
        self.column = 1
        self.line_start = True
        self.in_body = False
        self.tokens = []

    def peek(self, ahead=0):
        index = self.index + ahead
        return self.source[index] if index < len(self.source) else None

    def position(self):
        return {"offset": self.index, "line": self.line, "column": self.column}

    def advance(self):
        character = self.source[self.index]
        self.index += 1
        if character == "\r":
            if self.peek() == "\n":
                self.index += 1
            self.line += 1
            self.column = 1
            self.line_start = True
        elif character == "\n":
            self.line += 1
            self.column = 1
            self.line_start = True
        else:
            self.column += 1
            if character not in (" ", "\t"):
                self.line_start = False
        return character

    def add(self, token_type, value, position):
        self.tokens.append({"type": token_type, "value": value, "pos": position})

    def quoted_string(self, position):
        self.advance()  # Opening apostrophe.
        characters = []
        while self.peek() is not None and self.peek() not in ("\r", "\n"):
            if self.peek() == "'":
                self.advance()
                if self.peek() == "'":
                    self.advance()
                    characters.append("'")
                else:
                    self.add("STRING", "".join(characters), position)
                    return
            else:
                characters.append(self.advance())
        raise RAError("Lexical", "unterminated string literal", position)

    def bare_value(self, position):
        characters = []
        delimiters = (" ", "\t", "\r", "\n", ",", "{", "}", "(", ")", "'")
        while self.peek() is not None and self.peek() not in delimiters:
            characters.append(self.advance())
        text = "".join(characters)
        if is_number_text(text):
            self.add("NUMBER", number_value(text, position), position)
        else:
            self.add("BARE", text, position)

    def number(self, position):
        characters = []
        if self.peek() in ("+", "-"):
            characters.append(self.advance())
        while is_digit(self.peek()):
            characters.append(self.advance())
        if self.peek() == ".":
            characters.append(self.advance())
            while is_digit(self.peek()):
                characters.append(self.advance())
        if self.peek() in ("e", "E"):
            characters.append(self.advance())
            if self.peek() in ("+", "-"):
                characters.append(self.advance())
            while is_digit(self.peek()):
                characters.append(self.advance())
        text = "".join(characters)
        if not is_number_text(text) or is_identifier_start(self.peek()):
            raise RAError("Lexical", f"invalid numeric literal starting with '{text}'", position)
        self.add("NUMBER", number_value(text, position), position)

    def scan(self):
        punctuation = {
            "(": "LPAREN", ")": "RPAREN", "[": "LBRACKET", "]": "RBRACKET",
            "{": "LBRACE", "}": "RBRACE", ",": "COMMA", ".": "DOT",
        }
        while self.peek() is not None:
            character = self.peek()
            position = self.position()
            # A number can start with a digit, a decimal point, or a sign.
            starts_number = is_digit(character)
            if character == ".":
                starts_number = is_digit(self.peek(1))
            elif character in ("+", "-"):
                if self.peek(1) == ".":
                    starts_number = is_digit(self.peek(2))
                else:
                    starts_number = is_digit(self.peek(1))

            if character in (" ", "\t"):
                self.advance()
            elif character in ("\r", "\n"):
                self.advance()
                if self.mode == "data":
                    self.add("NEWLINE", "\n", position)
            elif self.line_start and character == "/" and self.peek(1) == "/":
                while self.peek() is not None and self.peek() not in ("\r", "\n"):
                    self.advance()
            elif character == "'":
                self.quoted_string(position)
            elif self.mode == "data" and self.in_body and character not in (",", "{", "}", "(", ")"):
                # Data cells may contain bare emails and other non-identifier text.
                self.bare_value(position)
            elif is_identifier_start(character):
                characters = [self.advance()]
                while is_identifier_part(self.peek()):
                    characters.append(self.advance())
                # All words are IDENT; the parser interprets contextual keywords.
                self.add("IDENT", "".join(characters), position)
            elif starts_number:
                self.number(position)
            elif character in ("=", "!", "<", ">"):
                operation = self.advance()
                if operation in ("!", "<", ">") and self.peek() == "=":
                    operation += self.advance()
                if operation == "!":
                    raise RAError("Lexical", "expected '=' after '!'", position)
                self.add("COMPARE", operation, position)
            elif character in punctuation:
                self.advance()
                self.add(punctuation[character], character, position)
                if self.mode == "data" and character == "{":
                    self.in_body = True
                elif self.mode == "data" and character == "}":
                    self.in_body = False
            else:
                raise RAError("Lexical", f"unexpected character '{character}'", position)
        self.add("EOF", "", self.position())
        return self.tokens


def tokenize(source, mode="query"):
    return Scanner(source, mode).scan()


# Recursive descent: one parser method for each precedence level.

class Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.index = 0

    def peek(self, ahead=0):
        return self.tokens[min(self.index + ahead, len(self.tokens) - 1)]

    def take(self):
        token = self.peek()
        self.index += 1
        return token

    def is_token(self, token_type):
        return self.peek()["type"] == token_type

    def is_word(self, word):
        return self.is_token("IDENT") and self.peek()["value"] == word

    def accept(self, token_type):
        if self.is_token(token_type):
            return self.take()
        return None

    def expect(self, token_type, description):
        if not self.is_token(token_type):
            found = "end of input" if self.is_token("EOF") else repr(self.peek()["value"])
            raise RAError("Syntax", f"expected {description}; found {found}", self.peek()["pos"])
        return self.take()

    def expression(self):
        return self.set_expression()

    def set_expression(self):
        left = self.intersection()
        while self.is_word("union") or self.is_word("minus"):
            operation = self.take()
            right = self.intersection()
            # Keep the previous tree on the left: A minus B minus C is (A minus B) minus C.
            left = {"kind": operation["value"], "left": left,
                    "right": right, "pos": operation["pos"]}
        return left

    def intersection(self):
        left = self.product()
        while self.is_word("intersect"):
            operation = self.take()
            right = self.product()
            left = {"kind": "intersect", "left": left,
                    "right": right, "pos": operation["pos"]}
        return left

    def product(self):
        left = self.primary()
        while self.is_word("times") or self.is_word("join"):
            operation = self.take()
            condition = None
            if operation["value"] == "join":
                self.expect("LBRACKET", "'[' after join")
                condition = self.condition()
                self.expect("RBRACKET", "closing ']' after join condition")
            right = self.primary()
            left = {"kind": operation["value"], "left": left,
                    "right": right, "pos": operation["pos"]}
            if condition is not None:
                left["condition"] = condition
        return left

    def primary(self):
        if self.accept("LPAREN"):
            expression = self.expression()
            self.expect("RPAREN", "closing ')' for grouped expression")
            return expression
        if self.is_token("IDENT"):
            name = self.take()
            is_unary_operator = (
                name["value"] in ("select", "project", "rename")
                and self.is_token("LBRACKET")
            )
            if is_unary_operator:
                self.take()  # Opening square bracket.
                node = {"kind": name["value"], "pos": name["pos"]}
                if name["value"] == "select":
                    node["condition"] = self.condition()
                elif name["value"] == "rename":
                    node["name"] = self.expect("IDENT", "new relation name")["value"]
                else:
                    node["attributes"] = [self.attribute()]
                    while self.accept("COMMA"):
                        node["attributes"].append(self.attribute())
                self.expect("RBRACKET", "closing ']' after operator parameter")
                self.expect("LPAREN", "'(' before operator input")
                node["input"] = self.expression()
                self.expect("RPAREN", "closing ')' after operator input")
                return node
            return {"kind": "relation", "name": name["value"], "pos": name["pos"]}
        raise RAError("Syntax", "expected a relation, unary operation, or parenthesized expression (missing operand)", self.peek()["pos"])

    def attribute(self):
        first = self.expect("IDENT", "attribute name")
        if self.accept("DOT"):
            second = self.expect("IDENT", "attribute name after '.'")
            return {"name": second["value"], "qualifier": first["value"], "pos": first["pos"]}
        return {"name": first["value"], "qualifier": None, "pos": first["pos"]}

    def condition(self):
        return self.or_condition()

    def or_condition(self):
        left = self.and_condition()
        while self.is_word("or"):
            operation = self.take()
            right = self.and_condition()
            left = {"kind": "or", "left": left,
                    "right": right, "pos": operation["pos"]}
        return left

    def and_condition(self):
        left = self.not_condition()
        while self.is_word("and"):
            operation = self.take()
            right = self.not_condition()
            left = {"kind": "and", "left": left,
                    "right": right, "pos": operation["pos"]}
        return left

    def not_condition(self):
        # `not=1` names an attribute; `not a=1` negates a comparison.
        if self.is_word("not") and self.peek(1)["type"] not in ("COMPARE", "DOT"):
            operation = self.take()
            return {"kind": "not", "input": self.not_condition(), "pos": operation["pos"]}
        if self.accept("LPAREN"):
            condition = self.condition()
            self.expect("RPAREN", "closing ')' in condition")
            return condition
        left = self.operand()
        operation = self.expect("COMPARE", "comparison operator (=, !=, <, <=, >, >=)")
        right = self.operand()
        return {"kind": "compare", "op": operation["value"], "left": left,
                "right": right, "pos": operation["pos"]}

    def operand(self):
        if self.is_token("NUMBER") or self.is_token("STRING"):
            token = self.take()
            return {"kind": "literal", "value": token["value"], "pos": token["pos"]}
        attribute = self.attribute()
        attribute["kind"] = "attr"
        return attribute

    def newlines(self):
        while self.accept("NEWLINE"):
            pass

    def value(self):
        if self.peek()["type"] in ("NUMBER", "STRING", "BARE"):
            return self.take()["value"]
        raise RAError("Syntax", "expected a number or string value; quote strings containing spaces or punctuation", self.peek()["pos"])

    def definitions(self):
        relations = {}
        self.newlines()
        while not self.is_token("EOF"):
            name = self.expect("IDENT", "relation name")
            if name["value"] in relations:
                raise RAError("Name", f"duplicate relation '{name['value']}'", name["pos"])
            self.expect("LPAREN", "'(' before relation attributes")
            columns = [self.expect("IDENT", "attribute name")["value"]]
            while self.accept("COMMA"):
                columns.append(self.expect("IDENT", "attribute name")["value"])
            self.expect("RPAREN", "closing ')' after relation attributes")
            equal = self.expect("COMPARE", "'=' before relation body")
            if equal["value"] != "=":
                raise RAError("Syntax", "expected '=' before relation body", equal["pos"])
            self.expect("LBRACE", "'{' before relation tuples")
            self.newlines()
            rows = []
            while not self.is_token("RBRACE"):
                if self.is_token("EOF"):
                    self.expect("RBRACE", "closing '}' after relation tuples")
                row_position = self.peek()["pos"]
                row = [self.value()]
                while self.accept("COMMA"):
                    row.append(self.value())
                if len(row) != len(columns):
                    raise RAError("Schema", f"relation '{name['value']}' expects {len(columns)} values per tuple, received {len(row)}", row_position)
                rows.append(row)
                if not self.is_token("RBRACE"):
                    self.expect("NEWLINE", "newline between tuples or closing '}' (quote strings containing spaces)")
                self.newlines()
            self.take()  # Closing brace.
            try:
                relations[name["value"]] = create_relation(name["value"], columns, rows)
            except RAError as error:
                if error.position is None:
                    error.position = name["pos"]
                raise
            self.newlines()
        self.expect("EOF", "end of data file")
        return relations


def parse_query(source):
    parser = Parser(tokenize(source))
    tree = parser.expression()
    parser.expect("EOF", "end of query")
    return tree


def parse_definitions(source):
    return Parser(tokenize(source, mode="data")).definitions()


# Print the tree without executing its operations.

def attribute_text(attribute):
    if attribute.get("qualifier"):
        return f"{attribute['qualifier']}.{attribute['name']}"
    return attribute["name"]


def format_condition(node):
    kind = node["kind"]
    if kind == "attr":
        return f"Attr({attribute_text(node)})"
    if kind == "literal":
        value = node["value"]
        if isinstance(value, str):
            return "Str('" + value.replace("'", "''") + "')"
        return f"Num({value})"
    if kind == "compare":
        names = {"=": "Eq", "!=": "Ne", "<": "Lt", "<=": "Le", ">": "Gt", ">=": "Ge"}
        left = format_condition(node["left"])
        right = format_condition(node["right"])
        return f"{names[node['op']]}({left}, {right})"
    if kind == "not":
        return f"Not({format_condition(node['input'])})"
    left = format_condition(node["left"])
    right = format_condition(node["right"])
    return f"{kind.capitalize()}({left}, {right})"


def label(node):
    kind = node["kind"]
    if kind == "relation":
        return f"Relation({node['name']})"
    if kind == "select":
        return f"Select(cond={format_condition(node['condition'])})"
    if kind == "project":
        attribute_names = [attribute_text(attribute) for attribute in node["attributes"]]
        return "Project(attrs=[" + ", ".join(attribute_names) + "])"
    if kind == "rename":
        return f"Rename(name={node['name']})"
    if kind == "join":
        return f"Join(cond={format_condition(node['condition'])})"
    return kind.capitalize()


def format_tree(tree):
    lines = []

    def walk(node, prefix="", branch="", child_prefix=""):
        lines.append(prefix + branch + label(node))
        if "input" in node:
            children = [node["input"]]
        elif "left" in node:
            children = [node["left"], node["right"]]
        else:
            children = []
        for index, child in enumerate(children):
            if index == len(children) - 1:
                child_branch = "└── "
                grandchild_prefix = "    "
            else:
                child_branch = "├── "
                grandchild_prefix = "│   "
            walk(child, prefix + child_prefix, child_branch, grandchild_prefix)

    walk(tree)
    return "\n".join(lines)
