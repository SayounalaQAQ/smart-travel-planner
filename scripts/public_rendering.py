"""Type-safe tourist prose. Unsupported internal keys never become repr output."""
import re
LABELS={'when':'时间','time':'时间','item':'事项','decision':'决定','reason':'原因','risk':'风险','mitigation':'应对','note':'注意','notes':'提示','description':'说明',
    'activity':'活动','name':'名称','place':'地点','alternative':'替代','why_not':'舍弃原因','why_recommended':'推荐理由','drawbacks':'代价','tradeoff':'取舍','impact':'影响',
    'selected_option':'选择','why_selected':'原因','old_decision':'原安排','new_decision':'现在建议','title':'说明','text':'说明','value':'参考','message':'提示',
    'opening_hours':'营业','price_reference':'价格口径','address':'地址','source_url':'来源','url':'来源','limitations':'限制','repair':'行动建议','warning':'提醒','required_checks':'启用条件','status':'状态'}
ENUMS={'normal':'常规','regular':'常规作息','solo':'单人','HIGH':'高','MEDIUM':'中','LOW':'低','UNKNOWN':'未知','UNVERIFIED':'未核验','UNAVAILABLE':'尚未获得',
    'NOT_READY':'尚不具备预订条件','PROVISIONAL':'初步方案','CANDIDATE':'候选','CONFIRMED':'已确认','TRAIN':'铁路','AIR':'飞机','FLIGHT':'航班','CHECK_REQUIRED':'需要核对'}
RAW=re.compile(r"\{\s*['\"][^'\"{}\n]+['\"]\s*:|\[\s*\{\s*['\"]|\b(?:None|True|False)\b\s*[,}]")
def public_text(value):
    if value is None:return ''
    if isinstance(value,bool):return '是' if value else '否'
    if isinstance(value,(int,float)):return str(value)
    if isinstance(value,str):return ENUMS.get(value,value).strip()
    if isinstance(value,(list,tuple)):return '；'.join(x for x in (public_text(v) for v in value) if x)
    if isinstance(value,dict):
        parts=[]
        for k,v in value.items():
            if k not in LABELS:continue
            text=public_text(v)
            if text:parts.append(LABELS[k]+'：'+text)
        if value.get('evidence_ids'):parts.append('证据范围：相关资料见来源索引；未经核验的条件仍须确认')
        return '；'.join(parts)
    return ''

def public_text_errors(text,section='正文'):
    errors=[]
    for pattern,code,reason in [(RAW,'PUBLIC_DATA_STRUCTURE_LEAK','Raw Python/JSON representation'),
        (re.compile(r'适合：\s*(?:$|\n)|查询于[：\s]*未记录'),'PUBLIC_EMPTY_FIELD','Empty recommendation/source field'),
        (re.compile(r'\b(?:normal|regular|AREA_LEVEL_ANCHOR|ROUTE_PENDING)\b'),'PUBLIC_ENUM_LEAK','Internal enum')]:
        if pattern.search(text):errors.append(dict(code=code,field=section,reason=reason,repair='使用 public_text 和公开字段映射；省略空项，未核验条件给行动提醒'))
    return errors
