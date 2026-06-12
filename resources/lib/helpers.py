# -*- coding: utf-8 -*-

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
