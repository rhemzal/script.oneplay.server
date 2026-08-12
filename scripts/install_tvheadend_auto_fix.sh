#!/bin/bash
# Nainstaluje systemd drop-in pro automatický tvh-fix po startu TVHeadend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DROPIN_SRC="${SCRIPT_DIR}/tvheadend.service.d/oneplay-tvh-fix.conf"
DROPIN_DST="/etc/systemd/system/tvheadend.service.d/oneplay-tvh-fix.conf"
AUTO_FIX="${ROOT_DIR}/scripts/tvh_auto_fix.sh"

if [[ ! -f "${DROPIN_SRC}" ]]; then
	echo "CHYBA: ${DROPIN_SRC} neexistuje" >&2
	exit 1
fi

if [[ ! -x "${AUTO_FIX}" ]]; then
	chmod +x "${AUTO_FIX}"
fi

mkdir -p /etc/systemd/system/tvheadend.service.d
sed "s|/usr/src/oneplay/script.oneplay.server|${ROOT_DIR}|g" "${DROPIN_SRC}" > "${DROPIN_DST}"

systemctl daemon-reload
echo "OK: drop-in nainstalován: ${DROPIN_DST}"
echo "ExecStartPost spouští: ${AUTO_FIX}"
echo ""
echo "Provoz: po restartu TVH auto-fix běží sám – rutinně není potřeba make tvh-fix."
echo "Ověření: sudo systemctl restart tvheadend"
echo "         journalctl -t oneplay-tvh-auto-fix --since '5 min ago'"
echo "         make verify-tvh"
