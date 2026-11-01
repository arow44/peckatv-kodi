ITEMS=[]; RESOLVED=[]
def addDirectoryItem(h,url,li,isFolder=False): ITEMS.append((li.label,url,isFolder))
def endOfDirectory(h,cacheToDisc=False): pass
def setContent(h,c): pass
def setResolvedUrl(h,ok,li): RESOLVED.append((ok,li))
