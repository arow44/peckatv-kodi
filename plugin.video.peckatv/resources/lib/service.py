import os
import time

import xbmc

from resources.lib import kodiutils as ku

STAMP = os.path.join(ku.PROFILE, 'iptv_last.txt')


def _last():
    try:
        with open(STAMP) as f:
            return float(f.read().strip())
    except Exception:
        return 0.0


def _touch():
    with open(STAMP, 'w') as f:
        f.write(str(time.time()))


def run():
    monitor = xbmc.Monitor()
    if monitor.waitForAbort(30):  # let network come up
        return
    while not monitor.abortRequested():
        if ku.setting_bool('iptv_enabled'):
            hours = ku.setting_int('iptv_interval', 12) or 12
            if time.time() - _last() > hours * 3600:
                try:
                    from resources.lib import iptv
                    n = iptv.generate(ku.get_api())
                    _touch()
                    ku.log('service: IPTV export done (%d channels)' % n)
                except Exception as e:
                    ku.log('service: IPTV export failed: %s' % e, xbmc.LOGERROR)
        if monitor.waitForAbort(600):
            break
