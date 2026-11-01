"""M3U + XMLTV export for PVR IPTV Simple Client."""
import datetime
import os
import time
from xml.sax.saxutils import escape, quoteattr

import xbmcvfs

from resources.lib import kodiutils as ku
from resources.lib.api import logo_url, image_url

PLUGIN = 'plugin://plugin.video.peckatv/'
EPG_CHUNK = 40


def _fmt(ts):
    return time.strftime('%Y%m%d%H%M%S +0000', time.gmtime(ts))


def _write(folder, name, text):
    path = folder.rstrip('/\\') + '/' + name
    tmp = path + '.tmp'
    f = xbmcvfs.File(tmp, 'w')
    try:
        f.write(text)
    finally:
        f.close()
    if xbmcvfs.exists(path):
        xbmcvfs.delete(path)
    xbmcvfs.rename(tmp, path)
    return path


def build_m3u(channels):
    out = ['#EXTM3U']
    for c in channels:
        attrs = 'tvg-id="%s" tvg-name=%s tvg-logo="%s"' % (c['id'], quoteattr(c['name']), logo_url(c['id']))
        if c['catchup_hours']:
            attrs += (' catchup="default" catchup-days="%d" catchup-source="%s?action=play_archive&id=%s'
                      '&start={utc}&end={utcend}"' % (max(1, c['catchup_hours'] // 24), PLUGIN, c['id']))
        out.append('#EXTINF:-1 %s,%s' % (attrs, c['name']))
        out.append('%s?action=play_live&id=%s' % (PLUGIN, c['id']))
    return '\n'.join(out) + '\n'


def build_xmltv(api, channels, days_back, days_fwd):
    by_epg = {}
    for c in channels:
        if c.get('id_epg'):
            by_epg.setdefault(str(c['id_epg']), []).append(c)
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="plugin.video.peckatv">']
    for c in channels:
        out.append('<channel id="%s"><display-name>%s</display-name><icon src="%s"/></channel>'
                   % (c['id'], escape(c['name']), logo_url(c['id'])))
    epg_ids = list(by_epg)
    today = datetime.date.today()
    seen = set()
    for delta in range(-days_back, days_fwd + 1):
        day = (today + datetime.timedelta(days=delta)).isoformat()
        for i in range(0, len(epg_ids), EPG_CHUNK):
            try:
                data = api.epg_by_date(epg_ids[i:i + EPG_CHUNK], day)
            except Exception as e:
                ku.log('EPG %s failed: %s' % (day, e))
                continue
            for epg_id, bcs in data.items():
                for b in bcs:
                    if b['id'] in seen:
                        continue
                    seen.add(b['id'])
                    for c in by_epg.get(str(epg_id), []):
                        p = ['<programme start="%s" stop="%s" channel="%s">'
                             % (_fmt(b['timestamp_start']), _fmt(b['timestamp_end']), c['id']),
                             '<title lang="cs">%s</title>' % escape(b['name'])]
                        if b.get('name_episode'):
                            p.append('<sub-title lang="cs">%s</sub-title>' % escape(b['name_episode']))
                        if b.get('description_broadcast'):
                            p.append('<desc lang="cs">%s</desc>' % escape(b['description_broadcast']))
                        if b.get('year'):
                            p.append('<date>%s</date>' % b['year'])
                        img = image_url(b)
                        if img:
                            p.append('<icon src=%s/>' % quoteattr(img))
                        if b.get('number_series') or b.get('number_episode'):
                            s = (b.get('number_series') or 1) - 1
                            e = (b.get('number_episode') or 1) - 1
                            p.append('<episode-num system="xmltv_ns">%d.%d.</episode-num>' % (s, e))
                        p.append('</programme>')
                        out.append(''.join(p))
    out.append('</tv>')
    return '\n'.join(out) + '\n'


def generate(api):
    folder = ku.setting('iptv_folder') or ('special://profile/addon_data/%s/' % ku.ADDON_ID)
    if not xbmcvfs.exists(folder.rstrip('/\\') + '/'):
        xbmcvfs.mkdirs(folder)
    channels = [c for c in api.channels(force=True) if c['url']]
    m3u = _write(folder, 'peckatv.m3u', build_m3u(channels))
    xml = _write(folder, 'peckatv.xml', build_xmltv(
        api, channels, ku.setting_int('epg_days_back', 3), ku.setting_int('epg_days_forward', 2)))
    ku.log('IPTV export: %s, %s' % (m3u, xml))
    return len(channels)
