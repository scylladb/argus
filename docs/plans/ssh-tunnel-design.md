# SSH Tunnel Support for Argus Client

## Context

Automated traffic (SCT, dtest) routes through Cloudflare (HTTPS), incurring costs. This design adds an SSH tunnel in the Argus Python client to route traffic directly to the internal backend via a proxy host.

### Design Principles

- **Client-generated keypairs** — Clients generate ed25519 keypairs locally using Python's `cryptography` library. Only the public key is sent to Argus and stored in DB; the private key never leaves the client. This follows standard SSH key registration practices.
- **Single client per host** — no multi-client coordination needed.
- **DB-backed proxy tunnel config** — connection details stored in DB and managed via admin panel (not YAML config).
- **Real-time key lookup** — proxy host uses sshd `AuthorizedKeysCommand` to fetch valid keys from Argus API on each SSH auth attempt (via argus-cli). No `authorized_keys` file management.
- **In-process tunnel lifecycle** — per-session, with `atexit` cleanup.

### Security Properties

1. **No private key exposure** — private key is generated on the client and never transmitted. DB compromise or API interception cannot leak private keys.
2. **Minimal blast radius** — key only grants restricted port-forwarding (`ForceCommand /bin/false`, `PermitOpen` locked to single host:port). A compromised key cannot get a shell or access anything else.
3. **TTL-based expiration** — keys auto-expire via ScyllaDB TTL (default 24h, configurable). No stale keys accumulate.
4. **Real-time key validity** — `AuthorizedKeysCommand` queries Argus API on each SSH connection, so key validity is always current. No file writes, no sync races.
5. **Host key verification** — API returns proxy host key fingerprint; client uses `StrictHostKeyChecking=yes` with a generated known_hosts file (no TOFU).
6. **Instant revocation** — deleting a key row from DB takes immediate effect on next SSH connection attempt.

---

## Architecture

### Flow: First Request (tunnel setup)

```
Client                          Argus Backend (via Cloudflare)        Proxy Host
  |                                    |                                |
  |-- generate ed25519 keypair locally |                                |
  |   (Python cryptography library)    |                                |
  |                                    |                                |
  |-- POST /client/ssh/tunnel -------->|                                |
  |   (auth_token, public_key,         |                                |
  |    ttl_seconds?)                   |                                |
  |                                    |-- store PUBLIC key in DB       |
  |<-- {proxy_host, proxy_port,        |                                |
  |     proxy_user, target_host,       |                                |
  |     target_port,                   |                                |
  |     host_key_fingerprint,          |                                |
  |     expires_at} ------------------|                                |
  |                                                                     |
  |-- ssh -N -L local:target_host:target_port user@proxy-host ----------->|
  |   (using locally-held private_key, verifying host_key_fingerprint)  |
  |                                    |                                |
  |                                    |<-- AuthorizedKeysCommand ------|
  |                                    |    (argus-cli ssh-keys)        |
  |                                    |-- returns valid public keys -->|
  |                                    |                                |
  |-- HTTP requests via localhost:local_port --------------------------->|
```

### Flow: Subsequent Requests (cached)

```
Client
  |-- Check ~/.ssh/id_argus_proxy (existing key + comment contains expiry timestamp)
  |-- ssh -N -L ... (using local private key, verifying host fingerprint)
  |-- HTTP requests via localhost:local_port
  |
  |-- If tunnel fails: re-call /client/ssh/tunnel with same or new public key, get fresh config
  |-- If that also fails: delete cached key, fall back to Cloudflare
```

### Tunnel Lifecycle (per-session, in-process)

1. Client constructed — no tunnel yet (lazy)
2. On first HTTP request, calls `_ensure_tunnel()`:
    - Checks `~/.ssh/id_argus_proxy` for cached keypair (expiry in key comment)
    - If no cache or expired: generates a new ed25519 keypair via Python `cryptography` library, saves private key to `~/.ssh/id_argus_proxy` (mode 0600), then calls `POST /api/v1/client/ssh/tunnel` with the public key to register it and receive proxy config
    - Writes known_hosts temp file from `host_key_fingerprint`
    - Spawns `ssh -N -L` subprocess with `StrictHostKeyChecking=yes` and `atexit` cleanup
    - Probes local port with `socket.connect_ex` to confirm tunnel is up
3. Before each subsequent request: checks tunnel is alive via `socket.connect_ex`
4. If tunnel dies mid-session: reconnect (up to 3 retries)
5. On process exit: `atexit` handler terminates SSH subprocess

### Graceful Fallback

If `ssh` binary missing, tunnel fails, or reconnection exhausted:

- `LOGGER.warning(...)` with clear message
- Fall back to original `base_url` (Cloudflare)
- No exceptions propagate — client continues to work

### Key Lifecycle

- **One key per session** — each `POST /client/ssh/tunnel` registers a fresh public key (generated client-side). Only the public key is stored in DB; the private key never leaves the client.
- **TTL via ScyllaDB** — rows inserted with ScyllaDB TTL (default 24 hours). Client can provide `ttl_seconds` for custom duration (e.g., longer for multi-day jobs). ScyllaDB automatically deletes expired rows — no manual cleanup needed.
- **All timestamps in UTC** — `created_at`, `expires_at` stored and transmitted as UTC ISO-8601
- **Revocation** — admin deletes the key row from DB via admin panel. Takes immediate effect on next SSH connection (proxy host queries API via `AuthorizedKeysCommand`).
- Client gets `expires_at` in tunnel response, stores as key comment in `~/.ssh/id_argus_proxy`
- Before using cached key: parse expiry from comment → if expired, generate new keypair and re-register
- **Mid-session revocation** — SSH authenticates only at connection establishment. A deleted key does NOT kill an active tunnel. The revocation takes effect on next reconnect, at which point the client generates a fresh keypair and re-registers.

---

## Proxy Host Setup

### Infrastructure (AWS)

- **Region:** eu-north-1
- **VPC:** sct-vpc2 (same VPC as Argus for internal connectivity)
- **Instance type:** t3.micro
- **Security group:** Allow inbound SSH (port 22) from `0.0.0.0/0` (SCT runner IPs are dynamic/unknown); allow outbound to Argus private IP:port

### OS Configuration

**Users:**

- `admin` — full shell access for maintenance
- `argus-proxy` — restricted tunnel-only account

**sshd_config:**

```
PasswordAuthentication no
PubkeyAuthentication yes

Match User argus-proxy
    AllowTcpForwarding yes
    PermitOpen <argus-private-ip>:8080
    X11Forwarding no
    AllowAgentForwarding no
    ForceCommand /bin/false
    PermitTTY no
    ClientAliveInterval 600
    ClientAliveCountMax 1
    AuthorizedKeysFile none
    AuthorizedKeysCommand /usr/local/bin/argus-authorized-keys
    AuthorizedKeysCommandUser nobody
```

**`AuthorizedKeysCommand` explanation:** On each SSH connection attempt by `argus-proxy`, sshd runs the `argus-authorized-keys` wrapper script. The wrapper calls `argus-cli ssh-keys`, which hits `GET /api/v1/client/ssh/keys` on the Argus backend and returns all non-expired public keys. sshd uses the output as the authorized_keys for that connection. This eliminates all file sync, race conditions, and stale state — key validity is always real-time from DB.

**Proxy Host requirements:**

- `argus-cli` binary installed at `/usr/local/bin/argus-cli` (owned by root, not writable by group/others — sshd requirement)
- `argus-authorized-keys` wrapper script at `/usr/local/bin/argus-authorized-keys` with API URL and auth token embedded (see provisioning template)

### Configuring target_host

The `target_host` is the **private IP** of the Argus instance in sct-vpc2:

```
aws ec2 describe-instances --filters "Name=tag:Name,Values=argus-*" \
  --query 'Reservations[].Instances[].PrivateIpAddress'
```

---

## Implementation Plan

### Current Status

- [x] Step 1: DB model - `argus/backend/models/ssh_key.py` (done in PR #967)
- [x] Step 2: Proxy tunnel config in DB - `argus/backend/models/ssh_key.py` (done in PR #967)
- [x] Step 3: Backend service - `argus/backend/service/tunnel_service.py` (done in PR #967)
- [x] Step 4a: Client API - `argus/backend/controller/ssh_api.py` (done in PR #967)
- [x] Step 9 (partial): backend tunnel tests (`argus/backend/tests/tunnel/test_tunnel_service.py`, `argus/backend/tests/tunnel/test_ssh_api.py`) (done in PR #967)
- [ ] Step 4b: Admin API
- [ ] Step 4c: Proxy host provisioning template
- [ ] Step 4d: Admin Panel UI
- [ ] Step 5: Client module - `argus/client/tunnel.py`
- [ ] Step 6: Modify `argus/client/base.py`
- [ ] Step 7: Python CLI integration
- [ ] Step 7b: Go CLI `ssh-keys` command

### Step 1: DB model — `argus/backend/models/ssh_key.py`

Status: Done in PR #967.

```python
class SSHTunnelKey(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    public_key = columns.Text()        # registered by client, used by AuthorizedKeysCommand
    fingerprint = columns.Text()
    created_at = columns.DateTime()    # UTC
    expires_at = columns.DateTime()    # UTC, informational (actual expiry via ScyllaDB TTL)
```

**Rows inserted with ScyllaDB TTL** — default 24 hours (86400s), configurable via client-provided `ttl_seconds`. ScyllaDB automatically deletes expired rows, no manual cleanup needed. The `expires_at` field is informational (returned to client so it knows when to re-register).

Add to `USED_MODELS` list in `argus/backend/models/web.py`.

### Step 2: Proxy tunnel config in DB — `argus/backend/models/ssh_key.py`

Status: Done in PR #967.

```python
class ProxyTunnelConfig(Model):
    id = columns.UUID(primary_key=True, default=uuid4)
    host = columns.Text()              # public hostname/IP
    port = columns.Integer()           # SSH port (default 22)
    proxy_user = columns.Text()        # e.g. "argus-proxy"
    target_host = columns.Text()       # Argus private IP
    target_port = columns.Integer()    # Argus internal port
    host_key_fingerprint = columns.Text()  # SSH host key fingerprint (SHA256:...)
    service_user_id = columns.UUID()       # Argus user created for this proxy host (for API access)
    is_active = columns.Boolean()
```

Add to `USED_MODELS`. Managed via admin panel (Step 4d). Only one active proxy host at a time (`is_active=True`).

**Service user per proxy host:** When admin saves a new proxy tunnel config, the backend automatically creates a dedicated Argus user (e.g., `proxy-tunnel-<host>`) with a fresh API token. This token is deployed to the proxy host during provisioning for argus-cli to call the authorized keys endpoint. Each proxy host gets its own isolated credentials — revoking a proxy host's access is as simple as deleting its service user.

`admin_user` and `admin_key_path` (SSH credentials for provisioning access to the proxy host) are stored in `argus_web.yaml`.

### Step 3: Backend service — `argus/backend/service/tunnel_service.py`

Status: Done in PR #967.

Class `TunnelService`:

- `register_tunnel(user: User, public_key: str, ttl_seconds: int = None) -> dict`:
    1. Store `SSHTunnelKey` in DB (public key only) with ScyllaDB TTL (default 86400s / 24h, or client-provided `ttl_seconds`). Set `expires_at = now_utc + ttl` for informational purposes.
    2. Get active `ProxyTunnelConfig`
    3. Return `{proxy_host, proxy_port, proxy_user, target_host, target_port, host_key_fingerprint, expires_at}` (all datetimes UTC ISO-8601)

- `get_authorized_keys() -> str`:
    1. Fetch all `SSHTunnelKey` records (expired rows already removed by ScyllaDB TTL)
    2. Return newline-separated public keys in OpenSSH `authorized_keys` format
    3. Called by proxy host via `AuthorizedKeysCommand` → argus-cli → this API

- `delete_key(key_id: UUID)`:
    1. Delete `SSHTunnelKey` row from DB
    2. Takes immediate effect — next `AuthorizedKeysCommand` call won't include it

- `get_proxy_tunnel_config() -> ProxyTunnelConfig | None`:
    1. Return active proxy tunnel config (for admin panel display)

- `save_proxy_tunnel_config(payload: dict) -> ProxyTunnelConfig`:
    1. Deactivate any existing active config
    2. Create a dedicated Argus service user for this proxy host (e.g., `proxy-tunnel-<host>`), generate API token
    3. Save proxy tunnel config with `service_user_id`
    4. Run provisioning script on the proxy host (Step 4c), passing the service user's API token
    5. On success: mark config as active. On failure: mark inactive, return error.
    6. Return saved config

- `provision_proxy_tunnel(config: ProxyTunnelConfig, auth_token: str)`:
    1. SSH to proxy host as admin (admin credentials from `argus_web.yaml`)
    2. Render Jinja provisioning template (Step 4c) with proxy tunnel config + auth token
    3. Transfer rendered script to proxy host and execute. The script:
        - Creates `argus-proxy` OS user (if not exists) with no shell
        - Installs `argus-cli` binary to `/usr/local/bin/argus-cli`
        - Writes `argus-authorized-keys` wrapper with API URL and auth token embedded
        - Configures sshd: writes `Match User argus-proxy` block
        - Restarts sshd and verifies API connectivity
    4. On failure: mark config as inactive, return error to admin

### Step 4a: Client API — `argus/backend/controller/ssh_api.py`

Status: Done in PR #967.

Blueprint registered under `/client/`:

```python
@bp.route("/ssh/tunnel", methods=["POST"])
@api_login_required
def register_tunnel():
    payload = request.get_json() or {}
    public_key = payload.get("public_key")
    ttl_seconds = payload.get("ttl_seconds")
    result = TunnelService().register_tunnel(g.user, public_key=public_key, ttl_seconds=ttl_seconds)
    return {"status": "ok", "response": result}

@bp.route("/ssh/keys", methods=["GET"])
@api_login_required
def get_authorized_keys():
    """Called by argus-cli on the proxy host via AuthorizedKeysCommand."""
    keys = TunnelService().get_authorized_keys()
    return Response(keys, mimetype="text/plain")
```

Register in `client_api.py` as sub-blueprint.

### Step 4b: Admin API — `argus/backend/controller/admin_api.py`

Add to existing admin API blueprint (follows existing pattern: `@api_login_required` + `@check_roles(UserRoles.Admin)`):

```python
# Proxy tunnel config management
@bp.route("/proxy-tunnel/config", methods=["GET"])
@api_login_required
@check_roles(UserRoles.Admin)
def get_proxy_tunnel_config():
    config = TunnelService().get_proxy_tunnel_config()
    return {"status": "ok", "response": config}

@bp.route("/proxy-tunnel/config", methods=["POST"])
@api_login_required
@check_roles(UserRoles.Admin)
def save_proxy_tunnel_config():
    payload = request.get_json()
    config = TunnelService().save_proxy_tunnel_config(payload)
    return {"status": "ok", "response": config}

# Key management (list, delete, cleanup)
@bp.route("/ssh/keys", methods=["GET"])
@api_login_required
@check_roles(UserRoles.Admin)
def list_ssh_keys():
    keys = TunnelService().list_keys()
    return {"status": "ok", "response": keys}

@bp.route("/ssh/keys/<key_id>", methods=["DELETE"])
@api_login_required
@check_roles(UserRoles.Admin)
def delete_ssh_key(key_id):
    TunnelService().delete_key(UUID(key_id))
    return {"status": "ok", "response": {"deleted": True}}
```

Note: no cleanup endpoint needed — ScyllaDB TTL handles expired row deletion automatically.

### Step 4c: Proxy host provisioning template — `argus/backend/templates/provision_proxy_tunnel.sh.j2`

Jinja template rendered by the backend with proxy tunnel config values, then transferred and executed on the proxy host via SSH. The rendered script is idempotent (safe to re-run).

```bash
#!/usr/bin/env bash
# Rendered by Argus backend from provision_proxy_tunnel.sh.j2
set -euo pipefail

# 1. Create restricted proxy user
id "{{ proxy_user }}" &>/dev/null || useradd -r -s /usr/sbin/nologin "{{ proxy_user }}"

# 2. Install argus-cli (pre-copied to /tmp/argus-cli by the backend before running this script)
install -o root -g root -m 0755 /tmp/argus-cli /usr/local/bin/argus-cli
rm -f /tmp/argus-cli

# 3. Wrapper script for AuthorizedKeysCommand (API config embedded)
cat > /usr/local/bin/argus-authorized-keys <<'WRAPPER'
#!/usr/bin/env bash
export ARGUS_API_URL="http://{{ target_host }}:{{ target_port }}"
export ARGUS_AUTH_TOKEN="{{ auth_token }}"
exec /usr/local/bin/argus-cli ssh-keys
WRAPPER
chown root:root /usr/local/bin/argus-authorized-keys
chmod 0755 /usr/local/bin/argus-authorized-keys

# 4. Configure sshd
cat > /etc/ssh/sshd_config.d/argus-proxy.conf <<'SSHDEOF'
Match User {{ proxy_user }}
    AllowTcpForwarding yes
    PermitOpen {{ target_host }}:{{ target_port }}
    X11Forwarding no
    AllowAgentForwarding no
    ForceCommand /bin/false
    PermitTTY no
    ClientAliveInterval 600
    ClientAliveCountMax 1
    AuthorizedKeysFile none
    AuthorizedKeysCommand /usr/local/bin/argus-authorized-keys
    AuthorizedKeysCommandUser nobody
SSHDEOF

# 5. Restart sshd
systemctl restart sshd

# 6. Verify
/usr/local/bin/argus-authorized-keys > /dev/null
echo "Proxy host provisioned successfully"
```

The backend:

1. Creates a dedicated Argus service user for this proxy host, generates API token
2. Renders the Jinja template with proxy tunnel config + service user's auth token
3. SCPs the `argus-cli` binary to `/tmp/argus-cli` on the proxy host
4. SCPs and executes the rendered provisioning script
5. Admin SSH credentials (`admin_user`, `admin_key_path`) from `argus_web.yaml`

### Step 4d: Admin Panel UI — `frontend/AdminPanel/ProxyTunnelManager.svelte`

New admin panel section "SSH Tunnel" accessible from the admin sidebar. Follows existing patterns (UserManager.svelte, ViewsManager.svelte).

**Proxy Tunnel Config form:**

- Host (text input)
- Port (number input, default 22)
- Proxy User (text input, default "argus-proxy")
- Target Host (text input — Argus private IP)
- Target Port (number input, default 8080)
- Host Key Fingerprint (text input — obtain via `ssh-keyscan proxy-host | ssh-keygen -lf -`)
- Service User (read-only, auto-created — shows the dedicated Argus user + token created for this proxy host)
- Active toggle (boolean)
- Save button → triggers provisioning script on the proxy host. On success: config saved + active. On failure: error message shown, config not activated.
- Re-provision button (re-run provisioning on existing proxy host, e.g., after argus-cli update)
- Deactivate button

**SSH Keys table:**

- Columns: Fingerprint, Created, Expires, Actions
- Actions: Delete button (with confirmation modal)

Wire into `AdminPanel.svelte` sidebar navigation alongside existing User/Release/Views sections.

### Step 5: Client module — `argus/client/tunnel.py`

**Dataclass `TunnelConfig`:**

```python
@dataclass
class TunnelConfig:
    proxy_host: str
    proxy_port: int
    proxy_user: str
    target_host: str
    target_port: int
    host_key_fingerprint: str
    expires_at: str        # UTC ISO-8601 datetime
```

**Class `SSHTunnel`:**

Attributes: `_process`, `_local_port`, `_key_path` (`~/.ssh/id_argus_proxy`)

Methods:

- `establish(config: TunnelConfig) -> int | None` — Write known_hosts temp file from `host_key_fingerprint`, find free port, spawn `ssh -N -L ... -i ~/.ssh/id_argus_proxy -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile={known_hosts_file} -o ConnectTimeout=10`, wait for port, register `atexit`. Returns local port or None.
- `is_alive() -> bool` — `_process.poll() is None` and `socket.connect_ex` on local port.
- `reconnect(config) -> int | None` — Kill existing, re-establish, up to 3 retries.
- `shutdown()` — Terminate process, remove known_hosts temp file.

**Function `resolve_tunnel_config`:**

```python
def resolve_tunnel_config(auth_token: str, base_url: str, force_refresh=False) -> TunnelConfig | None
```

1. Check `~/.ssh/id_argus_proxy` for a cached keypair (parse expiry from key comment)
2. If cached and not expired and not `force_refresh`: load the existing private key and return config from `~/.ssh/config`
3. Otherwise: generate a new ed25519 keypair via Python `cryptography` library, save private key to `~/.ssh/id_argus_proxy` (mode 0600), then `POST {base_url}/api/v1/client/ssh/tunnel` with the public key and receive proxy config. Store expiry as key comment.
4. On any failure: log warning, return None

### Step 6: Modify `argus/client/base.py`

Constructor adds:

```python
def __init__(self, auth_token, base_url, ..., use_tunnel: bool = None):
```

- `use_tunnel` defaults to `os.environ.get("ARGUS_USE_TUNNEL", "").lower() in ("1", "true", "yes")`
- Stores `self._original_base_url`, `self._tunnel = None`, `self._tunnel_config = None`

New method `_ensure_tunnel()` called at top of `get()` and `post()`:

```python
def _ensure_tunnel(self):
    if not self._use_tunnel:
        return
    if self._tunnel and self._tunnel.is_alive():
        return  # tunnel working, base_url already set
    # Tunnel dead or not yet established
    if self._tunnel:
        # Was alive, now dead — try reconnect
        port = self._tunnel.reconnect(self._tunnel_config)
        if port:
            self._base_url = f"http://localhost:{port}"
            return
    # Fresh establishment (or reconnect failed)
    config = resolve_tunnel_config(self._auth_token, self._original_base_url,
                                    force_refresh=bool(self._tunnel))
    if config:
        tunnel = SSHTunnel()
        port = tunnel.establish(config)  # uses ~/.ssh/id_argus_proxy written by resolve_tunnel_config
        if port:
            self._tunnel = tunnel
            self._tunnel_config = config
            self._base_url = f"http://localhost:{port}"
            return
    # Total failure — fall back, delete cached key
    _delete_cached_key()
    LOGGER.warning("SSH tunnel unavailable, using direct connection: %s", self._original_base_url)
    self._base_url = self._original_base_url
    self._tunnel = None
    self._use_tunnel = False  # don't retry this session
```

### Step 7: Python CLI integration

Add `--use-tunnel` / `ARGUS_USE_TUNNEL` option to CLI commands in `generic/cli.py` and `driver_matrix_tests/cli.py`. Forward to client constructor.

### Step 7b: Go CLI — `argus-cli ssh-keys` command

Add `ssh-keys` subcommand to the Go CLI (`cli/`). This is called by sshd's `AuthorizedKeysCommand` on the proxy host.

```
argus-cli ssh-keys
```

Behavior:

1. Calls `GET /api/v1/client/ssh/keys` with configured auth token
2. Prints non-expired public keys to stdout, one per line (OpenSSH `authorized_keys` format)
3. Exit code 0 on success, non-zero on failure (sshd falls through to next auth method)
4. Must be fast — sshd blocks the SSH handshake until this returns

**Proxy host deployment:** Binary at `/usr/local/bin/argus-cli`, owned by root, mode 0755. Config via env vars embedded in the `argus-authorized-keys` wrapper script.

### Step 9: Tests

Status: Partially done in PR #967 (backend tunnel tests for service/API).

**`argus/client/tests/test_tunnel.py`:**

- `test_ssh_not_available` — `shutil.which` returns None, fallback
- `test_establish_success` — mock Popen + socket
- `test_reconnect_success` / `test_reconnect_exhausted`
- `test_resolve_from_cached_key` / `test_resolve_expired_key`
- `test_resolve_from_api` — mock HTTP, verify key written to `~/.ssh/id_argus_proxy`
- `test_fallback_on_failure` — verify base_url unchanged, warning logged
- `test_atexit_cleanup` — verify process terminated
- `test_key_file_permissions` — verify `~/.ssh/id_argus_proxy` is 0600
- `test_host_key_verification` — verify known_hosts file written, StrictHostKeyChecking=yes
- `test_ttl_seconds_forwarded` — verify client passes ttl_seconds to API

**`argus/backend/tests/test_tunnel_service.py`:**

- Test public key registration and storage in DB
- Test custom ttl_seconds
- Test get_authorized_keys output format (valid OpenSSH authorized_keys)
- Test key deletion
- Test API returns correct proxy config response
- Test row inserted with ScyllaDB TTL

**`argus/backend/tests/test_admin_proxy_tunnel.py`:**

- Test proxy tunnel config CRUD (admin only)
- Test non-admin cannot access proxy tunnel config endpoints
- Test key list / delete endpoints

**`cli/cmd/ssh_keys_test.go`:**

- Test `ssh-keys` command calls `GET /api/v1/client/ssh/keys`
- Test output format (one key per line)
- Test error handling (API unavailable, auth failure)

---

## Files to Create/Modify

| File                                                   | Action     | Description                                                      |
| ------------------------------------------------------ | ---------- | ---------------------------------------------------------------- |
| `argus/backend/models/ssh_key.py`                      | **CREATE** | SSHTunnelKey + ProxyTunnelConfig models                          |
| `argus/backend/models/web.py`                          | **MODIFY** | Import + add to USED_MODELS                                      |
| `argus/backend/service/tunnel_service.py`              | **CREATE** | Public key registration, authorized keys query, tunnel API logic |
| `argus/backend/controller/ssh_api.py`                  | **CREATE** | Flask blueprint for client tunnel + authorized keys endpoints    |
| `argus/backend/controller/client_api.py`               | **MODIFY** | Register ssh_api blueprint                                       |
| `argus/backend/controller/admin_api.py`                | **MODIFY** | Add proxy tunnel config + key management endpoints               |
| `argus/backend/templates/provision_proxy_tunnel.sh.j2` | **CREATE** | Proxy host provisioning Jinja template                           |
| `argus/client/tunnel.py`                               | **CREATE** | SSHTunnel, TunnelConfig, resolve_tunnel_config                   |
| `argus/client/base.py`                                 | **MODIFY** | Add use_tunnel param, \_ensure_tunnel()                          |
| `argus/client/generic/cli.py`                          | **MODIFY** | Add --use-tunnel option                                          |
| `argus/client/driver_matrix_tests/cli.py`              | **MODIFY** | Add --use-tunnel option                                          |
| `cli/cmd/ssh_keys.go`                                  | **CREATE** | `argus-cli ssh-keys` command for AuthorizedKeysCommand           |
| `cli/cmd/ssh_keys_test.go`                             | **CREATE** | Tests for ssh-keys command                                       |
| `frontend/AdminPanel/AdminPanel.svelte`                | **MODIFY** | Add "SSH Tunnel" to sidebar nav                                  |
| `frontend/AdminPanel/ProxyTunnelManager.svelte`        | **CREATE** | Proxy tunnel config + SSH key management UI                      |
| `argus/client/tests/test_tunnel.py`                    | **CREATE** | Client tunnel tests                                              |
| `argus/backend/tests/test_tunnel_service.py`           | **CREATE** | Backend tunnel service tests                                     |
| `argus/backend/tests/test_admin_proxy_tunnel.py`       | **CREATE** | Admin proxy tunnel API tests                                     |

## Verification

1. **Unit tests:** `pytest argus/client/tests/test_tunnel.py`, `pytest argus/backend/tests/test_tunnel_service.py`, `pytest argus/backend/tests/test_admin_proxy_tunnel.py`, `go test ./cli/cmd/...`
2. **Manual test:**
    - Admin: configure proxy host via Admin Panel → SSH Tunnel section
    - Set `ARGUS_USE_TUNNEL=1` and `ARGUS_AUTH_TOKEN=<token>`
    - Run argus client command → first call hits API via Cloudflare, gets key+config, establishes tunnel, subsequent calls go through tunnel
    - Kill ssh process → client reconnects transparently
    - Admin: delete key via admin panel → next reconnect gets fresh key
    - Wait for key expiry → client re-requests key automatically
    - Unset `ARGUS_USE_TUNNEL` → direct Cloudflare connection as before
    - No `ssh` binary → warning logged, Cloudflare fallback
3. **AuthorizedKeysCommand test:**
    - On proxy host: `sudo -u nobody /usr/local/bin/argus-authorized-keys` → should output valid public keys
    - SSH as argus-proxy with a valid key → tunnel works
    - Delete key from admin panel → SSH rejected on next attempt
