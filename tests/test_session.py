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
    yield
    session_module._login_failure_until = 0
    session_module._login_failure_message = ''


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
