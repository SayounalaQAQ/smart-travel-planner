# Experience Discovery

Research possible experiences before selecting questions. The aim is to discover what the traveler hopes to do, not to complete a questionnaire. Preserve motivation, depth, priority, spending and pace in `trip_profile.experience_preferences` while retaining the legacy interests list.

Use `discover_experiences` to identify missing preference dimensions. Questions are proposals for AFTER preliminary research, not evidence that research ran. Bundle required trip facts and cash/budget meaning; choose only the 2–3 subjective questions with the greatest effect on choices. Keep the existing shared Decision Budget. If dates, origin or count are missing, a grouped critical question can leave room for interest discovery. Do not repeat known facts. Delegated preferences become exploration choices, never invented user preferences.

Supported anime subtypes: `pilgrimage`, `figure_collecting`, `retro_games`, `arcade`, `conventions`, `theme_cafe`, `voice_actor_events`, `exploration`. Favorite works stay empty until supplied. A pilgrimage needs real work/location association sources. Collecting needs store types, inventory specialties and district grouping, not guaranteed target-date stock. Participation in traditional culture needs a concrete experience and operator/booking conditions. Gender-targeted stores and specialized cafés require matching preferences.

Apply actual user answers with `experience_discovery.py --input profile-or-plan.json --answers user-answers.json --output updated.json`. Example answer shape (not a default):

```json
{"anime_subtypes":["figure_collecting","retro_games"],"favorite_works":[],"experience_priorities":{"fireworks":"MUST_HAVE"},"pace":"relaxed","experience_budget":{"currency":"JPY","amount":10000}}
```

`MUST_HAVE` is a scheduling requirement, not proof the event exists. Unknown future official event dates force a conditional plan and a stated alternative. An old-year photo or program is historical reference; never fix a future departure date from it. Different subtype answers must change selected candidates, time allocation or area sequence. Use `experience_match` through existing attraction/decision scoring; scores are advisory, and hard constraints still outrank interest.

If someone says “I have 15000”, retain `available_funds_amount`; ask currency, disposable travel amount, party basis and inclusions before setting `budget_amount`. An upper limit is not a spending target. Keep emergency reserves protected, never manufacture a feasible total from the cap.

Explicit adult-entertainment interest is separate OPTIONAL information. Without both adult confirmation and actual opt-in, omit it from itinerary and budget; legal cultural alternatives remain available. Discuss only non-explicit restrictions and practical uncertainty, verify any legal claim from authoritative applicable sources, never infer legality from a travel blog or a venue's existence. No payment, reservation or personal-data submission.
