# -*- coding: utf-8 -*-
import json
import gzip
import socket
import threading
import time
import uuid
from email.utils import parsedate_to_datetime
from websocket import create_connection
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from websocket import WebSocketException

from resources.lib.utils import appVersion, get_config_value, log_message, log_error, load_json_data, save_json_data

BASE_API_VERSION = 'v1.11'
API_BASE = 'https://http.cms.jyxo.cz/api/'
_API_BACKOFF_FILE = {'filename': 'api_backoff.txt', 'description': 'API cooldown'}
_API_VERSION_PROBE_FILE = {'filename': 'api_version_probe.txt', 'description': 'API version probe'}
_API_VERSION_CHECK_FILE = {'filename': 'api_version_check.txt', 'description': 'API version check'}
_API_BACKOFF_LOCK = threading.RLock()
_API_VERSION_CHECK_LOCK = threading.RLock()
_API_BACKOFF_STATE = None
_API_PROBE_IN_PROGRESS = False
_API_COOLDOWN_LOG_INTERVAL = 60
_API_COOLDOWN_LAST_LOG = 0
_API_RATE_LIMIT_DELAY = 15 * 60
_API_TRANSIENT_DELAY = 30
_API_MAX_TRANSIENT_DELAY = 15 * 60
_API_MAX_RATE_LIMIT_DELAY = 6 * 60 * 60
_API_NOT_FOUND_DELAY = 15 * 60
_API_VERSION_PROBE_BATCH = 5
_API_MAX_VERSION = 49
_API_VERSION_CHECK_INTERVAL = 30 * 24 * 60 * 60


def _load_api_backoff_state():
    global _API_BACKOFF_STATE
    if _API_BACKOFF_STATE is None:
        data = load_json_data(_API_BACKOFF_FILE)
        try:
            loaded = json.loads(data) if data else {}
            _API_BACKOFF_STATE = loaded if isinstance(loaded, dict) else {}
        except (TypeError, ValueError):
            _API_BACKOFF_STATE = {}
    return _API_BACKOFF_STATE


def _state_int(state, key):
    try:
        return int(state.get(key, 0))
    except (TypeError, ValueError):
        return 0


def get_api_backoff_seconds():
    with _API_BACKOFF_LOCK:
        state = _load_api_backoff_state()
        return max(0, _state_int(state, 'retry_until') - int(time.time()))


def _api_request_backoff():
    global _API_PROBE_IN_PROGRESS
    with _API_BACKOFF_LOCK:
        state = _load_api_backoff_state()
        remaining = max(0, _state_int(state, 'retry_until') - int(time.time()))
        if remaining:
            return remaining
        if _state_int(state, 'failures') > 0:
            if _API_PROBE_IN_PROGRESS:
                return _API_TRANSIENT_DELAY
            _API_PROBE_IN_PROGRESS = True
        return 0


def _store_api_failure(kind, retry_after=None):
    global _API_BACKOFF_STATE, _API_PROBE_IN_PROGRESS
    with _API_BACKOFF_LOCK:
        previous = _load_api_backoff_state()
        failures = min(20, max(0, _state_int(previous, 'failures')) + 1)
        if kind == 'rate_limit':
            delay = min(_API_RATE_LIMIT_DELAY * (2 ** (failures - 1)), _API_MAX_RATE_LIMIT_DELAY)
        elif kind == 'not_found':
            delay = min(_API_NOT_FOUND_DELAY * (2 ** (failures - 1)), _API_MAX_RATE_LIMIT_DELAY)
        else:
            delay = min(_API_TRANSIENT_DELAY * (2 ** (failures - 1)), _API_MAX_TRANSIENT_DELAY)
        if retry_after is not None:
            delay = max(delay, min(int(retry_after), 24 * 60 * 60))
        state = {
            'failures': failures,
            'kind': kind,
            'retry_until': int(time.time()) + delay,
        }
        _API_BACKOFF_STATE = state
        _API_PROBE_IN_PROGRESS = False
        save_json_data(_API_BACKOFF_FILE, json.dumps(state))
        return delay


def _clear_api_backoff():
    global _API_BACKOFF_STATE, _API_PROBE_IN_PROGRESS
    with _API_BACKOFF_LOCK:
        previous = _load_api_backoff_state()
        _API_BACKOFF_STATE = {}
        _API_PROBE_IN_PROGRESS = False
        if previous:
            save_json_data(_API_BACKOFF_FILE, '{}')


def _retry_after_seconds(value):
    if not value:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int(parsedate_to_datetime(value).timestamp() - time.time()))
        except (TypeError, ValueError, OverflowError):
            return None


def _is_rate_limit_error(message):
    message = str(message or '').lower()
    return 'too many requests' in message or '429' in message


def _is_transient_error(message):
    message = str(message or '').lower()
    return any(
        marker in message
        for marker in (
            'internal server error',
            'service unavailable',
            'temporarily unavailable',
            'bad gateway',
            'gateway timeout',
            'request timeout',
        )
    )


def load_api_version():
    data = load_json_data({'filename': 'api_version.txt', 'description': 'verze API'})
    if data:
        try:
            parsed = json.loads(data)
            version = parsed.get('api_version', BASE_API_VERSION)
            if version:
                return version
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    save_api_version(BASE_API_VERSION)
    return BASE_API_VERSION


def save_api_version(api_version):
    save_json_data(
        {'filename': 'api_version.txt', 'description': 'verze API'},
        json.dumps({'api_version': api_version}),
    )


def _save_api_version_check(checked_at=None):
    if checked_at is None:
        checked_at = int(time.time())
    save_json_data(_API_VERSION_CHECK_FILE, json.dumps({'checked_at': int(checked_at)}))


def _probe_api_version(version):
    url = API_BASE + version + '/user.login.step'
    request = Request(
        url=url,
        data=json.dumps({}).encode('utf-8'),
        headers={'Content-Type': 'application/json;charset=UTF-8'},
        method='POST',
    )
    response = urlopen(request, timeout=10)
    try:
        return response.getcode()
    finally:
        response.close()


def check_api_version_if_due():
    with _API_VERSION_CHECK_LOCK:
        current_version = load_api_version()
        if _API_PROBE_IN_PROGRESS or get_api_backoff_seconds() > 0:
            return current_version

        data = load_json_data(_API_VERSION_CHECK_FILE)
        try:
            checked_at = int(json.loads(data).get('checked_at', 0)) if data else 0
        except (AttributeError, TypeError, ValueError):
            checked_at = 0
        now = int(time.time())
        if now - checked_at < _API_VERSION_CHECK_INTERVAL:
            return current_version

        try:
            prefix, minor_text = current_version.split('.', 1)
            major = int(prefix.lstrip('v'))
            minor = int(minor_text)
        except (AttributeError, TypeError, ValueError):
            _save_api_version_check(now)
            return current_version
        if major != 1 or minor >= _API_MAX_VERSION:
            _save_api_version_check(now)
            return current_version

        candidate = 'v1.' + str(minor + 1).zfill(2)
        try:
            status = _probe_api_version(candidate)
        except HTTPError as error:
            if error.code == 400:
                save_api_version(candidate)
                save_json_data(_API_VERSION_PROBE_FILE, '{}')
                _save_api_version_check(now)
                log_message('Verze Oneplay API aktualizována na ' + candidate)
                return candidate
            if error.code == 404:
                _save_api_version_check(now)
                return current_version
            if error.code == 429:
                delay = _store_api_failure(
                    'rate_limit',
                    _retry_after_seconds(error.headers.get('Retry-After') if error.headers else None),
                )
                log_error('Kontrola verze API', 'Too Many Requests – další pokus za ' + str(delay) + ' s')
                return current_version
            if error.code == 408 or error.code >= 500:
                _store_api_failure('transient')
                return current_version
            _save_api_version_check(now)
            return current_version
        except (URLError, OSError, socket.timeout, TimeoutError, WebSocketException) as error:
            _store_api_failure('transient')
            log_error('Kontrola verze API selhala', str(error))
            return current_version

        if status is None or 200 <= status < 300:
            save_api_version(candidate)
            save_json_data(_API_VERSION_PROBE_FILE, '{}')
            _save_api_version_check(now)
            log_message('Verze Oneplay API aktualizována na ' + candidate)
            return candidate
        _save_api_version_check(now)
        return current_version


def get_api_version():
    api_version = load_api_version()
    try:
        start_version = int(api_version.split('.')[1])
    except (IndexError, ValueError):
        return api_version
    probe_data = load_json_data(_API_VERSION_PROBE_FILE)
    try:
        next_minor = int(json.loads(probe_data).get('next_minor', start_version + 1))
    except (AttributeError, TypeError, ValueError):
        next_minor = start_version + 1
    next_minor = max(start_version + 1, min(next_minor, _API_MAX_VERSION + 1))
    end_minor = min(next_minor + _API_VERSION_PROBE_BATCH, _API_MAX_VERSION + 1)
    for minor in range(next_minor, end_minor):
        version = 'v1.' + str(minor).zfill(2)
        try:
            status = _probe_api_version(version)
            if status is None or 200 <= status < 300:
                save_api_version(version)
                save_json_data(_API_VERSION_PROBE_FILE, '{}')
                _save_api_version_check()
                return version
            return api_version
        except HTTPError as e:
            if e.code == 404:
                continue
            if e.code == 400:
                save_api_version(version)
                save_json_data(_API_VERSION_PROBE_FILE, '{}')
                _save_api_version_check()
                return version
            if e.code == 429:
                delay = _store_api_failure(
                    'rate_limit',
                    _retry_after_seconds(e.headers.get('Retry-After') if e.headers else None),
                )
                log_error('Detekce verze API', 'Too Many Requests – další pokus za ' + str(delay) + ' s')
                return api_version
            if e.code == 408 or e.code >= 500:
                _store_api_failure('transient', _retry_after_seconds(e.headers.get('Retry-After') if e.headers else None))
            return api_version
    if end_minor <= _API_MAX_VERSION:
        save_json_data(_API_VERSION_PROBE_FILE, json.dumps({'next_minor': end_minor}))
    _save_api_version_check()
    return api_version


def api_url(endpoint):
    endpoint = endpoint.lstrip('/')
    return API_BASE + load_api_version() + '/' + endpoint


def _call_api_unchecked(url, data, token=None, probe_version=True):
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0',
        'Accept-Encoding': 'gzip',
        'Accept': '*/*',
        'Content-type': 'application/json;charset=UTF-8',
    }
    if token is not None:
        headers['Authorization'] = 'Bearer ' + token
    if get_config_value('debug') == 1 or get_config_value('debug') == '1' or get_config_value('debug') == -1 or get_config_value('debug') == '-1' or get_config_value('debug') == 'true':
        log_message(str(url))
        log_message(str(data))
    ws = None
    try:
        requestId = str(uuid.uuid4())
        clientId = str(uuid.uuid4())
        ws = create_connection('wss://ws.cms.jyxo.cz/websocket/' + clientId)
        ws_data = json.loads(ws.recv())
        post = {
            'deviceInfo': {
                'deviceType': 'web',
                'appVersion': appVersion,
                'deviceManufacturer': 'Unknown',
                'deviceOs': 'Linux',
            },
            'capabilities': {'async': 'websockets'},
            'context': {
                'requestId': requestId,
                'clientId': clientId,
                'sessionId': ws_data['data']['serverId'],
                'serverId': ws_data['data']['serverId'],
            },
        }
        if data is not None:
            post = {**data, **post}
        post = json.dumps(post).encode('utf-8')
        request = Request(url=url, data=post, headers=headers)
        response = urlopen(request, timeout=20)
        if response.getheader('Content-Encoding') == 'gzip':
            gzipFile = gzip.GzipFile(fileobj=response)
            data = gzipFile.read()
        else:
            data = response.read()
        if len(data) > 0:
            data = json.loads(data)
        if 'result' not in data or 'status' not in data['result'] or data['result']['status'] not in ['OkAsync', 'Ok']:
            api_msg = data.get('result', {}).get('message', 'Chyba při volání API')
            log_error('Chyba API ' + str(url), api_msg)
            ws.close()
            return {'result': {'status': 'Error', 'message': api_msg}}
        if data['result']['status'] == 'OkAsync':
            response = ws.recv()
            if (type(get_config_value('debug')) == int and get_config_value('debug') > 0) or get_config_value('debug') == '1' or get_config_value('debug') == 'true':
                if type(get_config_value('debug')) == int and get_config_value('debug') > 1 and len(str(response)) > get_config_value('debug'):
                    log_message('Odpověď obdržena (' + str(len(str(response))) + ')')
                else:
                    log_message(str(response))
            if response and len(response) > 0:
                data = json.loads(response)
                if 'response' not in data or 'result' not in data['response'] or 'status' not in data['response']['result'] or data['response']['result']['status'] != 'Ok' or data['response']['context']['requestId'] != requestId:
                    log_error('Chyba API ' + str(url), 'Neplatná asynchronní odpověď')
                    ws.close()
                    return {'err': 'Chyba při volání API'}
                ws.close()
                if 'data' in data['response']:
                    return data['response']['data']
                return []
            ws.close()
            return []
        elif data['result']['status'] == 'Ok':
            ws.close()
            if (type(get_config_value('debug')) == int and get_config_value('debug') > 0) or get_config_value('debug') == '1' or get_config_value('debug') == 'true':
                if type(get_config_value('debug')) == int and get_config_value('debug') > 1 and len(str(data)) > get_config_value('debug'):
                    log_message('Odpověď obdržena (' + str(len(str(data))) + ')')
                else:
                    log_message(str(data))
            if 'result' not in data or 'status' not in data['result'] or data['result']['status'] != 'Ok' or data['context']['requestId'] != requestId:
                log_error('Chyba API ' + str(url), 'Neplatná synchronní odpověď')
                return {'err': 'Chyba při volání API'}
            if 'data' in data:
                return data['data']
            return []
    except HTTPError as e:
        log_error('Chyba API ' + str(url), e.reason)
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        if e.code == 404:
            version_before = None
            if url.startswith(API_BASE):
                version_before = url[len(API_BASE):].split('/', 1)[0]
            if probe_version:
                get_api_version()
                version_after = load_api_version()
                if version_before and version_after != version_before:
                    old_prefix = API_BASE + version_before + '/'
                    new_url = API_BASE + version_after + '/' + url[len(old_prefix):]
                    return _call_api_unchecked(new_url, data, token, probe_version=False)
        retry_after = _retry_after_seconds(e.headers.get('Retry-After') if e.headers else None)
        return {'err': e.reason, 'http_status': e.code, 'retry_after': retry_after}
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass


def _api_cooldown_result(blocked_for):
    global _API_COOLDOWN_LAST_LOG
    now = int(time.time())
    with _API_BACKOFF_LOCK:
        state = _load_api_backoff_state()
        kind = state.get('kind', 'transient')
        should_log = now - _API_COOLDOWN_LAST_LOG >= _API_COOLDOWN_LOG_INTERVAL
        if should_log:
            _API_COOLDOWN_LAST_LOG = now
    if should_log:
        log_error('API cooldown aktivní', str(kind) + ', další pokus za ' + str(blocked_for) + ' s')
    return {
        'err': 'Oneplay API cooldown: Too Many Requests' if kind == 'rate_limit' else 'Oneplay API temporarily unavailable',
        'retry_after': blocked_for,
        'cooldown': True,
    }


def call_api(url, data, token=None):
    blocked_for = _api_request_backoff()
    if blocked_for:
        return _api_cooldown_result(blocked_for)

    version_before = load_api_version()
    version_after = check_api_version_if_due()
    blocked_for = get_api_backoff_seconds()
    if blocked_for:
        return _api_cooldown_result(blocked_for)
    if version_after != version_before:
        old_prefix = API_BASE + version_before + '/'
        if url.startswith(old_prefix):
            url = API_BASE + version_after + '/' + url[len(old_prefix):]

    try:
        result = _call_api_unchecked(url, data, token)
    except (HTTPError, URLError, OSError, socket.timeout, TimeoutError, ValueError, WebSocketException) as error:
        status_code = getattr(error, 'status_code', getattr(error, 'code', None))
        headers = getattr(error, 'headers', None)
        retry_after = _retry_after_seconds(headers.get('Retry-After') if headers else None)
        if status_code == 429 or _is_rate_limit_error(error):
            delay = _store_api_failure('rate_limit', retry_after)
        else:
            delay = _store_api_failure('transient', retry_after)
        log_error('Oneplay API nedostupné', str(error) + ' (další pokus za ' + str(delay) + ' s)')
        return {'err': str(error), 'retry_after': delay}
    except Exception:
        global _API_PROBE_IN_PROGRESS
        with _API_BACKOFF_LOCK:
            _API_PROBE_IN_PROGRESS = False
        raise

    api_error = None
    if isinstance(result, dict):
        result_data = result.get('result')
        api_error = result.get('err') or (result_data.get('message') if isinstance(result_data, dict) else None)
        http_status = result.get('http_status')
    else:
        http_status = None

    if isinstance(result, dict) and result.get('cooldown'):
        return result

    if http_status == 429 or _is_rate_limit_error(api_error):
        delay = _store_api_failure('rate_limit', result.get('retry_after'))
        if isinstance(result, dict):
            result['retry_after'] = delay
    elif http_status == 404:
        delay = get_api_backoff_seconds()
        if not delay:
            delay = _store_api_failure('not_found')
        if isinstance(result, dict):
            result['retry_after'] = delay
    elif (http_status is not None and (http_status == 408 or http_status >= 500)) or _is_transient_error(api_error):
        delay = _store_api_failure('transient', result.get('retry_after'))
        if isinstance(result, dict):
            result['retry_after'] = delay
    else:
        if get_api_backoff_seconds() <= 0:
            _clear_api_backoff()
    return result
