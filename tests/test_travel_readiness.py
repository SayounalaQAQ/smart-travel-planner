import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from travel_readiness import (apply_readiness, bounded_hotel_search_plan,
    build_data_completeness_matrix, detect_diversity_conflicts, flight_candidate,
    hotel_availability_record, plan_qa, rank_flight_candidates, rank_hotel_candidates, record_hotel_search, station_route,
    validate_route_chain)


class TravelReadinessTests(unittest.TestCase):
    def test_hotel_exact_price_requires_target_dates_room_party_and_source(self):
        with self.assertRaises(ValueError):
            hotel_availability_record(hotel_name="Hotel", area="Minami", room_type=None,
                guest_count=2, check_in="2027-04-20", check_out="2027-04-27",
                total_price=80000, currency="JPY", availability="AVAILABLE",
                source_url="https://hotel.example", price_type="EXACT_DATE_PRICE")
        record = hotel_availability_record(hotel_name="Hotel", area="Minami", room_type="Twin",
            guest_count=2, check_in="2027-04-20", check_out="2027-04-27",
            availability="UNKNOWN", price_type="UNAVAILABLE", source_url="https://hotel.example")
        self.assertIsNone(record["total_price"])

    def test_reference_rate_cannot_be_promoted_to_target_date_availability(self):
        with self.assertRaises(ValueError):
            hotel_availability_record(hotel_name="Hotel", area="Minami", room_type="Twin",
                guest_count=2, check_in="2027-04-20", check_out="2027-04-27",
                total_price=9000, currency="JPY", availability="AVAILABLE",
                source_url="https://ota.example", price_type="MONTHLY_REFERENCE")

    def test_flight_exact_quote_requires_operational_details_and_neighbor_needs_permission(self):
        with self.assertRaises(ValueError):
            flight_candidate(origin_airport="PVG", destination_airport="KIX",
                flight_date="2027-04-20", price=2000, currency="CNY", source="https://air.example",
                status="EXACT_DATE_QUOTE")
        with self.assertRaises(ValueError):
            flight_candidate(origin_airport="PVG", destination_airport="KIX",
                flight_date="2027-04-19", status="NEARBY_DATE_REFERENCE")

    def test_retry_provider_order_is_bounded_and_execution_is_auditable(self):
        plan = bounded_hotel_search_plan("Hotel")
        rows = [{"attempt": i + 1, "provider": slot["provider"], "executed": True,
                 "status": "NO_EXACT_DATE_RESULT", "failure_reason": "No target-date room and total."}
                for i, slot in enumerate(plan["attempts"])]
        result = record_hotel_search(plan, rows)
        self.assertEqual(result["attempt_count"], 4)
        self.assertEqual(len(result["providers_attempted"]), 4)
        self.assertIsNone(result["best_available_result"])
        with self.assertRaises(ValueError):
            bounded_hotel_search_plan("Hotel", max_attempts=6)

    def test_station_route_requires_fields_to_claim_verified(self):
        with self.assertRaises(ValueError):
            station_route(from_station="Namba", to_station="Yodoyabashi", status="VERIFIED")
        row = station_route(from_station="Namba", to_station="Yodoyabashi", status="UNAVAILABLE")
        self.assertIsNone(row["fare"])

    def test_disconnected_route_chain_is_detected(self):
        findings = validate_route_chain({"route_chain": [
            {"from": "Namba", "to": "Yodoyabashi", "status": "ESTIMATED", "source": "https://map.example"},
            {"from": "Osaka Station", "to": "Hotel", "status": "UNAVAILABLE"}]})
        self.assertTrue(findings)

    def test_duplicate_known_attraction_is_detected_across_different_activity_phrasing(self):
        conflicts = detect_diversity_conflicts([
            {"activities": [{"activity": "伏见稻荷下段鸟居短访"}]},
            {"activities": [{"activity": "伏见稻荷鸟居步道短线"}]},
        ], [{"name": "伏见稻荷"}])
        self.assertEqual(conflicts[0]["code"], "DUPLICATE_ACTIVITY")

    def test_user_requested_repeat_is_allowed(self):
        conflicts = detect_diversity_conflicts([
            {"activities": [{"activity": "Park", "repeat_requested": True}]},
            {"activities": [{"activity": "Park", "repeat_requested": True}]},
        ])
        self.assertFalse(any(row["code"] == "DUPLICATE_ACTIVITY" for row in conflicts))

    def test_hotel_picks_remain_pending_without_exact_date_stock_and_price(self):
        result = rank_hotel_candidates([{"hotel_name": "Candidate", "availability": "UNKNOWN",
            "price_type": "UNAVAILABLE", "fit": {"location": .9, "food_access": .8}}])
        self.assertEqual(result["status"], "DATA_PENDING")
        self.assertIsNone(result["picks"]["budget_pick"])

    def test_monthly_hotel_reference_is_not_ranked_as_a_budget_pick(self):
        rows = [
            {"hotel_name": "Monthly cheap", "availability": "UNKNOWN", "price_type": "MONTHLY_REFERENCE",
             "total_price": 100, "fit": {"location": .9}},
            {"hotel_name": "Exact A", "availability": "AVAILABLE", "price_type": "EXACT_DATE_PRICE",
             "total_price": 1000, "fit": {"location": .8, "airport_access": .9, "cancellation": .8}},
            {"hotel_name": "Exact B", "availability": "AVAILABLE", "price_type": "EXACT_DATE_PRICE",
             "total_price": 1200, "fit": {"location": .9, "airport_access": .8, "cancellation": .7}},
        ]
        result = rank_hotel_candidates(rows)
        self.assertEqual(result["picks"]["budget_pick"]["hotel_name"], "Exact A")
        self.assertNotEqual(result["picks"]["budget_pick"]["hotel_name"], "Monthly cheap")

    def test_flight_comparison_does_not_select_other_date_references(self):
        result = rank_flight_candidates([{"status": "NEARBY_DATE_REFERENCE", "price": 1000}])
        self.assertEqual(result["status"], "DATA_PENDING")
        self.assertIsNone(result["picks"]["best_overall"])

    def test_plan_qa_readiness_never_calls_missing_hotel_and_flight_bookable(self):
        plan = {"trip_profile": {"destination_resolved": True, "lodging_area": "Minami",
                "start_date": "2027-04-20", "end_date": "2027-04-20", "duration_days": 1,
                "traveler_count": 2, "budget_amount": 6000, "budget_scope": "PER_PERSON", "budget_currency": "CNY"},
            "hotel_availability": [{"price_type": "UNAVAILABLE"}],
            "flight_availability": [{"status": "UNAVAILABLE"}],
            "days": [{"date": "2027-04-20", "route_sequence": [{"type": item} for item in
                        ["START", "ACTIVITY", "TRANSIT", "ACTIVITY", "MEAL", "TRANSIT", "RETURN"]],
                "route_chain": [
                {"from": "Minami", "to": "Namba Station", "status": "UNAVAILABLE"},
                {"from": "Namba Station", "to": "Minami", "status": "UNAVAILABLE"}]}]}
        qa = plan_qa(plan)
        self.assertEqual(qa["readiness"]["plan_status"], "EXECUTION_PARTIAL")
        self.assertEqual(qa["readiness"]["data_status"], "PARTIAL")
        self.assertEqual(qa["readiness"]["booking_readiness"], "NOT_READY")
        self.assertEqual(qa["readiness"]["travel_plan_readiness"], "EXECUTION_PARTIAL")
        self.assertEqual(qa["status"], "PARTIAL")

    def test_plan_qa_requires_replanning_on_duplicate_and_opening_conflict(self):
        plan = {"trip_profile": {}, "days": [
            {"date": "Day 1", "area": "Kyoto", "route_chain": [{"from": "A", "to": "B", "status": "ESTIMATED", "source": "https://map.example"}],
             "activities": [{"activity": "Museum", "planned_finish": "18:30", "closes_at": "18:00"}]},
            {"date": "Day 2", "area": "Kyoto", "route_chain": [{"from": "A", "to": "B", "status": "ESTIMATED", "source": "https://map.example"}],
             "activities": [{"activity": "Museum"}]},
        ]}
        codes = {x["code"] for x in plan_qa(plan)["findings"]}
        self.assertIn("DUPLICATE_ACTIVITY", codes)
        self.assertIn("DUPLICATE_AREA", codes)
        self.assertIn("OPENING_HOURS_CONFLICT", codes)

    def test_plan_qa_enforces_no_early_preference_budget_and_date_logic(self):
        plan = {"trip_profile": {"preferred_start_time": "09:30", "start_date": "2027-04-20",
                "end_date": "2027-04-27", "duration_days": 7, "traveler_count": 2,
                "budget_amount": 6000, "budget_scope": "PER_PERSON", "budget_currency": "CNY"},
            "cost_ledger": [{"id":"expensive-reference", "category":"transit", "item":"priced cost",
                "amount":6500, "quantity":1, "scope":"PER_PERSON", "traveler_count":2,
                "currency":"CNY", "cost_type":"CURRENT_REFERENCE", "source":"https://rail.example/price", "checked_at":"2026-10-10T00:00:00Z"}],
            "budget_status": {"feasibility": "LIKELY_INSUFFICIENT"},
            "days": [{"date": "2027-04-20", "route_sequence": [{"type": t} for t in
                ["START", "ACTIVITY", "TRANSIT", "ACTIVITY", "MEAL", "TRANSIT", "RETURN"]],
                "route_chain": [{"from": "A", "to": "B", "status": "ESTIMATED", "source": "https://route.example"}],
                "activities": [{"time": "08:30", "activity": "Dawn visit"}]}]}
        codes = {item["code"] for item in plan_qa(plan)["findings"]}
        self.assertIn("SLEEP_SCHEDULE_CONFLICT", codes)
        self.assertIn("BUDGET_CONFLICT", codes)
        self.assertIn("DATE_LOGIC_CONFLICT", codes)

    def test_readiness_matrix_has_explicit_unavailable_and_legacy_field_is_removed(self):
        plan = {"trip_profile": {"destination_choice_confirmed": True,
                "selection_source": "AUTO_SELECTED", "start_date": "2027-04-20",
                "end_date": "2027-04-27"}, "days": []}
        out = apply_readiness(plan)
        self.assertNotIn("destination_choice_confirmed", out["trip_profile"])
        matrix = build_data_completeness_matrix(out)
        self.assertIn("UNAVAILABLE", {row["status"] for row in matrix})


if __name__ == "__main__":
    unittest.main()
