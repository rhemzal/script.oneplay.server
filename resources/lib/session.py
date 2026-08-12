# -*- coding: utf-8 -*-
import json
import threading
import time

from resources.lib.api import call_api, api_url
from resources.lib.helpers import collect_account_ids, get_api_error, select_account_id
from resources.lib.utils import (
    display_message,
    get_config_value,
    is_debug,
    load_json_data,
    log_error,
    log_message,
    OneplayError,
    raise_error,
    save_json_data,
)

_login_failure_until = 0
_login_failure_message = ''
_session_lock = threading.RLock()


def _fail_login(message, data=None):
    global _login_failure_until, _login_failure_message
    with _session_lock:
        if 'Too Many Requests' in message or '429' in message:
            _login_failure_until = int(time.time()) + 900
        else:
            _login_failure_until = int(time.time()) + 300
        _login_failure_message = message
    detail = str(data) if data is not None and is_debug() else None
    raise_error(message, detail)


def _perform_login():
    global _login_failure_until, _login_failure_message

    post = {"payload":{"command":{"schema":"LoginWithCredentialsCommand","email":get_config_value('username'),"password":get_config_value('password')}}}
    data = call_api(url = api_url('user.login.step'), data = post)
    api_error = get_api_error(data)
    if api_error or 'step' not in data or ('bearerToken' not in data['step'] and data['step']['schema'] != 'ShowAccountChooserStep'):
        message = 'Problém při přihlášení'
        if api_error:
            message = message + ': ' + api_error
        _fail_login(message, data)

    if data['step']['schema'] == 'ShowAccountChooserStep':
        authToken = data['step']['authToken']
        accounts = collect_account_ids(data['step'])
        if not accounts:
            if is_debug():
                log_message('ShowAccountChooserStep keys: ' + str(list(data['step'].keys())))
                log_message('ShowAccountChooserStep: ' + str(data['step']))
            _fail_login('Problém při přihlášení - žádné dostupné účty', data)
        accountId = select_account_id(accounts, get_config_value('poradi_sluzby'))
        if is_debug():
            log_message('Dostupné účty: ' + str(len(accounts)) + ', vybraný (poradi_sluzby=' + str(get_config_value('poradi_sluzby')) + '): ' + str(accountId))
        post = {"payload":{"command":{"schema":"LoginWithAccountCommand","accountId":accountId,"authCode":authToken}}}
        data = call_api(url = api_url('user.login.step'), data = post)
        api_error = get_api_error(data)
        if api_error or 'step' not in data or 'bearerToken' not in data['step']:
            message = 'Problém při přihlášení'
            if api_error:
                message = message + ': ' + api_error
            _fail_login(message, data)

    with _session_lock:
        _login_failure_until = 0
        _login_failure_message = ''
    token = data['step']['bearerToken']
    deviceId = data['step']['currentUser']['currentDevice']['id']
    post = {"payload":{"id":deviceId,"name": get_config_value('deviceid')}}
    data = call_api(url = api_url('user.device.change'), data = post, token = token)
    post = {"payload":{"screen":"devices"}}
    data = call_api(url = api_url('setting.display'), data = post, token = token)
    devices = []
    for block in data.get('screen', {}).get('blocks', []):
        if block.get('schema') == 'SettingUserDevicesBlock':
            devices = block.get('devices', {}).get('devices') or []
    if 'err' in data:
        _fail_login('Problém při přihlášení', data)
    for device in devices:
        if device['id'] != deviceId and device['name'] == get_config_value('deviceid'):
            post = {"payload":{"criteria":{"schema":"UserDeviceIdCriteria","id":device['id']}}}
            call_api(url = api_url('user.device.remove'), data = post, token = token)

    data = call_api(url = api_url('user.profiles.display'), data = {"payload": {"mode": "change"}}, token = token)
    if 'err' in data or 'availableProfiles' not in data or 'profiles' not in data['availableProfiles']:
        _fail_login('Problém při přihlášení', data)
    for profile in data['availableProfiles']['profiles']:
        if profile['profile']['name'] == get_config_value('profile') or get_config_value('profile') is None or len(get_config_value('profile')) == 0:
            if get_config_value('profile_pin') is not None and len(get_config_value('profile_pin')) > 0 and get_config_value('profile_pin') != '4321':
                post = {"payload":{"profileId":profile['profile']['id']},"authorization":[{"schema":"PinRequestAuthorization","pin":get_config_value('profile_pin'),"type":"profile"}]}
            else:
                post = {"payload":{"profileId":profile['profile']['id']}}
            data = call_api(url = api_url('user.profile.select'), data = post, token = token)
            if 'err' in data or 'bearerToken' not in data:
                _fail_login('Problém při přihlášení', data)
            display_message('Profil: ' + profile['profile']['name'])
            return data['bearerToken']
    return token


def get_token():
    with _session_lock:
        if _login_failure_until > int(time.time()):
            msg = _login_failure_message + ' (další pokus za ' + str(_login_failure_until - int(time.time())) + ' s)'
            log_error(msg)
            raise OneplayError(msg)
        return _perform_login()


def _read_cached_token():
    data = load_json_data({'filename' : 'session.txt', 'description' : 'session'})
    if data is None:
        return None
    try:
        parsed = json.loads(data)
    except (TypeError, ValueError):
        return None
    if 'valid_to' not in parsed or 'token' not in parsed:
        return None
    if int(parsed['valid_to']) < int(time.time()):
        return None
    return parsed['token']


def load_session(reset = False):
    global _login_failure_until, _login_failure_message
    if reset:
        with _session_lock:
            _login_failure_until = 0
            _login_failure_message = ''
            token = _perform_login()
            save_session(token)
            return token

    token = _read_cached_token()
    if token:
        return token

    with _session_lock:
        token = _read_cached_token()
        if token:
            return token
        token = _perform_login()
        save_session(token)
        return token


def save_session(token):
    data = json.dumps({'token' : token, 'valid_to' : int(time.time() + 60*60*4)})
    save_json_data({'filename' : 'session.txt', 'description' : 'session'}, data)


def is_session_cached():
    return _read_cached_token() is not None


def get_login_backoff_seconds():
    with _session_lock:
        remaining = _login_failure_until - int(time.time())
        if remaining > 0:
            return remaining
    return 0
