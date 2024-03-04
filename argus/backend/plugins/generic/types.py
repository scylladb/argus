from typing import TypedDict

class GenericRunSubmitRequest(TypedDict):
    build_id: str
    build_url: str
    run_id: str
    started_by: str
    scylla_version: str | None


class GenericRunFinishRequest(TypedDict):
    status: str
    scylla_version: str | None
