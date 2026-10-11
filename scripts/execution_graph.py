"""Ordered itinerary is canonical; every consecutive location change needs an edge.

Unknown endpoints never gain measured times from an area-level reference.
Legacy route fragments are matched by exact location identity only.
"""
from copy import deepcopy
from data_freshness import freshness

ROUTE_STATUSES = {"VERIFIED", "ESTIMATED", "CURRENT_REFERENCE", "COMPOSITE_REFERENCE", "UNAVAILABLE", "NO_ROUTE_FOUND"}
MODES = {"WALK", "METRO", "TRAIN", "BUS", "TAXI", "FLIGHT", "DRIVING", "UNAVAILABLE"}
MAX_ROUTE_PROVIDER_RETRIES = 3


def _node(node_id, role, place, place_id, *, resolved=False, **extra):
    return {"id": node_id, "role": role, "place": place, "place_id": place_id,
            "location_status": "RESOLVED" if resolved else "UNRESOLVED", **extra}


def required_pairs(nodes):
    return [(a, b) for a, b in zip(nodes, nodes[1:]) if a.get("place_id") != b.get("place_id")]


def route_evidence_valid(edge, nodes, *, now=None, strict=False):
    if edge.get("status") not in {"VERIFIED", "ESTIMATED", "CURRENT_REFERENCE", "COMPOSITE_REFERENCE"}:
        return False
    start, end = nodes.get(edge.get("from_node")), nodes.get(edge.get("to_node"))
    if not start or not end or any(n.get("location_status") != "RESOLVED" for n in (start, end)):
        return False
    if edge.get("mode") not in MODES - {"UNAVAILABLE"}:
        return False
    if edge.get('status') == 'COMPOSITE_REFERENCE':
        parts=edge.get('components',[])
        if strict or not parts or edge.get('duration_minutes') is not None or not edge.get('unknown_overhead'):
            return False
        at=edge.get('from_place_id')
        known=0
        for part in parts:
            if part.get('from_place_id')!=at or not part.get('boundary') or not part.get('source_url') or freshness(part,'route',now=now)['refresh_required']:
                return False
            if part.get('mode') not in MODES-{'UNAVAILABLE'}: return False
            minutes=part.get('duration_minutes')
            if minutes is not None:
                if not isinstance(minutes,(int,float)) or isinstance(minutes,bool) or minutes<0: return False
                known+=minutes
            at=part.get('to_place_id')
        return at==edge.get('to_place_id') and edge.get('known_component_minutes')==known and edge.get('duration_complete') is False
    duration = edge.get("duration_minutes")
    source = edge.get("source_url") or edge.get("source")
    if not isinstance(duration, (float, int)) or isinstance(duration, bool) or duration < 0 or not source:
        return False
    if not edge.get("checked_at"):
        return False
    if edge.get('status') == 'ESTIMATED' and not edge.get('estimation_basis'):
        return False
    if freshness(edge, "route", now=now)["refresh_required"]:
        return False
    if edge["mode"] != "WALK" and not (edge.get("operator") and edge.get("line")):
        return False
    if strict:
        if edge.get("status") != "VERIFIED" or freshness(edge, "route", now=now)["refresh_required"]:
            return False
        if edge.get("critical"):
            if edge.get("applicable_date") != edge.get("travel_date"):
                return False
            if edge["mode"] == "FLIGHT" and not edge.get("quote_id"):
                return False
            if edge.get("purpose") == "airport_transfer" and not all(
                edge.get(k) for k in ("departure_time", "arrival_time", "check_in_deadline", "buffer_minutes")):
                return False
    return True


def build_execution_graph(profile, day, index=0):
    """Migrate once. Subsequently graph nodes/edges are authoritative, not projections."""
    if day.get("execution_graph"):
        return deepcopy(day["execution_graph"])
    prefix = f"day-{index + 1}"
    hotel = profile.get("hotel") or profile.get("lodging_location") or profile.get("lodging_area") or "HOTEL_UNRESOLVED"
    hotel_resolved = bool(profile.get("hotel") and profile.get("hotel_address"))
    nodes = []
    def add(role, place, place_id, resolved=False, **extra):
        nodes.append(_node(f"{prefix}-node-{len(nodes)+1}", role, place, place_id, resolved=resolved, **extra))
    arrival = day.get("day_type") == "ARRIVAL" or (index == 0 and day.get("date") == profile.get("start_date"))
    departure = day.get("day_type") == "DEPARTURE" or (day.get("date") and day.get("date") == profile.get("end_date"))
    rail = profile.get('intercity_mode') == 'TRAIN'
    terminal = 'STATION' if rail else 'AIRPORT'
    suffix = 'station' if rail else 'airport'
    if arrival:
        for side in ('origin', 'arrival'):
            value = profile.get(side+'_'+suffix)
            add(terminal, value or terminal+'_UNRESOLVED', side+'-'+suffix, bool(value))
    add("HOTEL", hotel, "hotel", hotel_resolved)
    for item in day.get("itinerary_nodes", day.get("activities", [])):
        item = deepcopy(item) if isinstance(item, dict) else {"activity": str(item)}
        role = item.pop("role", "ACTIVITY")
        place = item.pop("place", None) or item.pop("location", None)
        location_known = bool(place)
        place = place or item.get("activity") or "ACTIVITY_LOCATION_UNRESOLVED"
        place_id = item.pop("place_id", None) or f"activity-location-{len(nodes)+1}"
        if role in {"HOTEL", "REST"} and place_id == "hotel":
            place, location_known = hotel, hotel_resolved
        item.pop("id", None)
        status = item.pop("location_status", "RESOLVED" if location_known else "UNRESOLVED")
        add(role, place, place_id, status == "RESOLVED", **item)
    if departure:
        for side in ('departure', 'return'):
            value = profile.get(side+'_'+suffix) or (profile.get('origin_'+suffix) if side=='return' else None)
            add(terminal, value or terminal+'_UNRESOLVED', side+'-'+suffix, bool(value))
    elif nodes[-1].get("place_id") != "hotel":
        add("HOTEL", hotel, "hotel", hotel_resolved)
    if "execution_nodes" in day:
        # Agent-authored explicit migration input may include intermediate stations.
        # It is consumed once; the resulting graph is the persistent source of truth.
        nodes = []
        for item in day["execution_nodes"]:
            item = deepcopy(item)
            role, place, place_id = item.pop("role"), item.pop("place"), item.pop("place_id")
            resolved = item.pop("location_status", "UNRESOLVED") == "RESOLVED"
            add(role, place, place_id, resolved, **item)
    records = day.get("route_evidence", [])
    edges = []
    for start, end in required_pairs(nodes):
        evidence = next((deepcopy(r) for r in records if r.get("from_place_id") == start["place_id"] and r.get("to_place_id") == end["place_id"]), {})
        airport = start["role"] == "AIRPORT" or end["role"] == "AIRPORT"
        flight = start["role"] == end["role"] == "AIRPORT"
        rail_intercity = rail and start['role'] == end['role'] == 'STATION' and (
            start['place_id'] in {'home','origin-station'} or end['place_id'] in {'return','return-station'})
        purpose = evidence.get("purpose") or ("flight" if flight else "airport_transfer" if airport else "cross_city" if evidence.get("cross_city") or rail_intercity else "local")
        critical = airport or purpose in {"flight", "airport_transfer", "cross_city"}
        edge = {"id": f"{start['id']}--{end['id']}", "from_node": start["id"], "to_node": end["id"],
                "from_place_id": start["place_id"], "to_place_id": end["place_id"],
                "mode": "UNAVAILABLE", "status": "UNAVAILABLE", "duration_minutes": None,
                "fare": None, "currency": None, "source_url": None, "checked_at": None,
                "operator": None, "line": None, "purpose": purpose, "critical": critical,
                "travel_date": day.get("date"), "failure_reason": "No endpoint-specific route evidence", **evidence}
        # Generated identity cannot be replaced by untrusted provider data.
        edge.update({"id": f"{start['id']}--{end['id']}", "from_node": start["id"], "to_node": end["id"],
                     "from_place_id": start["place_id"], "to_place_id": end["place_id"], "travel_date": day.get("date"),
                     "critical": critical, "purpose": purpose})
        if evidence:
            edge.pop("failure_reason", None)
        if any(n["location_status"] != "RESOLVED" for n in (start, end)):
            edge.update(status="UNAVAILABLE", mode="UNAVAILABLE", duration_minutes=None, fare=None,
                        failure_reason="Endpoint unresolved; area reference is not a property route")
        edges.append(edge)
    return {"date": day.get("date"), "nodes": nodes, "edges": edges,
            "source_of_truth": "ordered execution_graph.nodes"}


def route_closure(graph, *, now=None):
    nodes = graph.get("nodes", [])
    lookup = {node.get("id"): node for node in nodes}
    issues = []
    if not nodes or len(lookup) != len(nodes) or None in lookup:
        issues.append("NODE_ID_OR_EMPTY_GRAPH")
    expected = {(a.get("id"), b.get("id")) for a, b in required_pairs(nodes)}
    actual = [(edge.get("from_node"), edge.get("to_node")) for edge in graph.get("edges", [])]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        issues.append("EDGE_COVERAGE_MISMATCH")
    resolved = verified = 0
    weight = 0.0
    unresolved = []
    for edge in graph.get("edges", []):
        a, b = lookup.get(edge.get("from_node")), lookup.get(edge.get("to_node"))
        if a and b and (edge.get("from_place_id") != a.get("place_id") or edge.get("to_place_id") != b.get("place_id")):
            issues.append("EDGE_ENDPOINT_IDENTITY_MISMATCH")
        if edge.get("status") not in ROUTE_STATUSES:
            issues.append("INVALID_EDGE_STATUS")
        valid = route_evidence_valid(edge, lookup, now=now)
        exact = route_evidence_valid(edge, lookup, now=now, strict=True)
        resolved += int(valid)
        verified += int(exact)
        if valid:
            weight += {"VERIFIED": 1, "ESTIMATED": .5, "CURRENT_REFERENCE": .25, "COMPOSITE_REFERENCE": .25}[edge["status"]]
        if not exact:
            unresolved.append({"edge_id": edge.get("id"), "critical": edge.get("critical", False),
                               "status": edge.get("status"), "reason": edge.get("failure_reason") or "Target-date route verification pending"})
    count = len(expected)
    # All declared location changes must be present; absence cannot inflate coverage.
    status = "COMPLETE" if not issues else "INCOMPLETE"
    return {"route_structure_status": status, "required_edges": count,
            "resolved_edges": resolved, "verified_edges": verified,
            "route_coverage": round(resolved/count, 4) if count else 0.0,
            "evidence_weighted_coverage": round(weight/count, 4) if count else 0.0,
            "route_verification_status": "EXECUTION_VERIFIED" if count and verified == count and not issues else "PARTIAL" if resolved else "UNAVAILABLE",
            "unresolved_edges": unresolved, "issues": issues}


def route_retry_plan(graph, *, max_attempts=MAX_ROUTE_PROVIDER_RETRIES):
    if not 1 <= max_attempts <= MAX_ROUTE_PROVIDER_RETRIES:
        raise ValueError("route retries must be 1..3")
    lookup = {n["id"]: n for n in graph["nodes"]}
    result = []
    for edge in graph["edges"]:
        if edge["status"] in {"UNAVAILABLE", "NO_ROUTE_FOUND"}:
            result.append({"edge_id": edge["id"], "from": lookup[edge["from_node"]]["place"],
                           "to": lookup[edge["to_node"]]["place"], "date": graph.get("date"),
                           "max_attempts": max_attempts, "status": "PENDING",
                           "providers": ["configured_route_provider", "official_operator", "host_web_search"][:max_attempts]})
    return result


def record_route_attempts(graph, edge_id, attempts):
    if not 1 <= len(attempts) <= MAX_ROUTE_PROVIDER_RETRIES:
        raise ValueError("executed route attempts must be 1..3")
    edge = next(e for e in graph["edges"] if e["id"] == edge_id)
    for row in attempts:
        if row.get("executed") is not True or not all(row.get(k) for k in ("provider", "query", "checked_at", "result_status")):
            raise ValueError("missing executed provider/query/time/status audit")
    edge["search_attempts"] = deepcopy(attempts)
    # Provider failure is not proof that no service exists.
    if all(a["result_status"] != "FOUND" for a in attempts):
        edge.update(status="UNAVAILABLE", failure_reason=attempts[-1].get("failure_reason", "No reliable result returned"))


def project_graph(day):
    """Produce compatibility views from the graph; never maintain three independent lists."""
    graph = day["execution_graph"]
    lookup = {n["id"]: n for n in graph["nodes"]}
    day["activities"] = [{"node_id":n['id'],"node_role":n['role'], **{k: deepcopy(v) for k, v in n.items() if k not in {"id", "role", "place_id", "location_status"}}}
                         for n in graph["nodes"] if n["role"] in {"ACTIVITY", "MEAL", "REST"}]
    day["route_sequence"] = [{"node_id": n["id"], "type": n["role"], "place": n["place"]} for n in graph["nodes"]]
    day["route_chain"] = [{**deepcopy(e), "from": lookup.get(e["from_node"], {}).get("place"),
                           "to": lookup.get(e["to_node"], {}).get("place")} for e in graph["edges"]]
    day["route_origin"] = graph["nodes"][0]["place"] if graph["nodes"] else None
    day["route_state"] = "ROUTE_PENDING" if any(e["status"] == "UNAVAILABLE" for e in graph["edges"]) else "AREA_LEVEL_ANCHOR"
    day.pop("itinerary_nodes", None)
    day.pop("execution_nodes", None)
