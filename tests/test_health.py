# -*- coding: utf-8 -*-
import json
from unittest.mock import patch

import resources.lib.web as web_module
from resources.lib.utils import OneplayError


def test_health_ok_when_session_and_channels_cached(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: True)
    monkeypatch.setattr(web_module, 'read_channels_cache', lambda: ({'ch1': {}}, 42))
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_api_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_version', lambda: '1.5.7')
    monkeypatch.setattr(web_module, 'load_api_version', lambda: 'v1.11')

    body = json.loads(web_module.health())

    assert body['status'] == 'ok'
    assert body['session_cached'] is True
    assert body['channels_cached'] == 42
    assert body['api_version'] == 'v1.11'
    assert body['login_backoff'] == 0
    assert body['api_backoff'] == 0


def test_health_degraded_on_login_backoff(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: True)
    monkeypatch.setattr(web_module, 'read_channels_cache', lambda: ({'ch1': {}}, 10))
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 120)
    monkeypatch.setattr(web_module, 'get_api_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_version', lambda: '1.5.7')
    monkeypatch.setattr(web_module, 'load_api_version', lambda: 'v1.11')

    body = json.loads(web_module.health())

    assert body['status'] == 'degraded'
    assert body['login_backoff'] == 120


def test_health_degraded_without_session(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: False)
    monkeypatch.setattr(web_module, 'read_channels_cache', lambda: (None, 0))
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_api_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_version', lambda: '1.5.7')
    monkeypatch.setattr(web_module, 'load_api_version', lambda: 'v1.11')

    body = json.loads(web_module.health())

    assert body['status'] == 'degraded'
    assert body['session_cached'] is False
    assert body['channels_cached'] == 0


def test_health_degraded_on_api_backoff(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: True)
    monkeypatch.setattr(web_module, 'read_channels_cache', lambda: ({'ch1': {}}, 10))
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_api_backoff_seconds', lambda: 900)
    monkeypatch.setattr(web_module, 'get_version', lambda: '1.5.7')
    monkeypatch.setattr(web_module, 'load_api_version', lambda: 'v1.11')

    body = json.loads(web_module.health())

    assert body['status'] == 'degraded'
    assert body['api_backoff'] == 900


def test_health_error_on_exception(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: (_ for _ in ()).throw(RuntimeError('boom')))

    body = json.loads(web_module.health())

    assert body['status'] == 'error'
    assert 'boom' in body['message']


def test_oneplay_error_plugin_returns_retry_after(monkeypatch):
    class FakeResponse:
        status = None
        content_type = None
        headers = {}

        def set_header(self, name, value):
            self.headers[name] = value

    fake_response = FakeResponse()
    monkeypatch.setattr(web_module, 'response', fake_response)
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_api_backoff_seconds', lambda: 120)

    def fail():
        raise OneplayError('Too Many Requests')

    wrapped = web_module.OneplayErrorPlugin().apply(fail, None)

    assert wrapped() == 'Too Many Requests'
    assert fake_response.status == 503
    assert fake_response.headers['Retry-After'] == '120'
