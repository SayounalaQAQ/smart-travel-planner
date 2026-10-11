"""Bounded in-memory TTL cache for public provider responses."""
import time
class TTLCache:
    def __init__(self,max_entries=256): self.max_entries=max_entries; self._values={}
    def get(self,key,ttl):
        item=self._values.get(key)
        if not item: return None
        if time.time()-item[0]>=ttl: self._values.pop(key,None); return None
        return item[1]
    def set(self,key,value):
        if len(self._values)>=self.max_entries: self._values.clear()
        self._values[key]=(time.time(),value)
