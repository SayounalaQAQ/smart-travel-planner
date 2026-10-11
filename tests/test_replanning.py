import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from replanning import (MAX_REPLAN_ROUNDS, budget_status, build_retry_strategy,
                        classify_constraints, classify_flight_result, detect_conflicts,
                        record_retry_results, replan, selection_metadata)


class ReplanningTests(unittest.TestCase):
    def evidence(self, ident, name, **kwargs):
        return {"id": ident, "name": name, "source_url": "https://official.example/route",
                "checked_at": "2026-10-07T00:00:00Z", "confidence": "high", **kwargs}

    def profile(self):
        return {"budget_amount": 6000, "budget_currency": "CNY", "budget_scope": "per person including airfare",
                "walking_tolerance_steps": 12000, "walking_limit_priority": "HARD_CONSTRAINT",
                "sleep_schedule": "late_start", "preferred_start_time": "09:30", "interests": ["food", "photography"],
                "auto_decision_mode": True}

    def test_constraint_priority_does_not_promote_preference_to_hard(self):
        got = classify_constraints(self.profile())
        self.assertEqual(got["budget"]["priority"], "HARD_CONSTRAINT")
        self.assertEqual(got["walking"]["priority"], "HARD_CONSTRAINT")
        self.assertEqual(got["sleep"]["priority"], "SOFT_CONSTRAINT")
        self.assertEqual(got["interests"]["priority"], "PREFERENCE")

    def test_detects_budget_walking_sleep_and_opening_conflicts(self):
        plan = {"budget_state": {"current_plan_cost": 6800}, "days": [{"estimated_steps": 15000,
            "activities": [{"name": "Dawn hike", "start_time": "07:00"},
                           {"name": "Museum", "arrival_time": "17:30", "planned_finish": "18:30", "closes_at": "18:00"}]}]}
        codes = {item["code"] for item in detect_conflicts(self.profile(), plan)}
        self.assertEqual(codes, {"BUDGET_CONFLICT", "WALKING_CONFLICT", "SLEEP_SCHEDULE_CONFLICT", "OPENING_HOURS_CONFLICT"})

    def test_detects_remaining_supported_conflict_types_from_explicit_validation_data(self):
        profile = {"daily_distance_limit_km": 8, "daily_activity_limit_minutes": 360,
                   "max_daily_commute_minutes": 45, "minimum_interest_match": .4,
                   "avoid_crowds": True}
        plan = {"hotel": {"daily_commute_minutes": 70, "commute_evidence": ["https://map.example/route"]},
                "days": [{"distance_km": 11, "activities": [
                    {"name": "Overloaded day", "duration_minutes": 400, "interest_match_score": .1,
                     "crowd_level": "high", "crowd_evidence": ["https://official.example/crowds"],
                     "reservation_required": True, "reservation_status": "sold_out",
                     "reservation_evidence": ["https://official.example/tickets"],
                     "weather_sensitive": True, "weather_status": "unsafe",
                     "weather_evidence": ["https://official.example/weather"]}],
                    "transport_conflict": True, "transport_evidence": ["https://rail.example/status"]}]}
        codes = {x["code"] for x in detect_conflicts(profile, plan)}
        self.assertEqual(codes, {"DISTANCE_CONFLICT", "TIME_CONFLICT", "TRANSPORT_CONFLICT",
                                 "HOTEL_LOCATION_CONFLICT", "INTEREST_CONFLICT", "CROWD_CONFLICT",
                                 "RESERVATION_CONFLICT", "WEATHER_CONFLICT"})

    def test_self_resolves_early_high_walk_route_from_sourced_alternative(self):
        profile = self.profile()
        initial = {"decisions": {"route": "full-hike"}, "days": [{"estimated_steps": 16000,
            "activities": [{"name": "Fushimi full mountain route", "start_time": "07:00"}]}]}
        candidates = {"route": [
            self.evidence("full-hike", "Full mountain hike", estimated_steps=16000, start_time="07:00",
                          utility_components={"walking": 0.9, "sleep": 0.9, "interests": 1.0}),
            self.evidence("late-short-route", "Late-start short shrine route", estimated_steps=9500, start_time="10:00",
                          utility_components={"walking": 0.9, "sleep": 1.0, "interests": 0.9},
                          why_selected="Official visitor tour offers 10:00/11:30 starts and about one hour; avoids the 2–3 hour full mountain circuit.",
                          plan_patch={"days": [{"estimated_steps": 9500, "activities": [{"name": "Fushimi short route", "start_time": "10:00"}]}]})]}
        out = replan(profile, initial, candidates)
        self.assertEqual(out["status"], "REPLANNED")
        self.assertEqual(out["revised_plan"]["decisions"]["route"], "late-short-route")
        self.assertEqual(out["revised_plan"]["days"][0]["estimated_steps"], 9500)
        self.assertFalse(out["conflicts_after"])
        self.assertEqual(out["revision_ledger"][0]["trigger"], "WALKING_CONFLICT")
        self.assertIn("SLEEP_SCHEDULE_CONFLICT", out["revision_ledger"][0]["triggers"])
        self.assertEqual(out["user_decision_count"], 0)
        self.assertFalse(any(out["side_effects"].values()))

    def test_no_early_start_is_not_silently_traded_for_better_photography(self):
        initial = {"decisions": {"route": "dawn"}, "days": [{"estimated_steps": 7000,
            "activities": [{"name": "Photo walk", "start_time": "07:00"}]}]}
        late = self.evidence("late", "Late-start photo route", start_time="10:30", estimated_steps=8000,
                             utility_components={"sleep": 1.0, "interests": 0.8},
                             plan_patch={"days": [{"estimated_steps": 8000, "activities": [{"name": "Photo walk", "start_time": "10:30"}]}]})
        dawn = self.evidence("dawn", "Dawn photo route", start_time="07:00", estimated_steps=7000,
                             utility_components={"sleep": 0.1, "interests": 1.0})
        out = replan(self.profile(), initial, {"route": [dawn, late]})
        self.assertEqual(out["revised_plan"]["decisions"]["route"], "late")
        self.assertEqual(out["revision_ledger"][0]["trigger"], "SLEEP_SCHEDULE_CONFLICT")

    def test_no_sourced_resolution_escalates_only_after_self_resolution_attempt(self):
        initial = {"decisions": {"route": "route-a"}, "days": [{"estimated_steps": 18000,
            "activities": [{"name": "All-day route", "start_time": "07:00"}]}]}
        out = replan(self.profile(), initial, {"route": []})
        self.assertEqual(out["status"], "USER_DECISION_REQUIRED")
        self.assertEqual(out["user_decision_count"], 1)
        self.assertEqual(out["user_decisions"][0]["level"], 3)

    def test_level_two_presents_tradeoffs_with_default_without_forcing_a_question(self):
        profile = {"sleep_schedule": "late_start", "preferred_start_time": "09:30", "interests": ["photography"]}
        initial = {"decisions": {"route": "dawn"}, "days": [{"estimated_steps": 8000,
            "activities": [{"name": "Photo route", "start_time": "07:00"}]}]}
        options = [
            self.evidence("late-view-a", "Late option A", start_time="10:00", estimated_steps=8000,
                          utility_components={"interests": .80}, plan_patch={"days": [{"estimated_steps": 8000,
                          "activities": [{"name": "Late route", "start_time": "10:00"}]}]}),
            self.evidence("late-view-b", "Late option B", start_time="10:00", estimated_steps=8500,
                          utility_components={"interests": .82}),
        ]
        out = replan(profile, initial, {"route": options})
        self.assertEqual(out["question_escalation_level"], 2)
        self.assertEqual(out["user_decision_count"], 0)
        self.assertEqual(len(out["revision_ledger"][0]["tradeoff_options"]), 2)
        self.assertTrue(out["revision_ledger"][0]["default_recommendation"])

    def test_missing_or_untrusted_candidate_cannot_cause_revision(self):
        initial = {"decisions": {"route": "old"}, "days": [{"estimated_steps": 16000,
            "activities": [{"name": "Long", "start_time": "07:00"}]}]}
        out = replan(self.profile(), initial, {"route": [{"id": "fake", "name": "Fake", "source_url": "http://x", "checked_at": "bad"}]})
        self.assertFalse(out["revision_ledger"])
        self.assertTrue(out["conflicts_after"])

    def test_revisions_are_material_and_stable(self):
        initial = {"decisions": {"route": "same"}, "days": [{"estimated_steps": 9000,
            "activities": [{"name": "Late route", "start_time": "10:00"}]}]}
        same = self.evidence("same", "Same route", start_time="10:00", estimated_steps=9000,
                             utility_components={"interests": 0.91})
        slightly_better = self.evidence("small-change", "Marginal change", start_time="10:00", estimated_steps=9000,
                                        utility_components={"interests": 0.95})
        out = replan(self.profile(), initial, {"route": [same, slightly_better]})
        self.assertFalse(out["revision_ledger"])
        self.assertEqual(out["revised_plan"]["decisions"]["route"], "same")
        with self.assertRaises(ValueError):
            replan(self.profile(), initial, {}, max_rounds=MAX_REPLAN_ROUNDS + 1)

    def test_retry_plans_are_bounded_and_do_not_claim_search_execution(self):
        lodging = build_retry_strategy("hotels", {"travel_window": "late April 2027", "traveler_count": 2})
        flight = build_retry_strategy("flights", {"travel_window": "late April 2027", "traveler_count": 2})
        self.assertEqual(len(lodging["attempts"]), 5)
        self.assertEqual(len(flight["attempts"]), 5)
        self.assertFalse(flight["nearby_date_search_allowed"])
        self.assertTrue(all(item["status"] == "PENDING" for item in lodging["attempts"]))
        self.assertIn("not evidence", lodging["note"])

    def test_executed_retry_log_requires_provider_and_records_failure_reason(self):
        plan = build_retry_strategy("hotels", {"travel_window": "2027-04-20/27", "traveler_count": 2})
        rows = [{"attempt": i, "executed": True, "provider": provider,
                 "status": "NO_EXACT_DATE_QUOTE", "failure_reason": "Target room/date price not returned."}
                for i, provider in enumerate(("official", "ota", "regional", "hotel-page", "multilingual"), 1)]
        result = record_retry_results(plan, rows)
        self.assertEqual(result["search_status"], "UNAVAILABLE")
        self.assertEqual(len(result["providers_attempted"]), 5)
        self.assertIn("Target room/date price", result["failure_reason"])
        with self.assertRaises(ValueError):
            record_retry_results(plan, [{"attempt": 1, "provider": "official"}])

    def test_nearby_flight_reference_is_never_promoted_without_date_permission(self):
        reference = {"dates": "different dates", "fare": 999}
        self.assertEqual(classify_flight_result(nearby_date_reference=reference, date_flexibility=False)["status"], "UNAVAILABLE")
        self.assertEqual(classify_flight_result(nearby_date_reference=reference, date_flexibility=True)["status"], "NEARBY_DATE_REFERENCE")
        exact = {"dates": "requested dates", "fare": 1234}
        self.assertEqual(classify_flight_result(exact_date_quote=exact)["status"], "EXACT_DATE_QUOTE")

    def test_budget_fields_separate_limit_from_verified_cost(self):
        status = budget_status(6000, 6450, 6300, 6300, evidence_status="verified", currency="CNY")
        self.assertEqual(status["user_budget_limit"], 6000)
        self.assertEqual(status["current_plan_cost"], 6450)
        self.assertEqual(status["lowest_found_cost"], 6300)
        self.assertEqual(status["budget_gap"], 300)
        self.assertEqual(status["feasibility"], "LIKELY_INSUFFICIENT")
        self.assertEqual(budget_status(6000, 6000, evidence_status="unverified")["feasibility"], "UNVERIFIED")

    def test_budget_conflict_starts_bounded_hotel_and_flight_research(self):
        profile = self.profile()
        initial = {"budget_state": {"current_plan_cost": 6800}}
        out = replan(profile, initial, {})
        self.assertEqual(out["bounded_retry_plans"]["hotels"]["max_attempts"], 5)
        self.assertEqual(out["bounded_retry_plans"]["flights"]["max_attempts"], 5)
        self.assertTrue(all(attempt["status"] == "PENDING" for attempt in out["bounded_retry_plans"]["hotels"]["attempts"]))

    def test_budget_conflict_switches_to_evidenced_area_under_cap_without_asking(self):
        profile = self.profile()
        initial = {"decisions": {"lodging_area": "minami"}, "budget_state": {"current_plan_cost": 7500}}
        options = [
            self.evidence("minami", "Minami", total_trip_cost_per_person=7500,
                          utility_components={"interests": 1.0}),
            self.evidence("hommachi", "Hommachi", total_trip_cost_per_person=6300,
                          utility_components={"interests": .8}),
            self.evidence("tennoji", "Tennoji", total_trip_cost_per_person=5900,
                          utility_components={"interests": .7},
                          why_selected="Target-date total trip cost stays under the hard cap after lodging plus added local transport.",
                          plan_patch={"budget_state": {"current_plan_cost": 5900, "evidence_status": "verified"}}),
        ]
        out = replan(profile, initial, {"lodging_area": options})
        self.assertEqual(out["status"], "REPLANNED")
        self.assertEqual(out["revised_plan"]["decisions"]["lodging_area"], "tennoji")
        self.assertEqual(out["revision_ledger"][0]["trigger"], "BUDGET_CONFLICT")
        self.assertEqual(out["user_decision_count"], 0)
        self.assertFalse(out["conflicts_after"])

    def test_selection_source_and_confirmation_are_explicit(self):
        self.assertEqual(selection_metadata("AUTO_SELECTED"), {"selection_source": "AUTO_SELECTED", "confirmation_status": "NOT_REQUIRED"})
        self.assertEqual(selection_metadata("AGENT_SELECTED"), {"selection_source": "AGENT_SELECTED", "confirmation_status": "AWAITING_USER"})
        self.assertEqual(selection_metadata("USER_SELECTED"), {"selection_source": "USER_SELECTED", "confirmation_status": "USER_CONFIRMED"})


if __name__ == "__main__":
    unittest.main()
