#!/usr/bin/env bash
set -euo pipefail

BASE_URL="https://github.com/XTLS/Xray-core/releases/latest/download"
INSTALL_PATH="/usr/local/bin/xray"
TMP_DIR="$(mktemp -d)"

cleanup() {
    rm -rf "$TMP_DIR"
}
trap cleanup EXIT

os="$(uname -s)"
arch="$(uname -m)"

case "$os" in
    Linux)
        case "$arch" in
            x86_64)  archive="Xray-linux-64.zip" ;;
            aarch64) archive="Xray-linux-arm64-v8a.zip" ;;
            *) echo "Unsupported Linux architecture: $arch" >&2; exit 1 ;;
        esac
        ;;
    Darwin)
        case "$arch" in
            x86_64)  archive="Xray-macos-64.zip" ;;
            arm64)   archive="Xray-macos-arm64-v8a.zip" ;;
            *) echo "Unsupported macOS architecture: $arch" >&2; exit 1 ;;
        esac
        ;;
    *)
        echo "Unsupported OS: $os" >&2
        exit 1
        ;;
esac

echo "Detected OS: $os, architecture: $arch"
echo "Downloading $archive ..."
curl -fsSL "$BASE_URL/$archive" -o "$TMP_DIR/$archive"

echo "Extracting ..."
unzip -q "$TMP_DIR/$archive" -d "$TMP_DIR"

echo "Installing xray to $INSTALL_PATH ..."
if [ "$os" = "Darwin" ] && [ ! -w "$(dirname "$INSTALL_PATH")" ]; then
    sudo install -m 755 "$TMP_DIR/xray" "$INSTALL_PATH"
else
    install -m 755 "$TMP_DIR/xray" "$INSTALL_PATH"
fi

echo "Verifying installation ..."
xray version

echo "Done."
