import operator
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from functools import partial
from uuid import UUID

from argus.backend.db import ScyllaCluster
from argus.backend.models.result import ArgusGenericResultMetadata, ArgusGenericResultData
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
from argus.backend.service.results_service import ResultsService, Cell
from argus.backend.util.enums import TestStatus


class ClientException(Exception):
    pass


class ClientService:
    PLUGINS = {name: plugin.model for name, plugin in AVAILABLE_PLUGINS.items()}

    def __init__(self) -> None:
        self.cluster = ScyllaCluster.get()

    def get_model(self, run_type: str) -> PluginModelBase:
        cls = self.PLUGINS.get(run_type)
        if not cls:
            raise ClientException(f"Unsupported run type: {run_type}", run_type)
        return cls

    def submit_run(self, run_type: str, request_data: dict) -> str:
        model = self.get_model(run_type)
        model.submit_run(request_data=request_data)

        return "Created"

    def get_run(self, run_type: str, run_id: str):
        model = self.get_model(run_type)
        try:
            run = model.get(id=run_id)
        except model.DoesNotExist:
            return None
        return run

    def heartbeat(self, run_type: str, run_id: str) -> int:
        model = self.get_model(run_type)
        run = model.load_test_run(UUID(run_id))
        run.update_heartbeat()
        run.save()
        return run.heartbeat

    def get_run_status(self, run_type: str, run_id: str) -> str:
        model = self.get_model(run_type)
        run = model.load_test_run(UUID(run_id))
        return run.status

    def update_run_status(self, run_type: str, run_id: str, new_status: str) -> str:
        model = self.get_model(run_type)
        run = model.load_test_run(UUID(run_id))
        run.change_status(new_status=TestStatus(new_status))
        run.save()

        return run.status

    def submit_product_version(self, run_type: str, run_id: str, version: str) -> str:
        model = self.get_model(run_type)
        run = model.load_test_run(UUID(run_id))
        run.submit_product_version(version)
        run.save()

        return "Submitted"

    def submit_logs(self, run_type: str, run_id: str, logs: list[dict]) -> str:
        model = self.get_model(run_type)
        run = model.load_test_run(UUID(run_id))
        run.submit_logs(logs)
        run.save()

        return "Submitted"

    def finish_run(self, run_type: str, run_id: str, payload: dict | None = None) -> str:
        model = self.get_model(run_type)
        run = model.load_test_run(UUID(run_id))
        run.finish_run(payload)
        run.save()

        return "Finalized"

    def submit_results(self, run_type: str, run_id: str, results: dict) -> dict[str, str]:
        model = self.get_model(run_type)
        try:
            run = model.load_test_run(UUID(run_id))
        except model.DoesNotExist:
            return {"status": "error", "response": {
                "exception": "DoesNotExist",
                "arguments": [run_id]
            }}
        table_name = results["meta"]["name"]
        results_service = ResultsService()
        cells = [Cell(**cell) for cell in results["results"]]
        table_metadata = results_service.get_table_metadata(test_id=run.test_id, table_name=table_name)
        if table_metadata:
            table_metadata = table_metadata.update_if_changed(results["meta"])
        else:
            table_metadata = ArgusGenericResultMetadata(test_id=run.test_id, **results["meta"])
            table_metadata.save()
        if results.get("sut_timestamp", 0) == 0:
            results["sut_timestamp"] = run.sut_timestamp()  # automatic sut_timestamp
        results["sut_timestamp"] = datetime.fromtimestamp(results["sut_timestamp"])
        best_results = results_service.update_best_results(test_id=run.test_id, table_name=table_name, table_metadata=table_metadata,
                                                           cells=cells, run_id=run_id)
        table_name = results["meta"]["name"]
        sut_timestamp = results["sut_timestamp"]
        for cell in cells:
            cell.update_cell_status_based_on_rules(table_metadata, best_results)
            ArgusGenericResultData(test_id=run.test_id,
                                   run_id=run.id,
                                   name=table_name,
                                   sut_timestamp=sut_timestamp,
                                   **asdict(cell)
                                   ).save()
        return {"status": "ok", "message": "Results submitted"}
