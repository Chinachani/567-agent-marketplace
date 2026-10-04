# 567 Agent 官方能力市场

本仓库是 567 Agent 能力市场的**目录与内容分发源**，不是桌面客户端，也不会在这里运行 MCP 服务。客户端读取市场清单来浏览能力，并安装有完整内容和配置的条目。

仓库维护两类能力：

- **Skills**：镜像 `SKILL.md` 及其必要的参考资料、脚本和模板。
- **MCP**：收集上游项目的发现信息；只有维护者审核过安装配置的 MCP 才提供安装。尚未审核的候选仍可用于发现和查看上游信息，但不会触发安装。

市场现在按用途分成两类清单：

- **可安装清单**：根目录 [`marketplace.json`](marketplace.json) 及兼容副本 [`.567agent/marketplace.json`](.567agent/marketplace.json)、[`.vetta/marketplace.json`](.vetta/marketplace.json)。这里仅发布可直接分发的 Skills、维护者审核过的 MCP 和其他能力；对应内容在 `skills/` 与 `mcps/`，客户端仍通过主分支归档安装。
- **MCP 发现目录**：同步器生成到 `catalog-dist/`，工作流将它发布到独立的 [`catalog` 分支](https://github.com/Chinachani/567-agent-marketplace/tree/catalog)。`index.json` 记录清单版本、分类计数和分片摘要；`shards/` 按分类和大小拆分尚未审核的 MCP 候选；`classification-suggestions.json` 供维护者审核。客户端只把候选作为只读信息展示，不会提供安装入口。

发现目录的更新不会提高 `marketplaceVersion`，也不会让客户端重下 Skills 归档；可安装能力变化才会更新主清单版本。当前维护者确认的 MCP 安装元数据记录在 [`mcp-curation.json`](mcp-curation.json) 中；新增上游候选须经审核后才会进入可安装范围。兼容客户端仍可使用旧主分支清单；新客户端优先读取 `catalog` 分支，缺少该分支时沿用已缓存目录。

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

MCP 目录全量发现以下上游的条目：官方 [MCP Registry](https://registry.modelcontextprotocol.io/)（只取每个服务的 latest 版本）、[mcpHQ](https://landscape.mcphq.org/)、[punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) 和 [TensorBlock/awesome-mcp-servers](https://github.com/TensorBlock/awesome-mcp-servers)。同步器按上游 GitHub 仓库或 Registry 名称去重，并保留来源链接。聚合仓库只作为发现索引；本仓库不因此重新分发其收录项目的代码。

发现不等于可安装。只有在 `mcp-curation.json` 中经维护者确认分类、功能标签、运行方式、平台、权限范围、认证要求和安装配置的条目，才会有 `mcp.json` 并标记为可安装。其它候选仍以 `type: "mcp"` 出现在目录中，分类固定为 `uncategorized`、功能标签为空、`installable: false`，客户端展示上游信息而不提供安装动作。官方 Registry 的登记也不代表项目质量、安全性或供应方背书。

主分类是受控枚举：`ai-agents`、`automation`、`cad-3d`、`communication`、`creative-media`、`data-databases`、`developer-tools`、`knowledge-memory`、`productivity`、`system-tools`、`web-search` 和 `uncategorized`。功能标签从 `MCP_FUNCTION_TAGS` 受控集合中选择，每项最多三个。`catalog-dist/classification-suggestions.json` 根据名称和描述生成建议，仅供审核，绝不会覆盖已发布分类；确认后由维护者把值写入 `mcp-curation.json`。没有确定分类时保留 `uncategorized`。

MCP 元数据固定写入独立的 `mcpMetadata` 字段：`runtimeMode`、`platforms`、`permissionScopes`、`authentication`、`publisherType` 和 `installable`。信息不足时使用 `unknown`，尤其权限范围不会仅凭项目名称推断。CAD、Blender、FreeCAD、SolidWorks 等候选会由分类建议帮助定位，但在审核安装配置前不会显示为可直接安装。

## 自动同步和翻译

工作流 [`sync-marketplace.yml`](.github/workflows/sync-marketplace.yml) 每天 **00:00 UTC（北京时间 08:00）**运行，也支持在 GitHub Actions 页面手动触发；推送 `marketplace-v*` tag 也会触发同步。工作流先运行测试，再抓取 Skills 与四个 MCP 发现源、生成可安装清单和发现目录：可安装清单及能力文件推送到 `main`，发现索引与分类分片推送到 `catalog`。所有触发方式共用一个并发锁，避免同时写入两个分发分支。

要翻译新收录的英文说明，仓库 Actions Secrets 需要配置 `API_567_KEY`。`API_567_BASE_URL` 和 `API_567_MODEL` 可选，未配置时使用脚本默认值。自动工作流默认使用 6 个并发线程，每次同步最多处理 1,000 条新的 MCP 说明，避免首次导入海量候选时压满翻译服务；脚本在手动运行时可分别用 `API_567_TRANSLATION_WORKERS`（1–16）和 `API_567_MAX_TRANSLATIONS_PER_SYNC`（1–5,000）调整这两个限制。后续同步按原文缓存继续补齐。没有密钥或调用失败时，说明保留原文，之后仍可重试；已成功生成的中文翻译会按原文缓存，避免重复请求。

## 本地运行

需要 Python 3.11 或更新版本；同步还需要 Git 和网络访问。

```bash
python3 -m unittest discover -s tests -v
python3 sync_marketplace.py
```

第二条命令会下载三个 Skills 来源、读取四个 MCP 发现源和官方 MCP 参考仓库，并更新 `skills/`、`mcps/`、三份可安装清单以及被忽略的 `catalog-dist/` 生成目录。同步工作流额外把 `catalog-dist/` 发布到 `catalog` 分支；本地运行只生成文件，不会推送任何分支。配置 `API_567_KEY` 后，也会并发翻译新增或英文说明有变化的条目；未变化且已有成功译文的条目会复用缓存。只改脚本或来源配置不会改变 GitHub 上的自动任务，需先推送代码到 `main`。
