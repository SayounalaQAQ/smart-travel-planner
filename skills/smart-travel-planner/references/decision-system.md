# Candidate and decision lifecycle

Use this common lifecycle for lodging, flights, attractions, transit, tickets, restaurants, and route options:

`DISCOVERING → PROPOSED → USER_DECISION_REQUIRED → CONFIRMED`

When the user explicitly delegates a decision, use:

`DISCOVERING → PROPOSED → AUTO_SELECTED → FINAL_OPTIMIZATION`

`UNAVAILABLE` is a data status, not a fabricated candidate. Preserve the reason and what must be rechecked. A user may revise an `AUTO_SELECTED` or `CONFIRMED` choice.

## Candidate record

Each researched candidate should include `id`, `name`, `kind`, `price`/`price_range` with currency and party/date/room conditions where relevant, `duration` where relevant, `pros`, `cons`, `fit_reasons`, `source_urls`, `checked_at`, `confidence`, and `availability_status`. Omit unknown values or mark them `unavailable`; do not fill with guesses. For flight candidates also record airports, departure/arrival time, total travel time, fare basis, baggage and source. For lodging candidates record room/occupancy, exact stay dates, tax/cancellation, distance to transit and whether the price is a dated quote or a reference price.

## Recommendations

Show a small set (normally 2–4) and make the default explicit. A recommendation must cite which known user constraints it serves and which trade-off it accepts. If required search capability is missing, return `UNAVAILABLE` and a clear limited comparison; do not ask the user to search for options.

## Automatic decisions

Enter `AUTO_DECISION_MODE` only on explicit delegation (for example “你决定/都帮我安排/你看着办”). Choose the best evidence-backed option under user constraints, preserve protected budget and safety constraints, state the reason, and keep the choice editable. Delegation does not authorize booking, payment, sharing personal data, or irreversible actions.
