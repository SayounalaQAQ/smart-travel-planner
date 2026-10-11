"""Keep synthetic/fixture evidence out of a real acceptance verdict."""
from urllib.parse import urlparse


def validate_live_evidence(plan, evidence):
    issues = []
    if evidence.get('kind') != 'LIVE_HOST_WEB' or not evidence.get('raw_results_file'):
        issues.append('LIVE_RESEARCH_PROVENANCE_MISSING')
    live_quote_ids = {r.get('quote_id') for r in evidence.get('verified_quotes', [])}
    def visit(value):
        if isinstance(value, dict):
            if value.get('mode') == 'TEST_SYNTHETIC' or value.get('synthetic') is True or value.get('provider_kind') in {'mock','fixture'}:
                issues.append('SYNTHETIC_EVIDENCE_FORBIDDEN')
            if value.get('cost_type') == 'VERIFIED_QUOTE' and value.get('quote_id') not in live_quote_ids:
                issues.append('VERIFIED_COST_WITHOUT_LIVE_QUOTE_EVIDENCE')
            for key,item in value.items():
                if key in {'source_url','source','url'} and isinstance(item,str) and item.startswith('http'):
                    host = urlparse(item).hostname or ''
                    if host.endswith(('.example','.test','.invalid')) or host in {'example.com','localhost'}:
                        issues.append('PLACEHOLDER_SOURCE_IN_LIVE_EVIDENCE')
                elif key in {'source_file','raw_results_file'} and isinstance(item,str) and any(token in item.replace('\\','/') for token in ('tests/fixtures','acceptance/fixtures')):
                    issues.append('FIXTURE_SOURCE_IN_LIVE_EVIDENCE')
                visit(item)
        elif isinstance(value,list):
            for child in value: visit(child)
    visit(plan); visit(evidence)
    return {'status':'PASS' if not issues else 'FAIL','issues':sorted(set(issues))}
