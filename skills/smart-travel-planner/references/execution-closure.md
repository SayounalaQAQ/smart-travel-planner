# Execution and budget closure (V0.9.1)

Read this policy when turning a researched plan into an execution handbook or
reconsidering a plan after real prices arrive. Keep the existing decision loop,
priority rules, Information Classification and Decision Budget.

## Canonical state and graph

Put user facts in `trip_profile`. Store budget scope (`PER_PERSON`/`PER_PARTY`)
and the separate boolean `airfare_included`. Derive the summary, date window and
compatibility projections through `state_consistency.sync_profile`.
Update canonical facts and graph nodes when revising; never change only visible
date text. Check raw externally supplied state with `validate_state` before
synchronizing if discrepancies should be reported rather than repaired.

Store each day's ordered places in `execution_graph.nodes`; each consecutive
location change requires an edge. Migration input `execution_nodes` is consumed
once. Include airport/flight, station entrances, meal travel, hotel rest returns
and the final hotel/home-airport return. Derive activities, sequence and chain
with `project_graph`. An area is not a resolved hotel property. A route source
describing one station pair cannot resolve an unrelated final mile.

Run `validate_plan_readiness.py`. Report structure, resolved/required coverage
and target-date verification separately. `CURRENT_REFERENCE` and `ESTIMATED`
contribute to resolved coverage, never exact verification. Provider failure is
`UNAVAILABLE`; use `NO_ROUTE_FOUND` only with affirmative evidence. Mark
unresolved service dates/terminals/meals/last-mile points explicitly. Do not
infer airport departure clocks from a generic journey duration.

## Monetary contracts

Use `cost_ledger` with id, category, item, amount, currency, scope, traveler_count,
quantity, cost_type, source, checked_at, confidence and status. PER_NIGHT/RIDE
also require unit_scope; room costs require room_count. Give estimates a stated
basis. A user cap/allocation is USER_BUDGET, excluded from costs. Unknown amounts
stay null, and full total/minimum realistic cost remain unknown if categories
are missing. Report party and per-person totals, known subtotals, unknown
categories and gap independently. Never present a zero known subtotal as a
zero-cost trip.

Select quote ids explicitly. Hotel: exact check-in/out, room type/count, guests,
stock, currency and full-stay party total. Flight: complete round trip, exact
dates, airports, airline, itinerary id, both leg identities/clocks, count, fare
scope and currency. Current/monthly/nearby-date references are not exact quotes.
Nearby dates never replace hard dates without explicit flexibility permission.

## Bounded autonomous closure

Reconcile first. When sourced costs reveal a conflict, execute real searches,
then pass complete candidate plans to `budget_closure_replanning.replan_budget`:
at most 3 rounds, hotel 4 attempts, flight 4 attempts, each route edge 3 attempts.
Research optional expenses, hotel candidates and Minami/Honmachi/Tennoji/Umeda,
then transport delta, meals and flight combinations. Compare total trip cost and
added travel time, not the cheapest room alone. Preserve hard facts, sleep and
walking preferences. Revise only for material utility improvement; record old,
new, trigger, source, reason and impact. If only a cheaper over-cap option is
found, retain it as BEST_FOUND_INFEASIBLE and keep the budget conflict explicit.
Escalate genuine user trade-offs through the existing maximum 3-question P2
budget. If exact quotes cannot be fetched, explain queries/providers/failures,
return NOT_VERIFIABLE for live budget replanning and record a retry checkpoint.
A queue, replay script, mock or synthetic test is never new live research.

## Freshness and delivery

Policy ceilings: flights 6h, hotels 12h, exchange 24h, routes/timetables 7d,
forecast 6h, static attraction data 30d. Earlier provider expiry wins. Expiry
requires refresh and downgrades readiness. Re-evaluate before user confirmation
or booking handoff. READY_FOR_BOOKING requires selected exact fresh quotes,
resolved airports/property, all required edges verified, complete feasible
costs and no state/constraint conflict; planning never performs reservations,
payments or personal-data submission.

Word must show readiness, blockers, missing/estimated/freshness status and
changes, with a public source index. Keep raw ledgers/internal provider output
in JSON. Validate DOCX structure, then attempt a trusted local renderer with
`render_docx_windows.py`. A successful ZIP/XML check is not a pagination review;
without page images and review, visual status stays UNVERIFIED. Live acceptance
must pass `live_evidence_guard` and retain actual raw web responses; unit test
fixtures are excluded from distribution and cannot prove live closure.
