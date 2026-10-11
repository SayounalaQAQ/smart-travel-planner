#!/usr/bin/env python3
"""Run V0.9 route/diversity/availability QA and emit plan readiness."""
import argparse
import json
from pathlib import Path
from execution_readiness import evaluate_plan

parser = argparse.ArgumentParser()
parser.add_argument("input")
parser.add_argument("--output", help="Optional path to write plan with readiness fields")
parser.add_argument("--now", help="ISO UTC timestamp for deterministic freshness checks")
parser.add_argument("--require-ready", action="store_true", help="Exit 2 unless booking readiness is READY")
args = parser.parse_args()
source = Path(args.input).resolve()
plan = evaluate_plan(json.loads(source.read_text(encoding="utf-8")), now=args.now)
if args.output:
    Path(args.output).resolve().write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"readiness": plan["readiness"], "plan_qa": plan["plan_qa"],
                  "route_closure": plan["route_closure"], "budget_reconciliation": plan["budget_reconciliation"],
                  "state_consistency": plan["state_consistency"],
                  "data_completeness_matrix": plan["data_completeness_matrix"]}, ensure_ascii=False, indent=2))
raise SystemExit(1 if plan["plan_qa"]["status"] == "FAIL" else 2 if args.require_ready and plan["readiness"]["booking_readiness"] != "READY" else 0)
