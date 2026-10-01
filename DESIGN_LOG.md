My design log

This log covers problems found in the Python code and changes I asked for. I used AI to help write, check, and fix the code.

Revision 1: Saving results in the wrong place

The first Python timing code from AI chose where to save results based on where the command was started. A review showed that this could save results in the wrong place and overwrite another results file. The code was changed to use the Python project's measurements location by default. A test checked the save location without writing over any results.

Revision 2: Incorrect report text

The first Python report code from AI assumed that each row would have one join match. Reviewing the code against the test settings showed that this was wrong when the match rate changed. For example, with four rows in each table and two matches per row, the join returns eight rows. The report needed to use the saved settings and actual results.

The same review found that the report also assumed projection would not remove any rows. That is wrong when values repeat in the selected column. A small check with b values 0, 1, 0, 1 confirmed that project[b](R) returns only two rows. The query code handled this correctly; the report wording was the problem.

Both statements were fixed to use the saved results. The automatic report writer was later removed when I asked to simplify the project.

Revision 3: Code that was hard to follow

Some of the Python code from AI used short one-line functions and extra calculations to group rows before checking for duplicates. I wanted code that was easier to understand and explain, so I asked for clearer names and smaller steps. The revised code used named functions and simpler row grouping, while keeping its own check for duplicate rows.

All 54 tests passed after these changes. The timing study was repeated so the report would match the revised code. The join with 64,000 rows in each table took about 350.63 seconds and counted 4,096,000,000 pairs. The million-row join was only estimated, as required.
