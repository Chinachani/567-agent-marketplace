---
name: "azure-advisor-cost-optimization"
description: "分析 Azure Advisor Cost/IdleResources 检测结果并预验证删除安全性，包括 Service Groups。适用场景：“查找未使用的 Azure 资源”、“哪些资源我正在付费但已不再使用”、“闲置资源节省”、“历史闲置资源节省”、“这些闲置资源是否可以安全删除”。通用 Cost、其他子类别和跨类别请求请使用 azure-advisor。"
version: "1.0.11"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.0.11"
---
# Azure Advisor Cost Optimization

Use existing Advisor tools only with `category=Cost` and `sub-category=IdleResources`.
Never substitute billing, inventory or runtime KQL. Preserve selected scope, type and tenant;
pass supplied identities unchanged.

## Shared rules

Use only returned structured retail savings; MCP owns calculations. Never annualize,
reconstruct amounts from dates, or fall back to legacy annualSavingsAmount/savingsAmount
or raw pricing. Cost is accumulated Advisor cost, not monthly spend or yearly savings.
Completed reports use Realized savings.
Every monetary answer or proposal visibly shows Currency and `Pricing basis: <basis>`
from the calculated measure or its documented source. Missing amounts are Unavailable,
not zero; numeric zero stays zero. Preserve a known basis even when amounts are missing.
Potential savings depend on validating and deleting eligible resources. Estimates do not
establish inactivity or safe deletion and never authorize remediation.

## Workflow

Before each flow, read its matching references below, including when using supplied results.
Before scoped calls, read [Scope resolution](references/scope-resolution.md).
Reuse already loaded references.
If a required file is unavailable, report it and stop the affected flow.

Use the matching scenario guidance; [Reference index](references/README.md).

## Quick reference

| Flow | Required reference |
|---|---|
| Discovery and type expansion | [Workflow](references/workflow.md) |
| Counts, savings field mapping and pricing-source interpretation | [Output and savings](references/output-and-savings.md) |
| Tables and selected resources | [Table format](references/table-format.md) |
| Completed/historical reports | [Lifecycle](references/lifecycle.md) |
| State changes | [State updates](references/state-updates.md) |
| Selection/remediation handoff | [Selection](references/selection-and-handoff.md) |
| Explicit prevalidation/safety checks | [Selection](references/selection-and-handoff.md#read-only-prevalidation) |
| Filters/errors | [Tools and recovery](references/tools-and-recovery.md) |
| Routing examples | [Examples](references/examples.md) |

## Response guidance

Use shared headings and column order across models, with documented scope/lifecycle variations.
Visibly show results/proposals before dependent questions; reasoning, tool output or text
inside `ask_user` does not count. Ask directly for missing input.

