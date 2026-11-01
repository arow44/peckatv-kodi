LOGINFO,LOGWARNING,LOGERROR=1,2,3
LOG=[]
def log(m,l=1): LOG.append(m)
def getCondVisibility(c): return True
class Monitor:
    def abortRequested(self): return True
    def waitForAbort(self,t): return True
