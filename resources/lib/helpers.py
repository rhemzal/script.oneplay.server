# -*- coding: utf-8 -*-

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
        if acc.get('extId') or acc.get('isActive'):
            account_ids.append(acc['accountId'])
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


def extract_hls_url(data, fallback=NO_ACCESS_URL):
    if not isinstance(data, dict):
        return fallback
    assets = data.get('media', {}).get('stream', {}).get('assets', [])
    url = fallback
    for asset in assets:
        if asset.get('protocol') != 'hls':
            continue
        if asset.get('drm'):
            continue
        src = asset.get('src', '')
        if not src:
            continue
        if 'clear' not in src and 'free' not in src:
            return src
        if url == fallback:
            url = src
    return url


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
