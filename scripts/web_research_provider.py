"""Host capabilities are injected, never invented. Adapter performs search AND open."""
from abc import ABC, abstractmethod
from source_ranker import ranked
from evidence_extractor import public_url

class SearchProvider(ABC):
    name='CUSTOM_SEARCH_API'
    @abstractmethod
    def search(self, query, *, language='en'): pass
    @abstractmethod
    def open(self, url): pass

class CallableProvider(SearchProvider):
    def __init__(self,name,search,open_page):
        if name not in {'HOST_NATIVE_SEARCH','BROWSER_SEARCH','MCP_SEARCH','CUSTOM_SEARCH_API'}:
            raise ValueError('Unknown provider adapter')
        self.name=name; self._search=search; self._open=open_page
    def search(self,query,*,language='en'): return self._search(query,language=language)
    def open(self,url): return self._open(url)

class ProviderChain:
    def __init__(self,providers):
        priority=['HOST_NATIVE_SEARCH','BROWSER_SEARCH','MCP_SEARCH','CUSTOM_SEARCH_API']
        self.providers=sorted(providers,key=lambda p:priority.index(p.name))
        self.page_cache={}
        self.negative_cache={}
    def capabilities(self):
        return {name:any(p.name==name for p in self.providers) for name in
                ('HOST_NATIVE_SEARCH','BROWSER_SEARCH','MCP_SEARCH','CUSTOM_SEARCH_API')}
    def execute(self,task,*,max_sources=5):
        attempts=[]
        for provider in self.providers:
            try:
                results=provider.search(task['query'],language=task['language'])
                if not results: raise RuntimeError('Empty search response')
            except Exception as exc:
                attempts.append({'provider':provider.name,'result':'PROVIDER_UNAVAILABLE','failure_reason':type(exc).__name__})
                continue
            pages=[]
            for result in ranked(results)[:max_sources]:
                if not public_url(result['url']):
                    pages.append({'url':result['url'],'status':'ERROR','failure_reason':'Non-public HTTPS source rejected'})
                    continue
                from data_freshness import freshness
                from data_freshness import timestamp
                from research_ledger import stamp
                from datetime import timedelta
                negative_key=(provider.name,result['url'])
                failed=self.negative_cache.get(negative_key)
                if failed and timestamp(stamp())-timestamp(failed['retrieved_at'])<timedelta(minutes=30):
                    pages.append({**failed,'cache_hit':True});continue
                cached=self.page_cache.get(result['url'])
                if cached and not freshness(cached,'route')['refresh_required']:
                    pages.append({**cached,'cache_hit':True});continue
                try:
                    opened=provider.open(result['url']);pages.append(opened)
                    if opened.get('status')=='OPENED' and opened.get('retrieved_at'):self.page_cache[result['url']]=opened
                    elif opened.get('status')=='ERROR':self.negative_cache[negative_key]={**opened,'retrieved_at':opened.get('retrieved_at') or stamp()}
                except Exception as exc:
                    failure={'url':result['url'],'status':'ERROR','failure_reason':type(exc).__name__,'retrieved_at':stamp()}
                    pages.append(failure);self.negative_cache[negative_key]=failure
            if not any(p.get('status')=='OPENED' for p in pages):
                attempts.append({'provider':provider.name,'result':'SOURCE_UNAVAILABLE','pages':pages})
                continue
            return {'task_id':task['task_id'],'query':task['query'],'provider':provider.name,
                'results':results,'pages':pages,'provider_attempts':attempts,'claims':[]}
        return {'task_id':task['task_id'],'query':task['query'],'provider':None,'results':[],
            'pages':[],'provider_attempts':attempts,'claims':[],'failure_reason':'All callable providers failed'}
