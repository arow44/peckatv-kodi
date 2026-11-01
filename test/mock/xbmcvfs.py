import os
def translatePath(p): return p
def exists(p): return os.path.exists(p)
def mkdirs(p): os.makedirs(p,exist_ok=True)
def delete(p): os.remove(p)
def rename(a,b): os.rename(a,b); return True
class File:
    def __init__(self,p,m): self.f=open(p,m,encoding='utf-8')
    def write(self,s): self.f.write(s)
    def close(self): self.f.close()
