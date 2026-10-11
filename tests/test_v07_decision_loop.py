import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from decision_loop import ask_value_test, compress_decisions, execute_decision_loop
from travel_utils import decision_mode, trip_readiness
from analyze_trip_request import analyze_request


class V07DecisionLoopTests(unittest.TestCase):
    def test_area_only_lodging_location_does_not_claim_property_level_anchor(self):
        result = trip_readiness({"trip_profile": {"destination": "Osaka", "destination_scope": "city",
            "destination_resolved": True, "travel_window": "2027-04-20 to 2027-04-27", "duration_days": 8,
            "traveler_count": 2, "origin": "Shanghai", "budget_amount": 6000, "budget_currency": "CNY",
            "budget_scope": "per person; airfare included", "lodging_location": "Shinsaibashi area (hotel not booked)",
            "lodging_area": "Shinsaibashi"}})
        self.assertEqual(result["route_state"], "AREA_LEVEL_ANCHOR")

    def test_nine_user_prompt_regressions_keep_discoverable_choices_agent_owned(self):
        prompts = [
            "我想去日本玩8天，预算6000，两个人，4月，上海出发，喜欢美食和拍照，不要太累。",
            "我不知道大阪住哪里。", "酒店你帮我挑。", "我不知道大阪有什么值得去的，你安排。",
            "交通你决定。", "吃什么你安排。", "这些我都不知道，你全部帮我决定。",
            "你觉得合适就行。", "我只告诉你预算6000元，其他都你决定。",
        ]
        for prompt in prompts:
            result = analyze_request(prompt)
            asked = " ".join(q["question"] for q in result["questions"])
            self.assertNotRegex(asked, r"你想住哪个区域|想住哪家酒店|想去哪些景点|想坐地铁还是 JR|想吃哪家餐厅")
            self.assertIn("lodging", [x["domain"] for x in result["agent_discovery"]["research_queue"]])
        self.assertFalse(analyze_request(prompts[0])["trip_profile"].get("destination") == "Tokyo")
        self.assertEqual(analyze_request(prompts[6])["decision_mode"], "AUTO_DECISION_MODE")
        self.assertEqual(analyze_request(prompts[7])["decision_mode"], "AUTO_DECISION_MODE")
        self.assertEqual(analyze_request(prompts[8])["decision_mode"], "AUTO_DECISION_MODE")
        self.assertTrue(analyze_request(prompts[8])["missing_critical_fields"])

    def test_explicit_auto_decision_phrases_activate_mode_without_silent_consent(self):
        for phrase in ("你看着办", "你决定", "我都不知道", "随便", "都可以", "按你觉得合适的来"):
            self.assertTrue(decision_mode(phrase), phrase)
        self.assertFalse(decision_mode("我还在考虑大阪住哪里。"))

    def test_discoverable_lodging_and_p3_are_not_user_questions(self):
        lodging = ask_value_test({"field": "lodging_area", "user_information_need": .3, "agent_discoverability": .9, "impact_on_plan": .8, "preference_dependence": .2})
        detail = ask_value_test({"field": "meal_time", "impact_on_plan": .1})
        self.assertEqual(lodging["priority"], "P1")
        self.assertFalse(lodging["ask_user"])
        self.assertEqual(detail["priority"], "P3")

    def test_subjective_decisions_respect_three_item_budget_but_p0_survives(self):
        rows = [{"field": f"tradeoff_{n}", "user_information_need": .8, "agent_discoverability": .1,
                 "impact_on_plan": .9, "preference_dependence": .9} for n in range(5)]
        rows.append({"field": "origin"})
        out = compress_decisions(rows)
        self.assertEqual(sum(x["priority"] == "P2" for x in out["questions"]), 3)
        self.assertEqual(sum(x["priority"] == "P0" for x in out["questions"]), 1)
        self.assertEqual(len(out["overflow"]), 2)

    def test_research_loop_requires_real_https_source_and_timestamp(self):
        queue = [{"domain": "lodging", "status": "complete"}, {"domain": "flights", "status": "complete"}]
        evidence = {"lodging": [{"id": "a", "name": "A", "source_url": "https://hotel.example/", "checked_at": "2026-10-07T00:00:00Z", "recommendation_score": 5, "price": 200, "stay_dates": "2027-04-20/2027-04-27", "room_type": "double", "traveler_count": 2}],
                    "flights": [{"id": "fiction", "name": "No source", "price": 100}]}
        out = execute_decision_loop({"destination": "Osaka"}, queue, evidence, auto_decision=True)
        self.assertEqual(out["domain_status"]["lodging"], "AUTO_SELECTED")
        self.assertEqual(out["domain_status"]["flights"], "EVIDENCE_INCOMPLETE")
        self.assertEqual(len(out["decision_ledger"]), 1)
        self.assertFalse(out["side_effects"]["booking"])

    def test_sourced_hotel_listing_without_date_price_is_not_a_hotel_recommendation(self):
        out = execute_decision_loop({}, [{"domain": "lodging", "status": "complete"}], {"lodging": [
            {"id": "hotel", "name": "Hotel", "source_url": "https://hotel.example/", "checked_at": "2026-10-07T00:00:00Z"}
        ]})
        self.assertEqual(out["domain_status"]["lodging"], "EVIDENCE_INCOMPLETE")
        self.assertEqual(out["decision_ledger"], [])
        self.assertEqual(len(out["candidates"]["lodging"]), 1)

    def test_selection_schema_and_bounded_retry_policy_are_reported(self):
        out = execute_decision_loop({"travel_window": "late April", "traveler_count": 2},
            [{"domain": "lodging", "status": "unavailable"}, {"domain": "flights", "status": "unavailable"}],
            {}, auto_decision=True)
        self.assertEqual(out["selection_status"]["lodging"]["status"], "UNAVAILABLE")
        self.assertIsNone(out["selection_status"]["lodging"]["selection_source"])
        self.assertEqual(out["bounded_retry_plans"]["lodging"]["max_attempts"], 5)
        self.assertEqual(out["bounded_retry_plans"]["flights"]["max_attempts"], 5)
        self.assertEqual(out["replanning_policy"]["priority_order"], ["HARD_CONSTRAINT", "SOFT_CONSTRAINT", "PREFERENCE", "OPTIONAL"])
        self.assertFalse(out["replanning_policy"]["side_effects_enabled"])

    def test_over_budget_triggers_new_research_round(self):
        out = execute_decision_loop({}, [{"domain": "lodging"}], {}, budget_state={"estimated_total": 7000, "limit": 6000})
        self.assertEqual(out["state"], "RESEARCH_REQUIRED")
        self.assertEqual(out["rounds"], 2)

    def test_source_conflict_is_preserved_and_requests_authoritative_research(self):
        records = {"attractions": [
            {"id": "one", "name": "Ticket", "source_url": "https://official.example/ticket", "checked_at": "2026-10-07T00:00:00Z", "claim_key": "ticket", "value": "JPY 1000"},
            {"id": "two", "name": "Ticket", "source_url": "https://platform.example/ticket", "checked_at": "2026-10-07T00:00:00Z", "claim_key": "ticket", "value": "JPY 1200"},
        ]}
        out = execute_decision_loop({}, [{"domain": "attractions"}], records)
        self.assertEqual(len(out["evidence_conflicts"]), 1)
        self.assertIn("evidence_conflict", [x["trigger"] for x in out["replan_triggers"]])

    def test_user_decision_ledger_contains_only_material_preference_tradeoffs(self):
        out = execute_decision_loop({}, [], {}, potential_questions=[
            {"field": "lodging", "question": "每人多花300元，是否少通勤25分钟？", "reason": "预算与时间取舍", "options": ["省钱", "省时间"], "impact": "每日通勤时长", "default_recommendation": "省钱", "user_information_need": .9, "agent_discoverability": .1, "impact_on_plan": .9, "cost_difference": .8, "preference_dependence": .9},
            {"field": "meal_time", "question": "早餐几点？", "impact_on_plan": .1}
        ])
        self.assertEqual(len(out["user_decision_ledger"]), 1)
        self.assertIn("300元", out["user_decision_ledger"][0]["question"])


if __name__ == "__main__":
    unittest.main()
