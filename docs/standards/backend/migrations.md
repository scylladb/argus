## Schema and Data Changes

### Models Are the Schema
`uv run python -m argus.backend.cli sync-models` applies the models in
`argus/backend/models/` and the plugin declarations to the keyspace. There is
no migration file for a schema change. The model is the definition.

### Additive First
Add a column. ScyllaDB fills it with NULL for the existing rows, so the reading
code must handle the missing value. A rename and a type change are not
additive, so they arrive as a new versioned table.

### A New Table for a Breaking Change
When a read cannot survive the change, create the next versioned table, as in
`_v1` to `_v2`. Write to the new table, backfill, then move the read. Remove
the old table in a later change.

### Data Jobs Are Scripts
A one-off data change lives in `scripts/migration/` as a dated script. A
developer runs it by hand. Name it for what it does.

### Small and Focused
Keep one logical change per script. Keep a schema change and a data change
apart, so a rollback stays simple.

### Zero Downtime
Four workers serve the application during the change. The old code and the new
code both read the table for the length of the deployment, so every step must
work for both.

### Version Control
Commit the script. Never edit a script that already ran in production.
