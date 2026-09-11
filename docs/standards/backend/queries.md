## Database Queries

### Read Through the Mapper
Query through the model. `find()` takes the key equality filters, and `all()`
or `first()` runs the query.

```python
plans = list(ArgusReleasePlan.find(release_id=release.id).allow_filtering().all())
```

Never build CQL from user input by string formatting.

### Design the Partition Key for the Read
A query that does not restrict the partition key scans the cluster. Decide the
read first, then the key. A new read that the current key cannot serve needs a
new table or a secondary index, not a scan.

### allow_filtering() Is a Cost
`allow_filtering()` lets ScyllaDB scan beyond the key. The current code uses it
for a bounded table, such as the release plans of one release. Do not add it to
a table that grows without a bound, such as the runs or the events.

State in the pull request why a new `allow_filtering()` call stays bounded.

### One Read per Screen
A row carries the identifiers a reader needs, so a read needs no second query
to resolve a reference. Fetch the rows of a view in one query per table.

### Avoid the Loop of Queries
A query inside a loop over rows multiplies the round trips. Read the set once
and join it in Python.

### Select What You Need
Restrict the columns when a row is wide. An event or a result row carries large
collections.

### Uniqueness
Read through the secondary index first, then write. The database enforces no
unique constraint, so two concurrent writers can both pass the read. Keep the
window small and treat a duplicate as possible.

### Precompute the Expensive Aggregate
A dashboard aggregate that several requests share belongs in a snapshot table,
as `ReleaseStatsSnapshot` does for the release statistics. Write the aggregate
once and read the row, rather than recomputing it per request.
