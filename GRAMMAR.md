# Relational algebra language

These rules use the commands in the assignment such as `select` and `project`.

## 1. What these rules mean

A grammar is a set of rules for writing something the program can understand. Here, the rules cover two things:

- `Query`: how to write a query, such as `select[Age>30](Employees)`.
- `DataFile`: how to write tables, column names, and rows in a file.

Each named part has its own rule. That rule can be used wherever the part appears. This is called a context-free grammar. These rules describe how the input is written. The program checks things such as whether a table exists later.

The rules below use EBNF, a short way to write grammar rules. Here is how to read the signs and names:

- `=` means "can be written as."
- Quoted text means write exactly that text. For example, `"select"` means the word `select`.
- `,` means one part comes after another.
- `|` means "or."
- `{ X }` means use X as many times as needed, or leave it out.
- `[ X ]` means use X once, or leave it out.
- `( X )` groups parts of a rule together.
- `;` ends a rule.
- `IDENT` means a name, such as `Employees` or `Age`.
- `EOF` means the end of what the program is reading.

Quotes matter: `"["` means an actual `[` must be written in the query. But `[ X ]` without quotes means X can be left out.

Capital and small letters are different: `Employees` and `employees` are two different names.

## 2. Query grammar

```ebnf
Query          = Expression, EOF ;
Expression     = SetExpression ;
SetExpression  = Intersection, { ("union" | "minus"), Intersection } ;
Intersection   = Product, { "intersect", Product } ;
Product        = Primary, { ProductSuffix } ;
ProductSuffix  = "times", Primary
               | "join", "[", Condition, "]", Primary ;
Primary        = "select", "[", Condition, "]", "(", Expression, ")"
               | "project", "[", AttributeList, "]", "(", Expression, ")"
               | "rename", "[", IDENT, "]", "(", Expression, ")"
               | "(", Expression, ")"
               | IDENT ;
AttributeList  = Attribute, { ",", Attribute } ;
Attribute      = IDENT, [ ".", IDENT ] ;

Condition      = OrCondition ;
OrCondition    = AndCondition, { "or", AndCondition } ;
AndCondition   = NotCondition, { "and", NotCondition } ;
NotCondition   = "not", NotCondition
               | "(", Condition, ")"
               | Comparison ;
Comparison     = Operand, CompareOp, Operand ;
CompareOp      = "=" | "!=" | "<" | "<=" | ">" | ">=" ;
Operand        = NUMBER | STRING | Attribute ;
```

Repeated binary operators build the tree from left to right: `A minus B minus C` groups as `(A minus B) minus C`. Comparisons cannot be chained: write `a < b and b < c`, not `a < b < c`. Arithmetic and boolean literal operands are unsupported.

### Contextual keywords

Every word scans as `IDENT`. Its position determines whether it is a name or an operator. `select`, `project`, and `rename` start unary operators only when followed by `[`; otherwise they can name relations.

An identifier in a comparison names an attribute: `select[union=3](R)` uses column `union`, and `select[A=B](R)` compares two columns. Query strings must be quoted, as in `Name='John'`; bare strings are allowed only in data definitions.

At the start of a condition, `not` followed by a comparison operator or `.` is an attribute name (`not=1` or `not.value=1`); otherwise it means negation. `and` and `or` are operators between complete conditions and can be attribute names in operand positions.

## 3. Lexical grammar and positions

```ebnf
IDENT          = LetterOrUnderscore, { LetterOrUnderscore | Digit } ;
LetterOrUnderscore = "A".."Z" | "a".."z" | "_" ;
Digit          = "0".."9" ;
Digits         = Digit, { Digit } ;
NUMBER         = [ "+" | "-" ], Mantissa, [ Exponent ] ;
Mantissa       = Digits, [ ".", { Digit } ] | ".", Digits ;
Exponent       = ("e" | "E"), [ "+" | "-" ], Digits ;
STRING         = "'", { StringCharacter | "''" }, "'" ;
StringCharacter = ? any character except apostrophe, CR, and LF ? ;
```

Character ranges are checked by hand, without regular expressions. Strings may be empty or contain punctuation and spaces. Two apostrophes represent one apostrophe; backslashes are ordinary characters. Strings cannot span lines. `CR` and `LF` are carriage return and line feed.

Numbers without a decimal point or exponent are exact Python integers; other spellings are finite floats and may round. Both have type `number`: `1` equals `1.0`, and negative zero equals zero. Null, NaN, infinity, and booleans are not value types. A query number immediately followed by a letter or underscore, such as `1foo`, is a lexical error.

The scanner uses maximal munch: it takes the longest valid token. Thus `>=` and `x1` are each one token, while `Age>-30` becomes `IDENT(Age)`, `>`, and `NUMBER(-30)`. Spaces are unnecessary between distinct tokens; adjacent identifiers need separation.

Whitespace means ASCII space, tab, CR, and LF. It is ignored between query tokens. Lines starting with `//` after optional whitespace are comments; trailing comments are unsupported, and `//` inside a string stays literal. Every token, including EOF, records its starting offset, line, and column. Error messages use one-based lines and columns.

## 4. Relation definitions

```ebnf
DataFile       = { NEWLINE }, { Definition, { NEWLINE } }, EOF ;
Definition     = IDENT, "(", NameList, ")", "=", "{", Body, "}" ;
NameList       = IDENT, { ",", IDENT } ;
Body           = { NEWLINE }, [ Row, { NEWLINE, { NEWLINE }, Row },
                              { NEWLINE } ] ;
Row            = Value, { ",", Value } ;
Value          = NUMBER | STRING | BARE ;
BARE           = BareCharacter, { BareCharacter } ;
BareCharacter  = ? any character except whitespace, comma, apostrophe,
                   parentheses, and braces ? ;
NEWLINE        = LF | CR, [ LF ] ;
```

Spaces and tabs around tokens and cells, blank lines, and whole-line comments are ignored. Each row occupies one line and must have one value per header attribute. The final row may end directly with `}`; `{}` is an empty relation. Headers stay on one line and need at least one attribute. Duplicate attribute names or relation definitions are errors.

An unquoted data cell matching the complete `NUMBER` rule is numeric; other valid `BARE` cells are strings. Quoting forces a string, so `30` is numeric and `'30'` is text. Strings containing whitespace, commas, parentheses, apostrophes, or braces must be quoted. Bare values such as `E1` and `al@c.ca` are allowed.

```text
// employees and their departments
Employees (EID, Name, Age, DID) = {
E1, John, 32, D1
E2, Alice, 28, D2
E3, 'O''Brien', 29, D1
}
```

Column types are inferred from their values; mixing numbers and strings in one column is an error. Empty input columns have unknown types, compatible with either type. Known types must agree, and empty results retain their known types. Duplicate input rows collapse to one.

## 5. Precedence and associativity

Precedence determines which operators group first; higher levels bind more tightly. Associativity determines grouping when operators share a level.

| Relational level | Operators                                             | Associativity                | Enforcing production |
| ---------------- | ----------------------------------------------------- | ---------------------------- | -------------------- |
| 4                | `(...)`, `select[...]`, `project[...]`, `rename[...]` | Explicitly delimited nesting | `Primary`            |
| 3                | `times`, `join[...]`                                  | Left                         | `Product`            |
| 2                | `intersect`                                           | Left                         | `Intersection`       |
| 1                | `union`, `minus`                                      | Left, including mixed chains | `SetExpression`      |

| Condition level | Operators                       | Associativity                         | Enforcing production |
| --------------- | ------------------------------- | ------------------------------------- | -------------------- |
| 5               | Attribute and literal operands  | Not applicable                        | `Operand`            |
| 4               | `=`, `!=`, `<`, `<=`, `>`, `>=` | Non-associative; exactly two operands | `Comparison`         |
| 3               | `not`                           | Right, as repeated prefix negation    | `NotCondition`       |
| 2               | `and`                           | Left                                  | `AndCondition`       |
| 1               | `or`                            | Left                                  | `OrCondition`        |

Parentheses override precedence. `not a=1 and b=2 or c=3` means `((not (a=1)) and (b=2)) or (c=3)`. Unary relational operators take a whole expression inside their required parentheses.

## 6. Ambiguity demonstration

The assignment's deliberately naive grammar is:

```ebnf
Expr = Expr, "union", Expr
     | Expr, "minus", Expr
     | "(", Expr, ")"
     | IDENT ;
```

It permits two trees for the same input, `A union B minus C`:

```text
Tree 1: (A union B) minus C       Tree 2: A union (B minus C)

Minus                            Union
├── Union                        ├── Relation(A)
│   ├── Relation(A)               └── Minus
│   └── Relation(B)                   ├── Relation(B)
└── Relation(C)                       └── Relation(C)
```

Let all three relations have schema `(x)` with numeric values:

```text
A(x) = {1}
B(x) = {2}
C(x) = {1}
```

Tree 1 yields `{1,2} minus {1} = {2}`. Tree 2 yields `{1} union ({2} minus {1}) = {1,2}`. The ambiguity changes the answer.

Section 2 separates precedence levels. Its `SetExpression` rule combines each following operator with the tree built so far, forcing Tree 1. Explicit parentheses in `A union (B minus C)` produce Tree 2.

### Difference is not associative

For `A minus B minus C`, use `A(x)={1}`, `B(x)={1}`, and `C(x)={1}`. The documented left grouping gives `(A minus B) minus C = {} minus {1} = {}`. The other grouping gives `A minus (B minus C) = {1} minus {} = {1}`. The printed tree for the unparenthesized expression must therefore have a `Minus` node as the left child of the root `Minus`.

## 7. Names, schemas, and equality

Rows are equal when they have the same length and equal values of the same language type at every position. Numeric equality follows section 3; a number and a string remain distinct. Strings compare case sensitively in Python's Unicode lexicographic order. Relations are sets, so duplicates disappear and row order is unspecified.

- An unqualified attribute must match exactly one column. Unknown or ambiguous names are errors.
- Projection preserves the requested column order and removes duplicate rows. An empty list is a syntax error; requesting the same column twice, including `Name` and `R.Name`, is a schema error.
- Base schemas display column names. Products and joins display `Qualifier.Name`, preserve original qualifiers through nesting, and reject duplicate qualified names.
- Rename replaces qualifiers while preserving column names and their qualified/unqualified display. It rejects resulting name collisions.
- Set operations require matching displayed names in the same order and compatible types. They retain the left schema, refining unknown types from the right when possible. Base `R(a)` and `S(a)` are compatible; differently qualified product columns are not.
- Comparing a known number with a string is a type error, even for `!=`. All condition names and known types are checked before visiting rows, including empty inputs and branches that would otherwise be skipped.

## 8. Parsing strategy

The handwritten parser uses recursive descent: functions follow grammar rules, consume tokens, and build an abstract syntax tree (AST). Each precedence level has its own function. This maps directly to the grammar and makes errors such as missing brackets easy to locate.

The naive rule `Expr = Expr, "union", Expr | ...` is left recursive: `Expr` would call itself before consuming a token, repeating until Python's recursion limit. Section 2 removes this problem: `SetExpression` first parses an `Intersection`, then loops over following operators. `Intersection`, `Product`, `AndCondition`, and `OrCondition` use the same pattern. Recursive calls for `not` and parentheses consume `not` or `(` first, so they make progress.

## 9. Sources, assignment corrections, and AI assistance

Sources consulted for the earlier design, which this Python version adapts:

1. Assignment write-up supplied with the coursework, sections 4–7: required syntax, semantics, restrictions, and test cases.
2. Abdelghny Orogat, Carleton University, _Relational Algebra_ lecture supplied with the coursework: selection/projection (pages 30–32), products/joins (35–39), set operators (46–52), and examples (63–70). The assignment's matching-column-name rule takes priority over the lecture's differently named `Dept`/`Depar` examples.
3. Robert Nystrom, [Crafting Interpreters: Scanning](https://craftinginterpreters.com/scanning.html), read 2026-09-30: token boundaries, maximal munch, and quoted-string scanning.
4. Robert Nystrom, [Crafting Interpreters: Parsing Expressions](https://craftinginterpreters.com/parsing-expressions.html), read 2026-09-30: precedence levels, associativity, and removing left recursion for recursive descent.

Write-up section 6.2 and test case 14 contain `<...>` wrappers and `%3E`, apparently formatting errors. We follow section 4's ASCII syntax and use `project[Name](select[Age>30](select[DID='D1'](Employees)))` for case 14. The parser does not URL-decode `%3E`, accept the extra wrappers, or support Unicode operators.

One AI mistake in the earlier JavaScript version was a grammar description claiming that large integers could round, while its scanner actually rejected them. Comparing the document with the code exposed the mismatch. The Python version's number rules were rewritten to match Python's exact integers and finite floats. Further observed mistakes and fixes are recorded in [DESIGN_LOG.md](DESIGN_LOG.md).
