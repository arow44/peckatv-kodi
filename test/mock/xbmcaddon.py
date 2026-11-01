import os
PROFILE='/tmp/peckatv-profile/'
SETTINGS={'login':'','password':'','session_token':'TESTTOKEN','use_isa':'true','max_height':'720',
 'epg_days_back':'1','epg_days_forward':'1'}
class Addon:
    def __init__(self,id=None): pass
    def getAddonInfo(self,k): return {'id':'plugin.video.peckatv','profile':PROFILE,'version':'test'}[k]
    def getSetting(self,k): return SETTINGS.get(k,'')
