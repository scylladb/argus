# Argus API

To use argus API the user first should generate an API token. To do so, proceed to the Profile Page inside the application and locate the button to generate the token. WARNING: The token will be shown only once, so be sure to save it after copying. For each API call, the token should be provided as part of Authorization header, example:

```sh
curl --request GET \
 --url https://argus.scylladb.com/api/v1/client/driver_matrix/test_report?buildId=example/driver-matrix/test \
 --header "Authorization: token YourTokenHere"
```

## Current endpoints

```http
GET /api/v1/client/driver_matrix/test_report
```

Accepts following parameters:

| Parameter | Type | Description |
| --------- | ---- | ------------|
| buildId          | string     | build id of the test to query            |

```json
{
  "response": {
    "build_id": "example/driver-matrix/test", 
    "release": "xxxxxxxx", 
    "test": "testing-driver-matrix", 
    "versions": {
      "datastax": [
        "pytest.datastax.v3.3.24.0", 
        "pytest.datastax.v3.3.25.0", 
        "pytest.datastax.v4.3.24.0", 
        "pytest.datastax.v4.3.25.0"
      ], 
      "scylla": [
        "pytest.scylla.v3.3.24.8", 
        "pytest.scylla.v3.3.25.5", 
        "pytest.scylla.v4.3.24.8", 
        "pytest.scylla.v4.3.25.5"
      ]
    }
  }, 
  "status": "ok"
}
```
