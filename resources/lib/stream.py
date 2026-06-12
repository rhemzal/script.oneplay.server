# -*- coding: utf-8 -*-
import time
from datetime import datetime

from resources.lib.channels import load_channels
from resources.lib.session import load_session
from resources.lib.epg import get_channel_epg
from resources.lib.api import call_api
from resources.lib.helpers import (
    NO_ACCESS_URL,
    extract_hls_url,
    get_api_error,
    is_truthy,
    resolve_channel_internal_id,
)
from resources.lib.utils import get_config_value, api_version, is_debug, log_error

PLAYBACK_CAPS = {
    "protocols": ["dash", "hls"],
    "drm": ["widevine", "fairplay"],
    "altTransfer": "Unicast",
    "subtitle": {"formats": ["vtt"], "locations": ["InstreamTrackLocation", "ExternalTrackLocation"]},
    "liveSpecificCapabilities": {
        "protocols": ["dash", "hls"],
        "drm": ["widevine", "fairplay"],
        "altTransfer": "Unicast",
        "multipleAudio": False,
    },
}


def _parental_pin():
    pin = get_config_value('pin')
    if pin is not None and len(pin) > 0:
        return pin
    return '1234'


def get_channel_id(channel_name):
    return resolve_channel_internal_id(
        load_channels(),
        channel_name,
        strip_hd=is_truthy(get_config_value('odstranit_hd')),
    )


def get_live(channel_ref):
    token = load_session()
    channels = load_channels()
    channel_id = resolve_channel_internal_id(
        channels,
        channel_ref,
        strip_hd=is_truthy(get_config_value('odstranit_hd')),
    )
    if channel_id is None:
        if '~' in str(channel_ref):
            channel_id = str(channel_ref)
        else:
            channel_id = channel_ref
    else:
        channel_ref = channel_id

    md = False
    md_stream = 0
    if '~' in str(channel_id):
        md = True
        base_id, md_stream = str(channel_id).split('~', 1)
        channel_id = base_id
        md_stream = int(md_stream)

    if channel_id not in channels:
        log_error('Neznámý kanál', channel_ref)
        return NO_ACCESS_URL

    if channels[channel_id]['adult']:
        post = {
            "authorization": [{"schema": "PinRequestAuthorization", "pin": _parental_pin(), "type": "parental"}],
            "payload": {"criteria": {"schema": "ContentCriteria", "contentId": "channel." + channel_id}, "startMode": "start"},
            "playbackCapabilities": PLAYBACK_CAPS,
        }
    else:
        post = {
            "payload": {"criteria": {"schema": "ContentCriteria", "contentId": "channel." + channel_id}, "startMode": "start"},
            "playbackCapabilities": PLAYBACK_CAPS,
        }

    data = call_api(url='https://http.cms.jyxo.cz/api/' + api_version + '/content.play', data=post, token=token)
    if get_api_error(data):
        post['payload']['startMode'] = 'live'
        data = call_api(url='https://http.cms.jyxo.cz/api/' + api_version + '/content.play', data=post, token=token)

    live_control = data.get('playerControl', {}).get('liveControl', {})
    if md and 'mosaic' in live_control:
        stream_number = 1
        for md_item in live_control.get('mosaic', {}).get('items', []):
            if md_stream == stream_number:
                payload = md_item.get('play', {}).get('params', {}).get('payload', {})
                criteria = payload.get('criteria', {})
                md_id = criteria.get('contentId') or payload.get('contentId')
                if md_id is not None:
                    md_post = {
                        "payload": {"criteria": {"schema": "MDPlaybackCriteria", "contentId": md_id, "position": 0}, "startMode": "start"},
                        "playbackCapabilities": PLAYBACK_CAPS,
                    }
                    data = call_api(url='https://http.cms.jyxo.cz/api/' + api_version + '/content.play', data=md_post, token=token)
                    if get_api_error(data) or 'media' not in data:
                        return NO_ACCESS_URL
            stream_number += 1

    timeline = live_control.get('timeline', {})
    time_shift = timeline.get('timeShift', {})
    if time_shift.get('available') is False:
        post.update({'payload': {'criteria': post['payload']['criteria'], 'startMode': 'live'}})
        data = call_api(url='https://http.cms.jyxo.cz/api/' + api_version + '/content.play', data=post, token=token)

    url = extract_hls_url(data)
    if url == NO_ACCESS_URL:
        detail = str(data) if is_debug() else None
        log_error('Nepodařilo se získat stream pro kanál ' + str(channel_ref), detail)
    return url


def get_archive(channel_name, start_ts, end_ts):
    start_ts = int(start_ts)
    end_ts = int(end_ts)
    token = load_session()
    channel_id = get_channel_id(channel_name)
    if channel_id in (-1, None, ''):
        log_error('Neznámý kanál pro archiv', channel_name)
        return get_live(channel_name)

    md = '~' in str(channel_id)
    channels = load_channels()
    if channel_id not in channels:
        return get_live(channel_name)

    epg = get_channel_epg(channel_id=channel_id, from_ts=start_ts, to_ts=end_ts + 60 * 60 * 12)
    if start_ts not in epg:
        return get_live(channel_name)

    if epg[start_ts]['endts'] > int(time.mktime(datetime.now().timetuple())) - 10:
        return get_live(channel_name)

    if channels[channel_id]['adult']:
        deeplink = (epg[start_ts].get('payload') or {}).get('deeplink') or {}
        post = {
            "authorization": [{"schema": "PinRequestAuthorization", "pin": _parental_pin(), "type": "parental"}],
            "payload": {
                "criteria": {
                    'schema': 'ChannelPlaybackCriteria',
                    'channel': deeplink.get('channel'),
                    'time': deeplink.get('time'),
                }
            },
            "playbackCapabilities": PLAYBACK_CAPS,
        }
    elif md:
        post = {
            "payload": {"criteria": {"schema": "MDPlaybackCriteria", "contentId": epg[start_ts]['id'], "position": 0}},
            "playbackCapabilities": PLAYBACK_CAPS,
        }
    else:
        payload = None
        page_data = call_api(
            url='https://http.cms.jyxo.cz/api/' + api_version + '/page.content.display',
            data={'payload': epg[start_ts].get('payload')},
            token=token,
        )
        for block in page_data.get('layout', {}).get('blocks', []):
            if block.get('schema') == 'ContentHeaderBlock':
                action = block.get('mainAction', {}).get('action', {})
                if action.get('call') == 'content.play':
                    payload = action.get('params', {}).get('payload')
                    break
        if payload is None:
            log_error('Nepodařilo se získat payload archivu', channel_name)
            return NO_ACCESS_URL
        post = {"payload": payload, "playbackCapabilities": PLAYBACK_CAPS}

    data = call_api(url='https://http.cms.jyxo.cz/api/' + api_version + '/content.play', data=post, token=token)
    return extract_hls_url(data)
