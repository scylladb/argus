"""The Argus health process.

The gunicorn master starts it as a detached process. It probes the Argus
dependencies with the qatools-health runner and serves /health,
/health/ready and /metrics on an internal port.
"""
