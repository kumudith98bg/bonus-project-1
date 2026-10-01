Python relational algebra program

This is my relational algebra project in Python. I chose Python because it is easier for me to understand and explain. The program reads tables and answers queries about them. A query is an instruction, such as keeping employees older than 30. A relation means a table and a tuple means a row.

Requirements

The project needs Python 3.10 or newer. It was tested with Python 3.13.5. Running queries and tests needs no extra packages. Matplotlib is only needed to draw the graph.

All commands below run from the project folder that contains ra.py.

Running a query

python3 ra.py --data examples/employees.ra 'project[Name](select[Age>30](Employees))'

This finds employees older than 30 and shows their names. With the example data, the result is John.

A query run uses one data file and one query. The query is kept inside quotes in the terminal. The data file can contain several tables. The result shows the column names, even when no rows match.

Other example queries:

python3 ra.py -d examples/employees.ra 'project[DID](Employees)'
python3 ra.py -d examples/employees.ra 'Emp join[Emp.DID=Dept.DID] Dept'
python3 ra.py -d examples/employees.ra --stats 'select[Age>30](Employees)'

The first shows each department ID once. The second matches employees with their departments. The third finds employees older than 30 and shows how many rows were checked. The -d option is short for --data. The --stats option shows the work counted for each operation.

Command options:

python3 ra.py --help

Query tree

A query tree shows how the program groups the parts of a query. This command prints the tree without loading tables or running the query:

python3 ra.py --tree 'A union B minus C'

Minus appears at the top, with Union below it on the left. This means (A union B) minus C: first combine A and B, then remove rows found in C.

Project files

GRAMMAR.md: Rules for writing queries and data.
REPORT.md: Timing results, the graph filename, and explanations.
DESIGN_LOG.md: Problems found and changes made with AI help.
ra.py: Starts the program and prints results or errors.
source/language.py: Reads query text, builds the tree, and prints it.
source/engine.py: Stores tables and carries out the operations.
source/errors.py: Helps turn errors into short messages.
source/generate.py: Creates tables for testing.
source/benchmark.py: Runs timing tests and saves the results.
source/plot_report.py: Draws the graph from saved results.
tests/: Checks the 25 required cases and other cases.
examples/employees.ra: Sample tables for the commands above.
measurements/results.json: Saved times, counts, and settings.
measurements/performance.png: The report graph.

How a query goes through the code

First, language.py reads each character and splits the query into small pieces called tokens. For example, Age>30 becomes Age, >, and 30. Text inside quotes stays together.

Next, it builds a tree showing the order of the operations. For the first example, the program starts with Employees, selects rows where Age>30, and then keeps the Name column.

Then engine.py carries out those operations. It keeps John's row because his age is 32. Finally, ra.py prints his name.

Writing a data file

People (id, name, age) = {
1, Alice, 28
2, 'O''Brien', 32
3, 'Bob)', -30
}

Each row goes on its own line and has one value for each column. Repeated rows are kept only once. Blank lines and lines starting with // are ignored.

Text without spaces or special characters can be written without quotes in a data file. Text containing spaces, commas, parentheses, braces, or apostrophes needs single quotes around it. Two apostrophes inside quoted text stand for one apostrophe, as in 'O''Brien'.

In a query, text values must be quoted, such as Name='John'. A name without quotes refers to a column. Capital and small letters are different: Employees and employees are different names.

Supported operations

select[condition](R): Keeps rows that match the condition, with all their columns.
project[a,b](R): Keeps columns a and b in that order and removes repeated result rows.
rename[X](R): Gives the table the name X for use in the query.
R times S: Combines every row in R with every row in S.
R join[condition] S: Keeps the combined rows that match the condition, with columns from both tables.
R union S: Keeps rows found in either table, with no repeats.
R intersect S: Keeps rows found in both tables.
R minus S: Keeps rows in R that are not in S.

Conditions can use =, !=, <, <=, >, >=, not, and, or, and parentheses. A condition can compare a column with a value or another column. A column can have a name such as union; its place in the query tells the program that it is a column name.

Without parentheses, times and join group first, then intersect, then union and minus. Operations at the same level group from left to right. In conditions, not groups first, then and, then or. Parentheses change the grouping. GRAMMAR.md gives the full rules and examples.

Rules for columns and values

Union, intersect, and minus need tables with the same column names in the same order and matching value types. Their results keep the left table's columns.

Times and join keep all columns and add table names, such as Emp.DID and Dept.DID. The table name shows which column is meant when both tables have a column called DID. Repeating a full column name is an error. Listing the same column twice in project is also an error.

Values are numbers or text. A column cannot mix the two. Comparing a number with text is an error. Whole numbers stay exact. Decimal numbers and numbers written with an exponent, such as 1e3, may be rounded. The numbers 1 and 1.0 are equal, but the number 1 and the text '1' are different.

An empty table still has column names. If no values were given, their types are unknown. An empty result keeps any column types the program already knows.

Joining a table to itself

A self join uses the same table twice. This example matches employees with their managers:

python3 ra.py -d examples/employees.ra 'rename[E2](Emp) join[Emp.MgrID=E2.EID] Emp'

The name E2 is used for the manager side. Emp is used for the employee side. The condition matches an employee's MgrID with a manager's EID.

Without rename, both sides would have names such as Emp.EID. The program could not tell which side those names refer to, so it would report an error. Renaming one side before the join gives the two sides different names. Renaming an already joined table can still fail if it would give two columns the same name.

Counting work and removing repeats

Select counts each row it checks. Join counts every pair, including pairs that do not match. For each row in the first table, join goes through every row in the second table. Two rows on one side and three on the other mean six comparisons.

The code checks column names and types before going through the rows. It looks up column positions once so it does not repeat that work for every row.

TupleSet groups rows using a number called a hash. It then calls tuple_equal to check whether their values are equal. Sharing a hash does not automatically make rows equal. These checks remove repeats without skipping any join comparisons.

Error messages

Lexical error: Bad text, such as a quoted value with no closing quote.
Syntax error: A query written incorrectly, such as a missing parenthesis.
Name error: A missing table or column, or a column name that could mean more than one column.
Schema error: Columns that do not match the rules for an operation.
Type error: Values of the wrong kind, such as comparing a number with text.

Messages explain the problem. Lexical and syntax errors include a line and column. Known name and type errors are checked even if the input is empty or part of a condition would not be used.

Tests

python3 -m unittest discover -s tests -v

Creating test data

python3 source/generate.py --n 1000 --m 2000 --match-rate 4 --out data/generated/example.ra

This creates R(a,b) with 1,000 rows and S(b,c) with 2,000 rows. Match rate means roughly how many rows in S match each row in R. Here it asks for four matches per row. A rate of zero gives no matches. Some sizes and rates give uneven groups, so the actual rate can differ from the setting.

Join query for this data:

python3 ra.py -d data/generated/example.ra --stats 'R join[R.b=S.b] S'

Timing tests

python3 source/benchmark.py --out measurements/my-run

This runs join, select, and project at all seven required sizes, plus tests with different match rates. The largest join checks over four billion pairs and can take several minutes. Results are saved after each operation in measurements/my-run/results.json.

Command for a smaller run:

python3 source/benchmark.py --sizes 1000,2000,4000 --out measurements/small-run

Without --out, the program replaces measurements/results.json. The report and graph need to be updated to match whenever the saved measurements change.

Drawing the graph

The existing graph is measurements/performance.png. These commands draw it again from measurements/results.json on macOS or Linux:

python3 -m venv .venv
.venv/bin/pip install -r requirements-plot.txt
.venv/bin/python source/plot_report.py

The first command creates a separate place for the plotting package. The second installs it. The third draws the graph. This command draws a graph from the new timing run:

.venv/bin/python source/plot_report.py measurements/my-run/results.json --out measurements/my-run/performance.png

Limits

Tables and results are kept in memory. Very large joins or products can run out of memory. Very deep queries and extremely long numbers can reach Python's limits.

The program supports the operations listed above. It does not support SQL, calculations inside queries, grouped sums or counts, natural or outer joins, or relational division. It does not change queries to make them faster or use indexes, hash joins, or sort-merge joins. Boolean values, null, NaN, and infinity are not supported value types.

The code reads queries character by character. It does not use regular expressions, parser generators, or Python eval or exec. The table operations do not use data-processing libraries.
