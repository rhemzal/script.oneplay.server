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
PIPE_TIMEOUT=20
MIN_BYTES=100000

echo "=== Test TVHeadend pipe z ${BASE}/playlist/tvheadend ==="

LINE="$(curl -sS --connect-timeout 5 "${BASE}/playlist/tvheadend" | grep -m1 '^pipe://' || true)"
[[ -n "${LINE}" ]] || { echo "CHYBA: playlist neobsahuje pipe:// řádek" >&2; exit 1; }

CMD="${LINE#pipe://}"
echo "Příkaz: ${CMD}"

OUT="$(mktemp)"
ERR="$(mktemp)"
trap 'rm -f "${OUT}" "${ERR}"' EXIT

run_pipe() {
	timeout "${PIPE_TIMEOUT}" bash -c "${CMD}" >"${OUT}" 2>"${ERR}"
}

BYTES=0
for attempt in 1 2; do
	: >"${OUT}"
	: >"${ERR}"
	set +e
	run_pipe
	pipe_status=$?
	set -e
	BYTES="$(wc -c <"${OUT}" | tr -d ' ')"
	if [[ "${BYTES}" -ge "${MIN_BYTES}" ]]; then
		echo "OK: pipe za ${PIPE_TIMEOUT} s vyprodukoval $(( BYTES / 1024 )) KB MPEG-TS"
		exit 0
	fi
	if [[ "${attempt}" -eq 1 ]]; then
		echo "INFO: pokus 1 jen ${BYTES} B, čekám 3 s a zkouším znovu (server může být po restartu)..." >&2
		sleep 3
	fi
done

echo "CHYBA: pipe za ${PIPE_TIMEOUT} s vyprodukoval jen ${BYTES} B (očekáváno >$(( MIN_BYTES / 1024 )) KB), exit=${pipe_status}" >&2
echo "TIP: po změně playlistu restartujte TVHeadend a načtěte IPTV síť znovu." >&2
if [[ -s "${ERR}" ]]; then
	echo "--- ffmpeg stderr ---" >&2
	cat "${ERR}" >&2
else
	echo "--- ffmpeg stderr prázdné (ffmpeg čeká na server/CDN?) ---" >&2
fi
exit 1
