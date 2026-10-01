# -*- coding: utf-8 -*-
import json
import threading
import time
from unittest.mock import patch

import pytest

import resources.lib.session as session_module


@pytest.fixture(autouse=True)
def reset_session_state():
    session_module._login_failure_until = 0
    session_module._login_failure_message = ''
    session_module._login_cooldown_last_log = 0
    yield
    session_module._login_failure_until = 0
    session_module._login_failure_message = ''
    session_module._login_cooldown_last_log = 0


def test_load_session_uses_cache_without_login(monkeypatch, tmp_path):
    session_file = tmp_path / 'session.txt'
    session_file.write_text(
        json.dumps({'token': 'cached-token', 'valid_to': int(time.time()) + 3600}) + '\n',
        encoding='utf-8',
    )

    def fake_load_json_data(file):
        return session_file.read_text(encoding='utf-8').strip()

    monkeypatch.setattr(session_module, 'load_json_data', fake_load_json_data)
    with patch.object(session_module, '_perform_login') as perform_login:
        token = session_module.load_session()
    assert token == 'cached-token'
    perform_login.assert_not_called()


def test_load_session_respects_login_backoff(monkeypatch):
    monkeypatch.setattr(session_module, 'load_json_data', lambda file: None)
    session_module._login_failure_until = int(time.time()) + 60
    session_module._login_failure_message = 'Too Many Requests'

    with patch.object(session_module, '_perform_login') as perform_login:
        with pytest.raises(session_module.OneplayError, match='Too Many Requests'):
            session_module.load_session()

    perform_login.assert_not_called()


def test_api_cooldown_sets_login_backoff_from_retry_after():
    now = int(time.time())
    with pytest.raises(session_module.OneplayError, match='API cooldown aktivní'):
        session_module._fail_login('Problém při přihlášení', {
            'cooldown': True,
            'retry_after': 240,
            'err': 'Oneplay API cooldown: Too Many Requests',
        })

    assert session_module._login_failure_until == now + 240
    assert session_module._login_failure_message.startswith('API cooldown aktivní:')


def test_login_backoff_is_logged_as_cooldown_without_request_spam(monkeypatch):
    monkeypatch.setattr(session_module, 'load_json_data', lambda file: None)
    session_module._login_failure_until = int(time.time()) + 60
    session_module._login_failure_message = 'API cooldown aktivní: Too Many Requests'

    with patch.object(session_module, 'log_error') as log:
        for _ in range(3):
            with pytest.raises(session_module.OneplayError, match='API cooldown aktivní'):
                session_module.load_session()

    log.assert_called_once()
    assert log.call_args.args[0] == 'Přihlašovací cooldown aktivní'
    assert 'další pokus za' in log.call_args.args[1]


def test_load_session_serializes_parallel_refresh(monkeypatch):
    storage = {'data': None}
    saved = []
    concurrent = {'max': 0, 'current': 0}
    gate = threading.Lock()

    def fake_load_json_data(file):
        return storage['data']

    def fake_save_json_data(file, data):
        storage['data'] = data
        saved.append(data)

    def slow_login():
        with gate:
            concurrent['current'] += 1
            concurrent['max'] = max(concurrent['max'], concurrent['current'])
        time.sleep(0.05)
        with gate:
            concurrent['current'] -= 1
        return 'fresh-token'

    monkeypatch.setattr(session_module, 'load_json_data', fake_load_json_data)
    monkeypatch.setattr(session_module, 'save_json_data', fake_save_json_data)
    monkeypatch.setattr(session_module, '_perform_login', slow_login)

    threads = [threading.Thread(target=session_module.load_session) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert concurrent['max'] == 1
    assert len(saved) == 1
