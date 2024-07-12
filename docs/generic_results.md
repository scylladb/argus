# Generic results
Generic results is Argus feature that allows receiving and storing arbitrary table data from tests. 
Generic Result in terms of Argus is a table with columns and rows (like a spreadsheet). Each result has a name, description and belongs to given test (Jenkins job).

## How it works
Generic results are stored in 2 tables: ArgusGenericResultMetadata ArgusGenericResultData.

### ArgusGenericResultMetadata
This table stores information what results are available for given `test_id` (Jenkins job). Contain information about each result: name, description, columns, and rows.

### ArgusGenericResultData
This table stores actual data for each result. Each row in this table is a cell in the result table. Its location is defined by `column` and `row` fields.
Besides the value, each cell contains information about value status (PASS, WARNING, ERROR) and `sut_timestamp` which corresponds to SUT version (e.g. calculated from binaries build date for ScyllaDB). SUT version is not shown in the result table, but it is used for sorting purposes (needed when graphing results in time - time refers to SUT version).

## Usage
Generic results are stored in Argus database and can be accessed via Argus API and displayed in Argus UI in `Results` tab for given run.

To send generic results to Argus, you need to create `ResultTable` class basing on `GenericResultTable` available in Argus Client library and send it using `ArgusClient` class (or it's child class like `ArgusSCTClient`). 

Child class of `GenericResultTable` needs to define `Meta` class with `name` and `description` fields. It also needs to define `Columns` field that will describe available columns details for given result: as a list of `ColumnMetadata` objects. Each `ColumnMetadata` object needs to have `name`, `unit` and `type` fields. `type` field can be one of `ResultType` enum values.

See example:

```python
from uuid import UUID

from argus.client.sct.client import ArgusSCTClient
from argus.client.generic_result import GenericResultTable, ColumnMetadata, ResultType, Status


class LatencyResultTable(GenericResultTable):
    class Meta:
        name = "Write Latency"
        description = "Latency for write operations"
        Columns = [ColumnMetadata(name="latency", unit="ms", type=ResultType.FLOAT),
                   ColumnMetadata(name="op_rate", unit="ops", type=ResultType.INTEGER),
                   ColumnMetadata(name="duration", unit="HH:MM:SS", type=ResultType.DURATION)]


result_table = LatencyResultTable()

result_table.add_result(column="latency", row="mean", value=1.1, status=Status.WARNING)
result_table.add_result(column="op_rate", row="mean", value=59988, status=Status.ERROR)
result_table.add_result(column="latency", row="p99", value=2.7, status=Status.PASS)
result_table.add_result(column="op_rate", row="p99", value=59988, status=Status.WARNING)
result_table.add_result(column="duration", row="p99", value=8888, status=Status.ERROR)
result_table.add_result(column="duration", row="mean", value=332, status=Status.PASS)

# when testing locally, otherwise just use ArgusClient instance in your test.
run_id = UUID("24e09748-bba4-47fd-a615-bf7ea2c425eb")
client = ArgusSCTClient(run_id, auth_token="<token>",
                        base_url="http://localhost:5000")
client.submit_results(result_table)
```

If using different SUT than ScyllaDB (or need to adjust dynamically) you can set `sut_timestamp` field in table constructor. `sut_timestamp` should always correspond to SUT build timestamp. Like this:
```python
result_table = LatencyResultTable(sut_timestamp=1629302400)
```
This will assure proper sorting of results in Argus UI when comparing to different versions in time based graphs.

# Limitations
* Only 3 types of values are supported: FLOAT, INTEGER, DURATION
* automatic SUT timestamp supported only by SCT: it calculates based on the Scylla Version date and commit id (builds from the same date are not the same, but timestamp does not reflect which one was earlier).
