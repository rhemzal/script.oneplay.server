import json
from unittest.mock import Mock

import pytest

import resources.lib.epg as epg_module
from resources.lib.utils import OneplayError


VALID_EPG = '<?xml version="1.0"?><tv><channel id="channel-1" /></tv>'


@pytest.mark.parametrize(
    'error_response',
    [
        {'err': 'Too Many Requests'},
        {'result': {'status': 'Error', 'message': 'Too Many Requests'}},
    ],
)
def test_get_day_epg_propagates_api_failure_without_retry(monkeypatch, error_response):
    api_call = Mock(return_value=error_response)
    monkeypatch.setattr(epg_module, 'load_session', lambda: 'token')
    monkeypatch.setattr(epg_module, 'load_channels', lambda: {'channel-1': {}})
    monkeypatch.setattr(epg_module, 'api_url', lambda endpoint: endpoint)
    monkeypatch.setattr(epg_module, 'call_api', api_call)

    with pytest.raises(OneplayError, match='Nepodařilo se načíst denní EPG') as error:
        epg_module.get_day_epg(1_700_000_000, 1_700_086_400)

    assert error.value.detail == 'Too Many Requests'
    api_call.assert_called_once()


def test_failed_refresh_preserves_last_good_epg(monkeypatch):
    cached_data = json.dumps({'epg': VALID_EPG})
    saved = []
    monkeypatch.setattr(epg_module, 'load_json_data', lambda file: cached_data)
    monkeypatch.setattr(epg_module, 'save_json_data', lambda file, data: saved.append(data))
    monkeypatch.setattr(epg_module, 'get_epg', Mock(side_effect=OneplayError('API unavailable')))

    with pytest.raises(OneplayError, match='API unavailable'):
        epg_module.load_epg(reset=True)

    assert saved == []
    assert json.loads(cached_data)['epg'] == VALID_EPG


def test_on_demand_refresh_serves_last_good_epg_on_failure(monkeypatch):
    cached_data = json.dumps({'epg': VALID_EPG})
    saved = []
    monkeypatch.setattr(epg_module, 'load_json_data', lambda file: cached_data)
    monkeypatch.setattr(epg_module, 'save_json_data', lambda file, data: saved.append(data))
    monkeypatch.setattr(epg_module, 'get_epg', Mock(side_effect=OneplayError('API unavailable')))

    assert epg_module.load_epg(reset=True, stale_on_error=True) == VALID_EPG
    assert saved == []


def test_on_demand_epg_skips_refresh_during_api_cooldown(monkeypatch):
    monkeypatch.setattr(epg_module, 'load_json_data', lambda file: json.dumps({'epg': VALID_EPG}))
    monkeypatch.setattr(epg_module, 'get_api_backoff_seconds', lambda: 900)
    monkeypatch.setattr(epg_module, 'get_login_backoff_seconds', lambda: 900)
    get_epg = Mock(side_effect=AssertionError('refresh attempted during cooldown'))
    monkeypatch.setattr(epg_module, 'get_epg', get_epg)

    assert epg_module.load_epg(reset=True, stale_on_error=True) == VALID_EPG
    get_epg.assert_not_called()


def test_next_epg_retry_delay_waits_for_cooldown(monkeypatch):
    monkeypatch.setattr(epg_module, 'get_api_backoff_seconds', lambda: 900)
    monkeypatch.setattr(epg_module, 'get_login_backoff_seconds', lambda: 600)

    assert epg_module.next_epg_retry_delay(4 * 60 * 60) == 900


def test_next_epg_retry_delay_never_precedes_longer_cooldown(monkeypatch):
    monkeypatch.setattr(epg_module, 'get_api_backoff_seconds', lambda: 6 * 60 * 60)
    monkeypatch.setattr(epg_module, 'get_login_backoff_seconds', lambda: 0)

    assert epg_module.next_epg_retry_delay(60 * 60) == 6 * 60 * 60


def test_next_epg_retry_delay_uses_configured_interval_without_cooldown(monkeypatch):
    monkeypatch.setattr(epg_module, 'get_api_backoff_seconds', lambda: 0)
    monkeypatch.setattr(epg_module, 'get_login_backoff_seconds', lambda: 0)

    assert epg_module.next_epg_retry_delay(4 * 60 * 60) == 4 * 60 * 60


def test_load_epg_serves_valid_cache_without_network(monkeypatch):
    monkeypatch.setattr(epg_module, 'load_json_data', lambda file: json.dumps({'epg': VALID_EPG}))
    get_epg = Mock(side_effect=AssertionError('unexpected API access'))
    monkeypatch.setattr(epg_module, 'get_epg', get_epg)

    assert epg_module.load_epg() == VALID_EPG
    get_epg.assert_not_called()


def test_scheduled_epg_refresh_contains_failures(monkeypatch):
    monkeypatch.setattr(epg_module, 'load_epg', Mock(side_effect=OneplayError('API unavailable')))

    assert epg_module.refresh_epg_safely() is False