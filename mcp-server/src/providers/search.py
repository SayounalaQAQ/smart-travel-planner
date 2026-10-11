"""Replaceable search providers. Host search is preferred; MCP fallbacks stay explicit."""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import os
import re
import urllib.parse
from urllib.parse import urlsplit

from models.evidence import record as evidence_record


class SearchProvider(ABC):
    name = "search-provider"

    @abstractmethod
    def search(self, query, *, domains=None, recency=None, language="en"):
        raise NotImplementedError


class HostNativeSearchProvider(SearchProvider):
    """Adapter for a host runtime's native search callable; never silently emulated."""
    name = "host-native-search"

    def __init__(self, search_callable):
        self.search_callable = search_callable

    def search(self, query, *, domains=None, recency=None, language="en"):
        raw = self.search_callable(query, domains=domains, recency=recency, language=language)
        return normalize_search_response(raw, self.name)


class BraveSearchProvider(SearchProvider):
    """Optional keyed web search. No credential is stored in plugin files."""
    name = "Brave Search API"
    endpoint = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, request_json, api_key=None, checked_at=None, endpoint=None):
        self.request_json = request_json
        self.api_key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY")
        self.checked_at = checked_at or (lambda: datetime.now(timezone.utc).replace(microsecond=0).isoformat())
        self.endpoint = endpoint or self.endpoint

    def search(self, query, *, domains=None, recency=None, language="en"):
        if not self.api_key:
            return {"status": "unavailable", "results": [], "provider": self.name,
                    "checked_at": self.checked_at(), "limitations": ["BRAVE_SEARCH_API_KEY is not configured."]}
        q = query
        if domains:
            q += " " + " ".join("site:" + d for d in domains)
        params = {"q": q, "count": 10, "search_lang": language[:2] if language else "en"}
        if recency in {"day", "week", "month", "year"}:
            params["freshness"] = {"day": "pd", "week": "pw", "month": "pm", "year": "py"}[recency]
        raw = self.request_json(self.endpoint + "?" + urllib.parse.urlencode(params),
                                headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"})
        rows = (raw.get("web") or {}).get("results") or []
        results = [{"title": x.get("title"), "url": x.get("url"), "snippet": x.get("description") or "",
                    "source_domain": urlsplit(x.get("url") or "").hostname or "", "source": self.name,
                    "published_at": x.get("page_age"), "retrieved_at": self.checked_at(),
                    "relevance": "web search result"} for x in rows]
        results = prioritize_official_results(results)
        evidences = [evidence_record("search result", x.get("snippet") or x.get("title") or "", x.get("title") or self.name,
                    x["url"], classify_domain(x.get("source_domain", "")), x["retrieved_at"],
                    confidence="medium", published_at=x.get("published_at")) for x in results if x.get("url")]
        return {"status": "available" if results else "empty", "results": results, "provider": self.name,
                "evidence": evidences, "checked_at": self.checked_at(), "limitations": []}


class WikipediaSearchProvider(SearchProvider):
    name = "Wikipedia API"

    def __init__(self, endpoint, get_json, checked_at):
        self.endpoint, self.get_json, self.checked_at = endpoint, get_json, checked_at

    def search(self, query, *, domains=None, recency=None, language="en"):
        params={"action":"query","generator":"search","gsrsearch":query,"gsrlimit":8,
                "prop":"extracts|info","exintro":1,"explaintext":1,"inprop":"url",
                "format":"json","utf8":1}
        payload=self.get_json(self.endpoint+"?"+urllib.parse.urlencode(params))
        pages=payload.get("query",{}).get("pages",{}).values()
        stamp=self.checked_at()
        results=[{"title":page.get("title"),"url":page.get("fullurl"),
                  "source_domain":urlsplit(page.get("fullurl") or "").hostname or "",
                  "snippet":(page.get("extract") or "")[:600],"source":self.name,
                  "published_at":None,"retrieved_at":stamp,"relevance":"encyclopedia match"} for page in pages]
        evidence=[evidence_record("encyclopedia background, not current travel fact",x.get("snippet") or x.get("title") or "",
                    x.get("title") or self.name,x["url"],"medium",stamp,confidence="low") for x in results if x.get("url")]
        limits=["Wikipedia is an encyclopedia fallback, not general web search; do not use it as current price, hours, reservation, or transit evidence."]
        if domains: limits.append("The Wikipedia fallback cannot guarantee domain filtering.")
        if recency: limits.append("The Wikipedia fallback cannot guarantee publication recency.")
        return {"status":"degraded","results":results,"provider":self.name,"evidence":evidence,
                "checked_at":stamp,"limitations":limits}


def classify_domain(domain):
    d = (domain or "").casefold().split(":")[0]
    if d.endswith((".go.jp", ".gov", ".gov.uk", ".gov.cn", ".gov.au")) or any(
            marker in d for marker in ("japan.travel", "gotokyo.org", "kyoto.travel", "osaka-info.jp", "jr-central.co.jp", "jr-odekake.net")):
        return "official"
    if d.endswith(".edu") or d.endswith(".ac.jp"):
        return "high"
    return "unknown"


def prioritize_official_results(results):
    return sorted(results, key=lambda x: (0 if classify_domain(x.get("source_domain") or urlsplit(x.get("url") or "").hostname or "") == "official" else 1))


def normalize_search_response(raw, provider):
    stamp = raw.get("checked_at") or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    out=[]
    for item in raw.get("results", []):
        url=item.get("url")
        if not isinstance(url,str) or not url.startswith("https://"): continue
        domain=urlsplit(url).hostname or ""
        out.append({"title":item.get("title") or "Untitled", "url":url, "source_domain":domain,
                    "snippet":item.get("snippet") or item.get("evidence") or "", "source":provider,
                    "retrieved_at":item.get("retrieved_at") or stamp,
                    "published_at":item.get("published_at"), "source_type":item.get("source_type") or classify_domain(domain),
                    "confidence":item.get("confidence") or "medium", "relevance":item.get("relevance")})
    normalized=prioritize_official_results(out)
    evidence=raw.get("evidence") or [evidence_record("search result",item.get("snippet") or item.get("title") or "",
        item.get("title") or provider,item["url"],item.get("source_type") or "unknown",item["retrieved_at"],
        confidence=item.get("confidence") or "medium",published_at=item.get("published_at")) for item in normalized]
    return {**raw, "results":normalized, "evidence":evidence, "provider":provider, "checked_at":stamp}


class SearchService:
    """Provider order: injected host search, configured keyed MCP search, then explicitly degraded background."""
    def __init__(self, config, get_json, checked_at, *, request_json=None, host_search=None, api_key=None):
        self.config=config; self.get_json=get_json; self.checked_at=checked_at
        self.request_json=request_json; self.host_search=host_search; self.api_key=api_key

    def research_web(self, query, *, domains=None, recency=None, language="en"):
        if not isinstance(query,str) or not query.strip() or len(query)>500:
            raise ValueError("query must be non-empty and at most 500 characters")
        if domains is not None and (not isinstance(domains,list) or any(not isinstance(d,str) or not re.fullmatch(r"(?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,}",d) for d in domains)):
            raise ValueError("domains must contain only valid public DNS names")
        host_limits=[]
        if self.host_search:
            try:
                host_result=HostNativeSearchProvider(self.host_search).search(query,domains=domains,recency=recency,language=language)
                if host_result.get("results") and host_result.get("status") not in {"unavailable","empty"}:
                    return host_result
                host_limits=host_result.get("limitations",[])
            except Exception as exc:
                host_limits=[f"Host-native search failed ({type(exc).__name__}); trying configured MCP fallback."]
        settings=self.config.get("search",{}); primary=settings.get("primary") or {}; fallback=settings.get("fallback") or {}
        keyed=settings.get("keyed_fallback") or {}
        if self.request_json and keyed.get("type","brave")=="brave" and (self.api_key or os.environ.get("BRAVE_SEARCH_API_KEY")):
            try: result=BraveSearchProvider(self.request_json,self.api_key,self.checked_at,keyed.get("base_url")).search(query,domains=domains,recency=recency,language=language)
            except Exception as exc: result={"status":"unavailable","results":[],"provider":"Brave Search API","evidence":[],"checked_at":self.checked_at(),"limitations":[f"Optional search provider failed ({type(exc).__name__}); no search results returned."]}
            if host_limits: result.setdefault("limitations",[]).extend(host_limits)
            return result
        selected=fallback if primary.get("type")=="agent" else primary
        if selected.get("adapter")=="wikipedia" and selected.get("base_url"):
            try: result=WikipediaSearchProvider(selected["base_url"],self.get_json,self.checked_at).search(query,domains=domains,recency=recency,language=language)
            except Exception as exc: result={"status":"unavailable","results":[],"provider":selected.get("name"),"evidence":[],"checked_at":self.checked_at(),"limitations":[f"Configured MCP fallback failed ({type(exc).__name__}); use host-native search if available."]}
            if host_limits: result.setdefault("limitations",[]).extend(host_limits)
            return result
        return {"status":"unavailable","results":[],"provider":selected.get("name"),"evidence":[],"checked_at":self.checked_at(),
                "limitations":["No callable MCP web-search provider is configured; the Skill should call host-native search directly.",*host_limits]}

    def search(self, query, *, domains=None, recency=None, language="en"):
        return self.research_web(query,domains=domains,recency=recency,language=language)
