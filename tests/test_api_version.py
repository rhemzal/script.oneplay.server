# -*- coding: utf-8 -*-
import json
import time
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

import pytest

import resources.lib.api as api_module


@pytest.fixture
def json_storage(monkeypatch):
    storage = {}

    def fake_load(file):
        return storage.get(file['filename'])

    def fake_save(file, data):
        storage[file['filename']] = data

    monkeypatch.setattr(api_module, 'load_json_data', fake_load)
    monkeypatch.setattr(api_module, 'save_json_data', fake_save)
    monkeypatch.setattr(api_module, '_API_BACKOFF_STATE', None)
    monkeypatch.setattr(api_module, '_API_PROBE_IN_PROGRESS', False)
    monkeypatch.setattr(api_module, '_API_COOLDOWN_LAST_LOG', 0)
    storage['api_version_check.txt'] = json.dumps({'checked_at': int(time.time())})
    return storage


def test_load_api_version_defaults_to_base(json_storage):
    version = api_module.load_api_version()
    assert version == api_module.BASE_API_VERSION
    saved = json.loads(json_storage['api_version.txt'])
    assert saved['api_version'] == api_module.BASE_API_VERSION


def test_api_backoff_base_delays_are_one_minute():
    assert api_module._API_RATE_LIMIT_DELAY == 60
    assert api_module._API_NOT_FOUND_DELAY == 60
    assert api_module._API_TRANSIENT_DELAY == 60


def test_api_version_check_interval_is_six_hours():
    assert api_module._API_VERSION_CHECK_INTERVAL == 6 * 60 * 60


def test_load_api_version_reads_persisted_value(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.12'})
    assert api_module.load_api_version() == 'v1.12'


def test_api_url_uses_loaded_version(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.12'})
    assert api_module.api_url('content.play') == 'https://http.cms.jyxo.cz/api/v1.12/content.play'
    assert api_module.api_url('/epg.display') == 'https://http.cms.jyxo.cz/api/v1.12/epg.display'


def test_get_api_version_detects_new_version(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})

    def fake_urlopen(request, timeout=10):
        url = request.full_url
        if 'v1.12' in url:
            raise HTTPError(url, 404, 'Not Found', None, None)
        if 'v1.13' in url:
            raise HTTPError(url, 400, 'Bad Request', None, None)
        raise HTTPError(url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.get_api_version()

    assert version == 'v1.13'
    saved = json.loads(json_storage['api_version.txt'])
    assert saved['api_version'] == 'v1.13'


def test_get_api_version_accepts_successful_probe_response(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    response = MagicMock()
    response.getcode.return_value = 200

    def supported_then_missing(request, timeout=10):
        if 'v1.12/' in request.full_url:
            return response
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', supported_then_missing):
        version = api_module.get_api_version()

    assert version == 'v1.12'
    assert json.loads(json_storage['api_version.txt'])['api_version'] == 'v1.12'


def test_monthly_check_promotes_next_minor_version(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    json_storage['api_version_check.txt'] = json.dumps({'checked_at': 0})
    response = MagicMock()
    response.getcode.return_value = 200
    calls = []

    def supported_then_missing(request, timeout=10):
        calls.append(request.full_url)
        if 'v1.12/' in request.full_url:
            return response
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', supported_then_missing):
        version = api_module.check_api_version_if_due()

    assert version == 'v1.12'
    assert len(calls) == 2
    assert json.loads(json_storage['api_version.txt'])['api_version'] == 'v1.12'
    assert int(json.loads(json_storage['api_version_check.txt'])['checked_at']) > 0


def test_monthly_check_accepts_bad_request_as_supported_version(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    json_storage['api_version_check.txt'] = json.dumps({'checked_at': 0})

    def bad_request_probe(request, timeout=10):
        if 'v1.12/' in request.full_url:
            raise HTTPError(request.full_url, 400, 'Bad Request', None, None)
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', bad_request_probe):
        version = api_module.check_api_version_if_due()

    assert version == 'v1.12'
    assert json.loads(json_storage['api_version.txt'])['api_version'] == 'v1.12'


def test_monthly_check_is_skipped_until_interval_elapses(json_storage):
    json_storage['api_version_check.txt'] = json.dumps({'checked_at': int(time.time())})

    with patch.object(api_module, 'urlopen') as probe:
        version = api_module.check_api_version_if_due()

    assert version == api_module.BASE_API_VERSION
    probe.assert_not_called()


def test_monthly_check_retains_current_version_when_candidate_is_missing(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    json_storage['api_version_check.txt'] = json.dumps({'checked_at': 0})

    def fake_urlopen(request, timeout=10):
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.check_api_version_if_due()

    assert version == 'v1.11'
    assert json.loads(json_storage['api_version.txt'])['api_version'] == 'v1.11'
    assert int(json.loads(json_storage['api_version_check.txt'])['checked_at']) > 0


def test_monthly_check_is_skipped_during_backoff(json_storage, monkeypatch):
    monkeypatch.setattr(api_module, '_API_BACKOFF_STATE', {
        'failures': 1,
        'kind': 'rate_limit',
        'retry_until': int(time.time()) + 60,
    })
    with patch.object(api_module, 'urlopen') as probe:
        version = api_module.check_api_version_if_due()

    assert version == api_module.BASE_API_VERSION
    probe.assert_not_called()


def test_call_api_rebases_url_after_monthly_version_update(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    json_storage['api_version_check.txt'] = json.dumps({'checked_at': 0})
    response = MagicMock()
    response.getcode.return_value = 200

    def supported_then_missing(request, timeout=10):
        if 'v1.12/' in request.full_url:
            return response
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', supported_then_missing):
        with patch.object(api_module, '_call_api_unchecked', return_value={'result': {'status': 'Ok'}}) as request:
            api_module.call_api(api_module.API_BASE + 'v1.11/epg.display', {}, token=None)

    assert request.call_args.args[0] == api_module.API_BASE + 'v1.12/epg.display'


def test_monthly_probe_429_blocks_the_main_api_request(json_storage):
    json_storage['api_version_check.txt'] = json.dumps({'checked_at': 0})

    def rate_limited_probe(request, timeout=10):
        raise HTTPError(request.full_url, 429, 'Too Many Requests', None, None)

    with patch.object(api_module, 'urlopen', rate_limited_probe):
        with patch.object(api_module, '_call_api_unchecked') as request:
            result = api_module.call_api(api_module.API_BASE + 'v1.11/epg.display', {})

    assert result['cooldown'] is True
    assert result['retry_after'] == api_module._API_RATE_LIMIT_DELAY
    request.assert_not_called()
    assert json.loads(json_storage['api_backoff.txt'])['kind'] == 'rate_limit'


def test_get_api_version_scans_a_bounded_batch_after_404(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    calls = []

    def fake_urlopen(request, timeout=10):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.get_api_version()

    assert version == 'v1.11'
    assert len(calls) == api_module._API_VERSION_PROBE_BATCH
    assert json.loads(json_storage['api_version_probe.txt'])['next_minor'] == 17


def test_get_api_version_accepts_unauthorized_response_as_supported_endpoint(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})

    def unauthorized_probe(request, timeout=10):
        if 'v1.12/' in request.full_url:
            raise HTTPError(request.full_url, 401, 'Unauthorized', None, None)
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', unauthorized_probe):
        version = api_module.get_api_version()

    assert version == 'v1.12'
    assert json.loads(json_storage['api_version.txt'])['api_version'] == 'v1.12'
    assert json_storage['api_version_probe.txt'] == '{}'


def test_get_api_version_saves_cursor_before_transient_probe_failure(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})

    def not_found_then_unavailable(request, timeout=10):
        if 'v1.12/' in request.full_url:
            raise HTTPError(request.full_url, 404, 'Not Found', None, None)
        raise HTTPError(request.full_url, 503, 'Service Unavailable', None, None)

    with patch.object(api_module, 'urlopen', not_found_then_unavailable):
        version = api_module.get_api_version()

    assert version == 'v1.11'
    assert json.loads(json_storage['api_version_probe.txt'])['next_minor'] == 13
    assert json.loads(json_storage['api_backoff.txt'])['kind'] == 'transient'


def test_get_api_version_resumes_from_cursor_and_saves_discovered_version(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    json_storage['api_version_probe.txt'] = json.dumps({'next_minor': 17})
    calls = []

    def fake_urlopen(request, timeout=10):
        calls.append(request.full_url)
        if 'v1.17/' in request.full_url:
            raise HTTPError(request.full_url, 404, 'Not Found', None, None)
        if 'v1.18/' in request.full_url:
            raise HTTPError(request.full_url, 400, 'Bad Request', None, None)
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.get_api_version()

    assert version == 'v1.18'
    assert len(calls) == 3
    assert json.loads(json_storage['api_version.txt'])['api_version'] == 'v1.18'
    assert json_storage['api_version_probe.txt'] == '{}'


def test_404_retries_original_request_once_with_discovered_version(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    websocket = MagicMock()
    websocket.recv.return_value = json.dumps({'data': {'serverId': 'server'}})
    response = MagicMock()
    response.getheader.return_value = None
    urls = []

    def discover_version():
        api_module.save_api_version('v1.12')
        return 'v1.12'

    def fake_urlopen(request, timeout=20):
        urls.append(request.full_url)
        if 'v1.11/' in request.full_url:
            raise HTTPError(request.full_url, 404, 'Not Found', None, None)
        body = json.loads(request.data)
        response.read.return_value = json.dumps({
            'result': {'status': 'Ok'},
            'context': {'requestId': body['context']['requestId']},
            'data': {'ok': True},
        }).encode('utf-8')
        return response

    with patch.object(api_module, 'create_connection', return_value=websocket):
        with patch.object(api_module, 'urlopen', fake_urlopen):
            with patch.object(api_module, 'get_api_version', side_effect=discover_version):
                result = api_module._call_api_unchecked(
                    api_module.API_BASE + 'v1.11/user.login.step',
                    {},
                )

    assert result == {'ok': True}
    assert urls == [
        api_module.API_BASE + 'v1.11/user.login.step',
        api_module.API_BASE + 'v1.12/user.login.step',
    ]


def test_get_api_version_skips_probe_on_429(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})

    def fake_urlopen(request, timeout=10):
        raise HTTPError(request.full_url, 429, 'Too Many Requests', None, None)

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.get_api_version()

    assert version == 'v1.11'
    assert json.loads(json_storage['api_backoff.txt'])['kind'] == 'rate_limit'


def test_api_rate_limit_is_persisted_and_blocks_followup_calls(json_storage):
    with patch.object(
        api_module,
        '_call_api_unchecked',
        return_value={'result': {'status': 'Error', 'message': 'Too Many Requests'}},
    ) as request:
        result = api_module.call_api('https://example/api', {}, token=None)
        assert result['retry_after'] == api_module._API_RATE_LIMIT_DELAY

        api_module._API_BACKOFF_STATE = None
        assert api_module.get_api_backoff_seconds() > 0
        blocked = api_module.call_api('https://example/api', {}, token=None)

    assert request.call_count == 1
    assert blocked['retry_after'] > 0
    assert 'cooldown' in blocked['err']
    state = json.loads(json_storage['api_backoff.txt'])
    assert state['kind'] == 'rate_limit'
    assert state['failures'] == 1


def test_api_cooldown_is_logged_explicitly_and_throttled(json_storage):
    api_module._API_BACKOFF_STATE = {'kind': 'rate_limit', 'failures': 1, 'retry_until': int(time.time()) + 60}
    with patch.object(api_module, 'log_error') as log:
        api_module._api_cooldown_result(60)
        api_module._api_cooldown_result(59)

    log.assert_called_once()
    assert log.call_args.args[0] == 'API cooldown aktivní'
    assert 'další pokus za 60 s' in log.call_args.args[1]


def test_http_not_found_uses_persistent_backoff(json_storage):
    with patch.object(
        api_module,
        '_call_api_unchecked',
        return_value={'err': 'Not Found', 'http_status': 404},
    ) as request:
        result = api_module.call_api('https://example/api', {}, token=None)
        blocked = api_module.call_api('https://example/api', {}, token=None)

    assert result['retry_after'] == api_module._API_NOT_FOUND_DELAY
    assert blocked['retry_after'] > 0
    request.assert_called_once()
    assert json.loads(json_storage['api_backoff.txt'])['kind'] == 'not_found'


def test_transient_api_failure_uses_shorter_backoff(json_storage):
    with patch.object(api_module, '_call_api_unchecked', side_effect=OSError('offline')) as request:
        result = api_module.call_api('https://example/api', {}, token=None)
        blocked = api_module.call_api('https://example/api', {}, token=None)

    assert result['retry_after'] == api_module._API_TRANSIENT_DELAY
    assert blocked['retry_after'] > 0
    request.assert_called_once()


def test_websocket_rate_limit_uses_rate_limit_backoff(json_storage):
    error = api_module.WebSocketException('429 Too Many Requests')
    error.status_code = 429
    with patch.object(api_module, '_call_api_unchecked', side_effect=error):
        result = api_module.call_api('https://example/api', {}, token=None)

    assert result['retry_after'] == api_module._API_RATE_LIMIT_DELAY
    assert json.loads(json_storage['api_backoff.txt'])['kind'] == 'rate_limit'


def test_half_open_waiters_do_not_reset_cooldown(json_storage, monkeypatch):
    original_until = 1
    monkeypatch.setattr(api_module.time, 'time', lambda: 100)
    monkeypatch.setattr(api_module, '_API_BACKOFF_STATE', {
        'failures': 1,
        'kind': 'rate_limit',
        'retry_until': original_until,
    })
    monkeypatch.setattr(api_module, '_API_PROBE_IN_PROGRESS', True)

    with patch.object(api_module, '_call_api_unchecked') as request:
        result = api_module.call_api('https://example/api', {}, token=None)

    assert result['retry_after'] == api_module._API_TRANSIENT_DELAY
    assert api_module._API_PROBE_IN_PROGRESS is True
    assert api_module._API_BACKOFF_STATE['retry_until'] == original_until
    request.assert_not_called()


def test_transient_half_open_waiters_do_not_extend_backoff(json_storage, monkeypatch):
    monkeypatch.setattr(api_module.time, 'time', lambda: 100)
    monkeypatch.setattr(api_module, '_API_BACKOFF_STATE', {
        'failures': 2,
        'kind': 'transient',
        'retry_until': 1,
    })
    monkeypatch.setattr(api_module, '_API_PROBE_IN_PROGRESS', True)

    with patch.object(api_module, '_call_api_unchecked') as request:
        result = api_module.call_api('https://example/api', {}, token=None)

    assert result['cooldown'] is True
    assert api_module._API_PROBE_IN_PROGRESS is True
    assert api_module._API_BACKOFF_STATE['failures'] == 2
    request.assert_not_called()


def test_invalid_persisted_api_backoff_state_is_ignored(json_storage):
    json_storage['api_backoff.txt'] = json.dumps({
        'retry_until': 'invalid',
        'failures': None,
    })
    api_module._API_BACKOFF_STATE = None

    assert api_module.get_api_backoff_seconds() == 0
