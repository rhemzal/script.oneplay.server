# -*- coding: utf-8 -*-
import json
import gzip
import uuid
from websocket import create_connection
from urllib.request import urlopen, Request
from urllib.error import HTTPError

from resources.lib.utils import appVersion, get_config_value, log_message, log_error, load_json_data, save_json_data

BASE_API_VERSION = 'v1.11'
API_BASE = 'https://http.cms.jyxo.cz/api/'


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


def get_api_version():
    api_version = load_api_version()
    try:
        start_version = int(api_version.split('.')[1])
    except (IndexError, ValueError):
        return api_version
    consecutive_404 = 0
    for minor in range(start_version + 1, start_version + 6):
        version = 'v1.' + str(minor).zfill(2)
        url = API_BASE + version + '/user.login.step'
        post = json.dumps({}).encode('utf-8')
        request = Request(url=url, data=post, headers={'Content-Type': 'application/json;charset=UTF-8'}, method='POST')
        try:
            urlopen(request, timeout=10)
            return api_version
        except HTTPError as e:
            if e.code == 404:
                consecutive_404 += 1
                if consecutive_404 >= 3:
                    return api_version
                continue
            if e.code == 400:
                save_api_version(version)
                return version
            if e.code == 429:
                log_error('Detekce verze API', 'Too Many Requests – přeskakuji probe')
                return api_version
    return api_version


def api_url(endpoint):
    endpoint = endpoint.lstrip('/')
    return API_BASE + load_api_version() + '/' + endpoint


def call_api(url, data, token=None):
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
            get_api_version()
        return {'err': e.reason}
