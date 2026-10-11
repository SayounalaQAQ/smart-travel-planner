import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_trip_request import analyze_request
from travel_decisions import propose_candidates
from travel_utils import ask_value_test, classify_profile_fields, critical_information_gate, discovery_workflow, decision_mode, trip_readiness, validate_trip


class V06ProductLogicTests(unittest.TestCase):
    def test_selection_source_and_confirmation_status_replace_ambiguous_legacy_flag(self):
        profile={'destination':'Japan','destination_scope':'country','selection_source':'AUTO_SELECTED',
                 'confirmation_status':'NOT_REQUIRED','destination_choice_confirmed':False,
                 'travel_window':'2027-04','duration_days':8,'traveler_count':2,'origin':'Shanghai',
                 'budget_amount':6000,'budget_currency':'CNY','budget_scope':'per person including airfare'}
        state=trip_readiness({'trip_profile':profile})
        self.assertNotIn('destination_choice',state['missing_critical_fields'])

    def test_information_classes_make_unknown_lodging_a_research_task(self):
        result=analyze_request('帮我安排日本8天，4月底，两个人，预算6000元一个人，从上海出发，喜欢美食和拍照，不要太累。')
        self.assertEqual(result['trip_profile']['traveler_count'],2)
        self.assertEqual(result['trip_profile']['origin'],'上海')
        self.assertEqual(result['trip_profile']['pace'],'relaxed')
        self.assertEqual(result['information_classification']['lodging_area']['class'],'AGENT_DISCOVERABLE')
        self.assertEqual(result['information_classification']['flight_candidates']['status'],'research_required')
        self.assertIn('lodging', [item['domain'] for item in result['agent_discovery']['research_queue']])
        self.assertNotIn('住宿', ' '.join(q['question'] for q in result['questions']))
        self.assertIn('budget_scope',result['missing_critical_fields'])

    def test_lodging_not_required_to_pass_gate_or_route_validation(self):
        data={'destination':'Osaka','trip_profile':{'destination':'Osaka','destination_scope':'city','destination_resolved':True,
              'travel_window':'2027-04','duration_days':8,'traveler_count':2,'origin':'Shanghai','budget_amount':6000,
              'budget_currency':'CNY','budget_scope':'per person, airfare included','lodging_area':'Shinsaibashi'},
              'days':[{'activities':['area cluster'],'route_state':'AREA_LEVEL_ANCHOR','route_origin':'Shinsaibashi area','route_chain':[]} ]}
        self.assertTrue(critical_information_gate(data)['ready_for_final'])
        self.assertEqual(trip_readiness(data)['route_state'],'AREA_LEVEL_ANCHOR')
        self.assertEqual(validate_trip(data),[])

    def test_broad_destination_is_provisional_comparison_not_a_blocking_city_question(self):
        data={'trip_profile':{'destination':'Japan','destination_scope':'country','travel_window':'2027-04','duration_days':8,
              'traveler_count':2,'origin':'Shanghai','budget_amount':6000,'budget_currency':'CNY',
              'budget_scope':'per person, airfare included'}}
        state=trip_readiness(data)
        self.assertEqual(state['mode'],'PROVISIONAL_MODE')
        self.assertTrue(state['ready_for_provisional_plan'])
        self.assertFalse(state['ready_for_formal_plan'])
        result=analyze_request('日本8天，2027年4月，两人，预算6000元每人含往返机票，上海出发。')
        self.assertEqual(result['planning_level'],'LEVEL_1_PROVISIONAL')
        self.assertTrue(result['provisional_plan_allowed'])
        self.assertFalse(any('想去哪个城市' in q['question'] for q in result['questions']))
        self.assertIn('destination_choice',result['missing_critical_fields'])

    def test_discoverable_domains_are_not_user_questions(self):
        result=analyze_request('我不知道大阪住哪里，我不知道去哪些景点，机票你帮我看看，交通你安排就行。')
        questions=' '.join(q['question'] for q in result['questions'])
        for low_value in ('住哪里','哪些景点','坐什么交通','哪家酒店'):
            self.assertNotIn(low_value,questions)
        domains={row['domain'] for row in result['agent_discovery']['research_queue']}
        self.assertTrue({'lodging','flights','attractions','transit','restaurants'} <= domains)
        self.assertTrue({'lodging_candidates','flight_candidates','attraction_candidates','transit_candidates','restaurant_candidates'} <= set(result['agent_discovery']['candidate_sets']))

    def test_explicit_lodging_area_triggers_hotel_discovery_without_address_question(self):
        result=analyze_request('我就想住心斋桥，帮我安排大阪旅行。')
        self.assertEqual(result['trip_profile']['lodging_area'],'心斋桥')
        self.assertEqual(result['route_state'],'AREA_LEVEL_ANCHOR')
        self.assertIn('lodging', [x['domain'] for x in result['agent_discovery']['research_queue']])

    def test_auto_decision_mode_requires_explicit_delegation_and_keeps_choices_editable(self):
        self.assertTrue(decision_mode('这些我都不知道，你全帮我决定。'))
        self.assertFalse(decision_mode('我还没想好住宿区域。'))
        result=analyze_request('大阪8天，2027年4月，两人，预算每人6000元含往返机票，上海出发，这些我都不知道，你全帮我决定。')
        self.assertEqual(result['decision_mode'],'AUTO_DECISION_MODE')
        self.assertEqual(result['agent_discovery']['after_research_state'],'FINAL_OPTIMIZATION')
        self.assertEqual(result['agent_discovery']['selection_status']['lodging'],'DISCOVERING')

    def test_candidate_proposal_requires_sources_and_auto_selects_only_researched_option(self):
        rows=[{'id':'hotel-a','name':'Hotel A','price':100,'source_url':'https://hotel.example/rate',
               'checked_at':'2026-10-07T00:00:00Z','pros':['cheap'],'cons':['far']}]
        proposal=propose_candidates('lodging',rows,recommendation_id='hotel-a',auto_decision=True)
        self.assertEqual(proposal['decision_status'],'AUTO_SELECTED')
        self.assertEqual(proposal['recommendation']['id'],'hotel-a')
        self.assertFalse(proposal['user_choice_needed'])
        bad=propose_candidates('flight',[{'id':'fake','name':'unverified'}],recommendation_id='fake',auto_decision=True)
        self.assertEqual(bad['status'],'DISCOVERING')
        self.assertEqual(len(bad['rejected']),1)

    def test_unavailable_candidates_degrade_without_asking_user_to_research(self):
        result=propose_candidates('transit',[],search_status='unavailable')
        self.assertEqual(result['status'],'UNAVAILABLE')
        self.assertFalse(result['candidates'])
        self.assertFalse(ask_value_test({'class':'AGENT_DISCOVERABLE'}))
        self.assertTrue(ask_value_test({'class':'USER_REQUIRED'}))
        self.assertEqual(classify_profile_fields({'flight_candidates':{'status':'unavailable','reason':'fare calendar closed'}})['flight_candidates']['class'],'UNAVAILABLE')


if __name__=='__main__': unittest.main()
