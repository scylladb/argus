#!/usr/bin/env bash
# Argus SSH proxy-tunnel provisioning script.
# Run as root on the proxy host. Idempotent — safe to re-run.
#
# Usage:
#   tunnel-server-setup.sh --token <api-token> --target-host <ip> [options]
#
# Required flags:
#   --token           <str>   Argus API token (ROLE_SSH_TUNNEL_SERVER)
#   --target-host     <str>   Private IP / hostname of the Argus backend
#   --cf-client-id    <str>   Cloudflare Access service-token client ID
#   --cf-client-secret <str>  Cloudflare Access service-token client secret
#
# Optional flags:
#   --target-port     <int>   Argus internal port            (default: 80)
#   --proxy-user      <str>   OS user for tunnel connections  (default: argus-proxy)
#   --argus-bin       <str>   Path to the argus binary        (default: /usr/local/bin/argus)
#   --argus-url       <str>   Public Argus URL                (default: https://argus.scylladb.com)
set -euo pipefail
umask 027

# ── Defaults ─────────────────────────────────────────────────────────────────
TARGET_PORT="80"
PROXY_USER="argus-proxy"
ARGUS_CLI_SRC="/usr/local/bin/argus"
ARGUS_URL="https://argus.scylladb.com"
TARGET_HOST=""
ARGUS_AUTH_TOKEN=""
CF_CLIENT_ID=""
CF_CLIENT_SECRET=""

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --token)             ARGUS_AUTH_TOKEN="$2"; shift 2 ;;
        --target-host)       TARGET_HOST="$2";      shift 2 ;;
        --target-port)       TARGET_PORT="$2";      shift 2 ;;
        --proxy-user)        PROXY_USER="$2";       shift 2 ;;
        --argus-bin)         ARGUS_CLI_SRC="$2";    shift 2 ;;
        --argus-url)         ARGUS_URL="$2";        shift 2 ;;
        --cf-client-id)      CF_CLIENT_ID="$2";     shift 2 ;;
        --cf-client-secret)  CF_CLIENT_SECRET="$2"; shift 2 ;;
        *) echo "Unknown flag: $1" >&2; exit 1 ;;
    esac
done

# ── Validation ────────────────────────────────────────────────────────────────
die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]]            || die "must be run as root"
[[ -n "$ARGUS_AUTH_TOKEN" ]]  || die "--token is required"
[[ -n "$TARGET_HOST" ]]       || die "--target-host is required"
[[ -n "$CF_CLIENT_ID" ]]      || die "--cf-client-id is required (Cloudflare Access service token)"
[[ -n "$CF_CLIENT_SECRET" ]]  || die "--cf-client-secret is required (Cloudflare Access service token)"
[[ -f "$ARGUS_CLI_SRC" ]]     || die "argus binary not found at $ARGUS_CLI_SRC — copy it first:  scp /path/to/argus argus-tunnel-1:$ARGUS_CLI_SRC"

# ── 1. Restricted proxy OS user ──────────────────────────────────────────────
if ! id "$PROXY_USER" &>/dev/null; then
    useradd \
        --system \
        --no-create-home \
        --shell /usr/sbin/nologin \
        --comment "Argus SSH tunnel proxy (no login)" \
        "$PROXY_USER"
    echo "Created user: $PROXY_USER"
else
    echo "User $PROXY_USER already exists — skipping"
fi
passwd -l "$PROXY_USER" &>/dev/null || true

# ── 2. Write argus-authorized-keys wrapper ────────────────────────────────────
# All credentials are embedded directly — sourcing an env file does not work
# when sshd invokes this as AuthorizedKeysCommandUser nobody.
# CF Access service-token headers are required to pass through Cloudflare before
# the Argus ARGUS_TOKEN can authenticate with the backend.
cat > /usr/local/bin/argus-authorized-keys << WRAPPER
#!/usr/bin/env bash
set -euo pipefail
export ARGUS_TOKEN="${ARGUS_AUTH_TOKEN}"
export ARGUS_CF_ACCESS_CLIENT_ID="${CF_CLIENT_ID}"
export ARGUS_CF_ACCESS_CLIENT_SECRET="${CF_CLIENT_SECRET}"
exec /usr/local/bin/argus \\
    ssh keys list \\
    --url "${ARGUS_URL}" \\
    --use-cloudflare=false \\
    --no-cache \\
    --non-interactive
WRAPPER

chown root:root /usr/local/bin/argus-authorized-keys
chmod 0755 /usr/local/bin/argus-authorized-keys
echo "Wrote /usr/local/bin/argus-authorized-keys"

# ── 3. sshd drop-in config ───────────────────────────────────────────────────
mkdir -p /etc/ssh/sshd_config.d

cat > /etc/ssh/sshd_config.d/99-argus-proxy.conf << SSHDEOF
# Argus SSH tunnel proxy — managed by tunnel-server-setup.sh
# Do not edit by hand; re-run the provisioning script to update.

PasswordAuthentication no
ChallengeResponseAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes

Match User ${PROXY_USER}
    AllowTcpForwarding local
    PermitOpen ${TARGET_HOST}:${TARGET_PORT}
    GatewayPorts no
    X11Forwarding no
    AllowAgentForwarding no
    PermitTTY no
    ForceCommand /bin/false
    AuthorizedKeysFile none
    AuthorizedKeysCommand /usr/local/bin/argus-authorized-keys
    AuthorizedKeysCommandUser nobody
    ClientAliveInterval 600
    ClientAliveCountMax 1
    MaxSessions 5
SSHDEOF

chown root:root /etc/ssh/sshd_config.d/99-argus-proxy.conf
chmod 0644 /etc/ssh/sshd_config.d/99-argus-proxy.conf
echo "Wrote /etc/ssh/sshd_config.d/99-argus-proxy.conf"

# ── 4. Validate and reload sshd ──────────────────────────────────────────────
echo "Validating sshd configuration..."
sshd -t || die "sshd config validation failed — NOT restarting sshd."

if systemctl reload sshd 2>/dev/null || systemctl reload ssh 2>/dev/null; then
    echo "sshd reloaded"
else
    systemctl restart sshd 2>/dev/null || systemctl restart ssh \
        || die "Cannot reload/restart sshd — do it manually"
    echo "sshd restarted"
fi

# ── 5. Smoke-test ─────────────────────────────────────────────────────────────
echo "Verifying API connectivity..."
if sudo -u nobody /usr/local/bin/argus-authorized-keys > /dev/null 2>&1; then
    echo "API connectivity OK"
else
    echo "WARNING: argus-authorized-keys returned non-zero — check credentials and --argus-url." >&2
fi

echo ""
echo "Done."
echo "  User:              $PROXY_USER"
echo "  Tunnel target:     $TARGET_HOST:$TARGET_PORT"
echo "  Argus URL:         $ARGUS_URL"
echo "  argus binary:      $ARGUS_CLI_SRC"
echo "  AuthorizedKeysCmd: /usr/local/bin/argus-authorized-keys"
echo "  sshd drop-in:      /etc/ssh/sshd_config.d/99-argus-proxy.conf"
