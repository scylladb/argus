---
status: draft
domain: client
created: 2026-04-08
last_updated: 2026-04-20
owner: null
---

# SSH Tunnel Support for Argus Client

## Context

Automated traffic (SCT, dtest) routes through Cloudflare (HTTPS), incurring costs. This design adds an SSH tunnel in the Argus Python client to route traffic directly to the internal backend via a proxy host.

### Design Principles

- **Client-generated keypairs** — Clients generate ed25519 keypairs locally using Python's `cryptography` library. Only the public key is sent to Argus and stored in DB; the private key never leaves the client. This follows standard SSH key registration practices.
- **Single client per host** — no multi-client coordination needed.
- **DB-backed proxy tunnel config** — connection details stored in DB and managed via admin panel (not YAML config).
- **Real-time key lookup** — proxy host uses sshd `AuthorizedKeysCommand` to fetch the offered key from the Argus API on each SSH auth attempt (via argus-cli). No `authorized_keys` file management.
- **One key per lookup** — sshd passes the fingerprint of the offered key as the `%f` token. The backend answers with that one key, not the whole key table. See "Fingerprint-scoped key lookup" below.
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
4. If tunnel dies mid-session: the monitor thread tears it down and re-establishes on a backoff ladder
5. On process exit: `atexit` handler terminates SSH subprocess

### Graceful Fallback and Reconnect

The `argus-tunnel-monitor` daemon thread owns every tunnel state transition.
`TunneledSession.request()` never spawns SSH and never blocks on it.

If the `ssh` binary is missing, or the tunnel fails to establish:

- `LOGGER.warning(...)` once per outage, naming the reason
- Traffic falls back to the original `base_url` (Cloudflare) immediately
- No exceptions propagate — the client keeps working

The monitor keeps re-attempting in the background:

1. Nothing happens until the session has made `ARGUS_TUNNEL_MIN_REQUESTS`
   requests (default 10). See "Paying for the handshake" below.
2. After a failure the next attempt is delayed, and the delay doubles from
   `ARGUS_TUNNEL_RETRY_MIN_SECONDS` (default 30) up to
   `ARGUS_TUNNEL_RETRY_MAX_SECONDS` (default 600).
3. Each delay carries ±20 % jitter. A fleet of CI runners that lose one proxy
   at the same moment must not retry in lockstep against its replacement.
4. On success the delay resets and the log records `SSH tunnel restored`.
   Later requests move back onto the tunnel with no client restart.

When a request through the tunnel raises `ConnectionError`, the request thread
flags the tunnel and retries directly. The monitor tears the tunnel down on its
next tick. The caller never waits on SSH.

### Paying for the handshake

Building a tunnel is not free. It costs one registration call from the client
and one authorized-keys lookup from the proxy host, and both travel direct
because they are what create the tunnel. A process that makes two requests and
exits therefore adds public traffic instead of removing it.

Measured on production, the handshake ran at 25.3 requests per minute while the
tunnel carried 7.6. The tunnel was costing more public requests than it moved.

Two changes address it, one in each repository:

- **The client does not tunnel until it is worth it.** `TunneledSession` counts
  requests and the monitor stays idle below `ARGUS_TUNNEL_MIN_REQUESTS`
  (default 10). A one-shot client such as `argus-client-generic submit` never
  handshakes. A long SCT run passes the threshold in seconds and loses ten
  direct requests out of thousands.
- **The proxy host looks keys up over the private network.** The
  `AuthorizedKeysCommand` runs once per SSH authentication attempt. Pointing it
  at the public URL sends every one of those through Cloudflare, from inside the
  VPC, to reach a backend the host already forwards TCP to. The `argus_tunnel`
  role defaults `argus_tunnel_keys_url` to the backend's private address.

### Proxy failover

The tunnel API returns a `proxies` array holding every active proxy, best
choice for this user first. `TunnelConfig.candidates()` exposes them in order,
and each establish attempt walks the whole list before it gives up. A dead
primary therefore costs one extra SSH connect timeout, not a full backoff
window on the public endpoint.

The array is additive. A client that predates it reads only the scalar
`proxy_host` / `proxy_port` fields and behaves exactly as before.

### Proxy selection

`_ordered_active_configs(user_id)` scores each active proxy with
`sha256(f"{user_id}:{config.id}")` and sorts by the score. That is rendezvous
hashing. Three properties matter:

- **No shared state.** The previous design kept a counter in a single
  `RuntimeStore` row and rewrote it on every registration. That is one
  contended partition under concurrent CI load, and lost updates skewed the
  distribution it was meant to even out.
- **Stable per user.** A client's cached config and a later `GET /ssh/tunnel`
  name the same primary. Under the old counter they could disagree, so a
  re-registration could silently move a client to a different proxy.
- **Minimal churn.** Adding or retiring a proxy only reassigns the users that
  proxy owns, about 1/N of them. Rotating the list by `hash % len` would give
  the same load spread but reassign roughly 2/N — measured at 67 % against
  33 % when a third proxy joins two.

Different users still get different primaries, so load spreads.

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
    AuthorizedKeysCommand /usr/local/bin/argus-authorized-keys %f
    AuthorizedKeysCommandUser nobody
```

**`AuthorizedKeysCommand` explanation:** On each SSH connection attempt by `argus-proxy`, sshd runs the `argus-authorized-keys` wrapper script. sshd expands the `%f` token to the SHA-256 fingerprint of the key the client offered, and passes it as `$1`. The wrapper calls `argus ssh keys list --fingerprint "$1"`, which hits `GET /api/v1/client/ssh/keys?fingerprint=...` and gets back that one key. sshd uses the output as the authorized_keys for that connection. This eliminates all file sync, race conditions, and stale state — key validity is always real-time from DB.

The `%f` token needs OpenSSH 6.9 or later.

### Fingerprint-scoped key lookup

Before this change the endpoint scanned the whole `SSHTunnelKey` table and
returned every non-expired key of every user, on every authentication attempt.
With hundreds of concurrent CI runners each holding a 24 h key, the transfer
grew with the size of the fleet.

Three parts fixed it:

1. `SSHTunnelKeyByFingerprint` keys the fingerprint as the partition key, so the
   lookup is an exact match instead of a table scan. See "Why a table, not a
   secondary index" below.
2. `get_authorized_keys(fingerprint=...)` returns only the matching key. An
   unknown fingerprint returns an empty body, which sshd reads as a denial. A
   malformed fingerprint gets a plain-text 400, never a JSON error body.
3. The Go client sets `IdentitiesOnly=yes`. Without it `ssh` offers every agent
   key and default identity before `-i`, and each rejected offer costs the
   proxy host one more lookup and one more `MaxAuthTries` slot. The Go client
   does not set `PubkeyAcceptedAlgorithms`, because that option needs OpenSSH
   8.5 and the CLI also runs on developer machines with older clients, where an
   unknown option makes `ssh` exit 255.

The lookup is not scoped by tunnel. All proxies front the same backend, so a
key registered against one proxy and accepted by another is not an escalation.
Scoping would instead break for a client whose primary proxy is down and that
has failed over to another one.

Calls that omit `fingerprint` still get the full list, with a warning in the
log. That path exists only for proxy hosts that still run the old wrapper.
Re-apply the `argus_tunnel` role from `qatools-deployments` on those hosts, then
remove the path.

### Why a table, not a secondary index

A secondary index on `SSHTunnelKey.fingerprint` is a materialized view.
ScyllaDB applies the view update after it acknowledges the base write, so a
read through the index can miss a row that the base table already holds.

That window sits on the authentication path. A client registers a key and
connects at once, and the SSH attempt is the request right after the write. An
index miss reads as "no authorized key", so the client is denied. Client retry
hides it, but every denial costs an SSH round trip and one `MaxAuthTries` slot,
and hundreds of CI runners registering together widen the window.

`SSHTunnelKeyByFingerprint` is a plain table with `fingerprint` as the partition
key and `key_id` as the clustering key. Argus writes it on the registration path
and reads it by partition key. Both operations run at `QUORUM`, so the read that
follows the write always sees the row.

The cost is manual consistency:

1. `register_tunnel` writes both tables. It also repairs a missing lookup row
   when a client registers a key it already holds.
2. `delete_key` removes the lookup row first, then the key. A revoked key that
   still authenticates is worse than a lookup row with no key behind it.
3. Both rows carry the same TTL, so ScyllaDB expires them together.

Keys registered before the table existed have no lookup row. Run
`scripts/migration/migration_2026-08-03.py` after `flask cli sync-models` and
before the new backend takes traffic. Then drop the now-unused secondary index
on `ssh_tunnel_key.fingerprint`.

**Proxy host provisioning lives in `qatools-deployments`, not in this repository.**

The `argus_tunnel` Ansible role owns the proxy host: the restricted accounts, the
Argus CLI, the credentials file, the `AuthorizedKeysCommand` wrapper, and the sshd
drop-in. This repository ships the API and the CLI that the role installs.

The role turns the `%f` token on only when the Argus CLI on the host accepts
`--fingerprint`. An older binary exits non-zero, and sshd reads that as "no
authorized keys", so it would reject every client. Raise
`argus_tunnel_cli_version` and `cli_tools_argus_version` together once a release
carries the flag.

**Proxy host requirements:**

- `argus` binary installed at `/usr/local/bin/argus`, owned by root and not writable by group or others, which sshd requires
- `argus-authorized-keys` wrapper at `/usr/local/bin/argus-authorized-keys`, root-owned 0755
- Credentials in a separate 0640 file owned by root and readable only by the `AuthorizedKeysCommandUser` account. Never embed the token in the wrapper: sshd requires the wrapper to be world-readable
- OpenSSH 6.9 or later, for the `%f` token

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
- [x] Step 4b: Admin API - `argus/backend/controller/admin_api.py`
- [x] Step 9 (partial): backend tunnel tests (`argus/backend/tests/tunnel/test_tunnel_service.py`, `argus/backend/tests/tunnel/test_ssh_api.py`, `argus/backend/tests/tunnel/test_admin_proxy_tunnel_api.py`) (done in PR #967)
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

Add to `USED_MODELS`. Managed via admin panel (Step 4d).

**Multi-host active mode:** Multiple proxy hosts may be active at the same time (`is_active=True`).

- Tunnel registration and tunnel-info endpoints return **every** active host,
  ordered by a stable rotation keyed on the requesting user.
- Admin can disable a host by setting `is_active=False`.
- Disabled hosts remain in DB for audit/re-enable workflows.

**Service user per proxy host:** When admin saves a new proxy tunnel config, the backend automatically creates a dedicated Argus user (e.g., `proxy-tunnel-<host>`) with a fresh API token. This token is deployed to the proxy host during provisioning for argus-cli to call the authorized keys endpoint. Access is role-scoped (`ROLE_SSH_TUNNEL_SERVER`) and hard-limited to `GET /api/v1/client/ssh/keys`.

`admin_user` and `admin_key_path` (SSH credentials for provisioning access to the proxy host) are stored in `argus_web.yaml`.

### Step 3: Backend service — `argus/backend/service/tunnel_service.py`

Status: Done in PR #967.

Class `TunnelService`:

- `register_tunnel(user: User, public_key: str, ttl_seconds: int = None) -> dict`:
    1. Store `SSHTunnelKey` in DB (public key only) with ScyllaDB TTL (default 86400s / 24h, or client-provided `ttl_seconds`). Set `expires_at = now_utc + ttl` for informational purposes.
    2. Order active `ProxyTunnelConfig` rows for this user and take the first as primary
    3. Return `{proxy_host, proxy_port, proxy_user, target_host, target_port, host_key_fingerprint, expires_at, proxies}` (all datetimes UTC ISO-8601)

- `get_tunnel_connection(user_id: UUID, proxy_host: str | None = None) -> dict`:
    1. Return the primary proxy for `user_id` plus a `proxies` list holding every active proxy
    2. `proxy_host` pins a specific primary; the rest of the list still follows so failover keeps working

- `get_authorized_keys(fingerprint: str | None = None) -> str`:
    1. With a fingerprint: validate the `SHA256:<43-char base64>` shape, then fetch the single matching `SSHTunnelKey` by indexed lookup
    2. Without one: fetch all records and log a deprecation warning (old proxy wrappers only)
    3. Return newline-separated public keys in OpenSSH `authorized_keys` format
    4. Called by proxy host via `AuthorizedKeysCommand` → argus-cli → this API

- `delete_key(key_id: UUID)`:
    1. Delete `SSHTunnelKey` row from DB
    2. Takes immediate effect — next `AuthorizedKeysCommand` call won't include it

- `get_proxy_tunnel_config() -> ProxyTunnelConfig | None`:
    1. Return one deterministic active proxy tunnel config (for admin panel display)
    2. Non-mutating. Proxy selection holds no shared state, so an admin read cannot disturb it.

- `save_proxy_tunnel_config(payload: dict) -> ProxyTunnelConfig`:
    1. Create a proxy tunnel config row (active by default, or explicitly disabled via `is_active=false`)
    2. Create a dedicated Argus service user for this proxy host (e.g., `proxy-tunnel-<host>`), generate API token
    3. Verify `host_key_fingerprint` by running `ssh-keyscan` against `host:port` and comparing discovered fingerprint with the provided value
    4. Save proxy tunnel config with `service_user_id` and verified `host_key_fingerprint`
    5. Run provisioning script on the proxy host (Step 4c), passing the service user's API token
    6. On success: keep requested active state. On failure: mark inactive, return error.
    7. Return saved config

- `list_proxy_tunnel_configs(active_only: bool | None = None) -> list[ProxyTunnelConfig]`:
    1. Return all configs, optionally filtered by active state

- `set_proxy_tunnel_config_active(tunnel_id: UUID, is_active: bool) -> ProxyTunnelConfig`:
    1. Enable or disable a specific proxy host config

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
    try:
        keys = TunnelService().get_authorized_keys(fingerprint=request.args.get("fingerprint"))
    except TunnelServiceException:
        return Response("", mimetype="text/plain", status=400)
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
    # tunnel_id is optional:
    # - without tunnel_id: returns one deterministic active config (non-mutating)
    # - with tunnel_id: returns that config only if it is active
    config = TunnelService().get_proxy_tunnel_config(tunnel_id=request.args.get("tunnel_id"))
    return {"status": "ok", "response": config}

@bp.route("/proxy-tunnel/configs", methods=["GET"])
@api_login_required
@check_roles(UserRoles.Admin)
def list_proxy_tunnel_configs():
    # active_only is optional: "true" or "false"
    configs = TunnelService().list_proxy_tunnel_configs(active_only=request.args.get("active_only"))
    return {"status": "ok", "response": configs}

@bp.route("/proxy-tunnel/config", methods=["POST"])
@api_login_required
@check_roles(UserRoles.Admin)
def save_proxy_tunnel_config():
    payload = request.get_json()
    config = TunnelService().save_proxy_tunnel_config(payload)
    return {"status": "ok", "response": config}

@bp.route("/proxy-tunnel/config/<tunnel_id>/active", methods=["POST"])
@api_login_required
@check_roles(UserRoles.Admin)
def set_proxy_tunnel_config_active(tunnel_id):
    payload = request.get_json()
    config = TunnelService().set_proxy_tunnel_config_active(UUID(tunnel_id), payload["is_active"])
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
- Host Key Fingerprint (required input; backend verifies it with `ssh-keyscan` before saving)
- Service User (read-only, auto-created — shows the dedicated Argus user + token created for this proxy host)
- Active toggle (boolean; multiple hosts can be active at the same time)
- Save button → triggers provisioning script on the proxy host. On success: config saved + active. On failure: error message shown, config not activated.
- Re-provision button (re-run provisioning on existing proxy host, e.g., after argus-cli update)
- Deactivate button (sets `is_active=false` for that host)

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

**The shipped code diverges from this sketch.** Three differences matter:

- The keypair is never deleted on failure. It stays valid while the proxy host
  is unreachable, and deleting it would force a pointless re-registration over
  Cloudflare on every retry.
- The tunnel is never disabled for the rest of the session. The monitor thread
  keeps retrying with an escalating jittered delay, so a run that starts during
  a proxy outage still moves onto the tunnel once the proxy returns. See
  "Graceful Fallback and Reconnect" above.
- `request()` does not establish or reconnect. Only the monitor thread does.

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
