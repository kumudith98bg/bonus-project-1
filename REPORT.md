Python performance report

Python version: CPython 3.13.5. The program uses one Python thread.
Measured: 2026-09-30.

These results were collected after simplifying the code. The full results, exact times, and test settings are saved in measurements/results.json.

How the tests were run

These commands run the timing tests and draw the graph from the Python project:

python3 source/benchmark.py --out measurements
python3 source/plot_report.py

The graph program needs Matplotlib, listed in requirements-plot.txt. The timing program creates two tables, R(a,b) and S(b,c). Every row has its own ID. In the main tests, each row in R has one matching row in S.

Each operation was run twice with 250-row tables as a warmup. It was then timed once at each required size. The numbers below are individual runs, not averages.

The timer uses Python's time.perf_counter(). It includes checking column names and types, running the operation, and building the result. It does not include creating or loading the data, reading the query, the memory cleanup before each test, or saving the results. Other activity on the computer can affect the time.

The code counts the rows or pairs it checks while the operation runs. These counts are measured, not estimated.

Part 1: Join comparisons and time

Query: R join[R.b=S.b] S

n means the number of rows in R. m means the number of rows in S. Output rows means the number of rows in the result.

n m Comparisons Time (seconds) Output rows
1,000 1,000 1,000,000 0.076330 1,000
2,000 2,000 4,000,000 0.341989 2,000
4,000 4,000 16,000,000 1.203417 4,000
8,000 8,000 64,000,000 4.795561 8,000
16,000 16,000 256,000,000 19.451276 16,000
32,000 32,000 1,024,000,000 77.299765 32,000
64,000 64,000 4,096,000,000 350.629536 64,000

The join compares every row in R with every row in S, even when they do not match. The comparison count is n x m. Every measured count matches this rule.

For example, 64,000 x 64,000 = 4,096,000,000 comparisons. Doubling the rows in both tables gives four times as many comparisons.

Part 2: The graph and its slope

Graph file: measurements/performance.png

The graph uses log scales on both axes, as the assignment asks. Equal steps on a log scale mean multiplying by the same amount. This helps show how quickly the time grows as the tables get larger.

The slope tells us how steep the line is. The program calculates it by finding the line that best fits the log values of the sizes and times. The join slope is 2.005, which is close to 2. This means that doubling both table sizes takes about four times as long overall. The two loops in the join explain this growth: for each row in R, the program goes through every row in S.

Part 3: Select and project

Select keeps rows that pass a condition. The test uses select[a>=N](R), where N is replaced with half the table size. For 1,000 rows, the query is select[a>=500](R).

Select results:

Input rows Rows checked Time (seconds) Output rows
1,000 1,000 0.000218 500
2,000 2,000 0.000412 1,000
4,000 4,000 0.000834 2,000
8,000 8,000 0.001667 4,000
16,000 16,000 0.003182 8,000
32,000 32,000 0.006482 16,000
64,000 64,000 0.013476 32,000

Project keeps the listed columns and removes repeated rows. The test uses project[b](R).

Project results:

Input rows Rows checked Time (seconds) Output rows
1,000 1,000 0.000486 1,000
2,000 2,000 0.000937 2,000
4,000 4,000 0.001987 4,000
8,000 8,000 0.003648 8,000
16,000 16,000 0.007536 16,000
32,000 32,000 0.015199 32,000
64,000 64,000 0.031116 64,000

The select slope is 0.990. The project slope is 0.999. Both are close to 1: doubling the input rows takes about twice as long overall. Both operations go through the input once. Join checks every pair of rows, so its time grows much faster.

Project also builds new rows and checks for repeats, so it does more work per row than select. It groups rows using a number called a hash, then uses our own code to check whether the rows are equal. With these two-column tables, the total work grows roughly with the number of rows. If many different rows share the same hash, the checks can take longer.

In the main tests, every b value is different, so project keeps all rows. Separate tests check that repeated rows are removed.

Part 4: Estimating a join with one million rows per table

One million rows in each table would need 1,000,000 x 1,000,000 = 1,000,000,000,000 comparisons.

The estimate uses the measured time for 64,000 rows per table. The full saved time is used in the calculation:

Increase in each table's size = 1,000,000 / 64,000 = 15.625
Increase in comparisons = 15.625 x 15.625 = 244.140625
Estimated time = 350.629535708 seconds x 244.140625
Estimated time = about 85,602.91 seconds
Estimated time = about 1,426.72 minutes
Estimated time = about 23.78 hours

This assumes the same computer, similar time for each comparison, and about one match per row. Memory use and other activity on the computer could change the time. The million-row join was not run.

Part 5: Changing how many rows match

Match rate means how many rows in S match each row in R. These tests keep both tables at 4,000 rows and change the match rate. Requested rate is the setting used; actual rate comes from the result.

Requested rate Actual rate Comparisons Time (seconds) Output rows
0 0 16,000,000 1.226209 0
1 1 16,000,000 1.240591 4,000
4 4 16,000,000 1.234857 16,000
16 16 16,000,000 1.227033 64,000

Every test makes 16,000,000 comparisons because the join still checks every pair. More matches mean more result rows to create and store, which can take more time. But the times also vary because of other computer activity. In these runs, more matches did not always give a longer time.

Part 6: How a faster join could work

A hash join could group the rows in S by their b value. For each row in R, it could look up the group with the same b value. This would avoid checking every pair. The expected work would be about n + m + the number of result rows. Each group must keep all its rows, and the code must still check that values are equal. Very large results might need to be saved in parts to avoid running out of memory. This is only a suggested improvement. The current program uses the two loops required by the assignment.
