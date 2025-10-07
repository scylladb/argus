# Argus
[![PyPI - Version](https://img.shields.io/pypi/v/argus-alm)](https://pypi.python.org/pypi/argus-alm)

## Description

Argus is a test tracking system intended to provide observability into automated test pipelines which use long-running resources. It allows observation of a test status, its events and its allocated resources. It also allows easy comparison between particular runs of a specific test.

## Contributing

Review the [Repository Guidelines](AGENTS.md) for project structure, tooling expectations, and pull request practices before submitting changes.

## Installation notes

### Development

For development setup instructions, see [dev-setup.md](./docs/dev-setup.md).

### Prerequisites

- Python >=3.10.0 (system-wide or pyenv)

- NodeJS >=16 (with npm)

- Yarn (can be installed globally with `npm -g install yarn`)

- nginx

- uv

### From source

#### Production

Perform the following steps:

Create a user that will be used by uwsgi:

```bash
useradd -m -s /bin/bash argus
sudo -iu argus
```

(Optional) Install pyenv and create a virtualenv for this user:

```bash
pyenv install 3.10.0
pyenv virtualenv argus
pyenv activate argus
```

Clone the project into a directory somewhere where user has full write permissions

```bash
git clone https://github.com/scylladb/argus ~/app
cd ~/app
```

Install project dependencies:

```bash
uv sync --all-extras
yarn install
```

Compile frontend files from `/frontend` into `/public/dist`

```bash
yarn rollup -c
```

Create a `argus.local.yaml` configuration file (used to configure database connection) and a `argus_web.yaml` (used for webapp secrets) in your application install directory.

```bash
cp argus_web.example.yaml argus_web.yaml
cp argus.yaml argus.local.yaml
```

Open `argus.local.yaml` and add the database connection information (contact_points, user, password and keyspace name).

Open `argus_web.yaml` and change the `SECRET_KEY` value to something secure, like a sha512 digest of random bytes. Fill out GITHUB_* variables with their respective values.

Copy nginx configuration file from `docs/configs/argus.nginx.conf` to nginx virtual hosts directory:

Ubuntu:

```bash
sudo cp docs/configs/argus.nginx.conf /etc/nginx/sites-available/argus
sudo ln -s /etc/nginx/sites-enabled/argus /etc/nginx/sites-available/argus
```

RHEL/Centos/Alma/Fedora:

```bash
sudo cp docs/configs/argus.nginx.conf /etc/nginx/conf.d/argus.conf
```

Adjust the webhost settings in that file as necessary, particularly `listen` and `server_name` directives.

Copy systemd service file from `docs/config/argus.service` to `/etc/systemd/system` directory:

```bash
sudo cp docs/config/argus.service /etc/systemd/system
```

Open it and adjust the path to the `start_argus.sh` script in the `ExecStart=` directive and the user/group, then reload systemd daemon configuration and enable (and optionally start) the service.

WARNING: `start_argus.sh` assumes pyenv is installed into `~/.pyenv`

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now argus.service
```
