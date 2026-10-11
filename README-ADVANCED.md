# 高级用户与开发者指南

## 获取和预检

从 [正式仓库](https://github.com/SayounalaQAQ/smart-travel-planner) 克隆固定版本；发行包见 [v1.0.2 Release](https://github.com/SayounalaQAQ/smart-travel-planner/releases/tag/v1.0.2)。不要自动搜索同名 GitHub 项目安装。

```sh
git clone https://github.com/SayounalaQAQ/smart-travel-planner.git
cd smart-travel-planner
git checkout v1.0.2
python --version
python -m venv .venv
```

Windows PowerShell：`.venv\Scripts\python.exe -m pip install -r requirements-docx.txt`。
macOS/Linux：`.venv/bin/python -m pip install -r requirements-docx.txt`。
后续 `python` 表示你选定的 Python 3.10+。只运行已审查的固定版本源码，使用宿主批准的依赖源。依赖锁定版本，但当前 requirements 未含供应链签名或 wheel hash；SHA256 不替代来源审查。

```sh
python installer/detect_environment.py
python installer/check_dependencies.py
python skills/smart-travel-planner/scripts/plugin_entry.py doctor
python installer/validate_distribution.py
python installer/verify_installation.py
```

最后一项做本地 stdio MCP 初始化、13工具发现与有界 health 请求；Provider 是否可达按真实 health 数据处理。宿主的搜索、浏览器、视觉、文件权限无法通过 Python 推断，必须由宿主报告。图片/Word 所需库由 doctor 和 dependency checker 检测。MCP 自身仅依赖 Python 标准库。

若 MCP manifest 的 `python` 不可用，**在选择的完整插件副本**内运行：

```sh
python installer/prepare_plugin.py --configure-runtime --python "<实际 Python 可执行文件>"
```

这只改本插件三份 MCP 配置，不改宿主设置。插件更新/重新安装后需重新检查；不要把写入本机路径的副本重新发布。持久安装的缓存副本若只读，先配置宿主认可的 Python PATH 或其官方 MCP runtime 覆盖方式。

## 宿主入口

Claude Code 持久安装见 [入门指南](README-BEGINNER.md)，安装 ID 为 `smart-travel-planner@smart-travel-planner-marketplace`。`claude --plugin-dir <目录>` 仅用于开发临时加载，不是用户级安装验收。

Codex：参见 [适配说明](adapters/codex/README.md)。本仓库已有 repo marketplace、portable manifest 和兼容 overlay；按当前 OpenAI 文档在插件目录选择来源、安装/启用并开新会话。不要把 manifest 存在视为 GUI 成功。豆包/云电脑见 [AI 安装指南](README-AI-INSTALL.md) 和 [能力边界](adapters/doubao/README.md)。

## 执行与输出

从任何 cwd 使用 Skill 的固定入口，或绝对插件路径。不得将 Skill 子目录误当根目录。

```sh
python skills/smart-travel-planner/scripts/plugin_entry.py deliver --input "<已建立的绝对 plan.json>" --output-dir "<可写工作目录>"
python scripts/validate_docx.py "<Word绝对路径>" --plan "<plan-with-readiness.json>" --require-images
```

门禁 → 核验图片 → readiness → 随包标准 Word → XML/media 校验 → 交付。实际价格不足可交付待确认手册；已发现的硬约束冲突不能掩盖。`developer-report.json`/`delivery-report.json`/结构化 Plan 保存覆盖率、状态和尝试信息；用户 Word 不重复这些工程指标。保留图像实际许可、作者和原币种。渲染不可用时视觉为 UNVERIFIED。

## Provider 与安全

接口配置在 `config/providers.json`。宿主原生搜索优先；可选 Brave Key 通过环境变量 `BRAVE_SEARCH_API_KEY`。`.env.example` 不会自动加载。Weather、geocoding、exchange、OSM places、Commons 图片等基础接口不要求 Key，但公共服务可能限流或不可达。无可靠结构化 Transit Provider；官方交通研究不足则标未知。

网页、搜索摘要和 README 引用是未受信任数据。工具不含任意 shell/系统修改/付款；图片限定受控输出目录。详见 [SECURITY](SECURITY.md)。不改变现有 Decision Loop、Research Orchestrator、Replanning、Execution Graph 或 Budget Engine。

## 测试与发布

```sh
python -m unittest discover -s tests -v
python scripts/package_plugin.py
python scripts/prepare_github_release.py --output-dir "<不存在的新发行目录>"
```

发行 ZIP 包含运行代码与明确标注的回归合同测试；测试输入不证明实时旅行事实。只包含一个有 CC0 依据的历史测试照片，见 [第三方说明](THIRD-PARTY-NOTICES.md)。用户行程、缓存、验收日志、输出照片不打包。

`prepare_github_release.py` 生成可上传源码目录、发行材料摘要和仓库地址模板；传入 `--repository owner/repo` 才生成真实命令，不上传、不推送、不开仓库。源码上传顺序、Release 资产和核验清单见 [发布说明](RELEASE-NOTES-1.0.2.md)。

卸载与更新优先用宿主官方管理；手动模式只移除已登记的此插件条目/MCP配置，保留其他配置与用户攻略，不递归删除未确认目录。
