# 567 Agent 接入 MCP 分页目录 v2

能力库负责采集、翻译、分类、生成和发布；567 Agent 负责读取分页协议、渐进搜索、筛选、缓存和 UI。能力库已实现本文的生成端及回归测试，客户端接入需在 Agent 仓库完成。现有 Skills 与已审核 MCP 的 `main/marketplace.json` 安装协议不变。

## 给 Agent 工程师的任务

1. 新增 v2 解析器和分页加载器，优先读取 `catalog` 分支的 `v2/index.json`；整个加载过程固定同一个 Git commit SHA。
2. 按分类读取页索引，按需加载搜索分片；打开详情才下载对应完整分片。不要启动时下载全部详情，也不要把旧版 100 MiB / 250 分片 / 100,000 条总上限应用到 v2。
3. 支持分类、功能标签、运行方式、平台、权限范围、认证要求、发布者类型筛选。先用 facets 排除不可能匹配的分片，再对分片里的实际记录筛选。
4. 搜索和筛选必须能覆盖未加载的分片，显示进度、部分结果和失败页；用户取消或更换条件后中止旧任务，不能显示“全部结果”直到相应范围扫描完成。
5. 校验文件路径、SHA-256、字节数、版本、分类、计数和详情定位；单片失败允许重试；用有限并发和 LRU 控制下载与本地缓存。
6. 保留 v1 兼容及最后一次有效缓存，所有发现项继续只读，`installable: false` 不得触发安装。

现有代码入口可从 `apps/desktop/src/main/abilities/open-marketplace/mcp-discovery-catalog.ts`、`mcp-discovery-feed.ts` 查起，再接通能力页的数据层、筛选和加载状态。请新增 v2 解析路径，保留现有 v1 解析器。

可复制的测试数据在 [`fixtures/mcp-catalog-v2/`](../fixtures/mcp-catalog-v2/)：三条记录、两个分类，包含完整索引、页、搜索和详情文件，摘要均为实际值。`input.json` 是生成输入，不是客户端下载入口。客户端可直接将 `v2/` 作为离线 HTTP fixture。Python 端会验证其可重复生成；跨多页、容量溢出和损坏快照案例在 [`tests/test_discovery_catalog.py`](../tests/test_discovery_catalog.py)。

## 地址与版本固定

仓库：`Chinachani/567-agent-marketplace`，产物分支：`catalog`。

先将 `refs/heads/catalog` 解析为完整 commit SHA，之后使用：

```text
https://raw.githubusercontent.com/Chinachani/567-agent-marketplace/<commit>/v2/index.json
https://raw.githubusercontent.com/Chinachani/567-agent-marketplace/<commit>/<descriptor.path>
```

开发时可查看[分支入口](https://raw.githubusercontent.com/Chinachani/567-agent-marketplace/catalog/v2/index.json)，但运行时不要从可变分支 URL 混合取文件。第一次 v2 工作流发布前该地址可能返回 404。使用 GitHub Contents API 时必须设置 `Accept: application/vnd.github.raw+json`，不依赖大文件的 base64 包装响应。

`schemaVersion: 2` 标识协议；`catalogVersion` 标识发现记录的内容版本；`marketplaceVersion` 仅关联可安装清单版本。缓存键至少包含仓库、固定 commit、路径和文件摘要，不要仅按 `catalogVersion` 缓存：协议或兼容状态变化时，内容版本可以不变。

## 文件合同

所有大小和 SHA-256 都针对原始 UTF-8 JSON 文件字节。不能对重新序列化后的 JSON 求摘要。Python 生成器使用紧凑 JSON、排序键，文件不带换行。

| 文件 | 上限 | 内容 |
| --- | --- | --- |
| `v2/index.json` | 256 KiB | 分类统计、每类首个页索引、兼容状态 |
| `v2/pages/<category>/<number>.json` | 256 KiB、64 个 entries | 搜索/详情配对描述符、下一页描述符 |
| `v2/search/mcp-<category>-<number>.json` | 1 MiB、500 条 | 展示摘要、筛选元数据、详情定位 |
| `v2/shards/mcp-<category>-<number>.json` | 1 MiB、500 条 | 完整发现记录 |

编号从零开始，至少六位十进制数字。各分类内记录按 `slug` 排序；编号属于本次快照，不是永久 ID。稳定身份是 `slug`。过大的单条记录仍会拒绝发布；v2 取消的是旧协议的**总容量上限**，不是每个文件的边界。

通用描述符：

```ts
type FileRef = { path: string; sizeBytes: number; sha256: string };
type Facets = {
  tags: Record<string, number>;
  runtimeMode: Record<string, number>;
  platforms: Record<string, number>;
  permissionScopes: Record<string, number>;
  authentication: Record<string, number>;
  publisherType: Record<string, number>;
};
```

每个 facet 值是包含该值的记录数；多选字段在同一记录内去重。标签总数之和可以超过记录数，空标签不计入 `tags`。信息不足时元数据使用 `unknown`，不推断为“无权限”或“无需认证”。

根索引结构：

```ts
type CatalogIndexV2 = {
  schemaVersion: 2;
  catalogVersion: string;
  marketplaceVersion: string;
  recordCount: number;
  categories: Record<Category, {
    recordCount: number;
    facets: Facets;
    pageCount: number;
    shardCount: number;
    firstPage: FileRef;
  }>;
  totalBytes: { search: number; detail: number; pages: number };
  limits: { dataItems: 500; dataBytes: 1048576; pageEntries: 64; indexBytes: 262144 };
  legacy:
    | { status: "current"; path: "index.json"; catalogVersion: string; recordCount: number }
    | { status: "frozen"; reason: "capacity-exceeded"; path: "index.json"; catalogVersion: string; recordCount: number }
    | { status: "unavailable"; reason: string };
};
```

`categories` 只包含非空分类（TypeScript 实现应使用 partial record），缺席分类计数为零。全空目录是 `recordCount: 0`、`categories: {}`。`totalBytes` 是所有对应文件的字节和，不含根索引，用于展示和统计，不能据此一次分配内存或启动全部下载。客户端应自行实施上述文件硬上限，不允许远端 `limits` 放宽本地校验。

页索引结构：

```ts
type CatalogPageV2 = {
  schemaVersion: 2;
  catalogVersion: string;
  category: Category;
  entries: Array<{
    count: number;
    facets: Facets;
    search: FileRef;
    detail: FileRef;
  }>;
  next: FileRef | null;
};
```

从 `firstPage` 开始沿 `next` 读取，末页是 `null`；`next` 携带下一页摘要，因此整条链从根索引可逐跳校验。每个 entry 对应一对搜索/详情分片，两者 count、slug 集合及顺序相同。页描述符通常很小，读取页不会自动下载里面的所有分片。

搜索和完整分片都采用同一个外壳：

```ts
{
  schemaVersion: 2,
  catalogVersion: string,
  category: Category,
  abilities: Ability[]
}
```

搜索记录保留 `type: "mcp"`、`slug`、`name`、`description`、`version`、`configVersion`、`category`、`tags`、`mcpMetadata`，可选 `categoryI18n`、`classificationSource`，以及 `detailShard`。`license`、`author`、`icon` 在摘要中为空字符串。`detail.i18n` 保留英文/中文名称和描述差异；描述最多 320 个 Unicode 码点。搜索记录不含 `source`、安装配置或执行命令。

`detailShard` 必须等于所属 entry 的 `detail.path`。打开详情时从已校验 entry 取得描述符，下载后按 `slug` 查找，核对版本和分类。不能把上游给出的任意 URL 当成分片地址。

完整记录沿用现有发现项字段，包含 `source`、原文/译文、来源链接和独立 `mcpMetadata`。`detail.i18n.zh` 与顶层相同的 `name`、`description`、`tags` 会被省略，客户端逐字段使用 `localized[field] ?? item[field]` 回退；不要将缺失字段变成空字符串。`registryUpdatedAt` 只在采集状态保存，不影响发布内容。

## 分类、标签和其他筛选字段

`Category` 受控枚举：`ai-agents`、`automation`、`cad-3d`、`communication`、`creative-media`、`data-databases`、`developer-tools`、`knowledge-memory`、`productivity`、`system-tools`、`web-search`、`uncategorized`。

功能标签每条最多三个，当前全集：`3d-modeling`、`ai`、`automation`、`browser`、`cad`、`cloud`、`communication`、`data-analysis`、`database`、`documents`、`email`、`filesystem`、`finance`、`image-generation`、`issue-tracking`、`memory`、`maps`、`search`、`security`、`developer-tools`、`video-generation`、`blender`、`freecad`、`solidworks`、`git`。

| 元数据字段 | 形状与典型值 | UI 含义 |
| --- | --- | --- |
| `runtimeMode` | 字符串，`stdio` / `streamable-http` / `sse` / `unknown` | 运行/连接方式 |
| `platforms` | 字符串数组，如 `windows` / `macos` / `linux` / `unknown` | 支持平台 |
| `permissionScopes` | 字符串数组，如 `filesystem` / `network` / `unknown` | 权限范围 |
| `authentication` | 字符串，`none` / `api-key` / `oauth` / `credentials` / `unknown` | 认证要求 |
| `publisherType` | 字符串，通常为 `unknown`，由维护者补充 | 发布者类型 |
| `installable` | 固定 `false` | 只读候选，不能安装 |

这些字段独立于功能标签。具体值从 facets 建立选项，可为认识的值配置中文标签；新值显示为原值，保留 `unknown` 选项，不因为本地枚举过旧而丢弃整个目录。每个数组最多 32 项，字符串值非空且最长 128 字符。`classificationSource: "automatic" | "maintainer"` 表示分类来源，并非安全认证。维护者确认仍通过能力库 `mcp-curation.json` 完成。

## 加载、搜索、失败处理

建议流程：根索引 → 选中分类首个页索引 → 加载首个匹配的搜索分片 → 渲染 → 按滚动/搜索需要继续加载。建议初始下载并发 4、磁盘缓存 200 MiB，使用 LRU；这是客户端可调整的资源预算，不是目录总大小校验。返回第一页不应依赖全部分类下载完毕。

根分类 facets 和 entry facets 可以排除某个标签、运行方式等计数为零的范围。多标签 AND 查询不能仅靠单标签计数证明存在交集；多个筛选字段也一样，最终都要检查实际记录。分类计数是全量统计；组合筛选结果数只有遍历匹配范围后才确定。

**本协议没有远端全文搜索 API。** 关键词搜索针对名称、摘要中的描述及其英中文本，需要渐进扫描目标分类的搜索分片；只查当前已加载页不能宣称全量搜索。320 码点以外的完整描述不在摘要搜索合同中。UI 显示“已找到 N 条，仍在搜索/部分分片失败”，扫描完成才显示最终数量或“无结果”。取消旧搜索后，迟到响应不能混入新条件的结果。已下载数据可复用，完整详情无需参与普通检索。

必须校验：

- 根和每类计数为非负安全整数，非空类的 pageCount/shardCount 为正整数；分类计数之和等于根计数。按实际读取逐步核对页数、分片数和记录数，完成扫描时校验总和。
- 路径仅允许对应 `v2/pages/`、`v2/search/`、`v2/shards/` 的本分类目录与数字编号，禁止绝对路径、`..`、反斜线、URL、query 和 fragment。请求固定仓库及 commit，不跟随任意外部地址。
- 每个响应读取时即限制实际字节数，再校验 `sizeBytes`、64 位十六进制 SHA-256，最后解析 JSON。不要只信 `Content-Length`。
- 每层 `schemaVersion`、`catalogVersion`、`category` 对齐；entries 不超过 64；abilities 不超过 500 且数量等于 entry.count；发现项必须 `type: "mcp"`、`installable: false`。
- 页路径、分片路径、slug 不重复；记录已访问页，遇环终止；不得超过声明页数；读到 `null` 时核对已读页数。无须一次下载全部文件才能展示已验证结果。
- 单个失败分片不清空其它成功结果，保留错误和重试入口；摘要/版本不符的文件不入有效缓存。不可用或未知协议时保留此前有效缓存并显示状态。

仅当 v2 **404（尚未部署）** 时优先尝试同一固定 commit 的 v1。v2 超时或校验失败不应静默当成“没有目录”；使用有效缓存或明确提示异常。必要时可让用户主动切换兼容目录，但要标明它可能较旧。

## v1 迁移行为

能力库同时生成 v1 和 v2。v1 继续遵守最多 100,000 条、250 分片、每类分片文件总计 100 MiB 的合同，v2 不继承这些总量限制。

- `legacy.status: current`：本次 v1 仍在容量内，与 v2 覆盖相同记录。
- `legacy.status: frozen`：本次超出 v1 容量，能力库从固定旧 commit 读取并逐片校验上一份完整 v1，原字节保留旧 `index.json`、`search/`、`shards/`；v2 发布本次所有记录。旧客户端仍能读旧快照，新客户端以 v2 为准。
- `legacy.status: unavailable`：超限且无可验证的旧快照，仅发布完整 v2。不会制造空目录或截断后伪装全量的 v1。旧客户端应保留自己的有效缓存。

`catalog-state.json.gz` 和翻译缓存始终来自最新采集，不跟随冻结的 v1 回滚。兼容快照冻结可以持续多轮，但客户端必须升级到 v2 才能看到新增内容。Git 托管空间、历史增长、上游故障和翻译接口限额仍是独立运维边界，本协议不承诺消除所有同步失败。

## 客户端验收清单

- [ ] fixture 两类三条都能显示；中文省略字段正确回退；搜索→详情身份一致。
- [ ] 两页以上链式分页正常，“加载更多”不重复、不丢条；首次展示不下载全量详情。
- [ ] 目标记录只在尚未加载的页时，分类/标签/关键词查询最终仍可找到；中途有部分结果标识。
- [ ] 总量超过 100 MiB、100,000 条或 250 分片时，v2 分页仍可浏览；单文件上限继续生效。
- [ ] 分片 SHA/size 错误、缺页、循环 next、重复 slug、分类/版本混用、路径越界被拒绝；失败页可独立重试。
- [ ] 新发布发生在浏览中时继续使用固定 commit，手动刷新才切换版本；缓存按预算淘汰。
- [ ] v2 404 可回落 v1；frozen 显示旧快照版本；unknown schema/校验失败不会伪装成零结果。
- [ ] 所有候选只读，不出现一键安装；Skills 和已审核 MCP 的安装流程不受影响。
