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
