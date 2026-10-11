import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from travel_utils import critical_information_gate,optimize_budget,trip_readiness,personalize_candidate_clusters,validate_trip
from analyze_trip_request import analyze_request


class ProductizationTests(unittest.TestCase):
    def profile(self):
        return {"critical_info":{"destination":"Tokyo","destination_scope":"city","destination_resolved":True,"travel_window":"2027-04","duration_days":8,"traveler_count":2,
                "origin":"Shanghai","budget_amount":1000,"budget_currency":"USD","budget_scope":"whole trip per party, airfare excluded","free_accommodation":False}}

    def test_gate_accepts_minimum_complete_profile(self):
        self.assertTrue(critical_information_gate(self.profile())["ready_for_final"])

    def test_gate_requires_free_stay_location_only_when_applicable(self):
        profile=self.profile(); profile["critical_info"]["free_accommodation"]=True
        gate=critical_information_gate(profile)
        self.assertEqual(gate["missing"],["accommodation_location","free_stay_dates"])
        profile["critical_info"]["accommodation_location"]="Shinjuku"
        profile["critical_info"]["free_stay_dates"]="2027-04-12 to 2027-04-15"
        self.assertTrue(critical_information_gate(profile)["ready_for_final"])

    def test_gate_rejects_zero_party_and_placeholder_budget_scope(self):
        profile=self.profile(); profile["critical_info"].update({"traveler_count":0,"budget_scope":"TBD"})
        missing=critical_information_gate(profile)["missing"]
        self.assertIn("traveler_count",missing); self.assertIn("budget_scope",missing)

    def test_country_is_not_a_confirmed_city_and_questions_are_bounded(self):
        result=analyze_request('我想春节去日本玩七天，预算5000')
        self.assertEqual(result['mode'],'RESEARCH_MODE')
        self.assertFalse(result['formal_plan_allowed'])
        self.assertIn('destination_choice',result['missing_critical_fields'])
        self.assertLessEqual(len(result['questions']),5)

    def test_four_realistic_prompts_remain_research_only_without_critical_fields(self):
        prompts=['我要春节出去玩一周预算5000','Japan 8 days budget 6000; my friend can host me for 3 nights',
                 '东京5天，不早起，预算每人5000','我和女朋友去东京五天，预算每人5000，朋友住东京，可以住三晚，不喜欢早起，每天最多一万二步']
        for prompt in prompts:
            with self.subTest(prompt=prompt):
                result=analyze_request(prompt)
                self.assertEqual(result['mode'],'RESEARCH_MODE')
                self.assertFalse(result['formal_plan_allowed'])
                self.assertLessEqual(len(result['questions']),5)

    def test_personalization_applies_sleep_and_step_preferences(self):
        options=[{'name':'早晨长走','start_time':'07:00','estimated_steps':18000,'interest_tags':['anime']},
                 {'name':'午后近距离','start_time':'13:00','estimated_steps':7000,'interest_tags':['anime']}]
        ranked=personalize_candidate_clusters({'interests':['anime'],'sleep_schedule':'late_start','walking_tolerance_steps':10000},options)
        self.assertEqual(ranked[0]['candidate']['name'],'午后近距离')
        self.assertTrue(ranked[0]['decision_reasons'])

    def test_chinese_walking_limit_and_free_stay_location_are_extracted(self):
        result=analyze_request('我和女朋友去东京五天，预算每人5000，朋友住东京，可以住三晚，不喜欢早起，每天最多一万二步')
        self.assertEqual(result['trip_profile']['walking_tolerance_steps'],12000)
        self.assertEqual(result['trip_profile']['accommodation_location'],'东京')
        self.assertIn('free_stay_dates',result['missing_critical_fields'])

    def test_real_v05_japan_prompt_does_not_confuse_currency_or_girlfriend_with_guest_count_or_free_stay(self):
        result=analyze_request('我准备和女朋友去日本玩8天，预算每人6000人民币，2027年4月下旬出发，从上海出发，预算含往返机票、住宿、餐饮、市内交通和景点费用，不想每天早起，每天最多走12000步，比较喜欢美食和拍照。关西：大阪为基地、京都一日往返；经济型酒店，购物另计。')
        profile=result['trip_profile']
        self.assertEqual(profile['traveler_count'],2)
        self.assertFalse(profile.get('free_accommodation',False))
        self.assertEqual(profile['budget_amount'],6000)
        self.assertEqual(profile['budget_scope'],'per person, including airfare')
        self.assertEqual(profile['origin'],'上海')
        self.assertEqual(profile['destination'],'Osaka')
        self.assertEqual(profile['day_trip_destinations'],['Kyoto'])
        self.assertEqual(profile['walking_tolerance_steps'],12000)
        self.assertEqual(result['mode'],'PLANNING_MODE')
        self.assertNotIn('destination_choice',result['missing_critical_fields'])
        self.assertEqual(result['route_state'],'AREA_LEVEL_ANCHOR')
        self.assertEqual(profile['interests'],['food','photography'])

    def test_route_chain_must_start_at_confirmed_lodging_and_remain_continuous(self):
        data={'destination':'Tokyo','trip_profile':self.profile()['critical_info'],'lodging_location':'Shinjuku hotel',
              'days':[{'activities':['visit'],'route_state':'ORIGIN_BOUND','route_chain':[
                {'from':'Tokyo Station','to':'Asakusa','duration_minutes':20,'source_url':'https://example.org/r','checked_at':'2026-10-07T00:00:00Z'},
                {'from':'Ueno','to':'Shinjuku hotel'}]}]}
        issues=validate_trip(data)
        self.assertTrue(any('must start' in issue for issue in issues))
        self.assertTrue(any('discontinuous' in issue for issue in issues))

    def test_budget_reverse_optimization_respects_protected_costs_and_evidence(self):
        data={"budget":{"currency":"USD","traveler_count":1,"recommended":{"transport":100,"accommodation":500,"food":200,"emergency":100}},
              "budget_limit":770,"saving_options":[
                  {"category":"accommodation","max_saving":80,"tradeoff_score":1,"basis":"estimated","assumption":"switch to a lower-cost room"},
                  {"category":"food","max_saving":50,"tradeoff_score":2,"basis":"verified","source_url":"https://example.org/lunch"},
                  {"category":"emergency","max_saving":100,"tradeoff_score":0,"basis":"estimated","assumption":"remove reserve","protected":True}]}
        result=optimize_budget(data)
        self.assertEqual(result["original_total"],900)
        self.assertEqual(result["projected_total"],770)
        self.assertEqual(result['current_plan_cost'],900)
        self.assertIn(result['sacrifice_impact'],{'low','medium','high'})
        self.assertTrue(result["within_budget"])
        self.assertEqual(result["adjusted_categories"]["emergency"],100)

    def test_budget_optimizer_reports_unresolved_gap_and_rejects_unsupported_savings(self):
        data={"budget":{"currency":"USD","traveler_count":1,"recommended":{"food":100}},"budget_limit":50,
              "saving_options":[{"category":"food","max_saving":20,"tradeoff_score":1,"basis":"estimated"}]}
        with self.assertRaises(ValueError): optimize_budget(data)
        data["saving_options"][0]["assumption"]="choose a lower-cost meal"
        result=optimize_budget(data)
        self.assertFalse(result["within_budget"])
        self.assertEqual(result["remaining_gap"],30)


if __name__=="__main__": unittest.main()
