# -*- coding: utf-8 -*-
import os
import socket
import threading

import codecs
import json
from xml.dom import minidom
import ipaddress

_file_locks = {}
_file_locks_guard = threading.Lock()

class OneplayError(Exception):
    def __init__(self, message, detail=None):
        super().__init__(message)
        self.message = message
        self.detail = detail

appVersion = 'R11.33'

def is_docker():
    # Check for Docker-specific environment variables
    docker_env_vars = ['container', 'DOCKER']
    for var in docker_env_vars:
        if os.getenv(var):
            return True
    
    # Check for Docker-specific filesystem paths
    docker_paths = ['/proc/1/cgroup', '/.dockerenv']
    for path in docker_paths:
        if os.path.exists(path):
            return True
    return False

def is_kodi():
    try:
        import xbmc
        test = int(xbmc.getInfoLabel('System.BuildVersion').split('.')[0])
        return True
    except Exception:
        return False

def get_script_path():
    path = os.path.realpath(__file__)
    if path is not None:
        return path.replace('/resources/lib/utils.py', '').replace('\\resources\\lib\\utils.py', '')

def get_config_value(setting):
    if is_kodi() == True:
        import xbmcaddon
        addon = xbmcaddon.Addon()
        return addon.getSetting(setting)
    elif is_docker() == True and not os.path.exists(os.path.join(get_script_path(), 'config.txt')):
        defaults = {'WEBSERVER_IP' : '0.0.0.0', 'WEBSERVER_PORT' : 8082, 'EPG_DNU_ZPETNE' : 1, 'EPG_DNU_DOPREDU' : 1, 'INTERVAL_STAHOVANI_EPG' : 0, 'ODSTRANIT_HD' : 0, 'POUZIVAT_CISLA_KANALU' : 0, 'PORADI_SLUZBY' : -1, 'PIN' : '4321', 'PROFILE_PIN' : '4321', 'DEBUG' : 0, 'CESTA_FFMPEG' : '/usr/bin/ffmpeg', 'AUTH_USER' : '', 'AUTH_PASS' : ''} 
        value = os.getenv(setting.upper())
        if value is None and setting.upper() in defaults:
            value = defaults[setting.upper()]
        return value
    else:
        config_file = os.path.join(get_script_path(), 'config.txt')
        with codecs.open(config_file, 'r', 'utf-8') as f:
            config = json.load(f)
            f.close()
        if setting in config:
            return config[setting]

def is_debug():
    debug = get_config_value('debug')
    return debug == 1 or debug == '1' or debug == -1 or debug == '-1' or debug == 'true'

def _write_log(prefix, message):
    if is_kodi() == True:
        import xbmc
        xbmc.log('Oneplay Server > ' + prefix + message)
    else:
        print('Oneplay Server > ' + prefix + message, flush=True)

def log_message(message):
    _write_log('', message)

def log_error(message, detail=None):
    line = message
    if detail:
        line += ' | ' + str(detail)
    _write_log('CHYBA: ', line)

def raise_error(message, detail=None):
    log_error(message, detail)
    raise OneplayError(message, detail)

def display_message(message):
    if is_kodi() == True:
        import xbmcgui
        xbmcgui.Dialog().notification('Oneplay Server', message, xbmcgui.NOTIFICATION_ERROR, 4000)
    else:
        print('Oneplay Server > ' + message, flush=True)

def _get_data_dir():
    if is_kodi() == True:
        import xbmcaddon
        from xbmcvfs import translatePath
        addon = xbmcaddon.Addon()
        return translatePath(addon.getAddonInfo('profile'))
    return os.path.join(get_script_path(), 'data')


def _get_file_lock(filename):
    with _file_locks_guard:
        if filename not in _file_locks:
            _file_locks[filename] = threading.Lock()
        return _file_locks[filename]


def save_json_data(file, data):
    addon_userdata_dir = _get_data_dir()
    filename = os.path.join(addon_userdata_dir, file['filename'])
    lock = _get_file_lock(filename)
    with lock:
        try:
            os.makedirs(addon_userdata_dir, exist_ok=True)
            temp_name = filename + '.tmp'
            with open(temp_name, 'w', encoding='utf-8') as handle:
                handle.write('%s\n' % data)
            os.replace(temp_name, filename)
        except OSError:
            display_message('Chyba uložení ' + file['description'])


def load_json_data(file):
    addon_userdata_dir = _get_data_dir()
    filename = os.path.join(addon_userdata_dir, file['filename'])
    lock = _get_file_lock(filename)
    with lock:
        try:
            with open(filename, 'r', encoding='utf-8') as handle:
                for row in handle:
                    return row[:-1]
        except OSError as error:
            if error.errno != 2:
                display_message('Chyba při načtení ' + file['description'])
    return None

def replace_by_html_entity(string):
    return string.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace("'","&apos;").replace('"',"&quot;")

def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    return s.getsockname()[0]

def get_version():
    version = ''
    filename = os.path.join(get_script_path(), 'addon.xml')    
    try:
        xml = minidom.parse(filename)
        addon = xml.getElementsByTagName('addon')
        for element in addon:
            version = ' (v' + element.attributes['version'].value + ')'
    except IOError as error:
        return version
    return version

def check_client_network(ip):
    try:
        server_ip = get_ip_address()
        client_ip = ip
        server_parts = server_ip.split('.')
        client_parts = client_ip.split('.')
        return server_parts[:2] == client_parts[:2] or client_ip == '127.0.0.1' or ipaddress.ip_address(client_ip).is_private
    except Exception:
        return False

def check_ip_whitelist(ip):
    if ip == '127.0.0.1':
        return True
    ip_whitelist = get_config_value('ip_whitelist')
    if ip_whitelist is None or len(ip_whitelist.strip()) == 0:
        return False
    try:
        ip = ipaddress.ip_address(ip.strip())
    except ValueError:
        return False
    whitelist_items = ip_whitelist.strip().replace(' ', '').split(',')
    if not whitelist_items:
        return False
    for item in whitelist_items:
        try:
            network = ipaddress.ip_network(item, strict=True)
            if ip in network:
                return True
        except ValueError:
            continue
    return False
