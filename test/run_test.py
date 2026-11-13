"""Offline smoke test: mocked xbmc* modules + recorded (redacted) API responses."""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TMP = tempfile.mkdtemp(prefix='peckatv-test-')
os.environ['PECKATV_TEST_TMP'] = TMP
sys.path[:0] = [os.path.join(HERE, 'mock'), os.path.join(ROOT, 'plugin.video.peckatv')]

import xbmcaddon  # noqa: E402
xbmcaddon.SETTINGS['iptv_folder'] = os.path.join(TMP, 'out') + '/'
xbmcaddon.PROFILE = os.path.join(TMP, 'profile') + '/'

RESP = json.load(open(os.path.join(HERE, 'fixtures', 'responses.json'), encoding='utf-8'))

from resources.lib import api as A  # noqa: E402


PAIRED = []
DELETED = []
ADDED = []
SERIES = [{'id': 77, 'id_show': 999, 'id_channel': 643, 'id_epg': 1, 'name': 'Seriál'}]
_NOW = int(__import__('time').time())
# shape per web RecordMapper (api/device/getAllPvrs -> pvrs[])
PVRS = [
    {'id': 11, 'id_broadcast': 5001, 'id_channel': 643, 'id_epg': 1, 'name': 'Film',
     'start': _NOW - 7200, 'end': _NOW - 1800, 'playable': True, 'date_expired': _NOW + 86400 * 30,
     'poster': None, 'photo': None, 'poster_address': None},
    {'id': 12, 'id_broadcast': 5002, 'id_channel': 643, 'id_epg': 1, 'name': 'Budoucí pořad',
     'start': _NOW + 3600, 'end': _NOW + 7200, 'playable': False, 'date_expired': None,
     'poster': 'https://img.example/x{size}.jpg', 'photo': None, 'poster_address': None},
]
CALLS = []
DEVICE_INIT = {
    'api/device/getDeviceToken/': {'success': True, 'device_token': 'x'},
    'api/device/evaluateDeviceType/': {'success': True, 'device_type': 'web'},
    'api/device/logDeviceStart/': {'success': True},
    'api/device/getSettings/': {'success': True, 'settings': {}},
}


def fake_post(self, path, data=None):
    CALLS.append(path)
    if path in DEVICE_INIT:
        return DEVICE_INIT[path]
    if path == 'api/authenticate':
        return {'success': True, 'authorized_device': bool(PAIRED), 'session_token': 'NEWTOKEN'}
    if path == 'api/subscriber/pairBrowser':
        PAIRED.append(data['name'])
        return {'success': True, 'pairing_success': True}
    if path == 'api/epg/getEpgByDate':
        y, m, d = data['date'].split('-')
        assert not (m.startswith('0') or d.startswith('0')), data['date']
    if path == 'api/device/getAllPvrs':
        return {'success': True, 'pvrs': PVRS}
    if path == 'api/epg/getBroadcasts':
        return {'success': True, 'broadcasts': {'5001': {'id': 5001, 'name': 'Film', 'name_episode': None,
                                                         'description_broadcast': 'Popis filmu',
                                                         'poster': {'url': 'https://img.example/p{size}.jpg'}}}}
    if path == 'api/device/getAllPeriodicPvrs':
        return {'success': True, 'periodic_pvrs': SERIES}
    if path in ('api/device/addPvr', 'api/device/addPeriodicPvr', 'api/device/deletePeriodicPvr'):
        ADDED.append((path, data))
        return {'success': True}
    if path == 'api/device/deletePvr':
        DELETED.append(data['id'])
        return {'success': True}
    if path == 'api/contentdemon/getContent/':
        return {'stream_uri': 'https://streaming.example/arch.m3u8', 'start_from': 0, 'overlap_pre': 60}
    return json.loads(RESP[path])


A.PeckaApi._raw_post = fake_post

import xbmcplugin  # noqa: E402
import xbmcgui  # noqa: E402
from resources.lib import plugin  # noqa: E402


def go(q):
    xbmcplugin.ITEMS.clear()
    xbmcplugin.RESOLVED.clear()
    plugin.run(['plugin://plugin.video.peckatv/', '1', q])
    return list(xbmcplugin.ITEMS), list(xbmcplugin.RESOLVED)


try:
    assert len(go('?')[0]) == 5
    live = go('?action=live')[0]
    assert len(PAIRED) == 1 and PAIRED[0].startswith('Kodi'), PAIRED
    assert all(p in CALLS for p in DEVICE_INIT), CALLS
    assert CALLS.index('api/device/getSettings/') < CALLS.index('api/device/getSources'), CALLS
    assert len(live) > 100, len(live)
    assert len(go('?action=archive')[0]) > 0
    assert len(go('?action=archive_days&id=643')[0]) >= 7
    import time
    day = time.strftime('%Y-%m-%d', time.localtime(1793370300))
    _real_time = plugin.time.time
    plugin.time.time = lambda: 1793370300 + 6 * 3600  # fixture data is from this day, keep it in the catch-up window
    try:
        assert len(go('?action=archive_day&id=643&date=' + day)[0]) > 0
    finally:
        plugin.time.time = _real_time
    ok, li = go('?action=play_live&id=643')[1][0]
    assert ok and 'master.m3u8' in li.path
    ok, li = go('?action=play_archive&id=643&start=1793392800&end=1793405700')[1][0]
    assert ok and li.props.get('StartOffset') == '60'
    recs = [i for i in go('?action=recordings')[0] if not i[2]]  # without the series folder
    assert len(recs) == 2, recs
    fut, past = recs  # newest first
    assert 'naplánováno' in fut[0] and 'action=not_playable' in fut[1], fut
    assert 'action=play_archive' in past[1] and 'start=%d' % (_NOW - 7200) in past[1], past
    assert past[0].startswith('Film'), past
    ok, li = go('?action=play_archive&id=643&start=%d&end=%d' % (_NOW - 7200, _NOW - 1800))[1][0]
    assert ok and li.props.get('StartOffset') == '60'
    go('?action=delete_recording&pvr=11&name=Film')
    assert DELETED == [11], DELETED
    # recordings view lists the series folder first
    recs = go('?action=recordings')[0]
    assert 'Sériová nahrávání (1)' in recs[0][0] and 'action=series' in recs[0][1], recs[0]
    ser = go('?action=series')[0]
    assert len(ser) == 1 and 'Seriál' in ser[0][0], ser
    go('?action=delete_series&periodic=77&name=Seriál')
    assert ADDED[-1] == ('api/device/deletePeriodicPvr', {'id': 77, 'id_subscriber_profile': ADDED[-1][1]['id_subscriber_profile']})

    # programme + scheduling (fixture day, time frozen in the middle of it)
    assert len(go('?')[0]) == 5
    assert len(go('?action=program')[0]) > 100
    assert len(go('?action=program_days&id=643')[0]) == 8
    frozen = 1793450000  # mid-afternoon of the fixture day
    pday = time.strftime('%Y-%m-%d', time.localtime(frozen))
    plugin.time.time = lambda: frozen
    try:
        prog = go('?action=program_day&id=643&date=' + pday)[0]
        past = [i for i in prog if 'action=play_archive' in i[1]]
        fut = [i for i in prog if 'action=broadcast_menu' in i[1]]
        assert past and fut, prog
        url = fut[-1][1]  # last of the day = surely in the future
        ADDED.clear()
        go('?' + url.split('?', 1)[1])  # click -> select dialog -> first option "Nahrát"
        assert xbmcgui.SELECTS[-1][0] == 'Nahrát', xbmcgui.SELECTS[-1]
        path, body = ADDED[-1]
        assert path == 'api/device/addPvr', ADDED
        assert body['id_channel'] == 643 and body['start'] > frozen and body['name'], body
        go('?' + url.split('?', 1)[1].replace('action=broadcast_menu', 'action=record_series'))
        path, body = ADDED[-1]
        assert path == 'api/device/addPeriodicPvr' and body['id_show'] and body['id_channel'] == 643, ADDED[-1]
    finally:
        plugin.time.time = _real_time

    go('?action=iptv_generate')
    import xml.dom.minidom
    xml.dom.minidom.parse(os.path.join(TMP, 'out', 'peckatv.xml'))
    print('OK – live:%d, notes:%s' % (len(live), xbmcgui.NOTES))
finally:
    shutil.rmtree(TMP, ignore_errors=True)
