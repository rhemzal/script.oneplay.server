# -*- coding: utf-8 -*-
from urllib.parse import urljoin
from urllib.request import Request, urlopen

NO_ACCESS_URL = 'http://sledovanietv.sk/download/noAccess-cs.m3u8'


def is_truthy(value):
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.lower() in ('1', 'true', 'yes', 'on')
    return bool(value)


def channel_display_name(name, strip_hd=False):
    if strip_hd:
        return name.replace(' HD', '')
    return name


def select_account_id(account_ids, poradi_sluzby):
    if not account_ids:
        return ''
    if poradi_sluzby is None:
        return account_ids[0]
    try:
        index = int(poradi_sluzby)
    except (TypeError, ValueError):
        return account_ids[0]
    if index < 1 or index > len(account_ids):
        return account_ids[0]
    return account_ids[index - 1]


def collect_account_items(step):
    items = list(step.get('accounts', []))
    for group in step.get('groups', []):
        items.extend(group.get('accounts', []))
    return items


def collect_account_ids(step):
    account_ids = []
    for acc in collect_account_items(step):
        account_id = acc.get('accountId')
        if account_id and (acc.get('extId') or acc.get('isActive')):
            account_ids.append(account_id)
    if not account_ids:
        account_ids = [acc['accountId'] for acc in collect_account_items(step) if acc.get('accountId')]
    return account_ids


def resolve_channel_name_by_number(channels, channel_number, strip_hd=False):
    for chan_id in channels:
        if channels[chan_id]['channel_number'] == channel_number:
            return channel_display_name(channels[chan_id]['name'], strip_hd=strip_hd)
    return None


def resolve_channel_internal_id(channels, channel_name, strip_hd=False):
    for chan_id in channels:
        name = channel_display_name(channels[chan_id]['name'], strip_hd=strip_hd)
        if name == channel_name:
            return channels[chan_id]['id']
    return None


def get_api_error(data):
    if not isinstance(data, dict):
        return None
    if 'err' in data:
        return str(data['err'])
    result = data.get('result')
    if isinstance(result, dict) and result.get('status') == 'Error':
        return result.get('message', 'Chyba při volání API')
    return None


def _is_aes_hls_url(url):
    return 'hls-aes' in url or '/hls-aes/' in url


def _is_clear_hls_url(url):
    return 'hls-clear' in url or '/hls-clear/' in url


def extract_hls_url(data, fallback=NO_ACCESS_URL):
    if not isinstance(data, dict):
        return fallback
    assets = data.get('media', {}).get('stream', {}).get('assets', [])
    clear_url = None
    other_url = None
    aes_url = None
    for asset in assets:
        if asset.get('protocol') != 'hls':
            continue
        if asset.get('drm'):
            continue
        src = asset.get('src', '')
        if not src or 'noAccess' in src:
            continue
        if _is_clear_hls_url(src):
            clear_url = src
        elif _is_aes_hls_url(src):
            aes_url = src
        elif 'free' not in src:
            other_url = src
        elif other_url is None:
            other_url = src
    if clear_url:
        return clear_url
    if other_url:
        return other_url
    if aes_url:
        return aes_url
    return fallback


def resolve_hls_manifest(stream_url, user_agent=None):
    if not stream_url or stream_url == NO_ACCESS_URL:
        return None
    headers = {
        'User-Agent': user_agent or 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0',
        'Accept': '*/*',
    }
    try:
        resp = urlopen(Request(stream_url, headers=headers), timeout=20)
        final_url = resp.geturl()
        base = final_url.rsplit('/', 1)[0] + '/'
        body = resp.read().decode('utf-8', errors='replace')
    except Exception:
        return None
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            lines.append(line)
            continue
        if stripped.startswith('http://') or stripped.startswith('https://'):
            lines.append(line)
        else:
            lines.append(urljoin(base, stripped))
    if body.endswith('\n'):
        return '\n'.join(lines) + '\n'
    return '\n'.join(lines)


def parse_epg_item_action(item):
    actions = item.get('actions') or []
    if not actions:
        return None, None
    params = actions[0].get('params') or {}
    payload = params.get('payload') or {}
    content_type = params.get('contentType')
    if content_type in ('show', 'movie') and 'contentId' not in payload:
        content_id = (payload.get('deeplink') or {}).get('epgItem')
    else:
        content_id = payload.get('contentId')
    return content_id, payload
