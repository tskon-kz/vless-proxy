#!/usr/bin/env bash
# Query the local proxy API and print current status.
# Usage: ./scripts/update-proxies.sh [api_host] [api_port]

set -euo pipefail

HOST="${1:-127.0.0.1}"
PORT="${2:-8888}"
BASE="http://${HOST}:${PORT}"

echo "=== Best proxy ==="
curl -sf "${BASE}/proxy/best" | python3 -m json.tool || echo "(none)"

echo ""
echo "=== All active proxies ==="
curl -sf "${BASE}/proxy/list" | python3 -m json.tool || echo "(none)"
