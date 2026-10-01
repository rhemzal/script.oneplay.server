import json
import time
from unittest.mock import Mock

import pytest

import resources.lib.channels as channels_module
from resources.lib.utils import OneplayError


def test_expired_channel_cache_is_served_when_refresh_fails(monkeypatch):
    cached_channels = {'channel-1': {'name': 'Nova HD', 'visible': True}}
    cached_data = json.dumps({
        'channels': cached_channels,
        'valid_to': int(time.time()) - 1,
    })
    refresh = Mock(side_effect=OneplayError('Oneplay unavailable'))
    save = Mock()
    monkeypatch.setattr(channels_module, 'load_json_data', lambda file: cached_data)
    monkeypatch.setattr(channels_module, 'get_api_backoff_seconds', lambda: 0)
    monkeypatch.setattr(channels_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(channels_module, 'get_channels', refresh)
    monkeypatch.setattr(channels_module, 'save_channels', save)

    assert channels_module.load_channels() == cached_channels

    refresh.assert_called_once()
    save.assert_not_called()


def test_expired_channel_cache_skips_refresh_during_cooldown(monkeypatch):
    cached_channels = {'channel-1': {'name': 'Nova HD', 'visible': True}}
    cached_data = json.dumps({
        'channels': cached_channels,
        'valid_to': int(time.time()) - 1,
    })
    refresh = Mock(side_effect=AssertionError('refresh attempted during cooldown'))
    monkeypatch.setattr(channels_module, 'load_json_data', lambda file: cached_data)
    monkeypatch.setattr(channels_module, 'get_api_backoff_seconds', lambda: 900)
    monkeypatch.setattr(channels_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(channels_module, 'get_channels', refresh)

    assert channels_module.load_channels() == cached_channels
    refresh.assert_not_called()


def test_explicit_channel_reset_still_reports_refresh_failure(monkeypatch):
    refresh = Mock(side_effect=OneplayError('Oneplay unavailable'))
    monkeypatch.setattr(channels_module, 'get_channels', refresh)

    with pytest.raises(OneplayError, match='Oneplay unavailable'):
        channels_module.load_channels(reset=True)

    refresh.assert_called_once()