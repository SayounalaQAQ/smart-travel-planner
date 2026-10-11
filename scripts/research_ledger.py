"""Bounded research audit. Pending work is never reported as attempted failure."""
from datetime import datetime, timezone
from hashlib import sha256

STATUSES = {'NOT_RESEARCHED','RESEARCH_PENDING','RESEARCHING','PARTIAL_DATA',
    'CURRENT_REFERENCE_ONLY','EXACT_DATE_UNAVAILABLE','PROVIDER_UNAVAILABLE',
    'SOURCE_UNAVAILABLE','DYNAMIC_DATA_UNAVAILABLE','UNRESOLVED_AFTER_RETRIES','RESOLVED'}

def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def identity(*parts):
    return sha256('|'.join(map(str,parts)).encode('utf-8')).hexdigest()[:20]

def entry(gap):
    return {'gap_id':gap['gap_id'],'category':gap['category'],'attempts':[],
            'final_status':'NOT_RESEARCHED','failure_reason':None,'evidence_ids':[]}

def finish(row, status, reason=None):
    if status not in STATUSES:
        raise ValueError('Unknown research status')
    if status in {'EXACT_DATE_UNAVAILABLE','PROVIDER_UNAVAILABLE','SOURCE_UNAVAILABLE',
                  'DYNAMIC_DATA_UNAVAILABLE','UNRESOLVED_AFTER_RETRIES'} and not row['attempts']:
        raise ValueError('Unavailable requires an executed attempt')
    row.update(final_status=status,failure_reason=reason)
    return row
