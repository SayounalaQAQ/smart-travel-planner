#!/usr/bin/env python3
"""Validate the user-facing handbook structure without trusting its text payload."""
import argparse,json,posixpath,re,zipfile,hashlib
from pathlib import Path
from xml.etree import ElementTree as ET

p=argparse.ArgumentParser(); p.add_argument('file');p.add_argument('--plan');p.add_argument('--require-images',action='store_true'); a=p.parse_args(); path=Path(a.file); issues=[];consistency_errors=[]
INTERNAL=re.compile(r'\bMCP\b|tools/call|provider unavailable|health_check|acceptance session|\bmock\b|\bfixture\b|\bdebug\b|synthetic|内部证据|测试数据|调试信息|验收样例|PROVIDER_HOTEL_QUOTE_DEGRADED|BATCH_SHARED_NOT_PER_QUERY|RESEARCH_GAP_ID',re.I)
try:
  with zipfile.ZipFile(path) as z:
    if z.testzip(): issues.append('Corrupt ZIP member')
    names=set(z.namelist()); required={'[Content_Types].xml','word/document.xml','word/_rels/document.xml.rels','word/styles.xml'}
    issues += [f'Missing part: {x}' for x in required-names]
    root=ET.fromstring(z.read('word/document.xml')); relroot=ET.fromstring(z.read('word/_rels/document.xml.rels'))
    rels=[e.attrib for e in relroot]; text=' '.join((n.text or '') for n in root.iter() if n.tag.endswith('}t'))
    from public_rendering import public_text_errors
    chapter='封面'
    for child in root.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body'):
      line=''.join(n.text or '' for n in child.iter() if n.tag.endswith('}t'))
      style=next((n.get('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val') for n in child.iter() if n.tag.endswith('}pStyle')),None)
      if style and style.startswith('Heading'):chapter=line
      found=public_text_errors(line,chapter);consistency_errors.extend(found);issues.extend(x['code']+': '+chapter for x in found)
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
      from delivery_validation import validate_delivery_data,DATE_WEEKDAY,weekday,WEEKDAYS,ENGLISH
      checks=validate_delivery_data(plan);consistency_errors.extend(checks['errors'])
      if plan.get('trip_profile',{}).get('intercity_mode')=='TRAIN' and re.search(r'本次预算包含往返机票|本次不含往返机票',text):
        consistency_errors.append({'code':'DOCUMENT_TRANSPORT_SCOPE_MISMATCH','field':'预算方案','reason':'Rail scope rendered as airfare','repair':'按 intercity_fare_included 渲染铁路口径'})
      from build_docx import route_summary
      for i,d in enumerate(plan.get('days',[])):
        if d.get('execution_graph') and route_summary(d) not in text:consistency_errors.append({'code':'DOCUMENT_ROUTE_MISMATCH','field':f'days[{i}]','reason':'Canonical daily route not present','repair':'从有序执行节点重新生成路线摘要'})
      core=ET.fromstring(z.read('docProps/core.xml'))
      identifier=next((n.text for n in core.iter() if n.tag.endswith('}identifier')),None)
      if identifier!='stp-standard:'+hashlib.sha256(Path(a.plan).read_bytes()).hexdigest():
        consistency_errors.append({'code':'DOCUMENT_INPUT_MISMATCH','field':'docProps/core.xml','reason':'Document not bound to the exact validated input','repair':'使用标准入口重新生成并验证'})
      for index,day in enumerate(plan.get('days',[]),1):
        value=day.get('date','')
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):
          if f'Day {index} · {value} {weekday(value)}' not in text:
            consistency_errors.append({'code':'DOCUMENT_CALENDAR_MISMATCH','field':'days','reason':'Computed dated weekday heading missing','repair':'用标准生成器重新生成'})
      # Check actual daily rows, not only that the desired text appears somewhere.
      day_index=None
      for child in root.find('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}body'):
        line=''.join(n.text or '' for n in child.iter() if n.tag.endswith('}t'))
        heading=re.match(r'^Day (\d+)\b',line)
        if heading:day_index=int(heading[1])-1
        if child.tag.endswith('}tbl') and day_index is not None:
          rows=[[''.join(n.text or '' for n in cell.iter() if n.tag.endswith('}t')) for cell in row if cell.tag.endswith('}tc')] for row in child if row.tag.endswith('}tr')]
          if rows and rows[0]==['时间','活动','安排提示/费用']:
            if not 0<=day_index<len(plan.get('days',[])):
              consistency_errors.append({'code':'DOCUMENT_DAY_MISMATCH','field':'days','reason':'Unexpected day','repair':'重新生成每日行程'})
              continue
            day=plan['days'][day_index]
            activities=day.get('activities') or day.get('itinerary_nodes') or []
            from build_docx import public_place,daily_rows
            expected=[[str(x.get('time') or '随当天进度'),public_place(x.get('activity') or x.get('place') or '')] for x in activities]
            compact_expected=[[str(x.get('time') or '随当天进度'),public_place(x.get('activity') or x.get('place') or '')] for x in daily_rows(day,len(plan.get('days',[]))<=4)]
            if expected and [r[:2] for r in rows[1:]] not in (expected,compact_expected):
              consistency_errors.append({'code':'DOCUMENT_ACTIVITY_MISMATCH','field':f'days[{day_index}].activities','reason':'Daily Word table differs from the validated plan','repair':'用原计划和标准入口重新生成；不得插入未核实活动'})
      for match in DATE_WEEKDAY.finditer(text):
        from datetime import date
        try:
          n=date.fromisoformat(match[1]).weekday();valid={WEEKDAYS[n],WEEKDAYS[n].replace('星期','周'),ENGLISH[n]}
          if n==6:valid.update({'周天','星期天'})
          if match[2].casefold() not in valid:consistency_errors.append({'code':'DOCUMENT_WEEKDAY_MISMATCH','field':'word/document.xml','reason':'Written weekday is incorrect','repair':match[1]+' '+WEEKDAYS[n]})
        except ValueError:consistency_errors.append({'code':'INVALID_DATE','field':'word/document.xml','reason':'Invalid date','repair':'修正日期'})
      if plan.get('budget_math') and plan['budget_math']!=checks['budget_math']:
        consistency_errors.append({'code':'BUDGET_DERIVED_DATA_MISMATCH','field':'budget_math','reason':'Derived values differ from components','repair':'从原分项重新计算'})
      table_rows=[[''.join(n.text or '' for n in cell.iter() if n.tag.endswith('}t')) for cell in row if cell.tag.endswith('}tc')] for row in root.iter() if row.tag.endswith('}tr')]
      from build_docx import public_category
      budget_keys=list(checks['budget_math'])
      for key,spec in checks['budget_math'].items():
        label={'low':'低预算','recommended':'推荐','comfortable':'舒适'}.get(key,key)
        expected=[label+' 合计',f"{spec['currency']} {spec['total']:,.2f}",f"{spec['currency']} {spec['per_person']:,.2f}",f"{spec['currency']} {spec['budget_gap']:,.2f}"]
        if expected not in table_rows:consistency_errors.append({'code':'DOCUMENT_BUDGET_MISMATCH','field':'budget.scenarios.'+key,'reason':'Document total/person/gap differs from canonical calculation','repair':'用原分项与标准入口重新生成'})
        for category,amount in spec['components'].items():
          grid=[public_category(category)]+[f"{checks['budget_math'][k]['currency']} {checks['budget_math'][k]['components'][category]:,.2f}" if category in checks['budget_math'][k]['components'] else '未列入' for k in budget_keys]
          if grid not in table_rows and not any(row[:2]==[label+' / '+category,f"{spec['currency']} {amount:,.2f}"] for row in table_rows):
            consistency_errors.append({'code':'DOCUMENT_BUDGET_MISMATCH','field':'budget.scenarios.'+key+'.'+category,'reason':'Document component differs','repair':'用标准生成器重新生成'})
      if plan.get('readiness',{}).get('booking_readiness')!='READY' and '尚不具备预订条件' not in text:
        consistency_errors.append({'code':'DOCUMENT_FALSE_READINESS','field':'readiness','reason':'Preliminary qualification missing','repair':'明确初步规划、NOT_READY 和未核价说明'})
      issues.extend(x['code']+': '+x['field'] for x in consistency_errors)
      wanted={attraction_id(x):x for x in plan.get('attractions',[])}
      descriptions=[n.get('descr','').split(' | ')[0] for n in root.iter() if n.tag.endswith('}docPr')]
      for image in plan.get('images',[]):
        identifier=image.get('attraction_id') or next((k for k,x in wanted.items() if x.get('name')==image.get('attraction')),None)
        if identifier not in wanted:issues.append('Image is not bound to a selected attraction')
        elif identifier not in descriptions:issues.append('Bound image not embedded: '+str(identifier))
        if not image.get('license') or str(image['license']) not in text:issues.append('Image license attribution missing')
        author=image.get('author') or image.get('artist')
        if author and author not in text:issues.append('Image author attribution missing')
      external_urls={r.get('Target') for r in external}
      from trip_entities import selected_attractions
      for attraction in selected_attractions(plan):
        identifier=attraction_id(attraction)
        refs=[r for r in plan.get('photo_references',[]) if r.get('attraction_id')==identifier and r.get('page_status')=='ACCESSIBLE'][:3]
        for ref in refs:
          if ref.get('url') not in external_urls:issues.append('Bound external photo reference missing: '+identifier)
        req=next((r for r in plan.get('image_pipeline',{}).get('requirements',[]) if r.get('attraction_id')==identifier),{})
        if req.get('visual_status')=='EMBEDDED_LICENSED' and identifier not in descriptions:issues.append('Visual state claims an image that is not embedded')
        if req.get('visual_status')=='EXTERNAL_PHOTO_REFERENCES' and not any(r.get('photo_match')=='VERIFIED' for r in refs):issues.append('Visual state lacks verified original photo page')
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
    report={'valid':not issues,'file':str(path.resolve()),'bytes':path.stat().st_size,'text_characters':len(text),'tables':tables,'images':len(embeds),'hyperlinks':len(hyperlinks),'external_hyperlinks':len(external),'static_toc_links':len(internal),'issues':issues,'consistency_errors':consistency_errors}
except (zipfile.BadZipFile,OSError,KeyError,ET.ParseError) as e: report={'valid':False,'file':str(path.resolve()),'issues':[str(e)]}
print(json.dumps(report,ensure_ascii=False,indent=2)); raise SystemExit(0 if report['valid'] else 1)
