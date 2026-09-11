## Validation

### The Database Enforces Nothing
ScyllaDB gives no unique constraint, no foreign key and no NOT NULL beyond the
type. Every rule lives in the application. A write that skips the check
corrupts the data silently.

### Validate at the Boundary
Declare a request body as a Pydantic model in the router, so a type error stops
before the service. Keep the business rule in the service.

### Server-Side Always
Validate on the server. A client-side check gives feedback only. Repeat every
check on the server.

### Validate Early
Reject a bad payload before the first write. A partial write leaves rows that
no code path cleans up.

### Uniqueness
Read through the secondary index first, then write. Treat a duplicate as
possible, because two writers can pass the same read.

### Reference Checks
A row carries the identifiers of its release, group and test. Confirm each one
exists before the write. Nothing else will.

### Specific Errors
Name the field and the reason. `DataValidationError` carries the message to the
client.

### Allowlists Over Blocklists
State what is allowed. A list of what is rejected always misses a case.

### Sanitize Input
The templates run in an unescaped environment, and `rendering.py` escapes only
bare markup extensions. Escape user content before it reaches a template.

### Consistent Enforcement
Apply the same rule at every entry point: the REST API, the client library
submission, the CLI and the maintenance command.
