"""Explicit monetary scopes, quote contracts, and conservative budget reconciliation."""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from data_freshness import freshness

COST_TYPES = {"VERIFIED_QUOTE", "CURRENT_REFERENCE", "ESTIMATED", "USER_BUDGET", "UNAVAILABLE"}
SCOPES = {"PER_PERSON", "PER_PARTY", "PER_ROOM", "PER_NIGHT", "PER_RIDE"}
DEFAULT_REQUIRED = {"flight", "hotel", "transit", "food", "attractions", "internet", "insurance", "visa_related", "misc", "emergency"}


def number(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("numeric amount required")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid monetary amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("amount must be finite and nonnegative")
    return amount


def _source(row):
    value = row.get("source_url") or row.get("source")
    return isinstance(value, str) and value.startswith("https://")


def validate_quote(row, kind, profile, *, now=None):
    issues = []
    fresh = freshness(row, "hotel_quote" if kind == "hotel" else "flight_quote", now=now)
    if not _source(row):
        issues.append("QUOTE_SOURCE_MISSING")
    if not row.get("quote_id"):
        issues.append("QUOTE_ID_MISSING")
    if not re.fullmatch(r"[A-Z]{3}", str(row.get("currency", ""))):
        issues.append("QUOTE_CURRENCY_MISSING")
    if kind == "hotel":
        required = ("hotel_name", "check_in", "check_out", "guest_count", "room_count", "room_type", "total_price", "scope")
        for key in required:
            if row.get(key) is None or row.get(key) == "": issues.append(f"HOTEL_{key.upper()}_MISSING")
        if row.get("price_type") != "EXACT_DATE_PRICE" or row.get("availability") != "AVAILABLE":
            issues.append("EXACT_HOTEL_QUOTE_MISSING")
        if row.get("check_in") != profile.get("start_date") or row.get("check_out") != profile.get("end_date"):
            issues.append("HOTEL_DATES_MISMATCH")
        if row.get("guest_count") != profile.get("traveler_count"):
            issues.append("HOTEL_GUEST_COUNT_MISMATCH")
        if profile.get("hotel") and row.get("hotel_name") != profile["hotel"]:
            issues.append("HOTEL_PROPERTY_MISMATCH")
        if row.get("scope") != "PER_PARTY":
            issues.append("HOTEL_STAY_TOTAL_SCOPE_INVALID")
        price = row.get("total_price")
    else:
        required = ("origin_airport", "destination_airport", "outbound_date", "return_date", "airline",
                    "itinerary_id", "departure_time", "arrival_time", "price", "currency", "traveler_count", "scope")
        for key in required:
            if row.get(key) is None or row.get(key) == "": issues.append(f"FLIGHT_{key.upper()}_MISSING")
        if row.get("status") != "EXACT_DATE_QUOTE" or row.get("trip_type") != "ROUND_TRIP":
            issues.append("EXACT_ROUND_TRIP_QUOTE_MISSING")
        if row.get("outbound_date") != profile.get("start_date") or row.get("return_date") != profile.get("end_date"):
            issues.append("FLIGHT_DATES_MISMATCH")
        if row.get("traveler_count") != profile.get("traveler_count"):
            issues.append("FLIGHT_PARTY_COUNT_MISMATCH")
        if row.get("scope") not in {"PER_PERSON", "PER_PARTY"}:
            issues.append("FLIGHT_SCOPE_INVALID")
        legs = row.get("legs", [])
        for direction in ("OUTBOUND", "RETURN"):
            candidates = [leg for leg in legs if leg.get("direction") == direction]
            if not candidates or not all(all(leg.get(k) for k in ("flight_number", "origin_airport", "destination_airport", "date", "departure_time", "arrival_time")) for leg in candidates):
                issues.append(f"{direction}_IDENTITY_OR_CLOCK_MISSING")
            target_date = profile.get("start_date") if direction == "OUTBOUND" else profile.get("end_date")
            if candidates and candidates[0].get("date") != target_date:
                issues.append(f"{direction}_DATE_MISMATCH")
            expected_origin = row.get("origin_airport") if direction == "OUTBOUND" else row.get("destination_airport")
            expected_destination = row.get("destination_airport") if direction == "OUTBOUND" else row.get("origin_airport")
            if candidates and (candidates[0].get("origin_airport") != expected_origin or candidates[-1].get("destination_airport") != expected_destination):
                issues.append(f"{direction}_AIRPORT_MISMATCH")
            if any(a.get("destination_airport") != b.get("origin_airport") for a,b in zip(candidates,candidates[1:])):
                issues.append(f"{direction}_CONNECTION_MISMATCH")
        price = row.get("price")
    try:
        if number(price) <= 0: issues.append("QUOTE_PRICE_INVALID")
        if kind == "hotel" and (not isinstance(row.get("room_count"), int) or row["room_count"] < 1):
            issues.append("HOTEL_ROOM_COUNT_INVALID")
    except (ValueError, TypeError):
        issues.append("QUOTE_PRICE_INVALID")
    if fresh["refresh_required"]:
        issues.append("QUOTE_REFRESH_REQUIRED")
    return {"status": "VERIFIED" if not issues else "EXPIRED" if issues == ["QUOTE_REFRESH_REQUIRED"] else "UNAVAILABLE",
            "issues": sorted(set(issues)), **fresh}


def party_amount(row, traveler_count):
    """No inferred units. PER_NIGHT/RIDE need explicit billing unit and quantity."""
    scope = row.get("scope")
    if scope not in SCOPES: raise ValueError("explicit cost scope required")
    if row.get("traveler_count") != traveler_count: raise ValueError("traveler_count mismatch")
    quantity = number(row.get("quantity"))
    if quantity <= 0: raise ValueError("quantity must be positive")
    amount = number(row.get("amount")) * quantity
    if scope == "PER_PERSON": return amount * traveler_count
    if scope == "PER_PARTY": return amount
    if scope == "PER_ROOM":
        rooms = row.get("room_count")
        if not isinstance(rooms, int) or rooms < 1: raise ValueError("room_count required")
        return amount * rooms
    unit = row.get("unit_scope")
    if unit == "PER_PERSON": return amount * traveler_count
    if unit == "PER_PARTY": return amount
    if unit == "PER_ROOM":
        rooms = row.get("room_count")
        if not isinstance(rooms, int) or rooms < 1: raise ValueError("room_count required")
        return amount * rooms
    raise ValueError("PER_NIGHT/PER_RIDE require explicit unit_scope")


def budget_limit(profile):
    value = profile.get("budget_amount")
    scope = str(profile.get("budget_scope", ""))
    count = profile.get("traveler_count")
    if not isinstance(count, int) or count < 1: raise ValueError("positive traveler_count required")
    amount = number(value)
    if scope == "PER_PERSON" or scope.lower().startswith("per person"):
        return amount * count, amount
    if scope == "PER_PARTY" or scope.lower().startswith("party"):
        return amount, amount/count
    raise ValueError("budget scope must explicitly be PER_PERSON or PER_PARTY")


def reconcile_budget(profile, ledger, quotes=None, exchange_rates=None, *, now=None):
    quotes, exchange_rates = quotes or {}, exchange_rates or []
    currency = profile.get("budget_currency")
    count = profile.get("traveler_count")
    rows, issues, unknown = [], [], set()
    default_required={'transit','hotel','food','attractions','misc','emergency'} if profile.get('intercity_mode')=='TRAIN' and profile.get('domestic_trip') is True else DEFAULT_REQUIRED
    required = set(profile.get("budget_categories", default_required))
    present = {r.get("category") for r in ledger if r.get("cost_type") != "USER_BUDGET" and r.get("optional_excluded") is not True}
    unknown.update(required - present)
    try:
        cap_party, cap_person = budget_limit(profile)
    except ValueError as exc:
        cap_party = cap_person = None; issues.append(str(exc))
    sums = {key: Decimal(0) for key in ("verified", "estimated", "known_min", "known_max")}
    ids = set()
    for original in ledger:
        row = dict(original); category = row.get("category") or "uncategorized"
        row["errors"] = []
        if not row.get("id") or row["id"] in ids: row["errors"].append("MISSING_OR_DUPLICATE_COST_ID")
        ids.add(row.get("id"))
        kind = row.get("cost_type")
        if kind not in COST_TYPES: row["errors"].append("INVALID_COST_TYPE")
        if row.get("scope") not in SCOPES: row["errors"].append("EXPLICIT_COST_SCOPE_REQUIRED")
        if row.get("traveler_count") != count: row["errors"].append("COST_PARTY_COUNT_MISMATCH")
        try:
            if number(row.get("quantity")) <= 0: row["errors"].append("POSITIVE_QUANTITY_REQUIRED")
        except ValueError:
            row["errors"].append("POSITIVE_QUANTITY_REQUIRED")
        if row["errors"]:
            issues.append({"cost_id": row.get("id"), "issues": row["errors"]})
            unknown.add(category)
            row.update(status="UNAVAILABLE", party_total=None, per_person_total=None)
            rows.append(row); continue
        if kind == "USER_BUDGET" or row.get("optional_excluded") is True:
            row["party_total"] = row["per_person_total"] = None
            row["status"] = "EXCLUDED_FROM_COST"
            rows.append(row); continue
        if kind == "UNAVAILABLE" or row.get("amount") is None:
            unknown.add(category); row.update(status="UNAVAILABLE", party_total=None, per_person_total=None)
            rows.append(row); continue
        try:
            total = party_amount(row, count)
            if not row.get("currency"): raise ValueError("currency required")
            if not _source(row) or not row.get("checked_at"): raise ValueError("cost provenance required")
            if kind == "ESTIMATED" and not row.get("estimation_basis"): raise ValueError("estimate basis required")
            if kind == "CURRENT_REFERENCE" and category == "transit" and freshness(row, "train_timetable", now=now)["refresh_required"]:
                unknown.add(category)
                row.update(status="EXPIRED", party_total=None, per_person_total=None, refresh_required=True)
                rows.append(row); continue
            if kind == "VERIFIED_QUOTE":
                quote = quotes.get(row.get("quote_id"))
                if not quote or category not in {"hotel", "flight"}: raise ValueError("verified cost requires a linked complete hotel/flight quote")
                contract = validate_quote(quote, category, profile, now=now)
                row["quote_validation"] = contract
                if contract["status"] == "EXPIRED":
                    unknown.add(category)
                    row.update(status="EXPIRED", party_total=None, per_person_total=None, refresh_required=True)
                    rows.append(row)
                    continue
                if contract["status"] != "VERIFIED": raise ValueError("quote incomplete, mismatched, or expired")
                quote_value = quote.get("total_price") if category == "hotel" else quote.get("price")
                if number(row["amount"]) != number(quote_value) or row["currency"] != quote["currency"] or row["scope"] != quote["scope"] or row["quantity"] != 1:
                    raise ValueError("cost and quote amount/currency/scope/quantity mismatch")
            converted_kind = kind
            if row["currency"] != currency:
                rate = next((r for r in exchange_rates if r.get("base_currency") == row["currency"] and r.get("quote_currency") == currency and _source(r) and not freshness(r, "exchange", now=now)["refresh_required"]), None)
                if not rate: raise ValueError("fresh sourced exchange rate required")
                total *= number(rate["rate"])
                row["exchange_evidence"] = dict(rate)
                # A future currency spend converted at today's rate is a reference.
                converted_kind = "CURRENT_REFERENCE"
            minimum = total
            maximum = total
            if row.get("min_amount") is not None or row.get("max_amount") is not None:
                factor = total/number(row["amount"]) if number(row["amount"]) else Decimal(1)
                minimum = number(row.get("min_amount", row["amount"]))*factor
                maximum = number(row.get("max_amount", row["amount"]))*factor
                if minimum > total or maximum < total: raise ValueError("range does not contain amount")
            sums["verified" if converted_kind == "VERIFIED_QUOTE" else "estimated"] += total
            sums["known_min"] += minimum; sums["known_max"] += maximum
            row.update(status="ACCOUNTED", party_total=round(float(total), 2), per_person_total=round(float(total/count), 2), calculation_currency=currency, calculation_type=converted_kind)
        except (ValueError, TypeError, ZeroDivisionError) as exc:
            row["errors"].append(str(exc)); unknown.add(category)
            row.update(status="UNAVAILABLE", party_total=None, per_person_total=None)
        if row["errors"]: issues.append({"cost_id": row.get("id"), "issues": row["errors"]})
        rows.append(row)
    known = sums["verified"] + sums["estimated"]
    complete = not unknown and not issues and bool(rows)
    if cap_party is not None and sums["known_min"] > cap_party:
        feasibility = "INFEASIBLE"
    elif not complete or cap_party is None:
        feasibility = "UNVERIFIED"
    elif sums["known_max"] > cap_party:
        feasibility = "UNVERIFIED"
    else:
        feasibility = "NEAR_LIMIT" if sums["known_max"] >= cap_party*Decimal("0.95") else "FEASIBLE"
    gap = (sums["known_min"] - cap_party)/count if feasibility == "INFEASIBLE" else (known-cap_party)/count if complete and cap_party is not None else None
    return {"currency": currency, "traveler_count": count,
            "user_budget_limit_party": float(cap_party) if cap_party is not None else None,
            "user_budget_limit_per_person": float(cap_person) if cap_person is not None else None,
            "verified_cost_party": round(float(sums["verified"]), 2),
            "verified_cost_per_person": round(float(sums["verified"]/count), 2) if count else None,
            "estimated_cost_party": round(float(sums["estimated"]), 2),
            "estimated_cost_per_person": round(float(sums["estimated"]/count), 2) if count else None,
            "minimum_known_cost_party": round(float(sums["known_min"]), 2),
            "maximum_known_cost_party": round(float(sums["known_max"]), 2),
            "minimum_known_cost_per_person": round(float(sums["known_min"]/count), 2) if count else None,
            "maximum_known_cost_per_person": round(float(sums["known_max"]/count), 2) if count else None,
            "party_total": round(float(known), 2) if complete else None,
            "per_person_total": round(float(known/count), 2) if complete else None,
            "known_subtotal_party": round(float(known), 2),
            "unknown_cost_categories": sorted(unknown), "unknown_cost": None,
            "budget_gap_per_person": round(float(gap), 2) if gap is not None else None,
            "gap_is_lower_bound": bool(unknown and gap is not None), "feasibility": feasibility,
            "closure_status": "PASS" if complete else "PARTIAL", "issues": issues, "rows": rows,
            "replanning_required": feasibility == "INFEASIBLE",
            "budget_basis": "verified quotes + dated references/estimates; USER_BUDGET excluded"}
