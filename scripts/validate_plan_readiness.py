#!/usr/bin/env python3
"""Run V0.9 route/diversity/availability QA and emit plan readiness."""
import argparse
import json
from pathlib import Path
from execution_readiness import evaluate_plan
from delivery_validation import apply_delivery_checks, planning_delivery_gate

parser = argparse.ArgumentParser()
parser.add_argument("input")
parser.add_argument("--output", help="Optional path to write plan with readiness fields")
parser.add_argument("--now", help="ISO UTC timestamp for deterministic freshness checks")
parser.add_argument("--require-ready", action="store_true", help="Exit 2 unless booking readiness is READY")
parser.add_argument('--purpose',choices=('booking','planning'),default='booking',help='Planning permits missing quotes; never bypasses known conflicts')
args = parser.parse_args()
source = Path(args.input).resolve()
data=apply_delivery_checks(json.loads(source.read_text(encoding='utf-8')))
if args.purpose=='planning' and data['delivery_validation']['errors']:
    print(json.dumps({'status':'BLOCKED','planning_delivery':data['delivery_validation']},ensure_ascii=False,indent=2));raise SystemExit(1)
plan = evaluate_plan(data, now=args.now)
plan['planning_delivery']=planning_delivery_gate(plan)
if args.output:
    Path(args.output).resolve().write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"readiness": plan["readiness"], "plan_qa": plan["plan_qa"],
                  "route_closure": plan["route_closure"], "budget_reconciliation": plan["budget_reconciliation"],
                  "state_consistency": plan["state_consistency"],
                  "data_completeness_matrix": plan["data_completeness_matrix"],
                  "planning_delivery":plan['planning_delivery']}, ensure_ascii=False, indent=2))
failed=not plan['planning_delivery']['can_generate'] if args.purpose=='planning' else plan['plan_qa']['status']=='FAIL'
raise SystemExit(1 if failed else 2 if args.require_ready and plan['readiness']['booking_readiness']!='READY' else 0)
