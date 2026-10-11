#!/usr/bin/env python3
import argparse,json,sys
from pathlib import Path
from travel_utils import validate_trip,critical_information_gate,trip_readiness,detect_hidden_constraints
p=argparse.ArgumentParser(); p.add_argument('input'); a=p.parse_args(); data=json.loads(Path(a.input).read_text(encoding='utf-8')); errors=validate_trip(data)
state=trip_readiness(data); gate=critical_information_gate(data)
print(json.dumps({'valid':not errors and gate['ready_for_final'],'issues':errors,'mode':state['mode'],'trip_readiness':state,'critical_gate':gate,'hidden_constraints':detect_hidden_constraints(data)},ensure_ascii=False,indent=2)); sys.exit(bool(errors) or not gate['ready_for_final'])
