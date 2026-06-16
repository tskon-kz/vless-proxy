#!/usr/bin/env bash
set -euo pipefail

BASE_URL="https://github.com/XTLS/Xray-core/releases/latest/download"
INSTALL_PATH="/usr/local/bin/xray"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

arch="$(uname -m)"
case "$arch" in
    x86_64)
        archive="Xray-linux-64.zip"
        ;;
    aarch64)
        archive="Xray-linux-arm64-v8a.zip"
        ;;
    *)
        echo "Unsupported architecture: $arch" >&2
        exit 1
        ;;
esac

echo "Detected architecture: $arch"
echo "Downloading $archive ..."
curl -fsSL "$BASE_URL/$archive" -o "$TMP_DIR/$archive"

echo "Extracting ..."
unzip -q "$TMP_DIR/$archive" -d "$TMP_DIR"

echo "Installing xray to $INSTALL_PATH ..."
install -m 755 "$TMP_DIR/xray" "$INSTALL_PATH"

echo "Verifying installation ..."
xray version

echo "Done."
