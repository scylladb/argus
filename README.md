# Argus

## Description

Argus is a test tracking system intended to provide observability into automated test pipelines which use long-running resources. It allows observation of a test status, its events and its allocated resources. It also allows easy comparison between particular runs of a specific test.

## Installation notes

### Prerequisites

- Python >=3.10.0 (system-wide or pyenv)

- NodeJS >=16 (with npm)

- Yarn (can be installed globally with `npm -g install yarn`)

- nginx

- poetry >=1.2.0b1

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
poetry install --with default,dev,web-backend,docker-image
yarn install
```

Compile frontend files from `/frontend` into `/public/dist`

```bash
yarn webpack
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

#### Development

Clone the project into a directory somewhere

```bash
git clone https://github.com/scylladb/argus
cd argus
```

Install project dependencies:

```bash
poetry install --with default,dev,web-backend,docker-image
yarn install
```

Compile frontend files from `/frontend` into `/public/dist`. Add --watch to recompile files on change.

```bash
yarn webpack --watch
```
##### Configuration
Create a `argus.local.yaml` configuration file (used to configure database connection) and a `argus_web.yaml` (used for webapp secrets) in your application install directory.

See `Production` section for more details.
To configure Github authentication follow steps:
1. Authorize OAuth App
   1. go to your Account Settings (top right corner) -> Developer settings (left pane) -> OAuth Apps
   2. Click Create New OAuth App button
   3. Fill the fields (app name: `argus-dev`, homepage URL `http://localhost:5000`, Auth callback URL: `http://localhost:5000/profile/oauth/github`)
   4. Confirm and get the tokens/ids required for config
2. Create Jenkins token for your account
   1. Go to `Configure` in top right corner
   2. Click `Add new Token`
   3. Get it and paste to config to `JENKINS_API_TOKEN` param
##### Database Initialization

You can initialize a scylla cluster in any way you like, either using docker image with docker-compose or using cassandra cluster manager. You will need to create the keyspace manually before you can sync database models.

Create keyspace according to your configuration.
e.g. (need to test if it works with RF=1 if not, make it 3)
```
CREATE KEYSPACE argus WITH replication = {'class': 'SimpleStrategy', 'replication_factor' : 1}
```

Initial sync can be done as follows:

```py
from argus.backend.db import ScyllaCluster
from argus.db.testrun import TestRun
db = ScyllaCluster.get()

db.sync_models() # Syncronizes Object Mapper models
TestRun.init_own_table() # Syncronizes TestRun table (separate from python-driver Object Mapper)

```

You can also use `flask sync-models` afterwards during development when making small changes to models.

It is recommended to set up jenkins api key and run `flask scan-jenkins` afterwards to get basic release/group/test structure.

There are scripts in `./scripts` directory that can be used to download data from production, upload them into your dev db and fix their relations to other models in your instance of the application. Specifically, `download_runs_from_prod.py` requires additional config, `argus.local.prod.yaml` which is the config used to connect to the production cluster. The scripts are split to prevent mistakes and accidentally affecting production cluster.

##### Configuration

Create a `argus.local.yaml` configuration file (used to configure database connection) and a `argus_web.yaml` (used for webapp secrets) in your application install directory.

```bash
cp argus_web.example.yaml argus_web.yaml
cp argus.yaml argus.local.yaml
```

Open `argus.local.yaml` and add the database connection information (contact_points, user, password and keyspace name).

Open `argus_web.yaml` and change the `SECRET_KEY` value to something secure, like a sha512 digest of random bytes. Fill out GITHUB_* and JENKINS_* variables with their respective values.

Run the application from CLI using:

```bash
FLASK_ENV="development" FLASK_APP="argus_backend:start_server" FLASK_DEBUG=1 CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 flask run
```

Omit `FLASK_DEBUG` if running your own debugger (pdb, pycharm, vscode)
