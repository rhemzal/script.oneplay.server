#!/bin/bash
# Nainstaluje systemd unit bez ExecStartPre (session se nemaže při restartu).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_SRC="${SCRIPT_DIR}/oneplay_server.service"
UNIT_DST="/etc/systemd/system/oneplay_server.service"

if [[ ! -f "${UNIT_SRC}" ]]; then
	echo "CHYBA: ${UNIT_SRC} neexistuje" >&2
	exit 1
fi

if grep -q '^ExecStartPre=' "${UNIT_DST}" 2>/dev/null; then
	echo "Odstraňuji ExecStartPre z ${UNIT_DST} ..."
	sed -i '/^ExecStartPre=/d' "${UNIT_DST}"
else
	echo "Kopíruji ${UNIT_SRC} -> ${UNIT_DST}"
	cp "${UNIT_SRC}" "${UNIT_DST}"
fi

systemctl daemon-reload
echo "OK: unit aktualizován. Pro načtení kódu: systemctl restart oneplay_server"
echo "Pokud API vrací Too Many Requests, počkejte 10–15 min před restartem."
