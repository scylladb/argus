from cassandra.cqlengine.models import Model
from cassandra.cqlengine import columns



class RunConfiguration(Model):
    run_id = columns.UUID(primary_key=True, partition_key=True, required=True)
    name = columns.Text(primary_key=True, required=True)
    content = columns.Text(required=True)


class RunConfigParam(Model):
    name = columns.Text(partition_key=True, primary_key=True, required=True)
    value = columns.Text(partition_key=True, primary_key=True, required=True)
    run_id = columns.Text(primary_key=True, required=True)
