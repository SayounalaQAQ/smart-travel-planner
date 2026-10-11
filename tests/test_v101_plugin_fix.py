"""Controlled contracts, never evidence of a live Claude Code planning run."""
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_trip_request import analyze_request
from experience_discovery import apply_answers,experience_match,recommend_experiences,discover_experiences,research_intents
from image_pipeline import image_requirements,eligible_image,collect_images
from runtime_paths import resolve_plugin_root,standalone_collisions,python_runtime
from build_docx import clarify_currency
from package_plugin import build


class PreferenceContracts(unittest.TestCase):
    def candidates(self):
        return [{'id':tag,'name':tag,'interest_tags':['anime'],'experience_tags':[tag],
                 'coordinates':{'latitude':35.7,'longitude':139.7},'source_url':'https://example.org/'+tag,
                 'checked_at':'2026-10-11T00:00:00Z'} for tag in ('pilgrimage','figure_collecting','retro_games')]

    def test_cash_is_not_travel_budget(self):
        data=analyze_request('我手里有15000，想去日本体验二次元文化、和服、烟花祭和特色风俗。')
        self.assertEqual(data['trip_profile']['available_funds_amount'],15000)
        self.assertNotIn('budget_amount',data['trip_profile'])
        self.assertEqual(data['trip_profile']['destination'],'Japan')
        self.assertFalse(data['formal_plan_allowed'])
        self.assertTrue(any(q['field']=='anime_subtypes' for q in data['questions']))
        self.assertLessEqual(len(data['questions']),5)
        self.assertEqual(data['experience_discovery']['event_date_status'],'UNANNOUNCED_OR_NOT_RESEARCHED')

    def test_answers_change_selected_places(self):
        original={'interests':['anime']}
        a=apply_answers(original,{'anime_subtypes':['pilgrimage']})
        b=apply_answers(original,{'anime_subtypes':['figure_collecting','retro_games']})
        self.assertEqual([x['id'] for x in recommend_experiences(a,self.candidates())['selected']],['pilgrimage'])
        self.assertEqual({x['id'] for x in recommend_experiences(b,self.candidates())['selected']},{'figure_collecting','retro_games'})
        self.assertEqual(original,{'interests':['anime']})

    def test_known_favorite_work_filters_wrong_pilgrimage(self):
        p=apply_answers({}, {'anime_subtypes':['pilgrimage'],'favorite_works':['Work A']})
        self.assertFalse(experience_match(p,{'experience_tags':['pilgrimage'],'related_works':['Work B']})['allowed'])
        self.assertTrue(experience_match(p,{'experience_tags':['pilgrimage'],'related_works':['Work A']})['allowed'])

    def test_generic_anime_does_not_opt_into_specialized_activity(self):
        self.assertFalse(experience_match({'interests':['anime']},{'specialized_interest':'otome'})['allowed'])

    def test_adult_activities_need_both_confirmations(self):
        self.assertFalse(experience_match({}, {'adult_only':True})['allowed'])
        p=apply_answers({}, {'adult_include':True})
        self.assertFalse(experience_match(p, {'adult_only':True})['allowed'])
        p=apply_answers({}, {'adult_include':True,'adult_confirmed':True})
        self.assertTrue(experience_match(p, {'adult_only':True})['allowed'])

    def test_traditional_customs_not_automatically_adult(self):
        self.assertNotIn('adult_entertainment',discover_experiences('体验日本特色风俗和和服')['experience_preferences'])

    def test_delegation_stops_subjective_questions(self):
        data=discover_experiences('二次元和烟花，都可以你决定')
        self.assertFalse(any(x['priority']=='P2' for x in data['questions']))
        self.assertEqual(data['experience_preferences']['anime']['subtypes'],['exploration'])

    def test_analyzer_delegation_does_not_reask_optional_pace_or_interest(self):
        data=analyze_request('日本二次元七天，其他都可以你决定')
        self.assertFalse({'pace','interests','anime_subtypes'} & {q['field'] for q in data['questions']})

    def test_cash_purpose_question_not_duplicated_as_budget_scope(self):
        data=analyze_request('我手里有15000，想去日本体验二次元文化、和服、烟花祭和特色风俗。')
        self.assertTrue(any(q['field']=='budget_purpose' for q in data['questions']))
        self.assertFalse(any(q['field']=='budget_scope' for q in data['questions']))

    def test_budget_confirmation_preserves_currency_and_inclusions(self):
        p=apply_answers({'available_funds_amount':15000},{'travel_budget_available':True,'budget_amount':10000,'budget_currency':'CNY','budget_scope':'PER_PERSON','airfare_included':True})
        self.assertEqual(p['budget_amount'],10000);self.assertEqual(p['available_funds_amount'],15000)

    def test_unknown_favorite_work_not_invented(self):
        p=apply_answers({}, {'anime_subtypes':['pilgrimage']})
        intent=research_intents(p)[0]
        self.assertEqual(intent['favorite_works'],[])

    def test_interests_cannot_override_hard_steps_or_cost(self):
        from planning_engine import select_attractions
        p=apply_answers({'interests':['anime'],'walking_tolerance_steps':10000},{'anime_subtypes':['figure_collecting']})
        rows=self.candidates();rows[1].update(estimated_steps=17000,estimated_cost=500)
        self.assertNotIn('figure_collecting',[x['id'] for x in select_attractions(rows,p,attraction_budget=100)['selected']])

    def test_yen_symbol_uses_explicit_currency_only(self):
        data=clarify_currency({'attractions':[{'currency':'JPY','ticket_price':'¥1000'}], 'summary':'￥500'})
        self.assertEqual(data['attractions'][0]['ticket_price'],'JPY 1000')
        self.assertEqual(data['summary'],'币种未注明 500')


class ImageContracts(unittest.TestCase):
    def requirement(self):return {'attraction_id':'place','name':'Sample City Temple','aliases':['Sample City Temple'],'location':'Sample City','event':False}
    def photo(self):return {'title':'File:Sample City Temple.jpg','page_url':'https://commons.wikimedia.org/wiki/File:Sample_City_Temple.jpg',
        'license':'CC BY-SA 4.0','artist':'Example photographer','width':1200,'height':800,'image_id':'opaque'}

    def test_requirements_from_selected_core_places(self):
        plan={'attractions':[{'id':'a','name':'User selected place'},{'id':'b','name':'Omitted','core':False}]}
        self.assertEqual([x['attraction_id'] for x in image_requirements(plan)],['a'])

    def test_license_and_identity_are_checked(self):
        row=self.photo();self.assertTrue(eligible_image(row,self.requirement())['eligible'])
        row['license']='license_unknown';self.assertFalse(eligible_image(row,self.requirement())['eligible'])
        row=self.photo();row['title']='File:Wrong City Shrine.jpg';self.assertFalse(eligible_image(row,self.requirement())['eligible'])

    def test_small_thumbnails_are_rejected(self):
        row=self.photo();row.update(width=200,height=100)
        self.assertFalse(eligible_image(row,self.requirement())['eligible'])

    def test_non_commons_provenance_not_accepted_as_free(self):
        row=self.photo();row['page_url']='https://example.org/free-photo'
        self.assertFalse(eligible_image(row,self.requirement())['eligible'])

    def test_cc_license_requires_author(self):
        row=self.photo();row['artist']='';self.assertFalse(eligible_image(row,self.requirement())['eligible'])

    def test_failure_has_finite_retry_and_cause(self):
        class Service:
            @staticmethod
            def commons_images(*a,**k):raise TimeoutError('controlled contract timeout')
        result=collect_images({'attractions':[{'id':'place','name':'Sample City Temple','image_aliases':['Temple alternative']}],
            'trip_profile':{'destination':'Sample City'}},service=Service())
        self.assertEqual(len(result['attempts']),2)
        self.assertEqual(result['requirements'][0]['status'],'UNAVAILABLE')
        self.assertIn('TimeoutError',result['attempts'][0]['failure_reason'])

    def test_download_binding_and_normalization(self):
        from PIL import Image
        row=self.photo()
        class Service:
            @staticmethod
            def commons_images(*a,**k):return {'results':[row]}
            @staticmethod
            def download_image(image_id,name,output_root=None):
                target=Path(output_root)/name;target.parent.mkdir(parents=True,exist_ok=True)
                Image.new('RGB',(1200,800),'gray').save(target)
                return {'local_path':str(target),'page_url':row['page_url'],'image_url':'https://upload.wikimedia.org/contract.jpg',
                        'license':row['license'],'artist':row['artist'],'retrieved_at':'2026-10-11T00:00:00Z'}
        with tempfile.TemporaryDirectory() as directory:
            result=collect_images({'attractions':[{'id':'place','name':'Sample City Temple'}]},directory,service=Service())
            self.assertEqual(result['status'],'PASS');self.assertEqual(result['images'][0]['attraction_id'],'place')
            self.assertTrue(result['images'][0]['sha256'])

    def test_invalid_download_does_not_count_as_image(self):
        row=self.photo()
        class Service:
            @staticmethod
            def commons_images(*a,**k):return {'results':[row]}
            @staticmethod
            def download_image(*a,**k):raise ValueError('corrupt image')
        result=collect_images({'attractions':[{'id':'place','name':'Sample City Temple'}]},service=Service())
        self.assertEqual(result['images'],[]);self.assertIn('corrupt image',str(result['attempts']))

    def test_host_file_fallback_and_resumed_budget_are_bounded(self):
        class Service:
            @staticmethod
            def commons_images(*a,**k):raise OSError('SSL verification failure in controlled contract')
        plan={'attractions':[{'id':'place','name':'Sample City Temple','image_aliases':['Other Temple']}],
              'trip_profile':{'destination':'Sample City'}}
        first=collect_images(plan,service=Service());plan['image_pipeline']=first
        second=collect_images(plan,selections=[{'attraction_id':'place','file_title':'File:Sample City Temple.jpg'},
            {'attraction_id':'place','file_title':'File:Sample City Temple exterior.jpg'}],service=Service())
        self.assertEqual(len(second['attempts']),4)
        plan['image_pipeline']=second
        final=collect_images(plan,selections=[{'attraction_id':'place','file_title':'File:Another.jpg'}],service=Service())
        self.assertEqual(len(final['attempts']),4)
        self.assertIn('exhausted',final['requirements'][0]['failure_reason'])


class InstalledPaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.directory=Path(cls.temp.name)/'Chinese 中文 Path With Spaces'
        cls.directory.mkdir();archive=build(Path(cls.temp.name)/'contract.zip')
        with zipfile.ZipFile(archive) as z:z.extractall(cls.directory)
        cls.plugin=cls.directory/('smart-travel-planner-'+json.loads((ROOT/'plugin.json').read_text())['version'])

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def command(self,args):
        env={k:v for k,v in os.environ.items() if k not in {'PLUGIN_ROOT','CLAUDE_PLUGIN_ROOT'}}
        return subprocess.run([sys.executable,str(self.plugin/'skills/smart-travel-planner/scripts/plugin_entry.py'),*args],
            cwd=self.temp.name,env=env,capture_output=True,text=True,encoding='utf-8',timeout=30)

    def test_clean_extraction_has_complete_workflow(self):
        for name in ('plugin.json','.mcp.json','scripts/deliver_plan.py','scripts/image_pipeline.py','scripts/build_docx.py',
                     'requirements-docx.txt','installer/start_mcp.py','skills/smart-travel-planner/references/experience-discovery.md'):
            self.assertTrue((self.plugin/name).is_file(),name)

    def test_changed_cwd_and_spaces_resolve_installed_root(self):
        r=self.command(['doctor']);self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(Path(json.loads(r.stdout)['plugin_root']),self.plugin)

    @unittest.skipUnless(sys.platform=='win32','Actual Windows path test')
    def test_windows_backslashes(self):
        r=self.command(['--plugin-root',str(self.plugin).replace('/','\\'),'doctor'])
        self.assertEqual(r.returncode,0,r.stdout)

    def test_bad_explicit_root_does_not_fall_back_to_developer_checkout(self):
        r=self.command(['--plugin-root',self.temp.name,'doctor']);self.assertEqual(r.returncode,2)
        self.assertIn('FULL_PLUGIN_REQUIRED',r.stdout)

    def test_standalone_copy_is_detected_and_not_deleted(self):
        directory=Path(self.temp.name)/'standalone';candidate=directory/'smart-travel-planner/SKILL.md'
        candidate.parent.mkdir(parents=True,exist_ok=True);candidate.write_text('old Skill',encoding='utf-8')
        r=self.command(['--standalone-skills-dir',str(directory),'doctor'])
        self.assertEqual(len(json.loads(r.stdout)['standalone_skill_collisions']),1)
        self.assertTrue(candidate.is_file())

    def test_detached_skill_returns_fallback(self):
        directory=Path(self.temp.name)/'detached/skills/smart-travel-planner/scripts';directory.mkdir(parents=True,exist_ok=True)
        entry=directory/'plugin_entry.py';shutil.copy2(self.plugin/'skills/smart-travel-planner/scripts/plugin_entry.py',entry)
        env={k:v for k,v in os.environ.items() if k not in {'PLUGIN_ROOT','CLAUDE_PLUGIN_ROOT'}}
        r=subprocess.run([sys.executable,str(entry),'doctor'],cwd=self.temp.name,env=env,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(r.returncode,2);self.assertIn('FULL_PLUGIN_REQUIRED',r.stdout)

    def test_host_manifest_variables_do_not_mix(self):
        claude=json.loads((self.plugin/'.mcp.json').read_text())
        codex=json.loads((self.plugin/'adapters/codex/mcp.json').read_text())
        self.assertIn('${CLAUDE_PLUGIN_ROOT}',str(claude))
        self.assertNotIn('${CLAUDE_PLUGIN_ROOT}',str(codex))
        self.assertNotIn('mcpServers',json.loads((self.plugin/'.claude-plugin/plugin.json').read_text()))

    def test_mcp_launch_from_changed_cwd(self):
        message=json.dumps({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25'}})+'\n'
        r=subprocess.run([sys.executable,str(self.plugin/'installer/start_mcp.py')],cwd=self.temp.name,input=message,
            capture_output=True,text=True,encoding='utf-8',timeout=30)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['result']['serverInfo']['version'],json.loads((ROOT/'plugin.json').read_text())['version'])

    def test_python_executable_discovery(self):self.assertTrue(Path(python_runtime()).is_file())

    def delivery_contract(self,with_image):
        # Controlled engineering input, never a live traveler or network proof.
        destination=Path(self.temp.name)/('User Output Photos' if with_image else 'User Output No Photos')
        destination.mkdir(exist_ok=True)
        profile={'destination':'Tokyo','travel_window':'2027年夏季','duration_days':2,'traveler_count':1,
            'origin':'Beijing','budget_amount':15000,'budget_currency':'CNY','budget_scope':'PER_PERSON',
            'airfare_included':True,'lodging_area':'Ueno'}
        plan={'title':'东京旅行手册','summary':'以二次元和传统文化为主题；动态报价待核验。','destination':'Tokyo',
            'trip_profile':profile,'attractions':[{'id':'place','name':'文化体验','currency':'JPY','ticket_price':'¥3300 当前参考'}],
            'days':[{'date':'Day 1','day_type':'ARRIVAL','area':'到达','route_state':'AREA_LEVEL_ANCHOR',
                     'activities':[{'time':'随航班','activity':'抵达并入住'}]},
                    {'date':'Day 2','day_type':'DEPARTURE','area':'离开','route_state':'AREA_LEVEL_ANCHOR',
                     'activities':[{'time':'随航班','activity':'退房及返程'}]}],
            'public_sources':[{'title':'参考来源','url':'https://example.org/information','checked_at':'2026-10-11'}]}
        if with_image:
            from PIL import Image
            photo=destination/'images/controlled.jpg';photo.parent.mkdir(exist_ok=True)
            Image.new('RGB',(1200,800),'gray').save(photo)
            plan['images']=[{'attraction_id':'place','attraction':'文化体验','local_path':str(photo),
                'page_url':'https://commons.wikimedia.org/wiki/File:Controlled_contract.jpg',
                'license':'CC BY-SA 4.0','author':'Contract author','transformations':['RGB conversion']}]
        source=destination/'input.json';source.write_text(json.dumps(plan,ensure_ascii=False),encoding='utf-8')
        result=self.command(['deliver','--input',str(source),'--output-dir',str(destination),'--skip-images'])
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads((destination/'delivery-report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['status'],'DELIVERED')
        builds=[x for x in report['attempts'] if x.get('script')=='build_docx.py']
        self.assertEqual(len(builds),1)
        self.assertEqual(Path(builds[0]['command'][1]),self.plugin/'scripts/build_docx.py')
        doc=Path(report['document'])
        checked=destination/'plan-with-readiness.json'
        r=subprocess.run([sys.executable,str(self.plugin/'scripts/validate_docx.py'),str(doc),'--plan',str(checked),
                          *(['--require-images'] if with_image else [])],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(r.returncode,0,r.stdout+r.stderr)
        validation=json.loads(r.stdout);self.assertEqual(validation['images'],int(with_image))
        with zipfile.ZipFile(doc) as archive:
            document=archive.read('word/document.xml').decode('utf-8')
            styles=archive.read('word/styles.xml').decode('utf-8')
            self.assertIn('JPY 3300',document);self.assertIn('Microsoft YaHei',styles)
            self.assertNotIn('¥3300',document)
            self.assertNotIn('AIRPORT_UNRESOLVED',document)
            if with_image:
                self.assertTrue(any(x.startswith('word/media/') for x in archive.namelist()))
                self.assertIn('Contract author',document);self.assertIn('CC BY-SA 4.0',document)
                self.assertIn('place | 文化体验',document)
        return report

    def test_clean_plugin_standard_delivery_embeds_bound_image(self):self.delivery_contract(True)

    def test_clean_plugin_missing_images_delivers_text_handbook(self):self.delivery_contract(False)


if __name__=='__main__':unittest.main()
