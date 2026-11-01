NOTIFICATION_ERROR='err'; NOTIFICATION_INFO='info'
NOTES=[]
class Tag:
    def __getattr__(self,n): return lambda *a,**k: None
class ListItem:
    def __init__(self,label='',path='',offscreen=False): self.label=label; self.path=path; self.props={}; self.art={}
    def setArt(self,a): self.art=a
    def getVideoInfoTag(self): return Tag()
    def setProperty(self,k,v): self.props[k]=v
    def setMimeType(self,m): self.mime=m
    def setContentLookup(self,b): pass
class Dialog:
    def notification(self,*a): NOTES.append(a)
