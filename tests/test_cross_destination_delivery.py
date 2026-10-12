"""Controlled consistency contracts; actual user/network acceptance lives outside ZIP."""
import copy,json,sys,tempfile,subprocess,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from handbook_validation import validate_boundaries,cost_coverage,prepare_required_costs,verification_priority
from public_rendering import public_text,public_text_errors
from execution_graph import build_execution_graph
from test_doubao_delivery_fix import scenario,entry,text_of

def anchor(id,role='HOTEL'):
    return dict(place_id=id,place='Contract '+id,role=role,location_status='UNRESOLVED',status='CANDIDATE')
def d(start,end,date='2027-07-21'):
    return dict(date=date,start_anchor=anchor(start),overnight_anchor=anchor(end),execution_nodes=[anchor(start),anchor('visit','ACTIVITY'),anchor(end)])
def costs(amounts):
    ledger=[dict(id=str(i),category='intercity_rail' if i==0 else 'station_transfer',item='Contract segment',currency='CNY',scope='PER_PERSON',quantity=1,traveler_count=1,cost_type='ESTIMATED',amount=x,source_url='https://example.org/source',checked_at='2026-10-12',estimation_basis='Contract allowance') for i,x in enumerate(amounts)]
    edges=[dict(id='edge'+str(i),cost_id=str(i),from_place_id='from'+str(i),to_place_id='to'+str(i),mode='TRAIN') for i in range(len(amounts))]
    return dict(trip_profile=dict(traveler_count=1,budget_currency='CNY',intercity_mode='TRAIN'),cost_ledger=ledger,days=[{'execution_graph':{'edges':edges}}],budget={'recommended':{'transport':540}})

class CrossDestinationContracts(unittest.TestCase):
    def test_same_hotel_continuity(self):
        self.assertFalse(validate_boundaries({'days':[d('A','A'),d('A','A')]})['errors'])
    def test_changed_hotel_continuity(self):
        self.assertFalse(validate_boundaries({'days':[d('A','B'),d('B','C')]})['errors'])
    def test_city_seasonal_lodge_continuity(self):
        days=[d('city','lodge'),d('lodge','city')];days[0]['overnight_anchor']['seasonal']=True
        result=validate_boundaries({'days':days});self.assertFalse(result['errors']);self.assertEqual(result['warnings'][0]['code'],'SEASONAL_LODGING_UNVERIFIED')
    def test_multicity_requires_actual_transfer_node(self):
        result=validate_boundaries({'days':[d('A','B'),d('C','C')]})
        self.assertIn('OVERNIGHT_CONTINUITY_CONFLICT',{e['code'] for e in result['errors']})
    def test_night_train_and_flight_boundaries(self):
        for role in ('NIGHT_TRANSIT','AIRPORT'):
            a=d('A','overnight');a['overnight_anchor']=anchor('overnight',role);a['execution_nodes'][-1]=anchor('overnight',role)
            b=d('overnight','B');b['start_anchor']=anchor('overnight',role);b['execution_nodes'][0]=anchor('overnight',role)
            self.assertFalse(validate_boundaries({'days':[a,b]})['errors'])
    def test_checkout_day_starts_at_previous_hotel(self):
        b=dict(day_type='DEPARTURE',execution_nodes=[anchor('B'),anchor('station','STATION')])
        self.assertFalse(validate_boundaries({'days':[d('A','B'),b]})['errors'])
    def test_candidate_lodging_does_not_gain_confirmation(self):
        result=validate_boundaries({'days':[d('A','A')]})
        self.assertEqual(result['overnights'][0]['status'],'CANDIDATE')
    def test_explicit_boundary_avoids_default_base_append(self):
        profile=dict(lodging_area='Default city base',start_date='2027-07-20',end_date='2027-07-23')
        day=dict(date='2027-07-21',start_anchor=anchor('A'),overnight_anchor=anchor('B'),itinerary_nodes=[anchor('visit','ACTIVITY')])
        ns=build_execution_graph(profile,day)['nodes']
        self.assertEqual([n['place_id'] for n in ns],['A','visit','B'])
    def test_train_carriage_not_added_as_sight(self):
        p={'days':[{'itinerary_nodes':[dict(role='ACTIVITY',place='高铁车厢',place_id='v')]}]}
        self.assertIn('TRANSPORT_ACTIVITY_DUPLICATION',{e['code'] for e in validate_boundaries(p)['errors']})
    def test_known_rail_transfer_costs_cannot_hide_under_allocation(self):
        p=costs([539,80,120]);r=cost_coverage(p)
        self.assertEqual(r['known_transport_amount'],739);self.assertEqual(r['errors'][0]['code'],'REQUIRED_TRANSPORT_BUDGET_CONFLICT')
    def test_unknown_cost_is_not_zero(self):
        p=costs([200,None]);r=cost_coverage(p)
        self.assertEqual(r['status'],'INCOMPLETE');self.assertIsNone(r['complete_transport_estimate']);self.assertEqual(len(r['unknown_required_edges']),1)
    def test_air_and_rental_car_both_count(self):
        p=costs([300,200]);p['cost_ledger'][0]['category']='flight';p['cost_ledger'][1]['category']='rental_car'
        self.assertEqual(cost_coverage(p)['known_transport_amount'],500)
    def test_shared_roundtrip_package_explicit_and_not_double_counted(self):
        p=costs([200]);e=p['days'][0]['execution_graph']['edges'];e.append({**e[0],'id':'edge-return'})
        self.assertTrue(cost_coverage(p)['errors'])
        p['cost_ledger'][0]['covers_edge_ids']=['edge0','edge-return']
        r=cost_coverage(p);self.assertFalse(r['errors']);self.assertEqual(r['known_transport_amount'],200)
    def test_new_unpriced_edges_get_unknown_records(self):
        p=costs([]);p['days'][0]['execution_graph']['edges']=[dict(id='new',from_place_id='A',to_place_id='B',mode='UNAVAILABLE',purpose='local')]
        prepare_required_costs(p);self.assertIsNone(p['cost_ledger'][0]['amount']);self.assertEqual(p['cost_ledger'][0]['cost_type'],'UNAVAILABLE')
    def test_included_excluded_train_not_inferred_from_flight_flag(self):
        p=costs([]);p['trip_profile'].update(airfare_included=False,intercity_fare_included=True)
        p['days'][0]['execution_graph']['edges']=[dict(id='rail',from_place_id='A',to_place_id='B',mode='TRAIN',purpose='cross_city')]
        prepare_required_costs(p);self.assertFalse(p['cost_ledger'][0]['optional_excluded'])
    def test_priority_uses_actual_days(self):
        p={'trip_profile':{'start_date':'2026-10-16','intercity_mode':'TRAIN'}}
        result=verification_priority(p,'2026-10-12T09:00:00+08:00')
        self.assertEqual(result['days_to_departure'],4);self.assertEqual(result['status'],'DEPARTURE_SOON');self.assertIn('铁路',result['actions'][0]['item'])
        self.assertEqual(verification_priority(p,'2026-01-01T00:00:00+08:00')['status'],'NORMAL')
    def test_public_structures_and_empty_fields(self):
        values=[dict(level='HIGH',risk='Cold',mitigation='Stay warm'),dict(id='private-id',decision='City lodging',reason='No transfer'),dict(when='Before departure',item='Check ticket',note='No booking performed'),[{'item':'A'},None,{'unknown_internal':{'secret':'do not show'}}]]
        for x in values:
            text=public_text(x);self.assertFalse(public_text_errors(text));self.assertNotIn('secret',text);self.assertNotIn('private-id',text)
        self.assertEqual(public_text(None),'');self.assertEqual(public_text({'unsupported':1}),'')
    def test_validator_identifies_section_and_repair(self):
        result=public_text_errors("{'risk': 'raw', 'mitigation': 'raw'}",'省钱与天气备选')
        self.assertEqual(result[0]['code'],'PUBLIC_DATA_STRUCTURE_LEAK');self.assertEqual(result[0]['field'],'省钱与天气备选');self.assertTrue(result[0]['repair'])
    def test_bad_structural_types_return_formal_repair_report(self):
        for key,bad in [('days',{'day':'bad'}),('attractions','bad'),('hotel_candidates',[None])]:
            plan=scenario();plan[key]=bad
            with tempfile.TemporaryDirectory() as tmp:
                r,report=entry(plan,tmp);self.assertNotEqual(r.returncode,0)
                self.assertEqual(report['status'],'BLOCKED');self.assertEqual(report['errors'][0]['code'],'PLAN_DATA_INCOMPLETE');self.assertIsNone(report['document'])
    def test_object_and_null_prose_accepted_without_repr(self):
        plan=scenario();plan.update(risks={'risk':'Unknown connection','mitigation':'Check source'},checklist=None)
        with tempfile.TemporaryDirectory() as tmp:
            r,report=entry(plan,tmp);self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            text=text_of(report['document']);self.assertIn('风险：Unknown connection',text);self.assertNotIn("{'risk'",text)
    def test_formal_docx_with_real_types_and_rail_scope(self):
        plan=scenario();plan['days']=plan['days'][:3];plan['trip_profile'].update(end_date='2027-07-23',duration_days=3,sleep_schedule='normal',intercity_mode='TRAIN',intercity_fare_included=True)
        plan['risks']=[{'level':'HIGH','risk':'Transfer uncertainty','mitigation':'Confirm train'}]
        plan['key_decisions']=[{'id':'hidden','decision':'Stay in town','reason':'Keep return buffer'}]
        plan['checklist']=[{'when':'Departure day','item':'Check clock','note':'No purchase performed'}]
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(plan,tmp);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            text=text_of(report['document']);self.assertNotIn("{'",text);self.assertNotIn('normal',text)
            self.assertIn('包含往返铁路费用',text);self.assertNotIn('本次预算包含往返机票',text)
            self.assertIn('风险：Transfer uncertainty；应对：Confirm train',text)
    def test_actual_docx_tampering_raw_structure_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,report=entry(scenario(),tmp);path=Path(report['document']);bad=path.parent/'bad.docx'
            with zipfile.ZipFile(path) as src,zipfile.ZipFile(bad,'w') as dst:
                for item in src.infolist():
                    data=src.read(item.filename)
                    if item.filename=='word/document.xml':data=data.replace('旅行摘要'.encode(),"{'level': 'HIGH'}".encode(),1)
                    dst.writestr(item,data)
            r=subprocess.run([sys.executable,str(ROOT/'scripts/validate_docx.py'),str(bad)],capture_output=True,text=True,encoding='utf-8')
            self.assertNotEqual(r.returncode,0);self.assertIn('PUBLIC_DATA_STRUCTURE_LEAK',{e['code'] for e in json.loads(r.stdout)['consistency_errors']})

if __name__=='__main__':unittest.main()
