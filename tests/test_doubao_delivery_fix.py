"""Doubao-reported regression contracts, including real bundled-entry DOCX execution.

The plan and numerical allowances are explicit engineering inputs, not travel facts.
No exact future quotes or official future event announcement is fabricated.
"""
import copy,json,os,subprocess,sys,tempfile,unittest,zipfile,io
from unittest.mock import patch
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from delivery_validation import weekday,event_confirmed,apply_delivery_checks
from image_pipeline import licensed_page_image,verify_supplied_images

def scenario():
    profile={'destination':'Tokyo','start_date':'2027-07-21','end_date':'2027-07-27','duration_days':7,
        'traveler_count':2,'origin':'Example departure city','budget_amount':10000,'budget_currency':'CNY',
        'budget_scope':'PER_PARTY','airfare_included':True,'lodging_area':'Tokyo area under research',
        'selection_source':'USER_SELECTED','confirmation_status':'USER_CONFIRMED','preferred_start_time':'10:00',
        'walking_tolerance_steps':12000}
    places=['Asakusa','Akihabara','Harajuku','Ikebukuro','Odaiba','Shinjuku','Tokyo departure buffer']
    days=[{'date':f'2027-07-{21+i}','area':place,'theme':'区域探索建议','estimated_steps':7000,
        'steps_basis':'规划假设，真实路线尚未核验','route_state':'AREA_LEVEL_ANCHOR','route_origin':'Tokyo area under research',
        'activities':[{'time':'10:30','activity':place+' 区域自由探索' if i<6 else '返程与行李缓冲','place':place,
            'note':'初步安排；目标日期运营与完整路线待核验，暂不安排任何未官宣的固定活动'}],
        'rain_plan':'遇雨缩短户外停留，改同一区域室内自由活动；具体商户先查营业。'} for i,place in enumerate(places)]
    return {'title':'东京七日初步规划交付检查','trip_profile':profile,'days':days,
        'budget':{'currency':'CNY','traveler_count':2,'note':'三档金额均为明确的工程规划假设，不是目标日期机酒报价。',
            'scenarios':{'low':{'transport':1600,'accommodation':1800,'food':1400,'misc':240},
                         'recommended':{'transport':2000,'accommodation':2400,'food':1600,'misc':120},
                         'comfortable':{'transport':4000,'accommodation':5000,'food':3000,'misc':400}}},
        'seasonal_events':[{'id':'fireworks','name':'东京夏季花火候选','date':'2027-07-31','status':'HISTORICAL_PATTERN',
            'experience':'历史举办规律仅作候选，尚无目标年份官方日期证据；不纳入七日每日安排。',
            'alternative':'按原区域自由探索，不改变用户旅行窗口。'}],
        'risks':['未来机票、酒店及运营资料尚未取得；出发前复查天气、价格和开放信息。'],
        'checklist':['取得目标日期往返交通和酒店完整报价后，再核算真实预算。'],
        'bookings':['本手册不代表已预约、已订到或可直接预订。']}

def entry(plan,out,*args):
    source=Path(out)/'input.json';source.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
    env=dict(os.environ,PLUGIN_ROOT=str(ROOT),CLAUDE_PLUGIN_ROOT=str(ROOT),PYTHONIOENCODING='utf-8')
    result=subprocess.run([sys.executable,str(ROOT/'skills/smart-travel-planner/scripts/plugin_entry.py'),'deliver',
        '--input',str(source),'--output-dir',str(Path(out)/'delivery'),'--skip-images',*args],env=env,
        capture_output=True,text=True,encoding='utf-8',timeout=60)
    return result,json.loads(result.stdout)

def text_of(doc):
    with zipfile.ZipFile(doc) as z:
        xml=ET.fromstring(z.read('word/document.xml'))
        return ' '.join(n.text or '' for n in xml.iter() if n.tag.endswith('}t'))

class DeliveryRegression(unittest.TestCase):
    def test_all_seven_weekdays_and_last_saturday(self):
        self.assertEqual([weekday(f'2027-07-{d}') for d in range(21,28)],['星期三','星期四','星期五','星期六','星期日','星期一','星期二'])
        self.assertEqual(weekday('2027-07-31'),'星期六')
        self.assertFalse(event_confirmed(scenario()['seasonal_events'][0]))

    def test_entry_delivers_actual_docx_without_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(scenario(),tmp)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(report['status'],'DELIVERED');self.assertEqual(report['booking_readiness'],'NOT_READY')
            self.assertEqual(report['planning_delivery']['data_state'],'QUOTE_NOT_OBTAINED')
            self.assertFalse(report['budget_verified']);self.assertTrue(report['official_validation_passed'])
            self.assertEqual(report['artifact_type'],'PLUGIN_STANDARD');self.assertEqual(report['generator']['exit_code'],0)
            doc=Path(report['document']);self.assertTrue(doc.is_file());text=text_of(doc)
            for d in range(21,28):self.assertIn(f'2027-07-{d} '+weekday(f'2027-07-{d}'),text)
            self.assertIn('尚不具备预订条件',text);self.assertIn('未核实',text)
            self.assertNotIn('2027-07-31',text)
            self.assertIn('CNY 5,040.00',text);self.assertIn('CNY 2,520.00',text);self.assertIn('CNY 2,400.00',text)
            for command in json.loads((doc.parent/'delivery-report.json').read_text(encoding='utf-8'))['attempts']:
                if command.get('script')=='build_docx.py':self.assertEqual(Path(command['command'][1]),ROOT/'scripts/build_docx.py')

    def test_missing_budget_scope_still_blocks_and_explains(self):
        plan=scenario();del plan['trip_profile']['budget_scope']
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(plan,tmp);self.assertNotEqual(result.returncode,0)
            self.assertTrue(any(e['field']=='trip_profile.budget_scope' for e in report['errors']))
            self.assertIsNone(report['generated_by']);self.assertFalse(report['official_validation_passed'])
            self.assertIsNone(report['document'])

    def test_explicit_user_scope_text_maps_without_guessing(self):
        plan=scenario();plan['trip_profile']['budget_scope']='全团总预算含机票';del plan['trip_profile']['airfare_included']
        data=apply_delivery_checks(plan)
        self.assertEqual(data['trip_profile']['budget_scope'],'PER_PARTY');self.assertTrue(data['trip_profile']['airfare_included'])
        self.assertEqual(data['delivery_validation']['status'],'PASS')

    def test_known_walking_and_sleep_conflicts_still_block_actual_entry(self):
        for walking in (False,True):
            plan=scenario()
            if walking:plan['days'][1]['estimated_steps']=16000
            else:plan['days'][1]['activities'][0]['time']='07:00'
            with tempfile.TemporaryDirectory() as tmp:
                result,report=entry(plan,tmp);self.assertNotEqual(result.returncode,0)
                code='WALKING_CONFLICT' if walking else 'SLEEP_SCHEDULE_CONFLICT'
                self.assertIn(code,{x['code'] for x in report['errors']});self.assertFalse(report['official_validation_passed'])

    def test_wrong_weekday_is_correctable_error(self):
        plan=scenario();plan['days'][0]['weekday']='星期一'
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(plan,tmp);self.assertNotEqual(result.returncode,0)
            self.assertTrue(any(e['code']=='WEEKDAY_MISMATCH' and e['repair']=='星期三' for e in report['errors']))

    def test_written_weekday_is_also_checked(self):
        plan=scenario();plan['subtitle']='2027-07-21（星期五）'
        self.assertTrue(any(e['code']=='WEEKDAY_MISMATCH' for e in apply_delivery_checks(plan)['delivery_validation']['errors']))

    def test_scheduled_historical_future_event_is_rejected(self):
        plan=scenario();plan['days'][3]['activities'][0].update(activity='东京夏季花火候选',event_id='fireworks')
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(plan,tmp);self.assertNotEqual(result.returncode,0)
            codes={e['code'] for e in report['errors']}
            self.assertIn('EVENT_YEAR_EVIDENCE_MISSING',codes);self.assertIn('EVENT_DATE_OUTSIDE_WINDOW',codes)

    def test_official_label_without_year_evidence_is_not_confirmation(self):
        event={'status':'OFFICIALLY_ANNOUNCED','date':'2027-07-31','official_source_url':'https://example.org/event',
               'date_evidence':{'source_url':'https://example.org/event','source_type':'official','checked_at':'2026-10-11T00:00:00Z',
                   'applicable_year':2026,'value':'2027-07-31','excerpt':'Historical July pattern'}}
        self.assertFalse(event_confirmed(event))

    def test_tiers_computed_from_components(self):
        check=apply_delivery_checks(scenario())['delivery_validation'];self.assertEqual(check['status'],'PASS')
        self.assertEqual([check['budget_math'][x]['total'] for x in ('low','recommended','comfortable')],[5040,6120,12400])
        for spec in check['budget_math'].values():
            self.assertAlmostEqual(sum(spec['components'].values()),spec['total']);self.assertAlmostEqual(spec['per_person']*2,spec['total'])
            self.assertEqual(spec['budget_gap'],max(0,spec['total']-10000))

    def test_wrong_total_and_gap_block_actual_entry(self):
        for field in ('total','per_person','budget_gap'):
            plan=scenario();plan['budget']['scenarios']['low'][field]=1
            with tempfile.TemporaryDirectory() as tmp:
                result,report=entry(plan,tmp);self.assertNotEqual(result.returncode,0)
                self.assertTrue(any(e['code']=='BUDGET_ARITHMETIC_MISMATCH' for e in report['errors']))

    def test_unlicensed_photo_omitted_by_actual_entry(self):
        plan=scenario();plan['attractions']=[{'id':'a','name':'Asakusa','why_visit':'区域自由探索建议'}]
        plan['images']=[{'attraction_id':'a','license':'版权归原作者，仅供参考','local_path':'not-a-licensed-image.jpg'}]
        with tempfile.TemporaryDirectory() as tmp:
            result,report=entry(plan,tmp);self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            with zipfile.ZipFile(report['document']) as z:self.assertFalse(any(n.startswith('word/media/') for n in z.namelist()))
            self.assertTrue(report['image_validation']['rejected'])
            self.assertIn('未嵌入景点照片',text_of(report['document']))

    def test_commercial_disclaimer_is_not_permission(self):
        with self.assertRaises(ValueError):licensed_page_image('<p>版权归原作者，仅供参考</p>','https://example.org/a.jpg')

    def test_other_original_source_requires_image_specific_license(self):
        body='<script type="application/ld+json">'+json.dumps({'@type':'ImageObject','name':'Sample Temple',
            'contentUrl':'https://example.org/a.jpg','license':'https://creativecommons.org/licenses/by-sa/4.0/',
            'creator':{'@type':'Person','name':'Example creator'}})+'</script>'
        meta=licensed_page_image(body,'https://example.org/a.jpg');self.assertEqual(meta['license'],'CC BY-SA 4.0')
        self.assertEqual(meta['author'],'Example creator')
        with self.assertRaises(ValueError):licensed_page_image(body,'https://example.org/commercial.jpg')

    def test_verified_metadata_contract_can_embed_via_bundled_builder(self):
        # Controlled source/pixels only, not proof of an actual online license.
        from PIL import Image
        pixels=io.BytesIO();Image.new('RGB',(1200,800),'gray').save(pixels,format='JPEG')
        row={'title':'File:Example Temple.jpg','page_url':'https://commons.wikimedia.org/wiki/File:Example_Temple.jpg',
             'image_url':'https://upload.wikimedia.org/example.jpg','artist':'Example creator',
             'license':'CC BY-SA 4.0','width':1200,'height':800}
        class Service:
            @staticmethod
            def commons_images(*a,**k):return {'results':[row]}
        with tempfile.TemporaryDirectory() as tmp:
            plan=scenario();plan['attractions']=[{'id':'temple','name':'Example Temple'}]
            plan['images']=[{'attraction_id':'temple',**row}]
            sys.path.insert(0,str(ROOT/'mcp-server/src'))
            with patch('security.network.request_bytes',return_value=(pixels.getvalue(),'image/jpeg','utf-8',row['image_url'])):
                result=verify_supplied_images(plan,Path(tmp)/'images',service=Service())
            self.assertEqual(result['status'],'PASS');plan['images']=result['images']
            source=Path(tmp)/'plan.json';source.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
            doc=Path(tmp)/'positive-image.docx'
            cmd=[sys.executable,str(ROOT/'skills/smart-travel-planner/scripts/plugin_entry.py'),'--plugin-root',str(ROOT),'build',
                 '--input',str(source),'--output',str(doc),'--image-root',str(Path(tmp)/'images')]
            built=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8');self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            checked=subprocess.run([sys.executable,str(ROOT/'scripts/validate_docx.py'),str(doc),'--plan',str(source),'--require-images'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr);self.assertEqual(json.loads(checked.stdout)['images'],1)

    def test_booking_requirement_still_fails_for_provisional_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            _,report=entry(scenario(),tmp)
            checked=subprocess.run([sys.executable,str(ROOT/'scripts/validate_plan_readiness.py'),report['plan'],'--purpose','planning','--require-ready'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(checked.returncode,2)
            self.assertEqual(json.loads(checked.stdout)['readiness']['booking_readiness'],'NOT_READY')

    def test_post_generation_tampering_is_rejected(self):
        for old,new,code in [('2027-07-21 星期三','2027-07-21 星期一','DOCUMENT_WEEKDAY_MISMATCH'),
                              ('CNY 5,040.00','CNY 5,041.00','DOCUMENT_BUDGET_MISMATCH')]:
            with tempfile.TemporaryDirectory() as tmp:
                _,report=entry(scenario(),tmp);doc=Path(report['document']);tampered=doc.parent/'tampered.docx'
                with zipfile.ZipFile(doc) as z,zipfile.ZipFile(tampered,'w') as target:
                    for item in z.infolist():
                        data=z.read(item.filename)
                        if item.filename=='word/document.xml':data=data.replace(old.encode(),new.encode())
                        target.writestr(item,data)
                result=subprocess.run([sys.executable,str(ROOT/'scripts/validate_docx.py'),str(tampered),'--plan',report['plan']],capture_output=True,text=True,encoding='utf-8')
                self.assertNotEqual(result.returncode,0);self.assertIn(code,{e['code'] for e in json.loads(result.stdout)['consistency_errors']})

if __name__=='__main__':unittest.main()
