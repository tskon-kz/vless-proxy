#!/usr/bin/env bash
# Update the VLESS links file consumed by the file watcher.
# Usage:
#   echo "vless://..." | ./scripts/update-proxies.sh       # from stdin
#   ./scripts/update-proxies.sh "vless://..." "vless://..."  # as arguments

set -euo pipefail

VLESS_FILE="${VLESS_FILE:-./vless.txt}"
FILE_CHECK_INTERVAL="${FILE_CHECK_INTERVAL:-30}"

if [ -p /dev/stdin ]; then
    cat > "$VLESS_FILE"
elif [ "$#" -gt 0 ]; then
    printf '%s\n' "$@" > "$VLESS_FILE"
else
    echo "Usage: echo 'vless://...' | $0  OR  $0 'vless://...' 'vless://...'" >&2
    exit 1
fi

echo "Updated $VLESS_FILE — watcher will pick up in ${FILE_CHECK_INTERVAL}s"
