NOTIFICATION_ERROR='err'; NOTIFICATION_INFO='info'
NOTES=[]
SELECTS=[]
class Tag:
    def __getattr__(self,n): return lambda *a,**k: None
class ListItem:
    def __init__(self,label='',path='',offscreen=False): self.label=label; self.path=path; self.props={}; self.art={}
    def setArt(self,a): self.art=a
    def getVideoInfoTag(self): return Tag()
    def setProperty(self,k,v): self.props[k]=v
    def setMimeType(self,m): self.mime=m
    def setContentLookup(self,b): pass
    def addContextMenuItems(self,m): self.menu=m
class Dialog:
    def notification(self,*a): NOTES.append(a)
    def yesno(self,*a): return True
    def select(self,h,opts): SELECTS.append(opts); return 0
