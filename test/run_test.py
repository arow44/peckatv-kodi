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


def fake_post(self, path, data=None):
    if path == 'api/authenticate':
        return {'success': True, 'authorized_device': bool(PAIRED), 'session_token': 'NEWTOKEN'}
    if path == 'api/subscriber/pairBrowser':
        PAIRED.append(data['name'])
        return {'success': True, 'pairing_success': True}
    if path == 'api/epg/getEpgByDate':
        y, m, d = data['date'].split('-')
        assert not (m.startswith('0') or d.startswith('0')), data['date']
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
    assert len(go('?')[0]) == 3
    live = go('?action=live')[0]
    assert len(PAIRED) == 1 and PAIRED[0].startswith('Kodi'), PAIRED
    assert len(live) > 100, len(live)
    assert len(go('?action=archive')[0]) > 0
    assert len(go('?action=archive_days&id=643')[0]) >= 7
    go('?action=archive_day&id=643&date=2026-11-01')
    ok, li = go('?action=play_live&id=643')[1][0]
    assert ok and 'master.m3u8' in li.path
    ok, li = go('?action=play_archive&id=643&start=1793392800&end=1793405700')[1][0]
    assert ok and li.props.get('StartOffset') == '60'
    go('?action=iptv_generate')
    import xml.dom.minidom
    xml.dom.minidom.parse(os.path.join(TMP, 'out', 'peckatv.xml'))
    print('OK – live:%d, notes:%s' % (len(live), xbmcgui.NOTES))
finally:
    shutil.rmtree(TMP, ignore_errors=True)
