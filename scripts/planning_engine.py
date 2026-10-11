"""Small deterministic decision helpers. They rank supplied evidence; they never invent it."""
from math import asin, cos, radians, sin, sqrt


def _distance_km(a, b):
    lat1, lon1 = a; lat2, lon2 = b
    dlat=radians(lat2-lat1); dlon=radians(lon2-lon1)
    h=sin(dlat/2)**2+cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 6371*2*asin(sqrt(h))


def compare_destinations(candidates, priorities=None):
    """Score only caller-supplied comparison factors; absent values remain unknown."""
    priorities=priorities or {}
    weights={"budget_fit":.22,"season_fit":.16,"transport_fit":.14,"attraction_density":.12,
             "interest_match":.18,"pace_fit":.10,"risk_fit":.08}
    ranked=[]
    for item in candidates:
        factors=item.get("factors",{})
        known=[(k,w,float(factors[k])) for k,w in weights.items() if isinstance(factors.get(k),(int,float))]
        if not known:
            score=None
        else:
            denom=sum(w for k,w,v in known)
            score=round(sum(w*max(0,min(1,v)) for k,w,v in known)/denom*100,1)
        ranked.append({**item,"score":score,"known_factor_count":len(known),
                       "why_recommend":item.get("why_recommend") or "; ".join(f"{k}={v}" for k,w,v in known),
                       "why_not_recommend":item.get("why_not_recommend") or "需要逐项核验未提供的城市条件"})
    return sorted(ranked,key=lambda x:(x["score"] is None,-(x["score"] or 0)))


def select_attractions(candidates, profile, *, attraction_budget=None):
    """Return selected and omitted POIs using explicit constraints and available evidence."""
    interests={str(x).casefold() for x in profile.get("interests",[])}
    step_cap=profile.get("walking_tolerance_steps")
    scored=[]
    for item in candidates:
        reasons=[]; score=0
        from experience_discovery import experience_match
        match=experience_match(profile,item)
        if not match['allowed']:
            scored.append({**item,'score':-100,'decision_reasons':match['reasons']});continue
        score+=match['score'];reasons.extend(match['reasons'])
        tags={str(x).casefold() for x in item.get("interest_tags",[])}
        if interests & tags: score+=4; reasons.append("符合兴趣")
        if item.get("coordinates") and item.get("source_url"): score+=2; reasons.append("位置与来源可追溯")
        elif item.get("coordinates"): score-=6; reasons.append("缺少可追溯来源，不进入正式行程")
        elif item.get("source_url"): score-=3; reasons.append("缺少地点坐标，暂不能验证区域路线")
        else: score-=8; reasons.append("缺少地点和来源证据，不进入正式行程")
        cost=item.get("estimated_cost")
        if cost is None: reasons.append("费用未知")
        elif attraction_budget is not None and cost > attraction_budget: score-=100; reasons.append("超出景点预算")
        else: score+=1; reasons.append("符合景点预算")
        steps=item.get("estimated_steps")
        if step_cap and steps is not None and steps>step_cap: score-=100; reasons.append("超过每日步数上限")
        if item.get("reservation_required") is True and not item.get("reservation_source_url"):
            score-=2; reasons.append("预约条件缺少来源")
        scored.append({**item,"score":score,"reason":"；".join(reasons),"benefit":item.get("main_highlights"),
                       "risk":item.get("risk") or ("预约需核验" if item.get("reservation_required") is None else None),
                       "recommended_time":item.get("recommended_time"),"alternative":item.get("alternative")})
    selected=[x for x in scored if x["score"]>0]
    omitted=[{**x,"why_not":"；".join(part for part in (x.get("reason"),x.get("risk")) if part)} for x in scored if x["score"]<=0]
    return {"selected":selected,"omitted":omitted}


def optimize_route_order(stops, start, *, walking_limit_steps=None):
    """Nearest-next geography order; never returns time estimates or missing coordinates as fact."""
    remaining=list(stops); route=[]; current=start
    while remaining and current and len(current)==2:
        candidates=[x for x in remaining if isinstance(x.get("coordinates"),dict)
                    and isinstance(x["coordinates"].get("latitude"),(int,float))
                    and isinstance(x["coordinates"].get("longitude"),(int,float))]
        if not candidates: break
        nxt=min(candidates,key=lambda x:_distance_km(current,(x["coordinates"]["latitude"],x["coordinates"]["longitude"])))
        route.append(nxt); remaining.remove(nxt)
        current=(nxt["coordinates"]["latitude"],nxt["coordinates"]["longitude"])
    route.extend(remaining)
    steps=sum(int(x.get("estimated_steps") or 0) for x in route)
    return {"stops":route,"estimated_steps":steps if any(x.get("estimated_steps") is not None for x in route) else None,
            "walking_limit_steps":walking_limit_steps,"within_step_limit":None if not walking_limit_steps or not any(x.get("estimated_steps") is not None for x in route) else steps<=walking_limit_steps,
            "duration_status":"unavailable unless backed by route provider evidence"}


def weather_alternatives(outdoor_stops, indoor_candidates, *, extreme_candidates=None):
    """Map weather replacements by shared interest/category and explicit source-backed records."""
    indoor_candidates=indoor_candidates or []; extreme_candidates=extreme_candidates or []
    plans=[]
    for stop in outdoor_stops:
        tags={str(x).casefold() for x in stop.get("interest_tags",[])}
        def match(options):
            eligible=[x for x in options if x.get("source_url") and x.get("opening_hours") is not None]
            return max(eligible,key=lambda x:len(tags & {str(t).casefold() for t in x.get("interest_tags",[])}),default=None)
        plans.append({"outdoor":stop.get("name"),"sunny":stop.get("name"),"rain_alternative":match(indoor_candidates),
                      "extreme_weather_alternative":match(extreme_candidates),
                      "rain_status":"mapped" if match(indoor_candidates) else "unavailable",
                      "extreme_status":"mapped" if match(extreme_candidates) else "unavailable"})
    return plans
