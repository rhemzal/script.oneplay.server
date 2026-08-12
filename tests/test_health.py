# -*- coding: utf-8 -*-
import json
from unittest.mock import patch

import resources.lib.web as web_module


def test_health_ok_when_session_and_channels_cached(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: True)
    monkeypatch.setattr(web_module, 'read_channels_cache', lambda: ({'ch1': {}}, 42))
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_version', lambda: '1.5.7')
    monkeypatch.setattr(web_module, 'load_api_version', lambda: 'v1.11')

    body = json.loads(web_module.health())

    assert body['status'] == 'ok'
    assert body['session_cached'] is True
    assert body['channels_cached'] == 42
    assert body['api_version'] == 'v1.11'
    assert body['login_backoff'] == 0


def test_health_degraded_on_login_backoff(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: True)
    monkeypatch.setattr(web_module, 'read_channels_cache', lambda: ({'ch1': {}}, 10))
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 120)
    monkeypatch.setattr(web_module, 'get_version', lambda: '1.5.7')
    monkeypatch.setattr(web_module, 'load_api_version', lambda: 'v1.11')

    body = json.loads(web_module.health())

    assert body['status'] == 'degraded'
    assert body['login_backoff'] == 120


def test_health_degraded_without_session(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: False)
    monkeypatch.setattr(web_module, 'read_channels_cache', lambda: (None, 0))
    monkeypatch.setattr(web_module, 'get_login_backoff_seconds', lambda: 0)
    monkeypatch.setattr(web_module, 'get_version', lambda: '1.5.7')
    monkeypatch.setattr(web_module, 'load_api_version', lambda: 'v1.11')

    body = json.loads(web_module.health())

    assert body['status'] == 'degraded'
    assert body['session_cached'] is False
    assert body['channels_cached'] == 0


def test_health_error_on_exception(monkeypatch):
    monkeypatch.setattr(web_module, 'is_session_cached', lambda: (_ for _ in ()).throw(RuntimeError('boom')))

    body = json.loads(web_module.health())

    assert body['status'] == 'error'
    assert 'boom' in body['message']
