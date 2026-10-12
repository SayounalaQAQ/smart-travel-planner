# 入门用户指南

## 你需要什么

Claude Code，以及它能调用的 Python 3.10+。完整图文 Word 还需要 python-docx 和 Pillow；Agent 可以在得到许可后帮助安装。这是 Agent 插件，不是双击启动的独立聊天软件。

## 安装一次，以后正常启动

可信来源：[本项目 GitHub 仓库](https://github.com/SayounalaQAQ/smart-travel-planner)。最新交付修复在 `main`；版本元数据仍为 1.0.2。[v1.0.2 Release](https://github.com/SayounalaQAQ/smart-travel-planner/releases/tag/v1.0.2) 是修复前的固定快照，未被覆盖。推荐使用下方 GitHub 命令获取当前源码。使用本地 ZIP 时，应取得本次修复包及它自己的 SHA256；不要用旧 Release 摘要校验新包。

先按下方“ZIP 核验”检查并解压。进入 `smart-travel-planner-1.0.2` 目录，终端运行：

```sh
claude plugin marketplace add ./
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
claude plugin list
```

`--scope user` 是持久用户级安装。确认输出中本插件为 enabled，再重新正常启动 `claude`；以后无需每次 `--plugin-dir`。若被项目或组织政策禁用，按宿主设置启用，不绕过政策。当前仅完成清单/源码验收，真实用户级安装尚待宿主测试。

从正式 GitHub 仓库安装当前 `main`：

```sh
claude plugin marketplace add SayounalaQAQ/smart-travel-planner
claude plugin install smart-travel-planner@smart-travel-planner-marketplace --scope user
```

目录 `.claude-plugin/marketplace.json` 是目录清单；插件 `source` 为 `./`，从仓库根解析，包含 Skill、MCP 和所有脚本。不要只复制 SKILL.md，也不要额外安装同名独立 Skill。

## 第一次使用

说：“先检查智能旅行规划师的 Python、图片、Word 和联网能力。我要从上海去日本八天，两人，每人6000元包含机票住宿，喜欢美食摄影，不早起，其他你推荐。请生成有照片和来源的 Word。”

Skill 可匹配自然语言旅行需求；匹配失败时可明确调用 `/smart-travel-planner:smart-travel-planner`。Agent 应先调用随包 `plugin_entry.py doctor`，检查旧同名 Skill、依赖及输出目录。旧版 `~/.claude/skills/smart-travel-planner` 可由你备份移走；程序不会擅自删除。

有权限且你同意后，Agent 可在专用 Python 环境执行 `python -m pip install -r requirements-docx.txt`。若 MCP 的 `python` 不在 PATH，参考高级指南选择实际可执行文件；修改插件缓存可能在更新后丢失，须重新检查。缺少执行权限时只能输出宿主支持的文本或文件，不能保证 Word。

手册保存在 Agent 报告的用户工作目录；图片带作者、许可和来源。未来天气、活动、机酒库存或路线没查到，会给待确认项，不补造数字。攻略不会替你付款或预订。

## ZIP 核验

从同一可信分发位置获取 ZIP 与对应的 `.zip.sha256`，核对来源，再比较。以下文件名是旧固定 Release 示例；本次修复包应替换为实际文件名，不混用校验和：

```powershell
Get-FileHash -LiteralPath './Smart-Travel-Planner-1.0.2.zip' -Algorithm SHA256
Get-Content -LiteralPath './Smart-Travel-Planner-1.0.2.zip.sha256'
```

macOS/Linux：`sha256sum Smart-Travel-Planner-1.0.2.zip`（macOS 可用 `shasum -a 256`）。摘要不一致就停止。SHA256 验证完整性，不单独证明发布者身份。

## 更新和卸载

固定 `#v1.0.2` 的来源不会取得 `main` 上的修复。已安装旧版时，先在 `/plugin` 的 Marketplaces 中检查来源，按宿主官方流程改为本仓库当前分支，再更新并重启会话。当前版本号未升级，不能仅凭显示“1.0.2”确认缓存已更新；让 Agent 检查加载目录是否包含 `scripts/handbook_validation.py` 及每日住宿连续性规则。

已经跟踪 `main` 的来源可运行：

```sh
claude plugin marketplace update smart-travel-planner-marketplace
claude plugin update smart-travel-planner@smart-travel-planner-marketplace
```

按实际宿主输出确认源码更新，重新启动或重新加载插件后预检。下方卸载命令只用于卸载；移除 marketplace 会卸载其中所有插件，不能当作无损更新操作。

```sh
claude plugin uninstall smart-travel-planner@smart-travel-planner-marketplace --scope user
claude plugin marketplace remove smart-travel-planner-marketplace
```

卸载后需要的 Word 仍在用户工作目录。仅禁用可使用宿主插件管理界面；不需要删除旅行文件。

命令依据：[Claude 安装管理](https://code.claude.com/docs/en/discover-plugins)、[Marketplace 建立与路径规则](https://code.claude.com/docs/en/plugin-marketplaces)。安装、重启和版本查询按你当前客户端实际输出确认。
