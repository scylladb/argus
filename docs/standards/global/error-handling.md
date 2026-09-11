## Error Handling

### Typed Exceptions
Raise a specific exception. `APIException` covers a failed API call, and
`DataValidationError` covers a bad payload. A service that needs its own class
defines `<Domain>Error`, as `UserServiceException` and `UserViewException` do.

Chain the cause with `raise ... from e` when you wrap a failure from Jira,
GitHub, Jenkins, S3 or the driver.

### No Blind Except
Never write a bare `except:` or `except Exception` without a re-raise. Ruff
selects the `BLE` rules, but `exclude = ["argus/"]` keeps them off the web
backend, so the review is the only gate there.

### Raise, Do Not Return
A service raises. It does not return an error dictionary. The handlers
registered in `argus_backend.py` turn an exception into the JSON error contract
or into a redirect.

### Handle at the Boundary
Catch at the router or the handler, not inside the logic. A `try` block around
a few lines that cannot fail hides the real failure.

### Fail Fast
Validate the input and check the precondition first. Reject a bad payload
before a write reaches ScyllaDB, because the database enforces nothing.

### Clear User Messages
State what the user can do. Never put a traceback, a host name or a credential
in a response.

### Graceful Degradation
A failure in Jira, GitHub, Jenkins or the AI worker must not fail a run view.
Show the run without the linked issue.

### Retry with Backoff
Use an exponential backoff for a transient failure from an external service.

### Resource Cleanup
Release a connection, a file handle and a container in a `finally` block or a
context manager.
