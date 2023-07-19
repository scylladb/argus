from typing import TypedDict


class GeminiResultsRequest(TypedDict):
    oracle_nodes_count: int
    oracle_node_ami_id: str
    oracle_node_instance_type: str
    oracle_node_scylla_version: str
    gemini_command: str
    gemini_version: str
    gemini_status: str
    gemini_seed: str
    gemini_write_ops: int
    gemini_write_errors: int
    gemini_read_ops: int
    gemini_read_errors: int
