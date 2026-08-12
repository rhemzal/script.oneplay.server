#!/bin/bash
# Opraví mapování kanál -> služba v TVHeadendu po rescanu IPTV sítě.
# Po Force scan služby dostanou nová UUID, ale kanály odkazují na stará.
#
# Použití: sudo ./scripts/fix_tvh_channel_services.sh [síť]
#   síť = název (Oneplay1) nebo UUID sítě
#   bez parametru: nejdřív Oneplay, pak Oneplay1
#   TVH_CONF=/cesta/k/conf  – výchozí /home/hts/conf
#
# Skript je idempotentní – opakované spuštění nemění již správná mapování.

set -euo pipefail

TVH_CONF="${TVH_CONF:-/home/hts/conf}"
NETWORK="${1:-}"

if [[ ! -d "$TVH_CONF" ]]; then
	echo "CHYBA: konfigurační adresář TVHeadendu neexistuje: $TVH_CONF" >&2
	exit 1
fi

for sub in channel/config input/iptv/networks; do
	if [[ ! -d "$TVH_CONF/$sub" ]]; then
		echo "CHYBA: v konfiguraci TVHeadendu chybí adresář: $TVH_CONF/$sub" >&2
		exit 1
	fi
done

if [[ "$(id -u)" -eq 0 ]]; then
	SUDO_PREFIX=(sudo -u hts)
else
	SUDO_PREFIX=()
fi

"${SUDO_PREFIX[@]}" env TVH_CONF="$TVH_CONF" NETWORK="$NETWORK" python3 <<'PY'
import glob, gzip, re, json, os, sys
from urllib.parse import unquote

TVH_CONF = os.environ['TVH_CONF']
NETWORK = os.environ.get('NETWORK', '')
NETWORKS_DIR = os.path.join(TVH_CONF, 'input', 'iptv', 'networks')
CH_DIR = os.path.join(TVH_CONF, 'channel', 'config')

UUID_RE = re.compile(r'^[a-f0-9]{32}$')


def load_network_config(network_id):
    path = os.path.join(NETWORKS_DIR, network_id, 'config')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def find_network_by_name(name):
    for path in glob.glob(os.path.join(NETWORKS_DIR, '*/config')):
        with open(path, encoding='utf-8') as f:
            cfg = json.load(f)
        if cfg.get('networkname') == name:
            return os.path.basename(os.path.dirname(path)), cfg
    return None, None


def resolve_network():
    if NETWORK:
        if UUID_RE.match(NETWORK):
            config_path = os.path.join(NETWORKS_DIR, NETWORK, 'config')
            if not os.path.isfile(config_path):
                print(f'CHYBA: síť s UUID neexistuje: {NETWORK}', file=sys.stderr)
                sys.exit(1)
            return NETWORK, load_network_config(NETWORK)
        network_id, cfg = find_network_by_name(NETWORK)
        if not network_id:
            print(f'CHYBA: síť nenalezena: {NETWORK}', file=sys.stderr)
            sys.exit(1)
        return network_id, cfg

    for name in ('Oneplay', 'Oneplay1'):
        network_id, cfg = find_network_by_name(name)
        if network_id:
            return network_id, cfg

    print('CHYBA: nenalezena výchozí síť (Oneplay, Oneplay1)', file=sys.stderr)
    sys.exit(1)


def decode_mux(path):
    raw = open(path, 'rb').read()
    if raw.startswith(b'\xff\xffGZIP01'):
        return gzip.decompress(raw[12:]).decode('utf-8', 'replace')
    return None


def build_name_to_service(mux_dir):
    name_to_svc = {}
    for path in glob.glob(os.path.join(mux_dir, '*')):
        text = decode_mux(path)
        if not text:
            continue
        uuids = re.findall(r'[a-f0-9]{32}', text)
        m = re.search(r'/play/([^?\x00"]+\.m3u8)', text)
        if uuids and m:
            name_to_svc[unquote(m.group(1).replace('.m3u8', ''))] = uuids[0]
    return name_to_svc


network_id, network_cfg = resolve_network()
network_name = network_cfg.get('networkname', network_id)
mux_dir = os.path.join(NETWORKS_DIR, network_id, 'muxes')

if not os.path.isdir(mux_dir):
    print(f'CHYBA: mux adresář neexistuje: {mux_dir}', file=sys.stderr)
    sys.exit(1)

print(f'Síť: {network_name} ({network_id})')

name_to_svc = build_name_to_service(mux_dir)
if not name_to_svc:
    print('CHYBA: v muxech nebyly nalezeny žádné služby', file=sys.stderr)
    sys.exit(1)

fixed = 0
skipped = 0
for path in glob.glob(os.path.join(CH_DIR, '*')):
    try:
        with open(path, encoding='utf-8') as f:
            ch = json.load(f)
    except (OSError, json.JSONDecodeError):
        continue

    name = ch.get('name')
    if not name or name not in name_to_svc:
        continue

    new_svc = name_to_svc[name]
    if ch.get('services') == [new_svc]:
        skipped += 1
        continue

    ch['services'] = [new_svc]
    ch['enabled'] = True
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(ch, f, indent='\t', ensure_ascii=False)
        f.write('\n')
    fixed += 1
    print('Opraveno:', name)

print(f'Již v pořádku: {skipped}, opraveno: {fixed}')
if fixed == 0:
    print('Žádné změny nebyly potřeba.')
PY

echo "Hotovo."
if [[ "${TVH_AUTO_FIX:-}" != "1" ]]; then
	echo "Doporučeno: sudo systemctl restart tvheadend"
fi
