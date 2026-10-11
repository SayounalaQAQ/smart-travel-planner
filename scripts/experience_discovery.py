"""Conservative experience preferences and evidence-supplied candidate matching."""
import argparse
from copy import deepcopy
import json
import re
from travel_utils import decision_mode

SUBTYPES={'pilgrimage':r'圣地巡礼|取景地|pilgrimage', 'figure_collecting':r'手办|模型收藏|figure',
          'retro_games':r'复古游戏|怀旧游戏|retro.game', 'arcade':r'街机|arcade',
          'conventions':r'漫展|同人展|convention|comiket', 'theme_cafe':r'主题咖啡|theme.cafe',
          'voice_actor_events':r'声优|voice.actor'}


def discover_experiences(text,profile=None):
    profile=profile or {};result={}
    if re.search(r'二次元|动漫|anime|圣地巡礼|手办|复古游戏',text,re.I):
        result['anime']={'subtypes':[k for k,v in SUBTYPES.items() if re.search(v,text,re.I)],
                         'favorite_works':[], 'priority':'PREFERENCE','status':'USER_INTENT'}
    for name,pattern in (('kimono',r'和服|浴衣|kimono'),('fireworks',r'花火|烟花|fireworks'),
                         ('traditional_culture',r'风俗|传统|神社|祭典|文化体验')):
        if re.search(pattern,text,re.I):result[name]={'priority':'PREFERENCE','status':'USER_INTENT'}
    if re.search(r'泡泡浴|成人娱乐|adult.entertainment',text,re.I):
        result['adult_entertainment']={'priority':'OPTIONAL','status':'AWAITING_EXPLICIT_OPT_IN',
                                       'adult_confirmed':False,'include':False}
    cash=re.search(r'(?:手里有|手头有|存了|现金有)\s*([\d,]+(?:\.\d+)?)',text)
    questions=[]
    if cash and not profile.get('budget_purpose_confirmed'):
        questions.append({'field':'budget_purpose','class':'USER_REQUIRED','priority':'P0',
            'question':'这笔钱是全部可用现金，还是此次旅行预算？币种、每人/合计和机票是否包含？',
            'impact':'HIGH','available_funds_amount':float(cash.group(1).replace(',',''))})
    if result.get('anime') and not result['anime']['subtypes']:
        questions.append({'field':'anime_subtypes','class':'USER_DECISION','priority':'P2','impact':'HIGH',
            'question':'二次元更想体验哪类？圣地巡礼（可写作品）、手办/复古游戏，还是综合初体验？'})
    if result.get('fireworks') and len(result)>1:
        questions.append({'field':'experience_priorities','class':'USER_DECISION','priority':'P2','impact':'HIGH',
            'question':'花火必须看到，还是可用其他文化体验替代？更重要的体验可一起告诉我。'})
    if result and not profile.get('pace'):
        questions.append({'field':'experience_spending_pace','class':'USER_DECISION','priority':'P2','impact':'MEDIUM',
            'question':'特色体验愿意花多少、购物是否单列？节奏偏轻松还是深度体验？不知道可交给我决定。'})
    if result.get('adult_entertainment'):
        questions.append({'field':'adult_opt_in','class':'USER_REQUIRED','priority':'P0','impact':'HIGH',
            'question':'成人娱乐是否仅作了解，还是希望纳入可选项？纳入前需确认成年、实际意愿、语言与预算；不确认就省略。'})
    if decision_mode(text):
        questions=[q for q in questions if q['priority']=='P0']
        if 'anime' in result and not result['anime']['subtypes']:
            result['anime'].update(subtypes=['exploration'],status='DELEGATED_EXPLORATION')
    return {'experience_preferences':result,'questions':questions,'questions_stage':'AFTER_PRELIMINARY_RESEARCH',
            'event_date_status':'UNANNOUNCED_OR_NOT_RESEARCHED' if 'fireworks' in result else 'NOT_APPLICABLE'}


def apply_answers(profile,answers):
    """User answers, not scraped page text. Keep the legacy interests list intact."""
    result=deepcopy(profile);prefs=result.setdefault('experience_preferences',{})
    if 'anime_subtypes' in answers:
        values=answers['anime_subtypes']
        if not isinstance(values,list) or any(x not in {*SUBTYPES,'exploration'} for x in values):
            raise ValueError('anime_subtypes must contain supported preference codes')
        prefs.setdefault('anime',{}).update(subtypes=values,priority='PREFERENCE',status='USER_ANSWER')
    if 'favorite_works' in answers:
        works=answers['favorite_works']
        if not isinstance(works,list) or any(not isinstance(x,str) or len(x)>200 for x in works):raise ValueError('Invalid works')
        prefs.setdefault('anime',{})['favorite_works']=works
    for name,priority in answers.get('experience_priorities',{}).items():
        if priority not in {'MUST_HAVE','HIGH','PREFERENCE','OPTIONAL'}:raise ValueError('Invalid experience priority')
        prefs.setdefault(name,{})['priority']=priority
    if answers.get('delegate') is True:
        prefs.setdefault('anime',{}).setdefault('subtypes',['exploration'])
        result['experience_decision_mode']='DELEGATED_EXPLORATION'
    for name in ('pace','sleep_schedule','experience_budget','shopping_budget','specialized_interests'):
        if name in answers:result[name]=deepcopy(answers[name])
    if answers.get('travel_budget_available') is True:
        result['budget_purpose_confirmed']=True
        amount=answers.get('budget_amount',result.get('available_funds_amount'))
        if not isinstance(amount,(int,float)) or isinstance(amount,bool) or amount<=0:raise ValueError('Positive budget amount required')
        result['budget_amount']=amount
        for name in ('budget_currency','budget_scope','airfare_included'):
            if name in answers:result[name]=answers[name]
    if answers.get('adult_include') is True:
        prefs.setdefault('adult_entertainment',{}).update(include=answers.get('adult_confirmed') is True,
            adult_confirmed=answers.get('adult_confirmed') is True,priority='OPTIONAL')
    elif answers.get('adult_include') is False:
        prefs.setdefault('adult_entertainment',{})['include']=False
    result.setdefault('field_provenance',{})['experience_preferences']='user answers'
    return result


def experience_match(profile,candidate):
    prefs=profile.get('experience_preferences',{});anime=prefs.get('anime',{})
    tags=set(candidate.get('experience_tags',[]));tags.update(candidate.get('interest_tags',[]))
    requested=set(anime.get('subtypes',[]))-{'exploration'}
    reasons=[];score=0;allowed=True
    specialized=candidate.get('specialized_interest')
    if specialized and specialized not in profile.get('specialized_interests',[]):
        allowed=False;reasons.append('专门兴趣未确认，不默认安排')
    adult=candidate.get('adult_only') is True
    if adult and not (prefs.get('adult_entertainment',{}).get('include') is True and prefs['adult_entertainment'].get('adult_confirmed') is True):
        allowed=False;reasons.append('未确认成年与纳入意愿，省略可选成人活动')
    if requested & tags:score+=10;reasons.append('匹配具体兴趣：'+', '.join(sorted(requested & tags)))
    elif requested and 'anime' in tags:score-=12;reasons.append('二次元泛兴趣匹配，但不是此次体验重点，优先留给匹配体验')
    works=set(anime.get('favorite_works',[]));linked=set(candidate.get('related_works',[]))
    if 'pilgrimage' in tags and works:
        if works & linked:score+=12;reasons.append('对应用户喜欢的作品；取景关联仍须来源核验')
        else:allowed=False;reasons.append('没有用户作品对应证据，不作为专属巡礼')
    if 'pilgrimage' in tags and requested and not works:
        reasons.append('未提供作品，只能给作品确认后的巡礼候选，不捏造喜欢的作品')
    for name,pref in prefs.items():
        if name in tags:score+= {'MUST_HAVE':12,'HIGH':8,'PREFERENCE':3,'OPTIONAL':1}.get(pref.get('priority'),3)
    if candidate.get('event') and candidate.get('event_status')!='OFFICIALLY_ANNOUNCED':
        reasons.append('未来活动未官宣，仅保留可替换候选；不固定出票日期')
    return {'allowed':allowed,'score':score,'reasons':reasons}


def recommend_experiences(profile,candidates,limit=3):
    from planning_engine import select_attractions
    result=select_attractions(candidates,profile)
    result['selected']=sorted(result['selected'],key=lambda x:(-x['score'],str(x.get('id') or x.get('name'))))[:limit]
    result['experience_preferences']=deepcopy(profile.get('experience_preferences',{}))
    return result


def research_intents(profile):
    prefs=profile.get('experience_preferences',{});anime=prefs.get('anime',{})
    return [{'domain':'experience','destination':profile.get('destination'), 'subtype':tag,
             'favorite_works':anime.get('favorite_works',[]) if tag=='pilgrimage' else [],
             'required_evidence':['specific experience','identity/location','current operations','reservation','price scope'],
             'status':'NOT_RESEARCHED'} for tag in anime.get('subtypes',[])]


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--answers',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    from pathlib import Path
    data=json.loads(Path(a.input).read_text(encoding='utf-8'));profile=data.get('trip_profile',data)
    updated=apply_answers(profile,json.loads(Path(a.answers).read_text(encoding='utf-8')))
    if 'trip_profile' in data:data['trip_profile']=updated
    else:data=updated
    if 'trip_profile' in data:
        from state_consistency import sync_profile
        data=sync_profile(data)
    Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    Path(a.output).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
