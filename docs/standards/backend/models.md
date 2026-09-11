## Models

### Document Mapper
A model extends `coodie.sync.Document` and declares its fields as annotated
Pydantic types. A user-defined type extends `coodie.usertype.UserType`.

```python
class ArgusGenericResultMetadata(Document):
    test_id: Annotated[UUID, PrimaryKey()]
    name: Annotated[str, ClusteringKey()]
    columns_meta: list[ColumnMetadata] = Field(default_factory=list)

    class Settings:
        name = "generic_result_metadata_v1"
```

### Explicit Table Names
Every model sets `class Settings` with an explicit `name`. A schema change that
breaks a read arrives as a new versioned table, as in `_v1` to `_v2`.

### Keys Decide the Reads
Declare the keys with `PrimaryKey()`, `ClusteringKey()` and `Indexed()`. The
partition key decides which queries the table supports, so design it from the
read the feature needs. See `queries.md`.

### What ScyllaDB Does Not Give You
There are no joins, no foreign keys and no unique constraints. Three rules
follow.

- **Copy, do not reference.** A row carries the identifiers a reader needs. A
  run row carries its release, group and test identifiers directly.
- **Enforce uniqueness in the application.** Read through a secondary index
  first, then write.
- **Validate in the service.** The database enforces nothing beyond the type.

### Null Collections
The driver returns a NULL collection as `None`. A model that declares a
`default_factory` must drop the `None` values before it calls the parent
constructor, or the default never applies.

### Types
Annotate a text column that holds only ASCII with `Ascii()`. Annotate a float
with `Double()`. Wrap a collection of user-defined types in `Frozen()` when the
schema needs a frozen column.

### Timestamps
Store a created or updated timestamp as a timezone-aware `datetime` in UTC.

### Schema Changes
`uv run python -m argus.backend.cli sync-models` applies the models to the
keyspace. A plugin declares its run model and its user-defined types through
`PluginInfo`, and `sync-models` reads that declaration.

### Plugin Models
A test source keeps its models inside `argus/backend/plugins/<name>/`. The core
models stay free of source-specific fields.
