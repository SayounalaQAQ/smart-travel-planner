"""Provider configuration and bounded health probes."""
import json
import time
from pathlib import Path


class ProviderRegistry:
    def __init__(self, config_path=None):
        path=Path(config_path) if config_path else Path(__file__).resolve().parents[3]/"config"/"providers.json"
        self.config=json.loads(path.read_text(encoding="utf-8")).get("providers",{})

    def endpoint(self,name,fallback=False):
        item=self.config.get(name,{})
        selected=(item.get("fallback") if fallback else item.get("primary")) or {}
        return selected.get("base_url") or (item.get("fallback") or {}).get("base_url")

    def health(self,get_json):
        out={}
        for name,item in self.config.items():
            primary=item.get("primary") or {}
            fallback=item.get("fallback") or {}
            kind=primary.get("type")
            capability=primary.get("capability") or item.get("capability") or "unknown"
            if kind in {"agent","manual","unavailable"} or not primary:
                checked=False; error=None; latency=None
                if fallback.get("health_check_url"):
                    started=time.monotonic()
                    try: get_json(fallback["health_check_url"],timeout=3,use_cache=False); checked=True
                    except Exception as exc: error=str(exc)[:160]
                    latency=round((time.monotonic()-started)*1000)
                state="degraded" if kind=="agent" or fallback.get("type")=="agent" or checked else "unavailable"
                out[name]={"status":state,"configured":bool(primary.get("base_url") or primary.get("type") in {"agent","manual"}),
                           "reachable":None if kind=="agent" else False,"provider":primary.get("name"),
                           "capability":capability,
                           "fallback_capability":fallback.get("capability"),
                           "primary_runtime":"unknown" if kind=="agent" else None,
                           "fallback":fallback.get("name"),
                           "fallback_reachable":checked if fallback.get("health_check_url") else None,
                           "fallback_runtime":"unknown" if fallback.get("type")=="agent" else None,
                           "latency_ms":latency}
                if error: out[name]["fallback_error"]=error
                continue
            started=time.monotonic(); error=None
            try: get_json(primary.get("health_check_url"),timeout=3,use_cache=False); state="available"
            except Exception as exc: state="unavailable"; error=str(exc)[:160]
            result={"status":state,"configured":bool(primary.get("base_url")),"reachable":state=="available",
                    "provider":primary.get("name"),"requires_key":primary.get("requires_key",False),
                    "capability":capability,
                    "latency_ms":round((time.monotonic()-started)*1000)}
            if error: result["error"]=error
            if state=="unavailable":
                result["fallback"]=fallback.get("name")
                if fallback.get("health_check_url"):
                    fallback_started=time.monotonic()
                    try:
                        get_json(fallback["health_check_url"],timeout=3,use_cache=False)
                        result["fallback_reachable"]=True; result["status"]="degraded"
                    except Exception as exc:
                        result["fallback_reachable"]=False; result["fallback_error"]=str(exc)[:160]
                    result["fallback_latency_ms"]=round((time.monotonic()-fallback_started)*1000)
                elif fallback.get("type")=="agent":
                    result["status"]="degraded"; result["fallback_runtime"]="unknown"
            out[name]=result
        return out
