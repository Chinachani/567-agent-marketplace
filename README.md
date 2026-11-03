# 567 Agent 官方能力市场

本仓库是 567 Agent 能力市场的**目录与内容分发源**，不是桌面客户端，也不会在这里运行 MCP 服务。客户端读取市场清单来浏览能力，并安装有完整内容和配置的条目。

仓库维护两类能力：

- **Skills**：镜像 `SKILL.md` 及其必要的参考资料、脚本和模板。
- **MCP**：收集上游项目的发现信息；只有维护者审核过安装配置的 MCP 才提供安装。尚未审核的候选仍可用于发现和查看上游信息，但不会触发安装。

市场现在按用途分成两类清单：

- **可安装清单**：根目录 [`marketplace.json`](marketplace.json) 及兼容副本 [`.567agent/marketplace.json`](.567agent/marketplace.json)、[`.vetta/marketplace.json`](.vetta/marketplace.json)。这里仅发布可直接分发的 Skills、维护者审核过的 MCP 和其他能力；对应内容在 `skills/` 与 `mcps/`，客户端仍通过主分支归档安装。
- **MCP 发现目录**：同步器生成到 `catalog-dist/`，工作流将它发布到独立的 [`catalog` 分支](https://github.com/Chinachani/567-agent-marketplace/tree/catalog)。`index.json` 记录清单版本、分类计数和分片摘要；`shards/` 按分类和大小拆分尚未审核的 MCP 候选；`classification-suggestions.json` 供维护者审核。客户端只把候选作为只读信息展示，不会提供安装入口。

发现目录的更新不会提高 `marketplaceVersion`，也不会让客户端重下 Skills 归档；可安装能力变化才会更新主清单版本。当前维护者确认的 MCP 安装元数据记录在 [`mcp-curation.json`](mcp-curation.json) 中；新增上游候选须经审核后才会进入可安装范围。兼容客户端仍可使用旧主分支清单；新客户端优先读取 `catalog` 分支，缺少该分支时沿用已缓存目录。

## 当前运行状态

2026-11-03 核对：容量去重修复后的 [#53](https://github.com/Chinachani/567-agent-marketplace/actions/runs/40646474687) 至 [#58](https://github.com/Chinachani/567-agent-marketplace/actions/runs/41395088059) 连续六次同步发布成功。11 月 2 日的发布快照包含 **67,654 个 MCP 发现项**、142 个完整分片，完整内容约 **95.19 MiB**，搜索摘要约 **40.11 MiB**。这些是指定日期的快照，实时数量以 `catalog` 分支的 `index.json` 为准。

成功发布不等于所有外部服务都正常：#58 的 mcpHQ 源发生 DNS 故障，已保留原有 228 个条目；翻译接口也有超时。该快照中非空描述仅 26 条不含中文，日志里大量待补项目主要是名称，不能把名称与描述合计的失败数理解为同样数量的 MCP 没有中文介绍。品牌名、缩写和 `owner/repository` 标识允许保留原文。

当前完整目录接近 100 MiB 的客户端合同上限。去重只能缓解体积问题；长期扩容需要与 567 Agent 共同实现分页目录，见下文“容量与后续扩容”。

## 仓库结构

```text
main 分支
├── marketplace.json                    # 可安装清单
├── .567agent/marketplace.json           # 清单兼容副本
├── .vetta/marketplace.json              # 清单兼容副本
├── skills/                             # Skills 镜像及许可、来源文件
├── mcps/                               # 已审核 MCP 的安装配置
├── mcp-curation.json                    # 维护者确认的元数据
├── marketplace_sync.py                 # 上游列表、分类与内容处理
├── sync_marketplace.py                 # 采集、翻译、缓存与目录生成
├── marketplace_contract.py             # 发布字段校验
├── tests/                              # 采集、翻译与分发回归测试
└── .github/workflows/sync-marketplace.yml

catalog 分支（由 catalog-dist/ 发布）
├── index.json                          # 版本、分类计数、文件大小及 SHA-256
├── search/                             # 搜索摘要分片
├── shards/                             # MCP 完整详情分片
├── classification-suggestions.json     # 待维护者确认的分类建议
├── catalog-state.json.gz               # 下次采集的完整状态，含原文及译文
└── translation-cache.json.gz            # 翻译检查点，可跨运行恢复
```

`catalog-dist/`、`.marketplace-state.json.gz` 和 `.translation-cache.json.gz` 都是本地生成或恢复的文件，不提交到 `main`。

## Skills 来源

GitHub Actions 每天扫描以下仓库里的 `SKILL.md`，并镜像技能所需的参考文件、脚本和模板：

| 上游 | 扫描目录 | 说明 |
| --- | --- | --- |
| [microsoft/skills](https://github.com/microsoft/skills) | `.github/plugins/`、`.github/skills/` | Azure、Foundry、SDK 和开发工具 |
| [github/awesome-copilot](https://github.com/github/awesome-copilot) | `skills/`、`.github/skills/` | GitHub Copilot 社区技能 |
| [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) | `skills/` | 软件工程、测试、代码质量和性能 |

仓库原先保留的 74 个 `anbeime/skill` 历史镜像已隔离，不再出现在当前清单或分发目录中。该来源缺少可核实的再分发许可，部分内容还触发凭据与外联检查；原因记录在 `quarantined-skills.json`，不会自动重新采集。

收录要求上游仓库声明 MIT 许可；若单个技能声明 Apache-2.0，或在本地 `LICENSE.txt` 中给出 MIT/Apache-2.0 条款，也会保留对应许可文本和来源署名。单技能许可无法核实时跳过该技能，并只保留此前通过校验的合法镜像；仓库整体许可发生变化时中止同步，等待处理。新增来源前请先确认再分发条款。

同步器跳过隐藏目录、符号链接、超过 512 KiB 的 `SKILL.md`，以及单文件超过 2 MiB 或总资源超过 10 MiB 的技能。若已收录技能因限制被跳过，仅在此前版本通过合同与内容检查时保留；上游拉取失败、目录意外为空或仓库许可变化时，不发布部分结果。技能标识按来源仓库和上游路径复用，内容指纹涵盖说明及附属文件，内容变化会更新 `configVersion` 和市场版本。

分类依据技能名称和描述自动判断，类别包括系统、网络、开发、设计、文档、媒体、研究、数据、数据库、写作、商业、效率、安全和实用技能。分类是便于浏览的规则标签，并非对技能质量或安全性的认证。

## MCP

MCP 目录全量发现以下上游的条目：官方 [MCP Registry](https://registry.modelcontextprotocol.io/)（只取每个服务的 latest 版本）、[mcpHQ](https://landscape.mcphq.org/)、[punkpeye/awesome-mcp-servers](https://github.com/punkpeye/awesome-mcp-servers) 和 [TensorBlock/awesome-mcp-servers](https://github.com/TensorBlock/awesome-mcp-servers)。同步器按上游 GitHub 仓库或 Registry 名称去重，并保留来源链接。聚合仓库只作为发现索引；本仓库不因此重新分发其收录项目的代码。mcpHQ、TensorBlock、punkpeye 为可选来源：暂时不可用时保留此前收录的对应项目并继续同步其它来源；Registry 失败会中止发布以保护已有数据。

发现不等于可安装。只有在 `mcp-curation.json` 中经维护者确认分类、功能标签、运行方式、平台、权限范围、认证要求和安装配置的条目，才会有 `mcp.json` 并标记为可安装。其它候选仍以 `type: "mcp"` 出现在目录中，采用名称优先、描述其次的受控规则自动分类并添加最多三个标签，明确标注 `classificationSource: "automatic"`、`installable: false`，客户端展示上游信息而不提供安装动作。官方 Registry 的登记也不代表项目质量、安全性或供应方背书。

主分类是受控枚举：`ai-agents`、`automation`、`cad-3d`、`communication`、`creative-media`、`data-databases`、`developer-tools`、`knowledge-memory`、`productivity`、`system-tools`、`web-search` 和 `uncategorized`。功能标签从 `MCP_FUNCTION_TAGS` 受控集合中选择，每项最多三个。`catalog-dist/classification-suggestions.json` 根据名称和描述生成建议，供维护者审核纠正；维护者在 `mcp-curation.json` 中确认的分类和标签优先于自动规则。自动分类只用于检索，不表示通过安全审核；匹配不到时保留 `uncategorized`。

当前功能标签集合：`3d-modeling`、`ai`、`automation`、`browser`、`cad`、`cloud`、`communication`、`data-analysis`、`database`、`documents`、`email`、`filesystem`、`finance`、`image-generation`、`issue-tracking`、`memory`、`maps`、`search`、`security`、`developer-tools`、`video-generation`、`blender`、`freecad`、`solidworks`、`git`。客户端可组合分类和标签筛选，运行方式、权限与认证要求应分别展示。

MCP 元数据固定写入独立的 `mcpMetadata` 字段：`runtimeMode`、`platforms`、`permissionScopes`、`authentication`、`publisherType` 和 `installable`。另用 `classificationSource` 表明分类来自自动规则还是维护者。信息不足时使用 `unknown`，尤其权限范围不会仅凭项目名称推断。CAD、Blender、FreeCAD、SolidWorks 等候选会由分类建议帮助定位，但在审核安装配置前不会显示为可直接安装。

## 自动同步和翻译

工作流 [`sync-marketplace.yml`](.github/workflows/sync-marketplace.yml) 配置为每天 **00:00 UTC（北京时间 08:00）**触发，实际启动可能因 GitHub 调度延后；也支持在 GitHub Actions 页面手动触发。推送 `marketplace-v*` tag 会触发同步，普通 `main` 推送不会触发。工作流先运行测试，恢复上一版采集状态与翻译检查点，再抓取 Skills 与四个 MCP 发现源、生成可安装清单和发现目录：可安装清单及能力文件推送到 `main`，发现索引与分类分片推送到 `catalog`。所有触发方式共用一个并发锁，任务超时为 240 分钟。

翻译需配置 Actions Secret `API_567_KEY`。`API_567_BASE_URL` 和 `API_567_MODEL` 可选，未配置时分别使用 `https://api.567.wiki/v1` 和 `gemini-3.8-flash-high`。当前参数如下：

| 环境变量 | 默认值 / 工作流值 | 作用 |
| --- | --- | --- |
| `API_567_TRANSLATION_WORKERS` | 8，允许 1–16 | 并行翻译批数 |
| `API_567_TRANSLATION_BATCH_ITEMS` | 24，允许 1–32 | 每批条数；原文合计超过 8,000 字符时提前分批 |
| `API_567_MAX_TRANSLATIONS_PER_SYNC` | 200,000，允许 1–200,000 | 每次 `translate_texts` 调用的去重待译文本上限；不是所有阶段的累计 API 调用预算 |
| `API_567_TRANSLATION_CHECKPOINT_BATCHES` | 250 | 每完成这些批次向 `catalog` 提交一次翻译检查点 |
| `API_567_TRANSLATION_SINGLE_FALLBACK_ITEMS` | 500 | 每轮单条回退的条目预算 |
| `API_567_TRANSLATION_CIRCUIT_FAILURE_LIMIT` | 8 | 请求连续失败达到此值后停止新翻译请求，本轮剩余项目延后 |

MCP 先翻译描述，再翻译名称。新增或原文变化才进入待译队列；已有中文在原文一致时复用。批量响应必须逐项返回 `{id, translation}`，按 id 回填并拒绝缺失、重复或越界 id。描述必须含中文才计为成功；名称若只包含品牌或专有名词，模型可显式返回 `keepOriginal: true`，并且 `translation` 必须与输入完全相同，才接受保留原名。普通名称中的功能词仍要求翻译。名称的保留决定使用独立缓存键，不能当作描述译文复用；超时、失败或无效响应不会产生成功缓存。

每个 HTTP 请求最多尝试三次，单次网络超时为 45 秒，退避遵从 `Retry-After`。无中文响应和格式错误受回退预算约束；失败项目保留原文并在后续运行重试。翻译每完成 25 批输出进度。缓存按原文 SHA-256 索引，最多 100,000 项且未压缩 JSON 不超过 16 MiB，超限时淘汰最久未使用项；检查点采用固定 gzip 时间戳，未变化的内容不会反复提交。运行被取消后，已提交检查点可恢复，检查点之后的结果仍可能需要重做。

`Translation incomplete` 表示存在未完成翻译，不等于目录发布失败；最终结果应检查生成、推送 `main`、发布 `catalog` 三个步骤。测试阶段会故意打印超时、无效缓存和熔断日志，判断生产故障时应查看 `Run sync and generate catalog` 步骤。

## 本地运行

需要 Python 3.11 或更新版本；同步还需要 Git 和网络访问。

```bash
python3 -m unittest discover -s tests -v
python3 sync_marketplace.py
```

第二条命令会下载三个 Skills 来源、读取四个 MCP 发现源和官方 MCP 参考仓库，并更新 `skills/`、`mcps/`、三份可安装清单以及被忽略的 `catalog-dist/` 生成目录。最终清单和完整目录只在工作流中推送；但本地长时间翻译达到检查点间隔时，检查点函数也会尝试推送缓存到 `catalog` 分支。只需验证生成时可不设置 `API_567_KEY`，此时使用原文。需要复用线上数据的本地运行，应先按工作流恢复 `catalog-state.json.gz` 到 `.marketplace-state.json.gz`，并恢复 `translation-cache.json.gz` 到 `.translation-cache.json.gz`。代码或来源配置需先推送到 `main`，再手动触发或等待定时任务生效。

客户端应先固定 `catalog` 分支的 commit SHA，再从该 SHA 下载索引及分片；不要混用可变分支 URL。分片包含完整摘要和字节长度，可独立缓存、校验及重试。可安装清单与发现目录分别加载，单片失败不应隐藏已成功加载的条目。可选图标字段 `icon` 默认空字符串；所有发现项保持不可一键安装，安全性未知。

## 搜索索引与详情按需加载

`catalog/index.json` 保留旧 `shards`，同时提供 `searchShards`。搜索分片只包含可搜索摘要、受控分类/标签和 `detailShard` 定位，不包含执行配置；客户端首次浏览下载搜索分片，打开详情时按固定 Git commit 下载对应完整分片。两类分片均校验 SHA-256、字节数、条目数和分类。旧客户端继续读取 `shards`。

安装主清单在发布前经过出口校验；非法版本等条目跳过，旧镜像只有合同有效且通过内容检查才可保留。客户端带 Token 读取 GitHub Contents 时必须使用 `application/vnd.github.raw+json`，不能依赖大于 1MB 文件的 base64 JSON 响应。

单个分片最多 500 条、1 MiB。原始完整目录超过 100 MiB 时，生成器会从完整分片的 `detail.i18n.zh` 中省略与顶层 `name`、`description` 或 `tags` 完全相同的字段；英文及不同的中文内容保留。搜索摘要也使用顶层字段回退，省略值不能变成空字符串覆盖中文说明。Registry 更新时间仅保存在采集状态中，不计入发布摘要与内容版本，避免只有时间戳变化时重复下载。

## 容量与后续扩容

**当前已实现的 schemaVersion 1 合同**仍为最多 100,000 条、250 个完整分片、100 MiB 完整内容；超过 80% 输出告警，越界则中止暂存发布，保留上一版。客户端也校验总容量，因此不能只在生成器中调大常量；Git LFS 或 gzip 文件替换也不能被当前 JSON 读取协议直接消费。

**后续需要与 567 Agent 联动的方案，尚未实现**：增加版本化的分页索引，以分类和页为单位发布。页索引携带版本、条目计数、文件大小和 SHA-256；搜索与详情按页下载，单请求维持大小上限，用分页和本地缓存预算控制开销，不再以“整个市场最多 100 MiB”为边界。旧协议在迁移期保持兼容，不能静默删除超限条目或让旧客户端把分页子集当作全量。

567 Agent 需要配合：识别新索引版本；按页查询、加载更多并显示加载状态；分类和标签筛选覆盖尚未下载的页；详情与搜索固定到同一个 commit；校验每页摘要并允许失败页单独重试；限制本地缓存容量。这个协议升级完成前，容量增长仍可能触发保护性中止，去重修复不代表取消了容量上限。

## 隔离与来源追溯

`quarantined-skills.json` 只记录 slug、来源和原因，绝不保存匹配到的凭据。旧 `anbeime/skill` 镜像缺少可核实的再分发许可，已从当前清单和资源目录移除；恢复需要先确认许可，再审核内容。所有自动镜像经过凭据字面量、远程 heartbeat 指令、公开裸 IP 明文端点等检查。检查是已知风险拦截，不代表第三方技能安全，也不代替人工审核。

上游技能与参考 MCP 每次采集先解析 commit，然后仅取该 SHA；可在来源配置的 `commit` 字段固定经审核的版本。技能来源记录 `upstreamCommit`。默认仍会自动跟进最新版本，固定单次采集版本保证可追溯性，不保证上游未经投毒。

本次只清理当前分发内容，**Git 历史中的大文件和历史凭据仍存在**。删除文件不会吊销 Token；凭据持有人必须吊销或轮换。历史瘦身需要协调使用者并重写分支，不由日常同步工作流自动执行。
