# SSH Tunnel Support for Argus Client

## Context

Automated traffic (SCT, dtest) currently routes through Cloudflare (HTTPS), incurring unnecessary costs. This change adds an embedded SSH tunnel in the Argus Python client that routes traffic directly to the internal Argus backend via an SSH bastion, with automatic key registration and tunnel lifecycle management.

**Current flow:** Client -> Cloudflare (HTTPS) -> Argus Service
**New flow:** Client -> SSH Tunnel -> Bastion -> Argus Service (internal)

---

## Architecture

### Key Registration Flow (one-time per client)
1. Client has `ARGUS_SSH_KEY_PATH` env var pointing to SSH private key
2. Client checks for local config file (`~/.argus/tunnel_config.json`)
3. If no config:
   - Reads public key from `{key_path}.pub` (convention)
   - If `.pub` not found, falls back to `ARGUS_SSH_PUB_KEY_PATH` / `--ssh-pub-key`
   - Calls Argus backend `POST /api/v1/client/ssh/register` with the public key
4. Backend stores the public key in DB, SSHes into bastion as admin to write full `authorized_keys` (not append — full rewrite from DB, ensuring consistency)
5. Backend responds with bastion details: `{bastion_host, bastion_port, bastion_user, target_host, target_port}`
6. Client saves config locally for future use

### Config Invalidation
The cached `~/.argus/tunnel_config.json` includes a `bastion_host` field. If the tunnel fails to establish (SSH connection refused / timeout to bastion), the client:
1. Deletes the stale config file
2. Re-calls the registration API to get fresh bastion details
3. Saves the new config and retries tunnel establishment
4. If that also fails, **deletes the config file** (so next process start doesn't reuse broken config) and falls back to direct Cloudflare connection

### Tunnel Lifecycle (lazy, shared across clients)
1. Client constructed with SSH config (env vars or constructor params) — no tunnel yet
2. On first HTTP request, tunnel is lazily established via `ssh -N -L` subprocess
3. The SSH process is **daemonized** (`start_new_session=True` in Popen) — it runs independently of any client process. No `PR_SET_PDEATHSIG` — the tunnel survives client exits so other clients can continue using it.
4. Before each request, client checks tunnel liveness by probing the local port with `socket.connect_ex`. If dead, reconnects (up to 3 retries).
5. Each client updates an **activity timestamp** file (`/tmp/argus-ssh-tunnel/tunnel.last_activity`) on every request.
6. No client kills the tunnel on exit. Idle cleanup happens via:
   - **Lazy cleanup by next client:** when a new client tries to reuse the tunnel, if `last_activity` is older than 5 min, it kills the idle tunnel and starts fresh
   - **Bastion-side backstop:** sshd_config for `argus-proxy` sets `ClientAliveInterval 300` + `ClientAliveCountMax 3` — if no SSH activity for ~15 min (truly abandoned), bastion kills the connection

### Multi-Client Sharing
Multiple argus clients on the same host share a single SSH tunnel:
- First client spawns the tunnel, writes PID + port to lock files
- Subsequent clients discover the tunnel via PID/port files, verify it's alive, and reuse it (`_owns_process = False`)
- No client kills the tunnel — it's shared infrastructure
- All clients update the activity timestamp, keeping the tunnel alive as long as any client is active
- SSH is spawned **without** `ServerAliveInterval` (no client-side keepalive) so the connection is "quiet" when no forwarding happens, allowing the bastion's `ClientAliveInterval` to detect true abandonment
- Dead tunnel detection uses `socket.connect_ex` on the local port, not SSH keepalive

### Lock/State Files (`/tmp/argus-ssh-tunnel/`)
- `tunnel.pid` — PID of the SSH process
- `tunnel.port` — local port number (so reusing clients know which port to connect to)
- `tunnel.last_activity` — timestamp of last HTTP request through the tunnel

### Graceful Fallback
If SSH binary is missing, tunnel fails to establish, or tunnel dies and reconnection fails:
- Log a clear `LOGGER.warning(...)` message explaining what failed
- Fall back to the original `base_url` (Cloudflare)
- No exceptions propagate to the caller — the client continues to work

### Authorized Keys Sync
Keys are synced to the bastion in two ways:
1. **On each key registration/unregistration** — the API handler calls `sync_authorized_keys()` which does a full rewrite of the bastion's `authorized_keys` from the DB
2. **Via CLI command** — `flask sync-ssh-keys` (or equivalent management command) for manual sync after bastion recreation or config changes

No automatic startup sync (avoids multi-worker race conditions). The config file includes a comment documenting that this CLI should be run after changing bastion config.

---

## Bastion Host Setup

### Infrastructure (AWS)
- **Region:** eu-north-1
- **VPC:** sct-vpc2 (same VPC as Argus for internal connectivity)
- **Instance type:** t3.micro (tunneling only, minimal resources)
- **Security group:** Allow inbound SSH (port 22) from SCT/dtest runner IPs; allow outbound to Argus internal host:port

### OS Configuration

**Users:**
- `admin` — full shell access for maintenance (key-based auth only)
- `argus-proxy` — restricted service account for tunnel clients

**sshd_config for argus-proxy:**
```
Match User argus-proxy
    AllowTcpForwarding yes
    PermitOpen <argus-private-ip>:8080
    X11Forwarding no
    AllowAgentForwarding no
    ForceCommand /bin/false
    PermitTTY no
    ClientAliveInterval 300
    ClientAliveCountMax 3
```

The `ClientAliveInterval`/`ClientAliveCountMax` settings ensure abandoned tunnels (where no client is active and no SSH keepalive is sent) are automatically closed by the bastion after ~15 minutes.

This ensures `argus-proxy` can only do TCP forwarding to the specific Argus internal endpoint — no shell, no file transfer, no other forwarding targets.

**Global sshd_config:**
```
PasswordAuthentication no
PubkeyAuthentication yes
```

### Configuring argus-internal (target_host)

The `target_host` in the bastion config is the **private IP address** of the Argus instance within sct-vpc2. Since the bastion and Argus are in the same VPC, they communicate over private networking.

To find the Argus private IP:
1. In AWS Console: EC2 -> Instances -> find Argus instance -> copy "Private IPv4 address"
2. Or via CLI: `aws ec2 describe-instances --filters "Name=tag:Name,Values=argus-*" --query 'Reservations[].Instances[].PrivateIpAddress'`

Example: if Argus private IP is `10.0.1.42` and it listens on port `8080`:
- `target_host: "10.0.1.42"`
- `target_port: 8080`
- `PermitOpen 10.0.1.42:8080` in sshd_config

### Argus Backend Config (`argus_web.yaml`)
```yaml
# SSH Bastion configuration for client tunnel support.
# After changing bastion host/credentials, run: flask sync-ssh-keys
bastion:
  host: bastion.example.com       # public hostname/IP of the bastion
  port: 22
  admin_user: admin               # user with shell access for key management
  admin_key_path: /path/to/key    # private key for admin SSH access to bastion
  proxy_user: argus-proxy         # restricted tunnel-only user
  target_host: "10.0.1.42"       # Argus private IP within sct-vpc2
  target_port: 8080              # Argus internal port
```

### Bastion Recreation Procedure
1. Launch new t3.micro in eu-north-1, sct-vpc2 VPC
2. Configure OS users (`admin`, `argus-proxy`) and sshd_config as above
3. Update `argus_web.yaml` with new bastion host
4. Run `flask sync-ssh-keys` to push all registered keys to the new bastion
5. Clients with stale `tunnel_config.json` will auto-invalidate and re-register on next use

---

## Implementation Plan

### Step 1: New model — `argus/backend/models/ssh_key.py`

New ScyllaDB model to store registered SSH public keys:

```python
class SSHPublicKey(Model):
    user_id = columns.UUID(primary_key=True)
    key_fingerprint = columns.Text(primary_key=True, clustering_order="ASC")
    public_key = columns.Text()      # full public key string
    comment = columns.Text()          # key comment (e.g. user@host)
    registered_at = columns.DateTime()
```

Import this in `argus/backend/models/web.py` so it gets synced with the DB.

### Step 2: New backend service — `argus/backend/service/ssh_key_service.py`

Service class `SSHKeyService` with methods:

- `register_key(user: User, public_key: str) -> dict` — Validates the public key format, computes fingerprint, stores in DB, calls `sync_authorized_keys()`, returns bastion config.
- `unregister_key(user: User, key_fingerprint: str)` — Removes from DB, calls `sync_authorized_keys()`.
- `get_bastion_config() -> dict` — Returns bastion connection details from `argus_web.yaml` config.
- `sync_authorized_keys()` — Public method. Fetches ALL keys from DB, SSHes into bastion as admin, writes the complete `authorized_keys` file (full rewrite, not append). Called on registration/unregistration and via CLI.
- `_write_authorized_keys_to_bastion(keys: list[str])` — SSHes into bastion as admin, writes the full authorized_keys file atomically (write to temp file, then mv).

Bastion admin SSH credentials come from `argus_web.yaml` config (new `bastion` section).

### Step 3: Flask CLI command for key sync

Add a Flask CLI command `flask sync-ssh-keys` that calls `SSHKeyService().sync_authorized_keys()`. This is used:
- After changing bastion config in `argus_web.yaml`
- After bastion recreation
- As a manual recovery tool

Registered via `app.cli.add_command()` in the Flask app setup.

### Step 4: New backend API — `argus/backend/controller/ssh_api.py`

New Flask blueprint registered under `/client/ssh/`:

- `POST /api/v1/client/ssh/register` — `@api_login_required`. Accepts `{public_key: str}`. Calls `SSHKeyService.register_key()`. Returns `{status: "ok", response: {bastion_host, bastion_port, bastion_user, target_host, target_port}}`.
- `DELETE /api/v1/client/ssh/unregister` — `@api_login_required`. Accepts `{key_fingerprint: str}`. Removes key, syncs authorized_keys.

Register this blueprint in `client_api.py`.

### Step 5: New client module — `argus/client/tunnel.py`

#### Class `SSHTunnelConfig`
Dataclass holding: `bastion_host`, `bastion_port`, `bastion_user`, `target_host`, `target_port`, `ssh_key_path`.

#### Class `SSHTunnel`
Manages the SSH subprocess lifecycle.

**Key attributes:**
- `_process: subprocess.Popen | None`
- `_local_port: int | None`
- `_owns_process: bool`
- `_config: SSHTunnelConfig`

**Key methods:**
- `establish() -> int | None` — Checks SSH available (`shutil.which`), tries reusing existing tunnel via PID+port files at `/tmp/argus-ssh-tunnel/`, otherwise starts new. Returns local port or `None`.
- `_start_tunnel() -> int` — Finds free ephemeral port, spawns SSH subprocess daemonized (`start_new_session=True`). SSH flags: `-N -L {local_port}:{target_host}:{target_port} -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10`. No `ServerAliveInterval` — the connection stays "quiet" when idle so the bastion's `ClientAliveInterval` can detect abandonment. The full command line (e.g. `ssh -N -L 12345:10.0.1.42:8080 argus-proxy@bastion.example.com`) is visible in `ps aux` and via `ss -tnp`/`netstat -tnp`, making the tunnel's purpose identifiable by ops. Waits for port to become connectable.
- `_find_free_port() -> int` — Bind to port 0, get assigned port, close socket.
- `_wait_for_tunnel(port, timeout=10) -> bool` — Poll `socket.connect_ex` until success or timeout.
- `_try_reuse_existing() -> int | None` — Read PID from `tunnel.pid`, port from `tunnel.port`, and last activity from `tunnel.last_activity`. If activity is older than 5 min (idle), kill the old process and return None (caller will start fresh). Otherwise verify process is alive (`os.kill(pid, 0)`) and port is connectable. If both check out, set `_owns_process = False` and return the port. Otherwise clean up stale files and return None.
- `_update_activity()` — Write current timestamp to `tunnel.last_activity`. Called by `ensure_alive()` on each request.
- `is_alive() -> bool` — Process poll + socket probe.
- `reconnect() -> int | None` — Kill existing, start new, up to 3 retries.
- `ensure_alive() -> bool` — Check alive, reconnect if dead.
- `shutdown()` — Terminate subprocess, remove lock files. Only called during idle cleanup or config invalidation, never on normal client exit.
- No `atexit` handler and no `PR_SET_PDEATHSIG` — the tunnel is shared and must survive individual client exits.

**Lock/state files:** `/tmp/argus-ssh-tunnel/tunnel.pid`, `tunnel.port`, `tunnel.last_activity` (see Architecture section)

#### Function `resolve_tunnel_config`
```python
def resolve_tunnel_config(
    ssh_key_path: str,
    ssh_pub_key_path: str | None,
    auth_token: str,
    base_url: str,
    force_refresh: bool = False,
) -> SSHTunnelConfig | None
```
1. If not `force_refresh`, check for local config at `~/.argus/tunnel_config.json`.
2. If config exists and is valid, return `SSHTunnelConfig` from it.
3. Otherwise (or if `force_refresh`):
   a. Delete existing config file if present
   b. Try reading public key from `{ssh_key_path}.pub`
   c. If not found, try `ssh_pub_key_path` (from `ARGUS_SSH_PUB_KEY_PATH`)
   d. If neither found, log error and return None
   e. Call `POST {base_url}/api/v1/client/ssh/register` with auth token + public key
   f. Save response to `~/.argus/tunnel_config.json`, return config

#### Click decorator `ssh_tunnel_options`
Adds to CLI commands:
- `--ssh-key` / `ARGUS_SSH_KEY_PATH` — path to SSH private key
- `--ssh-pub-key` / `ARGUS_SSH_PUB_KEY_PATH` — path to SSH public key (fallback if `.pub` convention doesn't apply)

### Step 6: Modify `argus/client/base.py`

**Constructor changes:**
```python
def __init__(self, auth_token, base_url, api_version="v1",
             extra_headers=None, ssh_key_path=None, ssh_pub_key_path=None) -> None:
```
- `ssh_key_path` defaults to `os.environ.get("ARGUS_SSH_KEY_PATH")`
- `ssh_pub_key_path` defaults to `os.environ.get("ARGUS_SSH_PUB_KEY_PATH")`
- Store `self._original_base_url = base_url`
- `self._tunnel: SSHTunnel | None = None`
- Tunnel is NOT established here (lazy)

**New method `_ensure_tunnel()`:**
Called at the top of `get()` and `post()`:
```python
def _ensure_tunnel(self):
    if not self._ssh_key_path:
        return
    # Tunnel exists and is alive — use it
    if self._tunnel and self._tunnel.ensure_alive():
        self._base_url = f"http://localhost:{self._tunnel.local_port}"
        return
    # Tunnel exists but died — try reconnect
    if self._tunnel and not self._tunnel.is_alive():
        port = self._tunnel.reconnect()
        if port:
            self._base_url = f"http://localhost:{port}"
            return
        # Reconnect failed — maybe bastion changed? Invalidate config and retry
        LOGGER.warning("SSH tunnel reconnect failed, refreshing bastion config...")
        config = resolve_tunnel_config(
            self._ssh_key_path, self._ssh_pub_key_path,
            self._auth_token, self._original_base_url,
            force_refresh=True,
        )
        if config:
            tunnel = SSHTunnel(config)
            port = tunnel.establish()
            if port:
                self._tunnel = tunnel
                self._base_url = f"http://localhost:{port}"
                return
        # Total failure — delete config, fall back
        self._delete_tunnel_config()
        LOGGER.warning("SSH tunnel lost, falling back to direct connection: %s", self._original_base_url)
        self._base_url = self._original_base_url
        self._tunnel = None
        self._ssh_key_path = None  # Don't retry this session
        return
    # No tunnel yet — lazy establishment
    if self._tunnel is None:
        config = resolve_tunnel_config(
            self._ssh_key_path, self._ssh_pub_key_path,
            self._auth_token, self._original_base_url,
        )
        if config:
            tunnel = SSHTunnel(config)
            port = tunnel.establish()
            if port:
                self._tunnel = tunnel
                self._base_url = f"http://localhost:{port}"
                return
            # Tunnel failed — maybe stale config? Retry with fresh config
            LOGGER.warning("SSH tunnel failed, refreshing bastion config...")
            config = resolve_tunnel_config(
                self._ssh_key_path, self._ssh_pub_key_path,
                self._auth_token, self._original_base_url,
                force_refresh=True,
            )
            if config:
                tunnel = SSHTunnel(config)
                port = tunnel.establish()
                if port:
                    self._tunnel = tunnel
                    self._base_url = f"http://localhost:{port}"
                    return
        # Failed — delete config so next process doesn't reuse broken config
        self._delete_tunnel_config()
        LOGGER.warning("SSH tunnel setup failed, falling back to direct connection: %s", self._original_base_url)
        self._ssh_key_path = None  # Don't retry this session

@staticmethod
def _delete_tunnel_config():
    """Remove cached tunnel config so next process start doesn't reuse broken config."""
    config_path = Path.home() / ".argus" / "tunnel_config.json"
    config_path.unlink(missing_ok=True)
```

### Step 7: Modify CLI files

**`argus/client/generic/cli.py`** and **`argus/client/driver_matrix_tests/cli.py`:**
- Add `@ssh_tunnel_options` decorator to each command
- Forward `ssh_key` and `ssh_pub_key` params to client constructor

### Step 8: Backend config

Add `bastion` section to `argus_web.example.yaml`:
```yaml
# SSH Bastion configuration for client tunnel support.
# After changing bastion host/credentials, run: flask sync-ssh-keys
bastion:
  host: ""                    # public hostname/IP of the bastion
  port: 22
  admin_user: "admin"         # user with shell access for key management
  admin_key_path: ""          # private key for admin SSH access to bastion
  proxy_user: "argus-proxy"   # restricted tunnel-only user
  target_host: ""             # Argus private IP within sct-vpc2
  target_port: 8080           # Argus internal port
```

### Step 9: Tests

**`argus/client/tests/test_tunnel.py`** (new):
- `test_ssh_not_available_returns_none` — mock `shutil.which` -> None, verify log warning
- `test_tunnel_establish_success` — mock Popen + socket
- `test_tunnel_reuse_existing` — pre-create PID/port files, verify correct port returned
- `test_tunnel_reuse_stale_pid` — PID file with dead process, starts new tunnel
- `test_tunnel_startup_timeout` — socket never connects
- `test_reconnect_success` / `test_reconnect_exhausted`
- `test_cleanup_terminates_owned_process` / `test_cleanup_skips_reused`
- `test_resolve_config_from_cache` — config file exists
- `test_resolve_config_from_api` — mock API call, verify config saved
- `test_resolve_config_invalidation` — stale config triggers refresh
- `test_resolve_config_deleted_on_total_failure` — config file removed after all retries fail
- `test_pub_key_fallback` — `.pub` not found, uses `ARGUS_SSH_PUB_KEY_PATH`
- `test_client_fallback_on_tunnel_failure` — verify `_base_url` stays original, warning logged
- `test_idle_tunnel_killed_on_reuse` — tunnel with stale `last_activity` gets killed and restarted
- `test_active_tunnel_reused` — tunnel with recent `last_activity` is reused without restart
- `test_tunnel_daemonized` — verify `start_new_session=True` passed to Popen
- `test_no_atexit_registered` — tunnel doesn't register atexit handler (shared, nobody kills)

**`argus/backend/tests/test_ssh_key_service.py`** (new):
- Test key registration stores in DB
- Test key format validation
- Test `sync_authorized_keys` does full rewrite (mock subprocess)
- Test API endpoint returns correct bastion config
- Test unregister removes key and syncs
- Test Flask CLI command `sync-ssh-keys` calls sync

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `argus/client/tunnel.py` | **CREATE** | SSHTunnel, SSHTunnelConfig, resolve_tunnel_config, ssh_tunnel_options |
| `argus/client/base.py` | **MODIFY** | Add ssh_key_path/ssh_pub_key_path params, _ensure_tunnel(), call from get()/post() |
| `argus/client/generic/cli.py` | **MODIFY** | Add @ssh_tunnel_options, forward to client |
| `argus/client/driver_matrix_tests/cli.py` | **MODIFY** | Same as above |
| `argus/backend/models/ssh_key.py` | **CREATE** | SSHPublicKey model |
| `argus/backend/models/web.py` | **MODIFY** | Import SSHPublicKey for DB sync |
| `argus/backend/service/ssh_key_service.py` | **CREATE** | Key registration, authorized_keys sync |
| `argus/backend/controller/ssh_api.py` | **CREATE** | Flask blueprint for SSH key endpoints |
| `argus/backend/controller/client_api.py` | **MODIFY** | Register ssh_api blueprint |
| Flask app setup | **MODIFY** | Register `flask sync-ssh-keys` CLI command |
| `argus_web.example.yaml` | **MODIFY** | Add bastion config section with comment about sync CLI |
| `argus/client/tests/test_tunnel.py` | **CREATE** | Client tunnel unit tests |
| `argus/backend/tests/test_ssh_key_service.py` | **CREATE** | Backend SSH key service tests |
| `docs/bastion-setup.md` | **CREATE** | Bastion provisioning guide (AWS eu-north-1, sct-vpc2) |

## Verification

1. **Unit tests:** `pytest argus/client/tests/test_tunnel.py` — tunnel lifecycle, config resolution, fallback, config cleanup
2. **Backend tests:** `pytest argus/backend/tests/test_ssh_key_service.py` — key registration, sync, API, CLI command
3. **Manual integration test:**
   - Set `ARGUS_SSH_KEY_PATH=~/.ssh/id_ed25519` and `ARGUS_AUTH_TOKEN=<token>`
   - Run any argus client command (e.g. `argus-client-generic submit ...`)
   - Verify: first run calls register API, creates `~/.argus/tunnel_config.json`, establishes tunnel
   - Verify: subsequent runs reuse config file, reuse or re-establish tunnel
   - Verify: kill ssh process manually -> client auto-reconnects or falls back with warning log
   - Verify: unset `ARGUS_SSH_KEY_PATH` -> client uses direct Cloudflare connection as before
   - Verify: change bastion host in backend config, run `flask sync-ssh-keys` -> keys synced to new bastion
   - Verify: client with old config auto-invalidates and re-registers on next use
   - Verify: total tunnel failure -> `tunnel_config.json` is deleted, next process starts fresh
   - Verify: client A spawns tunnel, client B reuses it, client A exits -> tunnel survives, client B continues working
   - Verify: all clients exit, tunnel sits idle -> bastion kills connection after ~15 min (ClientAliveInterval)
   - Verify: new client finds idle tunnel (stale last_activity) -> kills it and starts fresh
