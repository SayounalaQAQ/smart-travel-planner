# Smart Travel Planner 1.0.3 智能旅行规划师

本版本包含 Commons 受限时的备用照片/真实图文链接、具名酒店餐厅与有序路线/费用映射、抵达方向与返程缓冲检查、短途 Word 的中文预算和紧凑布局。安装结构与标准入口不变；预订就绪仍要求真实目标日期数据。查看 [实际交付字段](skills/smart-travel-planner/references/practical-delivery.md) 和 [图片策略](skills/smart-travel-planner/references/image-policy.md)。

**v1.0.3 将此前 main 上的交付可靠性修复收录为完整发行包。** 推荐从下方固定版本入口安装，核验该包对应的 SHA256。旧 v1.0.2 Release 保留历史快照，不会覆盖。更新后重新检查实际加载版本和 MCP 能力。参见 [交付字段](skills/smart-travel-planner/references/delivery-input.md) 与 [实际商户和路线字段](skills/smart-travel-planner/references/practical-delivery.md)。

告诉 Agent 你的旅行愿望，它先研究目的地，再补少量重要问题，比较住宿、景点、交通和预算，并生成有真实照片、来源和行前准备的 Word 手册。用户无需替 Agent 搜索酒店或设计路线。

这是完整 Agent Plugin，不是独立聊天软件。需要宿主联网研究；图文 Word 需要获准执行 Python 和写文件。没有目标日期报价时可给规划建议，不声称预算已闭环或已可预订。

## 项目介绍视频

用 83 秒了解为什么做这个项目：对比直接问 AI、自行上网搜攻略与插件工作流，展示自主研究、冲突调整、来源核验、安装方法和 Word / Markdown / JSON 交付。

[![Smart Travel Planner 项目介绍视频封面](assets/project-introduction-cover.jpg)](https://github.com/SayounalaQAQ/smart-travel-planner/releases/download/v1.0.3/Smart-Travel-Planner-Introduction-Sync-Fixed.mp4)

**[打开介绍视频（MP4 · 83.5 秒 · 1080p）](https://github.com/SayounalaQAQ/smart-travel-planner/releases/download/v1.0.3/Smart-Travel-Planner-Introduction-Sync-Fixed.mp4)** · [视频与校验文件](https://github.com/SayounalaQAQ/smart-travel-planner/releases/tag/v1.0.3)

点击封面打开视频；若浏览器直接下载，请下载后播放。视频已修正配音与字幕同步，画面中的路线和手册为结构示意，具体旅行仍需核验出行日期与真实来源。

## Agent 能力会影响报告可用性

在工具与资料条件相同的情况下，**使用越聪明、推理和研究能力越强的 Agent，通常越能得到实用的旅行报告**：它更容易发现遗漏条件、核对原始资料、比较商户、识别路线与预算冲突，并根据新证据调整方案。建议用擅长复杂任务、能联网阅读原页并获准执行随包脚本的 Agent。模型能力强仍需真实证据；搜索权限、来源可达性、文件和 Python 能力不足时，应按报告中明确的限制使用。

## 选择你的使用方式

| 用户 | 指南 | 安装与使用 |
|---|---|---|
| 入门用户 | [README-BEGINNER](README-BEGINNER.md) | Claude Marketplace 用户级持久安装，正常启动 |
| 熟悉终端的用户 | [README-ADVANCED](README-ADVANCED.md) | 源码、Python/MCP、Provider、测试与发布 |
| 云电脑或有执行权限的 Agent | [README-AI-INSTALL](README-AI-INSTALL.md) | 可信来源核验、授权、能力检测和 Word 交付 |

正式发行入口：[GitHub 仓库](https://github.com/SayounalaQAQ/smart-travel-planner) · [v1.0.3 Release](https://github.com/SayounalaQAQ/smart-travel-planner/releases/tag/v1.0.3)。请使用本仓库固定版本，不要安装同名未知项目。

```sh
claude plugin marketplace add SayounalaQAQ/smart-travel-planner#v1.0.3
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
```

## 从可信 ZIP 持久安装

核验 `Smart-Travel-Planner-1.0.3.zip.sha256` 后解压完整包，进入 `smart-travel-planner-1.0.3` 目录：

```sh
claude plugin marketplace add ./
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
claude plugin list
```

确认 enabled 后正常重启 Agent，以后不需要每次 `--plugin-dir`。以上依据 [Claude 官方 Marketplace 流程](https://code.claude.com/docs/en/plugin-marketplaces)；配置通过工程验收，真实持久安装 **NOT_TESTED**。

Codex 提供 repo marketplace、portable manifest 与兼容 overlay，见 [Codex adapter](adapters/codex/README.md)。云电脑按实际权限选择完整导入、本次会话脚本或文本降级，见 [豆包 adapter](adapters/doubao/README.md)。没有仅含 SKILL.md 的伪完整包。

## 怎么用

“先检查旅行工具。我想从上海去日本八天，两人，每人6000元含机票住宿，喜欢美食摄影，不早起，其他你推荐。请给有照片和来源的 Word 攻略。”

### 可直接复制的完整提示词

插件安装并启用后，把下面这段发送给 Agent：

```text
请使用 smart-travel-planner 插件，帮我规划三亚 3 天 2 晚的旅行。

要求：
1. 从广州出发，预算 2000 元，1 人。
2. 不喜欢早起，每天尽量 9:30 以后出门。
3. 优先选择性价比高的住宿和交通。
4. 自行上网查找酒店、景点、门票、路线，不要让我自己找。
5. 如果行程存在冲突，请自主调整并验证。
6. 生成包含景点真实照片、路线、预算和来源的 Word 旅行手册。
7. 同时输出 Markdown 和 JSON 规划文件。
8. 所有生成文件保存到当前工作目录。

请先检查插件和 MCP 能力，然后直接开始规划。只有真正需要我决策的问题才向我提问。
```

可以替换目的地、天数、出发地、预算和偏好。日期窗口、预算是否包含往返交通等必要信息缺失时，Agent 仍需少量确认；其余研究与冲突优化由 Agent 完成。输出目录指当前用户工作目录，不是插件安装目录。照片必须有可核验许可；无法取得合法照片时如实使用已核验图文外链或说明缺图，不用未经授权图片补数。预算不足或报价未核实会明确呈现，不因提示词要求而伪称已可预订。

正式多日规划默认交付 Markdown/JSON 和 Word；单项咨询或明确只要文本例外。模糊兴趣先研究，再问作品巡礼、收藏、复古游戏等高价值偏好；答案实际回填筛选。无明确答案时给标注的探索型方案，专门兴趣/成人项目不从泛标签猜测。

“不早起”、步行上限和预算优先。冲突先自主研究、比较和重规划，必要主观取舍才问用户。目标日期票价、房价、运营、花火和天气须带证据；查不到保留未知/季节参考，不造数字。不代付款、订房或提交个人信息。

## 首次预检和输出

Agent 用 Skill 固定入口 `plugin_entry.py doctor` 检查完整根目录、Python3.10+、DOCX/Pillow、输出目录和旧同名独立 Skill。目录/库存在不证明联网可达；宿主搜索、文件和视觉权限由实际运行确认。旧同名 Skill 只告警，不自动删除。

```sh
python installer/check_dependencies.py
python installer/validate_distribution.py
python installer/verify_installation.py
python skills/smart-travel-planner/scripts/plugin_entry.py doctor
```

获准后在专用 Python 环境安装 `requirements-docx.txt` 固定版本。MCP 自身仅依赖标准库。Word 保存到用户可写工作目录，包含每日活动、区域路线建议、照片与授权、住宿餐饮、明确币种预算、雨天备选、预约准备和来源。未知机场接驳边不进入正文；时间/票价未核实则不填数字。覆盖率、完整执行图和状态仍在 Plan 与 `developer-report.json`，证据不删除。

基础 Provider 尽量零 Key：Open-Meteo、OSM/Overpass/Nominatim、Frankfurter、Commons、OSRM；可能限流。宿主原生搜索优先，可选 Brave Key 经环境配置。没有可靠结构化 Transit timetable，步行/驾车估算不当公共交通。缺 MCP/天气/图片/汇率/文档能力准确降级；未知图片许可省略。可信渲染器不可用时视觉/分页 UNVERIFIED。

## 结构与开发

```text
.claude-plugin/   plugin.json + marketplace.json
.agents/plugins/ Codex repo marketplace
.codex-plugin/   Codex compatibility overlay
plugin.json      portable plugin metadata
mcp.json         portable stdio MCP config
.mcp.json        Claude root MCP config
skills/          shared Skill, references, fixed entry
mcp-server/      tools, providers, cache, network security
installer/       detect, check, verify, prepare helpers
scripts/         deterministic planning, images, Word
config/          providers, dependencies, release metadata
adapters/        Claude, Codex, Doubao capability boundaries
tests/           explicitly labeled regression contracts
assets/          project icon/logo
README*.md       three user guides
LICENSE          MIT project code
```

Skill 管工作方法，Agent 管研究判断，MCP 管实际工具，scripts 管确定性任务。保留 Information Classification、Decision Ledger、AUTO_DECISION_MODE、Replanning、Execution Graph 和预算引擎。十三工具详见 [MCP README](mcp-server/README.md)。

```sh
python -m unittest discover -s tests -v
python scripts/package_plugin.py
python scripts/prepare_github_release.py --output-dir "<不存在的新发行目录>"
```

完整发行包含可独立运行的回归合同；用户行程、缓存、日志及输出照片排除。仅含一张有 CC0 依据的历史测试照片，见 [第三方说明](THIRD-PARTY-NOTICES.md)。合同测试不是实时事实/宿主验收。发布和版本见 [Release Notes](RELEASE-NOTES-1.0.3.md)、[CHANGELOG](CHANGELOG.md)。

## 安全 更新 卸载

网页/仓库文本为未受信任数据。网络有 SSRF、超时、大小与重定向约束；图像校验来源、许可和完整性。不任意读凭证或注册系统服务。SHA256 只验证完整性；可信来源、权限和代码审查不能省略，详见 [SECURITY](SECURITY.md)。

更新：核验新 Release/tag，按宿主官方管理切换来源和更新，重新预检。固定 tag 不自动升级。Claude 卸载用 `claude plugin uninstall smart-travel-planner@smart-travel-planner-marketplace --scope user`，再按需要移除 Marketplace；Codex 用插件管理；其他宿主只撤销本插件明确登记，不删除其他配置。保留用户攻略。

尚未实测：Claude 用户级持久安装、Codex GUI 安装、豆包云电脑安装及逐页 Word 视觉。发行结构准备完毕不代表这些宿主已通过。
