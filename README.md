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

当前有 7 个手工维护的 MCP 配置：Filesystem、Fetch、Brave Search、GitHub、PostgreSQL、SQLite 和 Memory。它们由同步脚本中的精选列表生成，**目前没有自动抓取 MCP 上游**。

需要发现更多服务时，可以查看 [官方 MCP Registry](https://registry.modelcontextprotocol.io/) 及其 [API 文档](https://github.com/modelcontextprotocol/registry/blob/main/docs/reference/api/official-registry-api.md)。官方 Registry 是可查询的服务目录；将条目加入本市场仍需审核维护状态、许可、安装方式和所需凭据，并映射为本仓库的 MCP 配置格式。

Filesystem、Brave Search、GitHub、PostgreSQL、SQLite 和 Memory 等配置源自 MCP 参考实现。MCP 官方仓库将 Brave Search、GitHub、PostgreSQL 和 SQLite 列为已归档项目；参考实现不等同于生产质量或安全保证。集成状态请查看 [官方参考服务器说明](https://github.com/modelcontextprotocol/servers)。

Fetch 和 SQLite 通过 `uvx` 启动，需要安装 `uv`；Fetch 上游见[项目说明](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch)，SQLite 参考实现在[归档仓库](https://github.com/modelcontextprotocol/servers-archived/tree/main/src/sqlite)。Node.js MCP 使用 `npx`。Brave Search、GitHub 和 PostgreSQL 还需要相应 API 密钥或数据库连接信息。

## 自动同步和翻译

工作流 [`sync-marketplace.yml`](.github/workflows/sync-marketplace.yml) 每天 **00:00 UTC（北京时间 08:00）**运行，也支持在 GitHub Actions 页面手动触发；推送 `marketplace-v*` tag 也会触发同步。工作流先运行测试，再抓取来源、生成清单和镜像文件，并将变更推送到 `main`。同一分支的同步任务会排队串行执行。

要翻译新收录的英文说明，仓库 Actions Secrets 需要配置 `API_567_KEY`。`API_567_BASE_URL` 和 `API_567_MODEL` 可选，未配置时使用脚本默认值。没有密钥或调用失败时，说明保留原文，之后仍可重试；已成功生成的中文翻译会按原文缓存，避免重复请求。

## 本地运行

需要 Python 3.11 或更新版本；同步还需要 Git 和网络访问。

```bash
python3 -m unittest discover -s tests -v
python3 sync_marketplace.py
```

第二条命令会下载三个 Skills 来源并更新 `skills/`、`mcps/` 和三份市场清单。配置 `API_567_KEY` 后，也会翻译尚无缓存的新英文说明。只改脚本或来源配置不会改变 GitHub 上的自动任务，需先推送代码到 `main`。
