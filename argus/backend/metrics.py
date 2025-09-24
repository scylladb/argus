import os
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_flask_exporter.multiprocess import UWsgiPrometheusMetrics

from argus.backend.service.user import api_login_required

if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
    """
        Initialize prometheus metrics in a multiprocess environment
        and set up authentication to the /metrics endpoint
    """
    METRICS = UWsgiPrometheusMetrics.for_app_factory(path="/metrics", export_defaults=False, metrics_decorator=api_login_required)
else:
    METRICS = PrometheusMetrics.for_app_factory(path="/metrics", export_defaults=False)
