# -*- coding: utf-8 -*-
import time
from unittest.mock import patch

import resources.lib.stream_cache as cache_module
from resources.lib.helpers import NO_ACCESS_URL


def test_live_cache_hit_and_miss(monkeypatch):
    cache_module.clear()
    monkeypatch.setattr(cache_module, 'get_config_value', lambda key: {'stream_cache_enabled': 1, 'stream_cache_ttl': 45}.get(key))

    assert cache_module.get_live_url('ch1') is None
    cache_module.set_live_url('ch1', 'https://cdn.example/stream.m3u8')
    assert cache_module.get_live_url('ch1') == 'https://cdn.example/stream.m3u8'


def test_live_cache_skips_no_access(monkeypatch):
    cache_module.clear()
    monkeypatch.setattr(cache_module, 'get_config_value', lambda key: {'stream_cache_enabled': 1, 'stream_cache_ttl': 45}.get(key))

    cache_module.set_live_url('ch1', NO_ACCESS_URL)
    assert cache_module.get_live_url('ch1') is None


def test_live_cache_expires(monkeypatch):
    cache_module.clear()
    monkeypatch.setattr(cache_module, 'get_config_value', lambda key: {'stream_cache_enabled': 1, 'stream_cache_ttl': 1}.get(key))

    cache_module.set_live_url('ch1', 'https://cdn.example/stream.m3u8')
    time.sleep(1.1)
    assert cache_module.get_live_url('ch1') is None


def test_cache_disabled(monkeypatch):
    cache_module.clear()
    monkeypatch.setattr(cache_module, 'get_config_value', lambda key: {'stream_cache_enabled': 0, 'stream_cache_ttl': 45}.get(key))

    cache_module.set_live_url('ch1', 'https://cdn.example/stream.m3u8')
    assert cache_module.get_live_url('ch1') is None


def test_archive_cache(monkeypatch):
    cache_module.clear()
    monkeypatch.setattr(cache_module, 'get_config_value', lambda key: {'stream_cache_enabled': 1, 'stream_cache_ttl': 45}.get(key))

    cache_module.set_archive_url('ch1', 100, 200, 'https://cdn.example/archive.m3u8')
    assert cache_module.get_archive_url('ch1', 100, 200) == 'https://cdn.example/archive.m3u8'


def test_clear_removes_entries(monkeypatch):
    cache_module.clear()
    monkeypatch.setattr(cache_module, 'get_config_value', lambda key: {'stream_cache_enabled': 1, 'stream_cache_ttl': 45}.get(key))

    cache_module.set_live_url('ch1', 'https://cdn.example/stream.m3u8')
    cache_module.clear()
    assert cache_module.get_live_url('ch1') is None
