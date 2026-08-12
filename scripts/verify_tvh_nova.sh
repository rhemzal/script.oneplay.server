#!/bin/bash
# Ověří Nova HD přes TVHeadend HTTP stream (port 9981) s opakováním po restartu TVH.
# Použití: ./scripts/verify_tvh_nova.sh [TVH_URL]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
TVH_CONF="${TVH_CONF:-/home/hts/conf}"
NOVA_CHANNEL_CONFIG="${TVH_CONF}/channel/config/acaab01b8661bb155b67bdf93ef8682d"
TVH_URL="${1:-http://127.0.0.1:9981/stream/channelname/Nova%20HD}"
MIN_BYTES=100000
SAMPLE_SEC=10
MAX_ATTEMPTS=6
SLEEP=5
OUT="$(mktemp)"
trap 'rm -f "${OUT}"' EXIT

if [[ ! -f "${NOVA_CHANNEL_CONFIG}" ]]; then
	echo "CHYBA: kanál Nova HD nenalezen v ${TVH_CONF}" >&2
	exit 1
fi

services="$(python3 -c "import json; print(json.load(open('${NOVA_CHANNEL_CONFIG}')).get('services', []))")"
echo "Nova HD services: ${services}"
if [[ "${services}" == "[]" ]]; then
	echo "CHYBA: Nova HD nemá přiřazenou službu – spusťte make tvh-fix" >&2
	exit 1
fi

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
