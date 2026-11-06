# 567 Agent 官方能力市场

本仓库是 567 Agent 能力市场的**目录与内容分发源**，不是桌面客户端，也不会在这里运行 MCP 服务。客户端读取市场清单来浏览能力，并安装有完整内容和配置的条目。

仓库维护两类能力：

- **Skills**：镜像 `SKILL.md` 及其必要的参考资料、脚本和模板。
- **MCP**：收集上游项目的发现信息；只有维护者审核过安装配置的 MCP 才提供安装。尚未审核的候选仍可用于发现和查看上游信息，但不会触发安装。

市场现在按用途分成两类清单：

- **可安装清单**：根目录 [`marketplace.json`](marketplace.json) 及兼容副本 [`.567agent/marketplace.json`](.567agent/marketplace.json)、[`.vetta/marketplace.json`](.vetta/marketplace.json)。这里仅发布可直接分发的 Skills、维护者审核过的 MCP 和其他能力；对应内容在 `skills/` 与 `mcps/`，客户端仍通过主分支归档安装。
- **MCP 发现目录**：同步器生成到 `catalog-dist/`，工作流将它发布到独立的 [`catalog` 分支](https://github.com/Chinachani/567-agent-marketplace/tree/catalog)。新版入口 `v2/index.json` 按分类链接到分页索引和搜索/详情分片；旧入口 `index.json` 保留兼容。`classification-suggestions.json` 供维护者审核。客户端只把候选作为只读信息展示，不会提供安装入口。

发现目录的更新不会提高 `marketplaceVersion`，也不会让客户端重下 Skills 归档；可安装能力变化才会更新主清单版本。当前维护者确认的 MCP 安装元数据记录在 [`mcp-curation.json`](mcp-curation.json) 中；新增上游候选须经审核后才会进入可安装范围。兼容客户端仍可使用旧主分支清单；新客户端优先读取 `catalog` 分支，缺少该分支时沿用已缓存目录。

## 当前运行状态

2026-11-06 核对：v2 已从 [#60](https://github.com/Chinachani/567-agent-marketplace/actions/runs/41587410864) 开始成功发布；11 月 4–6 日 #62、#63、[#64](https://github.com/Chinachani/567-agent-marketplace/actions/runs/42172462996) 连续成功。11 月 6 日发布版本 `2026.11.06.1` 包含 **70,347 个 MCP 发现项**、13 个目录页、147 组搜索/详情分片，完整内容约 **98.94 MiB**，v2 搜索摘要约 **53.85 MiB**。旧入口状态为 `current`。这些是指定日期的快照，实时数量以 `catalog` 分支的 `v2/index.json` 为准，旧入口可能冻结。

成功发布不等于所有外部服务都正常：#64 的 mcpHQ 源仍有 DNS 故障，已保留原有 228 个条目；翻译接口连续返回 HTTP 503，熔断后本轮 708 个 MCP 描述文本、515 个名称文本及 1 个 Skill 描述延后处理，后续同步会重试。这里统计的是待译文本，不能相加作为 MCP 数量。已有中文继续保留；品牌名、缩写和 `owner/repository` 标识允许保留原文。

11 月 3 日 [#61](https://github.com/Chinachani/567-agent-marketplace/actions/runs/41588887952) 生成成功但推送被拒绝：任务排队期间 #60 已更新 `main`，默认 checkout 仍使用触发事件的旧提交。本工作流现已显式在获得并发锁后读取最新 `main`，避免串行排队任务仍基于旧提交。运行途中如果有人另行推送，普通 Git 推送保护仍会阻止覆盖远端，需基于最新代码重新运行。

能力库已实现 **schemaVersion 2 分页目录生成和双版本发布**，不再用 100 MiB 限制新版目录总量。567 Agent 客户端仍需接入新协议，工程交接说明和验收清单见 [`docs/mcp-catalog-v2.md`](docs/mcp-catalog-v2.md)。使用上述快照本地验证得到 13 个目录页、142 组搜索/详情分片；v2 搜索摘要因包含完整筛选元数据约为 51.90 MiB，客户端按需读取。

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
├── translation_fallback.py             # Index-Translate 免费备用接口适配与限速
├── marketplace_contract.py             # 发布字段校验
├── discovery_catalog.py                # v2 分页目录与旧快照校验
├── docs/mcp-catalog-v2.md               # Agent 客户端接入合同及验收项
├── fixtures/mcp-catalog-v2/             # 可独立验证的客户端测试样例
├── tests/                              # 采集、翻译与分发回归测试
└── .github/workflows/sync-marketplace.yml

catalog 分支（由 catalog-dist/ 发布）
├── v2/
│   ├── index.json                      # 全量分类计数、首个页索引及 v1 状态
│   ├── pages/<category>/               # 每页最多 64 组分片描述符，含下一页摘要
│   ├── search/                         # 按需加载的摘要及完整筛选元数据
│   └── shards/                         # 打开详情时读取
├── index.json                          # v1 兼容索引；超限时保留完整旧快照
├── search/                             # v1 搜索摘要分片
├── shards/                             # v1 完整详情分片
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

工作流 [`sync-marketplace.yml`](.github/workflows/sync-marketplace.yml) 配置为每天 **00:00 UTC（北京时间 08:00）**触发，实际启动可能因 GitHub 调度延后；也支持在 GitHub Actions 页面手动触发。推送 `marketplace-v*` tag 会触发同步，普通 `main` 推送不会触发。所有触发方式共用一个并发锁，取得锁后 checkout 最新 `main`；tag 和手动所选 ref 作为触发来源，实际采集代码及配置以最新 `main` 为准。工作流先运行测试，恢复上一版采集状态与翻译检查点，再抓取 Skills 与四个 MCP 发现源、生成可安装清单和发现目录：可安装清单及能力文件推送到 `main`，发现索引与分类分片推送到 `catalog`。任务超时为 240 分钟。

主翻译接口使用 Actions Secret `API_567_KEY`。`API_567_BASE_URL` 和 `API_567_MODEL` 可选，未配置时分别使用 `https://api.567.wiki/v1` 和 `gemini-3.8-flash-high`。工作流默认启用哔哩哔哩 **Index-Translate 免费公开接口作为备用**，无需新增 Secret；未配置主 Key 时也可以单独使用备用接口。当前参数如下：

| 环境变量 | 默认值 / 工作流值 | 作用 |
| --- | --- | --- |
| `API_567_TRANSLATION_WORKERS` | 8，允许 1–16 | 并行翻译批数 |
| `API_567_TRANSLATION_BATCH_ITEMS` | 24，允许 1–32 | 每批条数；原文合计超过 8,000 字符时提前分批 |
| `API_567_MAX_TRANSLATIONS_PER_SYNC` | 200,000，允许 1–200,000 | 每次 `translate_texts` 调用的去重待译文本上限；不是所有阶段的累计 API 调用预算 |
| `API_567_TRANSLATION_CHECKPOINT_BATCHES` | 250 | 每完成这些批次向 `catalog` 提交一次翻译检查点 |
| `API_567_TRANSLATION_SINGLE_FALLBACK_ITEMS` | 500 | 每轮单条回退的条目预算 |
| `API_567_TRANSLATION_CIRCUIT_FAILURE_LIMIT` | 8 | 每个接口独立统计连续失败；主接口熔断后仍可使用备用接口 |
| `API_567_INDEX_TRANSLATE_ENABLED` | 本地默认 `false`，Actions 默认 `true` | 启用免费备用接口；可在 Repository Variables 中设为 `false` 关闭 |
| `API_567_INDEX_TRANSLATE_MAX_REQUESTS` | 5,000，允许 0–5,000 | 备用接口每轮 HTTP 尝试总预算，含重试；可用同名 Repository Variable 调低 |

备用接口按官方 [`call_api.py`](https://github.com/bilibili/Index-Translate/blob/main/inference/llm/call_api.py) 的协议接入：`https://index-translate.bilibili.com/v1/chat/completions`，模型 `Index-Translate-35B-A3B`，`temperature: 0`，`chat_template_kwargs.enable_thinking: false`。只发送公开能力名称与描述，不发送主接口 Key。这是公开服务，不保证可用性或固定配额；不通过增加并发规避限流。

调用顺序为主接口 → Index-Translate。主接口重试耗尽、认证/HTTP 错误、超时、无效 HTTP 响应或熔断时，本次请求可切换备用。主接口熔断在本轮保持，后续批次直接使用备用，下轮重新尝试主接口。备用接口独立单并发、**每批最多 4 条**，相邻请求启动至少间隔 1 秒，遵从 `Retry-After`（最长等待 60 秒），每个小批最多三次尝试、单次网络超时 45 秒。大批在备用侧拆成小批，用 JSON 对象 key 保留原始 id，再还原统一的 `{id, translation}` 响应；重复、遗漏或被修改的 key 会拒收。备用连续失败达到阈值、遇到不可重试 HTTP 错误或耗尽预算时也会停止请求；原文保留并延后重试。批量 JSON 的 id/中文校验仍由同一条管线执行，语义或格式校验失败沿用原有受预算限制的单条回退，不把接口成功响应等同于翻译成功。

仓库的 [Actions Variables 设置](https://github.com/Chinachani/567-agent-marketplace/settings/variables/actions) 可设置上述两个备用参数；没有设置时工作流即使用默认值。本地需要显式 `API_567_INDEX_TRANSLATE_ENABLED=true python3 sync_marketplace.py` 才开启公开接口。新增备用不会清空缓存或重翻全部已有中文。

MCP 先翻译描述，再翻译名称。新增或原文变化才进入待译队列；已有中文在原文一致时复用。批量响应必须逐项返回 `{id, translation}`，按 id 回填并拒绝缺失、重复或越界 id。描述必须含中文才计为成功；名称若只包含品牌或专有名词，模型可显式返回 `keepOriginal: true`，并且 `translation` 必须与输入完全相同，才接受保留原名。普通名称中的功能词仍要求翻译。名称的保留决定使用独立缓存键，不能当作描述译文复用；超时、失败或无效响应不会产生成功缓存。

每个接口对同一 HTTP 请求最多尝试三次：例如主接口 24 条批次失败后，备用拆为 6 个小批，正常只需 6 次备用请求；含所有重试最多为主接口 3 次加备用 18 次，熔断和备用总预算可提前终止。无中文响应和批量格式错误受单条回退预算约束；失败项目保留原文并在后续运行重试。翻译每完成 25 批输出进度。缓存按原文 SHA-256 索引，最多 100,000 项且未压缩 JSON 不超过 16 MiB，超限时淘汰最久未使用项；检查点采用固定 gzip 时间戳，未变化的内容不会反复提交。运行被取消后，已提交检查点可恢复，检查点之后的结果仍可能需要重做。

`Translation incomplete` 表示存在未完成翻译，不等于目录发布失败；最终结果应检查生成、推送 `main`、发布 `catalog` 三个步骤。测试阶段会故意打印超时、无效缓存和熔断日志，判断生产故障时应查看 `Run sync and generate catalog` 步骤。

## 本地运行

需要 Python 3.11 或更新版本；同步还需要 Git 和网络访问。

```bash
python3 -m unittest discover -s tests -v
python3 sync_marketplace.py
```

第二条命令会下载三个 Skills 来源、读取四个 MCP 发现源和官方 MCP 参考仓库，并更新 `skills/`、`mcps/`、三份可安装清单以及被忽略的 `catalog-dist/` 生成目录。最终清单和完整目录只在工作流中推送；但本地长时间翻译达到检查点间隔时，检查点函数也会尝试推送缓存到 `catalog` 分支。只需验证生成时可不设置 `API_567_KEY`，并保持 `API_567_INDEX_TRANSLATE_ENABLED=false`，此时使用原文。需要复用线上数据的本地运行，应先按工作流恢复 `catalog-state.json.gz` 到 `.marketplace-state.json.gz`，并恢复 `translation-cache.json.gz` 到 `.translation-cache.json.gz`。代码或来源配置需先推送到 `main`，再手动触发或等待定时任务生效。

客户端应先固定 `catalog` 分支的 commit SHA，再从该 SHA 下载索引及分片；不要混用可变分支 URL。分片包含完整摘要和字节长度，可独立缓存、校验及重试。可安装清单与发现目录分别加载，单片失败不应隐藏已成功加载的条目。可选图标字段 `icon` 默认空字符串；所有发现项保持不可一键安装，安全性未知。

## 搜索索引与详情按需加载

新版从 `catalog` 分支的 `v2/index.json` 读取分类计数及首个页索引，沿 `next` 获取后续页。每个页内提供搜索/详情的配对描述符及 facets（分类范围或分片范围内的筛选值计数）。搜索摘要包含受控分类/标签、完整 `mcpMetadata` 和 `detailShard` 定位，不含执行配置；打开详情时才读取完整分片。所有文件固定到同一 Git commit，并校验 SHA-256、字节数、版本、条目数和分类。旧 `index.json`、`shards`、`searchShards` 协议继续保留。

关键词搜索需要渐进扫描对应分类的搜索分片；本仓库不提供远端搜索 API。尚未扫描完或存在失败分片时，应显示部分结果状态。facets 可排除不可能命中的分片，多标签交集仍需检查记录本身。

安装主清单在发布前经过出口校验；非法版本等条目跳过，旧镜像只有合同有效且通过内容检查才可保留。客户端带 Token 读取 GitHub Contents 时必须使用 `application/vnd.github.raw+json`，不能依赖大于 1MB 文件的 base64 JSON 响应。

单个分片最多 500 条、1 MiB；v2 根索引和页索引最多 256 KiB，每页最多 64 组分片。v2 总是省略 `detail.i18n.zh` 中与顶层 `name`、`description` 或 `tags` 完全相同的字段，v1 在容量紧张时才进行这项去重；英文及不同的中文内容保留。搜索摘要也使用顶层字段回退，省略值不能变成空字符串覆盖中文说明。Registry 更新时间仅保存在采集状态中，不计入发布摘要与内容版本，避免只有时间戳变化时重复下载。

## 容量与客户端迁移

**schemaVersion 2 已实现生成端**：全量记录按分类、页和分片发布，搜索和详情均按字节数及条数拆分。取消旧的总记录数、总分片数和总字节限制，用单文件边界及客户端加载/缓存预算控制资源。单条非法或超大记录仍会拒绝发布；上游和翻译服务故障、Git 托管空间及历史增长需分别处理。

**schemaVersion 1 兼容合同**仍为最多 100,000 条、250 个完整分片、搜索/详情各不超过 100 MiB。容量内继续生成最新 v1；超限后逐片校验并保留上一份完整旧快照，同时继续发布全量 v2。v2 根索引的 `legacy.status` 明示 `current`、`frozen` 或 `unavailable`。没有有效旧快照时只发布 v2，不制造空 v1，也不截断目录伪装全量。采集状态和翻译缓存始终保持最新。

567 Agent 需要配合：识别 v2；按页查询和加载更多；分类、标签及独立元数据筛选覆盖尚未下载的页；展示渐进搜索状态；详情与搜索固定到同一个 commit；校验每页摘要并允许失败页单独重试；限制本地缓存容量。详细字段、路径、回退策略和测试样例见[客户端接入文档](docs/mcp-catalog-v2.md)。客户端升级前仍使用 v1；如果 v1 已冻结，只有升级后才能看到新增发现项。

## 隔离与来源追溯

`quarantined-skills.json` 只记录 slug、来源和原因，绝不保存匹配到的凭据。旧 `anbeime/skill` 镜像缺少可核实的再分发许可，已从当前清单和资源目录移除；恢复需要先确认许可，再审核内容。所有自动镜像经过凭据字面量、远程 heartbeat 指令、公开裸 IP 明文端点等检查。检查是已知风险拦截，不代表第三方技能安全，也不代替人工审核。

上游技能与参考 MCP 每次采集先解析 commit，然后仅取该 SHA；可在来源配置的 `commit` 字段固定经审核的版本。技能来源记录 `upstreamCommit`。默认仍会自动跟进最新版本，固定单次采集版本保证可追溯性，不保证上游未经投毒。

本次只清理当前分发内容，**Git 历史中的大文件和历史凭据仍存在**。删除文件不会吊销 Token；凭据持有人必须吊销或轮换。历史瘦身需要协调使用者并重写分支，不由日常同步工作流自动执行。
