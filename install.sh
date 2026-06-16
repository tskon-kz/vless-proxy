#!/usr/bin/env bash
# Install VLESS Proxy Manager as a systemd service on Ubuntu 22.04+
set -euo pipefail

INSTALL_DIR="/opt/vless-manager"
SERVICE_USER="vless-manager"
SERVICE_FILE="vless-manager.service"

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "This installer targets Ubuntu/Linux. For local dev on macOS, run directly with uv." >&2
    exit 1
fi

if [[ $EUID -ne 0 ]]; then
    echo "Run as root: sudo bash install.sh" >&2
    exit 1
fi

echo "=== Installing VLESS Proxy Manager ==="

# 1. System user
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --no-create-home --shell /bin/false "$SERVICE_USER"
    echo "Created system user: $SERVICE_USER"
fi

# 2. Install directory
mkdir -p "$INSTALL_DIR"
rsync -a --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
      --exclude='.venv' --exclude='state.db' \
      . "$INSTALL_DIR/"

# 3. uv + virtualenv
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

cd "$INSTALL_DIR"
uv sync --no-dev

# 4. xray-core
bash "$INSTALL_DIR/install-xray.sh"

# 5. .env
if [[ ! -f "$INSTALL_DIR/.env" ]]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    API_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    sed -i "s|^API_SECRET_KEY=.*|API_SECRET_KEY=$API_KEY|" "$INSTALL_DIR/.env"
    echo ""
    echo "⚠  Edit $INSTALL_DIR/.env before starting:"
    echo "   Required: TG_BOT_TOKEN, TG_ALLOWED_USER_IDS"
fi

# 6. Permissions
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
chmod 640 "$INSTALL_DIR/.env"

# 7. systemd
cp "$INSTALL_DIR/$SERVICE_FILE" /etc/systemd/system/
systemctl daemon-reload
systemctl enable "$SERVICE_FILE"

echo ""
echo "=== Installation complete ==="
echo ""
echo "Next steps:"
echo "  1. nano $INSTALL_DIR/.env               # set TG_BOT_TOKEN"
echo "  2. systemctl start $SERVICE_FILE         # start the service"
echo "  3. journalctl -u vless-manager -f        # watch logs"
