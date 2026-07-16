# Production Deployment

This guide covers a source-based production deployment of Argus.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Node.js >= 22 with npm
- Yarn (`npm -g install yarn`)
- nginx

## Install from Source

Create a user for the service:

```bash
useradd -m -s /bin/bash argus
sudo -iu argus
```

Optional: install `pyenv` and create a virtualenv for this user:

```bash
pyenv install 3.12.0
pyenv virtualenv argus
pyenv activate argus
```

Clone the repository somewhere the `argus` user can write to:

```bash
git clone https://github.com/scylladb/argus ~/app
cd ~/app
```

Install dependencies:

```bash
uv sync --all-extras
yarn install
```

Build the frontend:

```bash
yarn build
```

## Configure Argus

Create the local config files in the application directory:

```bash
cp argus_web.example.yaml argus_web.yaml
cp argus.yaml argus.local.yaml
```

Update `argus.local.yaml` with your database connection settings:

- `contact_points`
- `user`
- `password`
- `keyspace name`

Update `argus_web.yaml` with:

- a secure `SECRET_KEY`
- the required `GITHUB_*` values

## Configure nginx

Copy the bundled nginx config.

Ubuntu:

```bash
sudo cp docs/config/argus.nginx.conf /etc/nginx/sites-available/argus
sudo ln -s /etc/nginx/sites-available/argus /etc/nginx/sites-enabled/argus
```

RHEL, CentOS, AlmaLinux, Fedora:

```bash
sudo cp docs/config/argus.nginx.conf /etc/nginx/conf.d/argus.conf
```

Adjust the virtual host settings as needed, especially `listen` and `server_name`.

## Configure systemd

Install the service file:

```bash
sudo cp docs/config/argus.service /etc/systemd/system/argus.service
```

Edit it and adjust:

- `ExecStart` to point at `start_argus.sh`
- the service user and group

`start_argus.sh` assumes `pyenv` is installed in `~/.pyenv`.

Reload and enable the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now argus.service
```

## Configure Logging

`uwsgi.ini` logs to `/var/log/argus/argus.log`. Create the directory and install log rotation:

```bash
sudo mkdir -p /var/log/argus
sudo chown argus:argus /var/log/argus
sudo cp docs/config/argus.logrotate /etc/logrotate.d/argus
```
