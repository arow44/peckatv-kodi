"""Pecka.TV (4NET.TV LiveWeb) API client.

Session is cookie based (online.pecka.tv). Expired session -> HTTP 403,
then we re-authenticate with session_login_token or login/password.
"""
import json
import os
import time
import http.cookiejar
import urllib.request
import urllib.error

BASE = 'https://online.pecka.tv/'
BRAND_ID = 66
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36')
LANGS = ['ces', 'slk', 'eng', 'deu']
SOURCES_TTL = 1800  # signed URLs are valid 24 h, refresh every 30 min


class ApiError(Exception):
    pass


class AuthError(ApiError):
    pass


def tz_offset_minutes(ts=None):
    ts = time.time() if ts is None else ts
    lt = time.localtime(ts)
    return int(lt.tm_gmtoff // 60)


class PeckaApi(object):
    def __init__(self, profile_dir, login='', password='', session_token='', log=None, device_name='Kodi'):
        self.profile_dir = profile_dir
        self.login = login
        self.password = password
        self.session_token = session_token
        self.device_name = device_name
        self.log = log or (lambda msg: None)
        if not os.path.isdir(profile_dir):
            os.makedirs(profile_dir)
        self.state_file = os.path.join(profile_dir, 'state.json')
        self.cookie_file = os.path.join(profile_dir, 'cookies.lwp')
        self.state = self._load_state()
        self.cj = http.cookiejar.LWPCookieJar(self.cookie_file)
        try:
            self.cj.load(ignore_discard=True, ignore_expires=True)
        except Exception:
            pass
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cj))

    # ---------- state ----------
    def _load_state(self):
        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_state(self):
        with open(self.state_file, 'w', encoding='utf-8') as f:
            json.dump(self.state, f)
        try:
            self.cj.save(ignore_discard=True, ignore_expires=True)
        except Exception as e:
            self.log('cookie save failed: %s' % e)

    def reset(self):
        # keep cookies: they identify the paired device, clearing them would take another device slot
        self.state = {}
        self._save_state()

    # ---------- http ----------
    def _raw_post(self, path, data=None):
        body = json.dumps(data if data is not None else {}).encode('utf-8')
        req = urllib.request.Request(BASE + path, data=body, method='POST')
        req.add_header('Content-Type', 'application/json')
        req.add_header('Accept', 'application/json, text/plain, */*')
        req.add_header('User-Agent', UA)
        req.add_header('Origin', BASE.rstrip('/'))
        req.add_header('Referer', BASE)
        try:
            with self.opener.open(req, timeout=20) as resp:
                raw = resp.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise AuthError('HTTP %d on %s' % (e.code, path))
            try:
                msg = json.loads(e.read().decode('utf-8')).get('message')
            except Exception:
                msg = None
            raise ApiError(msg or 'HTTP %d on %s' % (e.code, path))
        try:
            return json.loads(raw)
        except ValueError:
            raise ApiError('Invalid JSON from %s' % path)

    def post(self, path, data=None, _retry=True):
        if not self.state.get('logged_in'):
            self.authenticate()
        try:
            res = self._raw_post(path, data)
        except AuthError:
            if not _retry:
                raise
            self.log('session expired, re-authenticating')
            self.authenticate()
            return self.post(path, data, _retry=False)
        self.cj.save(ignore_discard=True, ignore_expires=True)
        return res

    # ---------- auth ----------
    def authenticate(self):
        token = self.state.get('session_token') or self.session_token
        res = None
        if token:
            try:
                res = self._raw_post('api/authenticate', {'session_login_token': token})
                if not res.get('success'):
                    res = None
            except ApiError as e:
                self.log('session token login failed: %s' % e)
                res = None
        if res is None and self.login and self.password:
            res = self._raw_post('api/authenticate', {
                'login': self.login, 'password': self.password, 'id_brand': BRAND_ID})
            if not res.get('success'):
                raise AuthError(res.get('message') or 'Přihlášení selhalo')
        if res is None:
            raise AuthError('Vyplň v nastavení přihlašovací údaje nebo session token')
        if res.get('session_token'):
            self.state['session_token'] = res['session_token']
        if res.get('authorized_device') is False:
            self._pair_device()
        self.state['logged_in'] = True
        self._save_state()
        self._ensure_profile()

    def _pair_device(self):
        """New client = unauthorized device; the web app pairs itself as a 'browser' the same way."""
        self.log('device not authorized, pairing as "%s"' % self.device_name)
        try:
            res = self._raw_post('api/subscriber/pairBrowser', {'name': self.device_name})
        except ApiError as e:
            raise AuthError('Spárování zařízení selhalo: %s' % e)
        if not res.get('pairing_success'):
            raise AuthError(res.get('message') or 'Spárování zařízení selhalo (limit zařízení?)')
        self._save_state()  # persist device cookie, otherwise every start would pair a new device

    def _ensure_profile(self):
        if self.state.get('profile_id'):
            return
        res = self._raw_post('api/device/getSubscriberProfiles/', {})
        pid = res.get('remembered_subscriber_profile_id')
        if not pid and res.get('profiles'):
            pid = res['profiles'][0]['id']
        if not pid:
            raise ApiError('Nenalezen žádný profil')
        self._raw_post('api/device/subscriberProfileUsed/',
                       {'id_subscriber_profile': pid, 'remember_subscriber_profile': True})
        self.state['profile_id'] = pid
        self._save_state()

    @property
    def profile_id(self):
        if not self.state.get('profile_id'):
            self.authenticate()
        return self.state['profile_id']

    # ---------- data ----------
    def channels(self, force=False):
        cache = self.state.get('sources')
        if not force and cache and time.time() - cache.get('ts', 0) < SOURCES_TTL:
            return cache['channels']
        res = self.post('api/device/getSources', {'id_subscriber_profile': self.profile_id})
        if not res.get('success'):
            raise ApiError(res.get('message') or 'getSources selhalo')
        chans = []
        for c in res.get('channels', []):
            src = c.get('content_sources') or []
            url, drm = None, None
            if src:
                urls = src[0].get('stream_profile_urls') or {}
                key = 'adaptive' if 'adaptive' in urls else (list(urls)[0] if urls else None)
                url = urls.get(key) if key else None
                drm = (src[0].get('drm_config') or {}).get(key) if key else None
            chans.append({
                'id': c['id'], 'id_epg': c.get('id_epg'), 'name': c.get('name'),
                'type': c.get('type'), 'weight': c.get('weight', 0),
                'timeshift': c.get('timeshift'), 'catchup_hours': c.get('catchup_length') or 0,
                'url': url, 'drm': drm,
            })
        chans.sort(key=lambda x: x['weight'])
        self.state['sources'] = {'ts': time.time(), 'channels': chans}
        self._save_state()
        return chans

    def channel(self, channel_id):
        for c in self.channels():
            if str(c['id']) == str(channel_id):
                return c
        return None

    def epg_by_date(self, epg_ids, date_str):
        # web app sends the date without zero padding ('2026-11-1'); padded days are rejected
        y, m, d = (int(x) for x in str(date_str).split('-'))
        res = self.post('api/epg/getEpgByDate', {
            'epg_ids': [str(i) for i in epg_ids], 'date': '%d-%d-%d' % (y, m, d),
            'language': LANGS, 'timezone_offset': tz_offset_minutes()})
        return res.get('broadcasts') or {}

    def catchup(self, id_epg, ts_from, ts_to):
        res = self.post('api/epg/getCatchupBroadcasts', {
            'from': int(ts_from), 'to': int(ts_to), 'id_epg': id_epg,
            'language': LANGS, 'timezone_offset': tz_offset_minutes()})
        return res.get('broadcasts') or []

    def archive_stream(self, channel_id, start, end, offset=None):
        res = self.post('api/contentdemon/getContent/', {
            'channel_id': int(channel_id), 'start': int(start), 'end': int(end),
            'broadcast_offset': int(offset) if offset else None})
        if not res.get('stream_uri'):
            raise ApiError(res.get('message') or 'Archiv není dostupný')
        return res

    def stream_limit(self):
        try:
            res = self.post('api/peoplemeter/getStreamLimit/',
                            {'id_subscriber_profile': self.profile_id, 'services_changed': False})
            return res.get('stream_limit') or {}
        except ApiError:
            return {}


def logo_url(channel_id):
    return 'https://epg.as.4net.tv/files/channel_logos/%s.png' % channel_id


def image_url(bc, size='_300'):
    for k in ('photo', 'poster'):
        p = bc.get(k)
        if p and p.get('url'):
            return p['url'].replace('{size}', size)
    return None
