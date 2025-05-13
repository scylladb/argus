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

```http
POST /api/v1/planning/plan/trigger
```

Accepts following payload:

Type: application/json

| Parameter | Type | Description |
| --------- | ---- | ------------|
| release          | string     | Release name to trigger plans in (can be mixed vith version to narrow filter)            |
| plan_id          | string     | Specific plan id to trigger            |
| version          | string     | Target scylla version of plans to trigger             |
| common_params          | object{ param_name: value }     | Common parameters, such as backend            |
| params          | object{ param_name: value }[]     | specific job parameters            |

Example payload:

```json
{
  {
  "version": "2024.3.1~rc0",
  "release": "scylla-master",
  "plan_id": "some-plan-uuid",
  "common_params": {
      "instance_provision": "spot",
  },
  "params": [
      {
          "test": "longevity",
          "backend": "aws",
          "region": "eu-west-1",
          "scylla_ami_id": "ami-abcd"
      },
      {
          "test": "longevity",
          "backend": "azure",
          "region": "us-east1",
          "azure_image_id": "/subscriptions…",
      }
  ]
  }

}
```

```json
{
  "response": {
    "jobs": [
      "http://jenkins/path/job/one/1",
      "http://jenkins/path/job/two/3",
      "http://jenkins/path/job/three/5",
      "http://jenkins/path/job/four/9"
    ],
    "failed_to_execute": [
      "path/job/one",
      "path/job/two",
      "path/job/three",
      "path/job/four"
    ]
  },
  "status": "ok"
}
```

Additionally, this endpoint is available inside `argus-client-generic` executable, as follows:

```bash
argus-client-generic trigger-jobs --api-key $key --version $version --plan_id $id --release $release --job-info-file $file_path
```

`--job-info-file` is a .json file containing `common_params` and `params` parts of the payload, everything else is specified on the command line.
