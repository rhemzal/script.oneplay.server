# -*- coding: utf-8 -*-
import json
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
    return storage


def test_load_api_version_defaults_to_base(json_storage):
    version = api_module.load_api_version()
    assert version == api_module.BASE_API_VERSION
    saved = json.loads(json_storage['api_version.txt'])
    assert saved['api_version'] == api_module.BASE_API_VERSION


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
        return MagicMock()

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.get_api_version()

    assert version == 'v1.13'
    saved = json.loads(json_storage['api_version.txt'])
    assert saved['api_version'] == 'v1.13'


def test_get_api_version_stops_after_consecutive_404(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})
    calls = []

    def fake_urlopen(request, timeout=10):
        calls.append(request.full_url)
        raise HTTPError(request.full_url, 404, 'Not Found', None, None)

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.get_api_version()

    assert version == 'v1.11'
    assert len(calls) == 3


def test_get_api_version_skips_probe_on_429(json_storage):
    json_storage['api_version.txt'] = json.dumps({'api_version': 'v1.11'})

    def fake_urlopen(request, timeout=10):
        raise HTTPError(request.full_url, 429, 'Too Many Requests', None, None)

    with patch.object(api_module, 'urlopen', fake_urlopen):
        version = api_module.get_api_version()

    assert version == 'v1.11'
