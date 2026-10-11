# Smart Travel Planner 1.0.2 智能旅行规划师

告诉 Agent 你的旅行愿望，它先研究目的地，再补少量重要问题，比较住宿、景点、交通和预算，并生成有真实照片、来源和行前准备的 Word 手册。用户无需替 Agent 搜索酒店或设计路线。

这是完整 Agent Plugin，不是独立聊天软件。需要宿主联网研究；图文 Word 需要获准执行 Python 和写文件。没有目标日期报价时可给规划建议，不声称预算已闭环或已可预订。

## 选择你的使用方式

| 用户 | 指南 | 安装与使用 |
|---|---|---|
| 入门用户 | [README-BEGINNER](README-BEGINNER.md) | Claude Marketplace 用户级持久安装，正常启动 |
| 熟悉终端的用户 | [README-ADVANCED](README-ADVANCED.md) | 源码、Python/MCP、Provider、测试与发布 |
| 云电脑或有执行权限的 Agent | [README-AI-INSTALL](README-AI-INSTALL.md) | 可信来源核验、授权、能力检测和 Word 交付 |

正式发行入口：[GitHub 仓库](https://github.com/SayounalaQAQ/smart-travel-planner) · [v1.0.2 Release](https://github.com/SayounalaQAQ/smart-travel-planner/releases/tag/v1.0.2)。请使用本仓库固定版本，不要安装同名未知项目。

```sh
claude plugin marketplace add SayounalaQAQ/smart-travel-planner#v1.0.2
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
```

## 从可信 ZIP 持久安装

核验 `Smart-Travel-Planner-1.0.2.zip.sha256` 后解压完整包，进入 `smart-travel-planner-1.0.2` 目录：

```sh
claude plugin marketplace add ./
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
claude plugin list
```

确认 enabled 后正常重启 Agent，以后不需要每次 `--plugin-dir`。以上依据 [Claude 官方 Marketplace 流程](https://code.claude.com/docs/en/plugin-marketplaces)；配置通过工程验收，真实持久安装 **NOT_TESTED**。

Codex 提供 repo marketplace、portable manifest 与兼容 overlay，见 [Codex adapter](adapters/codex/README.md)。云电脑按实际权限选择完整导入、本次会话脚本或文本降级，见 [豆包 adapter](adapters/doubao/README.md)。没有仅含 SKILL.md 的伪完整包。

## 怎么用

“先检查旅行工具。我想从上海去日本八天，两人，每人6000元含机票住宿，喜欢美食摄影，不早起，其他你推荐。请给有照片和来源的 Word 攻略。”

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

完整发行包含可独立运行的回归合同；用户行程、缓存、日志及输出照片排除。仅含一张有 CC0 依据的历史测试照片，见 [第三方说明](THIRD-PARTY-NOTICES.md)。合同测试不是实时事实/宿主验收。发布和版本见 [Release Notes](RELEASE-NOTES-1.0.2.md)、[CHANGELOG](CHANGELOG.md)。

## 安全 更新 卸载

网页/仓库文本为未受信任数据。网络有 SSRF、超时、大小与重定向约束；图像校验来源、许可和完整性。不任意读凭证或注册系统服务。SHA256 只验证完整性；可信来源、权限和代码审查不能省略，详见 [SECURITY](SECURITY.md)。

更新：核验新 Release/tag，按宿主官方管理切换来源和更新，重新预检。固定 tag 不自动升级。Claude 卸载用 `claude plugin uninstall smart-travel-planner@smart-travel-planner-marketplace --scope user`，再按需要移除 Marketplace；Codex 用插件管理；其他宿主只撤销本插件明确登记，不删除其他配置。保留用户攻略。

尚未实测：Claude 用户级持久安装、Codex GUI 安装、豆包云电脑安装及逐页 Word 视觉。发行结构准备完毕不代表这些宿主已通过。
