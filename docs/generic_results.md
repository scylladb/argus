# Generic results

Generic results is Argus feature that allows receiving and storing arbitrary table data from tests.
Generic Result in terms of Argus is a table with columns and rows (like a spreadsheet). Each result has a name, description and belongs to
given test (Jenkins job).
Results are displayed in Argus UI in `Results` tab for given run and on graphs accessed by clicking a graph button next to run list in given
test.

## How it works

Generic results are stored in 2 tables: `ArgusGenericResultMetadata` `ArgusGenericResultData`.

### ArgusGenericResultMetadata

This table stores information what results are available for given `test_id` (Jenkins job in terms of Argus). Contain information about each
result: name, description, columns, and rows.
Columns are described by set of attributes: `name`, `unit`, `type` and `higher_is_better`. `type` can be one of `ResultType` enum values (FLOAT, INTEGER,DURATION, TEXT). `higher_is_better` is used for finding best value for given cell across all runs in given test.
Besides Columns metadata, user might supply also `validation_rules` which are used to validate data before storing it in Argus. `ValidationRules` are defined by map between column name and `ValidationRule` object that defines 3 fields:
- `best_pct` - defines max value limit relative to best result in percent unit
- `best_abs` - defines max value limit relative to best result in absolute unit
- `fixed_limit` - defines fixed value limit above/below which result is considered as ERROR

`TEXT` type columns are not validated.
### ArgusGenericResultData

This table stores actual data for each result. Each row in this table is a cell in the result table. Its location is defined by `column` and
`row` fields.
Besides the value, each cell contains information about value status (PASS, WARNING, ERROR, UNSET) and `sut_timestamp` which corresponds to
SUT version (for SCT test, by default is calculated from binaries build date for ScyllaDB). SUT version is not shown in the result table,
but it is used for
sorting purposes (needed when graphing results in time - time refers to SUT version).
Value status is used to color the cell in Argus UI (green for PASS, yellow for WARNING, red for ERROR, UNSET for no color at all).

## Sending generic results

Generic results are stored in Argus database and can be accessed via Argus API and displayed in Argus UI in `Results` tab for given run.

To send generic results to Argus, you need to create `ResultTable` class basing on `GenericResultTable` available in Argus Client library
and send it using `ArgusClient` class (or it's child class like `ArgusSCTClient`).

Child class of `GenericResultTable` needs to define `Meta` class with `name` and `description` fields. It also needs to define `Columns`
field that will describe available columns details for given result: as a list of `ColumnMetadata` objects. Each `ColumnMetadata` object
needs to have `name`, `unit` and `type` and optionally `higher_is_better` fields. `type` field can be one of `ResultType` enum values.
In order to make Argus validate results against fixed limit or relatively to best result, one can define `validation_rules` map field in `Meta`. Also for validation to happen, set result status to `UNSET` (default value) when adding result to table and each validated column must have `higher_is_better` field specified.

See example:

```python
from uuid import UUID

from argus.client.sct.client import ArgusSCTClient
from argus.client.generic_result import GenericResultTable, ColumnMetadata, ResultType, Status, ValidationRule


class LatencyResultTable(GenericResultTable):
    class Meta:
        name = "Write Latency"
        description = "Latency for write operations"
        Columns = [ColumnMetadata(name="latency", unit="ms", type=ResultType.FLOAT, higher_is_better=False),
                   ColumnMetadata(name="op_rate", unit="ops", type=ResultType.INTEGER, higher_is_better=True),
                   ColumnMetadata(name="duration", unit="HH:MM:SS", type=ResultType.DURATION, higher_is_better=False),
                   ColumnMetadata(name="overview", unit="ms", type=ResultType.TEXT),
                   ]
        ValidationRules = {"write": ValidationRule(best_abs=10), # 10ms margin from best
                           "read": ValidationRule(best_pct=50, best_abs=5), # 50% and 5ms margin from best
                           "duration": ValidationRule(best_abs=600)  # 10 minutes margin from best
                           }


result_table = LatencyResultTable()

result_table.add_result(column="latency", row="mean", value=1.1, status=Status.ERROR)
result_table.add_result(column="op_rate", row="mean", value=59988, status=Status.PASS)
result_table.add_result(column="latency", row="p99", value=2.7, status=Status.UNSET)
result_table.add_result(column="op_rate", row="p99", value=59988, status=Status.UNSET)
result_table.add_result(column="duration", row="p99", value=8888, status=Status.UNSET)
result_table.add_result(column="duration", row="mean", value=332, status=Status.UNSET)
result_table.add_result(column="overview", row="p99", value="<link_to_screenshot>", status=Status.UNSET)
result_table.add_result(column="overview", row="mean", value="<link_to_screenshot>", status=Status.UNSET)

# when testing locally, otherwise just use ArgusClient instance in your test.
run_id = UUID("24e09748-bba4-47fd-a615-bf7ea2c425eb")
client = ArgusSCTClient(run_id, auth_token="<token>",
                        base_url="http://localhost:5000")
client.submit_results(result_table)
```

If using different SUT than ScyllaDB (or need to adjust dynamically) you can set `sut_timestamp` field in table constructor. `sut_timestamp`
should always correspond to SUT build timestamp. Like this:

```python
result_table = LatencyResultTable(sut_timestamp=1629302400)
```

This will assure proper sorting of results in Argus UI when comparing to different versions in time based graphs.

## TEXT results

TEXT type columns can be used to send additional information like links, screenshot links or simple text with emojis. When sending
links/screenshots, don't add any additional text to the cell, as it will be displayed as a link/button in Argus UI.
Text results are not displayed in graphs.

# Limitations

* automatic SUT timestamp supported only by SCT: it calculates based on the Scylla Version date and commit id (builds from the same date are
  not the same, but timestamp does not reflect which one was earlier).
