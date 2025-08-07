# Quick setup for local development environment

Minimal local dev setup with one db node (adjust accordingly if needed more nodes)

## Prerequisites
1. Python >=3.10.0 (system-wide or pyenv)
2. NodeJS >=16 (with npm)
3. Yarn (can be installed globally with `npm -g install yarn`)
4. uv (https://docs.astral.sh/uv/getting-started/installation/)
5. docker-compose

## Installing argus dependencies
```bash
uv sync --all-extras
yarn install
```

## Configuring argus
Create a `argus.local.yaml` configuration file (used to configure database connection) and a `argus_web.yaml` (used for webapp secrets) in your application install directory.

### argus.local.yaml
```yaml

contact_points:
  - 172.18.0.2
username: cassandra
password: cassandra
keyspace_name: argus

```

### argus_web.yaml
Replace all <> with your values. Find instructions below.
```yaml
BASE_URL: "https://argus.scylladb.com"
SCYLLA_CONTACT_POINTS:
  - 172.18.0.2
SCYLLA_USERNAME: cassandra
SCYLLA_PASSWORD: cassandra
SCYLLA_KEYSPACE_NAME: argus

APP_LOG_LEVEL: INFO
SECRET_KEY: MUSTBEUNIQUE

GITHUB_CLIENT_ID: <>
GITHUB_CLIENT_SECRET: <>
GITHUB_ACCESS_TOKEN: unknown
# List of required organization names (Comment out to disable organization requirement)
#GITHUB_REQUIRED_ORGANIZATIONS:

JENKINS_URL: https://jenkins.scylladb.com
JENKINS_USER: <your username>
JENKINS_API_TOKEN_NAME: argus-dev
JENKINS_API_TOKEN: <jenkins api token>


EMAIL_SENDER: "qabot@scylladb.com"
EMAIL_SENDER_USER: ""
EMAIL_SENDER_PASS: ""
EMAIL_SERVER: "smtp.gmail.com"
EMAIL_SERVER_PORT: "587"

JOB_VALIDITY_PERIOD_DAYS: 30
```

#### Github OAuth App setup (getting :
1. GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET
   1. go to your Account Settings (top right corner) -> Developer settings (left pane) -> OAuth Apps
   2. Click Create New OAuth App button
   3. Fill the fields (app name: `argus-dev`, homepage URL `http://localhost:5000`, Auth callback URL: `http://localhost:5000/profile/oauth/github`)
   4. Confirm and get the tokens/ids required for config - visible on the page

#### Create Jenkins token for your account
1. Click your username in top right corner
2.  write down user id
3. Go to `Configure` from left panel
4. Click `Add new Token` and name it `argus-dev`
5. Get it and paste to config to `JENKINS_API_TOKEN` param

## Configure database

### Start database using docker-compose
```bash
docker-compose -f dev-db/docker-compose.yaml up -d
```

### create keyspace
```bash
docker exec -it argus_alpha_1 cqlsh --user cassandra --password cassandra -e "CREATE KEYSPACE argus WITH replication = {'class': 'NetworkTopologyStrategy', 'replication_factor' : 1};"
```

### create all tables
```bash
FLASK_DEBUG=1 FLASK_ENV=development FLASK_APP=argus_backend:argus_app uv run flask cli sync-models
```

### import jenkins jobs
```bash
FLASK_DEBUG=1 FLASK_ENV=development FLASK_APP=argus_backend:argus_app uv run flask cli scan-jenkins
```

### import data
#### Get sample data
1. From S3
```bash
aws s3 cp s3://argus-utilities/sample_data.tar.zst .
```
2. From prod db
   1. Configure prod db (setup argus.local.yaml) by creating a ssh tunnel:
   ```bash
   # get argus-web details from the tribe
   ssh argus-web -L 127.0.0.10:9042:10.10.2.62:9042 -L 127.0.0.11:9042:10.10.2.157:9042 -L 127.0.0.12:9042:10.10.2.74:9042 -L 127.0.0.10:19042:10.10.2.62:19042 -L 127.0.0.11:19042:10.10.2.157:19042 -L 127.0.0.12:19042:10.10.2.74:19042
   ```
    argus.local.yaml
   ```yaml
      # SCYLLA_CONTACT_POINTS:
      - 127.0.0.10
      - 127.0.0.11
      - 127.0.0.12
      # get db details from the tribe
   ```
Modify `release` variable in `dev-db/export_data.py` and glob paths to your need.
Run multiple times to download all the releases you need.
```bash
python dev-db/export_data.py
```

#### Import it
```bash
python dev-db/import_data.py
```
Sporadical errors like `Test entity missing for key "enterprise-2023.1/upgrade-with-raft/rolling-upgrade-centos8-with-raft-test", run won't be visible until this is corrected`
can be ignored.

## Run the application
Compile frontend files from `/frontend` into `/public/dist`. Add --watch to recompile files on change.
```bash
ROLLUP_ENV=development yarn rollup -c --watch
```

```bash
FLASK_ENV="development" FLASK_APP="argus_backend:start_server" FLASK_DEBUG=1 CQLENG_ALLOW_SCHEMA_MANAGEMENT=1 flask run
```
Omit `FLASK_DEBUG` if running your own debugger (pdb, pycharm, vscode)

## Try it
Open browser at `http://localhost:5000` (use localhost as Github OAuth setup instead of 127.0.0.1 )
