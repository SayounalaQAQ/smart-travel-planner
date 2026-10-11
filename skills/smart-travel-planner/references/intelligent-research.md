# Intelligent research and practical completion · V0.9.3

Use the existing orchestrator file protocol in autonomous-research.md. The host must actually search/open and inspect entities, dates, branches and route boundaries. Scripts cannot acquire a host tool merely by naming it.

## Before a query

`semantic_query_planner.py` resolves entity, location, information need, language, preferred source and date scope. A route with unresolved endpoints is blocked until place discovery succeeds. A meal task searches one actual destination district, not an entire daily route. Exact inventory queries require dates and party/room scope. Reject placeholders, internal enums and unrelated keywords. Do not bypass the gate to spend remaining quota.

`research_value_optimizer.py` uses transparent configurable heuristics, not probabilities. Weights are in config/defaults.json. Prioritize reusable access facts, actual plan nodes and useful public prices. Keep caps at 4 rounds / 64 queries / 96 source assignments. A source assignment can reuse a capture; report actual network opens separately.

Deduplicate queries for 6 hours and positive pages for at most 7 days; negative page errors expire after 30 minutes. Inventory breakers pause only an entity type/provider class after 2 relevant failures, for 6 hours. Record the actually observed failure class, not an invented provider outage. Alternative classes may continue; new capability or expiration permits refresh.

## From new evidence to a choice

For major local moves, try direct walk and public/composite transit. Preserve the exact endpoints: a district is not a bridge, a station concourse is not an exit. No straight-line distance as road distance, no in-vehicle minutes as door-to-door time. Candidate paths have their own source IDs, walking components, fare, transfers, waiting and unknown boundaries. Unknown cost/time is not zero. Reverse walking is an explicit assumption.

`decision_backfill.py` compares paths and researched lunch alternatives. Keep provisional status while daily steps, fare or access is incomplete. A meaningful route mode/path revision enters decision_revision_ledger with old/new/evidence/reason/impact. Retain a previously selected candidate when its score is within 10% of the best. Do not count new labels, IDs, source refreshes or unknown-to-reference status as a major decision change.

Restaurant options require branch/area and hours proof; menu item price is not a whole meal. A dinner-only shop is rejected for lunch. A same-address inference must disclose floor/access uncertainty. Backups are optional substitutions, not required extra stops. Changed places invalidate incident routes and trigger endpoint research.

After backfill, the established evaluator recalculates graph projections, cost, constraints and QA. Findings create targeted_replanning_tasks; run existing bounded replanning for a material constraint conflict. Hard dates/budget/walking constraints remain protected. Never move the start earlier for a photographic best time. Escalate only a remaining material subjective tradeoff, within the existing Decision Budget. No payment, booking or personal-data submission is authorized.

## Budget and stopping

`reference_budget_estimator.py` keeps exact booking cost, evidence item ranges and budget allocations separate. Retain native currency, item/party scope, source, checked date and limits. Other-date fare references never populate verified cost or trigger a real budget conflict. Complete scenario totals remain null unless supported quantities and all mandatory categories exist. Do not invent a lowest realistic budget.

Stop reasons: ALL_HIGH_VALUE_GAPS_RESOLVED, GLOBAL_BUDGET_EXHAUSTED, PROVIDER_CLASS_BLOCKED, DIMINISHING_RETURNS, NO_AVAILABLE_CAPABILITY. Low recent yield alone must not stop available high-value tasks. Never describe an unattempted gap as provider failure.

## Deliverables

Generate JSON plus the user handbook with the existing builder. Daily cards explain time, sequence, movements and missing components, meals, item prices, walking limitations, rain alternative and sources. Keep technical enums, raw captures, attempts and scores in acceptance artifacts. Preserve licensed real images and attribution. A route schematic must be explicitly illustrative and never pretend to be a verified map.

PRACTICAL_PLAN_READINESS is independent from BOOKING_READINESS. Unverified daily walking/routes/meals may leave practical readiness PARTIAL even with useful research. Structural DOCX QA is separate from visual rendering; when no renderer is available, mark visual QA UNVERIFIED. A real decision PASS requires new live evidence changing an actual previous choice, with graph update and QA rerun; unit fixtures never suffice.
