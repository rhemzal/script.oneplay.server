# -*- coding: utf-8 -*-
import threading
import time

from resources.lib.helpers import is_truthy, NO_ACCESS_URL
from resources.lib.utils import get_config_value

_lock = threading.RLock()
_cache = {}


def _enabled():
    value = get_config_value('stream_cache_enabled')
    if value is None:
        return True
    return is_truthy(value)


def _ttl():
    value = get_config_value('stream_cache_ttl')
    try:
        ttl = int(value) if value is not None else 45
    except (TypeError, ValueError):
        ttl = 45
    return max(1, ttl)


def _is_cacheable(url):
    if not url or url == NO_ACCESS_URL:
        return False
    if 'noAccess' in url:
        return False
    return True


def _get(key):
    if not _enabled():
        return None
    with _lock:
        entry = _cache.get(key)
        if entry and entry[1] > time.time():
            return entry[0]
        if entry:
            del _cache[key]
    return None


def _set(key, url):
    if not _enabled() or not _is_cacheable(url):
        return
    with _lock:
        _cache[key] = (url, time.time() + _ttl())


def get_live_url(channel_id):
    return _get(('live', str(channel_id)))


def set_live_url(channel_id, url):
    _set(('live', str(channel_id)), url)


def get_archive_url(channel_id, start_ts, end_ts):
    return _get(('archive', str(channel_id), int(start_ts), int(end_ts)))


def set_archive_url(channel_id, start_ts, end_ts, url):
    _set(('archive', str(channel_id), int(start_ts), int(end_ts)), url)


def clear():
    with _lock:
        _cache.clear()
