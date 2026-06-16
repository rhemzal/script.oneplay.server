#!/bin/bash
# Ověří, že TVHeadend pipe:// příkaz z playlistu skutečně produkuje MPEG-TS data.
# Použití: ./scripts/test_tvheadend_pipe.sh [host:port]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG="${ROOT_DIR}/config.txt"
PORT=8082
[[ -f "${CONFIG}" ]] && PORT="$(python3 -c "import json; print(json.load(open('${CONFIG}')).get('webserver_port', 8082))" 2>/dev/null || echo 8082)"

BASE="${1:-http://127.0.0.1:${PORT}}"
BASE="${BASE%/}"

echo "=== Test TVHeadend pipe z ${BASE}/playlist/tvheadend ==="

LINE="$(curl -sS "${BASE}/playlist/tvheadend" | grep -m1 '^pipe://' || true)"
[[ -n "${LINE}" ]] || { echo "CHYBA: playlist neobsahuje pipe:// řádek" >&2; exit 1; }

CMD="${LINE#pipe://}"
echo "Příkaz: ${CMD}"

BYTES="$(timeout 15 bash -c "${CMD}" 2>/dev/null | wc -c | tr -d ' ')" || true
if [[ "${BYTES}" -lt 100000 ]]; then
	echo "CHYBA: pipe za 15 s vyprodukoval jen ${BYTES} B (očekáváno >100 KB)" >&2
	exit 1
fi

echo "OK: pipe za 15 s vyprodukoval $(( BYTES / 1024 )) KB MPEG-TS"
exit 0
