import socket

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from resources.lib.api import PeckaApi, UA

ADDON = xbmcaddon.Addon('plugin.video.peckatv')
ADDON_ID = ADDON.getAddonInfo('id')
PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))


def log(msg, level=xbmc.LOGINFO):
    xbmc.log('[%s] %s' % (ADDON_ID, msg), level)


def setting(key):
    return xbmcaddon.Addon(ADDON_ID).getSetting(key)  # fresh instance = current values


def setting_bool(key):
    return setting(key) == 'true'


def setting_int(key, default=0):
    try:
        return int(float(setting(key)))
    except (TypeError, ValueError):
        return default


def notify(msg, error=False):
    xbmcgui.Dialog().notification('Pecka.TV', msg,
                                  xbmcgui.NOTIFICATION_ERROR if error else xbmcgui.NOTIFICATION_INFO, 5000)


def get_api():
    return PeckaApi(PROFILE, login=setting('login'), password=setting('password'),
                    session_token=setting('session_token').strip(), log=log,
                    device_name='Kodi (%s)' % socket.gethostname())


def isa_available():
    try:
        return bool(xbmc.getCondVisibility('System.HasAddon(inputstream.adaptive)')) and \
            bool(xbmc.getCondVisibility('System.AddonIsEnabled(inputstream.adaptive)'))
    except Exception:
        return False


def make_playable_item(url, label=None, drm=None, start_offset=None):
    headers = 'User-Agent=%s&Referer=https://online.pecka.tv/' % UA.replace(' ', '%20')
    use_isa = setting_bool('use_isa') and isa_available()
    if use_isa:
        li = xbmcgui.ListItem(label=label or '', path=url, offscreen=True)
        li.setProperty('inputstream', 'inputstream.adaptive')
        li.setProperty('inputstream.adaptive.manifest_headers', headers)
        li.setProperty('inputstream.adaptive.stream_headers', headers)
        max_h = setting('max_height') or '1080'
        if max_h in ('0', '1', '2'):  # select stores index
            max_h = ['1080', '720', '540'][int(max_h)]
        li.setProperty('inputstream.adaptive.chooser_resolution_max', max_h + 'p')
        li.setProperty('inputstream.adaptive.chooser_resolution_secure_max', max_h + 'p')
        if drm:
            log('DRM config present (untested): %s' % drm, xbmc.LOGWARNING)
    else:
        li = xbmcgui.ListItem(label=label or '', path=url + '|' + headers, offscreen=True)
    li.setMimeType('application/vnd.apple.mpegurl')
    li.setContentLookup(False)
    if start_offset:
        li.setProperty('StartOffset', str(int(start_offset)))
    return li
