# ARGUS-261 — Show who started each run in the Cost Explorer

## Problem

The Cost Explorer's "Top runs by cost" table lists the test, release, backend, status, start
time, duration, cost and coverage of each run, but not who launched it. To find out who is
behind an expensive run, a user has to open every run page one by one.

## Who it affects

Anyone reviewing cloud spend in the Cost Explorer: QA leads and managers who need to follow up
with the person who launched a costly, leaked or errored run. Runs from SCT and Generic
sources carry a `started_by` value; runs from other sources do not.

## Evidence

Jira ARGUS-261: "Fairly self-explanatory, add started-by field column to the cost dashboard to
see users launching jobs there."

## What good looks like

Every row of "Top runs by cost" shows the user who started the run, when the run recorded
one, and an explicit empty marker when it did not. The column sorts like the others.

## Out of scope

- Filtering or breaking down spend by user.
- The Views costs widget: it shows stat tiles and spend over time, no run table.
- The per-run Costs tab.
- Recording `started_by` for sources that do not send it today.
