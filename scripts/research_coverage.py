"""Different denominators for researched facts, connections and complete cost."""
from collections import Counter

def coverage(gaps,ledger):
    rows=[ledger.get(g['gap_id'],{}) for g in gaps if g.get('researchable')]
    resolved=sum(r.get('final_status') in {'RESOLVED','CURRENT_REFERENCE_ONLY'} for r in rows)
    partial=sum(r.get('final_status')=='PARTIAL_DATA' for r in rows)
    attempted=sum(bool(r.get('attempts')) for r in rows)
    return {'researchable_gaps':len(rows),'resolved':resolved,'partial':partial,
        'attempted':attempted,'not_researched':len(rows)-attempted,
        'unresolved_after_attempts':attempted-resolved-partial,
        'research_coverage':round(resolved/len(rows),4) if rows else 0,
        'attempt_coverage':round(attempted/len(rows),4) if rows else 0,
        'statuses':dict(Counter(r.get('final_status','NOT_RESEARCHED') for r in rows))}

def cost_coverage(plan,gaps,ledger):
    result={}
    for row in plan.get('cost_ledger',[]):
        category=row.get('category'); matching=[g for g in gaps if g['target'].get('category')==category or g['target'].get('kind')==category and g['required_field']=='exact_quote']
        statuses=[ledger.get(g['gap_id'],{}).get('final_status','NOT_RESEARCHED') for g in matching]
        group=result.setdefault(category,{'cost_known':True,'cost_research_status':statuses or ['NOT_RESEARCHED'],'unknown_rows':[]})
        if row.get('amount') is None:
            group['cost_known']=False
            group['unknown_rows'].append(row.get('id'))
        group['cost_research_status']=list(dict.fromkeys(group['cost_research_status']+statuses))
    known=sum(r['cost_known'] for r in result.values())
    return {'categories':result,'known_categories':known,'required_categories':len(result),
        'cost_coverage':round(known/len(result),4) if result else 0}
