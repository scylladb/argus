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


```http
GET /api/v1/run_configs/param_names
```

Searches the catalogue of flattened run configuration parameter names. SCT's
keys arrive prefixed with the config name, as in `sct_config.unified_package`.

| Parameter | Type | Description |
| --------- | ---- | ------------|
| query     | string  | case-insensitive substring; omit it to list from the start |
| limit     | integer | 1 to 100, default 100 |

```json
{
  "status": "ok",
  "response": [
    "sct_config.unified_package",
    "sct_config.backend"
  ]
}
```

```http
GET /api/v1/run_configs/param_values
```

Lists the distinct values a single parameter has taken.

| Parameter | Type | Description |
| --------- | ---- | ------------|
| name      | string  | required, the parameter name |
| query     | string  | case-sensitive **prefix** of the value |
| limit     | integer | 1 to 100, default 100 |

```json
{
  "status": "ok",
  "response": [
    "aws",
    "gce"
  ]
}
```

Both endpoints back the config parameter filter of the Test Dashboard view
widget (ARGUS-157).



```http
POST /api/v1/client/testrun/{run_id}/cost/estimated
```

Sets the estimated cost of a run. The producer computes the amount; Argus
stores it. Repeating the call replaces the stored estimate.

Accepts following payload:

Type: application/json

| Parameter | Type | Description |
| --------- | ---- | ------------|
| value          | number     | Estimated cost of the run in USD. Zero or more, and finite            |

```json
{
  "response": {
    "run_id": "b0a0e5ba-bd37-4f4e-bd1c-b4e0d4f80a1e",
    "estimated_cost": 118.4
  },
  "status": "ok"
}
```

```http
POST /api/v1/client/testrun/{run_id}/cost/items
```

Submits the final cost of one or more named resources. Argus sums every item
of the run into the run's actual cost. Send an item as soon as its price is
known, and send nothing for a resource whose price is unknown, because a zero
is stored as a real figure. An item is keyed by its name, so repeating a name
replaces that item. One call is applied as a single batch, so either every item
of it lands or none does.

Accepts following payload:

Type: application/json

| Parameter | Type | Description |
| --------- | ---- | ------------|
| items          | object[]     | The cost items. Names must be unique within one payload            |
| items[].name          | string     | Resource name, not empty            |
| items[].category          | string     | Free-form category, such as `db_node` or `loader`            |
| items[].cost          | number     | Final cost of the resource in USD. Zero or more, and finite            |
| items[].pricing_tier          | string, optional     | Pricing tier, such as `spot`            |
| items[].leaked          | boolean, optional     | Marks a resource found after the run ended. Defaults to false            |

Example payload:

```json
{
  "items": [
    {"name": "longevity-db-node-1", "category": "db_node", "cost": 12.30, "pricing_tier": "spot"},
    {"name": "longevity-loader-1", "category": "loader", "cost": 3.70}
  ]
}
```

```json
{
  "response": {
    "run_id": "b0a0e5ba-bd37-4f4e-bd1c-b4e0d4f80a1e",
    "submitted": 2,
    "actual_cost": 16.0
  },
  "status": "ok"
}
```

```http
GET /api/v1/cost/run/{run_id}
```

Reads the cost of one run. A figure that was never reported is `null`, never
zero. Items are sorted by category, then by name.

```json
{
  "response": {
    "estimated_cost": 118.4,
    "actual_cost": 16.0,
    "items": [
      {"name": "longevity-db-node-1", "category": "db_node", "cost": 12.3,
       "pricing_tier": "spot", "leaked": false},
      {"name": "longevity-loader-1", "category": "loader", "cost": 3.7,
       "pricing_tier": null, "leaked": false}
    ],
    "by_category": {
      "db_node": 12.3,
      "loader": 3.7
    }
  },
  "status": "ok"
}
```

```http
GET /api/v1/health/summary
```

Reads the health of the Argus dependencies from the health process. `status`
is `healthy`, `degraded`, `unhealthy` or `unknown`. It reads `unknown` when the
health process does not answer. `failing` lists the name, the severity and the
status of each check that is not healthy. A check that has not finished its
first run is left out of `failing` and out of `status`. `enabled` is `false`
when `HEALTH_ENABLED` is off.

```json
{
  "response": {
    "enabled": true,
    "status": "degraded",
    "failing": [
      {"name": "jira_api", "severity": "important", "status": "unhealthy"}
    ]
  },
  "status": "ok"
}
```

```http
GET /api/v1/issues/{key}/links
```

Lists the test runs linked to an issue, together with the issue itself. Argus
finds the tracker from the key, and `issue.subtype` names it; only Jira is
supported today. Links are sorted by run start time, newest first. The issue fields come from the
copy Argus keeps, which a periodic job syncs with Jira, so the state can lag
Jira by one sync. Ignore fields you do not use: new ones may appear.

| Parameter | Type | Description |
| --------- | ---- | ------------|
| key          | string     | Jira issue key, such as `SCT-1234`. Case does not matter. A value that is not an issue key returns `"status": "error"`            |

```sh
curl --request GET \
 --url https://argus.scylladb.com/api/v1/issues/SCT-1234/links \
 --header "Authorization: token YourTokenHere"
```

```json
{
  "response": {
    "issue": {
      "id": "6f0c2a8e-1d3b-4c7a-9e51-0b6f2d4c8a19",
      "user_id": "1d2e3f40-5a6b-4c7d-8e9f-0a1b2c3d4e5f",
      "key": "SCT-1234",
      "summary": "Nemesis fails to restart node",
      "state": "in progress",
      "project": "SCT",
      "permalink": "https://scylladb.atlassian.net/browse/SCT-1234",
      "labels": [{"id": 2915093381, "name": "triage", "color": "000", "description": ""}],
      "assignees": ["someone@scylladb.com"],
      "added_on": "2026-09-14T08:21:05.112Z",
      "subtype": "jira"
    },
    "links": [
      {
        "run_id": "a7b1c2d3-e4f5-4a6b-8c7d-9e0f1a2b3c4d",
        "test_id": "93c4d5e6-f7a8-4b9c-8d0e-1f2a3b4c5d6e",
        "test_name": "longevity-100gb-4h",
        "plugin_name": "scylla-cluster-tests",
        "status": "failed",
        "start_time": "2026-09-30T22:10:44.000Z",
        "build_id": "scylla-master/longevity/longevity-100gb-4h",
        "build_number": 412,
        "scylla_version": "2026.2.0~dev",
        "product_version": "2026.2.0~dev",
        "linked_on": "2026-10-01T07:02:13.540Z",
        "url": "https://argus.scylladb.com/test/scylla-master/longevity/longevity-100gb-4h/412"
      }
    ]
  },
  "status": "ok"
}
```

A key that Argus does not know is not an error:

```json
{
  "response": {
    "issue": null,
    "links": []
  },
  "status": "ok"
}
```

`linked_on` is `null` for links made before Argus recorded the time.

```http
POST /api/v1/client/replay/ingest
Content-Type: application/x-tar-zstd
```

Applies the requests that an Argus client recorded in replay logs
(`argus_replay_log_*.jsonl`). The body is an archive of those logs: `tar.zst`,
`tar.gz`, plain `tar` or `zip`. The server sorts the records, applies them
through the client API with the token of the caller, and returns a summary.
It skips the calls that send mail or start CI jobs.

| Parameter | Type | Default | Description |
| --------- | ---- | ------- | ----------- |
| dry_run | bool | `false` | Check the archive and the test entities. Apply nothing. |
| build_id | string | see below | Replay into a new run under this build path, such as `scylla-staging/jdoe/my-run`. Each run in the archive gets a new run ID, and `submit_run` gets the path as its job name. Each replay makes a new run. End the path with `#<n>` to choose the build number of the first run. |
| resume_run_id | uuid | none | Needs a build path, given or default. Write into this run in place of a new one, to finish a replay that failed. The archive must hold one run, and this run must be its copy under the same `build_id`. |
| as_me | bool | `true` with a build path, else `false` | With a build path, make the caller the starter and the assignee of each new run. Without one, make the caller the assignee of each run, and write the change to the run events. The run keeps its recorded starter. |
| create_missing_tests | bool | `true` for the `local-runs` default, else `false` | Create the group and the test that the build path names when they do not exist, and the release for the `local-runs` default. When `false`, a `submit_run` for a missing test fails with a message that names the missing parts. |
| backfill_logs | bool | `true` | List the S3 prefix of each run and attach the log archives that the logs do not record. |
| local_runs | bool | `false` | Send an archive of one local run to `local-runs/<caller username>/<job>` when `build_id` is absent. The CLI sends `true` unless the user gives `--keep-run`. |

With `local_runs` and without `build_id`, an archive of one local run, a
`submit_run` with no build URL, goes to `local-runs/<caller username>/<job>`. `<job>` is the first SCT
config file of the run without its directory and extension. Any other archive
keeps its recorded paths and run IDs. "A build path" in the table above means
`build_id` or this default.

`build_id` is two or more names split by `/`, with an optional `#<n>` at the
end. A name is not empty and holds no whitespace. `n` is a positive integer
that no run under the path has. Without `#<n>`, each new run takes the next
number above the highest build number under the path. A resumed run keeps its
build number. The first name is the release and the last name is the test.
The names between them make the group. The server reserves each build number
before it creates the run, so two replays into one path take two numbers. A
resume skips the `submit_run` record of the archive. A number that a failed
replay reserved, and that no run holds, is free again after ten minutes. An
explicit `build_id` must name a release that exists. Only the `local-runs`
default creates its release. The build URL of a new run is its own Argus
link, `<BASE_URL>/test/<path>/<n>/`, or `/test/<path>/<n>/` when `BASE_URL`
is not configured. A bad `build_id` or `resume_run_id` fails the request
before the server applies a record. A recorded S3 link
keeps the original run ID, because the log archive stays where the original
run uploaded it.

A run that a replay into a build path made stores the recorded run ID in
`source_run_id`. The run endpoints return the field, and the run page links
to the original run.

`runs` lists each run in the archive once. `id` is the run ID in Argus after
the replay. `source_id` is the run ID in the log. The two are equal without
a build path. `build_id` and `build_number` name the build of a new run, and are
`null` without a build path. A dry run returns the build each run would get.
An error with the endpoint `stamp_run` is a run that the server could not
stamp with its source run or its new owner.

```json
{
  "response": {
    "total": 83,
    "processed": 83,
    "succeeded": 83,
    "failed": 0,
    "skipped_no_replay": 0,
    "backfilled_logs": 2,
    "errors": [],
    "runs": [
      {"type": "scylla-cluster-tests",
       "id": "7f3e2a6c-5b1d-4c8e-9a0f-2d4b6c8e0a1f",
       "source_id": "91c226dc-a057-4ad4-a0b8-bf8bc73031b9",
       "build_id": "scylla-staging/jdoe/my-run",
       "build_number": 1}
    ]
  },
  "status": "ok"
}
```

## Email reporting API

```http
POST /api/v1/client/testrun/report/email
```

### Payload

|Key|Type|Description|
|---|----|-----------|
|recepients|array of string| List of email report recepients |
|title|string| Title of the email. Use `#auto` for automatically generated title |
|run_id|string| UUID of the run to report |
|attachments| Attachment[] | list of attachments to send |
|sections | mixed(string, Section)[] | list of mixed strings of section names or Section object |

#### Attachment

|Field|Type|Description|
|-----|----|-----------|
|filename|string| Filename of the attachment |
|data|string| Base64 encoded payload |

#### Section

|Field|Type|Description|
|-----|----|-----------|
|type|string| Section type [Required]|
|options| Options | Options object with supported option keys |

Supported sections are:

| Name|Description|
|-----|-----------|
| header| Topmost header of the email. Contains the link to the Argus run and a status icon |
| main| Info block similar to the Info tab on the Argus run page. Contains info about the run such as runtime, used scylla version and sct branch and others. |
| packages| Table with package name and version information |
| logs| List of links to the log files stored on S3 for this run |
| cloud| Contains active remaining resources running at the end the test. Table |
| nemesis| Table of nemeses in the run with their status and durations |
| generic_results| Generic Result API results, formatted as tables |
| events| Event block of most recent events sorted by timestamp |
| screenshots| Grafana screenshot gallery |
| custom_table| Custom table element. Can be used to display arbitrary tables. HTML in cells is **not** supported |
| custom_html| Arbitrary HTML |

If a section is unrecognized, it will be rendered as a special "Unsupported" section which will print all the options sent to that section.

If a section is passed but data for it in Argus is empty, the section won't be rendered. Some sections are always attempted to be rendered.

The `section` block can be provided as empty array to use the default template.

##### Section options

###### Events

|Option|Type|Description|
|------|----|-----------|
|amount_per_severity| number | Amount of events per severity to display (default 10)|
|severity_filter| string[] | Names of severities to include in the email (default [CRITICAL, ERROR]). Available severities: CRITICAL, ERROR, WARNING, NORMAL, DEBUG  (case-sensitive)|

###### Generic Results

|Option|Type|Description|
|------|----|-----------|
|table_filter| string[] | Array of regexes to filter tables by. Default: [] - all tables will be shown|
|section_name| string | Heading value for the results tables|

###### Nemesis

|Option|Type|Description|
|------|----|-----------|
|sort_order| tuple of key of NemesisRunInfo, direction | Default (start_time, desc). Direction can be: asc, desc. `NemesisRunInfo` can be viewed [here](https://github.com/scylladb/argus/blob/master/argus/backend/plugins/sct/udt.py#L78) |
|status_filter| string[] | Names of nemesis status to include in the email (default [failed, succeeded]). Available statuses: started, running, failed, skipped, succeeded, terminated (case-sensitive)|

###### Custom Table

|Option|Type|Description|
|------|----|-----------|
|table_name| string | Table title|
|headers| any[] | Table header columns (Required) |
|rows| any[][] | Array of table cell arrays. |

###### Custom HTML

|Option|Type|Description|
|------|----|-----------|
|section_name| string | Section Title |
|html| string | Section HTML Content |

Example:

```json
{
  "section_name": "Additional Info",
  "html": "<h1 title='lorem' style='background-color: red'>loremLorem, ipsum dolor.</h1><p>Lorem ipsum dolor sit amet consectetur adipisicing elit. Nisi maiores, eius nemo veritatis dolorem blanditiis nam magni dicta laborum iste!</p>"
}
```


### Example payload

```json
{
    "recepients": [
        "john.smith@scylladb.com"
    ],
    "run_id": "17351a94-3aba-41de-aba5-cda123dff0bb",
    "title": "#auto",
    "attachments": [
    ],
    "sections": [
        "header",
        "main",
        "packages",
        "screenshots",
        "cloud",
        {
            "type": "events",
            "options": {
                "amount_per_severity": 10,
                "severity_filter": [
                    "CRITICAL",
                    "ERROR"
                ]
            }
        },
        {
            "type": "nemesis",
            "options": {
                "sort_order": [
                    "start_time",
                    "desc"
                ],
                "status_filter": [
                    "failed",
                    "succeeded"
                ]
            }
        },
        "logs",
        {
            "type": "custom_table",
            "options": {
                "table_name": "My Table",
                "headers": ["hello", "one", "two"],
                "rows": [
                    [1,2,3],
                    ["four", "five", "six"]
                ]
            }
        }
    ]
}

```

### Response

```json
{
  "response": true,
  "status": "ok"
}
```
