from uuid import UUID
from argus.backend.db import ScyllaCluster
from argus.backend.plugins.core import PluginModelBase
from argus.backend.plugins.loader import AVAILABLE_PLUGINS
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
