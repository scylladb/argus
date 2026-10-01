# Deployment

Argus deploys from a release bundle, through the QA Tools deployment
repository: `make argus INVENTORY=<env>` in
[scylladb/qatools](https://github.com/scylladb/qatools), see `docs/argus.md`
there. It installs the bundle under `/opt/argus`, renders the configuration
from the inventory, runs the schema sync, and manages nginx, the service, the
argusAI worker, the maintenance timers and log rotation. Nothing is built on a
host.

This repository publishes the bundle on every `v*` tag, from
[`.github/workflows/release.yml`](../.github/workflows/release.yml):
`argus-<version>-linux-{x86_64,aarch64}.tar.zst`, each with a sha256 beside
it, next to the wheels. `scripts/release/build-bundle.sh` is the build, and
its header describes the layout the deployment relies on.

For the development setup, see [`dev-setup.md`](dev-setup.md).
