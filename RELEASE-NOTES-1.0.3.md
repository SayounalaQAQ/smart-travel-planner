# Smart Travel Planner v1.0.3

完整 Plugin 发行包，将 v1.0.2 后的交付可靠性修复正式发布。仓库：[SayounalaQAQ/smart-travel-planner](https://github.com/SayounalaQAQ/smart-travel-planner)。旧 v1.0.2 Release 保持不变。

## 本版内容

- 区分初步规划交付与预订准备度：必要信息完整但目标日期机酒报价不足时，可交付明确假设的初步 Word，仍保持 NOT_READY。
- 程序计算星期，核验活动年份和旅行窗口，预算合计来自同源分项；硬冲突拒绝错误成品。
- 检查每日起点、夜间终点和跨日住宿连续性，拦截重复交通；必要交通费用统一绑定、去重，未知费用不当作零。
- Word 类型安全渲染风险、决策和清单，避免 Python/JSON 对象、空字段和错误交通口径进入正文。
- 临近出发优先核验真实车票、住宿运营、接驳、天气与预约；具名商户按具体分店研究。
- 保留图片原页、作者、许可和再分发校验；照片不可合法嵌入时使用分级核验的图文外链，未确认照片不冒称已验证。
- README 增加可直接复制的“广州出发、三亚3天2晚、2000元、晚起、自主研究、Word/Markdown/JSON”提示词。
- 插件、MCP 与发行元数据统一为 1.0.3；三类指南同步固定版本安装入口。此次发布不重写旅行规划算法。

## 安装

```sh
claude plugin marketplace add SayounalaQAQ/smart-travel-planner#v1.0.3
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
```

已固定 v1.0.2 的用户须按宿主官方流程切换来源到 v1.0.3，再更新并重启/重新加载。检查实际插件及 MCP 版本与工具能力。Codex 和云电脑入口见仓库内三类指南；配置有效不等于真实宿主安装已经通过。

## 下载与完整性

- `Smart-Travel-Planner-1.0.3.zip`：完整插件、Skill、MCP、安装器、正式脚本、依赖资源和回归合同。
- `Smart-Travel-Planner-1.0.3.zip.sha256`：该 ZIP 的 SHA256；不能沿用旧版本摘要。

完整解压后再安装，不只复制 SKILL.md。发行包排除用户真实行程、生成文档、研究缓存、日志、凭据和未获许可的输出图片。仅保留明确归属和许可的项目资源/测试图片。

## 验收与限制

此前实际跨目的地交付回归包括内蒙古原输入拒绝与修订、三亚、成都标准 DOCX，并保留真实联网记录；未把合同测试冒充目标日期报价。v1.0.3 发布前重跑完整测试、干净 ZIP、MCP 初始化和标准交付检查。

没有可靠目标日期报价/路线时仍明确 estimated、unverified 或 unavailable，不自动付款、预订或提交个人信息。合法照片受来源可达性限制；强 Agent 仍不能替代证据。Claude 用户级持久安装、Codex GUI 和豆包真实客户端安装为 NOT_TESTED；缺少可信渲染器时逐页 Word 视觉为 UNVERIFIED。
