#!/usr/bin/env python3
"""Validate the user-facing handbook structure without trusting its text payload."""
import argparse,json,posixpath,re,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

p=argparse.ArgumentParser(); p.add_argument('file');p.add_argument('--plan');p.add_argument('--require-images',action='store_true'); a=p.parse_args(); path=Path(a.file); issues=[]
INTERNAL=re.compile(r'\bMCP\b|tools/call|provider unavailable|health_check|acceptance session|\bmock\b|\bfixture\b|\bdebug\b|synthetic|内部证据|测试数据|调试信息|验收样例|PROVIDER_HOTEL_QUOTE_DEGRADED|BATCH_SHARED_NOT_PER_QUERY|RESEARCH_GAP_ID',re.I)
try:
  with zipfile.ZipFile(path) as z:
    if z.testzip(): issues.append('Corrupt ZIP member')
    names=set(z.namelist()); required={'[Content_Types].xml','word/document.xml','word/_rels/document.xml.rels','word/styles.xml'}
    issues += [f'Missing part: {x}' for x in required-names]
    root=ET.fromstring(z.read('word/document.xml')); relroot=ET.fromstring(z.read('word/_rels/document.xml.rels'))
    rels=[e.attrib for e in relroot]; text=' '.join((n.text or '') for n in root.iter() if n.tag.endswith('}t'))
    tables=sum(n.tag.endswith('}tbl') for n in root.iter()); hyperlinks=[n for n in root.iter() if n.tag.endswith('}hyperlink')]
    external=[r for r in rels if r.get('TargetMode')=='External' and r.get('Type','').endswith('/hyperlink')]
    anchors={n.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}name') for n in root.iter() if n.tag.endswith('}bookmarkStart')}
    internal=[n.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}anchor') for n in hyperlinks if n.attrib.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}anchor')]
    if not internal: issues.append('Missing clickable static table of contents')
    if any(anchor not in anchors for anchor in internal): issues.append('Broken internal table-of-contents anchor')
    if 'TOC \\o' in z.read('word/document.xml').decode('utf-8',errors='ignore'): issues.append('Unexpected updateable TOC field placeholder')
    if INTERNAL.search(text): issues.append('Internal development or test text leaked into handbook')
    if re.search(r'\b(?:AIRPORT|HOTEL|STATION|ACTIVITY_LOCATION)_UNRESOLVED\b',text):issues.append('Internal location placeholder leaked into handbook')
    if 'destination_choice_confirmed' in text: issues.append('Legacy selection field leaked into user handbook')
    embeds=[n.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed') for n in root.iter() if n.tag.endswith('}blip')]
    if a.require_images and not embeds:issues.append('Required embedded photos missing')
    if re.search(r'[¥￥]\s*\d',text):issues.append('Ambiguous currency symbol; use explicit CNY/JPY')
    if a.plan:
      from image_pipeline import attraction_id
      plan=json.loads(Path(a.plan).read_text(encoding='utf-8'))
      wanted={attraction_id(x):x for x in plan.get('attractions',[])}
      descriptions=[n.get('descr','').split(' | ')[0] for n in root.iter() if n.tag.endswith('}docPr')]
      for image in plan.get('images',[]):
        identifier=image.get('attraction_id') or next((k for k,x in wanted.items() if x.get('name')==image.get('attraction')),None)
        if identifier not in wanted:issues.append('Image is not bound to a selected attraction')
        elif identifier not in descriptions:issues.append('Bound image not embedded: '+str(identifier))
        if not image.get('license') or str(image['license']) not in text:issues.append('Image license attribution missing')
        author=image.get('author') or image.get('artist')
        if author and author not in text:issues.append('Image author attribution missing')
    image_rels={r.get('Id'):posixpath.normpath(posixpath.join('word',r.get('Target',''))) for r in rels if r.get('Type','').endswith('/image')}
    for rid in embeds:
      if rid not in image_rels or image_rels[rid] not in names: issues.append(f'Broken image relationship: {rid}')
    for node in root.iter():
      if node.tag.endswith('}extent') and 'cx' in node.attrib and 'cy' in node.attrib:
        if int(node.attrib['cx'])>round(4.3*914400) or int(node.attrib['cy'])>round(2.8*914400): issues.append('Image exceeds layout bounds')
    if re.search(r'Day\s*\d+\s*[·•]\s*Day\s*\d+',text,re.I):issues.append('Duplicate daily title')
    if re.search(r'(?:机场|住宿|车站)待(?:确定|定)\s*→',text):issues.append('Meaningless unresolved route')
    for title in ('旅行摘要','当前旅行准备度','旅行画像','预算方案','住宿区域','交通路线','每日路线','Plan B','预约','行前清单','来源索引'):
      if title not in text: issues.append(f'Missing expected section: {title}')
    if len(text)<300: issues.append('Document text unexpectedly short')
    if tables<2: issues.append('Expected profile/budget/itinerary tables')
    if hyperlinks and not external and not internal: issues.append('Hyperlinks have no valid relationship')
    for name in names:
      if name.endswith(('.xml','.rels')): ET.fromstring(z.read(name))
    report={'valid':not issues,'file':str(path.resolve()),'bytes':path.stat().st_size,'text_characters':len(text),'tables':tables,'images':len(embeds),'hyperlinks':len(hyperlinks),'external_hyperlinks':len(external),'static_toc_links':len(internal),'issues':issues}
except (zipfile.BadZipFile,OSError,KeyError,ET.ParseError) as e: report={'valid':False,'file':str(path.resolve()),'issues':[str(e)]}
print(json.dumps(report,ensure_ascii=False,indent=2)); raise SystemExit(0 if report['valid'] else 1)
