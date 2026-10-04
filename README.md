# 567 Agent 官方能力市场

本仓库为 567 Agent 提供可浏览和安装的 Skills 与 MCP 配置。根目录的 [`marketplace.json`](marketplace.json) 是能力清单；客户端兼容副本保存在 [`.567agent/marketplace.json`](.567agent/marketplace.json) 和 [`.vetta/marketplace.json`](.vetta/marketplace.json)。同步时三个文件保持一致。

## Skills 来源

GitHub Actions 每天扫描以下仓库里的 `SKILL.md`，并镜像技能所需的参考文件、脚本和模板：

| 上游 | 扫描目录 | 说明 |
| --- | --- | --- |
| [microsoft/skills](https://github.com/microsoft/skills) | `.github/plugins/`、`.github/skills/` | Azure、Foundry、SDK 和开发工具 |
| [github/awesome-copilot](https://github.com/github/awesome-copilot) | `skills/`、`.github/skills/` | GitHub Copilot 社区技能 |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | `skills/` | 软件工程、测试、代码质量和性能 |

此外，清单中保留了仓库已有的 74 个 `anbeime/skill` 历史技能镜像。它们是随本市场仓库分发的文件，**不是 567 Agent 客户端内置能力**。该上游未声明许可证，因此目前只保留既有镜像，不自动抓取更新。

收录要求上游仓库声明 MIT 许可；若单个技能声明 Apache-2.0，或在本地 `LICENSE.txt` 中给出 MIT/Apache-2.0 条款，也会保留对应许可文本和来源署名。未知或无法核实的许可会让本次同步停止，等待处理。新增来源前请先确认再分发条款。

同步器跳过隐藏目录、符号链接、超过 512 KiB 的 `SKILL.md`，以及单文件超过 2 MiB 或总资源超过 10 MiB 的技能。若已收录技能因限制被跳过，会保留此前版本；上游拉取失败、目录意外为空或仓库许可变化时，不发布部分结果。技能标识按来源仓库和上游路径复用，内容指纹涵盖说明及附属文件，内容变化会更新 `configVersion` 和市场版本。

分类依据技能名称和描述自动判断，类别包括系统、网络、开发、设计、文档、媒体、研究、数据、数据库、写作、商业、效率、安全和实用技能。分类是便于浏览的规则标签，并非对技能质量或安全性的认证。

## MCP

当前有 10 个 MCP 配置。其中 6 个自动同步自 [modelcontextprotocol/servers](https://github.com/modelcontextprotocol/servers) 当前维护的参考服务器：Filesystem、Fetch、Memory、Git、Sequential Thinking 和 Time。同步器读取各服务的 `package.json` 或 `pyproject.toml`，把它们映射为 567 Agent 支持的本地 `stdio` 配置，并锁定上游包版本；上游版本更新后，日常同步会更新清单和安装配置。协议演示用的 Everything 服务没有加入市场。

Brave Search、GitHub、PostgreSQL 和 SQLite 是此前手工维护的配置，目前仍保留以兼容已有条目；它们来自已归档的 MCP 参考实现，不会从归档源自动更新。新服务采用自动收录前，需要先确认其维护状态、许可、安装方式和凭据要求。

官方 [MCP Registry](https://registry.modelcontextprotocol.io/) 是社区服务发现目录，当前没有把其中所有第三方条目自动变成可安装项。Registry 上架不代表维护质量或安全审查；本市场只自动同步官方维护仓库中明确支持的服务。

Python MCP 使用 `uvx`，Node.js MCP 使用 `npx`；运行相应服务需要本机安装这些工具。Filesystem 默认只开放当前目录。Fetch 上游提示它可以访问本机和内网地址；Git MCP 支持暂存、提交和切换分支，上游仍将其标为早期开发。启用前请按需限制它们可访问的目录和仓库。现有 Brave Search、GitHub、PostgreSQL 配置可能需要 API 密钥或数据库连接信息；安装前请检查 `mcps/<slug>/mcp.json` 中的参数。

## 自动同步和翻译

工作流 [`sync-marketplace.yml`](.github/workflows/sync-marketplace.yml) 每天 **00:00 UTC（北京时间 08:00）**运行，也支持在 GitHub Actions 页面手动触发；推送 `marketplace-v*` tag 也会触发同步。工作流先运行测试，再抓取 Skills 与官方 MCP 来源、生成清单和镜像文件，并将变更推送到 `main`。同一分支的同步任务会排队串行执行。

要翻译新收录的英文说明，仓库 Actions Secrets 需要配置 `API_567_KEY`。`API_567_BASE_URL` 和 `API_567_MODEL` 可选，未配置时使用脚本默认值。翻译默认使用 6 个并发线程，可通过 `API_567_TRANSLATION_WORKERS` 调整为 1–16 个。没有密钥或调用失败时，说明保留原文，之后仍可重试；已成功生成的中文翻译会按原文缓存，避免重复请求。

## 本地运行

需要 Python 3.11 或更新版本；同步还需要 Git 和网络访问。

```bash
python3 -m unittest discover -s tests -v
python3 sync_marketplace.py
```

第二条命令会下载三个 Skills 来源和官方 MCP 参考仓库，并更新 `skills/`、`mcps/` 和三份市场清单。配置 `API_567_KEY` 后，也会并发翻译新增或英文说明有变化的条目；未变化且已有成功译文的条目会复用缓存。只改脚本或来源配置不会改变 GitHub 上的自动任务，需先推送代码到 `main`。
