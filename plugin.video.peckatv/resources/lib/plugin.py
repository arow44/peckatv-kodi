import datetime
import json
import os
import time
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcgui
import xbmcplugin

from resources.lib import kodiutils as ku
from resources.lib.api import ApiError, AuthError, image_url, logo_url

DAYS_CZ = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']
NOW_CACHE_TTL = 300


class Router(object):
    def __init__(self, argv):
        self.base = argv[0]
        self.handle = int(argv[1])
        self.params = dict(parse_qsl(argv[2][1:])) if len(argv) > 2 else {}
        self._api = None

    @property
    def api(self):
        if self._api is None:
            self._api = ku.get_api()
        return self._api

    def url(self, **kw):
        return self.base + '?' + urlencode(kw)

    # ---------- helpers ----------
    def add_dir(self, label, art=None, info=None, folder=True, playable=False, **kw):
        li = xbmcgui.ListItem(label=label, offscreen=True)
        if art:
            li.setArt(art)
        if info:
            tag = li.getVideoInfoTag()
            if info.get('plot'):
                tag.setPlot(info['plot'])
            if info.get('title'):
                tag.setTitle(info['title'])
            if info.get('duration'):
                tag.setDuration(int(info['duration']))
            if info.get('year'):
                tag.setYear(int(info['year']))
            tag.setMediaType('video')
        if playable:
            li.setProperty('IsPlayable', 'true')
        xbmcplugin.addDirectoryItem(self.handle, self.url(**kw), li, isFolder=folder)

    def end(self, content='videos', cache=False):
        xbmcplugin.setContent(self.handle, content)
        xbmcplugin.endOfDirectory(self.handle, cacheToDisc=cache)

    def now_playing(self, channels):
        """Map id_epg -> current broadcast, cached 5 min."""
        cache_file = os.path.join(ku.PROFILE, 'now.json')
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                c = json.load(f)
            if time.time() - c['ts'] < NOW_CACHE_TTL:
                return c['data']
        except Exception:
            pass
        now = time.time()
        ids = [c['id_epg'] for c in channels if c.get('id_epg')]
        data = {}
        try:
            for day in (datetime.date.today() - datetime.timedelta(days=1), datetime.date.today()):
                for epg_id, bcs in self.api.epg_by_date(ids, day.isoformat()).items():
                    for b in bcs:
                        if b['timestamp_start'] <= now < b['timestamp_end']:
                            data[str(epg_id)] = b
        except ApiError as e:
            ku.log('EPG now failed: %s' % e)
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump({'ts': now, 'data': data}, f)
        except Exception:
            pass
        return data

    # ---------- views ----------
    def root(self):
        self.add_dir('Živé vysílání', action='live')
        self.add_dir('Archiv', action='archive')
        self.add_dir('Vygenerovat M3U + EPG pro IPTV Simple', folder=False, action='iptv_generate')
        self.end('files')

    def live(self):
        chans = [c for c in self.api.channels() if c['url']]
        now = self.now_playing(chans)
        for c in chans:
            b = now.get(str(c['id_epg']))
            label = c['name']
            info = {'title': c['name']}
            art = {'icon': logo_url(c['id']), 'thumb': logo_url(c['id'])}
            if b:
                start = time.strftime('%H:%M', time.localtime(b['timestamp_start']))
                end = time.strftime('%H:%M', time.localtime(b['timestamp_end']))
                label = '%s  [COLOR gray]%s (%s–%s)[/COLOR]' % (c['name'], b['name'], start, end)
                info['plot'] = '[B]%s[/B]\n%s' % (b['name'], b.get('description_broadcast') or '')
                img = image_url(b)
                if img:
                    art['fanart'] = img
            self.add_dir(label, art=art, info=info, folder=False, playable=True,
                         action='play_live', id=c['id'])
        self.end('videos')

    def archive(self):
        for c in self.api.channels():
            if c['catchup_hours'] and c['url']:
                self.add_dir(c['name'], art={'icon': logo_url(c['id']), 'thumb': logo_url(c['id'])},
                             action='archive_days', id=c['id'])
        self.end('files')

    def archive_days(self):
        c = self.api.channel(self.params['id'])
        days = max(1, int(c['catchup_hours'] // 24) + 1)
        today = datetime.date.today()
        for i in range(days):
            d = today - datetime.timedelta(days=i)
            if i == 0:
                label = 'Dnes'
            elif i == 1:
                label = 'Včera'
            else:
                label = '%s %s' % (DAYS_CZ[d.weekday()], d.strftime('%d.%m.'))
            self.add_dir(label, action='archive_day', id=c['id'], date=d.isoformat())
        self.end('files')

    def archive_day(self):
        c = self.api.channel(self.params['id'])
        now = time.time()
        limit = now - c['catchup_hours'] * 3600
        # web app uses getCatchupBroadcasts for a single channel; getEpgByDate fails there
        day_start = time.mktime(time.strptime(self.params['date'], '%Y-%m-%d'))
        bcs = self.api.catchup(c['id_epg'], day_start, day_start + 86400)
        for b in sorted(bcs, key=lambda x: x['timestamp_start']):
            if b['timestamp_start'] > now or b['timestamp_start'] < limit:
                continue
            if time.strftime('%Y-%m-%d', time.localtime(b['timestamp_start'])) != self.params['date']:
                continue  # API returns previous evening too
            running = b['timestamp_end'] > now
            t = time.strftime('%H:%M', time.localtime(b['timestamp_start']))
            label = '%s  %s' % (t, b['name'])
            if b.get('name_episode') and b['name_episode'] not in b['name']:
                label += ' – ' + b['name_episode']
            if running:
                label += '  [COLOR red](běží)[/COLOR]'
            img = image_url(b)
            art = {'thumb': img, 'fanart': img, 'icon': logo_url(c['id'])} if img else {'icon': logo_url(c['id'])}
            self.add_dir(label, art=art, folder=False, playable=True,
                         info={'title': b['name'], 'plot': b.get('description_broadcast') or '',
                               'duration': b['timestamp_end'] - b['timestamp_start'], 'year': b.get('year')},
                         action='play_archive', id=c['id'], start=b['timestamp_start'], end=b['timestamp_end'])
        self.end('episodes')

    # ---------- playback ----------
    def _check_limit(self):
        lim = self.api.stream_limit()
        if lim and lim.get('allow_stream') is False:
            ku.notify('Překročen limit streamů (%s/%s)' % (lim.get('current_devices'), lim.get('max_devices')), True)
            return False
        return True

    def play_live(self):
        c = self.api.channel(self.params['id'])
        if not c or not c['url']:
            raise ApiError('Kanál není dostupný')
        if not self._check_limit():
            xbmcplugin.setResolvedUrl(self.handle, False, xbmcgui.ListItem())
            return
        li = ku.make_playable_item(c['url'], c['name'], drm=c.get('drm'))
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def play_archive(self):
        cid, start, end = self.params['id'], int(self.params['start']), int(self.params['end'])
        if not self._check_limit():
            xbmcplugin.setResolvedUrl(self.handle, False, xbmcgui.ListItem())
            return
        res = self.api.archive_stream(cid, start, end)
        ku.log('archive content: protocol=%s start_from=%s overlap_pre=%s type=%s' % (
            res.get('protocol'), res.get('start_from'), res.get('overlap_pre'), res.get('hls_playlist_type')))
        offset = res.get('start_from') or res.get('overlap_pre') or 0
        li = ku.make_playable_item(res['stream_uri'], drm=res.get('drm_config'), start_offset=offset)
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    # ---------- misc ----------
    def iptv_generate(self):
        from resources.lib import iptv
        n = iptv.generate(self.api)
        ku.notify('Hotovo: %d kanálů' % n)

    def reset(self):
        self.api.reset()
        for f in ('now.json',):
            try:
                os.remove(os.path.join(ku.PROFILE, f))
            except OSError:
                pass
        ku.notify('Session smazána')

    def dispatch(self):
        action = self.params.get('action', 'root')
        fn = getattr(self, action, None)
        if fn is None or action.startswith('_'):
            raise ApiError('Neznámá akce: %s' % action)
        fn()


def run(argv):
    ku.log('v%s %s' % (ku.ADDON.getAddonInfo('version'), argv[2] if len(argv) > 2 else ''))
    r = Router(argv)
    try:
        r.dispatch()
    except AuthError as e:
        ku.log('auth error: %s' % e, xbmc.LOGERROR)
        r.api.state.pop('logged_in', None)
        ku.notify('Přihlášení: %s' % e, True)
        if r.params.get('action', '').startswith('play'):
            xbmcplugin.setResolvedUrl(r.handle, False, xbmcgui.ListItem())
    except ApiError as e:
        ku.log('api error: %s' % e, xbmc.LOGERROR)
        ku.notify(str(e), True)
        if r.params.get('action', '').startswith('play'):
            xbmcplugin.setResolvedUrl(r.handle, False, xbmcgui.ListItem())
