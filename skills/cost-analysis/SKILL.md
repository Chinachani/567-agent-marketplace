---
name: "cost-analysis"
description: "分析实际 Azure 开销、账单异常变动以及 AKS 或 AI 服务成本。适用场景包括：查询 Azure 费用明细、排查高成本资源、分析账单上涨或成本激增原因、核实意外扣费、分析 Cosmos DB 费用、Foundry 模型成本、AKS 集群与命名空间费用，以及启用 AKS 成本分析或排查 AKS 闲置容量。不适用于：成本预测、定价预估、规格优化（Rightsizing）、预留承诺折扣管理或预算设定。"
version: "1.1.1"
license: "MIT"
metadata:
  author: Microsoft
  version: "1.1.1"
---
# Azure Cost Analysis

## Quick Reference

| Intent | Workflow | Primary tools |
|--------|----------|---------------|
| Query historical spend | [Cost query](references/cost-query/workflow.md) | `query_costs` |
| Explain a spike | [Cost investigation](references/cost-investigation.md) | `query_costs`, Resource Graph |
| Analyze AKS spend | [AKS cost analysis](references/aks-cost-analysis.md) | `query_aks_costs`, Resource Graph |
| Analyze AI service spend | [AI cost analysis](references/ai-cost-analysis.md) | `query_costs` |

## When to Use This Skill

Use for spend, anomalies, and AKS or AI allocation.

## MCP Tools

Use cost tools and Resource Graph first. If an operation is unavailable, follow
[fallback and safety](references/tools-and-safety.md).

## Workflow

1. Confirm scope, period, currency, and breakdown.
2. Load only the matching workflow above.
3. Never transform MCP results in a shell or interpreter; request tool-side
   totals, grouping, sorting, or bounded follow-up queries.
4. Respect row limits and label incomplete data.
5. Separate measured cost from inferred causes and recommendations.

## Error Handling

| Error | Action |
|-------|--------|
| Access denied | Name the required scope and role. |
| Empty result | Distinguish no data from unavailable data. |
| Multiple currencies | Report each currency separately. |
| Server error | Retry once; then stop with the trace ID. |

