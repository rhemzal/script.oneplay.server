#!/bin/bash
TVH_CONF="${TVH_CONF:-${HOME}/.hts/tvheadend}"
XMLTV_SOCK="${XMLTV_SOCK:-${TVH_CONF}/epggrab/xmltv.sock}"
EPG_URL="${EPG_URL:-http://localhost:8082/epg}"
EPG_FILE="${EPG_FILE:-/tmp/epg.xml}"
EPG_TEMP="${EPG_FILE}.tmp.$$"

set -euo pipefail
trap 'rm -f "${EPG_TEMP}"' EXIT

wget -q --tries=1 --timeout=10 "${EPG_URL}" -O "${EPG_TEMP}"
python3 -c 'import sys, xml.etree.ElementTree as ET; root = ET.parse(sys.argv[1]).getroot(); sys.exit(0 if root.tag == "tv" and root.find("channel") is not None else 1)' "${EPG_TEMP}"
mv "${EPG_TEMP}" "${EPG_FILE}"
/usr/bin/socat - UNIX-CONNECT:"${XMLTV_SOCK}" < "${EPG_FILE}"

