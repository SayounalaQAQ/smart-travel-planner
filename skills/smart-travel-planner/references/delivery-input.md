# 标准交付输入与状态

使用完整插件中的 `scripts/plugin_entry.py deliver`。它依次做用户事实门禁、确定性校验、图片核验、readiness、正式 Word 生成和生成后校验。生成器失败可有界重试；不得把自写文件冒充插件交付。

## 最小输入

`trip_profile` 是唯一事实源；兼容 `profile` / `critical_info` 和明确给出的顶层事实。至少提供目的地、出发地、日期窗口、天数、正整数人数、预算金额、币种、每人或全团口径、是否包含机票。确切起止日期可推导天数和窗口，不推测预算口径。关键用户事实被标为 assumption 时不能补足门禁。选择可由 Agent 完成，但应有已研究的候选和明确 selection_source。

```json
{
  "trip_profile": {
    "destination": "Tokyo",
    "origin": "用户的实际出发城市",
    "start_date": "2027-07-21",
    "end_date": "2027-07-27",
    "traveler_count": 2,
    "budget_amount": 10000,
    "budget_currency": "CNY",
    "budget_scope": "PER_PARTY",
    "airfare_included": true
  },
  "days": [{"date": "2027-07-21", "route_state": "AREA_LEVEL_ANCHOR",
    "activities": [{"time": "随核验后的交通安排", "activity": "抵达与入住缓冲"}]}]
}
```

此片段只示范字段，实际七日计划须提供完整七天。普通活动可用区域建议和待确认接驳；不填未知时刻、价格。星期程序计算，错误的手填星期会返回 `WEEKDAY_MISMATCH` 与正确值。

## 门禁与降级

- `PLAN_DATA_INCOMPLETE`：关键输入、每日内容或图结构缺失/损坏，需要修复；不能仅加免责声明绕过。
- `QUOTE_NOT_OBTAINED`：必要用户事实与日程数据足够，目标日期机酒报价未取得；可以生成 **PROVISIONAL** 手册，但预订仍 **NOT_READY**、预算未验证。
- `INFORMATION_UNVERIFIED`：例如运营/交通/天气证据不足；按待确认项交付，不视为已核验。
- `CONFLICT`：日期、费用、步行、作息、活动窗口或其他已知冲突；返回结构化 `code / field / reason / repair`，错误成品不交付。

`validate_plan_readiness.py --purpose planning` 检查规划交付；默认 booking 目的保持原兼容语义。`--require-ready` 仍要求真正可预订，不用于阻止合格的初步 Word。

## 预算同源计算

三档使用 `budget.scenarios.low / recommended / comfortable` 各费用类别金额，口径为 **全团**，并显式标记规划假设及所含项目。币种、人数须与画像一致。程序产生 `budget_math` 的分项、合计、人均和超过预算上限的非负差额。缺少真实报价时这是预算情景，不是核验成本。若提供了 total、per_person、budget_gap 或重复版本，它们必须与分项一致，否则阻断。不手填 Word 中的加总。

实际报价/成本继续使用现有 `cost_ledger` 和 `budget_reconciliation`；未知项不填零，不用用户上限充当成本。Word 的规划情景与实际成本核算分别注明用途。

## 固定活动证据

历史规则、最后一个周六、用户记忆和搜索摘要不能宣布目标年日期。活动仅在 `status=OFFICIALLY_ANNOUNCED`、有效 ISO `date`、`official_source_url` 和以下 `date_evidence` 完整支持时被视为已公告：`source_url` 与官方地址一致、`source_type=official`、实际 `checked_at`、`applicable_year` 与活动年份相同、`value` 为活动日期、`excerpt` 包含该目标年份的完整日期。证据对象必须来自实际读取的官方页面，不能为了过门禁而补造。

每日项目用 `event_id` 关联 `seasonal_events[].id`，或活动对象中提供相同日期证据。未确认活动保留在专题候选，不能作为确定每日活动；已确认但在旅行窗口外也不能排入日程。生成后还核对实际每日表、星期、预算和精确输入绑定。

## 图片和产物身份

候选提供 attraction_id、原页面和原图 URL。Commons 由已有 API 元数据核验；其它来源仅接受原页面图像专属 ImageObject JSON-LD 中明确的开放许可、作者和匹配 contentUrl。页面页脚版权声明不算许可。当前支持 CC0、CC BY、CC BY-SA；未支持的许可按缺图处理，不自行解释授权。

像素从核验过的原图 URL 下载，校验图像完整性、大小及地点绑定，移除 EXIF 并按原比例嵌入；作者、来源、许可和修改说明保留。原页面无法读取、许可证缺失或商业图库图被拒绝时，生成注明缺图的版本。

报告中的 `artifact_type=PLUGIN_STANDARD` 和 `official_validation_passed=true` 仅在正式生成与校验成功后返回。生成失败/未运行时不填假生成器。暂存错误 Word 不替换最终文件。宿主自制文档应单独说明，不使用这两个标准成功标志。
