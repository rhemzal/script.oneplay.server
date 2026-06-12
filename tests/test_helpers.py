# -*- coding: utf-8 -*-
import json
import os

import pytest

from resources.lib.helpers import (
    NO_ACCESS_URL,
    channel_display_name,
    collect_account_ids,
    collect_account_items,
    extract_hls_url,
    get_api_error,
    is_truthy,
    parse_epg_item_action,
    resolve_channel_name_by_number,
    select_account_id,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), 'fixtures')


def load_fixture(name):
    with open(os.path.join(FIXTURES_DIR, name), 'r', encoding='utf-8') as handle:
        return json.load(handle)


@pytest.mark.parametrize('value,expected', [
    (None, False),
    (0, False),
    (1, True),
    ('0', False),
    ('1', True),
    ('true', True),
    ('false', False),
    (False, False),
    (True, True),
])
def test_is_truthy(value, expected):
    assert is_truthy(value) is expected


@pytest.mark.parametrize('poradi_sluzby,expected', [
    (None, 'acc-1'),
    (-1, 'acc-1'),
    (0, 'acc-1'),
    (99, 'acc-1'),
    ('invalid', 'acc-1'),
    (1, 'acc-1'),
    (2, 'acc-2'),
    (3, 'acc-3'),
])
def test_select_account_id(poradi_sluzby, expected):
    account_ids = ['acc-1', 'acc-2', 'acc-3']
    assert select_account_id(account_ids, poradi_sluzby) == expected


def test_select_account_id_empty_list():
    assert select_account_id([], 1) == ''


def test_collect_account_items_from_groups_fixture():
    step = load_fixture('account_chooser_groups.json')
    items = collect_account_items(step)
    assert len(items) == 3
    assert items[0]['accountId'] == 'acc-1'
    assert items[2]['accountId'] == 'acc-3'


def test_collect_account_items_from_legacy_fixture():
    step = load_fixture('account_chooser_legacy.json')
    items = collect_account_items(step)
    assert len(items) == 2
    assert items[0]['accountId'] == 'legacy-1'


def test_collect_account_ids_prefers_active_or_extid():
    step = load_fixture('account_chooser_groups.json')
    assert collect_account_ids(step) == ['acc-1', 'acc-2', 'acc-3']


def test_collect_account_ids_fallback_without_flags():
    step = {
        'groups': [
            {'accounts': [
                {'accountId': 'only-id-1'},
                {'accountId': 'only-id-2'},
            ]}
        ]
    }
    assert collect_account_ids(step) == ['only-id-1', 'only-id-2']


def test_collect_account_ids_skips_active_without_account_id():
    step = {
        'groups': [
            {'accounts': [
                {'isActive': True},
                {'extId': 'ext-1'},
                {'accountId': 'fallback-id'},
            ]}
        ]
    }
    assert collect_account_ids(step) == ['fallback-id']


def test_channel_display_name_strip_hd():
    assert channel_display_name('Nova HD', strip_hd=True) == 'Nova'
    assert channel_display_name('Nova HD', strip_hd=False) == 'Nova HD'


def test_resolve_channel_name_by_number():
    channels = {
        'ch-1': {'channel_number': 1, 'name': 'CT1 HD'},
        'ch-2': {'channel_number': 2, 'name': 'Nova HD'},
    }
    assert resolve_channel_name_by_number(channels, 1, strip_hd=False) == 'CT1 HD'
    assert resolve_channel_name_by_number(channels, 2, strip_hd=True) == 'Nova'
    assert resolve_channel_name_by_number(channels, 99, strip_hd=False) is None


def test_get_api_error():
    assert get_api_error({'err': 'timeout'}) == 'timeout'
    assert get_api_error({'result': {'status': 'Error', 'message': 'fail'}}) == 'fail'
    assert get_api_error({'result': {'status': 'Ok'}}) is None
    assert get_api_error(None) is None


def test_extract_hls_url():
    data = {
        'media': {
            'stream': {
                'assets': [
                    {'protocol': 'dash', 'src': 'http://example/dash'},
                    {'protocol': 'hls', 'drm': True, 'src': 'http://example/drm.m3u8'},
                    {'protocol': 'hls', 'src': 'http://example/live.m3u8'},
                ]
            }
        }
    }
    assert extract_hls_url(data) == 'http://example/live.m3u8'
    assert extract_hls_url({}) == NO_ACCESS_URL


def test_parse_epg_item_action_show_deeplink():
    item = {
        'actions': [{
            'params': {
                'contentType': 'show',
                'payload': {'deeplink': {'epgItem': 'epg-1'}},
            }
        }]
    }
    content_id, payload = parse_epg_item_action(item)
    assert content_id == 'epg-1'
    assert payload['deeplink']['epgItem'] == 'epg-1'


def test_parse_epg_item_action_missing_actions():
    assert parse_epg_item_action({}) == (None, None)
