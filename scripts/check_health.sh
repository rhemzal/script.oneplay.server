#!/bin/bash
# Ověří /health s opakováním po restartu služby.
# Použití: ./scripts/check_health.sh [host:port]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG="${ROOT_DIR}/config.txt"
PORT=8082
[[ -f "${CONFIG}" ]] && PORT="$(python3 -c "import json; print(json.load(open('${CONFIG}')).get('webserver_port', 8082))" 2>/dev/null || echo 8082)"

BASE="${1:-http://127.0.0.1:${PORT}}"
BASE="${BASE%/}"
URL="${BASE}/health"
MAX_ATTEMPTS=15
SLEEP=2

for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
	RESP="$(curl -sf --connect-timeout 3 "${URL}" 2>/dev/null || true)"
	if [[ -n "${RESP}" ]]; then
		echo "${RESP}" | python3 -m json.tool
		exit 0
	fi
	if [[ "${attempt}" -lt "${MAX_ATTEMPTS}" ]]; then
		echo "Čekám na server (${attempt}/${MAX_ATTEMPTS})..." >&2
		sleep "${SLEEP}"
	fi
done

echo "CHYBA: ${URL} neodpovídá po $(( MAX_ATTEMPTS * SLEEP )) s" >&2
exit 1
