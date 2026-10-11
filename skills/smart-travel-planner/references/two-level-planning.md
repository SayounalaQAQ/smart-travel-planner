# Two-level planning

## Level 1 — Provisional plan

Start when user-required facts are sufficient for meaningful destination research. Use an `AREA_LEVEL_ANCHOR` such as the destination center, a researched lodging neighborhood, or a user-preferred area. A specific property, room, flight, attraction list, or transit ticket is not required. Research and propose lodging neighborhoods/types, candidates, attraction clusters, airport/flight alternatives, approximate transit, budget, and a route skeleton. Label estimates and route limits; do not imply hotel-door timing or availability.

If the user's destination is broad, first compare plausible city/region candidates using the user's stated constraints. The provisional comparison is allowed while a destination `USER_DECISION` remains open; do not silently select a final city.

## Level 2 — Final plan

After the traveler confirms an area/candidate or explicitly delegates selection, refine the plan from researched options. After flight and property are known, calculate airport access, property-to-stop routes, date-specific public transport, exact daily time windows, meals near the route, and a more precise budget. Do not claim precision where a provider is unavailable.

## Route anchors

- `DESTINATION_AREA_ANCHOR`: only a city/area is known; present clusters and route skeleton, not door-to-door legs.
- `AREA_LEVEL_ANCHOR`: a neighborhood or station area is known/recommended; route segments may start there, with walking/transfers clearly approximate.
- `PROPERTY_LEVEL_ANCHOR`: a confirmed hotel address supports property-specific refinement.
- `ROUTE_PENDING`: reserve for unavailable route evidence/provider failures. It must not mean the user has not selected a hotel.

Replanning after a hotel/flight choice updates the same trip profile and preserves earlier evidence; it does not restart discovery.
