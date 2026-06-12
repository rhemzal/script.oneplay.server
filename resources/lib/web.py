# -*- coding: utf-8 -*-
import os

from urllib.parse import quote, unquote
from bottle import run, route, post, response, request, redirect, template, static_file, hook, HTTPResponse, HTTPError, TEMPLATE_PATH, install, abort, default_app
import traceback
import json
import base64
import hmac


from resources.lib.session import load_session
from resources.lib.channels import load_channels, load_diasbled_channels, save_disabled_channels
from resources.lib.epg import get_epg, load_epg, get_live_epg, get_channel_epg
from resources.lib.stream import get_live, get_archive
from resources.lib.helpers import is_truthy, resolve_channel_name_by_number
from resources.lib.utils import get_config_value, get_script_path, get_version, check_client_network, check_ip_whitelist, OneplayError, log_error, is_debug


class OneplayErrorPlugin:
    name = 'oneplay_errors'
    api = 2

    def apply(self, callback, route):
        def wrapper(*args, **kwargs):
            try:
                return callback(*args, **kwargs)
            except HTTPResponse:
                raise
            except HTTPError:
                raise
            except OneplayError as e:
                response.status = 500
                response.content_type = 'text/plain; charset=UTF-8'
                return e.message
            except Exception as e:
                log_error('Neočekávaná chyba', str(e))
                if is_debug():
                    log_error('Traceback', traceback.format_exc())
                response.status = 500
                response.content_type = 'text/plain; charset=UTF-8'
                return 'Interní chyba serveru'
        return wrapper


def get_base_url(include_auth = False):
    base_url = request.urlparts.scheme + '://' + request.urlparts.netloc
    if not include_auth:
        return base_url
    auth_user = get_config_value('auth_user')
    auth_pass = get_config_value('auth_pass')
    if not auth_user or not auth_pass:
        return base_url

    auth_prefix = quote(auth_user, safe = '') + ':' + quote(auth_pass, safe = '') + '@'
    return request.urlparts.scheme + '://' + auth_prefix + request.urlparts.netloc

@hook('before_request')
def check_basic_auth():
    auth_user = get_config_value('auth_user')
    auth_pass = get_config_value('auth_pass')
    if not auth_user or not auth_pass:
        return
    if check_ip_whitelist(request.environ.get('REMOTE_ADDR', '')):
        return
    auth = request.headers.get('Authorization')
    if auth and auth.startswith('Basic '):
        try:
            decoded = base64.b64decode(auth[6:]).decode('utf-8')
            username, password = decoded.split(':', 1)
            if hmac.compare_digest(username, auth_user) and hmac.compare_digest(password, auth_pass):
                return
        except Exception:
            pass
    err = HTTPResponse('Přístup odepřen', 401)
    err.set_header('WWW-Authenticate', 'Basic realm="Oneplay Server"')
    raise err

@route('/epg')
def epg():
    if  int(get_config_value('interval_stahovani_epg')) > 0:
        output = load_epg()
    else:
        output = get_epg()
    response.content_type = 'xml/application; charset=UTF-8'
    return output

@route('/epg_live')
def epg_now():
    epg_by_channel = get_live_epg()
    result = {}
    for channel_id, epg_data in epg_by_channel.items():
        if epg_data['now'] is not None:
            result[channel_id] = epg_data['now']
    response.content_type = 'application/json'
    response.set_header('Access-Control-Allow-Origin', '*')
    return json.dumps(result)

@route('/epg_channel/<channel_id>/<day_offset:int>')
def epg_channel(channel_id, day_offset):
    from datetime import datetime as dt
    import time as t
    today = dt.today()
    day_start = int(t.mktime(dt(today.year, today.month, today.day).timetuple())) + day_offset * 86400
    day_end = day_start + 86400 - 1
    epg = get_channel_epg(channel_id, day_start, day_end)
    result = []
    for ts in sorted(epg.keys()):
        item = epg[ts]
        result.append({
            'title': item['title'],
            'description': item.get('description', ''),
            'startts': item['startts'],
            'endts': item['endts'],
            'cover': item.get('cover', '')
        })
    response.content_type = 'application/json'
    response.set_header('Access-Control-Allow-Origin', '*')
    return json.dumps(result)

@route('/playlist')
def playlist():
    from urllib.parse import urlencode
    headers = {'User-Agent' : 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:142.0) Gecko/20100101 Firefox/142.0', 'Accept-Encoding' : 'gzip, deflate, br, zstd', 'Accept' : '*/*'}
    channels = load_channels()
    base_url = get_base_url()
    strip_hd = is_truthy(get_config_value('odstranit_hd'))
    use_numbers = is_truthy(get_config_value('pouzivat_cisla_kanalu'))
    output = '#EXTM3U x-tvg-url="' + base_url + '/epg"\n'
    for channel in channels:
        if channels[channel]['visible'] == True:
            logo = channels[channel]['logo'] or ''
            channel_name = resolve_channel_name_by_number(channels, channels[channel]['channel_number'], strip_hd=strip_hd)
            if channel_name is None:
                channel_name = channels[channel]['name']
            output += '#EXTINF:-1 provider="Oneplay" tvg-chno="' + str(channels[channel]['channel_number']) + '" tvg-name="' + channel_name + '" tvg-logo="' + logo + '" catchup-days="7" catchup="shift", ' + channel_name + '\n'
            output += '#KODIPROP:inputstream.adaptive.stream_headers=' + urlencode(headers) + '\n'
            output += '#KODIPROP:inputstream.adaptive.manifest_headers=' + urlencode(headers) + '\n'
            if not use_numbers:
                output += base_url + '/play/' + quote(channel_name.replace('/', 'sleš')) + '.m3u8\n'
            else:
                output += base_url + '/play_num/' + str(channels[channel]['channel_number']) + '.m3u8\n'
    response.content_type = 'text/plain; charset=UTF-8'
    return output

@route('/playlist/tvheadend')
def playlist_tvheadend():
    channels = load_channels()
    base_url = get_base_url()
    strip_hd = is_truthy(get_config_value('odstranit_hd'))
    use_numbers = is_truthy(get_config_value('pouzivat_cisla_kanalu'))
    output = '#EXTM3U x-tvg-url="' + base_url + '/epg"\n'
    ffmpeg = get_config_value('cesta_ffmpeg')
    if ffmpeg == None or len(ffmpeg) == 0:
        ffmpeg = '/usr/bin/ffmpeg'
    for channel in channels:
        if channels[channel]['visible'] == True:
            logo = channels[channel]['logo'] or ''
            channel_name = resolve_channel_name_by_number(channels, channels[channel]['channel_number'], strip_hd=strip_hd)
            if channel_name is None:
                channel_name = channels[channel]['name']
            output += '#EXTINF:-1 provider="Oneplay" tvg-chno="' + str(channels[channel]['channel_number']) + '" tvg-name="' + channel_name + '" tvg-logo="' + logo + '", ' + channel_name + '\n'
            if not use_numbers:
                output += 'pipe://' + ffmpeg + ' -loglevel error -fflags +genpts -i "' + base_url + '/play/' + quote(channel_name.replace('/', 'sleš')) + '.m3u8" -f mpegts -c copy -vcodec copy -acodec copy -metadata service_provider=Oneplay -metadata service_name="' + channel_name + '" pipe:1\n'
            else:
                output += 'pipe://' + ffmpeg + ' -loglevel error -fflags +genpts -i "' + base_url + '/play_num/' + str(channels[channel]['channel_number']) + '.m3u8" -f mpegts -c copy -vcodec copy -acodec copy -metadata service_provider=Oneplay -metadata service_name="' + channel_name + '" pipe:1\n'
    response.content_type = 'text/plain; charset=UTF-8'
    return output

@route('/stream_url/<channel>')
def stream_url(channel):
    try:
        channel = unquote(channel.replace('.m3u8', '')).replace('sleš', '/')
        if 'start_ts' in request.query and 'end_ts' in request.query:
            url = get_archive(channel, request.query['start_ts'], request.query['end_ts'])
        else:
            url = get_live(channel)
        if url is None or url == '':
            response.content_type = 'application/json'
            response.set_header('Access-Control-Allow-Origin', '*')
            return json.dumps({'url': None, 'error': 'Nepodařilo se získat stream'})
        response.content_type = 'application/json'
        response.set_header('Access-Control-Allow-Origin', '*')
        return json.dumps({'url': url})
    except Exception as e:
        response.content_type = 'application/json'
        response.set_header('Access-Control-Allow-Origin', '*')
        response.status = 200
        return json.dumps({'url': None, 'error': str(e)})

@route('/play/<channel>')
def play(channel):
    channel = unquote(channel.replace('.m3u8', '')).replace('sleš', '/')
    if 'start_ts' in request.query:
        stream = get_archive(channel, request.query['start_ts'], request.query['end_ts'])
    elif 'utc' in request.query:
        stream = get_archive(channel, request.query['utc'], request.query['lutc'])
    else:
        stream = get_live(channel)
    response.content_type = 'application/x-mpegURL'
    return redirect(stream)

@route('/play_num/<channel>')
def play_num(channel):
    channel_number = int(channel.replace('.m3u8', ''))
    channel_name = resolve_channel_name_by_number(
        load_channels(),
        channel_number,
        strip_hd=is_truthy(get_config_value('odstranit_hd')),
    )
    if channel_name is None:
        abort(404, 'Kanál nenalezen')
    if 'start_ts' in request.query:
        stream = get_archive(channel_name, request.query['start_ts'], request.query['end_ts'])
    elif 'utc' in request.query:
        stream = get_archive(channel_name, request.query['utc'], request.query['lutc'])
    else:
        stream = get_live(channel_name)
    response.content_type = 'application/x-mpegURL'
    return redirect(stream)

@route('/img/<image>')
def add_image(image):
    return static_file(image, root = os.path.join(get_script_path(), 'resources', 'templates'))

@route('/config')
def config():
    ip = request.environ.get('REMOTE_ADDR', '')
    if not check_client_network(ip) and not check_ip_whitelist(ip):
        abort(403, 'Přístup odepřen')
    config_data = {}
    params = ['username', 'password', 'profile', 'deviceid', 'webserver_ip', 'webserver_port', 'epg_dnu_zpetne', 'epg_dnu_dopredu', 'interval_stahovani_epg', 'odstranit_hd', 'pouzivat_cisla_kanalu', 'poradi_sluzby', 'pin', 'debug', 'cesta_ffmpeg', 'auth_user', 'auth_pass']
    for param in params:
        if get_config_value(param) is None:
            value = 'není'
        else:
            value = get_config_value(param)
        if param in ['password', 'auth_pass'] and value != 'není':
            config_data.update({param : '*' * len(value)})
        else:
            config_data.update({param : value})
    response.content_type = 'application/json'
    return json.dumps(config_data)

@route('/channel/<channel>/<status>')
def channel(channel, status):
    disabled_channels = load_diasbled_channels()
    if status == 'disable' and channel not in disabled_channels:
        disabled_channels.append(channel)
        save_disabled_channels(disabled_channels)
    elif status == 'enable' and channel in disabled_channels:
        disabled_channels.remove(channel)
        save_disabled_channels(disabled_channels)

@route('/')
@post('/')
def page():
    message = ''
    ip = request.environ.get('REMOTE_ADDR', '')
    warning = not check_client_network(ip) and not check_ip_whitelist(ip)
    if request.params.get('action') is not None:
        action = request.params.get('action')
        if action == 'reset_channels':
            load_channels(reset = True)
            message = 'Kanály resetovány!'
        elif action == 'reset_session':
            load_session(reset = True)
            message = 'Sessiona resetována!'
    auth_enabled = bool(get_config_value('auth_user') and get_config_value('auth_pass'))
    player_enabled = auth_enabled or not warning
    base_url_with_auth = get_base_url(include_auth = True)
    playlist_url = base_url_with_auth + '/playlist'
    playlist_tvheadend_url = base_url_with_auth + '/playlist/tvheadend'
    epg_url = base_url_with_auth + '/epg'
    playlist = []
    channels = load_channels()
    strip_hd = is_truthy(get_config_value('odstranit_hd'))
    use_numbers = is_truthy(get_config_value('pouzivat_cisla_kanalu'))
    for channel in channels:
        channel_name = resolve_channel_name_by_number(channels, channels[channel]['channel_number'], strip_hd=strip_hd)
        if channel_name is None:
            channel_name = channels[channel]['name']
        entry = {
            'name' : channel_name,
            'slug' : quote(channel_name.replace('/', 'sleš')) + '.m3u8',
            'logo' : channels[channel]['logo'],
            'channel_id' : channel,
            'liveOnly' : channels[channel].get('liveOnly', False),
            'visible' : channels[channel]['visible'],
        }
        if not use_numbers:
            entry['url'] = base_url_with_auth + '/play/' + quote(channel_name.replace('/', 'sleš')) + '.m3u8'
        else:
            entry['url'] = base_url_with_auth + '/play_num/' + str(channels[channel]['channel_number']) + '.m3u8'
        playlist.append(entry)
    TEMPLATE_PATH.append(os.path.join(get_script_path(), 'resources', 'templates'))
    return template('form.tpl', version = get_version(), message = message, warning = warning, playlist_url = playlist_url, playlist_tvheadend_url = playlist_tvheadend_url, epg_url = epg_url, playlist = playlist, auth_enabled = auth_enabled, player_enabled = player_enabled)

def _ensure_error_plugin():
    for plugin in default_app().plugins:
        if getattr(plugin, 'name', None) == OneplayErrorPlugin.name:
            return
    install(OneplayErrorPlugin())


def start_server():
    _ensure_error_plugin()
    port = int(get_config_value('webserver_port'))
    run(host = '0.0.0.0', port = port, debug = False)
