#!/usr/bin/env bash
set -euo pipefail

TCP_ADDR="tcp://127.0.0.1:2375"

echo "== Detecting Docker runtime mode =="

# --------------------------------------------------
# 1. Detect systemd socket activation
# --------------------------------------------------

SYSTEMD_SOCKET_ACTIVE=false

if systemctl list-units --type=socket --all | grep -q "docker.socket"; then
    # socket exists
    if systemctl is-active --quiet docker.socket; then
        SYSTEMD_SOCKET_ACTIVE=true
    fi
fi

echo "Systemd socket activation detected: $SYSTEMD_SOCKET_ACTIVE"

# --------------------------------------------------
# 2. If systemd mode → use override
# --------------------------------------------------

if [ "$SYSTEMD_SOCKET_ACTIVE" = true ]; then
    echo "== Using systemd override mode =="

    sudo mkdir -p /etc/systemd/system/docker.service.d

    cat <<EOF | sudo tee /etc/systemd/system/docker.service.d/override.conf >/dev/null
[Service]
ExecStart=
ExecStart=/usr/bin/dockerd -H unix:///var/run/docker.sock -H $TCP_ADDR
EOF

    echo "Reloading systemd..."
    sudo systemctl daemon-reload
    sudo systemctl restart docker

    echo "Done (systemd mode)."

# --------------------------------------------------
# 3. Else → fallback to daemon.json
# --------------------------------------------------
else
    echo "== Using daemon.json mode =="

    DAEMON_JSON="/etc/docker/daemon.json"

    if [ ! -f "$DAEMON_JSON" ]; then
        echo "{}" | sudo tee "$DAEMON_JSON" >/dev/null
    fi

    if command -v jq >/dev/null 2>&1; then
        echo "Updating daemon.json with jq..."

        jq --arg tcp "$TCP_ADDR" '
            .hosts = (["unix:///var/run/docker.sock", $tcp])
        ' "$DAEMON_JSON" | sudo tee "$DAEMON_JSON.tmp" >/dev/null

        sudo mv "$DAEMON_JSON.tmp" "$DAEMON_JSON"
    else
        echo "WARNING: jq not installed. Replacing daemon.json manually."

        sudo tee "$DAEMON_JSON" >/dev/null <<EOF
{
  "hosts": ["unix:///var/run/docker.sock", "$TCP_ADDR"]
}
EOF
    fi

    echo "Restarting Docker..."
    sudo systemctl restart docker

    echo "Done (daemon.json mode)."
fi

# --------------------------------------------------
# 4. Verify
# --------------------------------------------------

echo "== Verification =="

if ss -ltnp | grep -q 2375; then
    echo "TCP port 2375 is active"
else
    echo "WARNING: TCP port 2375 not detected"
fi

systemctl status docker --no-pager -l
