# Deployment

Argus deploys from a release bundle, through the QA Tools deployment
repository: `make argus INVENTORY=<env>` in
[scylladb/qatools](https://github.com/scylladb/qatools), see `docs/argus.md`
there. It installs the bundle under `/opt/argus`, renders the configuration
from the inventory, runs the schema sync, and manages nginx, the service, the
argusAI worker, the maintenance timers and log rotation. Nothing is built on a
host.

The nginx virtual host is `roles/argus/templates/argus.nginx.conf.j2` there.
It carries the static-asset cache headers that `tasks/ARGUS-245/rca.md`
selected: content-hashed chunks in `/s/dist/` as immutable, the other
`/s/dist/` files with `no-cache`, the rest of `/s/` for ten minutes. The
reference copy the RCA names, `docs/config/argus.nginx.conf`, was removed
with the other hand-deployment files.

This repository publishes the bundle on every `v*` tag, from
[`.github/workflows/release.yml`](../.github/workflows/release.yml):
`argus-<version>-linux-{x86_64,aarch64}.tar.zst`, each with a sha256 beside
it, next to the wheels. `scripts/release/build-bundle.sh` is the build, and
its header describes the layout the deployment relies on.

The health process (QATOOLS-425) is off unless `argus_web.yaml` sets
`HEALTH_ENABLED: true`. It then listens on `HEALTH_HOST:HEALTH_PORT`, 9300 by
default, for Prometheus; open that port to the monitoring host only. Set
`HEALTH_TOKEN` to a random key and give the scrape job the header
`Authorization: token <HEALTH_TOKEN>`. `HEALTH_NGINX_URL` defaults to
`http://127.0.0.1/s/argus.png`, which the deployment's virtual host serves;
the Docker image needs `http://127.0.0.1:8000/s/argus.png`. A SIGHUP to the
gunicorn master restarts the health process, so it reads an edit to these
keys. `/health/ready` answers 503 until the first probes end after a start or
a SIGHUP, so do not use it as a load balancer readiness probe. The deployment
repository renders these keys from its inventory like the rest of the file.

For the development setup, see [`dev-setup.md`](dev-setup.md).
