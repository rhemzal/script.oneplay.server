#!/bin/bash
# Automatický tvh-fix po startu TVHeadend (voláno z systemd ExecStartPost).
# Čeká na mux data, opraví mapování kanálů, při změnách restartuje TVH jednou.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIX_SCRIPT="${SCRIPT_DIR}/fix_tvh_channel_services.sh"
TVH_CONF="${TVH_CONF:-/home/hts/conf}"
POLL_INTERVAL="${TVH_AUTO_FIX_POLL_INTERVAL:-5}"
POLL_MAX="${TVH_AUTO_FIX_POLL_MAX:-120}"
LOCK_FILE="${TVH_AUTO_FIX_LOCK:-/tmp/oneplay-tvh-auto-fix.lock}"

log() {
	echo "oneplay-tvh-auto-fix: $*" | systemd-cat -t oneplay-tvh-auto-fix -p info 2>/dev/null || echo "oneplay-tvh-auto-fix: $*"
}

run_worker() {
	exec 9>"${LOCK_FILE}"
	if ! flock -n 9; then
		log "jiná instance už běží, končím"
		exit 0
	fi

	log "čekám na mux data (max ${POLL_MAX} s)"
	if ! python3 - "${TVH_CONF}" "${POLL_INTERVAL}" "${POLL_MAX}" <<'PY'
import glob, gzip, os, re, sys, time
from urllib.parse import unquote

tvh_conf, interval, max_wait = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
networks_dir = os.path.join(tvh_conf, 'input', 'iptv', 'networks')

def count_services():
    total = 0
    for mux_dir in glob.glob(os.path.join(networks_dir, '*', 'muxes')):
        for path in glob.glob(os.path.join(mux_dir, '*')):
            raw = open(path, 'rb').read()
            if not raw.startswith(b'\xff\xffGZIP01'):
                continue
            text = gzip.decompress(raw[12:]).decode('utf-8', 'replace')
            if re.search(r'/play/([^?\x00"]+\.m3u8)', text):
                total += 1
    return total

deadline = time.time() + max_wait
while time.time() < deadline:
    if count_services() > 0:
        sys.exit(0)
    time.sleep(interval)
sys.exit(1)
PY
	then
		log "mux data nejsou k dispozici – fix přeskočen"
		exit 1
	fi

	total_fixed=0
	run_fix() {
		local network="${1:-}"
		local output
		if [[ -n "${network}" ]]; then
			output="$(env TVH_CONF="${TVH_CONF}" TVH_AUTO_FIX=1 "${FIX_SCRIPT}" "${network}" 2>&1)" || true
		else
			output="$(env TVH_CONF="${TVH_CONF}" TVH_AUTO_FIX=1 "${FIX_SCRIPT}" 2>&1)" || true
		fi
		echo "${output}"
		local fixed
		fixed="$(echo "${output}" | sed -n 's/.*opraveno: \([0-9]*\).*/\1/p' | tail -1)"
		if [[ -n "${fixed}" ]]; then
			total_fixed=$(( total_fixed + fixed ))
		fi
		log "${output}"
	}

	run_fix Oneplay1
	run_fix

	if [[ "${total_fixed}" -gt 0 ]]; then
		log "opraveno ${total_fixed} kanálů – restart tvheadend"
		systemctl restart tvheadend
	else
		log "žádné změny, restart TVH není potřeba"
	fi
}

if [[ "${TVH_AUTO_FIX_WORKER:-}" == "1" ]]; then
	run_worker
	exit 0
fi

export TVH_AUTO_FIX_WORKER=1
export TVH_AUTO_FIX=1
nohup env TVH_AUTO_FIX_WORKER=1 TVH_AUTO_FIX=1 TVH_CONF="${TVH_CONF}" "$0" >/dev/null 2>&1 &
exit 0
