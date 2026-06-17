#!/usr/bin/env bash
set -euo pipefail

# Installs xray binary into ./bin/xray relative to the project root.
# Run from anywhere: bash scripts/install-xray.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DIR="$PROJECT_DIR/bin"
INSTALL_PATH="$INSTALL_DIR/xray"
TMP_DIR="$(mktemp -d)"

BASE_URL="https://github.com/XTLS/Xray-core/releases/latest/download"

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

if ! command -v unzip &>/dev/null; then
    echo "Installing unzip ..."
    if command -v apt-get &>/dev/null; then
        apt-get install -y unzip
    elif command -v yum &>/dev/null; then
        yum install -y unzip
    else
        echo "Cannot install unzip: no supported package manager found" >&2
        exit 1
    fi
fi

echo "Extracting ..."
unzip -q "$TMP_DIR/$archive" -d "$TMP_DIR"

mkdir -p "$INSTALL_DIR"
install -m 755 "$TMP_DIR/xray" "$INSTALL_PATH"

echo "Installed: $INSTALL_PATH"
"$INSTALL_PATH" version

echo "Done. Set XRAY_BINARY=./bin/xray in your .env"
