#!/usr/bin/env python3
"""Run one query against a relation file, or print its tree without executing it."""

import argparse
from pathlib import Path
import sys

from source.engine import evaluate, display_name
from source.language import parse_definitions, parse_query, format_tree
from source.errors import format_error


def render(relation):
    """Print the schema even when the result has no rows."""
    columns = [display_name(attribute) for attribute in relation.attributes]
    rows = []
    for row in relation.rows:
        formatted_row = []
        for value in row:
            if isinstance(value, str):
                text = "'" + value.replace("'", "''") + "'"
            else:
                text = str(value)
            formatted_row.append(text)
        rows.append(formatted_row)
    widths = [len(name) for name in columns]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(row):
        padded_cells = []
        for index, cell in enumerate(row):
            padded_cells.append(cell.ljust(widths[index]))
        return " | ".join(padded_cells)

    print(line(columns))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(line(row))
    print(f"({len(rows)} {'tuple' if len(rows) == 1 else 'tuples'})")


def main(arguments=None):
    arguments = sys.argv[1:] if arguments is None else arguments
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", metavar="QUERY", help="relational algebra query")
    parser.add_argument("-d", "--data", type=Path, help="file containing relation definitions")
    parser.add_argument("--tree", action="store_true", help="print the tree without loading or executing data")
    parser.add_argument("--stats", action="store_true", help="print each operator's counter")
    if not arguments:
        parser.print_help()
        return 0
    options = parser.parse_args(arguments)
    try:
        tree = parse_query(options.query)
        if options.tree:
            print(format_tree(tree))
            return 0
        relations = {}
        if options.data:
            data_text = options.data.read_text(encoding="utf-8")
            relations = parse_definitions(data_text)
        result = evaluate(tree, relations)
        render(result["relation"])
        if options.stats:
            for index, stat in enumerate(result["stats"], 1):
                print(
                    f"{index}. {stat['operator']}: "
                    f"examined={stat['examined']}, output={stat['output_rows']}",
                    file=sys.stderr,
                )
        return 0
    except RecursionError:
        print("Limit error: query is too deeply nested", file=sys.stderr)
    except MemoryError:
        print("Limit error: result exceeds available memory", file=sys.stderr)
    except KeyboardInterrupt:
        print("Interrupted: query cancelled", file=sys.stderr)
    except Exception as error:
        print(format_error(error), file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
