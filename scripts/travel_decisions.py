"""Evidence-gated candidate proposals shared by travel decision domains."""
from datetime import datetime


def propose_candidates(domain, candidates, *, search_status='available', recommendation_id=None, auto_decision=False):
    """Create a proposal from real sourced candidates; never invent missing options."""
    if not isinstance(candidates, list):
        raise ValueError('candidates must be a list')
    if search_status in {'unavailable','degraded'} and not candidates:
        return {'domain':domain,'status':'UNAVAILABLE','candidates':[],'recommendation':None,
                'decision_status':'UNAVAILABLE','reason':'搜索能力不可用或降级，未获得可核验候选。'}
    accepted=[]; rejected=[]
    for index,item in enumerate(candidates):
        if not isinstance(item,dict):
            rejected.append({'index':index,'reason':'candidate must be an object'}); continue
        sources=item.get('source_urls') or ([item['source_url']] if item.get('source_url') else [])
        valid_sources=[url for url in sources if isinstance(url,str) and url.startswith('https://')]
        checked=item.get('checked_at')
        try:
            datetime.fromisoformat(str(checked).replace('Z','+00:00'))
        except (TypeError,ValueError):
            checked=None
        missing=[key for key in ('id','name') if not item.get(key)]
        if not valid_sources: missing.append('https source')
        if not checked: missing.append('valid checked_at')
        if missing:
            rejected.append({'index':index,'reason':'missing '+', '.join(missing)}); continue
        accepted.append({**item,'source_urls':valid_sources,'checked_at':checked,'status':'researched'})
    if not accepted:
        status='DISCOVERING' if search_status=='available' else 'UNAVAILABLE'
        return {'domain':domain,'status':status,'candidates':[],'recommendation':None,
                'decision_status':status,'rejected':rejected,'reason':'没有满足来源/核验时间要求的候选。'}
    chosen=next((x for x in accepted if x['id']==recommendation_id),None)
    state='AUTO_SELECTED' if auto_decision and chosen else ('USER_DECISION_REQUIRED' if chosen else 'PROPOSED')
    return {'domain':domain,'status':'PROPOSED','candidates':accepted,
            'recommendation':chosen,'decision_status':state,'rejected':rejected,
            'user_choice_needed':state=='USER_DECISION_REQUIRED',
            'auto_selected':state=='AUTO_SELECTED'}
