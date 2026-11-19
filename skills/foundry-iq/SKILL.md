---
name: "foundry-iq"
description: "适用于 Azure AI Search、Foundry IQ、基于文档的智能体以及基于文档构建的知识图谱。适用场景：搜索、索引、查询、访问/连接失败、数据摄入/时效性失败、检索质量、事实依据、指导或 REST 有效负载；实体知识图谱（实体、关系、多跳问题）、主题图谱（整个语料库的主题）、基于图谱的事实依据段落、本体论（OWL 草案、版本、验证、导出）或 Foundry IQ 图谱演示。在回答或发起调用前均可使用，即使没有 Azure 访问权限。涵盖向量/语义/BM25 搜索。不适用于其他 Azure 产品、Microsoft Graph API 或持续评估。"
version: "0.3.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "0.3.1"
---
## Intent routing

Failures first; one route. Ask if unclear.
Diagnose before setup or quality; relevance needs proven freshness.

| Intent | Load |
|---|---|
| Graphs or ontologies | `workflows/graph/graph.md` |
| Other Search requests | [Azure AI Search documentation](https://learn.microsoft.com/en-us/azure/search/), using [context](references/context-resolution.md) and the shared rules below |

Use official documentation and shared guidance for Search requests.
Cleanup follows [shared safety](references/safety-and-idempotency.md#scenario-cleanup).

## Shared rules

Read [HTTP](references/http-contract.md), [versions](references/api-version-policy.md), [safety](references/safety-and-idempotency.md); return [handoff](references/output-contract.md). Resolve/reuse `managementApiVersion`/`dataApiVersion` before requests.
For errors, provisioning/429, or private access/DNS/connectivity, use [errors](references/error-taxonomy.md), [limits](references/limits-and-capacity.md) and [networking](references/networking.md).

For protected content, source access, or permission changes, load the matching
[source security section](references/source-security.md).
Keep caller, Search outbound identity, and end-user authorization distinct.
Entra/least privilege/reuse; approve billable/permission/network/production/destructive/credential/data-movement. No data/secrets.

