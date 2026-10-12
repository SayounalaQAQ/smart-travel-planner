"""Controlled contracts; real network acceptance is recorded separately."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from trip_entities import selected_attractions,compare_merchants,prepare_entities,entity_errors
from visual_sources import inspect_photo_page,discover_fallback
from image_pipeline import collect_images,image_requirements,licensed_page_image,eligible_image
from delivery_validation import apply_delivery_checks
from test_doubao_delivery_fix import scenario,entry,text_of

def merchant(identifier='h'):
    return dict(id=identifier,name='Contract merchant',address='Evidence-backed sample address',checked_at='2026-10-11T00:00:00Z',
        source_url='https://example.org/merchant',route_fit=True,route_fit_reason='Same district as daily route',
        interest_fit=True,field_evidence={'address':{'value':'Evidence-backed sample address','source_url':'https://example.org/merchant'},
        'interest_fit':{'value':'Matched requested food','source_url':'https://example.org/merchant'}})

class ExperienceContracts(unittest.TestCase):
    def test_namesake_metro_station_is_not_attraction_photo(self):
        item=dict(title='File:Du Fu Thatched Cottage Station Concourse.jpg',description='Chengdu',license='CC0',author='Creator',
            page_url='https://commons.wikimedia.org/wiki/File:Photo.jpg',width=1200,height=800)
        req=dict(aliases=['Du Fu Thatched Cottage'])
        self.assertFalse(eligible_image(item,req)['eligible'])
        req['aliases']=['Du Fu Thatched Cottage Station']
        self.assertTrue(eligible_image(item,req)['eligible'])

    def test_disabled_commons_still_allows_noncommons_license_candidates(self):
        req=dict(attraction_id='x',name='西岛',aliases=['西岛'])
        plan={'image_source_policy':{'commons_enabled':False},'attractions':[dict(id='x',name='西岛')],
            'image_selections':[dict(attraction_id='x',page_url='https://www.flickr.com/photos/person/1/',image_url='https://example.org/a.jpg')]}
        with patch('visual_sources.openverse_candidates',return_value=[dict(page_url='https://commons.wikimedia.org/wiki/File:X.jpg')]),patch('image_pipeline.verify_supplied_images',return_value={'images':[{'attraction_id':'x'}],'rejected':[]}) as verifier:
            result=discover_fallback(plan,req,Path('unused'),object())
        self.assertEqual(len(result['images']),1);self.assertEqual(verifier.call_count,1)
        self.assertNotIn('commons.wikimedia.org',verifier.call_args.args[0]['images'][0]['page_url'])
    def test_selected_core_controls_image_slots(self):
        plan={'attractions':[{'id':str(i),'name':'Place '+str(i),'selected':i in (6,8)} for i in range(9)]}
        self.assertEqual([r['attraction_id'] for r in image_requirements(plan)],['6','8'])

    def test_photo_reference_requires_direct_relevant_page(self):
        req=dict(attraction_id='x',aliases=['西岛'])
        body='<title>西岛官方介绍</title><img src="/island.jpg" alt="西岛景区">'
        ref=inspect_photo_page(body,'https://example.org/island',req)
        self.assertEqual(ref['photo_match'],'VERIFIED');self.assertEqual(ref['copy_permission'],'NOT_ESTABLISHED')
        for url in ('https://example.org/','https://example.org/search/island'):
            with self.assertRaises(ValueError):inspect_photo_page(body,url,req)
        with self.assertRaises(ValueError):inspect_photo_page('<title>Other place</title>','https://example.org/a',req)

    def test_og_image_or_logo_is_not_photo_identity(self):
        body='<title>西岛</title><meta property="og:image" content="/logo.jpg"><img src="/logo.jpg" alt="西岛">'
        ref=inspect_photo_page(body,'https://example.org/island',dict(attraction_id='x',aliases=['西岛']))
        self.assertEqual(ref['photo_match'],'UNCONFIRMED')

    def test_noncommercial_or_disclaimer_not_embedded(self):
        for license in ('https://creativecommons.org/licenses/by-nc-sa/2.0/','版权归原作者'):
            body='<script type="application/ld+json">'+json.dumps({'@type':'ImageObject','contentUrl':'https://example.org/a.jpg','license':license,'creator':{'name':'A'}})+'</script>'
            with self.assertRaises(ValueError):licensed_page_image(body,'https://example.org/a.jpg')

    def test_fallback_keeps_failure_and_real_page_contract_separate(self):
        req=dict(attraction_id='x',name='西岛',aliases=['西岛'])
        plan={'attractions':[dict(id='x',name='西岛',source_url='https://example.org/island')]}
        result=discover_fallback(plan,req,Path('unused'),object(),live=False,
            loader=lambda url:('<title>西岛</title><img src="/sea.jpg" alt="西岛实拍">',url))
        self.assertEqual(result['references'][0]['photo_match'],'VERIFIED');self.assertFalse(result['images'])

    def test_tls_circuit_avoids_repeating_dead_endpoint(self):
        class Dead:
            calls=0
            def commons_images(self,*a,**k):self.calls+=1;raise OSError('SSL handshake timed out')
        service=Dead()
        with tempfile.TemporaryDirectory() as tmp:
            result=collect_images({'attractions':[dict(id=str(i),name='Place'+str(i)) for i in range(4)]},tmp,service=service)
        self.assertEqual(service.calls,1);self.assertEqual(len(result['requirements']),4)
        self.assertTrue(all(r['visual_status']=='NO_VERIFIED_VISUAL_SOURCE' for r in result['requirements']))

    def test_hotel_choice_requires_evidence_not_search_rank(self):
        bad=merchant('first');bad['field_evidence']={}
        good=merchant('second')
        result=compare_merchants([bad,good],'hotel',{})
        self.assertEqual(result['selected_id'],'second');self.assertFalse(result['evaluations'][0]['eligible'])
        self.assertIn('recent_independent_reviews',result['evaluations'][1]['unknowns'])

    def test_merchant_cost_added_once_and_never_becomes_quote(self):
        c=merchant();c['selected']=True;c['planning_cost']=dict(amount=300,currency='CNY',scope='PER_NIGHT',quantity=2,
            unit_scope='PER_ROOM',room_count=1,cost_type='ESTIMATED',source_url=c['source_url'],checked_at=c['checked_at'],estimation_basis='Explicit allowance, not price')
        plan=prepare_entities({'trip_profile':{'traveler_count':1},'hotel_candidates':[c]})
        self.assertEqual(len(prepare_entities(plan)['cost_ledger']),1);self.assertEqual(plan['cost_ledger'][0]['cost_type'],'ESTIMATED')

    def test_arrival_reverse_rejected_through_standard_entry(self):
        plan=scenario();plan['days'][0]['execution_nodes']=[dict(role='HOTEL',place='Hotel',place_id='hotel'),
            dict(role='AIRPORT',place='Origin airport',place_id='origin-airport')]
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(plan,tmp)
            self.assertNotEqual(result.returncode,0);self.assertIn('ARRIVAL_DIRECTION_CONFLICT',{e['code'] for e in report['errors']})

    def test_shared_geography_conflict_rejected(self):
        p={'place_registry':[dict(id='pier',name='Pier',district='Sourced district')],
           'days':[{'execution_nodes':[dict(role='ACTIVITY',place='Pier',place_id='pier',district='Different district')]}]}
        self.assertEqual(entity_errors(p)[0]['code'],'GEOGRAPHIC_ENTITY_CONFLICT')

    def test_departure_cutoff_rejects_distant_sight(self):
        p={'days':[dict(day_type='DEPARTURE',return_constraint=dict(departure_time='16:00',airport_buffer_minutes=120,transfer_allowance_minutes=90,luggage_minutes=30),
           execution_nodes=[dict(role='ACTIVITY',place='Far sight',place_id='sight',time='11:00',end_time='13:00')])]}
        self.assertEqual(entity_errors(p)[0]['code'],'RETURN_BUFFER_CONFLICT')

    def test_selected_meal_must_be_routed(self):
        c=merchant('restaurant');c['selected']=True
        errors=entity_errors({'restaurant_candidates':[c]})
        self.assertIn('SELECTED_MEAL_NOT_ROUTED',{e['code'] for e in errors})

    def test_luggage_or_meal_can_also_break_departure_buffer(self):
        for role in ('HOTEL','MEAL'):
            p={'days':[dict(day_type='DEPARTURE',return_constraint=dict(departure_time='16:00',airport_buffer_minutes=120,transfer_allowance_minutes=90,luggage_minutes=30),
              execution_nodes=[dict(role=role,place='Late stop',place_id='hotel',time='12:30')])]}
            self.assertIn('RETURN_BUFFER_CONFLICT',{e['code'] for e in entity_errors(p)})

    def test_budget_cannot_omit_selected_merchant_allowance(self):
        plan=scenario();c=merchant();c['selected']=True
        c['planning_cost']=dict(amount=8000,currency='CNY',scope='PER_PARTY',quantity=1,cost_type='ESTIMATED',source_url=c['source_url'],checked_at=c['checked_at'])
        plan['hotel_candidates']=[c]
        codes={e['code'] for e in apply_delivery_checks(plan)['delivery_validation']['errors']}
        self.assertIn('MERCHANT_BUDGET_CONFLICT',codes)

    def test_short_actual_docx_translates_budget_and_omits_empty_food_heading(self):
        plan=scenario();plan['days']=plan['days'][:3];plan['trip_profile'].update(end_date='2027-07-23',duration_days=3,intercity_mode='AIR',sleep_schedule='regular')
        plan['key_decisions']=['Choose local area','Keep buffer']
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(plan,tmp);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            text=text_of(report['document'])
            self.assertNotIn('餐饮候选与排队备选',text);self.assertNotIn('recommended / accommodation',text)
            self.assertIn('常规作息',text);self.assertIn('飞机',text);self.assertIn('住宿',text);self.assertIn('1. Choose local area',text)

if __name__=='__main__':unittest.main()
