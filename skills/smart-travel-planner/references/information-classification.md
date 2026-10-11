# Information classification

Unknown is a state of knowledge, not a reason to ask the user. Classify each profile field:

| Class | Meaning | Examples | Default action |
|---|---|---|---|
| `USER_REQUIRED` | Only the traveler can reliably provide it | origin, dates/flexibility, party size, budget and airfare scope, hard constraints, explicit likes/dislikes | Ask concisely when it materially changes feasibility; permit explicit skip with a labeled assumption only for non-critical preferences. |
| `AGENT_DISCOVERABLE` | Can be researched from current sources/providers | lodging areas and candidates, airports/flights, attractions, hours/tickets, transit and passes, restaurants, free options, routes | Research first. Record evidence, query time, confidence, and unavailable fields. Never ask the traveler to do this research. |
| `USER_DECISION` | Research exposes a material trade-off or costly commitment | cheapest vs faster flight, area trade-off, ticketed attraction vs free option, booking | Present a compact comparison and a default recommendation; ask only after research. |
| `UNAVAILABLE` | Research/provider cannot reliably supply it | future fare not published, no transit provider, dates without forecast horizon | Mark unavailable with reason, fallback estimate/range and next recheck time. Do not transfer the research burden to the user. |

The same field can move through classes over time. For example, lodging area begins `AGENT_DISCOVERABLE`, becomes a sourced candidate set, then becomes `USER_DECISION` if costs/location trade off. If the user delegates the choice, mark the chosen sourced option `AUTO_SELECTED`; the user may still change it.

## Ask Value Test

Ask only if at least one applies: (1) the Agent cannot discover the fact, (2) a genuine preference changes the recommendation, (3) a researched trade-off needs the user's value judgment, (4) an irreversible/high-cost action needs approval, or (5) privacy, payment, or authorization requires the user. Otherwise research, infer only when safe, or mark `UNAVAILABLE`.

Never ask “where do you want to stay?”, “which sights?”, “which airport/flight?”, “JR or subway?”, or “which restaurant?” as an unresearched open question. Turn researched options into a comparison with price/time, advantages, disadvantages, and a default recommendation.
