## API Design

### Layers
A request passes through three layers. A router in
`argus/backend/controller/` parses and authorizes it. A service in
`argus/backend/service/` holds the logic. A document model in
`argus/backend/models/` reads and writes ScyllaDB.

A router holds no business logic. A service holds no request object.

### Routers
Declare one `APIRouter` per feature module with an explicit prefix.

```python
router = APIRouter(prefix="/planning")

@router.get("/release/{release_id}/gridview", name="api.planning_api.grid_view_for_release")
def grid_view_for_release(release_id: UUID, user: User = Depends(api_current_user)):
    ...
```

Name every route `api.<module>.<function>`. The templates and the redirect
handlers resolve a route by that name.

### Authentication
An API route takes `user: User = Depends(api_current_user)`. A route without
that dependency is public. Add it to every new API route.

### Response Shape
Return `APIResponse` with a `status` key and a `response` key.

```python
return APIResponse({"status": "ok", "response": result})
```

`APIResponse` applies the project JSON encoder, which handles the UUID, the
datetime and the model types.

### Request Bodies
Declare a request body as a Pydantic `BaseModel` in the router module. Keep the
field names the frontend sends, even when they are camelCase.

### Errors
Raise `APIException` for a failed API call and `DataValidationError` for a bad
payload. `argus_backend.py` registers the handler that turns each one into the
JSON error contract. Raise `UIRedirect` from a UI dependency instead.

Do not return an error dictionary from a service. Raise.

### Status Codes
The application answers an API failure inside an HTTP 200 envelope. Match that
contract, because the clients, the frontend and the tests all read it.

| Case | Status | Body |
|---|---|---|
| Success | 200 | `{"status": "ok", "response": ...}` |
| `APIException`, `DataValidationError`, a request validation error, an unhandled exception | 200 | `{"status": "error", "response": {...}}` |
| `AuthorizationError` | 403 | `{"status": "error", "message": ...}` |

`argus_backend.py` registers `api_exception_handler` for `APIException`, for
`RequestValidationError` and for `Exception`, and that handler always sets
status 200. A route that returns 404 by itself breaks the contract the clients
read. Raise instead.

`argus/backend/tests/integration/test_error_contract.py` asserts this contract
end to end. Match it until it changes.

An HTTP 200 on a server error hides the failure from a client, from a retry and
from the request metrics. ARGUS-227 tracks that defect.

### No Public Schema
`create_app()` sets `openapi_url=None`, so the OpenAPI schema is off. Document
a new endpoint in `docs/api_usage.md`.

### Naming
Use a plural noun for a collection and a path parameter for one member. Keep
nesting to three levels at most. Use a query parameter for a filter, a sort or
a page.
