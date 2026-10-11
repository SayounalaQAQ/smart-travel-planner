#!/usr/bin/env python3
import argparse,json
from pathlib import Path
from travel_utils import budget
from cost_ledger import reconcile_budget
p=argparse.ArgumentParser(); p.add_argument('input'); p.add_argument('--output'); a=p.parse_args()
data=json.loads(Path(a.input).read_text(encoding='utf-8'))
if 'cost_ledger' in data:
    quotes={r['quote_id']:r for field in ('hotel_availability','flight_availability') for r in data.get(field,[]) if r.get('quote_id')}
    result=reconcile_budget(data.get('trip_profile',{}),data['cost_ledger'],quotes,data.get('exchange_rates'))
else:
    result=budget(data)
text=json.dumps(result,ensure_ascii=False,indent=2)
if a.output: Path(a.output).write_text(text,encoding='utf-8')
print(text)
