"""Synthetic unit/integration inputs; never used to prove live acceptance."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cost_ledger import party_amount, reconcile_budget, validate_quote
from execution_graph import build_execution_graph, route_closure, record_route_attempts
from execution_readiness import evaluate_plan
from state_consistency import sync_profile, validate_state
from budget_closure_replanning import replan_budget, budget_research_tasks
from live_evidence_guard import validate_live_evidence
from data_freshness import freshness

NOW = '2026-10-10T06:00:00Z'


def profile():
    return dict(start_date='2027-04-20', end_date='2027-04-21', duration_days=2, traveler_count=2,
                destination='Osaka', origin='Shanghai', lodging_area='Minami', hotel='Hotel A', hotel_address='Test address',
                origin_airport='PVG', arrival_airport='KIX', departure_airport='KIX', return_airport='PVG',
                hotel_quote_id='hq', flight_quote_id='fq', budget_amount=6000, budget_currency='CNY', budget_scope='PER_PERSON',
                budget_categories=['flight','hotel','transit','food','attractions'], preferred_start_time='09:30')


def quotes(hotel=1000):
    h = dict(quote_id='hq', hotel_name='Hotel A', check_in='2027-04-20', check_out='2027-04-21', guest_count=2,
             room_count=1, room_type='Twin', total_price=hotel, currency='CNY', scope='PER_PARTY',
             price_type='EXACT_DATE_PRICE', availability='AVAILABLE', source_url='https://hotel.example/quote', checked_at=NOW)
    f = dict(quote_id='fq', origin_airport='PVG', destination_airport='KIX', outbound_date='2027-04-20', return_date='2027-04-21',
             trip_type='ROUND_TRIP', airline='Unit test airline', itinerary_id='fixture-roundtrip', departure_time='10:00', arrival_time='13:00',
             price=2000, currency='CNY', scope='PER_PERSON', traveler_count=2, status='EXACT_DATE_QUOTE',
             source_url='https://air.example/quote', checked_at=NOW,
             legs=[dict(direction='OUTBOUND', date='2027-04-20', flight_number='TEST001', origin_airport='PVG', destination_airport='KIX', departure_time='10:00',arrival_time='13:00'),
                   dict(direction='RETURN', date='2027-04-21', flight_number='TEST002', origin_airport='KIX', destination_airport='PVG', departure_time='15:00',arrival_time='17:00')])
    return h,f


def cost(category, amount, scope='PER_PERSON', **extra):
    return dict(id=category, category=category, item=category, amount=amount, currency='CNY', scope=scope, quantity=1,
                traveler_count=2, cost_type='CURRENT_REFERENCE', source='https://official.example/price', checked_at=NOW, **extra)


def complete_plan(hotel=1000, transit=100):
    h,f = quotes(hotel)
    ledger = [cost('flight',2000), cost('hotel',hotel,'PER_PARTY'), cost('transit',transit),cost('food',100),cost('attractions',0)]
    ledger[0].update(cost_type='VERIFIED_QUOTE',quote_id='fq')
    ledger[1].update(cost_type='VERIFIED_QUOTE',quote_id='hq')
    p = dict(mode='TEST_SYNTHETIC',trip_profile=profile(),hotel_availability=[h],flight_availability=[f],cost_ledger=ledger,
             days=[dict(date='2027-04-20',itinerary_nodes=[dict(role='ACTIVITY',place='Museum',place_id='museum',activity='Museum',time='11:00',operations_checked=True,source_url='https://official.example/museum',checked_at=NOW)]),
                   dict(date='2027-04-21',itinerary_nodes=[])])
    # Fully specified route fixture is explicitly test-only.
    for i,d in enumerate(p['days']):
        graph = build_execution_graph(p['trip_profile'],d,i)
        for e in graph['edges']:
            e.update(status='VERIFIED',mode='FLIGHT' if e['purpose']=='flight' else 'METRO',
                     duration_minutes=30,source_url='https://operator.example/route',checked_at=NOW,
                     operator='Test operator',line='Test line',applicable_date=d['date'],
                     departure_time='10:00',arrival_time='10:30',check_in_deadline='12:00',buffer_minutes=90,quote_id='fq')
            if e['mode']=='FLIGHT':
                e.update(departure_time='10:00' if i==0 else '15:00',arrival_time='13:00' if i==0 else '17:00')
        d['execution_graph'] = graph
    return p


class ExecutionClosureTests(unittest.TestCase):
    def test_execution_graph_covers_every_location_change(self):
        day=dict(date='2027-04-21', itinerary_nodes=[dict(place='Kuromon',place_id='kuromon'),dict(role='REST',place='Hotel A',place_id='hotel'),dict(place='Dotonbori',place_id='dotonbori'),dict(role='MEAL',place='Restaurant',place_id='restaurant')])
        p=profile(); p['end_date']='2027-04-22'
        graph=build_execution_graph(p,day,1)
        self.assertEqual(len(graph['nodes']),6)
        self.assertEqual(len(graph['edges']),5)
        self.assertEqual([e['to_place_id'] for e in graph['edges']],['kuromon','hotel','dotonbori','restaurant','hotel'])

    def test_route_structure_complete_does_not_mean_verified(self):
        graph=build_execution_graph(profile(),dict(date='2027-04-20',activities=[]))
        result=route_closure(graph,now=NOW)
        self.assertEqual(result['route_structure_status'],'COMPLETE')
        self.assertEqual(result['route_coverage'],0)
        self.assertEqual(result['route_verification_status'],'UNAVAILABLE')

    def test_missing_return_edge_is_structural_failure(self):
        plan=complete_plan(); graph=plan['days'][0]['execution_graph']; graph['edges'].pop()
        self.assertEqual(route_closure(graph,now=NOW)['route_structure_status'],'INCOMPLETE')

    def test_unavailable_critical_edge_blocks_execution_ready(self):
        plan=complete_plan(); plan['days'][0]['execution_graph']['edges'][0]['status']='UNAVAILABLE'
        out=evaluate_plan(plan,now=NOW)
        self.assertIn('CRITICAL_ROUTE_EDGES_UNRESOLVED',out['readiness']['blocking_reasons'])
        self.assertEqual(out['readiness']['booking_readiness'],'NOT_READY')

    def test_arrival_day_starts_from_airport(self):
        nodes=build_execution_graph(profile(),dict(date='2027-04-20',activities=[]))['nodes']
        self.assertEqual([n['role'] for n in nodes[:3]],['AIRPORT','AIRPORT','HOTEL'])

    def test_departure_day_contains_two_airports(self):
        graph=build_execution_graph(profile(),dict(date='2027-04-21',activities=[]),1)
        self.assertEqual([n['role'] for n in graph['nodes']],['HOTEL','AIRPORT','AIRPORT'])

    def test_current_route_reference_cannot_count_as_verified(self):
        graph=complete_plan()['days'][0]['execution_graph']; graph['edges'][0]['status']='CURRENT_REFERENCE'
        result=route_closure(graph,now=NOW)
        self.assertEqual(result['route_coverage'],1)
        self.assertLess(result['verified_edges'],result['required_edges'])

    def test_unknown_property_blocks_precise_last_mile(self):
        p=profile(); p.pop('hotel_address'); graph=build_execution_graph(p,dict(date='2027-04-20',activities=[]))
        self.assertEqual(graph['edges'][-1]['status'],'UNAVAILABLE')
        self.assertIsNone(graph['edges'][-1]['duration_minutes'])

    def test_cost_scope_per_person_vs_party(self):
        self.assertEqual(party_amount(cost('food',100),2),200)
        self.assertEqual(party_amount(cost('food',100,'PER_PARTY'),2),100)

    def test_explicit_room_night_ride_conversion(self):
        row=cost('hotel',100,'PER_NIGHT',room_count=1,unit_scope='PER_ROOM'); row['quantity']=7
        self.assertEqual(party_amount(row,2),700)
        row=cost('transit',100,'PER_RIDE',unit_scope='PER_PERSON'); row['quantity']=2
        self.assertEqual(party_amount(row,2),400)
        row.pop('unit_scope')
        with self.assertRaises(ValueError): party_amount(row,2)

    def test_unknown_scope_and_count_rejected(self):
        row=cost('food',100); row['scope']='implicit'
        with self.assertRaises(ValueError): party_amount(row,2)
        row=cost('food',100); row['traveler_count']=1
        with self.assertRaises(ValueError): party_amount(row,2)

    def test_budget_allocation_is_not_cost(self):
        plan=complete_plan(); plan['cost_ledger']=[]; plan['budget']={'cap_allocation':{'hotel':12000}}
        result=evaluate_plan(plan,now=NOW)['budget_reconciliation']
        self.assertIsNone(result['party_total']); self.assertEqual(result['known_subtotal_party'],0)

    def test_budget_unknown_if_hotel_or_flight_missing(self):
        for category in ('hotel','flight'):
            plan=complete_plan(); plan['cost_ledger']=[r for r in plan['cost_ledger'] if r['category']!=category]
            budget=evaluate_plan(plan,now=NOW)['budget_reconciliation']
            self.assertEqual(budget['feasibility'],'UNVERIFIED'); self.assertIn(category,budget['unknown_cost_categories'])

    def test_party_total_conversion(self):
        budget=evaluate_plan(complete_plan(),now=NOW)['budget_reconciliation']
        self.assertEqual(budget['party_total'],5400); self.assertEqual(budget['per_person_total'],2700)

    def test_real_quote_contract_required_for_verified_cost(self):
        plan=complete_plan(); plan['hotel_availability'][0].pop('room_count')
        result=evaluate_plan(plan,now=NOW)
        self.assertIn('hotel',result['budget_reconciliation']['unknown_cost_categories'])
        self.assertNotEqual(result['quote_validation']['hotel']['status'],'VERIFIED')

    def test_wrong_quote_amount_cannot_enter_cost(self):
        plan=complete_plan(); plan['cost_ledger'][1]['amount']=10
        budget=evaluate_plan(plan,now=NOW)['budget_reconciliation']
        self.assertTrue(budget['issues']); self.assertIsNone(budget['party_total'])

    def test_complete_inputs_can_reach_booking_ready(self):
        out=evaluate_plan(complete_plan(),now=NOW)
        self.assertEqual(out['state_consistency']['status'],'PASS')
        self.assertEqual(out['readiness']['booking_readiness'],'READY')

    def test_ready_requires_exact_hotel_flight_airport_budget(self):
        for target in ('hotel','flight','airport','budget'):
            plan=complete_plan()
            if target in ('hotel','flight'): plan['trip_profile'].pop(f'{target}_quote_id')
            if target=='airport': plan['trip_profile'].pop('arrival_airport')
            if target=='budget': plan['cost_ledger'][3]['amount']=None
            self.assertNotEqual(evaluate_plan(plan,now=NOW)['readiness']['booking_readiness'],'READY',target)

    def test_expired_quote_downgrades_readiness(self):
        plan=evaluate_plan(complete_plan(),now=NOW)
        expired=evaluate_plan(plan,now='2026-10-11T06:00:00Z')
        self.assertEqual(expired['readiness']['booking_readiness'],'NOT_READY')
        self.assertEqual(expired['readiness']['plan_status'],'DATA_PARTIAL')
        self.assertIn('HOTEL_QUOTE_REFRESH_REQUIRED',expired['readiness']['blocking_reasons'])

    def test_state_date_consistency(self):
        plan=complete_plan(); plan['trip_profile']['duration_days']=8
        self.assertEqual(validate_state(plan)['status'],'FAIL')

    def test_evaluation_does_not_hide_inconsistent_input_replicas(self):
        plan=complete_plan(); plan['profile']={'start_date':'2027-01-01'}
        result=evaluate_plan(plan,now=NOW)
        self.assertEqual(result['state_consistency']['status'],'FAIL')
        self.assertEqual(result['readiness']['plan_status'],'BLOCKED')

    def test_canonical_budget_gate_keeps_airfare_semantics(self):
        from travel_utils import trip_readiness
        p=profile(); p.update(airfare_included=True,travel_window='2027-04-20..21')
        self.assertNotIn('budget_scope',trip_readiness({'trip_profile':p})['missing_critical_fields'])
        p.pop('airfare_included')
        self.assertIn('budget_scope',trip_readiness({'trip_profile':p})['missing_critical_fields'])

    def test_summary_and_date_replicas_update(self):
        plan=complete_plan(); plan['summary']='具体日期未提供'; plan['profile']={'start_date':'2027-01-01'}
        plan['trip_profile']['travel_window']='2027 April; exact dates not provided'
        synced=sync_profile(plan)
        self.assertNotIn('未提供',synced['summary']); self.assertIn('2027-04-20',synced['summary'])
        self.assertEqual(synced['profile'],synced['trip_profile'])
        self.assertEqual(validate_state(synced)['status'],'PASS')

    def test_quote_date_count_and_selection_mismatches_fail(self):
        for field,value in (('check_in','2027-01-01'),('guest_count',1)):
            plan=complete_plan(); plan['hotel_availability'][0][field]=value
            self.assertEqual(evaluate_plan(plan,now=NOW)['state_consistency']['status'],'FAIL')
        plan=complete_plan(); plan['trip_profile'].update(selection_source='AUTO_SELECTED',confirmation_required=True)
        self.assertEqual(evaluate_plan(plan,now=NOW)['state_consistency']['status'],'FAIL')

    def test_provider_failure_not_no_service_and_retries_bounded(self):
        graph=build_execution_graph(profile(),dict(date='2027-04-20',activities=[]))
        attempts=[dict(executed=True,provider='official',query='airport route',checked_at=NOW,result_status='TIMEOUT')]*3
        record_route_attempts(graph,graph['edges'][0]['id'],attempts)
        self.assertEqual(graph['edges'][0]['status'],'UNAVAILABLE')
        with self.assertRaises(ValueError): record_route_attempts(graph,graph['edges'][0]['id'],attempts+[attempts[0]])

    def test_budget_conflict_replans_and_counts_transit_delta(self):
        initial=complete_plan(hotel=10000)
        candidate=complete_plan(hotel=6000,transit=200)
        candidate['trip_profile']['lodging_area']='Honmachi'
        result=replan_budget(initial,[[dict(id='honmachi',name='Honmachi',plan=candidate,source_url='https://hotel.example/quote',checked_at=NOW,additional_total_transit_minutes=30)]],now=NOW)
        self.assertEqual(result['status'],'REPLANNED')
        self.assertEqual(result['final_budget']['per_person_total'],5300)
        self.assertEqual(result['final_plan']['trip_profile']['lodging_area'],'Honmachi')
        self.assertEqual(result['user_question_count'],0)

    def test_budget_search_reconsiders_regions_with_bounds(self):
        tasks=budget_research_tasks(profile())
        self.assertEqual([x['area'] for x in tasks['tasks']],['Minami','Honmachi','Tennoji','Umeda'])
        self.assertEqual(tasks['max_rounds'],3); self.assertFalse(tasks['date_changes_allowed'])

    def test_negligible_saving_or_hard_area_cannot_trigger_revision(self):
        initial=complete_plan(hotel=8000)
        candidate=complete_plan(hotel=7990)
        result=replan_budget(initial,[[dict(id='tiny',plan=candidate,source_url='https://hotel.example/quote',checked_at=NOW)]],now=NOW)
        self.assertFalse(result['revision_ledger'])

    def test_hard_lodging_area_cannot_change(self):
        initial=complete_plan(hotel=10000); initial['trip_profile']['lodging_area_priority']='HARD_CONSTRAINT'
        candidate=complete_plan(hotel=6000); candidate['trip_profile']['lodging_area']='Honmachi'
        result=replan_budget(initial,[[dict(id='h',plan=candidate,source_url='https://hotel.example/quote',checked_at=NOW)]],now=NOW)
        self.assertFalse(result['revision_ledger'])
        self.assertIn('hard lodging area changed',result['candidate_audit'][0]['issues'])

    def test_best_cost_retained_when_gap_cannot_be_closed(self):
        initial=complete_plan(hotel=12000); candidate=complete_plan(hotel=9000)
        result=replan_budget(initial,[[dict(id='lower',plan=candidate,source_url='https://hotel.example/quote',checked_at=NOW)]],now=NOW)
        self.assertEqual(result['status'],'BEST_FOUND_INFEASIBLE')
        self.assertLess(result['final_budget']['per_person_total'],result['initial_budget']['per_person_total'])
        self.assertEqual(result['final_plan']['trip_profile']['budget_amount'],6000)
        self.assertEqual(result['final_plan']['readiness']['booking_readiness'],'NOT_READY')

    def test_duplicate_unknown_cost_is_invalid(self):
        plan=complete_plan(); row=cost('hotel',None); row['cost_type']='UNAVAILABLE'
        plan['cost_ledger']=[row,deepcopy(row)]
        self.assertTrue(evaluate_plan(plan,now=NOW)['budget_reconciliation']['issues'])

    def test_property_and_leg_airport_mismatch_rejected(self):
        h,f=quotes(); h['hotel_name']='Other hotel'
        self.assertIn('HOTEL_PROPERTY_MISMATCH',validate_quote(h,'hotel',profile(),now=NOW)['issues'])
        f['legs'][1]['origin_airport']='NRT'
        self.assertIn('RETURN_AIRPORT_MISMATCH',validate_quote(f,'flight',profile(),now=NOW)['issues'])

    def test_flight_route_cannot_borrow_unrelated_quote_or_clock(self):
        plan=complete_plan(); plan['days'][0]['execution_graph']['edges'][0]['quote_id']='other'
        result=evaluate_plan(plan,now=NOW)
        self.assertEqual(result['readiness']['booking_readiness'],'NOT_READY')
        self.assertIn('CRITICAL_ROUTE_EDGES_UNRESOLVED',result['readiness']['blocking_reasons'])

    def test_expired_route_loses_resolved_coverage(self):
        graph=complete_plan()['days'][0]['execution_graph']
        self.assertEqual(route_closure(graph,now='2026-10-18T06:00:00Z')['resolved_edges'],0)

    def test_provider_expiry_cannot_extend_policy(self):
        row=dict(checked_at=NOW,valid_until='2027-01-01T00:00:00Z')
        self.assertTrue(freshness(row,'flight_quote',now='2026-10-10T13:00:00Z')['refresh_required'])

    def test_live_guard_rejects_fixture_and_claimed_quote(self):
        result=validate_live_evidence(complete_plan(),dict(kind='LIVE_HOST_WEB',raw_results_file='actual-web.json',verified_quotes=[]))
        self.assertEqual(result['status'],'FAIL')
        self.assertIn('SYNTHETIC_EVIDENCE_FORBIDDEN',result['issues'])
        self.assertIn('VERIFIED_COST_WITHOUT_LIVE_QUOTE_EVIDENCE',result['issues'])

    def test_routine_meals_and_rest_not_duplicate_attractions(self):
        from travel_readiness import detect_diversity_conflicts
        days=[dict(activities=[dict(activity='午餐与休息',node_role='MEAL')]),dict(activities=[dict(activity='午餐与休息',node_role='MEAL')])]
        self.assertEqual(detect_diversity_conflicts(days),[])
        for d in days: d['activities'][0]['restaurant']='Named restaurant'
        self.assertIn('DUPLICATE_RESTAURANT',[r['code'] for r in detect_diversity_conflicts(days)])

    def test_departure_without_sightseeing_is_valid_travel_day(self):
        from travel_utils import validate_trip
        p=complete_plan(); p['days'][1]['day_type']='DEPARTURE'
        p=evaluate_plan(p,now=NOW)
        self.assertFalse(any('has no activities' in e for e in validate_trip(p)))


if __name__=='__main__': unittest.main()
