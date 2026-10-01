#!/bin/bash
# Ověří Nova HD přes TVHeadend HTTP stream (port 9981) s opakováním po restartu TVH.
# Použití: ./scripts/verify_tvh_nova.sh [TVH_URL]

set -euo pipefail

TVH_URL="${1:-http://127.0.0.1:9981/stream/channelname/Nova%20HD}"
MIN_BYTES=100000
SAMPLE_SEC=10
MAX_ATTEMPTS=6
SLEEP=5
OUT="$(mktemp)"
trap 'rm -f "${OUT}"' EXIT

for attempt in $(seq 1 "${MAX_ATTEMPTS}"); do
	bytes="$(curl -s --max-time "${SAMPLE_SEC}" -o "${OUT}" -w '%{size_download}' "${TVH_URL}" || true)"
	if [[ "${bytes}" -ge "${MIN_BYTES}" ]]; then
		echo "OK: TVH Nova HD ${bytes} B za ${SAMPLE_SEC} s (pokus ${attempt}/${MAX_ATTEMPTS})"
		exit 0
	fi
	if [[ "${attempt}" -lt "${MAX_ATTEMPTS}" ]]; then
		echo "INFO: pokus ${attempt}/${MAX_ATTEMPTS} jen ${bytes} B – čekám ${SLEEP} s (TVH mux může nabíhat po restartu)..." >&2
		sleep "${SLEEP}"
	fi
done

echo "CHYBA: TVH Nova HD jen ${bytes} B za ${SAMPLE_SEC} s (očekáváno >$(( MIN_BYTES / 1024 )) KB)" >&2
exit 1
