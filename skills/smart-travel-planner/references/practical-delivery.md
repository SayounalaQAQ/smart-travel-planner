# Practical merchant and route input

Small delivery-boundary mapping; preserve the existing research/decision/execution/cost engines.

## Merchant candidates

Use hotel_candidates / restaurant_candidates: id, exact name/branch, address, source_url, checked_at, field_evidence. Every field evidence is an object with value/source_url/checked_at from an actually read page. Record route_fit, route_fit_reason, why_recommended, drawbacks, price_reference, opening_hours and selected. Compare geography, interests/party, facilities and available independent recent review samples, not search ranking. Promotional pages support identity/advertised food, not consumer satisfaction. Missing prices/review dates/volume/negative-pattern evidence stay unknown.

compare_merchants scores only evidence-backed preference facts; scores are internal aids. Save evaluations and actual selection rationale, including slot-specific restaurant decisions. No cheapest/best/available claim without comparable evidence. Selected hotel populates profile hotel/address. A selected restaurant requires a matching daily MEAL node; markets remain area suggestions.

Selected planning_cost: amount/currency/scope/quantity/cost_type/source_url/checked_at; ESTIMATED needs estimation_basis. Hotel PER_NIGHT also needs unit_scope=PER_ROOM and room_count. CURRENT_REFERENCE requires an actually read price and units. A budget allowance remains ESTIMATED even when identity is official. Stable merchant cost IDs enter the existing ledger exactly once. Recommended allocations must cover declared amounts; alternate tiers may use different stated assumptions. No booking-ready claim follows from allowances.

## Geography and travel days

Declare daily start_anchor / overnight_anchor objects with place_id, place, role, location_status and status. They describe actual planned nightly endpoints, distinct from lodging-area candidates and never imply a reservation. Next-day first node must be the previous night anchor, followed by any actual transfer. For night trains/flights use NIGHT_TRANSIT/terminal anchors; do not inject a city hotel. Explicit execution_nodes are authoritative. A transport vehicle or arrival summary is not another ACTIVITY after the terminal journey. A vague overnight REST requires a declared anchor before standard delivery.

Each required graph edge links cost_id to the existing cost_ledger. A round-trip/pass can cover several edges only with explicit covers_edge_ids and must be counted once. Separate intercity_rail, station_transfer, airport_transfer, charter_transfer, rental_car and transit; any absent amount stays UNAVAILABLE/UNKNOWN. Allocation sums do not prove cost coverage. All tiers of the same route must cover known necessary transport; a cheaper mode needs its own explicit route/cost evidence. required_cost_coverage and lodging_continuity are developer-report checks, not proof that unknown logistics work.

TRAIN uses intercity_fare_included, separate from airfare_included. Explicit budget-note scope can map the field; an absent railway scope must remain unknown, never inferred solely from a flight flag. Keep near-date references separate from exact-date tickets. Do not fabricate a timetable to connect a cross-station journey.

For seasonal overnight anchors set seasonal=true and retain operational_evidence for operating, heating, hot_water and return_transfer. Advertised heating is not target-date operation. Missing conditions retain NOT_READY and a sourced alternative, not automatic payments/calls. For departures within seven days the actual clock raises ticket/transfer, nightly lodging, ground transport, weather/booking actions first. Missing prices still permit a qualified initial handbook.

## Public content types

Tourist prose uses strings, lists of strings/objects or objects with public fields: risk/mitigation; decision/reason/tradeoff/evidence_ids; when/item/note; name/description/alternative. Nested public values are rendered with Chinese labels; private IDs, unknown metadata and repr(dict/list) are omitted. Plain entity name/address/date/price units remain typed scalar fields. Unsupported content should be repaired, not serialized into Word. The final validator reports PUBLIC_DATA_STRUCTURE_LEAK/PUBLIC_ENUM_LEAK and the actual section. Empty advice/source-time labels are omitted or clearly marked unverified.

place_registry holds id/name/aliases/city/district/address/source_url/checked_at. Refer to place_id; conflicting city/district/address is rejected, not silently corrected.

Use ordered execution_nodes with role/place/place_id/location_status/time/note and optional end_time. Existing execution graph consumes these once. Arrival: origin-airport, arrival-airport, destination hotel. Rail uses origin-station/arrival-station. Flight text is not an attraction. Hotel/meal/activity/terminal order must match daily activities. Departure: safe sightseeing, hotel luggage, departure terminal, return terminal. Unresolved evidence never yields precise routes.

Day return_constraint: departure_time HH:MM, airport_buffer_minutes, transfer_allowance_minutes, luggage_minutes, source_url, clock_type. Calculate latest sightseeing finish. Target-date evidence is preferable; reference clocks must be PLANNING_ASSUMPTION, conditional on the real flight. Earlier flight means remove activities, never silently reduce buffers. Ground allowances are not measured journey times. Storm-related marine closure must not send travelers to another affected island.

Hard errors: ARRIVAL_DIRECTION_CONFLICT, TRAVEL_DAY_NODES_REQUIRED, GEOGRAPHIC_ENTITY_CONFLICT, RETURN_BUFFER_CONFLICT, SELECTED_MEAL_NOT_ROUTED, MERCHANT_BUDGET_CONFLICT. Correct data and rerun the same standard entry.

## Tourist Word

Short trips use compact cover/TOC, Chinese profile/budget labels, small hotel comparison, selected core cards, bound photos/direct references and daily tables. Unselected alternatives are brief; empty food headings are omitted. Generator command/hash, coverage and validation stay in separate reports. Preliminary status and actionable unknowns remain visible.
