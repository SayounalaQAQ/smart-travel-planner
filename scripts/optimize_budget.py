#!/usr/bin/env python3
"""Reverse-plan labeled savings options against a user's spending limit."""
import argparse
import json
from pathlib import Path
from travel_utils import optimize_budget

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('input',help='JSON containing budget, budget_limit, and saving_options')
parser.add_argument('--output')
args=parser.parse_args()
result=optimize_budget(json.loads(Path(args.input).read_text(encoding='utf-8')))
rendered=json.dumps(result,ensure_ascii=False,indent=2)
if args.output: Path(args.output).write_text(rendered,encoding='utf-8')
print(rendered)
