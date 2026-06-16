#!/bin/bash
# Ověří, že OnePlay server vrací živý stream pro Nova HD.
# Použití: ./scripts/test_nova_hd.sh [host:port]
# Příklad: ./scripts/test_nova_hd.sh
#          ./scripts/test_nova_hd.sh 127.0.0.1:8082

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIG="${ROOT_DIR}/config.txt"
CHANNEL="Nova HD"
CHANNEL_ENC="Nova%20HD"

fail() {
	echo "CHYBA: $*" >&2
	exit 1
}

ok() {
	echo "OK: $*"
}

# Port z config.txt nebo výchozí 8082
PORT=8082
if [[ -f "${CONFIG}" ]]; then
	PORT_CFG="$(python3 -c "import json; print(json.load(open('${CONFIG}')).get('webserver_port', 8082))" 2>/dev/null || true)"
	[[ -n "${PORT_CFG}" ]] && PORT="${PORT_CFG}"
fi

BASE="${1:-http://127.0.0.1:${PORT}}"
BASE="${BASE%/}"

echo "=== Test Nova HD přes OnePlay server ==="
echo "Server: ${BASE}"
echo

# 1) Server odpovídá
HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 5 "${BASE}/playlist" || echo 000)"
[[ "${HTTP_CODE}" == "200" ]] || fail "Server neodpovídá na /playlist (HTTP ${HTTP_CODE})"
ok "Server běží (/playlist HTTP 200)"

# 2) stream_url vrací CDN URL, ne noAccess
STREAM_JSON="$(curl -sS --connect-timeout 10 "${BASE}/stream_url/${CHANNEL_ENC}")"
STREAM_URL="$(echo "${STREAM_JSON}" | python3 -c "
import json, sys
d = json.load(sys.stdin)
url = d.get('url') or ''
err = d.get('error')
if err:
    print('ERROR:' + err)
elif not url:
    print('ERROR:prázdná URL')
elif 'noAccess' in url:
    print('ERROR:noAccess')
else:
    print(url)
" 2>/dev/null || echo "ERROR:neplatná JSON odpověď")"

[[ "${STREAM_URL}" != ERROR:* ]] || fail "stream_url: ${STREAM_URL#ERROR:}"
ok "stream_url vrací stream (${STREAM_URL:0:60}...)"

# 3) /play/ vrací manifest nebo redirect na CDN (ne noAccess)
PLAY_HDR="$(mktemp)"
PLAY_BODY="$(mktemp)"
trap 'rm -f "${PLAY_HDR}" "${PLAY_BODY}"' EXIT

curl -sS -D "${PLAY_HDR}" -o "${PLAY_BODY}" --connect-timeout 15 "${BASE}/play/${CHANNEL_ENC}.m3u8"

if grep -qi '^location:.*noAccess' "${PLAY_HDR}"; then
	fail "/play/ přesměrovává na noAccess"
fi

if grep -qi '^location:' "${PLAY_HDR}"; then
	LOC="$(grep -i '^location:' "${PLAY_HDR}" | tail -1 | cut -d' ' -f2- | tr -d '\r')"
	if echo "${LOC}" | grep -q 'noAccess'; then
		fail "/play/ Location obsahuje noAccess"
	fi
	ok "/play/ přesměrovává na CDN"
elif grep -q '#EXTM3U' "${PLAY_BODY}"; then
	if grep -q 'noAccess' "${PLAY_BODY}"; then
		fail "/play/ manifest obsahuje noAccess"
	fi
	ok "/play/ vrací HLS manifest"
else
	fail "/play/ nevrátil manifest ani platný redirect"
fi

# 4) ffmpeg – krátký test příjmu dat (volitelný, pokud je ffmpeg)
FFMPEG="${FFMPEG:-/usr/bin/ffmpeg}"
if [[ -x "${FFMPEG}" ]]; then
	OUT="$(mktemp)"
	trap 'rm -f "${PLAY_HDR}" "${PLAY_BODY}" "${OUT}"' EXIT
	if "${FFMPEG}" -loglevel error -y -i "${BASE}/play/${CHANNEL_ENC}.m3u8" -t 5 -f null - 2>/dev/null; then
		ok "ffmpeg přijal 5 s streamu"
	else
		fail "ffmpeg nedokázal přehrát 5 s streamu"
	fi
else
	echo "INFO: ffmpeg nenalezen, přeskočen test přehrání"
fi

echo
echo "=== Vše OK: Nova HD jede přes ${BASE} ==="
exit 0
