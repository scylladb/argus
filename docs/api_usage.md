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
GET /api/v1/planning/search
```

Searches releases, groups and tests by name. Each server worker answers from
an index it keeps in memory and rebuilds once it is 60 seconds old, so a new
release, group or test can take up to a minute to appear, and two requests may
see indexes of different ages.

| Parameter | Type | Description |
| --------- | ---- | ------------|
| query          | string     | The search query. The syntax follows this table. An empty query returns no hits            |
| releaseId          | uuid     | Optional. Returns only the groups and tests of this release            |
| limit          | integer     | Optional, at least 1. Returns one page of at most `limit` hits and leaves out the "Add all..." row            |
| offset          | integer     | Optional, default 0. The number of hits to skip before the page starts            |

The query is a list of words separated by spaces. Every word must match.

| Token | Matches |
| ----- | ------- |
| `longevity` | Names, pretty names and build ids that contain the text, in any case |
| `"cluster - tier1"` | The quoted text, spaces included |
| `release:2026.1`, `group:longevity` | Entities whose release or group name contains the value. Quote a value that holds spaces. Repeating a key matches any of its values |
| `type:test` | `release`, `group` or `test` |
| `status:fail`, `istatus:not` | Tests whose latest status, or latest investigation status, starts with the value, as the release stats show them: `status:fail` finds `failed`, `istatus:not` finds `not_investigated` |
| `assignee:alice` | Tests whose latest run is assigned to a user whose username or full name contains the value |

`status:`, `istatus:` and `assignee:` read the stats of one release: the one in
`releaseId`, or the one a `release:` value names exactly. Without one release
such a query matches nothing. With one, only tests match.
| `-azure`, `-release:2025.1` | Leaves out what the word or the facet matches |
| `https://jenkins.example.com/job/a/job/b/` | The test whose build id is `a/b` |
| A UUID | That release, group, test or run |
| `issue:SCT-1234` | The runs linked to that Jira issue, newest first, across releases: it ignores `releaseId` |
| `config:backend=aws` | Runs whose recorded config parameter has that value. `backend` stands for the one parameter whose name ends in `.backend`. Repeating a name matches any of its values; different names must all match. `config:backend` alone asks for the parameter to be set, and needs `issue:` beside it |

Hits come ranked: an exact name match first, then a name that starts with the
first word, then a word inside the name. Within each rank, releases come before
groups and groups before tests, and a release with a higher priority comes
first. `total` counts every match, so a client asks for the next page while
`offset + hits` is below it.

```sh
curl --request GET \
 --url 'https://argus.scylladb.com/api/v1/planning/search?query=longevity-50gb&limit=30' \
 --header "Authorization: token YourTokenHere"
```

```json
{
  "response": {
    "total": 14,
    "hits": [
      {
        "id": "3f1c9a52-7d4e-4b8a-9c21-5e6f7a8b9c0d",
        "type": "test",
        "name": "longevity-50gb-3days-test",
        "pretty_name": null,
        "build_system_id": "scylla-master/longevity/longevity-50gb-3days-test",
        "enabled": true,
        "test_metadata": {},
        "release_id": "5316e591-6a68-4814-b736-e294710d11e4",
        "group_id": "b197bc8c-71ce-4832-910f-f6daf47857b0",
        "release": {
          "id": "5316e591-6a68-4814-b736-e294710d11e4",
          "name": "scylla-master",
          "pretty_name": null,
          "enabled": true,
          "priority": 10,
          "dormant": false
        },
        "group": {
          "id": "b197bc8c-71ce-4832-910f-f6daf47857b0",
          "name": "longevity",
          "pretty_name": "Cluster - Longevity Tests",
          "enabled": true
        }
      }
    ]
  },
  "status": "ok"
}
```

`issue:` and `config:` return runs instead of releases, groups and tests, and
the rest of the query narrows those runs: words and `release:`, `group:` match
the run's test, `status:`, `istatus:` and `assignee:` match the run itself,
and `type:run` keeps them. With `issue:`, `config:` narrows the issue's runs.
Without `issue:`, `config:` inside one release (`releaseId`, or a `release:`
value that names exactly one) looks at the last five runs of each test, as
the release stats keep them; without a release it reads at most 500 runs of
the value, newest first among those.

An `issue:` or `config:` query returns run hits named `<test name>#<build number>` with
their `status`, `start_time`, `build_number`, `test_id` and the `test`, `group`
and `release` objects. An unknown key, or text that is not a Jira key, returns
no hits.

A release hit has `null` for `release_id`, `group_id`, `release` and `group`.
A group hit has `null` for `group_id` and `group`. A run hit, from a UUID query,
carries the run fields with `test`, `group` and `release` objects.

```http
GET /api/v1/release/stats/summary
```

Returns the status counts of a release, of each of its groups and of each
test, without the run details that `/api/v1/release/stats/v2` returns. It reads
the same stored snapshot as the release dashboard.

| Parameter | Type | Description |
| --------- | ---- | ------------|
| release          | string     | Release name            |
| force          | boolean     | Optional, default false. Recomputes the stats and stores a new snapshot            |

```json
{
  "response": {
    "total": 20,
    "created": 0,
    "running": 1,
    "failed": 3,
    "test_error": 0,
    "error": 0,
    "passed": 12,
    "aborted": 0,
    "not_planned": 0,
    "not_run": 4,
    "to_investigate": 2,
    "groups": {
      "b197bc8c-71ce-4832-910f-f6daf47857b0": {
        "total": 5,
        "failed": 1,
        "passed": 4,
        "to_investigate": 1,
        "tests": {
          "3f1c9a52-7d4e-4b8a-9c21-5e6f7a8b9c0d": {
            "status": "failed",
            "investigation_status": "not_investigated",
            "start_time": "2026-10-01T10:00:00.000Z"
          }
        }
      }
    }
  },
  "status": "ok"
}
```

A group carries every status count, as the release does; the example shortens
them. `to_investigate` counts the failed, test error and error tests nobody has
investigated. `start_time` is `null` for a test that never ran. A dormant
release answers `{"dormant": true}` unless it has a stored snapshot.

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
