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
PROGRAM_DAYS_FORWARD = 7
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
    def add_dir(self, label, art=None, info=None, folder=True, playable=False, menu=None, **kw):
        li = xbmcgui.ListItem(label=label, offscreen=True)
        if menu:
            li.addContextMenuItems(menu)
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

    # ---------- recording helpers ----------
    def _pvr_state(self):
        """Existing recordings / series as lookup sets (cached for this plugin call)."""
        if getattr(self, '_pvr_cache', None) is None:
            recs, series = {}, set()
            try:
                for r in self.api.recordings():
                    recs[(str(r.get('id_channel')), str(r.get('id_broadcast')))] = r
            except ApiError as e:
                ku.log('recordings lookup failed: %s' % e)
            try:
                for p in self.api.series_recordings():
                    series.add((str(p.get('id_channel')), str(p.get('id_show'))))
            except ApiError as e:
                ku.log('series lookup failed: %s' % e)
            self._pvr_cache = (recs, series)
        return self._pvr_cache

    @staticmethod
    def _can_record(c, b, now=None):
        """Same rule as web Channel.canBeBroadcastRecorded."""
        now = time.time() if now is None else now
        if not c.get('pvr', True):
            return False
        if b['timestamp_start'] >= now:
            return True
        if b['timestamp_end'] > now:  # running
            return bool(c.get('timeshift'))
        return b['timestamp_start'] >= now - (c.get('catchup_hours') or 0) * 3600

    def _bc_params(self, c, b):
        return dict(id=c['id'], bid=b['id'], start=b['timestamp_start'], end=b['timestamp_end'],
                    epg=b.get('id_epg') or c.get('id_epg') or 0, name=(b.get('name') or '')[:64],
                    show=b.get('id_show') or '', sname=(b.get('name_show') or '')[:64])

    def _record_options(self, c, b):
        """[(label, action-params)] available for a broadcast."""
        recs, series = self._pvr_state()
        opts = []
        rec = recs.get((str(c['id']), str(b['id'])))
        if rec:
            opts.append(('Smazat nahrávku', dict(action='delete_recording', pvr=rec['id'], name=b.get('name', ''))))
        elif self._can_record(c, b):
            opts.append(('Nahrát', dict(action='record', **self._bc_params(c, b))))
        if c.get('periodic_pvr') and b.get('id_show') and b['timestamp_end'] > time.time():
            if (str(c['id']), str(b['id_show'])) not in series:
                opts.append(('Nahrávat všechny díly', dict(action='record_series', **self._bc_params(c, b))))
        return opts

    def _record_menu(self, c, b):
        return [(label, 'RunPlugin(%s)' % self.url(**kw)) for label, kw in self._record_options(c, b)]

    def _rec_mark(self, c, b):
        recs, series = self._pvr_state()
        if (str(c['id']), str(b['id'])) in recs:
            return '  [COLOR red]●REC[/COLOR]'
        if b.get('id_show') and (str(c['id']), str(b['id_show'])) in series:
            return '  [COLOR orange]●série[/COLOR]'
        return ''

    # ---------- views ----------
    def root(self):
        self.add_dir('Živé vysílání', action='live')
        self.add_dir('Archiv', action='archive')
        self.add_dir('Nahrávky', action='recordings')
        self.add_dir('Program a nahrávání', action='program')
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
            menu = self._record_menu(c, b) if b and b.get('id') else None
            self.add_dir(label, art=art, info=info, folder=False, playable=True, menu=menu,
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
            label += self._rec_mark(c, b)
            img = image_url(b)
            art = {'thumb': img, 'fanart': img, 'icon': logo_url(c['id'])} if img else {'icon': logo_url(c['id'])}
            self.add_dir(label, art=art, folder=False, playable=True, menu=self._record_menu(c, b),
                         info={'title': b['name'], 'plot': b.get('description_broadcast') or '',
                               'duration': b['timestamp_end'] - b['timestamp_start'], 'year': b.get('year')},
                         action='play_archive', id=c['id'], start=b['timestamp_start'], end=b['timestamp_end'])
        self.end('episodes')

    def recordings(self):
        now = time.time()
        recs = self.api.recordings()
        try:
            n_series = len(self.api.series_recordings())
        except ApiError:
            n_series = 0
        if n_series:
            self.add_dir('[B]Sériová nahrávání (%d)[/B]' % n_series, action='series')
        details = {}
        try:
            details = self.api.broadcasts({r.get('id_broadcast') for r in recs})
        except ApiError as e:
            ku.log('recording details failed: %s' % e)
        names = {str(c['id']): c['name'] for c in self.api.channels()}
        # newest first (web default ordering by creation date desc ~ by start desc)
        for r in sorted(recs, key=lambda x: x.get('start') or 0, reverse=True):
            start, end = r.get('start') or 0, r.get('end') or 0
            b = details.get(str(r.get('id_broadcast'))) or details.get(r.get('id_broadcast')) or {}
            name = r.get('name') or b.get('name') or 'Nahrávka'
            channel = r.get('channel_name') or names.get(str(r.get('id_channel')), '')
            when = time.strftime('%d.%m. %H:%M', time.localtime(start)) if start else ''
            label = '%s  [COLOR gray]%s, %s[/COLOR]' % (name, channel, when)
            if b.get('name_episode') and b['name_episode'] not in name:
                label = label.replace(name, '%s – %s' % (name, b['name_episode']), 1)
            playable = start and start < now and r.get('playable', True) is not False
            if start > now:
                label += '  [COLOR yellow](naplánováno)[/COLOR]'
            elif end > now:
                label += '  [COLOR red](nahrává se)[/COLOR]'
            plot = b.get('description_broadcast') or ''
            if r.get('date_expired'):
                days = int((r['date_expired'] - now) // 86400) + 1
                plot = ('Smaže se za %d dní (%s)\n\n' % (days, time.strftime(
                    '%d.%m.%Y', time.localtime(r['date_expired'])))) + plot
            img = image_url(b) or image_url(r) or r.get('poster_address')
            art = {'icon': logo_url(r.get('id_channel'))}
            if img:
                art.update({'thumb': img, 'fanart': img, 'poster': img})
            menu = [('Smazat nahrávku', 'RunPlugin(%s)' % self.url(action='delete_recording', pvr=r['id'],
                                                                   name=name))]
            self.add_dir(label, art=art, folder=False, playable=bool(playable), menu=menu,
                         info={'title': name, 'plot': plot, 'duration': max(0, end - start),
                               'year': b.get('year')},
                         action='play_archive' if playable else 'not_playable',
                         id=r.get('id_channel'), start=start, end=end)
        self.end('episodes')

    def not_playable(self):
        ku.notify('Nahrávku zatím nelze přehrát')

    def delete_recording(self):
        name = self.params.get('name', '')
        if not xbmcgui.Dialog().yesno('Pecka.TV', 'Opravdu smazat nahrávku?\n[B]%s[/B]' % name):
            return
        self.api.delete_recording(self.params['pvr'])
        ku.notify('Nahrávka smazána')
        xbmc.executebuiltin('Container.Refresh')

    def series(self):
        names = {str(c['id']): c['name'] for c in self.api.channels()}
        for p in sorted(self.api.series_recordings(), key=lambda x: (x.get('name') or '').lower()):
            name = p.get('name') or 'Pořad'
            label = '%s  [COLOR gray]%s[/COLOR]' % (name, names.get(str(p.get('id_channel')), ''))
            menu = [('Zrušit sériové nahrávání', 'RunPlugin(%s)' % self.url(
                action='delete_series', periodic=p['id'], name=name))]
            self.add_dir(label, art={'icon': logo_url(p.get('id_channel'))}, folder=False, menu=menu,
                         action='delete_series', periodic=p['id'], name=name)
        self.end('files')

    def delete_series(self):
        name = self.params.get('name', '')
        if not xbmcgui.Dialog().yesno('Pecka.TV', 'Zrušit nahrávání všech dílů?\n[B]%s[/B]\n'
                                      'Už nahrané díly zůstanou.' % name):
            return
        self.api.delete_series_recording(self.params['periodic'])
        ku.notify('Sériové nahrávání zrušeno')
        xbmc.executebuiltin('Container.Refresh')

    # ---------- programme (EPG forward) + scheduling ----------
    def program(self):
        for c in self.api.channels():
            if c['url'] and c.get('pvr', True):
                self.add_dir(c['name'], art={'icon': logo_url(c['id']), 'thumb': logo_url(c['id'])},
                             action='program_days', id=c['id'])
        self.end('files')

    def program_days(self):
        c = self.api.channel(self.params['id'])
        today = datetime.date.today()
        for i in range(PROGRAM_DAYS_FORWARD + 1):
            d = today + datetime.timedelta(days=i)
            if i == 0:
                label = 'Dnes'
            elif i == 1:
                label = 'Zítra'
            else:
                label = '%s %s' % (DAYS_CZ[d.weekday()], d.strftime('%d.%m.'))
            self.add_dir(label, action='program_day', id=c['id'], date=d.isoformat())
        self.end('files')

    def _day_broadcasts(self, c, date):
        bcs = []
        try:
            bcs = self.api.epg_by_date([c['id_epg']], date).get(str(c['id_epg'])) or []
        except ApiError as e:
            ku.log('getEpgByDate failed for %s: %s' % (c['id_epg'], e))
        if not bcs:  # fallback: same endpoint as the archive
            day_start = time.mktime(time.strptime(date, '%Y-%m-%d'))
            bcs = self.api.catchup(c['id_epg'], day_start, day_start + 86400)
        return [b for b in bcs if time.strftime('%Y-%m-%d', time.localtime(b['timestamp_start'])) == date]

    def program_day(self):
        c = self.api.channel(self.params['id'])
        now = time.time()
        for b in sorted(self._day_broadcasts(c, self.params['date']), key=lambda x: x['timestamp_start']):
            if b['timestamp_end'] <= now - (c.get('catchup_hours') or 0) * 3600:
                continue  # neither playable nor recordable any more
            t = time.strftime('%H:%M', time.localtime(b['timestamp_start']))
            label = '%s  %s' % (t, b['name'])
            if b.get('name_episode') and b['name_episode'] not in b['name']:
                label += ' – ' + b['name_episode']
            past = b['timestamp_start'] <= now
            if past and b['timestamp_end'] > now:
                label += '  [COLOR red](běží)[/COLOR]'
            elif past:
                label = '[COLOR gray]%s[/COLOR]' % label
            label += self._rec_mark(c, b)
            img = image_url(b)
            art = {'icon': logo_url(c['id'])}
            if img:
                art.update({'thumb': img, 'fanart': img})
            info = {'title': b['name'], 'plot': b.get('description_broadcast') or '',
                    'duration': b['timestamp_end'] - b['timestamp_start'], 'year': b.get('year')}
            if past and b['timestamp_end'] <= now:
                self.add_dir(label, art=art, info=info, folder=False, playable=True,
                             menu=self._record_menu(c, b), action='play_archive',
                             id=c['id'], start=b['timestamp_start'], end=b['timestamp_end'])
            else:
                self.add_dir(label, art=art, info=info, folder=False, menu=self._record_menu(c, b),
                             action='broadcast_menu', **self._bc_params(c, b))
        self.end('episodes')

    def _bc_from_params(self):
        p = self.params
        b = {'id': int(p['bid']), 'timestamp_start': int(p['start']), 'timestamp_end': int(p['end']),
             'id_epg': int(p.get('epg') or 0), 'name': p.get('name', ''),
             'id_show': int(p['show']) if p.get('show') else None, 'name_show': p.get('sname') or None}
        try:  # web sends poster/photo objects too; take them from the broadcast detail
            d = self.api.broadcasts([b['id']])
            d = d.get(str(b['id'])) or d.get(b['id']) or {}
            for k in ('poster', 'photo'):
                if d.get(k):
                    b[k] = d[k]
        except ApiError as e:
            ku.log('broadcast detail failed: %s' % e)
        return b

    def broadcast_menu(self):
        c = self.api.channel(self.params['id'])
        b = self._bc_from_params()
        opts = self._record_options(c, b)
        if not opts:
            ku.notify('Tento pořad nelze nahrát')
            return
        i = xbmcgui.Dialog().select(b['name'], [o[0] for o in opts])
        if i < 0:
            return
        self.params = {k: str(v) for k, v in opts[i][1].items()}
        self.dispatch()

    def record(self):
        b = self._bc_from_params()
        self.api.add_recording(self.params['id'], b)
        ku.notify('%s: %s' % ('Nahrávka naplánována' if b['timestamp_end'] > time.time()
                              else 'Uloženo do nahrávek', b['name']))
        xbmc.executebuiltin('Container.Refresh')

    def record_series(self):
        b = self._bc_from_params()
        if not b.get('id_show'):
            raise ApiError('Pořad není seriál')
        if not xbmcgui.Dialog().yesno('Pecka.TV', 'Nahrávat všechny díly pořadu?\n[B]%s[/B]'
                                      % (b.get('name_show') or b['name'])):
            return
        self.api.add_series_recording(self.params['id'], b)
        ku.notify('Sériové nahrávání zapnuto')
        xbmc.executebuiltin('Container.Refresh')

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
