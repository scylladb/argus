from typing import TypedDict


class GenericRunSubmitRequest(TypedDict):
    build_id: str
    build_url: str
    run_id: str
    started_by: str
    scylla_version: str | None
    # sub_type is used to tell which framework the GenericRun belongs to
    sub_type: str | None #  pytest | dtest


class GenericRunFinishRequest(TypedDict):
    status: str
    scylla_version: str | None
